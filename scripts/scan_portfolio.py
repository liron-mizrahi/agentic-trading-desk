#!/usr/bin/env python3
"""
scan_portfolio.py — Scan all current positions with full analysis
=================================================================
Runs the three-pillar pipeline on every open position.

Usage:
  python3 scripts/scan_portfolio.py
  python3 scripts/scan_portfolio.py --json
"""

import json
import os
import subprocess
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def run(cmd: list) -> dict:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {"error": result.stderr.strip()}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": f"Invalid JSON: {result.stdout[:200]}"}


def main():
    # Get portfolio positions
    positions = run([sys.executable, f"{SCRIPT_DIR}/ibkr_webapi.py", "positions"])
    if "error" in positions:
        print(f"❌ {positions['error']}")
        sys.exit(1)

    portfolio = run([sys.executable, f"{SCRIPT_DIR}/ibkr_webapi.py", "portfolio"])

    holdings = positions.get("positions", [])
    if not holdings:
        print("📭 No open positions.")
        return

    print(f"\n{'='*60}")
    print(f"  PORTFOLIO SCAN  ·  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}")
    print(f"  Positions: {len(holdings)}")
    total_value = sum(p.get("mktValue", 0) for p in holdings)
    total_pnl = sum(p.get("unrealizedPNL", 0) for p in holdings)
    print(f"  Market value: ${total_value:,.2f}")
    print(f"  Unrealized P&L: ${total_pnl:+.2f}")
    print(f"{'='*60}\n")

    results = []
    for pos in holdings:
        sym = pos["symbol"]
        qty = pos["position"]
        price = pos.get("mktPrice", 0)
        cost = pos.get("avgCost", 0)
        pnl = pos.get("unrealizedPNL", 0)
        value = pos.get("mktValue", 0)

        print(f"── Analyzing {sym} ({qty} shares @ ${cost:.2f}) ──")

        # Run analysis
        result = run([sys.executable, f"{SCRIPT_DIR}/analyze.py", sym, "--holding", "--json"])
        if "error" in result:
            print(f"  ❌ {result['error']}\n")
            continue

        d = result.get("decision", {})
        total = result.get("pillar_total", 0)

        print(f"  Score: {total:+d}  →  {d.get('action', 'N/A')}")
        print(f"  P&L: ${pnl:+.2f}  ({((price/cost)-1)*100:+.1f}%)\n")

        results.append({
            "symbol": sym,
            "position": qty,
            "avgCost": cost,
            "mktPrice": price,
            "pnl": pnl,
            "pnl_pct": round(((price / cost) - 1) * 100, 1) if cost else 0,
            "score": total,
            "decision": d.get("action", "N/A"),
            "detail": result,
        })

    # Summary
    print(f"{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    for r in results:
        action = r["decision"]
        icon = "🟢" if "HOLD" in action or "RE-ENTRY" in action else \
               "🔴" if "EXIT" in action else \
               "🟡" if "WAIT" in action or "OBSERVE" in action else "⚪"
        print(f"  {icon} {r['symbol']:<6} {r['score']:+d}  {action:<25} P&L: ${r['pnl']:+.2f} ({r['pnl_pct']:+.1f}%)")


if __name__ == "__main__":
    main()
