"""Trade REST endpoints — pending, list, detail, action (approve/reject)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_client import celery_app
from app.database import get_db
from app.models import Trade, TradeStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/trades", tags=["trades"])


@router.get("")
async def list_trades(
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    stmt = select(Trade).order_by(Trade.created_at.desc())

    if status_filter:
        try:
            ts = TradeStatus(status_filter.upper())
            stmt = stmt.where(Trade.status == ts)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status: {status_filter}. Valid: {[s.value for s in TradeStatus]}",
            )

    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    trades = result.scalars().all()
    return [t.to_dict() for t in trades]


@router.get("/pending")
async def get_pending_trades(
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    stmt = (
        select(Trade)
        .where(Trade.status == TradeStatus.PENDING)
        .order_by(Trade.created_at.desc())
    )
    result = await db.execute(stmt)
    trades = result.scalars().all()
    return [t.to_dict() for t in trades]


@router.get("/{trade_id}")
async def get_trade(
    trade_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    trade: Trade | None = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trade {trade_id} not found",
        )

    resp = trade.to_dict()
    resp["analysis_logs"] = [log.to_dict() for log in trade.analysis_logs]
    return resp


@router.post("/{trade_id}/action")
async def approve_or_reject_trade(
    trade_id: str,
    payload: dict[str, str],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    action = payload.get("action", "").strip().upper()
    if action not in ("APPROVE", "REJECT"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="action must be 'APPROVE' or 'REJECT'",
        )

    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    trade: Trade | None = result.scalar_one_or_none()

    if not trade:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trade {trade_id} not found",
        )

    if trade.status != TradeStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Trade {trade_id} is '{trade.status.value}'; only PENDING trades can be actioned.",
        )

    if action == "APPROVE":
        trade.status = TradeStatus.APPROVED
        await db.commit()

        try:
            celery_app.send_task(
                "agent.tasks.task_execute_broker_order",
                args=[trade_id],
            )
            logger.info("Enqueued task_execute_broker_order for %s", trade_id)
        except Exception:
            logger.exception("Failed to enqueue execution for %s", trade_id)

        return {
            "status": "ok",
            "trade_id": trade_id,
            "new_status": TradeStatus.APPROVED.value,
            "message": "Trade approved and queued for execution.",
        }

    trade.status = TradeStatus.REJECTED
    trade.human_feedback = payload.get("feedback")
    await db.commit()

    return {
        "status": "ok",
        "trade_id": trade_id,
        "new_status": TradeStatus.REJECTED.value,
        "message": "Trade rejected.",
    }
