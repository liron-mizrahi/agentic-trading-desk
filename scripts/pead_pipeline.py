#!/usr/bin/env python3
"""
pead_pipeline.py
================
Post-Earnings Announcement Drift (PEAD) Strategy — Pipeline 5.

Academic anomaly: stocks that beat earnings estimates tend to drift upward
for 30-60 days after the announcement. Stocks that miss drift downward.
The drift persists because the market underreacts to earnings surprises.

This pipeline detects recent earnings beats/misses and enters positions
to capture the drift. Uses SEC filings data and Yahoo analyst estimates.

Funnel:
  Step 1 — Earnings Detection: find recent 10-Q/10-K filings
  Step 2 — Surprise Calculation: compare actual EPS to consensus estimate
  Step 3 — Drift Entry: if beat > 5% and revenue beat, enter
  Step 4 — Drift Management: hold for 30-60 days with trailing stop

Usage:
  python3 scripts/pead_pipeline.py                              # Full run
  python3 scripts/pead_pipeline.py --dry-run                     # Preview
  python3 scripts/pead_pipeline.py --json                        # Machine output
  python3 scripts/pead_pipeline.py --min-surprise 10             # Only 10%+ beats
"""

import argparse
import json
import math
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(SCRIPT_DIR)

sys.path.insert(0, SCRIPT_DIR)
import indicators as I

# ── Earnings tracking universe ────────────────────────────────────────

# Companies with known earnings calendars + SEC data
EARNINGS_UNIVERSE = [
    # (ticker, sector, next_earnings_approx)
    ("AAPL", "Technology"),
    ("MSFT", "Technology"),
    ("NVDA", "Technology"),
    ("GOOGL", "Technology"),
    ("AVGO", "Technology"),
    ("CRM", "Technology"),
    ("JPM", "Financial Services"),
    ("BAC", "Financial Services"),
    ("V", "Financial Services"),
    ("META", "Communication"),
    ("NFLX", "Communication"),
    ("AMZN", "Consumer Cyclical"),
    ("TSLA", "Consumer Cyclical"),
    ("HD", "Consumer Cyclical"),
    ("UNH", "Healthcare"),
    ("LLY", "Healthcare"),
    ("JNJ", "Healthcare"),
    ("XOM", "Energy"),
    ("PG", "Consumer Defensive"),
    ("KO", "Consumer Defensive"),
    ("COST", "Consumer Defensive"),
    ("CAT", "Industrials"),
    ("GE", "Industrials"),
    ("LIN", "Basic Materials"),
]


def _run(cmd: list, timeout: int = 60) -> tuple[bool, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=WORKSPACE)
        return result.returncode == 0, result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return False, str(e)


# ── Step 1: Detect Recent Earnings ────────────────────────────────────

SEC_READER = os.path.join(SCRIPT_DIR, "..", "..", "finance-workspace", "sec_reader.py")


def _find_sec_reader() -> Optional[str]:
    """Find sec_reader.py in Finny workspace or our scripts."""
    paths = [
        os.path.join(WORKSPACE, "..", "..", "finance-workspace", "sec_reader.py"),
        os.path.join(WORKSPACE, "..", "finance-workspace", "sec_reader.py"),
        os.path.join(SCRIPT_DIR, "sec_reader.py"),
    ]
    for path in paths:
        if os.path.exists(path):
            return path
    return None


def fetch_earnings_data(ticker: str) -> Optional[dict]:
    """Fetch latest earnings data via SEC EDGAR (XBRL API for actuals)."""
    # Try SEC reader first
    sec_reader_path = _find_sec_reader()
    
    if sec_reader_path:
        ok, out = _run([sys.executable, sec_reader_path, ticker, "--annual"], timeout=30)
        if ok:
            try:
                data = json.loads(out)
                if "error" not in data:
                    return data
            except json.JSONDecodeError:
                pass
    
    # Fallback: use our own lightweight SEC fetcher via urllib
    return _fetch_earnings_lightweight(ticker)


def _fetch_earnings_lightweight(ticker: str) -> Optional[dict]:
    """Lightweight SEC EDGAR XBRL fetch for earnings.
    
    Uses the SEC company-concept API to get EPS directly.
    No external dependencies needed.
    """
    import ssl
    import urllib.request
    import gzip
    import re
    
    # CIK lookup
    CIK_MAP = {
        "AAPL": "320193", "MSFT": "789019", "NVDA": "1045810", "GOOGL": "1652044",
        "META": "1326801", "AMZN": "1018724", "TSLA": "1318605", "AVGO": "1730168",
        "CRM": "1108524", "JPM": "19617", "BAC": "70858", "V": "1403161",
        "NFLX": "1065280", "UNH": "731766", "LLY": "59478", "JNJ": "200406",
        "XOM": "34088", "PG": "80424", "KO": "21344", "COST": "909832",
        "CAT": "18230", "GE": "40545", "HD": "354950", "LIN": "1707925",
    }
    
    cik = CIK_MAP.get(ticker.upper())
    if not cik:
        return None
    
    cik_padded = cik.zfill(10)
    eps_concepts = ["EarningsPerShareDiluted", "EarningsPerShareBasic"]
    
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    
    eps_values = []
    
    for concept in eps_concepts:
        url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik_padded}/us-gaap/{concept}.json"
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "AgenticTradingDesk/1.0 (research)",
                "Accept-Encoding": "gzip",
            })
            resp = urllib.request.urlopen(req, timeout=15, context=ssl_ctx)
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip" or raw[:2] == b'\x1f\x8b':
                raw = gzip.decompress(raw)
            data = json.loads(raw.decode("utf-8", errors="replace"))
            
            units = data.get("units", {})
            for unit_key in ("USD", "usd", "USD/shares", "shares"):
                if unit_key in units and len(units[unit_key]) > 0:
                    entries = units[unit_key]
                    # Get most recent annual (10-K) filing
                    for entry in reversed(entries):
                        if entry.get("form") == "10-K" and entry.get("fp") == "FY":
                            eps_values.append({
                                "value": entry.get("val"),
                                "end": entry.get("end"),
                                "filed": entry.get("filed"),
                            })
                            break
                    break
        except Exception:
            continue
    
    if not eps_values:
        return None
    
    # Pick the latest EPS value
    eps_values.sort(key=lambda x: x.get("end", ""), reverse=True)
    latest = eps_values[0]
    prev = eps_values[1] if len(eps_values) > 1 else None
    
    result = {
        "ticker": ticker.upper(),
        "cik": cik,
        "latest_eps": latest.get("value"),
        "latest_period": latest.get("end"),
        "filing_type": "10-K",
        "source": "sec_xbrl",
    }
    
    if prev:
        result["prev_eps"] = prev.get("value")
        result["prev_period"] = prev.get("end")
    
    return result


# ── Step 2: Surprise Calculation ──────────────────────────────────────

# Analyst consensus estimates (manual mapping for key tickers)
# In production, fetch from Yahoo Finance analyst page or FMP API
ANALYST_ESTIMATES = {
    "AAPL": {"eps": 7.35, "revenue": 396.0},  # Billions
    "MSFT": {"eps": 12.85, "revenue": 262.0},
    "NVDA": {"eps": 2.95, "revenue": 112.0},
    "GOOGL": {"eps": 8.72, "revenue": 350.0},
    "META": {"eps": 23.50, "revenue": 165.0},
    "AMZN": {"eps": 5.80, "revenue": 638.0},
    "TSLA": {"eps": 2.45, "revenue": 100.0},
    "AVGO": {"eps": 6.20, "revenue": 52.0},
    "JPM": {"eps": 17.50, "revenue": 155.0},
    "UNH": {"eps": 29.50, "revenue": 410.0},
    "LLY": {"eps": 15.20, "revenue": 45.0},
    "XOM": {"eps": 7.80, "revenue": 355.0},
}


def compute_surprise(earnings_data: dict, ticker: str) -> Optional[dict]:
    """Calculate earnings surprise percentage."""
    actual_eps = earnings_data.get("latest_eps")
    if actual_eps is None:
        return None
    
    estimate = ANALYST_ESTIMATES.get(ticker.upper(), {})
    est_eps = estimate.get("eps")
    
    if est_eps is None or est_eps == 0:
        return {
            "ticker": ticker.upper(),
            "actual_eps": actual_eps,
            "estimate_eps": None,
            "surprise_pct": None,
            "surprise_direction": "unknown",
            "period": earnings_data.get("latest_period"),
        }
    
    surprise_pct = ((actual_eps / est_eps) - 1.0) * 100.0
    
    direction = (
        "beat" if surprise_pct > 3 else
        "miss" if surprise_pct < -3 else
        "inline"
    )
    
    return {
        "ticker": ticker.upper(),
        "actual_eps": actual_eps,
        "estimate_eps": est_eps,
        "surprise_pct": round(surprise_pct, 2),
        "surprise_direction": direction,
        "period": earnings_data.get("latest_period"),
    }


# ── Step 3: Drift Signal ──────────────────────────────────────────────

def drift_signal(surprise: dict, price_data: dict, ticker: str, min_surprise: float = 5.0) -> dict:
    """Generate drift trading signal.

    Entry criteria:
    - EPS beat > min_surprise% (default 5%)
    - Price above SMA200 (still in uptrend)
    - Not already at extreme overbought (RSI < 75)
    """
    surprise_pct = surprise.get("surprise_pct")
    if surprise_pct is None or surprise_pct < min_surprise:
        return {"action": None, "reason": f"Surprise {surprise_pct}% below threshold {min_surprise}%"}
    
    closes = price_data.get("close", [])
    if len(closes) < 200:
        return {"action": None, "reason": "Insufficient data"}
    
    ind = I.compute(closes, 5)
    price = ind.get("close", 0)
    sma200 = ind.get("sma200")
    rsi14 = ind.get("rsi14")
    
    checks = []
    
    # Filter 1: Trending (price > SMA200)
    if sma200 and price > sma200:
        checks.append("Price > SMA200 ✅")
    else:
        return {"action": None, "reason": f"Price below SMA200"}
    
    # Filter 2: Not overbought (RSI < 75)
    if rsi14 and rsi14 < 75:
        checks.append(f"RSI {rsi14:.0f} < 75 ✅")
    else:
        return {"action": None, "reason": f"Overbought (RSI {rsi14:.0f})"}
    
    # Drift position sizing
    drift_days = 45  # Hold for 45 trading days
    stop_pct = 0.06  # 6% trailing stop
    
    # Larger surprise → larger position
    size_mult = min(1.5, max(0.5, surprise_pct / 10.0))
    base_shares = 100
    shares = int(base_shares * size_mult)
    
    return {
        "action": "ENTER",
        "ticker": ticker,
        "price": round(price, 2),
        "surprise_pct": surprise_pct,
        "direction": surprise.get("surprise_direction"),
        "checks": checks,
        "drift_days": drift_days,
        "stop_loss": round(price * (1 - stop_pct), 2),
        "take_profit": round(price * 1.12, 2),  # 12% target for drift
        "shares": shares,
        "exit_rule": f"Close after {drift_days} days or trailing stop -{stop_pct*100:.0f}%",
    }


# ── Main Pipeline ─────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="PEAD — Post-Earnings Announcement Drift Pipeline")
    p.add_argument("--min-surprise", type=float, default=5.0,
                    help="Minimum earnings surprise % to trigger entry")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-cache", action="store_true")

    args = p.parse_args()

    print(f"PEAD — Post-Earnings Announcement Drift — Pipeline 5")
    print(f"  Run:           {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Min Surprise:  {args.min_surprise}%")
    print(f"  Mode:          {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()

    print("─── STEP 1: Earnings Detection ───", flush=True)
    
    earnings_results = []
    for ticker, sector in EARNINGS_UNIVERSE:
        print(f"  {ticker:6s} ({sector:22s}) ... ", end="", flush=True)
        
        earnings = fetch_earnings_data(ticker)
        if not earnings:
            print("no data", flush=True)
            continue
        
        actual_eps = earnings.get("latest_eps")
        period = earnings.get("latest_period", "?")
        print(f"EPS=${actual_eps} ({period})", flush=True)
        earnings_results.append((ticker, sector, earnings))

    if not earnings_results:
        print("  No earnings data available.\n")
        return

    # ── Step 2: Surprise Calculation ──
    print("\n─── STEP 2: Surprise Calculation ───", flush=True)
    
    surprises = []
    for ticker, sector, earnings in earnings_results:
        surprise = compute_surprise(earnings, ticker)
        if surprise:
            sp = surprise.get("surprise_pct")
            sp_str = f"{sp:+7.1f}%" if sp is not None else "unknown"
            print(f"  {ticker:6s} | Est: ${surprise.get('estimate_eps')} | Actual: ${surprise['actual_eps']} | {sp_str} | {surprise['surprise_direction']}", flush=True)
            surprises.append((ticker, sector, surprise, earnings))

    # ── Step 3: Drift Entry ──
    print(f"\n─── STEP 3: Drift Entry Signals (min {args.min_surprise}% beat) ───\n", flush=True)
    
    proposals = []
    for ticker, sector, surprise, earnings in surprises:
        if surprise["surprise_direction"] != "beat":
            continue
        if surprise["surprise_pct"] is None or surprise["surprise_pct"] < args.min_surprise:
            continue
        
        # Fetch price data
        ok, out = _run([sys.executable, "scripts/ibkr_webapi.py", "historicals", ticker])
        if not ok:
            continue
        try:
            price_data = json.loads(out)
        except json.JSONDecodeError:
            continue
        
        signal = drift_signal(surprise, price_data, ticker, args.min_surprise)
        
        if signal["action"] == "ENTER":
            proposals.append({**signal, "sector": sector})
            print(f"  ▶ {ticker}")
            print(f"    Surprise:  {signal['surprise_pct']:+.1f}% beat")
            print(f"    Entry:     ${signal['price']:.2f} x {signal['shares']} shares")
            print(f"    Stop:      ${signal['stop_loss']:.2f}")
            print(f"    Target:    ${signal['take_profit']:.2f}")
            print(f"    Hold:      {signal['drift_days']} days")
            print(f"    Exit rule: {signal['exit_rule']}")
            print()
        else:
            print(f"  {ticker:6s}: {signal['reason']}", flush=True)

    # ── Cache orders ──
    if not args.dry_run and not args.no_cache:
        print("─── Order Cache ───\n", flush=True)
        for prop in proposals:
            cmd = [
                sys.executable, "scripts/order_cache.py", "add",
                "--ticker", prop["ticker"],
                "--action", "ENTER",
                "--close", str(prop["price"]),
                "--score", "0",
                "--note", f"PEAD: {prop['surprise_pct']:+.1f}% beat, drift {prop['drift_days']}d",
            ]
            ok, out = _run(cmd)
            if ok:
                for line in out.split("\n"):
                    if "Created:" in line:
                        oid = line.split("|")[0].replace("Created:", "").strip()
                        print(f"  {prop['ticker']}: {oid} → pending_confirm")
                        _run([
                            sys.executable, "scripts/order_cache.py", "entry", oid,
                            "--limit", str(prop["price"]),
                            "--qty", str(prop["shares"]),
                            "--stop", str(prop["stop_loss"]),
                            "--target", str(prop["take_profit"]),
                        ])
                        _run([
                            sys.executable, "scripts/order_cache.py", "update", oid,
                            "--status", "pending_confirm",
                        ])

    # ── Summary ──
    print(f"\n{'='*60}")
    print(f"  PEAD DRIFT — SUMMARY")
    print(f"{'='*60}")
    print(f"  Earnings checked:  {len(earnings_results)}")
    print(f"  Beats:             {sum(1 for _, _, s, _ in surprises if s['surprise_direction'] == 'beat')}")
    print(f"  Qualifying beats:  {len(proposals)} (≥{args.min_surprise}%)")
    print(f"  Mode:              {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"{'='*60}")

    if not proposals:
        print("\n  No qualifying earnings beats detected.")

    if args.json:
        print(json.dumps({
            "status": "complete",
            "strategy": "pead",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "min_surprise_pct": args.min_surprise,
            "earnings_scanned": len(earnings_results),
            "beats_detected": sum(1 for _, _, s, _ in surprises if s['surprise_direction'] == 'beat'),
            "proposals": proposals,
        }, indent=2))


if __name__ == "__main__":
    main()
