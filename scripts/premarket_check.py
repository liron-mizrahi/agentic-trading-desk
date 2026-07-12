#!/usr/bin/env python3
"""
premarket_check.py
==================
Pre-market sanity check for pending orders.
Runs 1 hour before market open. For each order in `confirmed` status:
  - Fetches current price from IBKR
  - Compares to EOD close price
  - If gap > |2%|: flags for reassessment (status → sanity_check_fail)
  - If gap ≤ |2%|: marks as sanity_check_ok → ready for manual execution

Usage:
  python3 scripts/premarket_check.py                     # Check all confirmed orders
  python3 scripts/premarket_check.py --dry-run            # Report without status changes
  python3 scripts/premarket_check.py --json               # Machine-readable output
  python3 scripts/premarket_check.py --force ORD-xxx      # Force-check a specific order
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(SCRIPT_DIR)

THRESHOLD_GAP_PCT = 2.0  # Flag if gap exceeds this in either direction


def _run(cmd: list, timeout: int = 20) -> tuple[bool, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=WORKSPACE)
        if result.returncode == 0:
            return True, result.stdout
        return False, result.stderr
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except FileNotFoundError as e:
        return False, str(e)


def _run_order_cache(args: list) -> tuple[bool, str]:
    return _run([sys.executable, "scripts/order_cache.py"] + args)


def get_quote(ticker: str) -> dict | None:
    """Fetch current quote from IBKR. Returns {'last', 'bid', 'ask'} or None."""
    ok, out = _run([sys.executable, "scripts/ibkr_webapi.py", "quote", ticker])
    if not ok:
        return None
    try:
        data = json.loads(out)
        return data
    except json.JSONDecodeError:
        return None


def check_order(order: dict, dry_run: bool) -> dict:
    """Check a single order's pre-market price."""
    ticker = order["ticker"]
    close = order.get("close_price", 0)
    order_id = order["id"]

    if not close or close <= 0:
        return {
            "order_id": order_id,
            "ticker": ticker,
            "status": "error",
            "message": "No close price in order record",
        }

    print(f"  📡 Checking {ticker} (close: ${close:.2f})...", end=" ", flush=True)
    quote = get_quote(ticker)

    if not quote:
        return {
            "order_id": order_id,
            "ticker": ticker,
            "status": "error",
            "message": "IBKR quote unavailable (market closed? no subscription?)",
        }

    # Use last price, fall back to bid/ask midpoint
    current = quote.get("last")
    if current is None:
        bid = quote.get("bid")
        ask = quote.get("ask")
        if bid is not None and ask is not None:
            current = (bid + ask) / 2
            source = "midpoint"
        else:
            return {
                "order_id": order_id,
                "ticker": ticker,
                "status": "error",
                "message": f"No price available (last={quote.get('last')}, bid={quote.get('bid')}, ask={quote.get('ask')})",
            }
    else:
        source = "last"

    gap_pct = round((current - close) / close * 100, 2)
    print(f"${current:.2f} ({source}) | gap: {gap_pct:+.1f}%", flush=True)

    if dry_run:
        print(f"    [DRY RUN] Would set pre-market: ${current}")
        return {
            "order_id": order_id,
            "ticker": ticker,
            "close": close,
            "current": current,
            "gap_pct": gap_pct,
            "passed": abs(gap_pct) <= THRESHOLD_GAP_PCT,
            "status": "dry_run",
        }

    # Store pre-market price in cache
    ok, _ = _run_order_cache(["premarket", order_id, "--premarket", str(current)])
    if not ok:
        return {
            "order_id": order_id,
            "ticker": ticker,
            "status": "error",
            "message": "Failed to update order cache",
        }

    if abs(gap_pct) > THRESHOLD_GAP_PCT:
        # Flag for reassessment
        direction = "up" if gap_pct > 0 else "down"
        _run_order_cache(["update", order_id, "--status", "sanity_check_fail"])
        return {
            "order_id": order_id,
            "ticker": ticker,
            "close": close,
            "current": current,
            "gap_pct": gap_pct,
            "passed": False,
            "status": "sanity_check_fail",
            "message": f"⚠️ Gapped {direction} {abs(gap_pct):.1f}% — flagged for reassessment",
        }
    else:
        # Passed — mark as ready
        _run_order_cache(["update", order_id, "--status", "sanity_check_ok"])
        return {
            "order_id": order_id,
            "ticker": ticker,
            "close": close,
            "current": current,
            "gap_pct": gap_pct,
            "passed": True,
            "status": "sanity_check_ok",
            "message": f"✅ Gap {gap_pct:+.1f}% — within threshold, ready for execution",
        }


def main():
    p = argparse.ArgumentParser(description="Pre-market sanity check for pending orders")
    p.add_argument("--dry-run", action="store_true", help="Report without status changes")
    p.add_argument("--json", action="store_true", help="JSON output")
    p.add_argument("--force", type=str, default=None, help="Force-check a specific order by ID")
    args = p.parse_args()

    print(f"Agentic Trading Desk — Pre-Market Sanity Check")
    print(f"  Run:   {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Threshold: {THRESHOLD_GAP_PCT}% gap")
    print(f"  Mode:  {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()

    if args.force:
        # Check a single order by ID
        ok, out = _run_order_cache(["get", args.force, "--json"])
        if not ok:
            print(f"  ❌ Order {args.force} not found")
            sys.exit(1)
        try:
            order = json.loads(out)
        except json.JSONDecodeError:
            print(f"  ❌ Failed to parse order data")
            sys.exit(1)
        orders_to_check = [order]
    else:
        # List confirmed orders
        ok, out = _run_order_cache(["list", "--status", "confirmed", "--json"])
        if not ok:
            print(f"  ❌ Failed to read order cache: {out[:200]}")
            sys.exit(1)
        try:
            orders = json.loads(out)
        except json.JSONDecodeError:
            orders = []
        orders_to_check = orders
        print(f"  Found {len(orders_to_check)} confirmed order(s) to check\n")

    if not orders_to_check:
        print("  No confirmed orders pending pre-market check.")
        return

    results = []
    for order in orders_to_check:
        result = check_order(order, args.dry_run)
        results.append(result)

    # Summary
    passed = [r for r in results if r.get("passed")]
    failed = [r for r in results if r.get("status") == "sanity_check_fail"]
    errors = [r for r in results if r.get("status") == "error"]

    print(f"\n{'─' * 50}")
    print(f"  Summary: {len(passed)} passed | {len(failed)} flagged | {len(errors)} errors")

    for r in failed:
        print(f"  ⚠  {r['ticker']}: {r['message']}")
    for r in errors:
        print(f"  ❌ {r.get('ticker', '?' )}: {r['message']}")

    if args.json:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
