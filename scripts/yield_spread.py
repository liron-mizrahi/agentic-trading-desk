#!/usr/bin/env python3
"""
yield_spread.py
================
Fetch 10Y-2Y Treasury yield spread from U.S. Treasury.gov (CSV).
No external dependencies — stdlib urllib only.

Usage:
  python3 scripts/yield_spread.py                    # latest spread only (human)
  python3 scripts/yield_spread.py --json             # JSON with latest spread
  python3 scripts/yield_spread.py --history 60       # last N daily spreads (JSON)
"""

import argparse
import csv
import io
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone


# Standard SSL verification — Treasury.gov has valid certs
_CTX = ssl.create_default_context()

# Cache dir for daily CSV to avoid repeated slow fetches
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".yield_cache")


def _cached_fetch(year_month: str) -> str:
    """Fetch with file cache (valid for one day)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"treasury_{year_month}.csv")
    
    # Use cache if from today
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    if os.path.exists(cache_path):
        # Check if cached today
        cache_mtime = datetime.fromtimestamp(os.path.getmtime(cache_path), tz=timezone.utc)
        if cache_mtime.strftime("%Y%m%d") == today:
            with open(cache_path) as f:
                return f.read()
    
    data = _fetch_monthly_csv(year_month)
    if data:
        with open(cache_path, "w") as f:
            f.write(data)
    return data


def _fetch_monthly_csv(year_month: str) -> str:
    """Fetch one month's Treasury yield curve CSV.
    
    year_month: "YYYYMM" format, e.g. "202607"
    """
    url = (
        "https://home.treasury.gov/resource-center/data-chart-center/"
        f"interest-rates/daily-treasury-rates.csv/all/{year_month}"
        f"?type=daily_treasury_yield_curve&field_tdr_date_value={year_month}"
    )
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, context=_CTX, timeout=15) as resp:
            return resp.read().decode("utf-8")
    except Exception:
        return ""


class YieldCurve:
    """Parse Treasury CSV and build yield spread time series."""

    def __init__(self):
        self.spreads: list[tuple[str, float, float, float]] = []

    def load(self, text: str):
        """Parse CSV text, appending rows (CSV is reverse-chronological).
        Deduplicates by date (keeps first occurrence = most recent)."""
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            date_str = row.get("Date", "").strip()
            y2_str = row.get("2 Yr", "").strip()
            y10_str = row.get("10 Yr", "").strip()
            if not date_str or not y2_str or not y10_str:
                continue
            try:
                y2 = float(y2_str)
                y10 = float(y10_str)
            except (ValueError, TypeError):
                continue
            self.spreads.append((date_str, y2, y10, round(y10 - y2, 3)))

    def get_latest(self):
        return self.spreads[0] if self.spreads else None

    def get_spread_series(self, n: int) -> list[float]:
        """Spread values oldest→newest for the macro_pillar."""
        vals = [s[3] for s in self.spreads[:n]]
        vals.reverse()
        return vals


def fetch_spread_history(n_days: int = 60) -> YieldCurve:
    """Fetch spread history across recent months (uses cache)."""
    curve = YieldCurve()
    now = datetime.now(timezone.utc)
    months_needed = max(3, n_days // 20 + 2)

    for offset in range(months_needed):
        y = now.year
        m = now.month - offset
        while m < 1:
            m += 12
            y -= 1
        ym = f"{y}{m:02d}"
        try:
            csv_text = _cached_fetch(ym)
            if csv_text:
                curve.load(csv_text)
                if len(curve.spreads) >= n_days:
                    break
        except Exception:
            pass

    return curve


def main():
    p = argparse.ArgumentParser(description="Fetch 10Y-2Y Treasury yield spread")
    p.add_argument("--json", action="store_true")
    p.add_argument("--history", type=int, default=0,
                   help="Historical spread count (0 = latest only)")
    args = p.parse_args()

    if args.history > 0:
        curve = fetch_spread_history(args.history)
    else:
        curve = fetch_spread_history(1)

    if args.json:
        if args.history > 0:
            spreads = curve.get_spread_series(args.history)
            latest = curve.get_latest()
            print(json.dumps({
                "latest_spread": latest[3] if latest else None,
                "yield_spread": spreads,
                "n_bars": len(spreads),
                "latest_raw": {
                    "date": latest[0], "2Y": latest[1], "10Y": latest[2]
                } if latest else None,
            }))
        else:
            latest = curve.get_latest()
            if latest:
                print(json.dumps({
                    "date": latest[0], "2Y": latest[1],
                    "10Y": latest[2], "spread": latest[3]
                }))
            else:
                print(json.dumps({"error": "no data"}))
    else:
        latest = curve.get_latest()
        if latest:
            date, y2, y10, sp = latest
            print(f"10Y-2Y Treasury Spread as of {date}:")
            print(f"  2-Year:  {y2}%")
            print(f"  10-Year: {y10}%")
            print(f"  Spread:  {sp:+.3f}%")
            if args.history > 0:
                vals = curve.get_spread_series(args.history)
                print(f"\n  Last {len(vals)} days: min={min(vals):.3f}% "
                      f"max={max(vals):.3f}% current={vals[-1]:.3f}%")
        else:
            print("No yield data fetched", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    raise SystemExit(main())
