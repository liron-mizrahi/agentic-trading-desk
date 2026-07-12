#!/usr/bin/env python3
"""
Celery app + tasks for the Agent Layer.

Tasks:
  task_run_daily_screener        — Celery Beat scheduled at 23:00 Mon-Fri
  task_execute_openclaw_analysis — 3-step Momentum-Dip funnel
  task_execute_broker_order      — Idempotent order execution

Retry policy: exponential backoff (max 3 retries) → Dead Letter Queue.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import redis as redis_module
from celery import Celery, signals
from celery.exceptions import MaxRetriesExceededError

from celery.schedules import crontab

from agent.config import (
    CELERY_BROKER_URL,
    CELERY_RESULT_BACKEND,
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DB,
    REDIS_PUBSUB_CHANNEL,
    BEAT_SCREENER_HOUR,
    BEAT_SCREENER_MINUTE,
)

logger = logging.getLogger(__name__)

celery_app = Celery(
    "agent",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=False,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
)

celery_app.conf.beat_schedule = {
    "run-daily-screener": {
        "task": "agent.tasks.task_run_daily_screener",
        "schedule": crontab(hour=BEAT_SCREENER_HOUR, minute=BEAT_SCREENER_MINUTE, day_of_week="mon-fri"),
        "options": {"expires": 3600},
    },
}

# ── Redis Pub/Sub ─────────────────────────────────────────────────────

_redis_client: Optional[redis_module.Redis] = None


def _get_redis() -> redis_module.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis_module.Redis(
            host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True
        )
    return _redis_client


def _emit_event(event_type: str, payload: dict) -> None:
    try:
        r = _get_redis()
        msg = json.dumps({
            "type": event_type,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        r.publish(REDIS_PUBSUB_CHANNEL, msg)
        logger.info("Emitted %s on channel %s", event_type, REDIS_PUBSUB_CHANNEL)
    except Exception as exc:
        logger.error("Failed to emit event %s: %s", event_type, exc)


def _handle_dead_letter(ticker: str, error: str, retry_count: int) -> None:
    logger.error("DEAD LETTER [%s] after %d retries: %s", ticker, retry_count, error)
    from agent.database import get_session
    from agent.models import AnalysisLog

    session = get_session()
    try:
        log_entry = AnalysisLog(
            ticker=ticker,
            error_message=f"DEAD LETTER: {error}",
            retry_count=retry_count,
            dead_letter=True,
        )
        session.add(log_entry)
        session.commit()
    except Exception as exc:
        logger.error("DLQ DB write failed: %s", exc)
        session.rollback()
    finally:
        session.close()

    _emit_event("SYSTEM_WARNING", {
        "message": f"Analysis failed for {ticker} after {retry_count} retries",
        "error": error,
        "ticker": ticker,
    })


# ── Worker startup ────────────────────────────────────────────────────

@signals.worker_ready.connect
def _worker_ready(sender=None, **kwargs):
    from agent.database import init_db
    try:
        init_db()
        logger.info("Worker ready — DB initialized")
    except Exception as exc:
        logger.error("Worker init — DB init failed: %s", exc)


# ── Task: Daily Screener ─────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="agent.tasks.task_run_daily_screener",
    max_retries=0,
    acks_late=True,
)
def task_run_daily_screener(self):
    logger.info("task_run_daily_screener: starting daily scan...")

    from agent.config import DEFAULT_SECTOR
    from agent.screener import run_screener

    candidates = run_screener(sector=DEFAULT_SECTOR)
    total = len(candidates)
    logger.info("task_run_daily_screener: %d candidates from %s", total, DEFAULT_SECTOR)

    for c in candidates:
        task_execute_openclaw_analysis.delay(c["ticker"])

    _emit_event("DAILY_SCREENER_COMPLETE", {
        "sector": DEFAULT_SECTOR,
        "candidates": total,
        "tickers": [c["ticker"] for c in candidates],
    })

    return {"status": "complete", "sector": DEFAULT_SECTOR, "candidates": total}


# ── Task: OpenClaw Analysis ──────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="agent.tasks.task_execute_openclaw_analysis",
    max_retries=3,
    default_retry_delay=5,
    acks_late=True,
    autoretry_for=(ConnectionError, TimeoutError, OSError),
)
def task_execute_openclaw_analysis(self, ticker: str):
    from agent.database import get_session
    from agent.models import AnalysisLog, Trade

    session = get_session()
    trade: Optional[Trade] = None

    try:
        from agent.pipeline import run_momentum_dip_analysis
        result = run_momentum_dip_analysis(ticker)

        steps = result.get("steps", [])
        # Step mapping: 1=DataFetch, 2/3/4=RSI+CHOP+SMA200, 5=LLM
        step1 = any(s.get("passed") for s in steps if s.get("step") == 1)
        step2 = any(s.get("passed") for s in steps if s.get("step") in (2, 3, 4))
        step3 = any(s.get("passed") for s in steps if s.get("step") == 5)
        all_passed = all(
            s.get("passed") for s in steps if s.get("step") in (2, 3, 4, 5)
        ) if steps else False

        llm_result = result.get("llm_result")
        indicators = result.get("indicators", {})

        log_entry = AnalysisLog(
            ticker=ticker,
            step1_passed=step1,
            step2_passed=step2,
            step3_passed=all_passed,
            rsi2=indicators.get("rsi2"),
            chop=indicators.get("chop"),
            sma200=indicators.get("sma200"),
            price=indicators.get("price"),
            llm_decision=llm_result.get("decision") if llm_result else None,
            llm_confidence=llm_result.get("confidence") if llm_result else None,
            raw_llm_reasoning=llm_result.get("reasoning") if llm_result else None,
            error_message=result.get("error"),
            retry_count=self.request.retries,
        )
        session.add(log_entry)
        session.flush()

        proposal = result.get("proposal")
        if proposal and proposal.get("decision") == "BUY":
            trade = Trade(
                ticker=ticker,
                strategy="momentum_dip",
                decision="BUY",
                confidence=proposal.get("confidence"),
                reasoning=proposal.get("reasoning"),
                proposed_price=proposal.get("entry_price"),
                position_size_pct=proposal.get("position_size_pct"),
                exit_condition=proposal.get("exit_condition"),
                stop_loss=proposal.get("stop_loss"),
                take_profit=proposal.get("take_profit"),
                risk_reward_ratio=proposal.get("risk_reward_ratio"),
                status="PENDING",
                sector=proposal.get("sector"),
                rsi_2_value=proposal.get("rsi2_value"),
                chop_value=proposal.get("chop_value"),
                sma_200_value=proposal.get("sma200_value"),
            )
            session.add(trade)
            session.flush()

            # Link log to trade
            log_entry.trade_id = trade.id

            event_payload = {
                "trade_id": trade.id,
                "ticker": ticker,
                "decision": "BUY",
                "confidence": proposal.get("confidence"),
                "proposed_price": proposal.get("entry_price"),
                "stop_loss": proposal.get("stop_loss"),
                "take_profit": proposal.get("take_profit"),
                "risk_reward_ratio": proposal.get("risk_reward_ratio"),
            }
            session.commit()
            _emit_event("NEW_PROPOSAL", event_payload)
            logger.info("BUY proposal created for %s (trade_id=%s)", ticker, trade.id)
        else:
            session.commit()
            _emit_event("ANALYSIS_COMPLETE", {
                "ticker": ticker,
                "decision": llm_result.get("decision", "NO_TRADE") if llm_result else "NO_TRADE",
            })

        return {
            "ticker": ticker,
            "status": "complete",
            "decision": llm_result.get("decision") if llm_result else "NO_TRADE",
            "trade_id": trade.id if trade else None,
        }

    except MaxRetriesExceededError:
        _handle_dead_letter(ticker, "Max retries exceeded (3 attempts)", 3)
        session.rollback()
        return {"ticker": ticker, "status": "dead_letter", "error": "Max retries exceeded"}

    except Exception as exc:
        session.rollback()
        logger.error("Analysis failed for %s: %s", ticker, exc)
        retry_count = self.request.retries
        if retry_count < 3:
            delay = min(5 * (2 ** retry_count), 60)
            logger.warning("Retrying %s (attempt %d/3) in %ds...", ticker, retry_count + 1, delay)
            raise self.retry(exc=exc, countdown=delay)
        else:
            _handle_dead_letter(ticker, str(exc), retry_count + 1)
            return {"ticker": ticker, "status": "dead_letter", "error": str(exc)}
    finally:
        session.close()


# ── Task: Execute Broker Order ───────────────────────────────────────

@celery_app.task(
    bind=True,
    name="agent.tasks.task_execute_broker_order",
    max_retries=0,
    acks_late=True,
)
def task_execute_broker_order(self, trade_id: str):
    from agent.database import get_session
    from agent.models import Trade

    session = get_session()
    try:
        # Use UUID comparison — trade_id is a UUID string
        trade = session.query(Trade).filter(Trade.id == trade_id).first()
        if trade is None:
            logger.error("Order execution: trade %s not found", trade_id)
            return {"status": "error", "message": f"Trade {trade_id} not found"}

        if trade.status == "EXECUTED":
            logger.info("Order execution: trade %s already EXECUTED (idempotent skip)", trade_id)
            return {"status": "skipped", "message": "Already executed", "trade_id": trade_id}

        if trade.status != "APPROVED":
            logger.warning(
                "Order execution: trade %s status is %s (need APPROVED)",
                trade_id, trade.status,
            )
            return {"status": "error", "message": f"Trade status is {trade.status}, need APPROVED"}

        logger.info(
            "Order execution: PLACEHOLDER — would place order for %s at $%.2f",
            trade.ticker, trade.proposed_price or 0,
        )

        trade.status = "EXECUTED"
        trade.updated_at = datetime.now(timezone.utc)
        session.commit()

        _emit_event("TRADE_EXECUTED", {
            "trade_id": trade_id,
            "ticker": trade.ticker,
            "proposed_price": trade.proposed_price,
            "position_size_pct": trade.position_size_pct,
        })

        return {"status": "executed", "trade_id": trade_id, "ticker": trade.ticker}

    except Exception as exc:
        session.rollback()
        logger.error("Order execution failed for trade %s: %s", trade_id, exc)
        raise
    finally:
        session.close()
