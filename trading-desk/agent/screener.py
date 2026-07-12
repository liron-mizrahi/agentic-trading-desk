"""
Simplified daily screener for the Celery worker.
Uses yfinance to scan a predefined watchlist for Momentum-Dip candidates.

Sector focus defaults to Technology but is configurable.
Performs a basic liquidity/price sanity check before returning tickers.
"""

import logging
from typing import Optional

import yfinance as yf

from agent.config import DEFAULT_SECTOR

logger = logging.getLogger(__name__)

# Master watchlist (mirrors scripts/screener.py / scripts/momentum_dip_pipeline.py)
SECTOR_TICKERS = {
    "Technology":          ["AAPL", "MSFT", "NVDA", "GOOGL", "AVGO", "CRM", "AMD", "ADBE", "INTC", "ORCL"],
    "Financial Services":  ["JPM", "BAC", "V", "MA", "GS", "WFC", "MS", "AXP", "BLK", "SCHW"],
    "Industrials":         ["CAT", "GE", "HON", "UPS", "RTX", "BA", "DE", "LMT", "MMM", "ETN"],
    "Communication":       ["META", "NFLX", "DIS", "TMUS", "CMCSA", "CHTR", "EA", "ROKU", "SNAP"],
    "Consumer Cyclical":   ["AMZN", "TSLA", "HD", "LOW", "MCD", "SBUX", "NKE", "TJX", "TGT", "BKNG"],
    "Healthcare":          ["UNH", "LLY", "MRK", "ABBV", "PFE", "TMO", "ABT", "MDT", "SYK", "JNJ"],
    "Energy":              ["XOM", "CVX", "COP", "SLB", "OXY", "EOG", "HAL", "MPC", "VLO", "PSX"],
    "Consumer Defensive":  ["PG", "KO", "COST", "WMT", "PEP", "CL", "KMB", "GIS", "K", "SYY"],
    "Basic Materials":     ["LIN", "BHP", "APD", "RIO", "FCX", "NEM", "SHW", "DOW", "DD", "ECL"],
    "Real Estate":         ["PLD", "AMT", "CCI", "EQIX", "SPG", "O", "DLR", "AVB", "EQR", "WELL"],
    "Utilities":           ["NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "XEL", "PEG", "ED"],
}


def get_tickers_for_sector(sector: str) -> list[str]:
    """Return the watchlist tickers for a given sector name."""
    return SECTOR_TICKERS.get(sector, [])


def list_sectors() -> list[str]:
    """Return all available sector names."""
    return list(SECTOR_TICKERS.keys())


def quick_validate_ticker(ticker: str, min_price: float = 5.0, min_volume: float = 100_000.0) -> bool:
    """Quick yfinance check: does the ticker have data, price > min_price, volume > min_volume?"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
        volume = info.get("volume") or info.get("regularMarketVolume") or 0
        if price is None or price <= min_price:
            logger.debug("Screener: %s skipped — price=%.2f (min=%.2f)", ticker, price or 0, min_price)
            return False
        if volume < min_volume:
            logger.debug("Screener: %s skipped — volume=%.0f (min=%.0f)", ticker, volume, min_volume)
            return False
        return True
    except Exception as exc:
        logger.debug("Screener: %s check failed: %s", ticker, exc)
        return False


def run_screener(sector: str | None = None) -> list[dict]:
    """
    Run the screener for a given sector (or DEFAULT_SECTOR).
    Returns a list of dicts: [{"ticker": "AAPL", "sector": "Technology"}, ...]
    for tickers that pass basic validation.
    """
    target_sector = sector or DEFAULT_SECTOR
    logger.info("Screener: scanning sector '%s'...", target_sector)

    tickers = get_tickers_for_sector(target_sector)
    if not tickers:
        logger.warning("Screener: unknown sector '%s', falling back to Technology", target_sector)
        tickers = get_tickers_for_sector("Technology")

    candidates: list[dict] = []
    for ticker in tickers:
        if quick_validate_ticker(ticker):
            candidates.append({"ticker": ticker, "sector": target_sector})
            logger.info("Screener: %s passed basic validation", ticker)
        else:
            logger.info("Screener: %s did not pass validation (price/volume)", ticker)

    logger.info("Screener: %d/%d candidates passed for sector '%s'", len(candidates), len(tickers), target_sector)
    return candidates
