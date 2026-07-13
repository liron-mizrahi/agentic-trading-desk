"""Backtest API endpoints for running and retrieving backtests."""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from sqlalchemy import text

from app.database import _get_async_sessionmaker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    strategy: str = "three_pillar"  # three_pillar | momentum_dip | squeeze | all
    start_date: str = "2024-01-01"
    end_date: str = "2025-12-31"
    sectors: list[str] | None = None
    benchmark: str = "SPY"
    capital: float = 100_000.0


@router.get("/results")
async def list_backtest_results(
    strategy: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """List saved backtest results, optionally filtered by strategy."""
    async with _get_async_sessionmaker()() as db:
        query = "SELECT * FROM backtest_results"
        bind: dict[str, Any] = {}
        
        if strategy:
            query += " WHERE strategy = :strategy"
            bind["strategy"] = strategy
        
        query += " ORDER BY created_at DESC LIMIT :lim"
        bind["lim"] = limit
        
        result = await db.execute(text(query), bind)
        rows = result.fetchall()
        
        def _r(row):
            m = row._mapping
            return {
                "id": m["id"],
                "strategy": m["strategy"],
                "start_date": str(m["start_date"]) if m["start_date"] else None,
                "end_date": str(m["end_date"]) if m["end_date"] else None,
                "sectors": m["sectors"],
                "total_return_pct": m["total_return_pct"],
                "annualized_return_pct": m["annualized_return_pct"],
                "benchmark_return_pct": m["benchmark_return_pct"],
                "sharpe_ratio": m["sharpe_ratio"],
                "max_drawdown_pct": m["max_drawdown_pct"],
                "win_rate_pct": m["win_rate_pct"],
                "total_trades": m["total_trades"],
                "equity_curve": m["equity_curve"],
                "benchmark_curve": m["benchmark_curve"],
                "trades": m["trades"],
                "metrics": m["metrics"],
                "created_at": str(m["created_at"]) if m["created_at"] else None,
            }
        
        return {"results": [_r(r) for r in rows]}


@router.get("/results/{result_id}")
async def get_backtest_result(result_id: int):
    """Get a single backtest result by ID with full details."""
    async with _get_async_sessionmaker()() as db:
        result = await db.execute(
            text("SELECT * FROM backtest_results WHERE id = :id"), {"id": result_id}
        )
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Backtest result not found")
        m = row._mapping
        return {
            "id": m["id"],
            "strategy": m["strategy"],
            "start_date": str(m["start_date"]),
            "end_date": str(m["end_date"]),
            "sectors": m["sectors"],
            "total_return_pct": m["total_return_pct"],
            "annualized_return_pct": m["annualized_return_pct"],
            "benchmark_return_pct": m["benchmark_return_pct"],
            "alpha_pct": m["alpha_pct"],
            "sharpe_ratio": m["sharpe_ratio"],
            "max_drawdown_pct": m["max_drawdown_pct"],
            "calmar_ratio": m["calmar_ratio"],
            "win_rate_pct": m["win_rate_pct"],
            "profit_factor": m["profit_factor"],
            "total_trades": m["total_trades"],
            "avg_hold_days": m["avg_hold_days"],
            "equity_curve": m["equity_curve"],
            "benchmark_curve": m["benchmark_curve"],
            "trades": m["trades"],
            "metrics": m["metrics"],
            "created_at": str(m["created_at"]),
        }


@router.post("/run")
async def run_backtest(req: BacktestRequest):
    """Trigger a new backtest run. Returns the run ID for polling."""
    import asyncio
    import os
    
    # scripts/ is mounted at /scripts in Docker; fallback for local dev
    script_dir = "/scripts" if os.path.isdir("/scripts") else os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "..", "..", "scripts"
    )
    workspace = script_dir
    
    cmd = [
        sys.executable,
        os.path.join(script_dir, "backtester.py"),
        req.strategy,
        "--start", req.start_date,
        "--end", req.end_date,
        "--benchmark", req.benchmark,
        "--capital", str(req.capital),
        "--json",
    ]
    
    if req.sectors:
        cmd += ["--sectors", ",".join(req.sectors)]
    
    logger.info(f"Running backtest: {' '.join(cmd)}")
    
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workspace,
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Backtest failed: {stderr.decode()[:500]}"
            )
        
        result = json.loads(stdout.decode())
        
        # Get the most recent DB entry
        async with _get_async_sessionmaker()() as db:
            row_result = await db.execute(
                text("SELECT id FROM backtest_results ORDER BY created_at DESC LIMIT 1")
            )
            row = row_result.fetchone()
        
        return {
            "status": "complete",
            "result_id": row[0] if row else None,
            "results": result,
        }
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Failed to parse backtest output")
    except Exception as e:
        logger.exception("Backtest execution failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies")
async def list_strategies():
    """List available backtest strategies with metadata."""
    return {
        "strategies": [
            {
                "id": "three_pillar",
                "name": "Three-Pillar Framework",
                "description": "Trend + Momentum + Macro-Sentiment scoring (-6 to +6)",
                "type": "trend_momentum",
                "default_sectors": ["Technology"],
            },
            {
                "id": "momentum_dip",
                "name": "Momentum-Dip Catalyst",
                "description": "RSI-2 oversold mean reversion with sector-adapted thresholds",
                "type": "mean_reversion",
                "default_sectors": ["Technology", "Healthcare", "Energy"],
            },
            {
                "id": "squeeze",
                "name": "Bollinger Squeeze Breakout",
                "description": "Volatility contraction → expansion breakout with momentum confirmation",
                "type": "volatility",
                "default_sectors": ["Technology", "Financial Services", "Industrials"],
            },
            {
                "id": "all",
                "name": "All Strategies",
                "description": "Run all three strategies and compare performance",
                "type": "comparison",
                "default_sectors": ["Technology"],
            },
        ]
    }


@router.get("/sectors")
async def list_sectors():
    """List available sectors for backtesting."""
    return {
        "sectors": [
            {"id": "Technology", "name": "Technology", "etf": "XLK"},
            {"id": "Financial Services", "name": "Financial Services", "etf": "XLF"},
            {"id": "Healthcare", "name": "Healthcare", "etf": "XLV"},
            {"id": "Consumer Cyclical", "name": "Consumer Cyclical", "etf": "XLY"},
            {"id": "Industrials", "name": "Industrials", "etf": "XLI"},
            {"id": "Communication", "name": "Communication", "etf": "XLC"},
            {"id": "Energy", "name": "Energy", "etf": "XLE"},
            {"id": "Consumer Defensive", "name": "Consumer Defensive", "etf": "XLP"},
            {"id": "Basic Materials", "name": "Basic Materials", "etf": "XLB"},
            {"id": "Real Estate", "name": "Real Estate", "etf": "XLRE"},
            {"id": "Utilities", "name": "Utilities", "etf": "XLU"},
        ]
    }
