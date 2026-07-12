---
name: agentic-trading-desk
description: >-
  Short-term technical trading desk for stocks/ETFs using the three-pillar
  framework (Trend/Momentum/Macro-Sentiment). Uses IBKR Web API for
  price data (REST, stdlib), Python scripts for deterministic calculations, and
  web_fetch for macro/analyst context. Automated daily EOD pipeline +
  pre-market sanity check via cron. Order cache with /confirm gateway.
---

# Agentic Trading Desk — Operations Manual

## How Data Flow Works

```
Client Portal Gateway (Docker)  ──→  ibkr_webapi.py (REST, stdlib)  ──→  Python scripts
         ↓                                                                    ↓
Investing.com (web_fetch)  ──→  macro_pillar.py                           Scorecard + Decision
         ↓
Google Finance (web_fetch)  ──  Qualitative context (does NOT alter scores)
```

**Data access (IBKR Web API):** REST API via Client Portal Gateway — no password stored on disk.
Uses OAuth 2.0 with JWT. Stdlib only (no pip install needed).

```bash
cd /home/liron/.openclaw/agentic-trading-desk-workspace
python3 scripts/ibkr_webapi.py historicals AAPL        # Price data for indicator computation
python3 scripts/ibkr_webapi.py macro-etfs               # All 8 macro ETFs in one call
python3 scripts/ibkr_webapi.py quote AAPL               # Live quote
python3 scripts/ibkr_webapi.py positions                # Current holdings
python3 scripts/ibkr_webapi.py portfolio                # Account summary
python3 scripts/yield_spread.py                         # 10Y-2Y yield spread from Treasury.gov
python3 scripts/yield_spread.py --history 60 --json     # Historical spread series for macro pillar
```

**Deterministic computation:** Python scripts in `scripts/` — pure stdlib, no network needed.

**Gateway requirement:** Docker container must be running.
Check: `python3 scripts/ibkr_webapi.py auth-check`

---

## Guardrails — Non-Negotiable

1. **Protected positions:** Certain tickers are restricted (e.g., stock grants). NEVER analyze them for exit/sell. Only mention as exposure context.
2. **Two accounts, two roles:**
   - **Agentic** (cash account) → short-term trading. You have execution permissions (with explicit confirmation).
   - **Individual** (margin account) → core buy-and-hold. Only analyze holding quality, no active trading.
3. **T+1 liquidity:** Only SETTLED cash counts as buying power in the cash account.
4. **HTML visualization only on Fridays** as part of weekly review. Not other days unless explicitly asked.
5. **Macro source:** Investing.com ONLY (no Polymarket — security risk).
6. **Explicit confirmation required** before any order. Always simulate via order preview first.
7. **Never calculate indicators by reasoning over price bars.** Always use the Python scripts.

---

## IBKR Data Access

IB Gateway must be running. Check first:
```bash
python3 scripts/ibkr_data.py auth-check
```

Expected: `{"status": "connected", "accounts": ["U1234567"]}`

### Fetch Historical Prices (Input for Python Scripts)
```bash
cd /home/liron/.openclaw/agentic-trading-desk-workspace
python3 scripts/ibkr_data.py historicals AAPL > /tmp/aapl_data.json
```
The JSON output has `{symbol, close: [...], n_bars}` — ready to pipe into score.py.

### Fetch Macro ETFs
```bash
python3 scripts/ibkr_webapi.py macro-etfs > /tmp/macro_data.json
```
Returns `{series: {SPY: [...], RSP: [...], ...}}` — feed directly into macro_pillar.py.

### Live Quote
```bash
python3 scripts/ibkr_data.py quote AAPL
```

### Positions & Portfolio
```bash
python3 scripts/ibkr_data.py positions
python3 scripts/ibkr_data.py portfolio
```

---

## Computation Flow

### Step 1 — Macro Pillar (once per session)
Assemble JSON with close prices for 8 ETFs (SPY, RSP, IWM, HYG, LQD, TLT, XLY, XLP) + 10Y-2Y yield spread.

Fetch yield spread from U.S. Treasury.gov (no Cloudflare issues):
```bash
cd /home/liron/.openclaw/agentic-trading-desk-workspace
python3 scripts/yield_spread.py --history 60 --json
```
This outputs `{"yield_spread": [...], "latest_spread": 0.38}`.
Inject the `yield_spread` array into the macro data JSON before running `macro_pillar.py`.

The Treasury CSV endpoint is reliable and doesn't require a browser.

If yield spread data is unavailable (e.g., API timeouts), the macro pillar redistributes
its 20% weight among other components automatically.

```bash
cd /home/liron/.openclaw/agentic-trading-desk-workspace
python3 scripts/macro_pillar.py macro_input.json --json
```

Save the `pillar_score` (-2..+2). Use it as the Macro-Sentiment score for ALL tickers this session.

### Step 2 — Per Ticker Scoring
Assemble JSON:
```json
{
  "symbol": "AAPL",
  "close": [220.5, 222.1, ...],
  "macro_score": 1,
  "holding": true
}
```

Run:
```bash
cd /home/liron/.openclaw/agentic-trading-desk-workspace
python3 scripts/score.py ticker_input.json        # human-readable
python3 scripts/score.py ticker_input.json --json  # machine-readable
```

### Step 3 — Qualitative Context (web_fetch)
Fetch analyst ratings from Google Finance:
```
https://www.google.com/finance/quote/AAPL:NASDAQ?tab=analysis
```
Extract: consensus (Buy/Hold/Sell), 12m price targets, recent rating changes.

Fetch macro news from Investing.com as needed.

---

## Three-Pillar Framework

Each pillar -2 to +2:

| Pillar | Range | Inputs |
|--------|-------|--------|
| **Trend** | -2..+2 | EMA20/50/200 structure, price vs. EMAs, slope of EMA200 |
| **Momentum** | -2..+2 | Wilder's RSI-14, MACD histogram, TRIX-15 vs signal |
| **Macro-Sentiment** | -2..+2 | Cross-asset regime from macro_pillar.py |

**Total: -6 to +6**

### Decisions

| Decision | Context |
|----------|---------|
| **EXIT / TRIM** | Holding — bullish momentum exhausted |
| **EXIT** | Holding — bearish momentum relentless |
| **RE-ENTRY (new cycle)** | Flat — rebound with healthy EMA structure |
| **TACTICAL REBOUND** | Flat — rebound inside a death-cross (reduced size) |
| **HOLD (ride the cycle)** | Holding — trend and momentum positive |
| **WAIT (do not chase)** | Flat — healthy trend but no fresh trigger |
| **STAY OUT / AVOID** | Flat — relentless bearish, no rebound |
| **OBSERVE** | Mixed signals — watch next close |

### Key Flags (from Python scripts)
- **Exhaustion:** RSI turning from overbought, MACD histogram shrinking, %B≥1, price stretched above EMA20
- **Relentless bearish:** Price<EMA50<EMA200 with EMA200↓, MACD deepening, TRIX<signal<0
- **Rebound:** RSI turning from oversold, MACD crossing bullishly, price reclaiming EMA20

---

## Order Execution (Manual Only)

The trading desk agent is **read-only by design**. IB Gateway is configured with Read-Only API mode:
1. Agent shows the scorecard + suggested action in `#trading-signals`
2. **You execute trades manually** via IBKR's Trader Workstation or mobile app
3. Agent can verify fills afterward via `python3 scripts/ibkr_data.py positions`

⚠ **NEVER attempt to place orders programmatically.** The data pipeline is for analysis only.
If you want automated execution later, that requires a dedicated execution agent with separate credentials.

---

## Automation Layer (Daily Hybrid Workflow)

Two cron jobs run on trading days:

### 1. EOD Pipeline (21:00 UTC, Mon-Fri)
Full 3-Step Filter Funnel, 1 hour after market close:

| Step | What | Script |
|------|------|--------|
| **1. Screener** | Refresh macro ETFs + yield spread. Filter universe by sector focus (default: Technology). Score top 15 candidates. | `screener.py` (via `eod_pipeline.py`) |
| **2. Metrics** | Run three-pillar scoring on each candidate. | `score.py` + `indicators.py` + `macro_pillar.py` |
| **3. Cognitive Review** | LLM evaluates context, produces structured proposal. Persona chain: analyst → risk → PM. | agent analysis |
| **→ Cache** | Viable proposals stored as orders in `pending_orders.json`. Status set to `pending_confirm`. Notification goes to `#trading-signals`. | `order_cache.py` |

Run manually:
```bash
cd /home/liron/.openclaw/agentic-trading-desk-workspace
python3 scripts/eod_pipeline.py                          # Tech focus (default)
python3 scripts/eod_pipeline.py --all-sectors             # Full sector scan
python3 scripts/eod_pipeline.py --dry-run                 # Review without caching
python3 scripts/eod_pipeline.py --json                    # Machine-readable
```

### 2. Pre-Market Sanity Check (12:30 UTC, Mon-Fri)
1 hour before market open. Checks all `confirmed` orders against live IBKR quotes.

- **Gap ≤ 2%:** Status → `sanity_check_ok` → flagged as ready for manual execution
- **Gap > 2%:** Status → `sanity_check_fail` → order alerted for reassessment

Run manually:
```bash
cd /home/liron/.openclaw/agentic-trading-desk-workspace
python3 scripts/premarket_check.py                        # Check all confirmed orders
python3 scripts/premarket_check.py --dry-run              # Preview without status changes
python3 scripts/premarket_check.py --force ORD-xxx        # Force-check a specific order
```

---

## Order Cache — State Machine

File: `pending_orders.json` in workspace root.

```
draft ──→ pending_confirm ──→ confirmed ──→ sanity_check_ok ──→ ready_for_execution
                             (via /confirm)       │
                                                  └── sanity_check_fail (gap > 2%)
```

### Order Lifecycle
1. **EOD pipeline** creates order → status `draft`
2. Agent reviews, posts to `#trading-signals` → status `pending_confirm`
3. **User types `/confirm ORD-xxx`** → status `confirmed`
4. **Pre-market check** runs → `sanity_check_ok` or `sanity_check_fail`
5. User executes manually via IBKR TWS
6. User types `/executed ORD-xxx` → status `executed`
7. User types `/cancel ORD-xxx` → status `cancelled`

### Cache CLI Commands
```bash
python3 scripts/order_cache.py add --ticker NVDA --action ENTER --close 120.50 --score +4
python3 scripts/order_cache.py confirm ORD-20260710-001
python3 scripts/order_cache.py list --status pending_confirm
python3 scripts/order_cache.py get ORD-20260710-001 --json
python3 scripts/order_cache.py update ORD-20260710-001 --status sanity_check_ok
python3 scripts/order_cache.py cancel ORD-20260710-001
python3 scripts/order_cache.py entry ORD-20260710-001 --limit 118.00 --qty 100 --stop 112.10 --target 126.00
python3 scripts/order_cache.py summary
```

### /confirm Protocol
When user types `/confirm` followed by an order ID in any channel:
1. Look up the order in `pending_orders.json`
2. Verify it's in `pending_confirm` status
3. Run: `python3 scripts/order_cache.py confirm <ORDER_ID>`
4. Confirm to user and note: pre-market check will fire at 12:30 UTC next trading day

For `/executed` or `/cancel`, same pattern with the respective command.

---

## Allowed Tools for This Agent
- `exec` — running Python scripts and bun client calls
- `web_fetch` — Investing.com, Google Finance for macro/analyst context
- `read` / `write` — workspace files
- `message` — sending to Discord (#trading-desk for commands, #trading-signals for publishing)
- `cron` — periodic analysis jobs
- `image_generate` — charts (Fridays only)
