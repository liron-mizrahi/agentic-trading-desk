# Agentic Trading Desk — Long-Term Memory

## Identity
- **Name:** Agentic Trading Desk
- **Creature:** Short-term Technical Trading Analyst
- **Vibe:** Systematic, disciplined, mathematical
- **Emoji:** 📈

## Infrastructure
- **Workspace:** ~/.openclaw/agentic-trading-desk-workspace
- **Scripts:** ~/.openclaw/agentic-trading-desk-workspace/scripts/
- **Python:** stdlib only for IBKR Web API scripts (ibkr_webapi.py, indicators.py, macro_pillar.py, score.py)
- **Data sources:** Interactive Brokers (REST API via Client Portal Gateway), U.S. Treasury.gov (yield curve CSV), Google Finance (analyst ratings)

## Repository
- **Source:** https://github.com/Oft3r/agentic-trading-desk
- **Status:** Converted from Claude Code SKILL pattern to OpenClaw agent on 2026-07-10

## IBKR Access
- **Client Portal Gateway:** Docker container on server03, port 5000 (REST API, https://localhost:5000)
- **Data script:** scripts/ibkr_webapi.py — stdlib-only REST client (no pip dependencies)
- **OAuth 2.0 with JWT** — no password stored on disk. Browser-based one-time login at https://localhost:5000

## Guardrails (Non-Negotiable)
1. **Read-only API** — agent can pull data but NEVER place orders. Orders are manual via IBKR app.
2. **IB Gateway on localhost only** — not network-exposed.
3. **Paper trading first** — mode=paper until verified.
4. **Macro source:** Investing.com only (no Polymarket — security risk).
5. **HTML visualization only on Fridays** — part of weekly review ritual.
6. **Explicit confirmation required** before any action.
7. **Full-stack testing mandatory** — every feature, fix, or change must be tested on BOTH backend and frontend before shipping. Backend: verify API responses, WebSocket, data endpoints. Frontend: verify page loads, JS hydration, buttons/links work, status LEDs. Never deploy without end-to-end verification.

## Discord Channels
- **#trading-desk** (1525113313128747028) — Command channel for conversation with this agent (no mentions required, requireMention: false)
- **#trading-signals** (1525113408658214923) — Published analysis, scorecards, and portfolio reports

## Important Decisions
- 2026-07-10: Created as an OpenClaw agent. Three-pillar framework ported from Claude Code.
- 2026-07-10: Switched from Robinhood to IBKR data (Liron not US-based). IB Gateway via Docker.

## Strategies Dashboard (2026-07-11)
- **Pipelines → Strategies** renamed throughout app (nav, URLs, page title)
- New `/strategies` page with Finviz-style scrollable data grid
- **⚠ When adding a new strategy, always update:**
  - `frontend/src/app/strategies/guide/page.tsx` — Strategy Guide documentation
  - `frontend/src/app/strategies/backtest/page.tsx` — Backtest strategy options
  - `SKILL.md` — This operations manual
- New `/strategies` page with Finviz-style scrollable data grid
- Columns ordered by funnel filter order, strategy-dependent (momentum_dip vs three_pillar)
- Click any row → expandable detail panel below table with step pass/fail gauges, LLM reasoning
- Fullscreen mode for deep indicator analysis
- Frozen ticker+sector columns with horizontal scroll like Finviz
- Color-coded cells: green=pass, red=fail, with threshold values inline
- LLM analysis persistence: reasoning, confidence bar, trade details all surfaced
- `/pipelines` → `/strategies` redirect (legacy link preserved in Strategies page)

## Automation Layer Built (2026-07-10)
### New Scripts
- **scripts/order_cache.py** — JSON-based order cache with state machine (draft→pending_confirm→confirmed→sanity_check_ok/fail→ready_for_execution)
- **scripts/eod_pipeline.py** — Full EOD orchestration: screener → metrics → cognitive review → order cache. Default sector focus: Technology. Supports --all-sectors, --dry-run, --json, --no-cache
- **scripts/premarket_check.py** — Checks confirmed orders against live IBKR quotes; flags gap > 2%. Threshold: 2%
- **scripts/generate_report.py** — Full HTML + PNG chart report for any ticker. Uses cairosvg for SVG→PNG conversion. Auto-runs after EOD for each actionable candidate.
- **scripts/momentum_dip_pipeline.py** — Momentum-Dip Catalyst Strategy (4-Step Filter Funnel). Uses RSI-2 with sector-adapted thresholds + CHOP index + SMA200 filter + QS Exit rule.

### Modified Scripts
- **scripts/screener.py** — Added --sectors flag for sector focus filter (e.g. Technology,Healthcare)
- **scripts/ibkr_webapi.py** — Historicals endpoint now returns high/low arrays alongside close (for CHOP computation)
- **scripts/indicators.py** — Added RSI-2 (rsi_wilder with period=2, already supported), Choppiness Index 14, SMA200, optional high/low params for compute()

### Updated SKILL.md
- Added Automation Layer section documenting EOD pipeline, pre-market check, order cache, and /confirm protocol

### Cron Jobs (both isolated agentTurn sessions)
- **eod-pipeline:** 21:00 UTC, Mon-Fri. Runs both strategies (three-pillar + momentum-dip). Generates report + PNG for each candidate. Posts to #trading-signals.
- **premarket-check:** 12:30 UTC, Mon-Fri. Validates confirmed orders against pre-market prices. Alerts on gap > 2%

### /confirm Protocol
- User types `/confirm ORD-xxx` → status changes from pending_confirm to confirmed
- User types `/executed ORD-xxx` → marks order as executed
- User types `/cancel ORD-xxx` → cancels order

### Two Trading Strategies
1. **Three-Pillar Framework** (eod_pipeline.py) — Trend/Momentum/Macro-Sentiment (-6 to +6). Rebound/reversal entry with capital rotation.
2. **Momentum-Dip Catalyst** (momentum_dip_pipeline.py) — RSI-2 mean reversion. SMA200 + CHOP filters. Sector-adapted thresholds. QS Exit (close > prev high). Size reduction by volatility.

## Backtesting Engine (2026-07-12)
- **scripts/backtester.py** — Time-Warp Backtesting Engine for all strategies (three_pillar, momentum_dip, squeeze). Chronological simulation with no lookahead bias. Supports --sectors filter, --json output, --benchmark comparison.
- **Backtest API:** `POST /api/backtest/run` via `trading-desk/backend/app/routers/backtest.py`. Triggers subprocess, persists results to PostgreSQL `backtest_results` table.
- **Frontend:** `/strategies/backtest` page with strategy selection, sector picker, date range, equity curve SVG charts, results table.
- **Docker:** Backend volume mount `../scripts:/scripts` so subprocess can find backtester.py at `/scripts/backtester.py`.

### Backtest Fixes Applied (2026-07-12)
- `indicators.py` `bollinger()` — now returns 5 values (was missing bandwidth, caused ValueError on unpack).
- `backtester.py` `--json` mode — all human-readable output routed to stderr so stdout is clean JSON.
- `backtest.py` router — `script_dir` uses `/scripts` path with fallback; DB queries rewritten to use SQLAlchemy `_get_async_sessionmaker()` (was calling `get_db()` async generator directly).

### Strategies Dashboard Fixes (2026-07-12)
- `pipelines.py` router — `/api/v1/pipelines/runs` now properly handles both momentum_dip and three_pillar strategies with correct SQL joins.
- Frontend builds and serves correctly (Dockerfile now runs `rm -rf /app/.next` before dev start to avoid stale chunks).
