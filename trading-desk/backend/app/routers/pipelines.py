"""
Pipeline results endpoint — historical run data for the Pipelines page.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select, func, distinct, and_
from sqlalchemy.orm import Session

from app.database import get_session_sync
from app.models import Trade, AnalysisLog, FundamentalSnapshot, TradeStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pipelines", tags=["pipelines"])

# ── Pipeline registry (generic — add new pipelines here) ─────────────

PIPELINES = {
    "momentum_dip": {
        "name": "Momentum-Dip Catalyst",
        "description": (
            "RSI-2 mean reversion strategy. 4-step filter funnel: RSI-2 oversold (sector-adapted "
            "thresholds) → Choppiness Index < 38.2 (trending) → Price > SMA200 (uptrend) → "
            "LLM structured analysis with entry/stop/target. Exit: QS rule — close > prior high. "
            "Size reduced for volatile sectors (Tech -30%, Healthcare full size). Data: IBKR → yfinance."
        ),
        "steps": [
            {"key": "step1_passed", "label": "RSI-2 Check", "detail": "Sector-adapted RSI-2 threshold: Tech <10, Healthcare <20"},
            {"key": "step2_passed", "label": "CHOP Index", "detail": "CHOP < 38.2 = trending; > 61.8 = choppy (no trade)"},
            {"key": "step3_passed", "label": "SMA200", "detail": "Price > SMA200 confirms long-term uptrend"},
        ],
    },
    "three_pillar": {
        "name": "Three-Pillar EOD",
        "description": (
            "Systematic short-term scoring framework (−6 to +6). Three pillars: Trend (EMA 20/50/200 "
            "structure + slope), Momentum (RSI-14, MACD histogram, TRIX-15 vs signal), Macro-Sentiment "
            "(7 ETF cross-asset regime + yield curve). Decision cascade: enter on confirmed rebound → "
            "ride momentum → exit on exhaustion → wait for next trigger. Death-cross detection for tactical "
            "vs cyclical entry sizing. Capital rotation over accumulation."
        ),
        "steps": [
            {"key": "trend_passed", "label": "Trend", "detail": "EMA 20 > EMA50 > EMA200 + EMA200 slope"},
            {"key": "momentum_passed", "label": "Momentum", "detail": "RSI-14, MACD histogram polarity, TRIX-15 crossover"},
            {"key": "macro_passed", "label": "Macro", "detail": "XLF/XLE/XLK/XLV/XLY/XLU/XLP + 10Y-2Y spread"},
        ],
    },
}

# Thresholds for momentum-dip (for display context)
SECTOR_THRESHOLDS = {
    "Technology": 10, "Communication": 10,
    "Financial Services": 15, "Industrials": 15, "Energy": 15,
    "Consumer Cyclical": 15, "Basic Materials": 15,
    "Healthcare": 20, "Consumer Defensive": 20, "Utilities": 20, "Real Estate": 20,
}


# ── Helpers ───────────────────────────────────────────────────────────

def _dedup_logs(logs: list[AnalysisLog]) -> list[AnalysisLog]:
    """Keep only the latest log per ticker per run (dedup retries)."""
    seen: dict[str, AnalysisLog] = {}
    for log in sorted(logs, key=lambda l: l.created_at):
        seen[log.ticker] = log
    return list(seen.values())


def _build_symbol_result(log: AnalysisLog, trade: Trade | None, pipeline: dict) -> dict:
    """Build a single symbol result from analysis log + optional trade."""
    is_three_pillar = trade is not None and trade.strategy == "three_pillar"
    if is_three_pillar:
        return _build_three_pillar_result(log, trade, pipeline)

    threshold = SECTOR_THRESHOLDS.get(trade.sector if trade else "Technology", 10)

    steps = []
    for step_def in pipeline["steps"]:
        passed = getattr(log, step_def["key"], None)
        step_data = {
            "name": step_def["label"],
            "detail": step_def["detail"],
            "passed": passed,
        }
        # Add indicator context for known steps
        if step_def["key"] == "step1_passed":
            step_data["value"] = log.rsi2
            step_data["threshold"] = threshold
            step_data["reason"] = f"RSI-2 {log.rsi2:.2f}" if log.rsi2 else "N/A"
            step_data["reason"] += f" vs threshold {threshold}"
        elif step_def["key"] == "step2_passed":
            step_data["value"] = log.chop
            step_data["threshold"] = 38.2
            step_data["reason"] = f"CHOP {log.chop:.2f}" if log.chop else "N/A"
            step_data["reason"] += f" vs 38.2"
        elif step_def["key"] == "step3_passed":
            step_data["value"] = log.sma200
            step_data["threshold"] = log.price
            if log.sma200 and log.price:
                step_data["reason"] = f"Price ${log.price:.2f} {'>' if log.price > log.sma200 else '≤'} SMA200 ${log.sma200:.2f}"
            else:
                step_data["reason"] = "N/A"
        steps.append(step_data)

    return {
        "ticker": log.ticker,
        "strategy": "momentum_dip",
        "sector": trade.sector if trade else None,
        "steps": steps,
        "indicators": {
            "rsi2": log.rsi2,
            "chop": log.chop,
            "sma200": log.sma200,
            "price": log.price,
        },
        "decision": log.llm_decision or (trade.decision if trade else None),
        "confidence": log.llm_confidence or (trade.confidence if trade else None),
        "reasoning": (log.raw_llm_reasoning or "")[:500],
        "error": log.error_message,
        "dead_letter": log.dead_letter,
        "trade_id": str(trade.id) if trade else None,
        "trade_status": trade.status.value if trade else None,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def _build_three_pillar_result(log: AnalysisLog, trade: Trade, pipeline: dict) -> dict:
    """Build a three-pillar symbol result from analysis log + trade."""
    # Extract pillar data from JSONB technical_data
    tech = log.technical_data or {}

    trend_score = tech.get("trend_score")
    momentum_score = tech.get("momentum_score")
    macro_score = tech.get("macro_score")
    pillar_total = tech.get("pillar_total")
    framing = tech.get("framing", "")

    # Pillar pass/fail: each pillar passes if score >= 0
    pillars = {
        "trend": {
            "score": trend_score,
            "detail": tech.get("trend_detail", ""),
            "passed": trend_score is not None and trend_score >= 0,
        },
        "momentum": {
            "score": momentum_score,
            "detail": tech.get("momentum_detail", ""),
            "passed": momentum_score is not None and momentum_score >= 0,
        },
        "macro_sentiment": {
            "score": macro_score,
            "detail": tech.get("macro_detail", ""),
            "passed": macro_score is not None and macro_score >= 0,
        },
        "composite": pillar_total,
    }

    # Build steps for funnel chart (pass/fail per pillar)
    steps = []
    for step_def in pipeline["steps"]:
        passed = log.step1_passed if step_def["key"] == "trend_passed" else \
                 log.step2_passed if step_def["key"] == "momentum_passed" else \
                 log.step3_passed if step_def["key"] == "macro_passed" else None
        step_data = {
            "name": step_def["label"],
            "detail": step_def["detail"],
            "passed": passed,
        }
        # Add pillar score context
        if step_def["key"] == "trend_passed":
            step_data["value"] = trend_score
            step_data["threshold"] = 0
            step_data["reason"] = f"Trend score {trend_score:+d} (needs ≥0)" if trend_score is not None else "N/A"
        elif step_def["key"] == "momentum_passed":
            step_data["value"] = momentum_score
            step_data["threshold"] = 0
            step_data["reason"] = f"Momentum score {momentum_score:+d} (needs ≥0)" if momentum_score is not None else "N/A"
        elif step_def["key"] == "macro_passed":
            step_data["value"] = macro_score
            step_data["threshold"] = 0
            step_data["reason"] = f"Macro score {macro_score:+d} (needs ≥0)" if macro_score is not None else "N/A"
        steps.append(step_data)

    # Three-pillar specific indicators
    price = tech.get("close") or log.price
    indicators_3p = {
        "price": price,
        "rsi14": tech.get("rsi14"),
        "macd_hist": tech.get("macd_hist"),
        "trix": tech.get("trix"),
        "trix_signal": tech.get("trix_signal"),
        "ema20": tech.get("ema20"),
        "ema50": tech.get("ema50"),
        "ema200": tech.get("ema200"),
        "percent_b": tech.get("percent_b"),
    }

    # Reasoning: use trade.reasoning (where rationale is stored for three-pillar)
    reasoning = trade.reasoning or ""

    return {
        "ticker": log.ticker,
        "strategy": "three_pillar",
        "sector": trade.sector if trade else None,
        "steps": steps,
        "pillars": pillars,
        "decision_framing": framing,
        "indicators": indicators_3p,
        "decision": log.llm_decision or (trade.decision if trade else None),
        "confidence": log.llm_confidence or (trade.confidence if trade else None),
        "reasoning": reasoning[:800] if reasoning else "",
        "error": log.error_message,
        "dead_letter": log.dead_letter,
        "trade_id": str(trade.id) if trade else None,
        "trade_status": trade.status.value if trade else None,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("")
async def list_pipelines() -> list[dict]:
    """Return registered pipelines with metadata."""
    return [
        {"key": key, "name": p["name"], "description": p["description"],
         "steps": [{"label": s["label"], "detail": s["detail"]} for s in p["steps"]]}
        for key, p in PIPELINES.items()
    ]


@router.get("/dates")
async def pipeline_dates(
    strategy: str = Query("momentum_dip", description="Pipeline strategy key"),
) -> list[dict]:
    """List available execution dates with symbol counts."""
    if strategy not in PIPELINES:
        raise HTTPException(status_code=404, detail=f"Unknown pipeline: {strategy}")

    session = get_session_sync()
    try:
        # Get distinct dates with analysis log counts, filtered by strategy
        date_query = select(
            func.date(AnalysisLog.created_at).label("run_date"),
            func.count(func.distinct(AnalysisLog.ticker)).label("symbol_count"),
        ).where(AnalysisLog.dead_letter == False)

        if strategy == "three_pillar":
            date_query = date_query.join(
                Trade, AnalysisLog.trade_id == Trade.id
            ).where(Trade.strategy == "three_pillar")
        else:
            from sqlalchemy import or_
            date_query = date_query.outerjoin(
                Trade, AnalysisLog.trade_id == Trade.id
            ).where(
                or_(
                    AnalysisLog.trade_id == None,
                    Trade.strategy == "momentum_dip",
                )
            )

        rows = session.execute(
            date_query.group_by(func.date(AnalysisLog.created_at))
            .order_by(func.date(AnalysisLog.created_at).desc())
        ).all()

        return [
            {"date": str(row.run_date), "symbol_count": row.symbol_count}
            for row in rows
        ]
    finally:
        session.close()


@router.get("/runs")
async def pipeline_run(
    strategy: str = Query("momentum_dip", description="Pipeline strategy key"),
    date_str: str = Query(..., alias="date", description="Run date (YYYY-MM-DD)"),
) -> dict[str, Any]:
    """Get full pipeline run results for a given strategy + date."""
    if strategy not in PIPELINES:
        raise HTTPException(status_code=404, detail=f"Unknown pipeline: {strategy}")

    pipeline = PIPELINES[strategy]

    try:
        run_date = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {date_str}")

    session = get_session_sync()
    try:
        # Get analysis logs for this date, filtered by strategy
        next_day = run_date + timedelta(days=1)
        query = select(AnalysisLog).where(
            and_(
                AnalysisLog.created_at >= run_date,
                AnalysisLog.created_at < next_day,
                AnalysisLog.dead_letter == False,
            )
        )
        # Filter by strategy: join with trades table
        if strategy == "three_pillar":
            query = query.join(Trade, AnalysisLog.trade_id == Trade.id).where(
                Trade.strategy == "three_pillar"
            )
        else:
            # momentum_dip: include logs without trades + logs linked to momentum_dip trades
            from sqlalchemy import or_
            query = query.outerjoin(Trade, AnalysisLog.trade_id == Trade.id).where(
                or_(
                    AnalysisLog.trade_id == None,
                    Trade.strategy == "momentum_dip",
                )
            )
        query = query.order_by(AnalysisLog.created_at.desc())
        logs = session.execute(query).scalars().all()

        if not logs:
            # Check for dead-letter entries
            dl_count = session.execute(
                select(func.count(AnalysisLog.id))
                .where(
                    and_(
                        AnalysisLog.created_at >= run_date,
                        AnalysisLog.created_at < next_day,
                        AnalysisLog.dead_letter == True,
                    )
                )
            ).scalar()
            raise HTTPException(
                status_code=404,
                detail=f"No pipeline run found for {date_str}" +
                        (f" ({dl_count} dead-letter entries)" if dl_count else ""),
            )

        # Dedup retries
        deduped = _dedup_logs(list(logs))
        deduped.sort(key=lambda l: l.ticker)

        # Get associated trades
        trade_ids = [log.trade_id for log in deduped if log.trade_id]
        if trade_ids:
            trades = session.execute(
                select(Trade).where(Trade.id.in_(trade_ids))
            ).scalars().all()
            trade_map = {t.id: t for t in trades}
        else:
            trade_map = {}

        # Build results
        symbols = []
        for log in deduped:
            trade = trade_map.get(log.trade_id) if log.trade_id else None
            symbols.append(_build_symbol_result(log, trade, pipeline))

        # Merge latest fundamental snapshots
        tickers = list({s["ticker"] for s in symbols})
        if tickers:
            # Get latest snapshot per ticker using a subquery
            latest_sub = (
                select(
                    FundamentalSnapshot.ticker,
                    func.max(FundamentalSnapshot.as_of_date).label("max_date"),
                )
                .where(FundamentalSnapshot.ticker.in_(tickers))
                .group_by(FundamentalSnapshot.ticker)
                .subquery()
            )
            fund_rows = session.execute(
                select(FundamentalSnapshot)
                .join(
                    latest_sub,
                    and_(
                        FundamentalSnapshot.ticker == latest_sub.c.ticker,
                        FundamentalSnapshot.as_of_date == latest_sub.c.max_date,
                    ),
                )
            ).scalars().all()
            fund_map = {f.ticker: f.to_dict() for f in fund_rows}
        else:
            fund_map = {}

        for s in symbols:
            s["fundamentals"] = fund_map.get(s["ticker"])

        # Summary stats
        total = len(symbols)
        passed_step1 = sum(1 for s in symbols if any(
            st.get("passed") for st in s["steps"] if st["name"] == pipeline["steps"][0]["label"]
        )) if pipeline["steps"] else 0
        passed_step2 = sum(1 for s in symbols if any(
            st.get("passed") for st in s["steps"] if len(pipeline["steps"]) > 1 and st["name"] == pipeline["steps"][1]["label"]
        )) if len(pipeline["steps"]) > 1 else 0
        passed_step3 = sum(1 for s in symbols if any(
            st.get("passed") for st in s["steps"] if len(pipeline["steps"]) > 2 and st["name"] == pipeline["steps"][2]["label"]
        )) if len(pipeline["steps"]) > 2 else 0
        actionable = sum(1 for s in symbols if s["decision"] == "BUY")

        return {
            "pipeline": pipeline["name"],
            "strategy": strategy,
            "date": date_str,
            "summary": {
                "total": total,
                "passed_step1": passed_step1,
                "passed_step2": passed_step2,
                "passed_step3": passed_step3,
                "actionable": actionable,
            },
            "symbols": symbols,
        }
    finally:
        session.close()
