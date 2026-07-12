#!/usr/bin/env python3
"""
analyze.py — Full analysis pipeline for Agentic Trading Desk
=============================================================
Fetches IBKR data → runs three-pillar scoring → outputs structured JSON
for the agent's persona chain to interpret.

Usage:
  python3 scripts/analyze.py AAPL
  python3 scripts/analyze.py AAPL --holding
  python3 scripts/analyze.py AAPL --macro 1
  python3 scripts/analyze.py AAPL --json > /tmp/analysis.json
"""

import argparse
import json
import os
import subprocess
import sys
from typing import Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(SCRIPT_DIR)


def run(cmd: list, input_data: Optional[str] = None) -> dict:
    """Run a script and parse its JSON output."""
    result = subprocess.run(
        cmd, capture_output=True, text=True, input=input_data, cwd=WORKSPACE
    )
    if result.returncode != 0:
        return {"error": result.stderr.strip()}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": f"Invalid JSON output: {result.stdout[:200]}"}


def analyze_ticker(symbol: str, macro_score: Optional[int] = None,
                   holding: Optional[bool] = None) -> dict:
    """Full pipeline: fetch data → score → output."""
    print(f"  📡 Fetching {symbol} data from IBKR...", file=sys.stderr)

    # Step 1: Get historical data
    hist = run([sys.executable, "scripts/ibkr_webapi.py", "historicals", symbol])
    if "error" in hist:
        return hist

    closes = hist.get("close", [])
    if len(closes) < 50:
        return {"error": f"Only {len(closes)} bars for {symbol}, need 50+"}

    print(f"  📊 {len(closes)} bars loaded ({min(closes):.2f} - {max(closes):.2f})", file=sys.stderr)

    # Step 2: Get current quote (may be null without market data subscription)
    quote = run([sys.executable, "scripts/ibkr_webapi.py", "quote", symbol])

    # Step 3: Get positions to check if we hold this ticker
    if holding is None:
        positions = run([sys.executable, "scripts/ibkr_webapi.py", "positions"])
        if "error" not in positions:
            for pos in positions.get("positions", []):
                if pos.get("symbol", "").upper() == symbol.upper():
                    holding = True
                    print(f"  💼 Position: {pos['position']} shares @ avg ${pos['avgCost']:.2f}", file=sys.stderr)
                    break
        if holding is None:
            holding = False

    # Step 4: Run macro pillar (or use provided score)
    if macro_score is None:
        print(f"  🌍 Fetching macro ETFs...", file=sys.stderr)
        macro_data = run([sys.executable, "scripts/ibkr_webapi.py", "macro-etfs"])
        if "error" not in macro_data and macro_data.get("series"):
            # Write macro input and run macro_pillar
            with open("/tmp/macro_input.json", "w") as f:
                json.dump({"series": macro_data["series"]}, f)
            macro_result = run([sys.executable, "scripts/macro_pillar.py",
                               "/tmp/macro_input.json", "--json"])
            if "error" not in macro_result:
                macro_score = macro_result.get("pillar_score", 0)
                print(f"  🌍 Macro pillar: {macro_score:+d} ({macro_result.get('regime', 'N/A')})", file=sys.stderr)
            else:
                macro_score = 0
        else:
            macro_score = 0

    # Step 5: Build score input and run score.py
    score_input = {
        "symbol": symbol.upper(),
        "close": closes,
        "macro_score": macro_score,
        "holding": holding,
    }

    with open("/tmp/score_input.json", "w") as f:
        json.dump(score_input, f)

    print(f"  🧮 Computing three-pillar score...", file=sys.stderr)
    scorecard = run([sys.executable, "scripts/score.py", "/tmp/score_input.json", "--json"])
    if "error" in scorecard:
        return scorecard

    # Step 6: Build final output
    result = {
        "ticker": symbol.upper(),
        "price": {
            "last": quote.get("last"),
            "bid": quote.get("bid"),
            "ask": quote.get("ask"),
            "note": "Quote requires IBKR market data subscription" if quote.get("last") is None else None,
        },
        "holding": holding,
        "n_bars": scorecard.get("n_bars", len(closes)),
        "pillars": scorecard.get("pillars", {}),
        "pillar_total": scorecard.get("pillar_total", 0),
        "decision": scorecard.get("decision", {}),
        "indicators": scorecard.get("indicators", {}),
        "macro": {
            "score": macro_score,
        },
    }

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Full analysis pipeline for Agentic Trading Desk")
    parser.add_argument("symbol", help="Ticker symbol (e.g., AAPL)")
    parser.add_argument("--macro", type=int, default=None,
                        help="Override macro score (-2 to +2)")
    parser.add_argument("--holding", action="store_true", default=None,
                        help="Force holding=true")
    parser.add_argument("--no-holding", action="store_true", default=None,
                        help="Force holding=false")
    parser.add_argument("--json", action="store_true",
                        help="Output raw JSON (for pipelining)")

    args = parser.parse_args()

    # Resolve holding flag
    holding = None
    if args.holding:
        holding = True
    elif args.no_holding:
        holding = False

    result = analyze_ticker(args.symbol, args.macro, holding)

    if "error" in result:
        print(f"❌ {result['error']}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    # Human-readable output
    p = result["pillars"]
    d = result["decision"]
    f = d.get("flags", {})

    print(f"\n{'═'*54}")
    print(f" {result['ticker']}  ·  {result['n_bars']} bars")
    if result["price"]["last"]:
        print(f" Last: ${result['price']['last']}")
    print(f" {'holding' if result['holding'] else 'flat'}")
    print(f"{'═'*54}")

    def line(name, sc, detail):
        s = f"{sc:+d}" if sc is not None else " ?"
        print(f"  {name:<16} {s:>3}   {detail}")

    line("Trend", p.get("trend", {}).get("score"),
         p.get("trend", {}).get("detail", ""))
    line("Momentum", p.get("momentum", {}).get("score"),
         p.get("momentum", {}).get("detail", ""))
    line("Macro-Sentiment", p.get("macro_sentiment", {}).get("score"),
         p.get("macro_sentiment", {}).get("detail", ""))

    print(f"  {'─'*50}")
    print(f"  TOTAL: {result['pillar_total']:+d}")
    print(f"  ► {d.get('action')}  —  {d.get('rationale')}")
    print(f"    {d.get('framing', '')}")

    if f.get("exhaustion"):
        print(f"    ⚠ exhaustion: {'; '.join(f['exhaustion'])}")
    if f.get("bearish"):
        print(f"    ⚠ bearish: {'; '.join(f['bearish'])}")
    if f.get("rebound"):
        print(f"    ✅ rebound: {'; '.join(f['rebound'])}")
    if f.get("death_cross"):
        print("    ⚠ active death-cross")


if __name__ == "__main__":
    sys.exit(main())
