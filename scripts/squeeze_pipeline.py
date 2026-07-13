#!/usr/bin/env python3
"""
squeeze_pipeline.py
====================
Bollinger Band Squeeze Breakout Strategy — Pipeline 3.

Classic setup: when Bollinger Band bandwidth contracts to a multi-period low
(the "squeeze"), it signals a volatility compression that typically resolves
into a directional breakout. This pipeline detects the squeeze and enters on
expansion with momentum confirmation.

Funnel:
  Step 1 — Squeeze Detection: BB bandwidth at 20-period minimum
  Step 2 — Expansion Trigger: bandwidth expanding + %B crossing 0.5
  Step 3 — Momentum Filter: RSI-14 > 50, MACD histogram positive
  Step 4 — Trade Proposal with volatility-based position sizing

Usage:
  python3 scripts/squeeze_pipeline.py                           # Full run
  python3 scripts/squeeze_pipeline.py --dry-run                  # Preview only
  python3 scripts/squeeze_pipeline.py --json                     # Machine-readable
  python3 scripts/squeeze_pipeline.py --sectors Technology       # Focus specific
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


# ── Sector ticker universe ─────────────────────────────────────────────

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


# ── Step 1: Squeeze Detection ─────────────────────────────────────────

def detect_squeeze(ind: dict, period: int = 20) -> dict:
    """
    Detect if Bollinger Band bandwidth is at a period-low (squeeze).

    A squeeze means bandwidth has contracted to its lowest level in `period` bars.
    We detect this retroactively by checking historical bandwidth against current.
    Returns squeeze status and metadata.
    """
    bw = ind.get("bb_bandwidth")
    if bw is None:
        return {"squeezed": False, "reason": "No bandwidth data"}

    # Bandwidth alone tells us the current state; without historical bandwidth
    # series we estimate squeeze by checking if bandwidth is below a threshold.
    # Typical squeeze thresholds: bandwidth < 0.04 (4%) for equities.
    SQUEEZE_THRESHOLD = 0.04  # 4% — anything below is a tight squeeze

    if bw < SQUEEZE_THRESHOLD:
        return {
            "squeezed": True,
            "bandwidth": round(bw, 4),
            "threshold": SQUEEZE_THRESHOLD,
            "severity": "tight" if bw < 0.02 else "moderate",
        }
    elif bw < SQUEEZE_THRESHOLD * 1.5:
        return {
            "squeezed": True,
            "bandwidth": round(bw, 4),
            "threshold": SQUEEZE_THRESHOLD * 1.5,
            "severity": "forming",
        }
    else:
        return {
            "squeezed": False,
            "bandwidth": round(bw, 4),
            "reason": f"Bandwidth {bw:.3f} above squeeze threshold",
        }


# ── Step 2: Expansion Trigger ──────────────────────────────────────────

def detect_expansion(ind: dict, squeeze: dict) -> dict:
    """
    Detect breakout from squeeze: %B must cross 0.5 (price moving from
    lower half to upper half of the bands), and momentum must confirm.
    """
    pct_b = ind.get("percent_b")
    rsi14 = ind.get("rsi14")
    macd_hist = ind.get("macd_hist")

    if pct_b is None:
        return {"triggered": False, "reason": "No %B data"}

    signals = []
    triggers = 0

    # Rule 1: %B > 0.5 — price in upper half of bands (bullish breakout)
    if pct_b > 0.5:
        triggers += 1
        signals.append(f"%B={pct_b:.2f} > 0.5 ✅")
    else:
        signals.append(f"%B={pct_b:.2f} ≤ 0.5 (no breakout)")

    # Rule 2: RSI-14 > 50 — momentum supportive
    if rsi14 is not None and rsi14 > 50:
        triggers += 1
        signals.append(f"RSI-14={rsi14:.1f} > 50 ✅")
    elif rsi14 is not None:
        signals.append(f"RSI-14={rsi14:.1f} ≤ 50 (weak)")

    # Rule 3: MACD histogram positive — bullish momentum
    if macd_hist is not None and macd_hist > 0:
        triggers += 1
        signals.append("MACD histogram > 0 ✅")
    elif macd_hist is not None:
        signals.append(f"MACD hist={macd_hist:.4f} ≤ 0 (bearish)")

    direction = "bullish" if triggers >= 2 else "no_trigger"

    return {
        "triggered": triggers >= 2,
        "direction": direction,
        "triggers": triggers,
        "signals": signals,
        "percent_b": round(pct_b, 3) if pct_b else None,
    }


# ── Step 3: Position Sizing by Volatility ──────────────────────────────

def size_position(ind: dict, price: float) -> dict:
    """
    Size position inversely to volatility.
    Wider bandwidth = more volatile = smaller position.
    """
    bw = ind.get("bb_bandwidth", 0.04)
    base_shares = 100

    # Normalize: at 4% bandwidth = full size, at 12% = half size
    vol_factor = max(0.3, min(1.0, 0.04 / max(bw, 0.01)))
    shares = int(base_shares * vol_factor)

    # ATR-based stop: 1.5x the band half-width as a proxy for ATR
    bb_upper = ind.get("bb_upper", 0)
    bb_mid = ind.get("bb_mid", 0)
    half_range = abs(bb_upper - bb_mid) if bb_upper and bb_mid else price * 0.03
    stop_distance = half_range * 2.0

    stop_loss = round(price - stop_distance, 2)
    take_profit = round(price + stop_distance * 1.5, 2)

    return {
        "shares": shares,
        "volatility_factor": round(vol_factor, 2),
        "entry_price": round(price, 2),
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk_per_share": round(stop_distance, 2),
    }


# ── Main Pipeline ──────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Bollinger Band Squeeze Breakout Pipeline")
    p.add_argument("--sectors", type=str, default=None,
                    help="Comma-separated sector focus (default: all)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-cache", action="store_true")

    args = p.parse_args()

    scan_sectors = (
        [s.strip() for s in args.sectors.split(",")]
        if args.sectors else list(SECTOR_TICKERS.keys())
    )

    print(f"Bollinger Squeeze Breakout — Pipeline 3")
    print(f"  Run:      {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Sectors:  {', '.join(scan_sectors)}")
    print(f"  Mode:     {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()

    all_tickers = []
    for sector in scan_sectors:
        for t in SECTOR_TICKERS.get(sector, []):
            all_tickers.append((t, sector))

    total = len(all_tickers)
    print(f"Universe: {total} tickers\n")
    print("─── STEP 1: Squeeze Detection ───", flush=True)

    squeezed = []
    for i, (ticker, sector) in enumerate(all_tickers, 1):
        print(f"  [{i}/{total}] {ticker:6s} ({sector:20s}) ... ", end="", flush=True)

        data = fetch_ohlcv(ticker)
        if data is None:
            print("❌ no data", flush=True)
            continue

        ind = I.compute(data.get("close", []), 5, data.get("high"), data.get("low"))
        squeeze = detect_squeeze(ind)

        if squeeze["squeezed"]:
            bw = squeeze["bandwidth"]
            sev = squeeze["severity"]
            price = ind.get("close", 0)
            print(f"🔒 SQUEEZE ({sev}, bw={bw:.3f}) @ ${price:.2f}", flush=True)
            squeezed.append({"ticker": ticker, "sector": sector, "ind": ind, "squeeze": squeeze, "data": data})
        else:
            print(f"⏭ {squeeze.get('reason', 'no squeeze')}", flush=True)

    print(f"\n  Step 1 passed: {len(squeezed)}/{total} in squeeze\n", flush=True)

    if not squeezed:
        print("No tickers in squeeze. Pipeline halting.")
        return

    print("─── STEP 2: Expansion Trigger ───", flush=True)

    triggered = []
    for entry in squeezed:
        ticker = entry["ticker"]
        ind = entry["ind"]
        price = ind.get("close", 0)
        expansion = detect_expansion(ind, entry["squeeze"])

        status = " ".join(expansion.get("signals", []))
        if expansion["triggered"]:
            print(f"  {ticker:6s} @ ${price:.2f} — 🚀 BREAKOUT {status}", flush=True)
            triggered.append({**entry, "expansion": expansion})
        else:
            print(f"  {ticker:6s} @ ${price:.2f} — waiting ({status})", flush=True)

    print(f"\n  Step 2 passed: {len(triggered)} breakouts\n", flush=True)

    if not triggered:
        print("No breakouts from squeeze. Pipeline halting.")
        return

    print("─── STEP 3 & 4: Position Sizing + Proposal ───\n", flush=True)

    proposals = []
    for entry in triggered:
        ticker = entry["ticker"]
        ind = entry["ind"]
        price = ind.get("close", 0)
        sizing = size_position(ind, price)
        squeeze = entry["squeeze"]
        expansion = entry["expansion"]

        proposal = {
            "ticker": ticker,
            "sector": entry["sector"],
            "strategy": "squeeze_breakout",
            "action": "ENTER",
            "entry_price": sizing["entry_price"],
            "shares": sizing["shares"],
            "stop_loss": sizing["stop_loss"],
            "take_profit": sizing["take_profit"],
            "risk_per_share": sizing["risk_per_share"],
            "squeeze_severity": squeeze["severity"],
            "bandwidth_at_entry": squeeze["bandwidth"],
            "percent_b": expansion.get("percent_b"),
        }
        proposals.append(proposal)

        print(f"  ▶ {ticker}")
        print(f"    Squeeze:  {squeeze['severity']} (bw={squeeze['bandwidth']:.3f})")
        print(f"    Entry:    ${sizing['entry_price']:.2f} x {sizing['shares']} shares")
        print(f"    Stop:     ${sizing['stop_loss']:.2f}")
        print(f"    Target:   ${sizing['take_profit']:.2f}")
        print(f"    Risk:     ${sizing['risk_per_share']:.2f}/share")
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
                "--note", f"SQUEEZE: bw={prop['bandwidth_at_entry']:.3f} sev={prop['squeeze_severity']}",
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
    print(f"  SQUEEZE BREAKOUT — SUMMARY")
    print(f"{'='*60}")
    print(f"  Scanned:   {total} tickers")
    print(f"  Squeezed:  {len(squeezed)}")
    print(f"  Breakouts: {len(triggered)}")
    print(f"  Proposals: {len(proposals)}")
    print(f"  Mode:      {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"{'='*60}")

    if not proposals:
        print("\n  No actionable squeeze breakouts today.")

    if args.json:
        print(json.dumps({
            "status": "complete",
            "strategy": "squeeze_breakout",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "universe": total, "squeezed": len(squeezed),
            "triggered": len(triggered), "proposals": proposals,
        }, indent=2))


if __name__ == "__main__":
    main()
