#!/usr/bin/env python3
"""
finny_imports.py
================
Adapter bridge between Finny Investment Agent tools and the Agentic Trading Desk.

Imports and wraps:
  - stocktwits_collector.py  — Social sentiment from StockTwits API (free, no key)
  - sec_reader.py            — SEC EDGAR filings scanner (XBRL + HTML)

Both tools live in ~/.openclaw/finance-workspace/ and use finny_utils.py
for DB, logging, and locking. This adapter provides standalone wrappers
that work without the Finny DB infrastructure.

Usage:
  python3 scripts/finny_imports.py stocktwits NVDA      # StockTwits sentiment for NVDA
  python3 scripts/finny_imports.py stocktwits trending   # Trending tickers
  python3 scripts/finny_imports.py sec AAPL              # Latest 10-Q for AAPL
  python3 scripts/finny_imports.py sec AAPL --annual     # Latest 10-K
  python3 scripts/finny_imports.py sec AAPL --numbers    # Financial numbers only
"""

from __future__ import annotations

import json
import os
import sys
import importlib.util
from typing import Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FINNY_DIR = os.path.join(
    os.path.dirname(SCRIPT_DIR), "..", "..", "finance-workspace"
)

# Resolve canonical path
if not os.path.isdir(FINNY_DIR):
    FINNY_DIR = os.path.expanduser("~/.openclaw/finance-workspace")


def _import_finny_module(name: str):
    """Import a Python module from the Finny workspace."""
    path = os.path.join(FINNY_DIR, f"{name}.py")
    if not os.path.exists(path):
        return None

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return None

    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── StockTwits Adapter ────────────────────────────────────────────────

def fetch_stocktwits_sentiment(ticker: str) -> Optional[dict]:
    """Fetch StockTwits sentiment for a single ticker.

    Returns:
      {
        "ticker": str,
        "score": float in [-1, +1],     # normalized bull/bear ratio
        "total_messages": int,
        "bullish": int,
        "bearish": int,
        "watchlist_count": int,
        "source": "stocktwits"
      }
    """
    st = _import_finny_module("stocktwits_collector")
    if st is None:
        return None

    try:
        result = st.collect_ticker(ticker.upper())
        if result is None:
            return None

        return {
            "ticker": result["ticker"],
            "score": result["st_score"],
            "total_messages": result["total_messages"],
            "bullish": result["bullish"],
            "bearish": result["bearish"],
            "bull_ratio": result.get("bull_ratio", 0),
            "watchlist_count": result.get("watchlist_count", 0),
            "source": "stocktwits",
        }
    except Exception:
        return None


def fetch_stocktwits_trending() -> list[dict]:
    """Fetch trending tickers from StockTwits.

    Returns list of {symbol, watchlist_count, title}.
    """
    st = _import_finny_module("stocktwits_collector")
    if st is None:
        return []

    try:
        trending = st.fetch_trending(10)
        return [
            {
                "ticker": s.get("symbol", "?"),
                "watchlist_count": s.get("watchlist_count", 0),
                "title": s.get("title", ""),
            }
            for s in trending
        ]
    except Exception:
        return []


# ── SEC Reader Adapter ────────────────────────────────────────────────

def fetch_sec_filing(ticker: str, filing_type: str = "10-Q") -> Optional[dict]:
    """Fetch and parse an SEC filing for a ticker.

    Uses XBRL API for financial numbers + HTML for narrative sections.

    Returns:
      {
        "ticker": str,
        "cik": str,
        "filing_type": str,
        "filing_date": str,
        "numbers": {revenue, net_income, eps, gross_margin, ...},
        "md_a_snippet": str (first 3000 chars),
        "risk_snippet": str (first 3000 chars),
        "sections": list[str],
      }
    """
    sec = _import_finny_module("sec_reader")
    if sec is None:
        return None

    try:
        result = sec.analyze_filing(ticker.upper(), filing_type, use_xbrl=True)
        if "error" in result:
            return None

        return {
            "ticker": result["ticker"],
            "cik": result["cik"],
            "filing_type": result["filing_type"],
            "filing_date": result["filing_date"],
            "description": result.get("description", ""),
            "numbers": result.get("numbers", {}),
            "md_a_snippet": result.get("md_a_snippet", ""),
            "risk_snippet": result.get("risk_snippet", ""),
            "sections": result.get("sections", []),
            "source": "sec_edgar",
        }
    except Exception:
        return None


def fetch_sec_numbers(ticker: str, filing_type: str = "10-K") -> dict:
    """Fetch only the financial numbers from the latest filing.

    Returns dict like:
      {revenue: float, net_income: float, eps: float, gross_margin: float, ...}
    """
    sec = _import_finny_module("sec_reader")
    if sec is None:
        return {}

    try:
        return sec.get_xbrl_numbers(ticker.upper(), filing_type)
    except Exception:
        return {}


def list_sec_filings(ticker: str, filing_type: str = "10-Q", count: int = 3) -> list[dict]:
    """List recent SEC filings for a ticker.

    Returns list of {type, date, url, description}.
    """
    sec = _import_finny_module("sec_reader")
    if sec is None:
        return []

    try:
        cik = sec.get_cik(ticker.upper())
        if not cik:
            return []
        return sec.list_filings(cik, filing_type, count)
    except Exception:
        return []


# ── Main CLI ───────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    command = sys.argv[1]

    if command == "stocktwits":
        ticker = sys.argv[2].upper() if len(sys.argv) > 2 else None
        if ticker == "TRENDING" or ticker is None:
            trending = fetch_stocktwits_trending()
            print(json.dumps(trending, indent=2))
        else:
            result = fetch_stocktwits_sentiment(ticker)
            if result:
                print(json.dumps(result, indent=2))
            else:
                print(f'{{"error": "No data for {ticker}"}}')

    elif command == "sec":
        ticker = sys.argv[2].upper() if len(sys.argv) > 2 else None
        if not ticker:
            print('{"error": "Ticker required"}')
            sys.exit(1)

        filing_type = "10-K" if "--annual" in sys.argv else "10-Q"

        if "--numbers" in sys.argv:
            nums = fetch_sec_numbers(ticker, filing_type)
            print(json.dumps(nums, indent=2))
        elif "--list" in sys.argv:
            filings = list_sec_filings(ticker, filing_type)
            print(json.dumps(filings, indent=2, default=str))
        else:
            result = fetch_sec_filing(ticker, filing_type)
            if result:
                # Truncate long snippets for display
                for key in ("md_a_snippet", "risk_snippet"):
                    if key in result:
                        result[key] = result[key][:500] + "..."
                print(json.dumps(result, indent=2, default=str))
            else:
                print(f'{{"error": "No data for {ticker}"}}')

    else:
        print(f"Unknown command: {command}")
        print("Available: stocktwits, sec")
        sys.exit(1)


if __name__ == "__main__":
    main()
