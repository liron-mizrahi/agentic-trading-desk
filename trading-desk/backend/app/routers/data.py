"""Market data endpoint — IBKR primary, yfinance fallback."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from app.data_adapter import fetch_ohlcv

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/data", tags=["data"])


@router.get("/{ticker}/ohlcv")
async def get_ohlcv(
    ticker: str,
    period: str = Query("5y", description="1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, max"),
) -> dict[str, Any]:
    """Fetch OHLCV data — tries IBKR first, falls back to yfinance."""
    ticker = ticker.strip().upper()
    if not ticker.isalpha() or len(ticker) > 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid ticker: '{ticker}'",
        )

    try:
        bars, source = fetch_ohlcv(ticker, period)
        if not bars:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No data for {ticker}",
            )
        return {"ticker": ticker, "period": period, "source": source, "bars": len(bars), "data": bars}

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Data fetch failed for %s: %s", ticker, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Data fetch failed for {ticker}",
        )
