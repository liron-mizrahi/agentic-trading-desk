#!/usr/bin/env python3
"""
Yahoo Finance fallback for IBKR Web API.
=========================================
Mimics ibkr_webapi.py CLI for historicals and macro-etfs commands.
Used when IBKR Gateway is unavailable.

Usage:
  python3 scripts/yahoo_fallback.py historicals AAPL
  python3 scripts/yahoo_fallback.py macro-etfs
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta

import yfinance as yf

# ── Helpers ───────────────────────────────────────────────────────────

def _fetch_ticker(symbol: str) -> dict:
    """Fetch 1 year of daily OHLCV from Yahoo Finance, return IBKR-format dict."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="1y", interval="1d")
        if df.empty:
            return {"error": f"No data for {symbol}"}
        
        closes = [round(c, 4) for c in df["Close"].tolist()]
        highs = [round(h, 4) for h in df["High"].tolist()]
        lows = [round(lw, 4) for lw in df["Low"].tolist()]
        
        return {
            "symbol": symbol.upper(),
            "conid": 0,  # placeholder - Yahoo has no conid
            "close": closes,
            "high": highs,
            "low": lows,
            "n_bars": len(closes),
        }
    except Exception as e:
        return {"error": str(e)}


def cmd_historicals(args):
    """Historicals command - same CLI as ibkr_webapi.py."""
    result = _fetch_ticker(args.symbol)
    print(json.dumps(result))
    return 0 if "error" not in result else 1


def cmd_macro_etfs(args):
    """Macro ETFs - 8 ETFs used by the macro pillar."""
    symbols = ["SPY", "RSP", "IWM", "HYG", "LQD", "TLT", "XLY", "XLP"]
    results = {}
    for sym in symbols:
        data = _fetch_ticker(sym)
        if "error" in data:
            results[sym] = {"error": data["error"]}
        else:
            results[sym] = data["close"]
        time.sleep(0.3)  # rate limit
    
    print(json.dumps({"series": results}))
    return 0


def main():
    parser = argparse.ArgumentParser(description="Yahoo Finance fallback for IBKR data")
    sub = parser.add_subparsers(dest="command", required=True)
    
    p_hist = sub.add_parser("historicals")
    p_hist.add_argument("symbol")
    
    sub.add_parser("macro-etfs")
    
    args = parser.parse_args()
    
    cmds = {
        "historicals": cmd_historicals,
        "macro-etfs": cmd_macro_etfs,
    }
    
    try:
        return cmds[args.command](args)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
