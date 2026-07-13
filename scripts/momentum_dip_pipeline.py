#!/usr/bin/env python3
"""
momentum_dip_pipeline.py
========================
Momentum-Dip Catalyst Strategy — 4-Step Filter Funnel.

Filters the daily market universe for extreme short-term oversold conditions
(R-2 based, sector-adapted) within trending macro structures (SMA200 + CHOP filters).

Sector adaptation matrix:
  Defensive (Utilities, Staples, Healthcare)  → R-2 < 20  → full size
  Broad Market / Financials                    → R-2 < 15  → standard
  High Growth / Tech / Semiconductors          → R-2 < 10  → -30% size
  Speculative / Biotech / Micro-caps           → R-2 < 5   → -50% size

Usage:
  python3 scripts/momentum_dip_pipeline.py                           # Full run
  python3 scripts/momentum_dip_pipeline.py --dry-run                  # Preview only
  python3 scripts/momentum_dip_pipeline.py --json                     # Machine-readable
  python3 scripts/momentum_dip_pipeline.py --sectors Technology       # Focus specific
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
import order_cache as oc

# --------------------------------------------------------------------------
# Sector definitions & adaptation matrix
# --------------------------------------------------------------------------

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

# Sector profile mapping
SECTOR_PROFILES = {
    "Technology":          {"profile": "high_growth", "threshold": 10, "size_reduction": 0.30},
    "Financial Services":  {"profile": "broad_market", "threshold": 15, "size_reduction": 0.0},
    "Industrials":         {"profile": "broad_market", "threshold": 15, "size_reduction": 0.0},
    "Communication":       {"profile": "high_growth", "threshold": 10, "size_reduction": 0.30},
    "Consumer Cyclical":   {"profile": "broad_market", "threshold": 15, "size_reduction": 0.0},
    "Healthcare":          {"profile": "defensive", "threshold": 20, "size_reduction": 0.0},
    "Energy":              {"profile": "broad_market", "threshold": 15, "size_reduction": 0.0},
    "Consumer Defensive":  {"profile": "defensive", "threshold": 20, "size_reduction": 0.0},
    "Basic Materials":     {"profile": "broad_market", "threshold": 15, "size_reduction": 0.0},
    "Real Estate":         {"profile": "defensive", "threshold": 20, "size_reduction": 0.0},
    "Utilities":           {"profile": "defensive", "threshold": 20, "size_reduction": 0.0},
}

PROFILE_LABELS = {
    "defensive": "Defensive (full size)",
    "broad_market": "Broad Market (standard)",
    "high_growth": "High Growth / Tech (-30% size)",
    "speculative": "Speculative (-50% size)",
}


def _run(cmd: list, timeout: int = 30) -> tuple[bool, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=WORKSPACE)
        if result.returncode == 0:
            return True, result.stdout
        return False, result.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return False, str(e)


def fetch_ohlcv(ticker: str) -> Optional[dict]:
    """Fetch OHLCV data via IBKR."""
    ok, out = _run([sys.executable, "scripts/ibkr_webapi.py", "historicals", ticker])
    if not ok:
        return None
    try:
        data = json.loads(out)
        if "error" in data:
            return None
        return data
    except json.JSONDecodeError:
        return None


def compute_indicators(data: dict) -> dict:
    """Compute the full indicator stack including RSI-2 and CHOP."""
    close = data.get("close", [])
    high = data.get("high")
    low = data.get("low")
    return I.compute(close, 5, high, low)


def sector_for_ticker(ticker: str) -> tuple[str, dict]:
    """Find which sector a ticker belongs to and return its profile."""
    for sector, tickers in SECTOR_TICKERS.items():
        if ticker in tickers:
            return sector, SECTOR_PROFILES.get(sector, SECTOR_PROFILES["Technology"])
    return "Unclassified", {"profile": "high_growth", "threshold": 10, "size_reduction": 0.30}


# --------------------------------------------------------------------------
# Step 1: Macro & Choppiness Screener
# --------------------------------------------------------------------------

def step1_screen(ticker: str, data: dict, ind: dict, sector: str) -> Optional[dict]:
    """Step 1 filter: Price > SMA200 AND CHOP < 50 (trending)."""
    close = data.get("close", [])
    if len(close) < 200:
        return {"ticker": ticker, "passed": False, "reason": f"Insufficient data ({len(close)} bars, need 200+)"}

    sma200 = ind.get("sma200")
    price = ind.get("close")
    chop = ind.get("choppiness_index")

    if sma200 is None or price is None:
        return {"ticker": ticker, "passed": False, "reason": "SMA200 unavailable"}

    checks = []

    # Rule 1: Price > SMA200
    if price > sma200:
        checks.append(f"Price ${price:.2f} > SMA200 ${sma200:.2f} ✅")
    else:
        checks.append(f"Price ${price:.2f} < SMA200 ${sma200:.2f} ❌ (downtrend)")
        return {"ticker": ticker, "passed": False, "reason": "; ".join(checks)}

    # Rule 2: CHOP < 50 (trending)
    if chop is not None:
        if chop < 50:
            checks.append(f"CHOP {chop:.1f} < 50 ✅ (trending)")
        else:
            checks.append(f"CHOP {chop:.1f} > 50 ❌ (choppy/sideways)")
            return {"ticker": ticker, "passed": False, "reason": "; ".join(checks)}
    else:
        checks.append("CHOP: unavailable (no high/low data)")

    return {"ticker": ticker, "passed": True, "checks": checks, "ind": ind, "data": data, "sector": sector}


# --------------------------------------------------------------------------
# Step 2: RSI-2 Mean Reversion Trigger
# --------------------------------------------------------------------------

def step2_rsi2_trigger(screen_result: dict, profile: dict) -> Optional[dict]:
    """Step 2 filter: RSI-2 below sector-adapted threshold."""
    ind = screen_result["ind"]
    rsi2 = ind.get("rsi2")
    threshold = profile["threshold"]

    if rsi2 is None:
        return {**screen_result, "passed": False, "reason": "RSI-2 unavailable"}

    if rsi2 >= threshold:
        return {
            **screen_result,
            "passed": False,
            "reason": f"RSI-2 {rsi2:.1f} >= threshold {threshold} ({PROFILE_LABELS.get(profile['profile'], profile['profile'])})",
            "rsi2": rsi2,
            "threshold": threshold,
        }

    return {
        **screen_result,
        "passed": True,
        "rsi2": rsi2,
        "threshold": threshold,
        "profile_name": PROFILE_LABELS.get(profile['profile'], profile['profile']),
        "size_reduction": profile["size_reduction"],
    }


# --------------------------------------------------------------------------
# Step 4: Exit Strategy & Proposal
# --------------------------------------------------------------------------

def step4_proposal(candidate: dict) -> dict:
    """Generate the final trade proposal with QS Exit rule."""
    ticker = candidate["ticker"]
    ind = candidate["ind"]
    price = ind.get("close", 0)
    rsi2 = candidate.get("rsi2", 0)
    threshold = candidate.get("threshold", 15)
    size_reduction = candidate.get("size_reduction", 0)
    sector = candidate.get("sector", "?")

    # QS Exit: sell when close > previous day's high
    close_series = candidate.get("data", {}).get("close", [])
    prev_high = None
    high_series = candidate.get("data", {}).get("high", [])
    if len(high_series) >= 2:
        prev_high = high_series[-2]
    elif len(close_series) >= 2:
        prev_high = close_series[-2]

    # Position sizing: baseline 100 shares, reduce by sector factor
    base_shares = 100
    adjusted_shares = int(base_shares * (1.0 - size_reduction))

    # Stop loss: 5% below entry unless extreme volatility
    stop_pct = 0.05
    take_profit_pct = 0.08

    proposal = {
        "ticker": ticker,
        "sector": sector,
        "action": "ENTER (Momentum-Dip)",
        "price": price,
        "rsi2": rsi2,
        "rsi2_threshold": threshold,
        "rsi2_triggered": rsi2 < threshold,
        "size_reduction_pct": size_reduction * 100,
        "adjusted_shares": adjusted_shares,
        "entry_price": round(price, 2),
        "stop_loss": round(price * (1 - stop_pct), 2),
        "take_profit": round(price * (1 + take_profit_pct), 2),
        "exit_rule": "QS Exit: SELL when daily close > previous day's high",
        "prev_day_high": prev_high,
        "exit_trigger": f"Close > ${prev_high:.2f}" if prev_high else "N/A (insufficient data)",
        "profile": candidate.get("profile_name", "?"),
    }

    return proposal


# --------------------------------------------------------------------------
# Main Pipeline
# --------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Momentum-Dip Catalyst Strategy Pipeline")
    p.add_argument("--sectors", type=str, default=None,
                    help="Comma-separated sector focus (default: all)")
    p.add_argument("--dry-run", action="store_true",
                    help="Preview without order caching")
    p.add_argument("--json", action="store_true",
                    help="JSON output")

    args = p.parse_args()

    # Determine which sectors to scan
    if args.sectors:
        scan_sectors = [s.strip() for s in args.sectors.split(",")]
    else:
        scan_sectors = list(SECTOR_TICKERS.keys())

    print(f"Momentum-Dip Catalyst — 4-Step Filter Funnel")
    print(f"  Run:      {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Sectors:  {', '.join(scan_sectors)}")
    print(f"  Mode:     {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()

    all_results = []
    step1_passed = []
    step2_passed = []

    # Build the full ticker list
    all_tickers = []
    for sector in scan_sectors:
        tickers = SECTOR_TICKERS.get(sector, [])
        for t in tickers:
            all_tickers.append((t, sector))

    total = len(all_tickers)
    print(f"Total universe: {total} tickers across {len(scan_sectors)} sectors\n", flush=True)

    # ---- Step 1: Macro & Choppiness Screener ----
    print("─── STEP 1: Macro & Choppiness Screener ───", flush=True)

    for i, (ticker, sector) in enumerate(all_tickers, 1):
        print(f"  [{i}/{total}] {ticker:6s} ({sector:20s}) ... ", end="", flush=True)

        # Fetch data
        data = fetch_ohlcv(ticker)
        if data is None:
            print("❌ no data", flush=True)
            continue

        # Compute indicators
        ind = compute_indicators(data)
        if ind.get("warning"):
            print(f"⚠ {ind['warning'][:40]} ... ", end="", flush=True)

        # Step 2 filter
        result = step1_screen(ticker, data, ind, sector)
        all_results.append(result)

        if result["passed"]:
            rsi2 = ind.get("rsi2")

        if result["passed"]:
            rsi2 = ind.get("rsi2")
            chop = ind.get("choppiness_index")
            price = ind.get("close")
            sma200 = ind.get("sma200")
            rsi2_str = f"RSI-2={rsi2:.1f}" if rsi2 is not None else "RSI-2=N/A"
            chop_str = f"CHOP={chop:.1f}" if chop is not None else "CHOP=N/A"
            print(f"✅ {rsi2_str}, {chop_str}, ${price:.2f}, SMA200=${sma200:.2f}", flush=True)
            step1_passed.append(result)
        else:
            print(f"❌ {result.get('reason', 'failed')[:80]}", flush=True)

    print(f"\n  Step 1 passed: {len(step1_passed)}/{total}\n", flush=True)

    if not step1_passed:
        print("No candidates passed Step 1. Pipeline halting.")
        return

    # ---- Step 2: RSI-2 Mean Reversion Trigger ----
    print("─── STEP 2: RSI-2 Mean Reversion Trigger ───\n", flush=True)

    for result in step1_passed:
        ticker = result["ticker"]
        sector = result.get("sector", "?")
        profile = SECTOR_PROFILES.get(sector, SECTOR_PROFILES["Technology"])

        r2result = step2_rsi2_trigger(result, profile)

        if r2result["passed"]:
            rsi2 = r2result.get("rsi2", 0)
            threshold = r2result.get("threshold", 15)
            print(f"  {ticker:6s} | RSI-2: {rsi2:.1f} | threshold: {threshold} | profile: {r2result.get('profile_name', '?')} ✅", flush=True)
            step2_passed.append(r2result)
        else:
            pass  # Failed silently (RSI-2 not oversold enough)

    print(f"\n  Step 2 passed: {len(step2_passed)} extreme oversold candidates\n", flush=True)

    if not step2_passed:
        print("No candidates passed Step 2. Pipeline halting.")
        return

    # ── News Sentiment Check (informational, no filtering) ──
    print("─── NEWS SENTIMENT (informational) ───\n", flush=True)
    for candidate in step2_passed:
        ticker = candidate["ticker"]
        sector = candidate.get("sector", "?")
        try:
            ok_ns, out_ns = _run([
                sys.executable, "scripts/news_sentiment.py", "--json", "full", ticker, candidate.get("sector", "Technology")
            ], timeout=15)
            if ok_ns:
                candidate["news_sentiment"] = json.loads(out_ns)
        except Exception:
            candidate["news_sentiment"] = {"score": 0.0, "signals": ["unavailable"]}
        
        ns = candidate.get("news_sentiment", {})
        ns_score = ns.get("score", 0)
        emoji = "🟢" if ns_score > 0.3 else "🔴" if ns_score < -0.3 else "⚪"
        sigs = ns.get("signals", ["no data"])[:2]
        print(f"  {emoji} {ticker:6s} | news: {ns_score:+.2f} | {'; '.join(sigs[:2])}", flush=True)
    print()

    # ---- Steps 3 & 4: Cognitive Review + Proposal ----
    print("─── STEP 3 & 4: Cognitive Review + Trade Proposal ───\n", flush=True)

    proposals = []
    for candidate in step2_passed:
        ticker = candidate["ticker"]
        proposal = step4_proposal(candidate)
        proposals.append(proposal)

        print(f"  ▶ {ticker}")
        print(f"    Sector:     {proposal['sector']}")
        print(f"    Profile:    {proposal['profile']}")
        print(f"    RSI-2:      {proposal['rsi2']:.1f} (threshold {proposal['rsi2_threshold']})")
        print(f"    Price:      ${proposal['price']:.2f}")
        print(f"    Shares:     {proposal['adjusted_shares']} (reduced {proposal['size_reduction_pct']:.0f}%)")
        print(f"    Stop:       ${proposal['stop_loss']:.2f}")
        print(f"    Target:     ${proposal['take_profit']:.2f}")
        print(f"    Exit rule:  {proposal['exit_rule']}")
        print(f"    Trigger:    {proposal['exit_trigger']}")
        ns = candidate.get("news_sentiment", {})
        if ns and ns.get("score", 0) != 0:
            print(f"    📰 News:   {ns.get('score', 0):+.2f} ({ns.get('source', '?')})")
        print()

    # ---- Cache orders (if not dry-run) ----
    if not args.dry_run:
        print("─── Order Cache ───\n", flush=True)
        for prop in proposals:
            cmd = [
                sys.executable, "scripts/order_cache.py", "add",
                "--ticker", prop["ticker"],
                "--action", "ENTER",
                "--close", str(prop["price"]),
                "--score", "0",  # Momentum-dip strategy doesn't use three-pillar score
                "--note", f"MDC: RSI-2={prop['rsi2']:.1f} (thresh {prop['rsi2_threshold']}), sector={prop['sector']}",
            ]
            ok, out = _run(cmd)
            if ok:
                for line in out.split("\n"):
                    if "Created:" in line:
                        oid = line.split("|")[0].replace("Created:", "").strip()
                        print(f"  {prop['ticker']}: {oid} created → pending_confirm")
                        # Set entry params
                        _run([
                            sys.executable, "scripts/order_cache.py", "entry", oid,
                            "--limit", str(prop["entry_price"]),
                            "--qty", str(prop["adjusted_shares"]),
                            "--stop", str(prop["stop_loss"]),
                            "--target", str(prop["take_profit"]),
                        ])
                        _run([
                            sys.executable, "scripts/order_cache.py", "update", oid,
                            "--status", "pending_confirm",
                        ])
            else:
                print(f"  {prop['ticker']}: ❌ cache error")

    # ---- Persist to DB ----
    if not args.dry_run:
        db_written = _save_mdc_to_db(proposals, step1_passed, step2_passed)
        if db_written:
            print(f"\n  DB: {db_written} rows persisted")

    # ---- Summary ----
    print(f"\n{'='*60}")
    print(f"  MOMENTUM-DIP CATALYST — SUMMARY")
    print(f"{'='*60}")
    print(f"  Universe:  {total} tickers")
    print(f"  Step 1:    {len(step1_passed)} passed (SMA200 + CHOP filter)")
    print(f"  Step 2:    {len(step2_passed)} extreme oversold (RSI-2 trigger)")
    print(f"  Proposals: {len(proposals)}")
    print(f"  Mode:      {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"{'─'*60}")

    for prop in proposals:
        print(f"\n  ▶ {prop['ticker']} — {prop['profile']}")
        print(f"    Entry: ${prop['entry_price']:.2f} x {prop['adjusted_shares']} shares")
        print(f"    Stop:  ${prop['stop_loss']:.2f}")
        print(f"    Exit:  {prop['exit_trigger']}")

    if not proposals:
        print("\n  No actionable dip candidates today.")
    print(f"{'='*60}")

    if args.json:
        print(json.dumps({
            "status": "complete",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "universe": total,
            "step1_passed": len(step1_passed),
            "step2_passed": len(step2_passed),
            "proposals": proposals,
        }, indent=2))


# ── DB persistence ───────────────────────────────────────────────────

def _save_mdc_to_db(proposals: list[dict], step1_passed: list, step2_passed: list) -> int:
    """Persist momentum-dip proposals to the trades table."""
    try:
        import psycopg2
        
        db_url = os.environ.get(
            "DATABASE_URL",
            "postgresql://admin:tradingdesk@localhost:5432/trading_desk"
        )
        
        conn = psycopg2.connect(db_url)
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
        
        written = 0
        now = datetime.now(timezone.utc)
        
        for prop in proposals:
            ticker = prop["ticker"]
            trade_id = str(uuid.uuid4())
            
            cur.execute("""
                INSERT INTO trades (
                    id, ticker, strategy, decision, reasoning,
                    proposed_price, position_size, stop_loss, take_profit,
                    risk_reward_ratio, status,
                    rsi_2_value, chop_value, sma_200_value, sector,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, 'momentum_dip', 'ENTER', %s,
                    %s, %s, %s, %s,
                    %s, 'PENDING',
                    %s, %s, %s, %s,
                    %s, %s
                )
            """, (
                trade_id, ticker,
                f"RSI-2={prop.get('rsi2', 0):.1f} (thresh {prop.get('rsi2_threshold', 0)}), CHOP={prop.get('chop', 0):.1f}, SMA200={prop.get('sma200', 0):.2f}",
                prop.get("entry_price", 0), prop.get("adjusted_shares", 0),
                prop.get("stop_loss", 0), prop.get("take_profit", 0),
                1.6,  # risk:reward: 8% target / 5% stop
                prop.get("rsi2", 0), prop.get("chop", 0),
                prop.get("sma200", 0), prop.get("sector", ""),
                now, now
            ))
            written += 1
        
        # Also save non-actionable candidates for pipeline funnel stats
        for ticker_data in step1_passed:
            ticker = ticker_data.get("ticker", ticker_data) if isinstance(ticker_data, dict) else ticker_data
            # Check if already written as a proposal
            already = any(p["ticker"] == ticker for p in proposals)
            if not already:
                trade_id = str(uuid.uuid4())
                rsi2 = ticker_data.get("rsi2", 30) if isinstance(ticker_data, dict) else 30
                cur.execute("""
                    INSERT INTO trades (
                        id, ticker, strategy, decision, reasoning,
                        proposed_price, position_size, status,
                        rsi_2_value, chop_value, sma_200_value, sector,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, 'momentum_dip', 'NO_TRADE', %s,
                        %s, 0, 'REJECTED',
                        %s, %s, %s, %s,
                        %s, %s
                    )
                """, (
                    trade_id, ticker,
                    f"RSI-2 {rsi2:.1f} passed oversold threshold but rejected",
                    ticker_data.get("price", 0) if isinstance(ticker_data, dict) else 0,
                    rsi2 if isinstance(ticker_data, dict) else 0,
                    ticker_data.get("chop", 0) if isinstance(ticker_data, dict) else 0,
                    ticker_data.get("sma200", 0) if isinstance(ticker_data, dict) else 0,
                    ticker_data.get("sector", "") if isinstance(ticker_data, dict) else "",
                    now, now
                ))
                written += 1
        
        conn.commit()
        cur.close()
        conn.close()
        return written
    except Exception as e:
        print(f"  DB write: {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    main()
