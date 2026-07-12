"""Analysis endpoints — trigger and retrieve pipeline results."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_client import celery_app
from app.database import get_db
from app.models import AnalysisLog, Trade

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["analysis"])


@router.post("/analyze")
async def request_analysis(payload: dict[str, str]) -> dict[str, Any]:
    """Enqueue an on-demand analysis task for a ticker."""
    ticker = (payload.get("ticker") or "").strip().upper()

    if not ticker:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="'ticker' is required")
    if not ticker.isalpha() or len(ticker) > 10:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid ticker: '{ticker}'")

    try:
        task = celery_app.send_task("agent.tasks.task_execute_openclaw_analysis", args=[ticker])
        logger.info("Enqueued analysis for %s (task %s)", ticker, task.id)
    except Exception:
        logger.exception("Failed to enqueue analysis for %s", ticker)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Analysis service unavailable.")

    return {"status": "queued", "ticker": ticker, "task_id": task.id}


@router.get("/analysis/{ticker}")
async def get_analysis(
    ticker: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get the latest pipeline analysis for a ticker."""
    ticker = ticker.strip().upper()

    # Latest analysis log
    stmt = select(AnalysisLog).where(AnalysisLog.ticker == ticker).order_by(desc(AnalysisLog.created_at)).limit(1)
    result = await db.execute(stmt)
    log: AnalysisLog | None = result.scalar_one_or_none()

    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No analysis found for {ticker}")

    # Associated trade (if any)
    trade_data = None
    if log.trade_id:
        trade_result = await db.execute(select(Trade).where(Trade.id == log.trade_id))
        trade: Trade | None = trade_result.scalar_one_or_none()
        if trade:
            trade_data = trade.to_dict()

    return {
        "ticker": log.ticker,
        "analysis": log.to_dict(),
        "trade": trade_data,
    }


@router.get("/analysis")
async def list_analyses(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List recent analyses."""
    stmt = select(AnalysisLog).order_by(desc(AnalysisLog.created_at)).offset(offset).limit(limit)
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return [log.to_dict() for log in logs]
