#!/usr/bin/env python3
"""
dual_momentum_pipeline.py
==========================
Dual Momentum Rotation Strategy — Pipeline 4.

Based on Gary Antonacci's Dual Momentum framework:
  1. Absolute Momentum: Is the asset above T-bills? (trend filter)
  2. Relative Momentum: Which sectors have the strongest returns?

The strategy ranks sectors by 6-month total return, buys the top 2-3,
and rotates out of underperformers. If all sectors underperform T-bills,
capital sits in cash.

This directly executes the "capital rotation over accumulation" philosophy.

Funnel:
  Step 1 — Sector Return Ranking: compute 3m/6m/12m total returns per sector ETF
  Step 2 — Absolute Momentum Filter: must beat T-bill rate over 6m
  Step 3 — Top-N Selection: pick best 2-3 sectors
  Step 4 — Ticker Selection: pick top ticker per sector by relative strength
  Step 5 — Position Sizing: equal-weight allocation with volatility adjustment

Usage:
  python3 scripts/dual_momentum_pipeline.py                        # Full run
  python3 scripts/dual_momentum_pipeline.py --dry-run               # Preview
  python3 scripts/dual_momentum_pipeline.py --json                  # Machine output
  python3 scripts/dual_momentum_pipeline.py --top-n 3               # Top 3 sectors
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

# ── Sector ↔ ETF mapping ──────────────────────────────────────────────

SECTOR_ETFS = {
    "Technology":          "XLK",
    "Financial Services":  "XLF",
    "Industrials":         "XLI",
    "Communication":       "XLC",
    "Consumer Cyclical":   "XLY",
    "Healthcare":          "XLV",
    "Energy":              "XLE",
    "Consumer Defensive":  "XLP",
    "Basic Materials":     "XLB",
    "Real Estate":         "XLRE",
    "Utilities":           "XLU",
}

SECTOR_TICKERS = {
    "Technology":          ["AAPL", "MSFT", "NVDA", "GOOGL", "AVGO", "CRM", "AMD", "ADBE"],
    "Financial Services":  ["JPM", "BAC", "V", "MA", "GS", "WFC", "MS", "AXP"],
    "Industrials":         ["CAT", "GE", "HON", "UPS", "RTX", "BA", "DE", "LMT"],
    "Communication":       ["META", "NFLX", "DIS", "TMUS", "CMCSA"],
    "Consumer Cyclical":   ["AMZN", "TSLA", "HD", "LOW", "MCD", "SBUX", "NKE"],
    "Healthcare":          ["UNH", "LLY", "MRK", "ABBV", "PFE", "TMO", "ABT"],
    "Energy":              ["XOM", "CVX", "COP", "SLB", "OXY", "EOG"],
    "Consumer Defensive":  ["PG", "KO", "COST", "WMT", "PEP"],
    "Basic Materials":     ["LIN", "BHP", "APD", "FCX", "NEM"],
    "Real Estate":         ["PLD", "AMT", "CCI", "EQIX", "SPG", "O"],
    "Utilities":           ["NEE", "DUK", "SO", "D", "AEP"],
}


def _run(cmd: list, timeout: int = 60) -> tuple[bool, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=WORKSPACE)
        return result.returncode == 0, result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return False, str(e)


def fetch_etf_data(ticker: str) -> Optional[dict]:
    """Fetch OHLCV for an ETF."""
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


# ── Step 1: Sector Return Ranking ────────────────────────────────────

def compute_sector_return(ticker: str, months: int = 6) -> Optional[float]:
    """Compute total return for an ETF over N months.

    Approximates ~21 trading days per month.
    """
    data = fetch_etf_data(ticker)
    if not data:
        return None
    
    closes = data.get("close", [])
    bars_needed = months * 21
    if len(closes) < bars_needed:
        return None
    
    start_price = closes[-(bars_needed + 1)] if len(closes) > bars_needed else closes[0]
    end_price = closes[-1]
    
    if start_price <= 0:
        return None
    
    return ((end_price / start_price) - 1.0) * 100.0


def rank_sectors(etf_returns: dict[str, float], tbill_rate: float = 4.5) -> list[dict]:
    """Rank sectors by 6-month return. Filter out those below T-bill rate.

    Returns sorted list of dicts: {sector, etf, return_6m, return_3m, rank, beats_tbill}
    """
    ranked = []
    for sector, etf in SECTOR_ETFS.items():
        ret_6m = etf_returns.get(etf)
        if ret_6m is None:
            continue
        
        beats = ret_6m > tbill_rate
        ranked.append({
            "sector": sector,
            "etf": etf,
            "return_6m": round(ret_6m, 2),
            "beats_tbill": beats,
            "momentum_score": round(ret_6m, 2),  # raw return is the score
        })
    
    ranked.sort(key=lambda x: x["return_6m"], reverse=True)
    for i, r in enumerate(ranked):
        r["rank"] = i + 1
    
    return ranked


# ── Step 2: Absolute Momentum Filter ──────────────────────────────────

def filter_absolute_momentum(ranked: list[dict], tbill_rate: float) -> list[dict]:
    """Keep only sectors that beat the T-bill rate (absolute momentum filter)."""
    passed = [r for r in ranked if r["beats_tbill"]]
    
    # If fewer than 2 sectors pass, it's a risk-off signal — stay in cash
    return passed


# ── Step 3: Ticker Selection ─────────────────────────────────────────

def select_ticker(sector: str, top_n_sectors: list[dict]) -> Optional[dict]:
    """Pick the best ticker in a sector based on recent relative strength.

    Uses RSI-14 and distance from SMA50 to gauge individual strength.
    """
    tickers = SECTOR_TICKERS.get(sector, [])
    if not tickers:
        return None
    
    best_score = -float("inf")
    best_ticker = None
    best_ind = None
    
    for ticker in tickers[:3]:  # Check top 3 per sector for performance
        data = fetch_etf_data(ticker)
        if not data:
            continue
        
        ind = I.compute(data.get("close", []), 5)
        rsi14 = ind.get("rsi14", 50)
        sma50 = ind.get("sma50")
        close = ind.get("close", 0)
        
        if sma50 is None or close == 0:
            continue
        
        # Score: combine RSI strength + SMA50 distance
        sma_dist = (close / sma50 - 1) * 100
        score = rsi14 + sma_dist  # Higher = stronger
        
        if score > best_score:
            best_score = score
            best_ticker = ticker
            best_ind = ind
    
    if best_ticker:
        return {
            "ticker": best_ticker,
            "price": best_ind.get("close", 0),
            "rsi14": best_ind.get("rsi14"),
            "momentum_score": round(best_score, 1),
        }
    return None


# ── Step 4: Position Sizing ──────────────────────────────────────────

def size_allocation(num_positions: int, total_capital: float = 100_000.0) -> float:
    """Equal-weight allocation across selected sectors."""
    if num_positions <= 0:
        return 0.0
    
    # Max 60% deployed at any time, keep 40% reserve
    deployable = total_capital * 0.60
    per_position = deployable / num_positions
    return round(per_position, 2)


def compute_position(ticker_data: dict, allocation: float) -> dict:
    """Compute shares, stop, and target for a position."""
    price = ticker_data["price"]
    if price <= 0:
        return {"shares": 0, "entry_price": price, "stop_loss": price, "take_profit": price}
    
    shares = max(1, int(allocation / price))
    stop_loss = round(price * 0.93, 2)   # 7% stop (tight for rotation)
    take_profit = round(price * 1.15, 2)  # 15% target
    
    return {
        "shares": shares,
        "entry_price": round(price, 2),
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "allocation": allocation,
    }


# ── Main Pipeline ─────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Dual Momentum Rotation Pipeline")
    p.add_argument("--top-n", type=int, default=3, help="Number of top sectors to select")
    p.add_argument("--tbill", type=float, default=4.5, help="T-bill rate for absolute momentum")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-cache", action="store_true")

    args = p.parse_args()

    print(f"Dual Momentum Rotation — Pipeline 4")
    print(f"  Run:      {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  T-bill:   {args.tbill}%")
    print(f"  Top-N:    {args.top_n}")
    print(f"  Mode:     {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()

    # ── Step 1: Compute sector returns ──
    print("─── STEP 1: Sector Return Ranking ───", flush=True)
    etf_returns: dict[str, float] = {}
    for sector, etf in SECTOR_ETFS.items():
        ret = compute_sector_return(etf, months=6)
        if ret is not None:
            etf_returns[etf] = ret
            status = "✅" if ret > args.tbill else "⚠" if ret > 0 else "❌"
            print(f"  {sector:22s} ({etf:4s}): {ret:+7.2f}%  {status}  "
                  f"{'beats T-bill' if ret > args.tbill else 'below T-bill'}", flush=True)
        else:
            print(f"  {sector:22s} ({etf:4s}): no data", flush=True)

    print()

    # ── Step 2: Rank & Filter ──
    print("─── STEP 2: Absolute Momentum Filter ───", flush=True)
    ranked = rank_sectors(etf_returns, args.tbill)
    qualified = filter_absolute_momentum(ranked, args.tbill)

    print(f"  Sectors above T-bill ({args.tbill}%): {len(qualified)}/{len(ranked)}")
    for r in ranked[:5]:
        tag = "✅ BUY" if r["beats_tbill"] else "⏭ SKIP"
        print(f"  #{r['rank']:2d} {r['sector']:22s} ({r['etf']:4s}): {r['return_6m']:+7.2f}%  {tag}")
    print()

    if len(qualified) < 2:
        print("  ⚠ RISK-OFF: Fewer than 2 sectors above T-bill. Stay in cash.")
        rotation_signal = "CASH"
    else:
        rotation_signal = "ROTATE"
        print(f"  🟢 ROTATION SIGNAL: Invest in top {min(args.top_n, len(qualified))} sectors")
    print()

    # ── Step 3: Ticker Selection ──
    if rotation_signal == "CASH":
        print("No positions taken (risk-off regime).")
        return

    print("─── STEP 3: Ticker Selection ───\n", flush=True)
    
    top_sectors = qualified[:args.top_n]
    selected_tickers = []
    
    for sec_data in top_sectors:
        sector = sec_data["sector"]
        print(f"  {sector} (#{sec_data['rank']}, {sec_data['return_6m']:+.1f}%) ...", end=" ", flush=True)
        ticker = select_ticker(sector, top_sectors)
        if ticker:
            selected_tickers.append({**ticker, "sector": sector, "sector_return": sec_data["return_6m"]})
            print(f"{ticker['ticker']} @ ${ticker['price']:.2f} (score: {ticker['momentum_score']:.1f})", flush=True)
        else:
            print("no ticker", flush=True)

    if not selected_tickers:
        print("\nNo eligible tickers found. Staying in cash.")
        return

    # ── Step 4: Position Sizing & Proposals ──
    print(f"\n─── STEP 4: Position Sizing ───\n", flush=True)
    
    allocation = size_allocation(len(selected_tickers))
    proposals = []
    
    for entry in selected_tickers:
        pos = compute_position(entry, allocation)
        proposal = {
            "ticker": entry["ticker"],
            "sector": entry["sector"],
            "strategy": "dual_momentum",
            "action": "ENTER",
            "sector_return_6m": entry["sector_return"],
            "momentum_score": entry["momentum_score"],
            **pos,
        }
        proposals.append(proposal)
        
        print(f"  ▶ {entry['ticker']:6s} ({entry['sector']})")
        print(f"    Entry:    ${pos['entry_price']:.2f} x {pos['shares']} shares")
        print(f"    Stop:     ${pos['stop_loss']:.2f}")
        print(f"    Target:   ${pos['take_profit']:.2f}")
        print(f"    Alloc:    ${pos['allocation']:,.0f}")
        print()

    # ── Cache orders ──
    if not args.dry_run and not args.no_cache:
        print("─── Order Cache ───\n", flush=True)
        for prop in proposals:
            cmd = [
                sys.executable, "scripts/order_cache.py", "add",
                "--ticker", prop["ticker"],
                "--action", "ENTER",
                "--close", str(prop["entry_price"]),
                "--score", "0",
                "--note", f"DUAL_MOM: sector={prop['sector']} ret6m={prop['sector_return_6m']:+.1f}%",
            ]
            ok, out = _run(cmd)
            if ok:
                for line in out.split("\n"):
                    if "Created:" in line:
                        oid = line.split("|")[0].replace("Created:", "").strip()
                        print(f"  {prop['ticker']}: {oid} → pending_confirm")
                        _run([
                            sys.executable, "scripts/order_cache.py", "entry", oid,
                            "--limit", str(prop["entry_price"]),
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
    print(f"  DUAL MOMENTUM ROTATION — SUMMARY")
    print(f"{'='*60}")
    print(f"  Sectors scanned:  {len(ranked)}")
    print(f"  Above T-bill:     {len(qualified)}")
    print(f"  Positions:        {len(proposals)}")
    print(f"  Allocation/pos:   ${allocation:,.0f}")
    print(f"  Regime:           {'🟢 ROTATE' if rotation_signal == 'ROTATE' else '🔴 CASH'}")
    print(f"  Mode:             {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"{'='*60}")

    if args.json:
        print(json.dumps({
            "status": "complete",
            "strategy": "dual_momentum",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rotation_signal": rotation_signal,
            "tbill_rate": args.tbill,
            "sector_returns": {s: round(r, 2) for s, r in etf_returns.items()},
            "qualified_sectors": [q["sector"] for q in qualified],
            "proposals": proposals,
        }, indent=2))


if __name__ == "__main__":
    main()
