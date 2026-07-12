#!/usr/bin/env python3
"""
generate_report.py
==================
Generates a detailed technical analysis report with embedded SVG chart
for a given ticker. Used by the EOD pipeline for actionable candidates.

Produces a self-contained HTML file with:
  - Price chart (SVG): price line, EMA20/50/200, Bollinger Bands, rebound markers
  - Indicator summary table
  - Pillar scorecard
  - Decision rationale with flags
  - Trade proposal (entry/stop/target)

Usage:
  python3 scripts/generate_report.py AMD > report_amd.html
  python3 scripts/generate_report.py AMD --price 554.14 --out /tmp/reports/
  python3 scripts/generate_report.py AMD --json > amd_analysis.json
"""

import argparse
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(SCRIPT_DIR)

# Chart dimensions
CHART_W = 700
CHART_H = 380
CHART_MARGIN = {"top": 30, "right": 40, "bottom": 40, "left": 60}


def _run(cmd: list, timeout: int = 30) -> tuple[bool, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=WORKSPACE)
        if result.returncode == 0:
            return True, result.stdout
        return False, result.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return False, str(e)


def fetch_full_analysis(ticker: str) -> dict | None:
    """Run the full analysis pipeline and return structured data."""
    ok, out = _run([sys.executable, "scripts/analyze.py", ticker, "--json"])
    if not ok:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def fetch_historicals(ticker: str) -> list[float] | None:
    """Fetch raw close prices for charting."""
    ok, out = _run([sys.executable, "scripts/ibkr_webapi.py", "historicals", ticker])
    if not ok:
        return None
    try:
        data = json.loads(out)
        close = data.get("close", [])
        return close[-200:] if len(close) > 200 else close  # last 200 bars
    except (json.JSONDecodeError, KeyError):
        return None


def compute_ema(values: list[float], period: int) -> list[float | None]:
    """Compute EMA series (same as indicators.py)."""
    n = len(values)
    out: list[float | None] = [None] * n
    if n < period:
        return out
    k = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def compute_bb(values: list[float], period: int = 20, mult: float = 2.0):
    """Bollinger Bands for each bar. Returns (mid, upper, lower) lists."""
    from statistics import pstdev
    n = len(values)
    mid: list[float | None] = [None] * n
    upper: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n
    for i in range(period - 1, n):
        window = values[i - period + 1:i + 1]
        m = sum(window) / period
        sd = pstdev(window)
        mid[i] = m
        upper[i] = m + mult * sd
        lower[i] = m - mult * sd
    return mid, upper, lower


def generate_svg_chart(ticker: str, close: list[float], analysis: dict) -> str:
    """Generate an SVG candlestick/line chart with EMAs and Bollinger Bands."""
    # Compute indicators for charting
    ema20 = compute_ema(close, 20)
    ema50 = compute_ema(close, 50)
    ema200 = compute_ema(close, 200)
    bb_mid, bb_up, bb_lo = compute_bb(close, 20, 2.0)

    i_data = analysis.get("indicators", {})
    decision = analysis.get("decision", {})
    flags = decision.get("flags", {})
    rebound_flags = flags.get("rebound", [])

    n = len(close)
    plot_n = min(120, n)  # Last 120 bars
    start = n - plot_n
    x_range = plot_n - 1

    # Price range with padding
    vals = [v for v in close[start:] if v]
    bb_up_vals = [v for v in bb_up[start:] if v is not None]
    bb_lo_vals = [v for v in bb_lo[start:] if v is not None]
    all_vals = vals + bb_up_vals + bb_lo_vals
    y_min = min(all_vals) * 0.995 if all_vals else min(vals) * 0.995
    y_max = max(all_vals) * 1.005 if all_vals else max(vals) * 1.005
    y_rng = y_max - y_min

    def x_pos(i: int) -> float:
        """Map bar index to canvas x."""
        return CHART_MARGIN["left"] + (i - start) / x_range * (CHART_W - CHART_MARGIN["left"] - CHART_MARGIN["right"])

    def y_pos(price: float) -> float:
        """Map price to canvas y."""
        return CHART_MARGIN["top"] + (1 - (price - y_min) / y_rng) * (CHART_H - CHART_MARGIN["top"] - CHART_MARGIN["bottom"])

    def path_from_series(series: list[float | None], skip_none: bool = False) -> str:
        """Build SVG path 'd' attribute from a list of values."""
        pts = []
        for i in range(start, n):
            v = series[i]
            if v is None:
                continue
            if not pts:
                pts.append(f"M{x_pos(i):.1f},{y_pos(v):.1f}")
            else:
                pts.append(f"L{x_pos(i):.1f},{y_pos(v):.1f}")
        return " ".join(pts)

    grid_color = "#e2e8f0"
    text_color = "#5b6475"
    axis_color = "#94a3b8"
    price_color = "#2563eb"
    ema20_color = "#f59e0b"
    ema50_color = "#10b981"
    ema200_color = "#ef4444"
    bb_fill = "rgba(37, 99, 235, 0.08)"
    rebound_color = "#22c55e"
    bg_color = "#ffffff"

    lines = []
    lines.append(f'<svg viewBox="0 0 {CHART_W} {CHART_H + 40}" xmlns="http://www.w3.org/2000/svg" style="font-family: ui-sans-serif, system-ui, sans-serif;">')
    lines.append(f'  <rect width="{CHART_W}" height="{CHART_H + 40}" fill="{bg_color}" rx="8"/>')

    # Grid lines (horizontal)
    n_grid = 5
    for gi in range(n_grid + 1):
        gy = CHART_MARGIN["top"] + gi / n_grid * (CHART_H - CHART_MARGIN["top"] - CHART_MARGIN["bottom"])
        price_label = y_max - gi / n_grid * y_rng
        lines.append(f'  <line x1="{CHART_MARGIN["left"]}" y1="{gy:.1f}" x2="{CHART_W - CHART_MARGIN["right"]}" y2="{gy:.1f}" stroke="{grid_color}" stroke-width="1"/>')
        lines.append(f'  <text x="{CHART_MARGIN["left"] - 8}" y="{gy + 4}" text-anchor="end" font-size="11" fill="{text_color}">${price_label:.2f}</text>')

    # Bollinger Bands fill
    bb_path = []
    for i in range(start, n):
        if bb_up[i] is None or bb_lo[i] is None:
            continue
        x = x_pos(i)
        if not bb_path:
            bb_path.append(f"M{x:.1f},{y_pos(bb_up[i]):.1f}")
        else:
            bb_path.append(f"L{x:.1f},{y_pos(bb_up[i]):.1f}")
    for i in range(n - 1, start - 1, -1):
        if bb_lo[i] is None:
            continue
        x = x_pos(i)
        bb_path.append(f"L{x:.1f},{y_pos(bb_lo[i]):.1f}")
    if len(bb_path) > 2:
        lines.append(f'  <path d="{" ".join(bb_path)}" fill="{bb_fill}" stroke="none"/>')

    # Bollinger lines
    lines.append(f'  <path d="{path_from_series(bb_up)}" stroke="{axis_color}" stroke-width="1" stroke-dasharray="4 3" fill="none"/>')
    lines.append(f'  <path d="{path_from_series(bb_mid)}" stroke="{axis_color}" stroke-width="1" stroke-dasharray="4 3" fill="none"/>')
    lines.append(f'  <path d="{path_from_series(bb_lo)}" stroke="{axis_color}" stroke-width="1" stroke-dasharray="4 3" fill="none"/>')

    # EMAs
    lines.append(f'  <path d="{path_from_series(ema20)}" stroke="{ema20_color}" stroke-width="1.5" fill="none"/>')
    lines.append(f'  <path d="{path_from_series(ema50)}" stroke="{ema50_color}" stroke-width="1.5" fill="none"/>')
    lines.append(f'  <path d="{path_from_series(ema200)}" stroke="{ema200_color}" stroke-width="1.5" fill="none"/>')

    # Price line
    lines.append(f'  <path d="{path_from_series(close)}" stroke="{price_color}" stroke-width="2" fill="none"/>')

    # Rebound markers (price reclaiming EMA20)
    if rebound_flags:
        max_x = 0
        max_y = 0
        found_marker = False
        for rb_flag in rebound_flags:
            if "price reclaims EMA20" in rb_flag:
                # Find the bar where price crossed above EMA20
                for i in range(start + 1, n):
                    if (ema20[i] is not None and close[i] > ema20[i] and
                        ema20[i - 1] is not None and close[i - 1] < ema20[i - 1]):
                        mx = x_pos(i)
                        my = y_pos(close[i])
                        lines.append(f'  <circle cx="{mx:.1f}" cy="{my:.1f}" r="6" fill="none" stroke="{rebound_color}" stroke-width="2"/>')
                        lines.append(f'  <circle cx="{mx:.1f}" cy="{my:.1f}" r="3" fill="{rebound_color}"/>')
                        lines.append(f'  <text x="{mx + 10}" y="{my + 4}" font-size="11" fill="{rebound_color}" font-weight="600">Rebound ✓</text>')
                        max_x, max_y, found_marker = mx, my, True
                        break
            elif "RSI turning from oversold" in rb_flag:
                for i in range(start + 1, n):
                    lines.append(f'  <circle cx="{x_pos(i)}" cy="{y_pos(close[i])}" r="5" fill="none" stroke="#8b5cf6" stroke-width="1.5" stroke-dasharray="3 2"/>')
                    lines.append(f'  <text x="{x_pos(i) + 8}" y="{y_pos(close[i]) + 4}" font-size="10" fill="#8b5cf6">RSI turn</text>')
                    break
            elif "MACD histogram crossing bullishly" in rb_flag:
                for i in range(start + 1, n):
                    pass  # marker already placed above

    # Latest price label
    last_x = x_pos(n - 1)
    last_y = y_pos(close[-1])
    lines.append(f'  <circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="4" fill="{price_color}"/>')
    lines.append(f'  <text x="{last_x + 8}" y="{last_y + 4}" font-size="12" fill="{price_color}" font-weight="700">${close[-1]:.2f}</text>')

    # Legend
    ly = CHART_H + 4
    leg_items = [
        (price_color, "Price"),
        (ema20_color, "EMA20"),
        (ema50_color, "EMA50"),
        (ema200_color, "EMA200"),
        (axis_color, "Bollinger"),
    ]
    lx = CHART_MARGIN["left"]
    for color, label in leg_items:
        lines.append(f'  <line x1="{lx}" y1="{ly}" x2="{lx + 18}" y2="{ly}" stroke="{color}" stroke-width="2"/>')
        lines.append(f'  <text x="{lx + 22}" y="{ly + 4}" font-size="10" fill="{text_color}">{label}</text>')
        lx += 70

    lines.append('</svg>')
    return "\n".join(lines)


def generate_report(ticker: str, analysis: dict, close_series: list[float] | None = None) -> str:
    """Generate a complete HTML report."""
    i = analysis.get("indicators", {})
    d = analysis.get("decision", {})
    f = d.get("flags", {})
    p = analysis.get("pillars", {})
    prin = analysis.get("price", {})

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Fetch close series for chart if not provided
    if close_series is None:
        close_series = fetch_historicals(ticker)
    if close_series is None:
        close_series = []

    svg_chart = generate_svg_chart(ticker, close_series, analysis) if len(close_series) > 50 else "<p>Insufficient data for chart</p>"

    # Decision color
    action = d.get("action", "?")
    if "ENTER" in action or "RE-ENTRY" in action:
        action_color = "#22c55e"
        action_bg = "#f0fdf4"
    elif "EXIT" in action or "TRIM" in action:
        action_color = "#ef4444"
        action_bg = "#fef2f2"
    elif "HOLD" in action:
        action_color = "#f59e0b"
        action_bg = "#fffbeb"
    else:
        action_color = "#64748b"
        action_bg = "#f8fafc"

    total = analysis.get("pillar_total", 0)
    total_color = "#22c55e" if total > 0 else "#ef4444" if total < 0 else "#64748b"

    # Extract pillar values to avoid f-string nesting issues
    t_score = p.get('trend',{}).get('score',0)
    m_score = p.get('momentum',{}).get('score',0)
    mac_score = p.get('macro_sentiment',{}).get('score')
    if mac_score is not None:
        mac_score_str = f"{mac_score:+d}"
    else:
        mac_score_str = "?"
    t_detail = p.get('trend',{}).get('detail','')
    m_detail = p.get('momentum',{}).get('detail','')
    
    # Indicator values
    close_price = i.get('close',0) or 0
    ema20 = i.get('ema20',0) or 0
    ema50 = i.get('ema50',0) or 0
    ema200 = i.get('ema200',0) or 0
    rsi14 = i.get('rsi14',0) or 0
    macd_hist = i.get('macd_hist',0) or 0
    trix = i.get('trix',0) or 0
    trix_sig = i.get('trix_signal',0) or 0
    pct_b = i.get('percent_b',0) or 0
    bars_below = i.get('bars_since_below_ema20')

    # Format flags
    flag_html = ""
    for flag in f.get("exhaustion", []):
        flag_html += f'        <tr><td class="flag-exhaustion">⚠ Exhaustion</td><td>{flag}</td></tr>\n'
    for flag in f.get("bearish", []):
        flag_html += f'        <tr><td class="flag-bearish">🔴 Bearish</td><td>{flag}</td></tr>\n'
    for flag in f.get("rebound", []):
        flag_html += f'        <tr><td class="flag-rebound">🟢 Rebound</td><td>{flag}</td></tr>\n'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{ticker} — Technical Analysis Report</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{
    margin: 0; background: #f8fafc; color: #172033;
    font: 14px/1.5 ui-sans-serif, system-ui, sans-serif;
  }}
  .report {{
    max-width: 800px; margin: 24px auto; padding: 0 16px;
  }}
  .card {{
    background: #fff; border-radius: 10px; padding: 20px 24px;
    margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }}
  .card h2 {{
    margin: 0 0 12px 0; font-size: 16px; font-weight: 650; color: #172033;
    border-bottom: 2px solid #e2e8f0; padding-bottom: 8px;
  }}
  .header {{
    display: flex; justify-content: space-between; align-items: center;
  }}
  .header h1 {{ margin: 0; font-size: 24px; }}
  .header .score {{ font-size: 28px; font-weight: 700; }}
  .action-badge {{
    display: inline-block; padding: 6px 16px; border-radius: 20px;
    font-weight: 700; font-size: 14px; background: {action_bg}; color: {action_color};
  }}
  .pillar-grid {{
    display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; margin: 8px 0;
  }}
  .pillar-box {{
    border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; text-align: center;
  }}
  .pillar-box .pillar-score {{ font-size: 24px; font-weight: 700; }}
  .pillar-box .pillar-name {{ font-size: 12px; color: #5b6475; margin-top: 4px; }}
  .pillar-box .pillar-detail {{ font-size: 11px; color: #94a3b8; margin-top: 4px; }}
  table {{
    width: 100%; border-collapse: collapse; margin: 8px 0;
  }}
  th, td {{
    text-align: left; padding: 6px 8px; border-bottom: 1px solid #f1f5f9;
    font-size: 13px;
  }}
  th {{ font-weight: 600; color: #5b6475; width: 120px; }}
  .positive {{ color: #16a34a; }}
  .negative {{ color: #dc2626; }}
  .neutral {{ color: #64748b; }}
  .flag-exhaustion {{ color: #d97706; font-weight: 600; }}
  .flag-bearish {{ color: #dc2626; font-weight: 600; }}
  .flag-rebound {{ color: #16a34a; font-weight: 600; }}
  .framing {{ font-size: 13px; color: #334155; line-height: 1.6; padding: 8px; background: #f8fafc; border-radius: 6px; }}
  .proposal {{ margin-top: 12px; }}
  .proposal-item {{
    display: inline-block; margin: 4px 8px 4px 0; padding: 6px 14px;
    border-radius: 6px; font-weight: 600; font-size: 13px;
  }}
  .proposal-entry {{ background: #dbeafe; color: #1d4ed8; }}
  .proposal-stop {{ background: #fee2e2; color: #dc2626; }}
  .proposal-target {{ background: #dcfce7; color: #16a34a; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #0f172a; color: #e5e7eb; }}
    .card {{ background: #1e293b; }}
    .card h2 {{ border-color: #334155; color: #e5e7eb; }}
    .pillar-box {{ border-color: #334155; }}
    th {{ color: #94a3b8; }}
    .framing {{ background: #0f172a; color: #cbd5e1; }}
    .proposal-entry {{ background: #1e3a5f; color: #93c5fd; }}
    .proposal-stop {{ background: #3b1f1f; color: #fca5a5; }}
    .proposal-target {{ background: #1a3b2a; color: #86efac; }}
  }}
</style>
</head>
<body>
<div class="report">
  <!-- Header -->
  <div class="card">
    <div class="header">
      <div>
        <h1>{ticker}</h1>
        <div style="font-size:13px;color:#5b6475;">Analysis · {now}</div>
      </div>
      <div style="text-align:right;">
        <div class="score" style="color:{total_color};">{total:+d}/6</div>
        <div class="action-badge">{action}</div>
      </div>
    </div>
    <div style="margin-top:12px;font-size:13px;color:#5b6475;">
      <b>Last:</b> ${close_price:.2f}
      &nbsp;·&nbsp; <b>Macro:</b> {p.get('macro_sentiment',{}).get('score','?')}
      &nbsp;·&nbsp; <b>Bars:</b> {analysis.get('n_bars','?')}
    </div>
  </div>

  <!-- Price Chart -->
  <div class="card">
    <h2>📈 Price &amp; Indicators</h2>
    {svg_chart}
  </div>

  <!-- Three Pillars -->
  <div class="card">
    <h2>📊 Three-Pillar Scorecard</h2>
    <div class="pillar-grid">
      <div class="pillar-box">
        <div class="pillar-score" style="color:{'#16a34a' if t_score > 0 else '#dc2626' if t_score < 0 else '#64748b'}">
          {t_score:+d}
        </div>
        <div class="pillar-name">📈 Trend</div>
        <div class="pillar-detail">{t_detail}</div>
      </div>
      <div class="pillar-box">
        <div class="pillar-score" style="color:{'#16a34a' if m_score > 0 else '#dc2626' if m_score < 0 else '#64748b'}">
          {m_score:+d}
        </div>
        <div class="pillar-name">⚡ Momentum</div>
        <div class="pillar-detail">{m_detail}</div>
      </div>
      <div class="pillar-box">
        <div class="pillar-score" style="color:{'#16a34a' if (mac_score or 0) > 0 else '#dc2626' if (mac_score or 0) < 0 else '#64748b'}">
          {mac_score_str}
        </div>
        <div class="pillar-name">🌐 Macro</div>
        <div class="pillar-detail">cross-asset regime</div>
      </div>
    </div>
    <div style="text-align:center;margin-top:8px;">
      <b>Composite:</b> <span style="font-size:18px;font-weight:700;color:{total_color};">{total:+d}/6</span>
    </div>
  </div>

  <!-- Indicator Values -->
  <div class="card">
    <h2>🔬 Key Indicators</h2>
    <table>
      <tr><th>EMA20</th><td>${ema20:.2f}</td><td class="{'positive' if ema20 < close_price else 'negative'}">{'Above' if ema20 < close_price else 'Below'}</td></tr>
      <tr><th>EMA50</th><td>${ema50:.2f}</td><td class="{'positive' if ema50 < close_price else 'negative'}">{'Above' if ema50 < close_price else 'Below'}</td></tr>
      <tr><th>EMA200</th><td>${ema200:.2f}</td><td class="{'positive' if ema200 < close_price else 'negative'}">{'Above' if ema200 < close_price else 'Below'}</td></tr>
      <tr><th>RSI-14</th><td>{rsi14:.1f}</td><td class="{'positive' if rsi14 > 50 else 'negative'}">{'Bullish (>50)' if rsi14 > 50 else 'Bearish (<50)'}</td></tr>
      <tr><th>MACD Hist</th><td>{macd_hist:+.3f}</td><td class="{'positive' if macd_hist > 0 else 'negative'}">{'Positive' if macd_hist > 0 else 'Negative'}</td></tr>
      <tr><th>TRIX</th><td>{trix:+.4f}</td><td>{'Above signal' if trix > trix_sig else 'Below signal'}</td></tr>
      <tr><th>%B (Bollinger)</th><td>{pct_b:.3f}</td><td>{'Upper band zone' if pct_b > 0.8 else 'Lower band zone' if pct_b < 0.2 else 'Middle zone'}</td></tr>
      <tr><th>Bars below EMA20</th><td>{bars_below if bars_below is not None else 'N/A'}</td><td>{'Recent pullback' if (bars_below or 999) <= 20 else 'Stable above'}</td></tr>
    </table>
  </div>

  <!-- Decision & Flags -->
  <div class="card">
    <h2>🎯 Decision</h2>
    <div class="action-badge" style="font-size:16px;padding:8px 20px;margin-bottom:12px;">{action}</div>
    <div style="font-weight:600;margin-bottom:8px;">{d.get('rationale','')}</div>
    <div class="framing">{d.get('framing','')}</div>
  </div>

  <!-- Flags Table -->
  <div class="card">
    <h2>🚩 Signal Flags</h2>
    <table>
      {flag_html if flag_html else '      <tr><td colspan="2" style="text-align:center;color:#94a3b8;">No significant flags</td></tr>'}
    </table>
  </div>

  <!-- Trade Proposal -->
  <div class="card">
    <h2>📋 Trade Proposal</h2>
    <table>
      <tr><th>Direction</th><td>{'LONG' if 'ENTER' in action or 'RE-ENTRY' in action else 'SHORT' if 'EXIT' in action else 'NONE'}</td></tr>
      <tr><th>Entry Zone</th><td>${close_price:.2f} (current price)</td></tr>
      <tr><th>Stop Loss</th><td style="color:#dc2626;">${close_price * 0.93:.2f} (-7%)</td></tr>
      <tr><th>Take Profit</th><td style="color:#16a34a;">${close_price * 1.08:.2f} (+8%)</td></tr>
      <tr><th>Risk/Reward</th><td>~1:1.1</td></tr>
      <tr><th>Conviction</th><td>{'HIGH' if abs(total) >= 4 else 'MEDIUM' if abs(total) >= 2 else 'LOW'}</td></tr>
    </table>
  </div>

</div>
</body>
</html>"""
    return html


def main():
    p = argparse.ArgumentParser(description="Generate technical analysis report for a ticker")
    p.add_argument("ticker", help="Ticker symbol")
    p.add_argument("--out", type=str, default="/tmp/reports",
                    help="Output directory (default: /tmp/reports)")
    p.add_argument("--price", type=float, default=None,
                    help="Override close price")
    p.add_argument("--json", action="store_true",
                    help="Output raw analysis JSON instead of HTML report")
    args = p.parse_args()

    ticker = args.ticker.upper()

    # Fetch full analysis
    analysis = fetch_full_analysis(ticker)
    if analysis is None:
        print(f"❌ Failed to analyze {ticker}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(analysis, indent=2))
        return

    # Override price if provided
    if args.price is not None and "price" in analysis:
        analysis["price"]["last"] = args.price

    # Fetch historical data for chart
    close_series = fetch_historicals(ticker)

    # Generate report
    report = generate_report(ticker, analysis, close_series)

    # Output
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)
    safe_ticker = ticker.lower().replace(".", "_")
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(out_dir, f"{safe_ticker}_report_{now}.html")

    with open(out_path, "w") as f:
        f.write(report)

    # Also generate PNG of the chart
    png_path = out_path.replace(".html", ".png")
    try:
        import cairosvg
        svg_start = report.find('<svg')
        svg_end = report.find('</svg>', svg_start) + 6
        svg_chart = report[svg_start:svg_end]
        cairosvg.svg2png(bytestring=svg_chart.encode(), write_to=png_path, scale=2)
        print(f"\n✅ Chart PNG saved: {png_path}", file=sys.stderr)
    except ImportError:
        print(f"  ⚠ cairosvg not available, skipping PNG generation", file=sys.stderr)
    except Exception as e:
        print(f"  ⚠ PNG generation failed: {e}", file=sys.stderr)

    # Also print to stdout
    print(report)

    print(f"\n✅ Report saved: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
