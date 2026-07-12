#!/usr/bin/env python3
"""
fundamentals.py — Fundamental Health Check
===========================================
Fetches key fundamental metrics via yfinance, scores company health on a
0-5 scale, and persists to the ``fundamental_snapshots`` table for use by
any pipeline.

Scoring logic (5 binary checks):
  1. Trailing P/E > 0 and < 50       (profitable, not speculative)
  2. Debt/Equity < 100%              (manageable leverage)
  3. Current Ratio > 1.5             (can cover short-term obligations)
  4. ROE > 10%                       (decent return on equity)
  5. Profit Margins > 5%             (not running at a loss)

Health label: 5 → HEALTHY, 3-4 → HEALTHY, 2 → CAUTION, 0-1 → HIGH_RISK

Usage:
  python3 scripts/fundamentals.py AAPL
  python3 scripts/fundamentals.py --batch AAPL MSFT NVDA
  python3 scripts/fundamentals.py --all          (all screener tickers)
  python3 scripts/fundamentals.py --json AAPL
"""

import argparse
import json
import os
import sys
import uuid
from datetime import date, datetime, timezone
from typing import Optional

import yfinance as yf

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(SCRIPT_DIR)

# Add trading-desk to path for DB access
sys.path.insert(0, os.path.join(WORKSPACE, "trading-desk", "backend"))


def _score(ticker: str) -> dict:
    """Fetch fundamental data from yfinance and compute health score."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
    except Exception as exc:
        return {"ticker": ticker, "error": f"yfinance fetch failed: {exc}", "health_score": 0, "health_label": "HIGH_RISK"}

    if not info or info.get("trailingEps") is None and info.get("marketCap") is None:
        return {"ticker": ticker, "error": "No fundamental data available", "health_score": 0, "health_label": "HIGH_RISK"}

    # Extract metrics
    trailing_pe = info.get("trailingPE")
    forward_pe = info.get("forwardPE")
    debt_to_equity = info.get("debtToEquity")  # yfinance returns as percentage (e.g., 50.5 = 50.5%)
    current_ratio = info.get("currentRatio")
    roe = info.get("returnOnEquity")  # Also as percentage
    profit_margins = info.get("profitMargins")  # Decimal (e.g., 0.15 = 15%)
    revenue_growth = info.get("revenueGrowth")  # Decimal
    market_cap = info.get("marketCap")
    beta = info.get("beta")

    # Normalize percentage-based fields to consistent decimal form
    if debt_to_equity is not None and abs(debt_to_equity) > 10:
        debt_to_equity = debt_to_equity / 100.0  # 50.5 → 0.505
    if roe is not None and abs(roe) > 10:
        roe = roe / 100.0  # 25.3 → 0.253
    if profit_margins is not None and abs(profit_margins) > 5:
        profit_margins = profit_margins / 100.0  # 15.0 → 0.15

    # Scoring
    checks = []
    score = 0

    # 1. P/E: positive and reasonable
    if trailing_pe is not None:
        if trailing_pe > 0 and trailing_pe < 50:
            score += 1
            checks.append({"metric": "trailing_pe", "value": trailing_pe, "status": "pass", "note": f"P/E={trailing_pe:.1f} (0<PE<50)"})
        elif trailing_pe <= 0:
            checks.append({"metric": "trailing_pe", "value": trailing_pe, "status": "fail", "note": f"P/E={trailing_pe:.1f} (negative earnings)"})
        else:
            checks.append({"metric": "trailing_pe", "value": trailing_pe, "status": "warn", "note": f"P/E={trailing_pe:.1f} (>50, speculative)"})

    # 2. Debt/Equity: manageable leverage
    if debt_to_equity is not None:
        if debt_to_equity < 1.0:
            score += 1
            checks.append({"metric": "debt_to_equity", "value": debt_to_equity, "status": "pass", "note": f"D/E={debt_to_equity:.2f}"})
        elif debt_to_equity < 2.0:
            checks.append({"metric": "debt_to_equity", "value": debt_to_equity, "status": "warn", "note": f"D/E={debt_to_equity:.2f} (elevated)"})
        else:
            checks.append({"metric": "debt_to_equity", "value": debt_to_equity, "status": "fail", "note": f"D/E={debt_to_equity:.2f} (high leverage)"})

    # 3. Current Ratio: can pay short-term debt
    if current_ratio is not None:
        if current_ratio > 1.5:
            score += 1
            checks.append({"metric": "current_ratio", "value": current_ratio, "status": "pass", "note": f"CR={current_ratio:.1f}"})
        elif current_ratio >= 1.0:
            checks.append({"metric": "current_ratio", "value": current_ratio, "status": "warn", "note": f"CR={current_ratio:.1f} (tight)"})
        else:
            checks.append({"metric": "current_ratio", "value": current_ratio, "status": "fail", "note": f"CR={current_ratio:.1f} (<1, liquidity risk)"})

    # 4. ROE: decent return
    if roe is not None:
        if roe > 0.10:
            score += 1
            checks.append({"metric": "roe", "value": roe, "status": "pass", "note": f"ROE={roe*100:.1f}%"})
        elif roe > 0:
            checks.append({"metric": "roe", "value": roe, "status": "warn", "note": f"ROE={roe*100:.1f}% (low)"})
        else:
            checks.append({"metric": "roe", "value": roe, "status": "fail", "note": f"ROE={roe*100:.1f}% (negative)"})

    # 5. Profit Margins
    if profit_margins is not None:
        if profit_margins > 0.05:
            score += 1
            checks.append({"metric": "profit_margins", "value": profit_margins, "status": "pass", "note": f"Margin={profit_margins*100:.1f}%"})
        elif profit_margins > 0:
            checks.append({"metric": "profit_margins", "value": profit_margins, "status": "warn", "note": f"Margin={profit_margins*100:.1f}% (thin)"})
        else:
            checks.append({"metric": "profit_margins", "value": profit_margins, "status": "fail", "note": f"Margin={profit_margins*100:.1f}% (unprofitable)"})

    # Health label
    if score >= 3:
        health_label = "HEALTHY"
    elif score == 2:
        health_label = "CAUTION"
    else:
        health_label = "HIGH_RISK"

    return {
        "ticker": ticker,
        "health_score": score,
        "health_label": health_label,
        "market_cap": market_cap,
        "trailing_pe": trailing_pe,
        "forward_pe": forward_pe,
        "debt_to_equity": debt_to_equity,
        "current_ratio": current_ratio,
        "return_on_equity": roe,
        "profit_margins": profit_margins,
        "revenue_growth": revenue_growth,
        "beta": beta,
        "flags": checks,
        "raw_data": {
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "fullTimeEmployees": info.get("fullTimeEmployees"),
            "shortName": info.get("shortName"),
        },
        "as_of_date": date.today().isoformat(),
    }


def _persist(result: dict) -> bool:
    """Write a fundamental snapshot to the DB."""
    try:
        import psycopg2

        db_url = os.environ.get(
            "DATABASE_URL",
            "postgresql://admin:***@localhost:5432/trading_desk"
        )

        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()

        cur.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
        cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

        cur.execute("""
            INSERT INTO fundamental_snapshots (
                id, ticker, as_of_date,
                health_score, health_label,
                market_cap, trailing_pe, forward_pe,
                debt_to_equity, current_ratio,
                return_on_equity, profit_margins,
                revenue_growth, beta,
                flags, raw_data,
                created_at, updated_at
            ) VALUES (
                %s, %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s::jsonb, %s::jsonb,
                %s, %s
            )
            ON CONFLICT DO NOTHING
        """, (
            str(uuid.uuid4()),
            result["ticker"],
            result["as_of_date"],
            result["health_score"],
            result["health_label"],
            result.get("market_cap"),
            result.get("trailing_pe"),
            result.get("forward_pe"),
            result.get("debt_to_equity"),
            result.get("current_ratio"),
            result.get("return_on_equity"),
            result.get("profit_margins"),
            result.get("revenue_growth"),
            result.get("beta"),
            json.dumps(result.get("flags", [])),
            json.dumps(result.get("raw_data", {})),
            datetime.now(timezone.utc),
            datetime.now(timezone.utc),
        ))

        cur.close()
        conn.close()
        return True
    except Exception as exc:
        print(f"  ⚠ DB persist failed for {result['ticker']}: {exc}", file=sys.stderr)
        return False


def get_all_tickers() -> list[str]:
    """Return all tickers from the screener universe."""
    import importlib.util
    screener_path = os.path.join(SCRIPT_DIR, "screener.py")
    spec = importlib.util.spec_from_file_location("screener", screener_path)
    screener = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(screener)
    tickers = []
    for sector_tickers in screener.SECTOR_TICKERS.values():
        tickers.extend(sector_tickers)
    return sorted(set(tickers))


def main():
    parser = argparse.ArgumentParser(description="Fundamental health check for trading desk tickers")
    parser.add_argument("tickers", nargs="*", help="Ticker symbols")
    parser.add_argument("--all", action="store_true", help="Score all screener universe tickers")
    parser.add_argument("--json", action="store_true", help="Output JSON only (no DB persist)")
    parser.add_argument("--batch", action="store_true", help="Process multiple tickers from args")
    args = parser.parse_args()

    if args.all:
        tickers = get_all_tickers()
    elif args.tickers:
        tickers = args.tickers
    else:
        parser.print_help()
        sys.exit(1)

    results = []
    for ticker in tickers:
        t = ticker.upper().strip()
        print(f"  🔍 {t}...", end=" ", flush=True)
        result = _score(t)

        if "error" in result:
            print(f"❌ {result['error']}")
        else:
            print(f"{result['health_label']} ({result['health_score']}/5)")
            if not args.json:
                _persist(result)

        results.append(result)

    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2, default=str))

    # Summary
    healthy = sum(1 for r in results if r.get("health_label") == "HEALTHY")
    caution = sum(1 for r in results if r.get("health_label") == "CAUTION")
    risk = sum(1 for r in results if r.get("health_label") == "HIGH_RISK")
    errors = sum(1 for r in results if "error" in r)

    print(f"\n  Summary: {healthy} healthy, {caution} caution, {risk} high-risk, {errors} errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
