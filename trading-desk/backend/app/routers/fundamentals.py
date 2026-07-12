"""Fundamental health endpoint."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, func, and_

from app.database import get_session_sync
from app.models import FundamentalSnapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/fundamentals", tags=["fundamentals"])


@router.get("/{ticker}")
async def get_fundamentals(ticker: str) -> dict[str, Any]:
    """Get the latest fundamental snapshot for a ticker."""
    session = get_session_sync()
    try:
        row = session.execute(
            select(FundamentalSnapshot)
            .where(FundamentalSnapshot.ticker == ticker.upper())
            .order_by(FundamentalSnapshot.as_of_date.desc())
            .limit(1)
        ).scalars().first()

        if not row:
            raise HTTPException(status_code=404, detail=f"No fundamental data for {ticker}")

        return row.to_dict()
    finally:
        session.close()
