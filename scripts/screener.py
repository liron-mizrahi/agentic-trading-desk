#!/usr/bin/env python3
"""
screener.py
============
Opportunity screener for the Agentic Trading Desk.
No external scraping — uses IBKR API + macro_pillar engine.

Pipeline:
  1. Fetch market data via IBKR (macro ETFs + yield spread)
  2. Run macro_pillar to determine macro regime and sector bias
  3. Generate candidate watchlist aligned with current regime
  4. Score each candidate through the three-pillar engine

Usage:
  python3 scripts/screener.py                          # Sector scan + macro bias
  python3 scripts/screener.py --score --limit 5         # Score top candidates
  python3 scripts/screener.py --tickers XLV,XLU,XLP     # Score specific tickers
  python3 scripts/screener.py --refresh                 # Refresh market data first
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

# --------------------------------------------------------------------------
# Sector definitions
# --------------------------------------------------------------------------

# Ticker candidates per sector (large-cap liquid names, sorted by relevance)
SECTOR_TICKERS = {
    "Technology":          ["AAPL", "MSFT", "NVDA", "GOOGL", "AVGO", "CRM", "AMD", "ADBE", "INTC", "ORCL"],
    "Financial Services":  ["JPM", "BAC", "V", "MA", "GS", "WFC", "MS", "AXP", "BLK", "SCHW"],
    "Industrials":         ["CAT", "GE", "HON", "UPS", "RTX", "BA", "DE", "LMT", "MMM", "ETN"],
    "Communication":       ["META", "GOOGL", "NFLX", "DIS", "TMUS", "CMCSA", "CHTR", "EA", "ROKU", "SNAP"],
    "Consumer Cyclical":   ["AMZN", "TSLA", "HD", "LOW", "MCD", "SBUX", "NKE", "TJX", "TGT", "BKNG"],
    "Healthcare":          ["UNH", "LLY", "MRK", "ABBV", "PFE", "TMO", "ABT", "MDT", "SYK", "JNJ"],
    "Energy":              ["XOM", "CVX", "COP", "SLB", "OXY", "EOG", "HAL", "MPC", "VLO", "PSX"],
    "Consumer Defensive":  ["PG", "KO", "COST", "WMT", "PEP", "CL", "KMB", "GIS", "K", "SYY"],
    "Basic Materials":     ["LIN", "BHP", "APD", "RIO", "FCX", "NEM", "SHW", "DOW", "DD", "ECL"],
    "Real Estate":         ["PLD", "AMT", "CCI", "EQIX", "SPG", "O", "DLR", "AVB", "EQR", "WELL"],
    "Utilities":           ["NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "XEL", "PEG", "ED"],
}

# ETF proxy for sector momentum (traded, so IBKR has data)
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

# Macro pillar component names that imply defensive vs cyclical bias
DEFENSIVE_COMPONENTS = ["sector rotation", "XLP", "defensive"]
CYCLICAL_COMPONENTS = ["cyclical", "XLY", "credit", "risk-on"]


def refresh_market_data() -> bool:
    """Fetch fresh macro ETF data + yield spread from IBKR and Treasury.gov.
    
    Returns True on success.
    """
    print("  Fetching macro ETF data from IBKR... ", end="", flush=True)
    result = subprocess.run(
        ['python3', 'scripts/ibkr_webapi.py', 'macro-etfs'],
        capture_output=True, text=True, timeout=20
    )
    if result.returncode != 0:
        print("FAILED")
        return False
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("FAILED (bad JSON)")
        return False
    
    series = data.get('series', {})
    if not series:
        print("FAILED (empty series)")
        return False
    
    print(f"OK ({len(series)} ETFs)")
    
    # Fetch yield spread
    print("  Fetching yield spread from Treasury.gov... ", end="", flush=True)
    spread_result = subprocess.run(
        ['python3', 'scripts/yield_spread.py', '--history', '60', '--json'],
        capture_output=True, text=True, timeout=45
    )
    if spread_result.returncode == 0:
        try:
            spread_data = json.loads(spread_result.stdout)
            data['yield_spread'] = spread_data.get('yield_spread', [])
            data['as_of'] = spread_data.get('latest_raw', {}).get('date', '')
            print(f"OK ({spread_data.get('n_bars', 0)} bars)")
        except json.JSONDecodeError:
            print("PARSE ERROR")
    else:
        print("SKIPPED (will redistribute weight)")
    
    # Clean up series data: remove entries that are errors (not lists)
    series = data.get('series', {})
    clean_series = {}
    for k, v in series.items():
        if isinstance(v, list) and len(v) > 0:
            clean_series[k] = v
        else:
            print(f'    {k}: unavailable (will redistribute weight)')
    data['series'] = clean_series
    
    # Write to temp file for macro_pillar
    with open('/tmp/screener_data.json', 'w') as f:
        json.dump(data, f)
    
    return True


def run_macro_pillar() -> dict | None:
    """Run macro_pillar on current data. Returns pillar result dict."""
    data_path = '/tmp/screener_data.json'
    if not os.path.exists(data_path):
        return None
    
    result = subprocess.run(
        ['python3', 'scripts/macro_pillar.py', data_path, '--json'],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode != 0:
        return None
    
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def determine_bias(pillar: dict) -> dict:
    """Translate macro pillar output into sector bias."""
    composite = pillar.get('composite', 0)
    score = pillar.get('pillar_score', 0)
    regime = pillar.get('regime', 'Unknown')
    components = pillar.get('components', [])
    
    # Read individual component signals
    signal_map = {}
    for c in components:
        name = c.get('name', '')
        sig = c.get('signal')
        if sig is not None:
            signal_map[name.lower()] = sig
    
    # Determine tone
    tone = 'neutral'
    favored = []
    avoid = []
    
    # XLY/XLP negative → defensives favored
    sector_rotation = (
        signal_map.get('sector rotation (cyclical vs defensive)', None) or
        next((v for k, v in signal_map.items() if 'cyclical' in k and 'defensive' in k), None)
    )
    
    # Concentration signal: negative → broadening concerns → defensives
    concentration = next((v for k, v in signal_map.items() if 'concentration' in k), None)
    
    # Credit signal: positive → risk-on
    credit = next((v for k, v in signal_map.items() if 'credit' in k), None)
    
    # Size signal: positive → small caps → risk-on/cyclical
    size_signal = next((v for k, v in signal_map.items() if 'size' in k), None)
    
    if composite is not None:
        if composite < -0.5:
            tone = 'defensive'
            favored = ['Healthcare', 'Consumer Defensive', 'Utilities']
            avoid = ['Consumer Cyclical', 'Technology']
        elif composite > 0.5:
            tone = 'offensive'
            favored = ['Technology', 'Consumer Cyclical', 'Industrials']
            avoid = ['Utilities', 'Consumer Defensive']
        else:
            # Mixed — use component signals for fine-tuning
            defensive_count = 0
            cyclical_count = 0
            
            if sector_rotation is not None and sector_rotation < 0:
                defensive_count += 1
            elif sector_rotation is not None and sector_rotation > 0:
                cyclical_count += 1
            
            if concentration is not None and concentration < 0:
                defensive_count += 1
            elif concentration is not None and concentration > 0:
                cyclical_count += 1
            
            if credit is not None and credit > 0:
                cyclical_count += 1
            
            if size_signal is not None and size_signal > 0:
                cyclical_count += 1
            elif size_signal is not None and size_signal < 0:
                defensive_count += 1
            
            if defensive_count >= 2:
                tone = 'slightly_defensive'
                favored = ['Healthcare', 'Consumer Defensive', 'Utilities']
                avoid = ['Consumer Cyclical']
            elif cyclical_count >= 2:
                tone = 'slightly_offensive'
                favored = ['Technology', 'Industrials', 'Consumer Cyclical']
                avoid = ['Utilities']
            else:
                tone = 'neutral'
                favored = ['Healthcare', 'Technology', 'Industrials']
                avoid = []
    
    return {
        'score': score,
        'label': regime,
        'composite': composite,
        'tone': tone,
        'favored': favored,
        'avoid': avoid,
    }


def score_ticker(symbol: str, macro_score: int = 0) -> dict | None:
    """Run one ticker through the three-pillar scoring engine.
    
    Returns full scorecard or None on failure.
    """
    # Historical prices
    result = subprocess.run(
        ['python3', 'scripts/ibkr_webapi.py', 'historicals', symbol],
        capture_output=True, text=True, timeout=20
    )
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, KeyError):
        return None
    
    close = data.get('close', [])
    if len(close) < 100:
        return None
    
    # Build input
    ticker_in = {'symbol': symbol, 'close': close, 'macro_score': macro_score, 'holding': False}
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(ticker_in, f)
        tmp_path = f.name
    
    result = subprocess.run(
        ['python3', 'scripts/score.py', tmp_path, '--json'],
        capture_output=True, text=True, timeout=10
    )
    os.unlink(tmp_path)
    
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def print_table(rows: list[list[str]], headers: list[str]):
    """Print a simple aligned table."""
    col_widths = []
    for i, h in enumerate(headers):
        col_widths.append(max(len(h), max((len(r[i]) for r in rows), default=0)))
    
    sep = "  "
    header = sep.join(h.ljust(w) for h, w in zip(headers, col_widths))
    print(header)
    print("-" * len(header))
    for row in rows:
        print(sep.join(r.ljust(w) for r, w in zip(row, col_widths)))


def main():
    p = argparse.ArgumentParser(description="Opportunity screener for trading desk")
    p.add_argument("--refresh", action="store_true", help="Force-refresh market data")
    p.add_argument("--score", action="store_true", help="Score candidates")
    p.add_argument("--limit", type=int, default=6, help="Max candidates")
    p.add_argument("--tickers", type=str, help="Comma-separated tickers to score")
    p.add_argument("--sectors", type=str, default=None,
                    help="Comma-separated sector filter (e.g. Technology,Healthcare)")
    p.add_argument("--json", action="store_true", help="JSON output")
    args = p.parse_args()

    has_data = os.path.exists('/tmp/screener_data.json')

    # ---- Refresh data if needed ----
    if args.refresh or not has_data:
        if not refresh_market_data():
            print("[screener] Failed to refresh market data", file=sys.stderr)
            sys.exit(1)
    else:
        data_age = datetime.now().timestamp() - os.path.getmtime('/tmp/screener_data.json')
        if data_age > 3600:  # Older than 1 hour
            print(f"[screener] Data is {data_age/60:.0f}m old. Use --refresh to update.")
    
    # ---- Run macro pillar ----
    pillar = run_macro_pillar()
    if not pillar:
        print("[screener] Failed to run macro pillar", file=sys.stderr)
        sys.exit(1)
    
    bias = determine_bias(pillar)
    
    if args.json:
        result = {"macro": pillar, "bias": bias}
    
    # ---- Direct ticker scoring ----
    if args.tickers:
        symbols = [s.strip().upper() for s in args.tickers.split(",") if s.strip()]
        scored = []
        for sym in symbols:
            scorecard = score_ticker(sym, bias.get('score', 0))
            if scorecard:
                scored.append({"symbol": sym, "scorecard": scorecard})
        
        if args.json:
            result["scored"] = scored
            print(json.dumps(result, indent=2))
        elif scored:
            print(f"\n  Scored {len(scored)} tickers:\n")
            rows = []
            for s in scored:
                sc = s['scorecard']
                total = sc.get('pillar_total', 0)
                decision = sc.get('decision', {}).get('action', '?')
                price = sc.get('indicators', {}).get('close', 0)
                rows.append([s['symbol'], f"{total:+d}/6", f"${price}", decision])
            print_table(rows, ["Symbol", "Score", "Price", "Decision"])
        return

    # ---- Macro summary ----
    if not args.json:
        print(f"\nMacro Regime:     {bias['label']} (composite {bias.get('composite', 0):+.3f})")
        print(f"Macro Score:      {bias['score']:+d}/2")
        print(f"Tone:             {bias['tone']}")
        print(f"Favored sectors:  {', '.join(bias['favored'])}")
        if bias['avoid']:
            print(f"Avoid:            {', '.join(bias['avoid'])}")
        print()
    
    # ---- Component details ----
    if not args.json:
        print(f"  {'Component':35s} {'Signal':>7s} {'Detail'}")
        print(f"  {'-'*35} {'-'*7} {'-'*40}")
        for c in pillar.get('components', []):
            sig_str = f"{c['signal']:+d}" if c['signal'] is not None and isinstance(c['signal'], int) else f"{c['signal']:+.0f}" if c['signal'] is not None else " N/A"
            detail = (c.get('detail') or 'unavailable')[:50]
            print(f"  {c['name']:35s} {sig_str:>7s}  {detail}")
    
    # ---- Generate candidates ----
    candidates = []
    seen = set()
    
    # Determine which sectors to scan
    if args.sectors:
        scan_sectors = [s.strip() for s in args.sectors.split(",")]
    else:
        scan_sectors = bias['favored']
    
    for sector in scan_sectors:
        tickers = SECTOR_TICKERS.get(sector, [])
        for t in tickers:
            if t not in seen:
                candidates.append({"symbol": t, "sector": sector})
                seen.add(t)
    
    if not candidates:
        # Fallback
        for sector in list(SECTOR_TICKERS.keys())[:3]:
            for t in SECTOR_TICKERS[sector][:5]:
                if t not in seen:
                    candidates.append({"symbol": t, "sector": sector})
                    seen.add(t)
    
    if not args.json:
        print(f"\nTop {min(args.limit, len(candidates))} candidates from favored sectors:")
        for i, c in enumerate(candidates[:args.limit], 1):
            print(f"  {i}. {c['symbol']:6s} — {c['sector']}")
    
    if args.json:
        result["candidates"] = candidates[:args.limit]

    # ---- Score candidates ----
    if args.score:
        if not args.json:
            print(f"\nScoring candidates...\n")
        
        scored = []
        for c in candidates[:args.limit]:
            sym = c['symbol']
            if not args.json:
                print(f"  {sym:6s} ... ", end="", flush=True)
            scorecard = score_ticker(sym, bias.get('score', 0))
            if scorecard:
                c['scorecard'] = scorecard
                scored.append(c)
                if not args.json:
                    decision = scorecard.get('decision', {}).get('action', '?')
                    total = scorecard.get('pillar_total', 0)
                    print(f"score {total:+d}/6 → {decision}")
            else:
                if not args.json:
                    print("no data (skipped)")
        
        if args.json:
            result["scored"] = scored
            print(json.dumps(result, indent=2))
        elif scored:
            print(f"\n  {'Sym':6s} {'Score':>6s} {'Decision':28s} {'Sector':20s}")
            print(f"  {'-'*6} {'-'*6} {'-'*28} {'-'*20}")
            scored.sort(key=lambda c: c['scorecard'].get('pillar_total', -10), reverse=True)
            for c in scored:
                s = c['scorecard']
                total = s.get('pillar_total', 0)
                decision = s.get('decision', {}).get('action', '?')
                print(f"  {c['symbol']:6s} | {total:+3d}/6 | {decision:28s} | {c['sector']:20s}")
            
            best = scored[0]
            print(f"\nBest setup: {best['symbol']} ({best['sector']}) "
                  f"— {best['scorecard'].get('decision', {}).get('action', '?')}")
            print(f"  {best['scorecard'].get('decision', {}).get('framing', '')}")
    
    elif args.json:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
