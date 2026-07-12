"""
Market data adapter — IBKR primary, yfinance fallback, DB cache.
Caches OHLCV data in PostgreSQL. First fetch = full pull. Subsequent = delta only.
"""

from __future__ import annotations

import json
import logging
import os
import ssl
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import create_engine, select, func, delete
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

IBKR_HOST = os.environ.get("IBKR_GATEWAY_HOST", "localhost")
IBKR_PORT = os.environ.get("IBKR_GATEWAY_PORT", "5000")
IBKR_BASE = f"https://{IBKR_HOST}:{IBKR_PORT}/v1/api"
_SSL_CTX = ssl._create_unverified_context()
_TIMEOUT = 15

# Sync engine for cache operations (lazy init to survive import-time DB outage)
_cache_engine = None
_CacheSession = None


def _get_cache_engine():
    global _cache_engine
    if _cache_engine is None:
        _cache_engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return _cache_engine


def _get_cache_session() -> Session:
    global _CacheSession
    if _CacheSession is None:
        _CacheSession = sessionmaker(bind=_get_cache_engine(), autocommit=False, autoflush=False)
    return _CacheSession()


# ── CACHE read/write ──────────────────────────────────────────────────


def _get_cached_bars(ticker: str) -> tuple[list[dict], date | None]:
    """Return cached bars and the latest cached date, or (empty, None)."""
    from app.ohlcv_model import OhlcvCache
    session = _get_cache_session()
    try:
        rows = session.execute(
            select(OhlcvCache)
            .where(OhlcvCache.ticker == ticker.upper())
            .order_by(OhlcvCache.date.asc())
        ).scalars().all()

        if not rows:
            return [], None

        latest = rows[-1].date
        bars = [r.to_dict() for r in rows]
        logger.info("Cache hit: %d bars for %s (latest=%s)", len(bars), ticker, latest)
        return bars, latest
    finally:
        session.close()


def _save_bars(ticker: str, bars: list[dict]) -> None:
    """Upsert bars into cache (ON CONFLICT do nothing)."""
    from app.ohlcv_model import OhlcvCache
    session = _get_cache_session()
    try:
        for bar in bars:
            try:
                bar_date = date.fromisoformat(bar["time"])
            except (ValueError, KeyError):
                continue
            existing = session.get(OhlcvCache, (ticker.upper(), bar_date))
            if existing:
                existing.open = bar["open"]
                existing.high = bar["high"]
                existing.low = bar["low"]
                existing.close = bar["close"]
                existing.volume = bar["volume"]
            else:
                session.add(OhlcvCache(
                    ticker=ticker.upper(),
                    date=bar_date,
                    open=float(bar["open"]),
                    high=float(bar["high"]),
                    low=float(bar["low"]),
                    close=float(bar["close"]),
                    volume=int(bar["volume"]),
                ))
        session.commit()
        logger.info("Cache saved: %d bars for %s", len(bars), ticker)
    except Exception as exc:
        session.rollback()
        logger.error("Cache save failed for %s: %s", ticker, exc)
    finally:
        session.close()


# ── IBKR / yfinance fetch ─────────────────────────────────────────────


def _ibkr_req(method: str, path: str, data: dict | None = None) -> dict:
    url = f"{IBKR_BASE}{path}"
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        return {"error": str(exc)}


def _ibkr_conid(symbol: str) -> int | None:
    result = _ibkr_req("GET", f"/trsrv/stocks?symbols={symbol}")
    stocks = result.get(symbol, []) or []
    if isinstance(stocks, dict):
        stocks = [stocks]
    if not stocks:
        return None
    for s in stocks:
        contracts = s.get("contracts", [])
        if isinstance(contracts, list) and contracts:
            return contracts[0].get("conid") if isinstance(contracts[0], dict) else None
    return None


def _ibkr_historicals(conid: int, period: str = "5y") -> list[dict] | None:
    result = _ibkr_req(
        "GET",
        f"/iserver/marketdata/history?conid={conid}&period={period}&bar=1d&outsideRth=false",
    )
    if "error" in result:
        return None
    data = result.get("data", [])
    if not data:
        return None
    bars = []
    for d in data:
        try:
            # IBKR returns epoch milliseconds; convert to ISO date string
            epoch_ms = d.get("t", 0)
            if epoch_ms and epoch_ms > 1000000000000:
                dt = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
                time_str = dt.strftime("%Y-%m-%d")
            else:
                time_str = ""
            bars.append({
                "time": time_str,
                "open": float(d.get("o", 0)), "high": float(d.get("h", 0)),
                "low": float(d.get("l", 0)), "close": float(d.get("c", 0)),
                "volume": int(d.get("v", 0)),
            })
        except (ValueError, TypeError):
            continue
    return bars if bars else None


def _yfinance_historicals(ticker: str, period: str = "5y") -> list[dict]:
    import yfinance as yf
    stock = yf.Ticker(ticker)
    df = stock.history(period=period)
    bars = []
    for idx, row in df.iterrows():
        bars.append({
            "time": str(idx.date()),
            "open": float(row["Open"]), "high": float(row["High"]),
            "low": float(row["Low"]), "close": float(row["Close"]),
            "volume": int(row["Volume"]),
        })
    return bars


# ── Public API ─────────────────────────────────────────────────────────


def fetch_ohlcv(ticker: str, period: str = "5y") -> tuple[list[dict], str]:
    """
    Fetch OHLCV with caching.
    First call fetches full history from IBKR/yfinance and caches it.
    Subsequent calls return cached + fetch only new bars since last cached date.
    """
    ticker = ticker.upper()

    # Check cache first
    cached, latest_date = _get_cached_bars(ticker)

    if cached and latest_date:
        # Determine how many new bars we need
        days_since = (date.today() - latest_date).days
        if days_since <= 0:
            logger.info("Cache fresh: %s (latest=%s)", ticker, latest_date)
            return cached, "cache"

        # Fetch only new bars (1mo to be safe, or exactly days_since)
        fetch_period = "1mo"
        logger.info("Cache stale by %d days, fetching delta for %s...", days_since, ticker)

        new_bars = _ibkr_data(ticker, fetch_period) or _yfinance_historicals(ticker, fetch_period)
        if new_bars:
            # Filter to only bars newer than latest_date
            new_bars = [b for b in new_bars if b["time"] > latest_date.isoformat()]
            if new_bars:
                cached.extend(new_bars)
                _save_bars_to_db(ticker, new_bars)
                logger.info("Cache updated: +%d new bars for %s", len(new_bars), ticker)

        return cached, "cache+delta"

    # No cache — full fetch from IBKR → yfinance
    logger.info("No cache for %s, full fetch...", ticker)
    bars = _ibkr_data(ticker, period)
    source = "ibkr"
    if not bars:
        logger.info("IBKR unavailable, falling back to yfinance")
        bars = _yfinance_historicals(ticker, period)
        source = "yfinance"

    if bars:
        _save_bars_to_db(ticker, bars)

    return bars, source


def _ibkr_data(ticker: str, period: str = "5y") -> list[dict] | None:
    conid = _ibkr_conid(ticker)
    if not conid:
        return None
    return _ibkr_historicals(conid, period)


def _save_bars_to_db(ticker: str, bars: list[dict]) -> None:
    from app.ohlcv_model import OhlcvCache
    session = _get_cache_session()
    try:
        for bar in bars:
            try:
                bar_date = date.fromisoformat(bar["time"])
            except (ValueError, KeyError):
                continue
            existing = session.get(OhlcvCache, (ticker, bar_date))
            if existing:
                existing.open = bar["open"]
                existing.high = bar["high"]
                existing.low = bar["low"]
                existing.close = bar["close"]
                existing.volume = bar["volume"]
            else:
                session.add(OhlcvCache(
                    ticker=ticker,
                    date=bar_date,
                    open=float(bar["open"]),
                    high=float(bar["high"]),
                    low=float(bar["low"]),
                    close=float(bar["close"]),
                    volume=int(bar["volume"]),
                ))
        session.commit()
        logger.info("DB cache: saved %d bars for %s", len(bars), ticker)
    except Exception as exc:
        session.rollback()
        logger.error("DB cache save failed for %s: %s", ticker, exc)
    finally:
        session.close()
