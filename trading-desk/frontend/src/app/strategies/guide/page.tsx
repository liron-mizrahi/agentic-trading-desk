"use client";

import { ArrowLeft, TrendingUp, Zap, Brain, Shield, Activity, Layers, Gauge, LineChart, ArrowUpDown, Filter, Target, PlayCircle, Clock, BarChart3 } from "lucide-react";
import Link from "next/link";
import clsx from "clsx";

// ─── Glossary — finance → engineering translations ──────────────────────

interface TermDef { term: string; engineering: string; detail: string; }

const GLOSSARY: TermDef[] = [
  {
    term: "RSI (Relative Strength Index)",
    engineering: "Velocity sensor",
    detail: "Measures how fast and far price moved recently. RSI > 70 = overbought (moved up too fast), RSI < 30 = oversold (moved down too fast). Think of it as a normalised velocity reading — how many of the last N bars were up vs down.",
  },
  {
    term: "EMA (Exponential Moving Average)",
    engineering: "Low-pass filter with recency bias",
    detail: "A weighted rolling average that gives more weight to recent data. EMA20 = ~1 month, EMA50 = ~1 quarter, EMA200 = ~1 year. Higher-period EMAs are slower to react — like a longer smoothing window. When shorter EMA > longer EMA, the trend is up (like a positive slope).",
  },
  {
    term: "MACD Histogram",
    engineering: "Acceleration / 2nd derivative",
    detail: "MACD line = EMA12 − EMA26 (velocity). Signal line = EMA9 of MACD (smoothed velocity). Histogram = MACD − Signal → is momentum speeding up or slowing down? Positive histogram = bullish acceleration, shrinking histogram = deceleration (exhaustion warning).",
  },
  {
    term: "TRIX-15",
    engineering: "Triple-smoothed ROC (noise-filtered trend)",
    detail: "Rate-of-change of price after passing through 3 cascaded EMA filters. Crosses above its own signal line → new uptrend confirmed. Crosses below → downtrend. Because it's triple-smoothed, it filters out almost all noise — when it flips, it's significant.",
  },
  {
    term: "CHOP (Choppiness Index)",
    engineering: "Signal-to-noise ratio (SNR)",
    detail: "CHOP < 38.2 → market is trending (high SNR, good signal). CHOP > 61.8 → market is choppy/sideways (low SNR, noise dominates). A trending market is predictable; a choppy market is random. Only trade when SNR is high.",
  },
  {
    term: "Bollinger Bands %B",
    engineering: "Z-score / standard deviation channel",
    detail: "Price vs its 20-bar middle band, measured in standard deviations. %B = 1.0 → price at upper band (extended). %B = 0 → price at lower band (compressed). %B > 1 → possible exhaustion. %B < 0 → possible mean reversion setup.",
  },
  {
    term: "SMA200",
    engineering: "200-bar simple average (long-term baseline)",
    detail: "The unweighted average of the last 200 daily closes (~1 year). Price above SMA200 = long-term uptrend (bull market). Price below = downtrend (bear market). The simplest and most widely-followed trend filter.",
  },
  {
    term: "Death Cross",
    engineering: "Bearish structural break",
    detail: "EMA50 crosses below EMA200. Indicates the medium-term trend has broken below the long-term trend — a structural shift. During a death cross, entries are tactical (short-term, tight stops), not cyclical (long-term holds).",
  },
  {
    term: "Yield Curve (10Y−2Y)",
    engineering: "Macro health check / recession probability",
    detail: "Difference between 10-year and 2-year Treasury yields. Normally positive (longer loans pay more). When it inverts (negative) → bond market expects recession within 6−18 months. Steepening → expansion expected. This is the single most reliable macro indicator.",
  },
  {
    term: "ETF Cross-Asset Regime",
    engineering: "System health dashboard",
    detail: "We track 7 sector/market ETFs: XLF (financials), XLE (energy), XLK (tech), XLV (healthcare), XLY (consumer), XLU (utilities), XLP (staples). When defensive sectors (utilities, staples) outperform cyclical sectors (tech, consumer) → risk-off regime. When cyclical leads → risk-on.",
  },
  {
    term: "Support / Resistance",
    engineering: "Historical min/max bounds",
    detail: "Price levels where the market previously reversed. Support = floor (buyers stepped in). Resistance = ceiling (sellers stepped in). Breaking through = the pattern is invalidated. These are like regression-tested boundaries.",
  },
  {
    term: "Stop-Loss",
    engineering: "Circuit breaker / kill switch",
    detail: "A pre-set exit price below your entry. If price drops to this level, you exit automatically — no questions asked. Protects against black-swan events and prevents one bad trade from wiping out multiple good ones. Usually set 3–5% below entry.",
  },
  {
    term: "Risk/Reward Ratio (R:R)",
    engineering: "Expected value calculation",
    detail: "How much you risk losing vs how much you stand to gain. R:R = 1:2 means you risk $1 to make $2. With a 50% win rate and 1:2 R:R, your expected value is positive. Minimum threshold: 1:1.6 — anything below is a coin flip at best.",
  },
  {
    term: "Position Sizing",
    engineering: "Memory allocation / resource budget",
    detail: "How much capital to allocate per trade. Not all trades deserve the same allocation — volatile sectors (Tech) get reduced size, defensive sectors (Healthcare) get full size. This is like dynamically allocating RAM based on task risk profile.",
  },
  {
    term: "Exhaustion / Relentless",
    engineering: "Signal degradation patterns",
    detail: "Exhaustion: bullish momentum is fading — RSI rolling over, MACD histogram shrinking, price stretched. Time to exit before the reversal. Relentless: bearish momentum is compounding — all signals aligned negative with no relief. Do not enter, do not average down.",
  },
  {
    term: "Rebound / Reversal",
    engineering: "State transition trigger",
    detail: "The market was falling (or consolidating), but a fresh signal cluster indicates a turn: RSI bouncing from oversold, MACD turning positive, TRIX crossing up, price reclaiming EMA20. This is the entry trigger — not 'it went down a lot so it must go up.'",
  },
];

// ─── Component ────────────────────────────────────────────────────────────

export default function StrategiesGuidePage() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-6">
        <Link
          href="/strategies"
          className="inline-flex items-center gap-1.5 text-xs text-accent-blue hover:text-accent-blue/80 mb-4 transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Strategies
        </Link>
        <h1 className="text-xl font-bold text-text-primary">Strategy Guide</h1>
        <p className="mt-1 text-sm text-text-muted max-w-2xl">
          Detailed explanations of all trading strategies, with every financial
          term translated into engineering concepts you already know.
        </p>
      </div>

      {/* ── Momentum-Dip Catalyst ──────────────────────────────────────── */}
      <section className="card mb-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-purple/10">
            <Zap className="h-5 w-5 text-accent-purple" />
          </div>
          <div>
            <h2 className="text-base font-bold text-text-primary">Momentum-Dip Catalyst</h2>
            <p className="text-xs text-accent-purple">Mean Reversion Strategy</p>
          </div>
        </div>

        <div className="space-y-4 text-sm text-text-secondary leading-relaxed">
          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-1.5">What It Does</h3>
            <p>
              Finds stocks that have sold off sharply but are still in a long-term uptrend. The
              idea: sharp selloffs in healthy stocks are usually temporary — panic, not structural
              damage. The pipeline detects when the selloff is extreme enough to buy, but only if
              the long-term structure is still intact.
            </p>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-2">The Funnel (4 Steps)</h3>
            <div className="space-y-3">
              <FunnelStep
                number={1}
                icon={<Gauge className="h-4 w-4" />}
                title="RSI-2 Check"
                subtitle="Is the selloff extreme enough?"
                detail="RSI-2 measures the velocity of the last 2 bars. When it drops below the sector threshold (e.g. <10 for Tech, <20 for Healthcare), it means the selloff is statistically extreme — the kind that typically snaps back. Sector thresholds exist because volatile sectors (Tech) need a lower threshold to filter out normal noise."
              />
              <FunnelStep
                number={2}
                icon={<Activity className="h-4 w-4" />}
                title="Choppiness Index"
                subtitle="Is the market trending or just noisy?"
                detail="CHOP measures signal-to-noise ratio. < 38.2 = trending (predictable), > 61.8 = choppy (random). We only enter when the market is trending — buying into a choppy market is gambling, not trading."
              />
              <FunnelStep
                number={3}
                icon={<LineChart className="h-4 w-4" />}
                title="SMA200 Filter"
                subtitle="Is the long-term structure intact?"
                detail="Price must be above the 200-day simple moving average. This ensures we're buying a dip in an uptrend, not catching a falling knife in a downtrend. Think of SMA200 as the 'healthy/broken' boundary."
              />
              <FunnelStep
                number={4}
                icon={<Brain className="h-4 w-4" />}
                title="LLM Analysis"
                subtitle="Does the setup make sense contextually?"
                detail="All three filters passed → the LLM examines the full picture: sector context, price action, proximity to support/resistance, and recent news. It produces a structured BUY or NO_TRADE decision with specific entry price, stop-loss, take-profit, position size, and exit condition."
              />
            </div>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-1.5">Exit Rule</h3>
            <p>
              <strong>QS Exit:</strong> Close the position when today's closing price exceeds yesterday's
              high. This is a simple but effective rule: if the stock is recovering so strongly that it's
              breaking above its prior day's high, the mean-reversion move is likely done — take the profit.
            </p>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-1.5">Sizing Logic</h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
              <div className="rounded bg-surface-elevated px-3 py-2">
                <span className="font-semibold text-accent-green">Defensive</span>
                <p className="text-text-muted mt-0.5">Healthcare, Utilities, Real Estate, Consumer Staples → Full allocation</p>
              </div>
              <div className="rounded bg-surface-elevated px-3 py-2">
                <span className="font-semibold text-accent-yellow">Broad Market</span>
                <p className="text-text-muted mt-0.5">Financials, Industrials, Energy, Materials, Consumer Cyclical → Standard</p>
              </div>
              <div className="rounded bg-surface-elevated px-3 py-2">
                <span className="font-semibold text-accent-red">High Growth</span>
                <p className="text-text-muted mt-0.5">Technology, Communication → −30% size reduction</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Three-Pillar EOD ────────────────────────────────────────────── */}
      <section className="card mb-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-blue/10">
            <Layers className="h-5 w-5 text-accent-blue" />
          </div>
          <div>
            <h2 className="text-base font-bold text-text-primary">Three-Pillar EOD</h2>
            <p className="text-xs text-accent-blue">Systematic Scoring Framework</p>
          </div>
        </div>

        <div className="space-y-4 text-sm text-text-secondary leading-relaxed">
          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-1.5">What It Does</h3>
            <p>
              Scores every stock on three independent dimensions (−2 to +2 each, total −6 to +6),
              then applies a decision cascade to determine the next action. Unlike momentum-dip
              which waits for a specific pattern, the three-pillar framework evaluates the full state
              of a stock — whether you already hold it or not — and tells you what to do: enter, ride,
              exit, or stay out.
            </p>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-2">The Three Pillars</h3>
            <div className="space-y-3">
              <PillarCard
                color="accent-green"
                icon={<ArrowUpDown className="h-4 w-4" />}
                title="Trend (−2 to +2)"
                subtitle="EMA 20/50/200 structure + slope"
                points={[
                  "Price above/below EMA20 = short-term direction",
                  "EMA20 above/below EMA50 = intermediate alignment",
                  "EMA50 above/below EMA200 = long-term structure (death cross?)",
                  "EMA200 slope = is the 1-year trend rising or falling?",
                  "+2 = all 4 signals bullish, −2 = all 4 bearish",
                ]}
              />
              <PillarCard
                color="accent-purple"
                icon={<Gauge className="h-4 w-4" />}
                title="Momentum (−2 to +2)"
                subtitle="RSI-14, MACD histogram, TRIX-15 crossover"
                points={[
                  "RSI-14: mid-term velocity. ≥55 = bullish, ≤45 = bearish",
                  "MACD histogram: acceleration. Positive = speeding up, Negative = slowing down",
                  "TRIX-15 vs signal: cleanest trend indicator. Double/triple smoothed",
                  "+2 = all 3 signals bullish, −2 = all 3 bearish",
                ]}
              />
              <PillarCard
                color="accent-yellow"
                icon={<Shield className="h-4 w-4" />}
                title="Macro-Sentiment (−2 to +2)"
                subtitle="7 ETF regime + yield curve"
                points={[
                  "7 sector ETFs scored for risk-on vs risk-off rotation",
                  "10Y−2Y yield spread: inverted = recession warning",
                  "+2 = strong risk-on, expanding economy",
                  "0 = neutral/mixed signals",
                  "−2 = strong risk-off, recessionary",
                ]}
              />
            </div>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-2">
              The Decision Cascade
            </h3>
            <p className="mb-3">
              The composite score (−6 to +6) is just the starting point. The real intelligence
              is in the <strong>pattern detection layer</strong> that checks for specific state
              transitions:
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
              <DecisionCard
                icon={<Target className="h-4 w-4" />}
                title="Rebound Detection"
                color="text-accent-green"
                items={[
                  "RSI turning up from oversold (<35 → rising)",
                  "MACD histogram crossing positive",
                  "Price reclaiming EMA20 after recent dip",
                  "TRIX fresh bullish crossover below zero",
                ]}
                summary="If ≥2 signals active: ENTRY trigger. No death cross → cyclical RE-ENTRY. Death cross → TACTICAL (small size, tight stop)."
              />
              <DecisionCard
                icon={<Activity className="h-4 w-4" />}
                title="Exhaustion Detection"
                color="text-accent-red"
                items={[
                  "RSI rolling over from overbought (≥70 → falling)",
                  "MACD histogram shrinking in positive territory",
                  "Price at upper Bollinger Band (%B ≥ 1.0)",
                  "Price stretched >10% above EMA20",
                ]}
                summary="If ≥2 signals active while holding: EXIT / TRIM. Bullish momentum is dying. Rotate capital, wait for next rebound."
              />
              <DecisionCard
                icon={<Filter className="h-4 w-4" />}
                title="Relentless Bearish"
                color="text-accent-orange"
                items={[
                  "Price < EMA50 < EMA200 + EMA200↓",
                  "MACD histogram deepening negative",
                  "TRIX < signal below zero",
                  "RSI weak and still falling (<45, decreasing)",
                ]}
                summary="If ≥3 signals active: STAY OUT. Selling pressure is sustained. Even if a rebound appears, it's for EXITING at better prices, not entering."
              />
            </div>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-1.5">
              Capital Rotation Principle
            </h3>
            <p>
              The framework operates on <strong>capital rotation, not accumulation</strong>. The
              default state is not 'holding a large position' — it's 'waiting for the next trigger.'
              The cycle: <em>enter on confirmed rebound → ride the momentum → exit when exhaustion
              appears → wait for the next rebound.</em> Holding beyond the exhaustion point traps
              capital that could be deployed elsewhere. Think of it like a thread pool — you want
              capital working, not idle, but you also don't want it stuck in a deadlocked process.
            </p>
          </div>
        </div>
      </section>

      {/* ── Backtesting Engine ──────────────────────────────────────── */}
      <section className="card mb-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-green/10">
            <PlayCircle className="h-5 w-5 text-accent-green" />
          </div>
          <div>
            <h2 className="text-base font-bold text-text-primary">Backtesting Engine</h2>
            <p className="text-xs text-accent-green">Time-Warp Simulation</p>
          </div>
        </div>

        <div className="space-y-4 text-sm text-text-secondary leading-relaxed">
          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-1.5">What It Does</h3>
            <p>
              Runs any strategy against historical data with strict out-of-sample partitioning.
              Simulates execution as if you were trading the strategy live — no look-ahead bias,
              realistic fills, and proper benchmark comparison against SPY buy-and-hold.
            </p>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-text-primary mb-2">Available Strategies</h3>
            <div className="space-y-3">
              <BacktestStrategyCard
                name="Three-Pillar EOD"
                icon={<Layers className="h-4 w-4 text-accent-blue" />}
                detail="Full trend/momentum/macro scoring with decision cascade. Tests the composite score thresholds and pattern detection layers against years of market history."
                metrics="Returns, Sharpe, Max DD, Win Rate, Calmar Ratio, Alpha vs SPY"
              />
              <BacktestStrategyCard
                name="Momentum-Dip Catalyst"
                icon={<Zap className="h-4 w-4 text-accent-purple" />}
                detail="RSI-2 mean reversion funnel with QS exit rule. Tests sector-adapted thresholds and position sizing logic across different volatility regimes."
                metrics="Returns, Sharpe, Max DD, Win Rate, Profit Factor, Avg Hold Days"
              />
              <BacktestStrategyCard
                name="Squeeze Breakout"
                icon={<Gauge className="h-4 w-4 text-accent-green" />}
                detail="Bollinger Band squeeze detection — finds low-volatility consolidations that resolve into explosive moves. Entry on band expansion + volume confirmation."
                metrics="Returns, Sharpe, Max DD, Win Rate, Profit Factor"
              />
              <BacktestStrategyCard
                name="Dual Momentum"
                icon={<ArrowUpDown className="h-4 w-4 text-accent-yellow" />}
                detail="Relative + absolute momentum: ranks candidates by 6-month return, only enters if absolute momentum is positive (price > SMA200). Rotates capital to strongest performers."
                metrics="Returns, Sharpe, Max DD, Win Rate, Turnover Ratio"
              />
              <BacktestStrategyCard
                name="PEAD Drift"
                icon={<TrendingUp className="h-4 w-4 text-orange-400" />}
                detail="Post-Earnings Announcement Drift — enters after positive earnings surprises with strong price reaction. Captures the ~60 day drift anomaly."
                metrics="Returns, Sharpe, Max DD, Win Rate, Avg Hold Days"
              />
            </div>
          </div>

          <div className="mt-4 flex items-center gap-3">
            <Link
              href="/strategies/backtest"
              className="inline-flex items-center gap-2 rounded-lg bg-accent-blue/10 px-4 py-2 text-sm font-semibold text-accent-blue hover:bg-accent-blue/20 transition-colors"
            >
              <PlayCircle className="h-4 w-4" />
              Run Backtests
            </Link>
            <span className="text-xs text-text-muted">Configure strategy, sectors, date range, and run historical simulations</span>
          </div>
        </div>
      </section>

      {/* ── Pipeline Comparison ────────────────────────────────────────── */}
      <section className="card mb-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-elevated">
            <ArrowUpDown className="h-5 w-5 text-text-secondary" />
          </div>
          <h2 className="text-base font-bold text-text-primary">Strategy Comparison</h2>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-surface-border text-left text-text-muted">
                <th className="pb-2 pr-4 font-medium">Aspect</th>
                <th className="pb-2 pr-4 font-medium text-accent-purple">Momentum-Dip</th>
                <th className="pb-2 font-medium text-accent-blue">Three-Pillar</th>
              </tr>
            </thead>
            <tbody className="text-text-secondary">
              <CompareRow label="Type" md="Pattern-based entry" tp="State-based framework" />
              <CompareRow label="Entry trigger" md="RSI-2 oversold + trending" tp="Confirmed rebound pattern" />
              <CompareRow label="Exit trigger" md="QS Rule (close > prior high)" tp="Exhaustion detection (≥2 flags)" />
              <CompareRow label="Time horizon" md="2–5 days (mean reversion)" tp="5–20 days (momentum cycle)" />
              <CompareRow label="Requires holding?" md="No — enters only on setup" tp="Works for both flat and holding" />
              <CompareRow label="LLM role" md="Final BUY/NO_TRADE decision" tp="Not used — deterministic rules" />
              <CompareRow label="Data source" md="IBKR → yfinance (1 year)" tp="IBKR → yfinance (1 year) + macro ETFs" />
              <CompareRow label="Sectors" md="Screener-determined (usually 1)" tp="Screener-determined (usually 1)" />
              <CompareRow label="Sizing" md="Sector-adapted (−30% to full)" tp="Position-size agnostic (score only)" />
              <CompareRow label="Schedule" md="Cron: 21:00 UTC Mon-Fri" tp="Cron: 23:00 UTC Mon-Fri" />
            </tbody>
          </table>
        </div>
      </section>

      {/* ── Glossary ───────────────────────────────────────────────────── */}
      <section className="card">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-green/10">
            <Brain className="h-5 w-5 text-accent-green" />
          </div>
          <h2 className="text-base font-bold text-text-primary">Financial → Engineering Glossary</h2>
        </div>
        <p className="text-xs text-text-muted mb-4">
          Every term used in the strategies, translated. If you understand DSP, signal processing,
          or control systems, these will feel familiar.
        </p>

        <div className="space-y-3">
          {GLOSSARY.map((item) => (
            <div key={item.term} className="rounded bg-surface-elevated px-3 py-2.5">
              <div className="flex items-baseline gap-2 mb-1">
                <code className="text-xs font-mono font-semibold text-text-primary">{item.term}</code>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent-blue/10 text-accent-blue font-medium">
                  {item.engineering}
                </span>
              </div>
              <p className="text-xs text-text-secondary leading-relaxed">{item.detail}</p>
            </div>
          ))}
        </div>
      </section>

      <div className="mt-6 text-center">
        <Link
          href="/strategies"
          className="inline-flex items-center gap-1.5 text-xs text-accent-blue hover:text-accent-blue/80 transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Strategies
        </Link>
      </div>
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────

function FunnelStep({ number, icon, title, subtitle, detail }: {
  number: number; icon: React.ReactNode; title: string; subtitle: string; detail: string;
}) {
  return (
    <div className="flex gap-3">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-purple/10 text-xs font-bold text-accent-purple">
        {number}
      </div>
      <div className="flex-1">
        <div className="flex items-center gap-1.5 mb-0.5">
          {icon}
          <span className="text-xs font-semibold text-text-primary">{title}</span>
        </div>
        <p className="text-xs text-text-muted italic mb-0.5">{subtitle}</p>
        <p className="text-xs text-text-secondary">{detail}</p>
      </div>
    </div>
  );
}

function PillarCard({ color, icon, title, subtitle, points }: {
  color: string; icon: React.ReactNode; title: string; subtitle: string; points: string[];
}) {
  return (
    <div className={clsx("rounded border px-3 py-2.5", `border-${color}/20`, `bg-${color}/5`)}>
      <div className="flex items-center gap-1.5 mb-1">
        {icon}
        <span className={clsx("text-xs font-semibold", `text-${color}`)}>{title}</span>
      </div>
      <p className="text-[10px] text-text-muted mb-1.5">{subtitle}</p>
      <ul className="space-y-0.5">
        {points.map((p, i) => (
          <li key={i} className="flex items-start gap-1.5 text-xs text-text-secondary">
            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-text-muted" />
            {p}
          </li>
        ))}
      </ul>
    </div>
  );
}

function DecisionCard({ icon, title, color, items, summary }: {
  icon: React.ReactNode; title: string; color: string; items: string[]; summary: string;
}) {
  return (
    <div className="rounded bg-surface-elevated px-3 py-2.5">
      <div className={clsx("flex items-center gap-1.5 mb-1.5", color)}>
        {icon}
        <span className="text-xs font-semibold">{title}</span>
      </div>
      <ul className="space-y-0.5 mb-2">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-1 text-[11px] text-text-secondary leading-snug">
            <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-text-muted" />
            {item}
          </li>
        ))}
      </ul>
      <p className="text-[10px] text-text-muted leading-snug border-t border-surface-border pt-1.5">
        {summary}
      </p>
    </div>
  );
}

function CompareRow({ label, md, tp }: { label: string; md: string; tp: string }) {
  return (
    <tr className="border-b border-surface-border/50">
      <td className="py-2 pr-4 font-medium text-text-primary">{label}</td>
      <td className="py-2 pr-4 text-accent-purple">{md}</td>
      <td className="py-2 text-accent-blue">{tp}</td>
    </tr>
  );
}

function BacktestStrategyCard({ name, icon, detail, metrics }: {
  name: string; icon: React.ReactNode; detail: string; metrics: string;
}) {
  return (
    <div className="rounded border border-surface-border bg-surface-elevated px-3 py-2.5">
      <div className="flex items-center gap-2 mb-1.5">
        {icon}
        <span className="text-xs font-semibold text-text-primary">{name}</span>
      </div>
      <p className="text-xs text-text-secondary mb-1.5">{detail}</p>
      <p className="text-[10px] text-text-muted">
        <span className="font-semibold text-text-secondary">Metrics: </span>
        {metrics}
      </p>
    </div>
  );
}
