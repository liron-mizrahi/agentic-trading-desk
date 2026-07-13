# Agentic Trading Desk 📈

**Systematic short-term trading engine** — a Python + Next.js platform that combines technical analysis, macro regime detection, and LLM-powered cognitive review to generate actionable trade proposals.

Built on a **Three-Pillar Framework** (Trend / Momentum / Macro-Sentiment) and a **Momentum-Dip Catalyst Strategy** (RSI-2 mean reversion with sector-adapted thresholds).

## ✨ Features

- **Three-Pillar Scoring Engine** — Trend (EMA 20/50/200), Momentum (RSI-14, MACD, TRIX-15), Macro-Sentiment (cross-asset ETF regime + yield curve). Each pillar scored -2 to +2, total -6 to +6.
- **Momentum-Dip Catalyst** — RSI-2 oversold detection with sector-adapted thresholds, CHOP filter, SMA200 trend confirmation, and QS Exit rule.
- **Deterministic Computation** — All indicators computed via Python stdlib (no TA-Lib or external dependencies for the core engine). No eyeballing charts.
- **Daily EOD Pipeline** — Automated screener → scoring → cognitive review → order caching. Runs at 21:00 UTC on trading days.
- **Pre-Market Sanity Check** — Validates confirmed orders against live quotes at 12:30 UTC. Flags >2% gaps.
- **Stateful Order Cache** — JSON-based order lifecycle with `/confirm`, `/cancel`, `/executed` protocol.
- **Web Dashboard** — Next.js frontend with real-time WebSocket updates, trade proposals, strategy results, and pipeline history.
- **FastAPI Backend** — REST API + WebSocket event streaming + Celery task queue for heavy analysis.
- **IBKR Integration** — Client Portal Gateway REST API for price data, positions, and portfolio. Read-only by design.
- **OpenClaw Agent** — LLM cognitive review with persona chain (analyst → risk manager → portfolio manager).

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      OpenClaw Agent                         │
│  Cognitive Review · Persona Chain · Order Caching           │
│  Cron Jobs (EOD Pipeline + Pre-Market Check)                │
└────────────┬────────────────────────────────────────────────┘
             │
    ┌────────┴────────┐
    │                 │
    ▼                 ▼
┌─────────┐    ┌──────────────┐    ┌───────────┐    ┌──────────┐
│  IBKR   │◄──►│   Backend    │◄──►│  Postgres │    │  Redis   │
│ Gateway │    │  (FastAPI)   │    │    DB     │    │ (Celery) │
└─────────┘    └──────┬───────┘    └───────────┘    └──────────┘
                      │
                      ▼
              ┌──────────────┐
              │   Frontend   │
              │  (Next.js)   │
              └──────────────┘
```

### Stack

| Layer | Technology |
|-------|-----------|
| **Core Engine** | Python 3 (stdlib indicators, no TA-Lib dependency) |
| **Data Source** | Interactive Brokers Client Portal Gateway (REST API) |
| **Backend** | FastAPI + SQLAlchemy + Celery |
| **Database** | PostgreSQL 15 + Redis |
| **Frontend** | Next.js 14 + TypeScript + Tailwind CSS + Lightweight Charts |
| **State Management** | Zustand |
| **Agent Runtime** | OpenClaw (LLM orchestration) |
| **Infrastructure** | Docker Compose |

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.9+ (for running scripts outside Docker)
- Interactive Brokers account with Client Portal Gateway access
- (Optional) Node.js 18+ for frontend development

### 1. Clone & Configure

```bash
git clone https://github.com/Oft3r/agentic-trading-desk.git
cd agentic-trading-desk

# Set up environment
cp trading-desk/.env.example trading-desk/.env
# Edit trading-desk/.env with your DeepSeek API key and DB password
```

### 2. Set Up IBKR Gateway

```bash
# Interactive — installs Java, downloads Gateway, creates systemd service
bash setup_server03.sh

# After initial setup, authenticate once via browser:
ssh -L 5000:localhost:5000 user@your-server
# Open https://localhost:5000 in browser, log in with IBKR credentials
```

### 3. Start the Platform

```bash
cd trading-desk
docker compose up -d
```

The dashboard will be available at `http://localhost:3000`.

### 4. Run Analysis

```bash
# Three-Pillar scoring for a single ticker
python3 scripts/ibkr_webapi.py historicals AAPL > /tmp/aapl.json
python3 -c "
import json
d = json.load(open('/tmp/aapl.json'))
json.dump({'symbol':'AAPL','close':d['close'],'macro_score':0,'holding':False}, open('/tmp/input.json','w'))
"
python3 scripts/score.py /tmp/input.json

# Full EOD pipeline (screener → scoring → proposals)
python3 scripts/eod_pipeline.py --sectors Technology

# Momentum-Dip strategy
python3 scripts/momentum_dip_pipeline.py --dry-run

# Pre-market check
python3 scripts/premarket_check.py --dry-run
```

## 📊 The Three-Pillar Framework

| Pillar | Range | Inputs |
|--------|-------|--------|
| **Trend** | -2..+2 | EMA20/50/200 structure, price vs. EMAs, EMA200 slope |
| **Momentum** | -2..+2 | RSI-14 (Wilder), MACD histogram, TRIX-15 vs signal |
| **Macro-Sentiment** | -2..+2 | Cross-asset ETF regime (SPY, RSP, IWM, HYG, LQD, TLT, XLY, XLP) + 10Y-2Y yield spread |

**Total: -6 to +6**

### Decision Cascade

| Action | Context |
|--------|---------|
| **EXIT / TRIM** | Holding — bullish momentum exhausted |
| **EXIT** | Holding — bearish momentum relentless |
| **RE-ENTRY** | Flat — rebound with healthy EMA structure |
| **TACTICAL REBOUND** | Flat — rebound inside a death-cross (reduced size) |
| **HOLD** | Holding — trend and momentum positive |
| **WAIT** | Flat — healthy trend but no trigger |
| **STAY OUT** | Flat — no signs of turning |

## 📋 Order Lifecycle

```
draft → pending_confirm → confirmed → sanity_check_ok → ready_for_execution
                                        │
                                        └── sanity_check_fail (gap > 2%)
```

- `/confirm ORD-xxx` — approve a pending order
- `/cancel ORD-xxx` — cancel an order
- `/executed ORD-xxx` — mark as executed

## 🛡 Guardrails

1. **Read-only API** — agent pulls data but never places orders. Execution is manual via IBKR TWS.
2. **Two accounts, two roles** — Agentic (cash, short-term) vs. Individual (margin, buy-and-hold).
3. **T+1 settling** — only settled cash counts as buying power in the cash account.
4. **Protected positions** — certain tickers (stock grants) are never analyzed for exit.
5. **Explicit confirmation required** — no order proceeds without `/confirm`.
6. **Macro data from Investing.com only** — no Polymarket (prompt injection risk).

## 📁 Project Structure

```
├── scripts/                    # Python analysis engine
│   ├── indicators.py           # EMA, RSI, MACD, TRIX, Bollinger, CHOP
│   ├── score.py                # Three-pillar scoring + decision logic
│   ├── macro_pillar.py         # Cross-asset regime detection
│   ├── screener.py             # Sector-based opportunity screening
│   ├── eod_pipeline.py         # Full EOD orchestration
│   ├── momentum_dip_pipeline.py # RSI-2 oversold strategy
│   ├── premarket_check.py      # Pre-market gap validation
│   ├── order_cache.py          # JSON-based order state machine
│   ├── ibkr_webapi.py          # IBKR REST API client (stdlib)
│   ├── yield_spread.py         # 10Y-2Y from Treasury.gov
│   ├── analyze.py              # Per-ticker analysis pipeline
│   └── generate_report.py      # HTML + PNG chart reports
├── trading-desk/               # Web platform (Docker Compose)
│   ├── frontend/               # Next.js dashboard
│   ├── backend/                # FastAPI + Celery
│   ├── agent/                  # Celery workers + LLM tasks
│   ├── db/                     # PostgreSQL init scripts
│   └── docker-compose.yml      # Full stack orchestration
├── personas/                   # LLM persona definitions
│   ├── analyst.md
│   ├── portfolio_manager.md
│   └── risk_manager.md
├── setup_server03.sh           # IBKR Gateway setup script
├── SKILL.md                    # OpenClaw agent operations manual
├── MEMORY.md                   # Agent long-term memory / decisions log
├── AGENTS.md                   # Agent workspace configuration
└── SOUL.md                     # Agent personality / methodology
```

## 🔧 Scripts Reference

| Script | Purpose |
|--------|---------|
| `indicators.py` | Compute EMA, RSI, MACD, TRIX, Bollinger Bands, Choppiness Index |
| `score.py` | Three-pillar scoring + exhaustion/rebound decision engine |
| `macro_pillar.py` | Cross-asset regime classification from 7 ETFs + yield curve |
| `screener.py` | Sector-focused opportunity screening with macro bias |
| `eod_pipeline.py` | Full EOD: screen → score → review → cache orders |
| `momentum_dip_pipeline.py` | RSI-2 oversold strategy with sector-adapted thresholds |
| `premarket_check.py` | Validate confirmed orders vs. live pre-market prices |
| `order_cache.py` | JSON-based order state machine (draft → confirmed → executed) |
| `ibkr_webapi.py` | IBKR Client Portal REST client (stdlib only, no pip) |
| `yield_spread.py` | Fetch 10Y-2Y yield spread from U.S. Treasury.gov |
| `analyze.py` | Wrapper that runs full analysis pipeline for one ticker |
| `generate_report.py` | HTML + PNG chart report generation |
| `backtester.py` | Time-Warp backtesting engine (three_pillar, momentum_dip, squeeze, all) |
| `dual_momentum_pipeline.py` | Dual Momentum strategy with relative strength ranking |
| `squeeze_pipeline.py` | Bollinger Squeeze Breakout strategy |
| `pead_pipeline.py` | Post-Earnings Announcement Drift strategy |
| `news_sentiment.py` | News sentiment analysis via Finnhub |
| `finny_imports.py` | Finnhub API client utilities for news and fundamentals |

## ⚙️ Cron Jobs

Two automated cron jobs run via OpenClaw on trading days:

| Job | Schedule (UTC) | Purpose |
|-----|---------------|---------|
| **EOD Pipeline** | 21:00 Mon-Fri | Full screener → scoring → cognitive review → order cache |
| **Pre-Market Check** | 12:30 Mon-Fri | Validate confirmed orders against pre-market prices |

## 📄 License

MIT © 2026 Liron Mizrahi

## ⚠️ Disclaimer

This software is for **educational and research purposes only**. It is not financial advice. Trading involves risk. Past performance does not guarantee future results. The authors assume no responsibility for trading losses. Always do your own research before making investment decisions.
