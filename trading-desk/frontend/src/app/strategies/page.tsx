"use client";

import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { Filter, Calendar, AlertTriangle, TrendingUp, ChevronDown, CheckCircle2, XCircle, BarChart3, Layers, GitFork, GripVertical, X, Minimize2, Maximize2, BookOpen, Zap } from "lucide-react";
import Link from "next/link";
import clsx from "clsx";
import { StrategyChart } from "@/components/StrategyChart";

// ─── Types ───────────────────────────────────────────────────────────

interface Pipeline {
  key: string;
  name: string;
  description: string;
  steps: { label: string; detail: string }[];
}

interface RunDate {
  date: string;
  symbol_count: number;
}

interface StepResult {
  name: string;
  detail: string;
  passed: boolean | null;
  value?: number | null;
  threshold?: number | null;
  reason?: string;
}

interface PillarScore {
  score: number | null;
  detail: string;
  passed: boolean | null;
}

interface Pillars {
  trend: PillarScore;
  momentum: PillarScore;
  macro_sentiment: PillarScore;
  composite: number | null;
}

interface ThreePillarIndicators {
  price: number | null;
  rsi14: number | null;
  macd_hist: number | null;
  trix: number | null;
  trix_signal: number | null;
  ema20: number | null;
  ema50: number | null;
  ema200: number | null;
  percent_b: number | null;
}

interface MomentumDipIndicators {
  rsi2: number | null;
  chop: number | null;
  sma200: number | null;
  price: number | null;
}

interface SymbolResult {
  ticker: string;
  strategy: "momentum_dip" | "three_pillar";
  sector: string | null;
  steps: StepResult[];
  indicators: MomentumDipIndicators | ThreePillarIndicators;
  pillars?: Pillars;
  decision_framing?: string;
  decision: string | null;
  confidence: number | null;
  reasoning: string;
  error: string | null;
  dead_letter: boolean;
  trade_id: string | null;
  trade_status: string | null;
  created_at: string | null;
  fundamentals?: {
    health_score: number;
    health_label: "HEALTHY" | "CAUTION" | "HIGH_RISK";
    trailing_pe: number | null;
    debt_to_equity: number | null;
    current_ratio: number | null;
    return_on_equity: number | null;
    profit_margins: number | null;
    flags: Array<{ metric: string; value: number; status: string; note: string }>;
  };
}

interface RunResults {
  pipeline: string;
  strategy: string;
  date: string;
  summary: { total: number; passed_step1: number; passed_step2: number; passed_step3: number; actionable: number };
  symbols: SymbolResult[];
}

// ─── Column definition for Finviz-style table ────────────────────────

interface ColumnDef {
  id: string;
  label: string;
  shortLabel: string;
  tooltip: string;
  width: number;
  minWidth: number;
  align?: "left" | "right" | "center";
  frozen?: "left";
  render: (s: SymbolResult) => React.ReactNode;
  sortable?: boolean;
}

// ─── Main Page ───────────────────────────────────────────────────────

export default function StrategiesPage() {
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [selectedPipeline, setSelectedPipeline] = useState<string>("momentum_dip");
  const [dates, setDates] = useState<RunDate[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [results, setResults] = useState<RunResults | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);
  const [sectorFilter, setSectorFilter] = useState<string>("ALL");
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [detailFullscreen, setDetailFullscreen] = useState(false);
  const tableRef = useRef<HTMLDivElement>(null!);

  useEffect(() => {
    fetch("/api/v1/pipelines")
      .then((r) => r.json())
      .then((data: Pipeline[]) => {
        setPipelines(data);
        if (data.length > 0) setSelectedPipeline(data[0].key);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedPipeline) return;
    fetch(`/api/v1/pipelines/dates?strategy=${selectedPipeline}`)
      .then((r) => r.json())
      .then((data: RunDate[]) => {
        setDates(data);
        if (data.length > 0) {
          setSelectedDate(data[0].date);
          setSectorFilter("ALL");
        } else {
          setSelectedDate("");
        }
        setResults(null);
        setError(null);
      })
      .catch(() => setDates([]));
  }, [selectedPipeline]);

  const loadRun = useCallback(() => {
    if (!selectedPipeline || !selectedDate) return;
    setLoading(true);
    setError(null);
    setExpandedTicker(null);
    fetch(`/api/v1/pipelines/runs?strategy=${selectedPipeline}&date=${selectedDate}`)
      .then((r) => {
        if (!r.ok) return r.json().then((e) => { throw new Error(e.detail || "Failed to load"); });
        return r.json();
      })
      .then((data: RunResults) => {
        setResults(data);
        setSectorFilter("ALL");
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [selectedPipeline, selectedDate]);

  useEffect(() => { if (selectedDate) loadRun(); }, [selectedDate, loadRun]);

  const pipeline = pipelines.find((p) => p.key === selectedPipeline);

  const sectors = useMemo(() => {
    if (!results) return [];
    const set = new Set<string>();
    results.symbols.forEach((s) => { if (s.sector) set.add(s.sector); });
    return Array.from(set).sort();
  }, [results]);

  const filteredSymbols = useMemo(() => {
    if (!results) return [];
    let syms = sectorFilter === "ALL" ? [...results.symbols] : results.symbols.filter((s) => s.sector === sectorFilter);
    if (sortCol) {
      syms.sort((a, b) => {
        let va: any, vb: any;
        if (sortCol === "ticker") { va = a.ticker; vb = b.ticker; }
        else if (sortCol === "sector") { va = a.sector || ""; vb = b.sector || ""; }
        else if (sortCol === "decision") { va = a.decision || ""; vb = b.decision || ""; }
        else if (sortCol === "confidence") { va = a.confidence ?? -1; vb = b.confidence ?? -1; }
        else if (sortCol === "price") {
          va = (a.indicators as any).price ?? 0; vb = (b.indicators as any).price ?? 0;
        } else if (sortCol === "rsi2" && selectedPipeline === "momentum_dip") {
          va = (a.indicators as MomentumDipIndicators).rsi2 ?? 999;
          vb = (b.indicators as MomentumDipIndicators).rsi2 ?? 999;
        } else if (sortCol === "chop" && selectedPipeline === "momentum_dip") {
          va = (a.indicators as MomentumDipIndicators).chop ?? 999;
          vb = (b.indicators as MomentumDipIndicators).chop ?? 999;
        } else if (sortCol === "composite") {
          va = a.pillars?.composite ?? -99; vb = b.pillars?.composite ?? -99;
        } else if (sortCol === "rsi14" && selectedPipeline === "three_pillar") {
          va = (a.indicators as ThreePillarIndicators).rsi14 ?? 999;
          vb = (b.indicators as ThreePillarIndicators).rsi14 ?? 999;
        } else {
          const stepIdx = a.steps.findIndex(s => s.name.toLowerCase().includes(sortCol || ""));
          if (stepIdx >= 0) {
            va = a.steps[stepIdx]?.passed === true ? 1 : a.steps[stepIdx]?.passed === false ? 0 : -1;
            vb = b.steps[stepIdx]?.passed === true ? 1 : b.steps[stepIdx]?.passed === false ? 0 : -1;
          } else { va = 0; vb = 0; }
        }
        if (va < vb) return sortDir === "asc" ? -1 : 1;
        if (va > vb) return sortDir === "asc" ? 1 : -1;
        return 0;
      });
    }
    return syms;
  }, [results, sectorFilter, sortCol, sortDir, selectedPipeline]);

  const handleSort = (colId: string) => {
    if (sortCol === colId) {
      setSortDir(d => d === "asc" ? "desc" : "asc");
    } else {
      setSortCol(colId);
      setSortDir("asc");
    }
  };

  // Build columns based on strategy
  const columns = useMemo((): ColumnDef[] => {
    if (selectedPipeline === "momentum_dip") {
      return [
        { id: "ticker", label: "Ticker", shortLabel: "Ticker", tooltip: "Ticker symbol of the stock being analyzed", width: 90, minWidth: 80, frozen: "left", align: "left",
          render: (s) => (
            <div className="flex items-center gap-1.5">
              <span className="font-mono font-bold text-text-primary text-[13px]">{s.ticker}</span>
              {s.fundamentals && (
                <span className={clsx("text-[9px] font-semibold px-1 rounded",
                  s.fundamentals.health_label === "HEALTHY" ? "bg-accent-green/10 text-accent-green" :
                  s.fundamentals.health_label === "CAUTION" ? "bg-accent-yellow/10 text-accent-yellow" :
                  "bg-accent-red/10 text-accent-red"
                )}>{s.fundamentals.health_score}/5</span>
              )}
            </div>
          ), sortable: true },
        { id: "sector", label: "Sector", shortLabel: "Sector", tooltip: "GICS sector classification", width: 110, minWidth: 90, align: "left",
          render: (s) => <span className="text-xs text-text-muted">{s.sector || "—"}</span>, sortable: true },
        { id: "price", label: "Price", shortLabel: "Px", tooltip: "Current closing price", width: 80, minWidth: 70, align: "right",
          render: (s) => {
            const p = (s.indicators as MomentumDipIndicators).price;
            return <span className="text-xs font-mono text-text-primary">{p != null ? `$${p.toFixed(2)}` : "—"}</span>;
          }, sortable: true },
        { id: "rsi2", label: "RSI-2", shortLabel: "RSI-2", tooltip: "Wilder's RSI with 2-period lookback — identifies extreme short-term oversold conditions. Below threshold (<10 for Tech) is a buy signal", width: 85, minWidth: 75, align: "center",
          render: (s) => {
            const rsi = (s.indicators as MomentumDipIndicators).rsi2;
            const step = s.steps.find(st => st.name === "RSI-2 Check");
            if (rsi == null) return <span className="text-xs text-text-muted">—</span>;
            const thresh = 10;
            const isPass = step?.passed === true;
            return (
              <span className={clsx("inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-mono font-bold",
                isPass ? "bg-accent-green/10 text-accent-green" : "bg-accent-red/10 text-accent-red"
              )}>
                {rsi.toFixed(2)}
                <span className="text-[9px] opacity-70">{isPass ? `<${thresh}` : `≥${thresh}`}</span>
              </span>
            );
          }, sortable: true },
        { id: "chop", label: "CHOP", shortLabel: "CHOP", tooltip: "Choppiness Index (14-period) — measures trend strength. Below 38.2 = strongly trending market", width: 85, minWidth: 75, align: "center",
          render: (s) => {
            const ch = (s.indicators as MomentumDipIndicators).chop;
            const step = s.steps.find(st => st.name === "CHOP Check");
            if (ch == null) return <span className="text-xs text-text-muted">—</span>;
            const isPass = step?.passed === true;
            return (
              <span className={clsx("inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-mono font-bold",
                isPass ? "bg-accent-green/10 text-accent-green" : "bg-orange-500/10 text-orange-400"
              )}>
                {ch.toFixed(2)}
                <span className="text-[9px] opacity-70">{isPass ? "<38.2" : "≥38.2"}</span>
              </span>
            );
          }, sortable: true },
        { id: "sma200", label: "SMA200", shortLabel: "SMA200", tooltip: "Price distance from 200-day Simple Moving Average — positive = uptrend, negative = downtrend", width: 95, minWidth: 85, align: "center",
          render: (s) => {
            const ind = s.indicators as MomentumDipIndicators;
            const step = s.steps.find(st => st.name === "SMA200 Check");
            if (ind.sma200 == null || ind.price == null) return <span className="text-xs text-text-muted">—</span>;
            const isPass = step?.passed === true;
            const distPct = ((ind.price - ind.sma200) / ind.sma200) * 100;
            return (
              <span className={clsx("inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-mono font-bold",
                isPass ? "bg-accent-green/10 text-accent-green" : "bg-accent-red/10 text-accent-red"
              )}>
                <span>{distPct >= 0 ? "+" : ""}{distPct.toFixed(1)}%</span>
              </span>
            );
          }, sortable: true },
        { id: "confidence", label: "Confidence", shortLabel: "Conf", tooltip: "LLM confidence score (0-100%) for the BUY recommendation", width: 90, minWidth: 80, align: "center",
          render: (s) => {
            if (s.confidence == null || s.confidence === 0) return <span className="text-xs text-text-muted">—</span>;
            const pct = s.confidence * 100;
            return (
              <div className="flex items-center gap-1.5">
                <div className="flex-1 h-1.5 rounded-full bg-surface-border overflow-hidden">
                  <div className={clsx("h-full rounded-full", pct >= 70 ? "bg-accent-green" : pct >= 40 ? "bg-accent-yellow" : "bg-accent-red")} style={{ width: `${pct}%` }} />
                </div>
                <span className="text-[10px] font-mono text-text-secondary">{pct.toFixed(0)}%</span>
              </div>
            );
          }, sortable: true },
        { id: "decision", label: "Decision", shortLabel: "Dec", tooltip: "Final trade decision: BUY or NO_TRADE", width: 90, minWidth: 80, align: "center",
          render: (s) => {
            if (s.error || s.dead_letter) return <span className="badge bg-accent-red/10 text-accent-red text-[10px]">ERR</span>;
            if (!s.decision) return <span className="text-xs text-text-muted">—</span>;
            const isBuy = s.decision === "BUY";
            return <span className={clsx("badge text-[10px] font-bold", isBuy ? "bg-accent-green/10 text-accent-green border border-accent-green/30" : "bg-surface-elevated text-text-muted border border-surface-border")}>{s.decision}</span>;
          }, sortable: true },
      ];
    } else {
      // Three-Pillar columns
      return [
        { id: "ticker", label: "Ticker", shortLabel: "Ticker", tooltip: "Ticker symbol of the stock being analyzed", width: 90, minWidth: 80, frozen: "left", align: "left",
          render: (s) => (
            <div className="flex items-center gap-1.5">
              <span className="font-mono font-bold text-text-primary text-[13px]">{s.ticker}</span>
              {s.fundamentals && (
                <span className={clsx("text-[9px] font-semibold px-1 rounded",
                  s.fundamentals.health_label === "HEALTHY" ? "bg-accent-green/10 text-accent-green" :
                  s.fundamentals.health_label === "CAUTION" ? "bg-accent-yellow/10 text-accent-yellow" :
                  "bg-accent-red/10 text-accent-red"
                )}>{s.fundamentals.health_score}/5</span>
              )}
            </div>
          ), sortable: true },
        { id: "sector", label: "Sector", shortLabel: "Sector", tooltip: "GICS sector classification", width: 100, minWidth: 80, align: "left",
          render: (s) => <span className="text-xs text-text-muted">{s.sector || "—"}</span>, sortable: true },
        { id: "price", label: "Price", shortLabel: "Px", tooltip: "Current closing price", width: 75, minWidth: 65, align: "right",
          render: (s) => {
            const p = (s.indicators as ThreePillarIndicators).price;
            return <span className="text-xs font-mono text-text-primary">{p != null ? `$${p.toFixed(2)}` : "—"}</span>;
          }, sortable: true },
        { id: "rsi14", label: "RSI-14", shortLabel: "RSI-14", tooltip: "Wilder's RSI with 14-period lookback — overbought >70, oversold <30", width: 80, minWidth: 70, align: "center",
          render: (s) => {
            const rsi = (s.indicators as ThreePillarIndicators).rsi14;
            if (rsi == null) return <span className="text-xs text-text-muted">—</span>;
            return <span className={clsx("text-xs font-mono font-bold px-1.5 py-0.5 rounded",
              rsi >= 70 ? "bg-accent-red/10 text-accent-red" : rsi <= 30 ? "bg-accent-green/10 text-accent-green" : "text-text-secondary"
            )}>{rsi.toFixed(1)}</span>;
          }, sortable: true },
        { id: "macd", label: "MACD Hist", shortLabel: "MACD", tooltip: "MACD histogram — bullish when positive, bearish when negative", width: 85, minWidth: 75, align: "center",
          render: (s) => {
            const macd = (s.indicators as ThreePillarIndicators).macd_hist;
            if (macd == null) return <span className="text-xs text-text-muted">—</span>;
            return <span className={clsx("text-xs font-mono font-bold px-1.5 py-0.5 rounded",
              macd > 0 ? "bg-accent-green/10 text-accent-green" : "bg-accent-red/10 text-accent-red"
            )}>{macd >= 0 ? "+" : ""}{macd.toFixed(3)}</span>;
          } },
        { id: "trix", label: "TRIX-15", shortLabel: "TRIX", tooltip: "Triple Exponential Average (15-period) — momentum oscillator. Positive = bullish", width: 80, minWidth: 70, align: "center",
          render: (s) => {
            const trix = (s.indicators as ThreePillarIndicators).trix;
            if (trix == null) return <span className="text-xs text-text-muted">—</span>;
            return <span className={clsx("text-xs font-mono font-bold px-1.5 py-0.5 rounded",
              trix > 0 ? "bg-accent-green/10 text-accent-green" : "bg-accent-red/10 text-accent-red"
            )}>{trix >= 0 ? "+" : ""}{trix.toFixed(2)}</span>;
          } },
        { id: "trend", label: "Trend", shortLabel: "Trend", tooltip: "EMA structure score (-2 to +2): price vs EMA20/50/200 alignment and slope", width: 75, minWidth: 65, align: "center",
          render: (s) => {
            const score = s.pillars?.trend.score;
            if (score == null) return <span className="text-xs text-text-muted">—</span>;
            return <PillarScoreCell score={score} />;
          }, sortable: true },
        { id: "momentum", label: "Momentum", shortLabel: "Mom", tooltip: "Momentum score (-2 to +2): RSI-14, MACD histogram, and TRIX-15 signal", width: 85, minWidth: 75, align: "center",
          render: (s) => {
            const score = s.pillars?.momentum.score;
            if (score == null) return <span className="text-xs text-text-muted">—</span>;
            return <PillarScoreCell score={score} />;
          }, sortable: true },
        { id: "macro", label: "Macro", shortLabel: "Macro", tooltip: "Macro-Sentiment score (-2 to +2): cross-asset ETF regime + yield curve", width: 75, minWidth: 65, align: "center",
          render: (s) => {
            const score = s.pillars?.macro_sentiment.score;
            if (score == null) return <span className="text-xs text-text-muted">—</span>;
            return <PillarScoreCell score={score} />;
          }, sortable: true },
        { id: "composite", label: "Composite", shortLabel: "Σ", tooltip: "Total composite score (-6 to +6) — sum of Trend + Momentum + Macro pillars", width: 90, minWidth: 80, align: "center",
          render: (s) => {
            const score = s.pillars?.composite;
            if (score == null) return <span className="text-xs text-text-muted">—</span>;
            return <CompositeCell score={score} />;
          }, sortable: true },
        { id: "decision", label: "Decision", shortLabel: "Dec", tooltip: "Final decision: BUY, HOLD, or EXIT", width: 85, minWidth: 75, align: "center",
          render: (s) => {
            if (s.error || s.dead_letter) return <span className="badge bg-accent-red/10 text-accent-red text-[10px]">ERR</span>;
            if (!s.decision) return <span className="text-xs text-text-muted">—</span>;
            const isBuy = s.decision === "BUY";
            return <span className={clsx("badge text-[10px] font-bold", isBuy ? "bg-accent-green/10 text-accent-green border border-accent-green/30" : "bg-surface-elevated text-text-muted border border-surface-border")}>{s.decision}</span>;
          }, sortable: true },
      ];
    }
  }, [selectedPipeline]);

  return (
    <div className="mx-auto max-w-[1600px] px-4 py-4 sm:px-6 lg:px-8">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-purple/10">
            <Layers className="h-5 w-5 text-accent-purple" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-text-primary">Strategies Dashboard</h1>
            <p className="text-xs text-text-muted">Multi-strategy signal analysis grid</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/strategies/guide"
            className="flex items-center gap-1.5 rounded-lg border border-surface-border px-3 py-1.5 text-xs text-accent-blue hover:bg-accent-blue/5 transition-colors"
          >
            <BookOpen className="h-3.5 w-3.5" />
            Strategy Guide
          </Link>
          <Link
            href="/pipelines"
            className="flex items-center gap-1.5 rounded-lg border border-surface-border px-3 py-1.5 text-xs text-text-muted hover:text-text-secondary transition-colors"
          >
            <GitFork className="h-3.5 w-3.5" />
            Legacy Pipelines
          </Link>
        </div>
      </header>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Zap className="h-4 w-4 text-accent-yellow" />
          <select
            value={selectedPipeline}
            onChange={(e) => { setSelectedPipeline(e.target.value); setSectorFilter("ALL"); }}
            className="rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm text-text-primary outline-none focus:border-accent-blue/50"
          >
            {pipelines.map((p) => (
              <option key={p.key} value={p.key}>{p.name}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <Calendar className="h-4 w-4 text-text-muted" />
          <select
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            disabled={dates.length === 0}
            className="rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm text-text-primary outline-none focus:border-accent-blue/50 disabled:opacity-50"
          >
            {dates.length === 0 && <option value="">No runs found</option>}
            {dates.map((d) => (
              <option key={d.date} value={d.date}>{d.date} ({d.symbol_count} symbols)</option>
            ))}
          </select>
        </div>
        {results && sectors.length > 1 && (
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-text-muted" />
            <select
              value={sectorFilter}
              onChange={(e) => { setSectorFilter(e.target.value); setExpandedTicker(null); }}
              className="rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm text-text-primary outline-none focus:border-accent-blue/50"
            >
              <option value="ALL">All Sectors ({results.symbols.length})</option>
              {sectors.map((sec) => (
                <option key={sec} value={sec}>{sec} ({results.symbols.filter((s) => s.sector === sec).length})</option>
              ))}
            </select>
          </div>
        )}
        {results && (
          <span className="text-xs text-text-muted">
            {filteredSymbols.length} symbols
            {results.summary.actionable > 0 && (
              <span className="ml-1 text-accent-green font-semibold">· {results.summary.actionable} BUY</span>
            )}
          </span>
        )}
        {pipeline && (
          <p className="text-xs text-text-muted max-w-2xl leading-relaxed ml-auto">{pipeline.description}</p>
        )}
      </div>

      {error && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-accent-red/30 bg-accent-red/5 px-4 py-2 text-sm">
          <AlertTriangle className="h-4 w-4 text-accent-red shrink-0" />
          <span className="flex-1 text-accent-red">{error}</span>
        </div>
      )}

      {loading && (
        <div className="card py-16 text-center">
          <div className="mx-auto h-6 w-6 animate-spin rounded-full border-2 border-accent-blue border-t-transparent" />
          <p className="mt-3 text-sm text-text-muted">Loading strategy results...</p>
        </div>
      )}

      {results && filteredSymbols.length === 0 && sectorFilter !== "ALL" && (
        <div className="card py-8 text-center">
          <p className="text-sm text-text-muted">No symbols in sector &quot;{sectorFilter}&quot; for this run.</p>
          <button onClick={() => setSectorFilter("ALL")} className="mt-2 text-xs text-accent-blue hover:underline">Show all sectors</button>
        </div>
      )}

      {results && filteredSymbols.length > 0 && (
        <div className={detailFullscreen && expandedTicker ? "hidden" : ""}>
          <FunnelSummaryBar summary={results!.summary} steps={pipeline?.steps || []} filteredCount={filteredSymbols.length} />

          <FinvizTable
            symbols={filteredSymbols}
            columns={columns}
            expandedTicker={expandedTicker}
            onToggle={(ticker) => setExpandedTicker(expandedTicker === ticker ? null : ticker)}
            sortCol={sortCol}
            sortDir={sortDir}
            onSort={handleSort}
            tableRef={tableRef}
          />

          {expandedTicker && (
            <StrategyDetailPanel
              symbol={filteredSymbols.find(s => s.ticker === expandedTicker)!}
              strategy={results!.strategy as "momentum_dip" | "three_pillar"}
              onClose={() => setExpandedTicker(null)}
              onFullscreen={() => setDetailFullscreen(true)}
            />
          )}
        </div>
      )}

      {detailFullscreen && expandedTicker && (
        <div className="fixed inset-0 z-50 bg-surface/95 backdrop-blur-sm overflow-auto">
          <div className="mx-auto max-w-5xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-text-primary flex items-center gap-2">
                <BarChart3 className="h-5 w-5 text-accent-blue" />
                {expandedTicker} — Full Analysis
              </h2>
              <button onClick={() => setDetailFullscreen(false)} className="rounded-lg p-2 text-text-muted hover:bg-surface-elevated hover:text-text-primary transition-colors">
                <Minimize2 className="h-5 w-5" />
              </button>
            </div>
            <StrategyDetailPanelFull
              symbol={filteredSymbols.find(s => s.ticker === expandedTicker)!}
              strategy={results!.strategy as "momentum_dip" | "three_pillar"}
            />
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Funnel Summary Bar ──────────────────────────────────────────────────

function FunnelSummaryBar({ summary, steps, filteredCount }: { summary: RunResults["summary"]; steps: { label: string }[]; filteredCount: number }) {
  const stages = [
    { label: "Subjects", value: filteredCount, color: "bg-accent-blue" },
    ...steps.map((s, i) => ({
      label: s.label,
      value: i === 0 ? summary.passed_step1 : i === 1 ? summary.passed_step2 : summary.passed_step3,
      color: i === 0 ? "bg-accent-purple" : i === 1 ? "bg-accent-yellow" : "bg-orange-500",
    })),
    { label: "BUY", value: summary.actionable, color: "bg-accent-green" },
  ];

  return (
    <div className="card mb-3 px-3 py-2">
      <div className="flex items-center gap-1">
        {stages.map((stage, i) => (
          <div key={i} className="flex-1 flex items-center gap-2 min-w-0">
            <div className={clsx("h-2 w-3 rounded-sm shrink-0", stage.color, stage.value === 0 && "opacity-20")} />
            <span className="text-[10px] text-text-muted truncate">{stage.label}</span>
            <span className="text-xs font-mono font-bold text-text-primary ml-auto">{stage.value}</span>
            {i < stages.length - 1 && (
              <TrendingUp className="h-3 w-3 text-text-muted opacity-40 shrink-0" />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Finviz-Style Scrollable Table ────────────────────────────────────────

function FinvizTable({
  symbols, columns, expandedTicker, onToggle,
  sortCol, sortDir, onSort, tableRef,
}: {
  symbols: SymbolResult[];
  columns: ColumnDef[];
  expandedTicker: string | null;
  onToggle: (ticker: string) => void;
  sortCol: string | null;
  sortDir: "asc" | "desc";
  onSort: (colId: string) => void;
  tableRef: React.RefObject<HTMLDivElement>;
}) {
  const frozenCols = columns.filter(c => c.frozen === "left");
  const scrollCols = columns.filter(c => c.frozen !== "left");
  const frozenWidth = frozenCols.reduce((acc, c) => acc + c.width, 0);
  const totalWidth = columns.reduce((acc, c) => acc + c.width, 0) + 12;

  return (
    <div className="card overflow-hidden p-0">
      <div ref={tableRef} className="overflow-x-auto" style={{ maxHeight: "calc(100vh - 340px)", overflowY: "auto" }}>
        <table className="w-full border-collapse" style={{ minWidth: totalWidth }}>
          <thead className="sticky top-0 z-20">
            <tr className="bg-surface-elevated border-b border-surface-border">
              {frozenCols.map(col => (
                <th
                  key={col.id}
                  className={clsx("px-2 py-2 text-left text-[11px] font-semibold text-text-secondary uppercase tracking-wider cursor-pointer hover:text-text-primary transition-colors select-none sticky left-0 bg-surface-elevated z-30 border-r border-surface-border")}
                  style={{ width: col.width, minWidth: col.minWidth, left: frozenCols.indexOf(col) * col.width }}
                  onClick={() => col.sortable && onSort(col.id)}
                  title={col.tooltip}
                >
                  <div className="flex items-center gap-1">
                    {col.label}
                    {sortCol === col.id && (
                      <ChevronDown className={clsx("h-3 w-3 transition-transform", sortDir === "desc" && "rotate-180")} />
                    )}
                  </div>
                </th>
              ))}
              {scrollCols.map(col => (
                <th
                  key={col.id}
                  className={clsx("px-2 py-2 text-left text-[11px] font-semibold text-text-secondary uppercase tracking-wider cursor-pointer hover:text-text-primary transition-colors select-none", col.align === "right" && "text-right", col.align === "center" && "text-center")}
                  style={{ width: col.width, minWidth: col.minWidth }}
                  onClick={() => col.sortable && onSort(col.id)}
                  title={col.tooltip}
                >
                  <div className={clsx("flex items-center gap-1", col.align === "right" && "justify-end", col.align === "center" && "justify-center")}>
                    {col.label}
                    {sortCol === col.id && (
                      <ChevronDown className={clsx("h-3 w-3 transition-transform", sortDir === "desc" && "rotate-180")} />
                    )}
                  </div>
                </th>
              ))}
              <th className="w-10 px-1 py-2" />
            </tr>
          </thead>
          <tbody>
            {symbols.map((sym, idx) => (
              <tr
                key={sym.ticker}
                className={clsx(
                  "border-b border-surface-border/50 transition-colors cursor-pointer",
                  expandedTicker === sym.ticker ? "bg-accent-blue/5" : "hover:bg-surface-elevated/40",
                  sym.decision === "BUY" && "bg-accent-green/[0.03]",
                  sym.error && "bg-accent-red/[0.03]",
                )}
                style={{ animationDelay: `${idx * 30}ms` }}
                onClick={() => onToggle(sym.ticker)}
              >
                {frozenCols.map((col, ci) => (
                  <td
                    key={col.id}
                    className={clsx("px-2 py-2 sticky left-0 z-10 border-r border-surface-border/50",
                      expandedTicker === sym.ticker ? "bg-accent-blue/5" :
                      sym.decision === "BUY" ? "bg-accent-green/[0.03]" :
                      sym.error ? "bg-accent-red/[0.03]" :
                      idx % 2 === 0 ? "bg-surface-card" : "bg-surface-card/50"
                    )}
                    style={{ width: col.width, minWidth: col.minWidth, left: ci * frozenCols[0].width }}
                  >
                    {col.render(sym)}
                  </td>
                ))}
                {scrollCols.map(col => (
                  <td
                    key={col.id}
                    className={clsx("px-2 py-2", col.align === "right" && "text-right", col.align === "center" && "text-center")}
                  >
                    {col.render(sym)}
                  </td>
                ))}
                <td className="w-10 px-1 py-2 text-center">
                  <ChevronDown className={clsx(
                    "h-3.5 w-3.5 text-text-muted transition-transform ml-auto",
                    expandedTicker === sym.ticker && "rotate-180 text-accent-blue"
                  )} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Pillar Score Cell ────────────────────────────────────────────────────

function PillarScoreCell({ score }: { score: number }) {
  const pct = ((score + 2) / 4) * 100;
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex-1 h-1.5 rounded-full bg-surface-border overflow-hidden">
        <div
          className={clsx("h-full rounded-full",
            score > 0 ? "bg-accent-green" : score === 0 ? "bg-accent-yellow" : "bg-accent-red"
          )}
          style={{ width: `${Math.max(pct, 8)}%` }}
        />
      </div>
      <span className={clsx("text-xs font-mono font-bold",
        score > 0 ? "text-accent-green" : score === 0 ? "text-accent-yellow" : "text-accent-red"
      )}>
        {score >= 0 ? "+" : ""}{score}
      </span>
    </div>
  );
}

// ─── Composite Score Cell ─────────────────────────────────────────────────

function CompositeCell({ score }: { score: number }) {
  return (
    <span className={clsx("inline-flex items-center justify-center h-6 w-7 rounded-full text-xs font-mono font-bold border",
      score > 0 ? "border-accent-green/50 text-accent-green bg-accent-green/10" :
      score === 0 ? "border-accent-yellow/50 text-accent-yellow bg-accent-yellow/10" :
      "border-accent-red/50 text-accent-red bg-accent-red/10"
    )}>
      {score >= 0 ? "+" : ""}{score}
    </span>
  );
}

// ─── Strategy Detail Panel (Below Table) ──────────────────────────────────

function StrategyDetailPanel({ symbol, strategy, onClose, onFullscreen }: {
  symbol: SymbolResult;
  strategy: "momentum_dip" | "three_pillar";
  onClose: () => void;
  onFullscreen: () => void;
}) {
  return (
    <div className="card mt-3 animate-fade-in border-l-2 border-l-accent-blue">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="font-mono font-bold text-text-primary text-sm">{symbol.ticker}</span>
          {symbol.sector && <span className="text-xs text-text-muted">· {symbol.sector}</span>}
          {symbol.decision && (
            <span className={clsx("badge text-[10px] font-bold", symbol.decision === "BUY" ? "bg-accent-green/10 text-accent-green border border-accent-green/30" : "bg-surface-elevated text-text-muted")}>{symbol.decision}</span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button onClick={onFullscreen} className="rounded p-1.5 text-text-muted hover:bg-surface-elevated hover:text-text-primary transition-colors" title="Fullscreen">
            <Maximize2 className="h-4 w-4" />
          </button>
          <button onClick={onClose} className="rounded p-1.5 text-text-muted hover:bg-surface-elevated hover:text-text-primary transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {strategy === "momentum_dip" ? (
        <MomentumDipDetail symbol={symbol} />
      ) : (
        <ThreePillarDetail symbol={symbol} />
      )}
    </div>
  );
}

// ─── Fullscreen Detail ────────────────────────────────────────────────────

function StrategyDetailPanelFull({ symbol, strategy }: {
  symbol: SymbolResult;
  strategy: "momentum_dip" | "three_pillar";
}) {
  return (
    <div className="card">
      <div className="flex items-center gap-2 mb-4">
        <span className="font-mono font-bold text-text-primary text-lg">{symbol.ticker}</span>
        {symbol.sector && <span className="text-sm text-text-muted">· {symbol.sector}</span>}
        {symbol.decision && (
          <span className={clsx("badge text-xs font-bold", symbol.decision === "BUY" ? "bg-accent-green/10 text-accent-green border border-accent-green/30" : "bg-surface-elevated text-text-muted")}>{symbol.decision}</span>
        )}
      </div>

      {strategy === "momentum_dip" ? (
        <MomentumDipDetail symbol={symbol} />
      ) : (
        <ThreePillarDetail symbol={symbol} />
      )}
    </div>
  );
}

// ─── Momentum-Dip Detail (graphical) ──────────────────────────────────────

function MomentumDipDetail({ symbol }: { symbol: SymbolResult }) {
  const ind = symbol.indicators as MomentumDipIndicators;
  const hasError = symbol.error || symbol.dead_letter;
  const stepResults = symbol.steps.filter(s => s.name !== "Data Fetch" && s.name !== "LLM Analysis");

  return (
    <div className="space-y-4">
      {/* OHLC Chart */}
      <StrategyChart ticker={symbol.ticker} height={280} />

      {/* Visual Step Pass/Fail Gauges */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {stepResults.map((step, i) => {
          let value: number | null = null;
          let threshold: number | null = null;
          let unit = "";
          let gaugeLabel = "";
          let inverted = false;

          if (step.name.includes("RSI")) {
            value = ind.rsi2;
            threshold = 10;
            unit = "";
            gaugeLabel = "RSI-2";
            inverted = true;
          } else if (step.name.includes("CHOP")) {
            value = ind.chop;
            threshold = 38.2;
            unit = "";
            gaugeLabel = "CHOP";
            inverted = true;
          } else if (step.name.includes("SMA")) {
            value = ind.sma200 != null && ind.price != null ? ((ind.price - ind.sma200) / ind.sma200) * 100 : null;
            threshold = 0;
            unit = "%";
            gaugeLabel = "Px vs SMA200";
            inverted = false;
          }

          return (
            <div key={i} className={clsx(
              "rounded-lg border p-3 transition-colors",
              step.passed === true ? "border-accent-green/30 bg-accent-green/5" :
              step.passed === false ? "border-accent-red/30 bg-accent-red/5" :
              "border-surface-border bg-surface-elevated"
            )}>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-text-secondary">{step.name}</span>
                <span className={clsx("text-[10px] font-bold px-1.5 py-0.5 rounded",
                  step.passed === true ? "bg-accent-green/10 text-accent-green" :
                  "bg-accent-red/10 text-accent-red"
                )}>
                  {step.passed === true ? "PASS" : "FAIL"}
                </span>
              </div>
              {value != null && threshold != null && (
                <div className="mb-1.5">
                  <StepGauge value={value} threshold={threshold} unit={unit} inverted={inverted} label={gaugeLabel} />
                </div>
              )}
              {value != null && (
                <div className="flex items-baseline justify-between">
                  <span className={clsx("text-lg font-mono font-bold", step.passed ? "text-accent-green" : "text-accent-red")}>
                    {value.toFixed(2)}{unit}
                  </span>
                  {threshold != null && (
                    <span className="text-[10px] text-text-muted">threshold: {threshold}{unit}</span>
                  )}
                </div>
              )}
              {step.reason && (
                <p className="mt-1 text-[10px] text-text-muted leading-tight">{step.reason}</p>
              )}
              <p className="mt-0.5 text-[10px] text-text-muted/70">{step.detail}</p>
            </div>
          );
        })}
      </div>

      <LLMAnalysisSection symbol={symbol} ind={ind} />

      {symbol.fundamentals && <FundamentalHealthCard fundamentals={symbol.fundamentals} />}

      {hasError && (
        <div className="flex items-start gap-2 rounded bg-accent-red/5 border border-accent-red/20 p-3">
          <AlertTriangle className="h-4 w-4 text-accent-red mt-0.5 shrink-0" />
          <div>
            <p className="text-xs font-medium text-accent-red">Analysis Error</p>
            <p className="text-xs text-accent-red/70 mt-0.5">{symbol.error || "Dead letter — max retries exceeded"}</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Step Gauge (visual indicator) ────────────────────────────────────────

function StepGauge({ value, threshold, unit, inverted, label }: {
  value: number;
  threshold: number;
  unit: string;
  inverted: boolean;
  label: string;
}) {
  let min: number, max: number;
  if (label === "CHOP") { min = 0; max = 100; }
  else if (label === "RSI-2") { min = 0; max = 100; }
  else { min = Math.min(value, threshold) - 10; max = Math.max(value, threshold) + 10; }

  const range = max - min || 1;
  const valPct = ((value - min) / range) * 100;
  const threshPct = ((threshold - min) / range) * 100;
  const isPass = inverted ? value < threshold : value > threshold;

  return (
    <div className="relative h-6 rounded-full bg-surface-border overflow-hidden">
      {inverted ? (
        <div className="absolute inset-y-0 left-0 bg-accent-green/15" style={{ width: `${threshPct}%` }} />
      ) : (
        <div className="absolute inset-y-0 right-0 bg-accent-green/15" style={{ left: `${threshPct}%` }} />
      )}
      {inverted ? (
        <div className="absolute inset-y-0 right-0 bg-accent-red/10" style={{ left: `${threshPct}%` }} />
      ) : (
        <div className="absolute inset-y-0 left-0 bg-accent-red/10" style={{ width: `${threshPct}%` }} />
      )}
      <div className="absolute inset-y-0 w-0.5 bg-white/50" style={{ left: `${threshPct}%` }} />
      <div className={clsx(
        "absolute top-1/2 -translate-y-1/2 h-4 w-1.5 rounded-sm shadow-md",
        isPass ? "bg-accent-green" : "bg-accent-red"
      )} style={{ left: `${Math.max(1, Math.min(99, valPct))}%` }} />
    </div>
  );
}

// ─── LLM Analysis Section ─────────────────────────────────────────────────

function LLMAnalysisSection({ symbol, ind }: { symbol: SymbolResult; ind: MomentumDipIndicators }) {
  const [showReasoning, setShowReasoning] = useState(false);
  const llmStep = symbol.steps.find(s => s.name === "LLM Analysis");

  return (
    <div className="rounded-lg border border-surface-border bg-surface-elevated p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-accent-blue" />
          <span className="text-xs font-semibold text-text-secondary">LLM Analysis</span>
        </div>
        {llmStep && (
          <span className={clsx("text-[10px] font-bold px-1.5 py-0.5 rounded",
            llmStep.passed ? "bg-accent-green/10 text-accent-green" : "bg-accent-red/10 text-accent-red"
          )}>{llmStep.passed ? "EXECUTED" : "FAILED/SKIPPED"}</span>
        )}
      </div>

      {symbol.confidence != null && symbol.confidence > 0 && (
        <div className="flex items-center gap-2 mb-2">
          <span className="text-[10px] text-text-muted">Confidence</span>
          <div className="flex-1 h-2 rounded-full bg-surface-border overflow-hidden">
            <div className={clsx("h-full rounded-full",
              symbol.confidence >= 0.7 ? "bg-accent-green" :
              symbol.confidence >= 0.4 ? "bg-accent-yellow" : "bg-accent-red"
            )} style={{ width: `${symbol.confidence * 100}%` }} />
          </div>
          <span className="text-[10px] font-mono font-bold text-text-primary">{(symbol.confidence * 100).toFixed(0)}%</span>
        </div>
      )}

      {symbol.decision === "BUY" && symbol.trade_id && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-2 text-[10px]">
          <div><span className="text-text-muted">Entry</span><p className="font-mono font-bold text-accent-blue">${ind.price?.toFixed(2)}</p></div>
          <div><span className="text-text-muted">Stop Loss</span><p className="font-mono font-bold text-accent-red">${(ind.price ?? 0 * 0.95).toFixed(2)}</p></div>
          <div><span className="text-text-muted">Take Profit</span><p className="font-mono font-bold text-accent-green">${(ind.price ?? 0 * 1.08).toFixed(2)}</p></div>
          <div><span className="text-text-muted">Position</span><p className="font-mono font-bold text-text-primary">{symbol.confidence ? (symbol.confidence * 100 * 0.3).toFixed(0) : "—"}%</p></div>
        </div>
      )}

      {symbol.reasoning && (
        <div>
          <button
            onClick={() => setShowReasoning(!showReasoning)}
            className="flex items-center gap-1.5 text-[10px] text-accent-blue hover:text-accent-blue/80 transition-colors"
          >
            <ChevronDown className={clsx("h-3 w-3 transition-transform", showReasoning && "rotate-180")} />
            {showReasoning ? "Hide" : "Show"} LLM Reasoning
          </button>
          {showReasoning && (
            <div className="mt-2 rounded bg-surface-card p-3 text-xs text-text-secondary leading-relaxed animate-slide-in">
              <pre className="whitespace-pre-wrap font-sans">{symbol.reasoning}</pre>
            </div>
          )}
        </div>
      )}

      {!symbol.reasoning && !symbol.error && (
        <p className="text-[10px] text-text-muted italic">No LLM reasoning available for this run.</p>
      )}
    </div>
  );
}

// ─── Three-Pillar Detail ──────────────────────────────────────────────────

function ThreePillarDetail({ symbol }: { symbol: SymbolResult }) {
  const pillars = symbol.pillars;
  const ind = symbol.indicators as ThreePillarIndicators;
  const [showReasoning, setShowReasoning] = useState(false);

  return (
    <div className="space-y-4">
      {/* OHLC Chart */}
      <StrategyChart ticker={symbol.ticker} height={280} />

      {/* Pillar Score Gauges */}
      {pillars && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <PillarGauge label="Trend" score={pillars.trend.score} detail={pillars.trend.detail} />
          <PillarGauge label="Momentum" score={pillars.momentum.score} detail={pillars.momentum.detail} />
          <PillarGauge label="Macro-Sentiment" score={pillars.macro_sentiment.score} detail={pillars.macro_sentiment.detail} />
        </div>
      )}

      {/* Composite Score */}
      {pillars?.composite != null && (
        <div className="flex items-center gap-3 rounded-lg border border-surface-border bg-surface-elevated p-3">
          <div className={clsx("flex items-center justify-center h-12 w-12 rounded-full border-2 font-mono font-bold text-lg",
            pillars.composite > 0 ? "border-accent-green/50 text-accent-green bg-accent-green/10" :
            pillars.composite === 0 ? "border-accent-yellow/50 text-accent-yellow bg-accent-yellow/10" :
            "border-accent-red/50 text-accent-red bg-accent-red/10"
          )}>
            {pillars.composite >= 0 ? "+" : ""}{pillars.composite}
          </div>
          <div>
            <span className="text-xs font-semibold text-text-secondary">Composite Score</span>
            <p className="text-[10px] text-text-muted">Scale: -6 to +6</p>
          </div>
          {symbol.decision && (
            <span className={clsx("badge text-xs font-bold ml-auto",
              symbol.decision === "BUY" ? "bg-accent-green/10 text-accent-green" :
              symbol.decision === "HOLD" ? "bg-accent-blue/10 text-accent-blue" :
              symbol.decision === "EXIT" ? "bg-accent-red/10 text-accent-red" :
              "bg-surface-elevated text-text-muted"
            )}>{symbol.decision}</span>
          )}
        </div>
      )}

      {symbol.decision_framing && (
        <div className="rounded-lg border-l-2 border-l-accent-blue bg-surface-elevated p-3">
          <span className="text-[10px] text-text-muted uppercase tracking-wide">Decision Framing</span>
          <p className="text-xs text-text-secondary leading-relaxed mt-1">{symbol.decision_framing}</p>
        </div>
      )}

      <div className="flex flex-wrap gap-1.5">
        {ind.price != null && <IndicatorPill label="Price" value={`$${ind.price.toFixed(2)}`} />}
        {ind.rsi14 != null && <IndicatorPill label="RSI-14" value={ind.rsi14.toFixed(1)} status={ind.rsi14 >= 70 ? "overbought" : ind.rsi14 <= 30 ? "oversold" : "neutral"} />}
        {ind.macd_hist != null && <IndicatorPill label="MACD Hist" value={`${ind.macd_hist >= 0 ? "+" : ""}${ind.macd_hist.toFixed(3)}`} status={ind.macd_hist > 0 ? "bullish" : "bearish"} />}
        {ind.trix != null && <IndicatorPill label="TRIX-15" value={`${ind.trix >= 0 ? "+" : ""}${ind.trix.toFixed(2)}`} status={ind.trix > 0 ? "bullish" : "bearish"} />}
        {ind.ema20 != null && <IndicatorPill label="EMA20" value={`$${ind.ema20.toFixed(2)}`} />}
        {ind.ema50 != null && <IndicatorPill label="EMA50" value={`$${ind.ema50.toFixed(2)}`} />}
        {ind.ema200 != null && <IndicatorPill label="EMA200" value={`$${ind.ema200.toFixed(2)}`} />}
      </div>

      {ind.price != null && ind.ema20 != null && ind.ema50 != null && ind.ema200 != null && (
        <div className="flex items-center gap-3 text-[10px]">
          {[
            { label: "EMA20", value: ind.ema20 },
            { label: "EMA50", value: ind.ema50 },
            { label: "EMA200", value: ind.ema200 },
          ].map((ema) => {
            const distPct = ((ind.price! - ema.value) / ema.value) * 100;
            return <span key={ema.label} className={clsx("font-mono", distPct > 0 ? "text-accent-green" : "text-accent-red")}>
              {ema.label}: {distPct >= 0 ? "+" : ""}{distPct.toFixed(1)}%
            </span>;
          })}
        </div>
      )}

      {symbol.reasoning && (
        <div className="rounded-lg border border-surface-border bg-surface-elevated">
          <button
            onClick={() => setShowReasoning(!showReasoning)}
            className="flex w-full items-center justify-between p-3 text-[10px] text-accent-blue hover:bg-surface-card/50 transition-colors rounded-lg"
          >
            <span className="flex items-center gap-1.5"><BarChart3 className="h-3.5 w-3.5" />LLM Analysis Reasoning</span>
            <ChevronDown className={clsx("h-3 w-3 transition-transform", showReasoning && "rotate-180")} />
          </button>
          {showReasoning && (
            <div className="px-3 pb-3">
              <pre className="whitespace-pre-wrap font-sans text-xs text-text-secondary leading-relaxed">{symbol.reasoning}</pre>
            </div>
          )}
        </div>
      )}

      {symbol.fundamentals && <FundamentalHealthCard fundamentals={symbol.fundamentals} />}
    </div>
  );
}

// ─── Pillar Gauge ─────────────────────────────────────────────────────────

function PillarGauge({ label, score, detail }: { label: string; score: number | null; detail: string }) {
  const pct = score != null ? ((score + 2) / 4) * 100 : 0;

  return (
    <div className={clsx(
      "rounded-lg border p-3",
      score != null && score > 0 ? "border-accent-green/30 bg-accent-green/5" :
      score != null && score === 0 ? "border-accent-yellow/30 bg-accent-yellow/5" :
      score != null ? "border-accent-red/30 bg-accent-red/5" :
      "border-surface-border bg-surface-elevated"
    )}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold text-text-secondary">{label}</span>
        <span className={clsx("text-sm font-mono font-bold",
          score != null && score > 0 ? "text-accent-green" :
          score != null && score === 0 ? "text-accent-yellow" :
          "text-accent-red"
        )}>
          {score != null ? `${score >= 0 ? "+" : ""}${score}` : "?"}
        </span>
      </div>
      <div className="relative h-4 rounded-full bg-surface-border overflow-hidden mb-1.5">
        <div className="absolute inset-y-0 left-0 bg-accent-red/20" style={{ width: "25%" }} />
        <div className="absolute inset-y-0 bg-accent-yellow/10" style={{ left: "25%", width: "25%" }} />
        <div className="absolute inset-y-0 bg-accent-green/15" style={{ left: "75%", width: "25%" }} />
        <div className={clsx("absolute top-1/2 -translate-y-1/2 h-3 w-1.5 rounded-sm",
          score != null && score > 0 ? "bg-accent-green" :
          score != null && score === 0 ? "bg-accent-yellow" :
          "bg-accent-red"
        )} style={{ left: `${Math.max(2, Math.min(98, pct))}%` }} />
      </div>
      <p className="text-[10px] text-text-muted leading-tight">{detail}</p>
    </div>
  );
}

// ─── Indicator Pill ───────────────────────────────────────────────────────

function IndicatorPill({ label, value, status }: { label: string; value: string; status?: "bullish" | "bearish" | "overbought" | "oversold" | "neutral" }) {
  return (
    <span className={clsx(
      "inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-mono",
      status === "bullish" || status === "oversold" ? "bg-accent-green/10 text-accent-green" :
      status === "bearish" || status === "overbought" ? "bg-accent-red/10 text-accent-red" :
      "bg-surface-elevated text-text-secondary"
    )}>
      <span className="text-text-muted">{label}:</span>
      {value}
    </span>
  );
}

// ─── Fundamental Health Card ──────────────────────────────────────────────

function FundamentalHealthCard({ fundamentals }: { fundamentals: NonNullable<SymbolResult["fundamentals"]> }) {
  const f = fundamentals;
  const labelColor =
    f.health_label === "HEALTHY" ? "text-accent-green border-accent-green/30" :
    f.health_label === "CAUTION" ? "text-accent-yellow border-accent-yellow/30" :
    "text-accent-red border-accent-red/30";

  return (
    <div className="rounded-lg border border-surface-border bg-surface-elevated p-3">
      <span className="text-[10px] text-text-muted uppercase tracking-wide">Fundamental Health</span>
      <div className="flex items-center gap-2 mt-1 mb-2">
        <span className={clsx("rounded border px-2 py-0.5 text-xs font-semibold", labelColor)}>
          {f.health_label}
        </span>
        <span className="text-xs text-text-muted">{f.health_score}/5 checks passed</span>
      </div>
      <div className="flex flex-wrap gap-1.5 text-[10px]">
        {f.trailing_pe != null && (
          <span className={clsx("rounded px-1.5 py-0.5 font-mono",
            f.trailing_pe > 0 && f.trailing_pe < 50 ? "bg-accent-green/10 text-accent-green" : "bg-accent-red/10 text-accent-red"
          )}>P/E: {f.trailing_pe.toFixed(1)}</span>
        )}
        {f.debt_to_equity != null && (
          <span className={clsx("rounded px-1.5 py-0.5 font-mono",
            f.debt_to_equity < 1.0 ? "bg-accent-green/10 text-accent-green" :
            f.debt_to_equity < 2.0 ? "bg-accent-yellow/10 text-accent-yellow" : "bg-accent-red/10 text-accent-red"
          )}>D/E: {(f.debt_to_equity * 100).toFixed(0)}%</span>
        )}
        {f.current_ratio != null && (
          <span className={clsx("rounded px-1.5 py-0.5 font-mono",
            f.current_ratio > 1.5 ? "bg-accent-green/10 text-accent-green" :
            f.current_ratio >= 1.0 ? "bg-accent-yellow/10 text-accent-yellow" : "bg-accent-red/10 text-accent-red"
          )}>CR: {f.current_ratio.toFixed(1)}</span>
        )}
        {f.return_on_equity != null && (
          <span className={clsx("rounded px-1.5 py-0.5 font-mono",
            f.return_on_equity > 0.10 ? "bg-accent-green/10 text-accent-green" :
            f.return_on_equity > 0 ? "bg-accent-yellow/10 text-accent-yellow" : "bg-accent-red/10 text-accent-red"
          )}>ROE: {(f.return_on_equity * 100).toFixed(0)}%</span>
        )}
        {f.profit_margins != null && (
          <span className={clsx("rounded px-1.5 py-0.5 font-mono",
            f.profit_margins > 0.05 ? "bg-accent-green/10 text-accent-green" :
            f.profit_margins > 0 ? "bg-accent-yellow/10 text-accent-yellow" : "bg-accent-red/10 text-accent-red"
          )}>Margin: {(f.profit_margins * 100).toFixed(0)}%</span>
        )}
      </div>
      {f.flags && f.flags.length > 0 && (
        <div className="mt-1.5 space-y-0.5">
          {f.flags.filter(fl => fl.status !== "pass").map((fl, i) => (
            <div key={i} className={clsx(
              "text-[10px] flex items-start gap-1",
              fl.status === "fail" ? "text-accent-red" : "text-accent-yellow"
            )}>
              <span className="mt-0.5">{fl.status === "fail" ? "✕" : "△"}</span>
              <span className="leading-snug">{fl.note}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
