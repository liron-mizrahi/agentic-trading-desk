"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Check, X, TrendingUp, TrendingDown, BarChart3, Target, AlertTriangle, Info } from "lucide-react";
import clsx from "clsx";

interface AnalysisResult {
  ticker: string;
  analysis: {
    id: string; ticker: string;
    step1_passed: boolean | null;
    step2_passed: boolean | null;
    step3_passed: boolean | null;
    rsi2: number | null; chop: number | null;
    sma200: number | null; price: number | null;
    raw_llm_reasoning: string | null;
    llm_decision: string | null;
    llm_confidence: number | null;
    error_message: string | null;
    dead_letter: boolean; retry_count: number;
    created_at: string | null;
  };
  trade: Record<string, unknown> | null;
}

interface PipelineResultsCardProps { data: AnalysisResult | null; loading: boolean; error: string | null; }

function StepPill({ passed, label, detail }: { passed: boolean | null; label: string; detail?: string }) {
  if (passed === null) return <span className="flex items-center gap-1 text-xs text-text-muted">— {label}</span>;
  return (
    <span className={clsx("flex items-center gap-1 text-xs font-medium", passed ? "text-accent-green" : "text-accent-red")} title={detail}>
      {passed ? <Check className="h-3.5 w-3.5" /> : <X className="h-3.5 w-3.5" />}
      {label}
    </span>
  );
}

function ConfidenceBar({ score }: { score: number | null }) {
  if (score === null) return null;
  const pct = Math.max(0, Math.min(100, score * 100));
  const color = pct >= 70 ? "bg-accent-green" : pct >= 40 ? "bg-accent-yellow" : "bg-accent-red";
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-text-muted">Confidence</span>
      <div className="flex-1 h-1.5 rounded-full bg-surface-elevated overflow-hidden">
        <div className={clsx("h-full rounded-full transition-all", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-mono">{pct.toFixed(0)}%</span>
    </div>
  );
}

export function PipelineResultsCard({ data, loading, error }: PipelineResultsCardProps) {
  const [reasoningOpen, setReasoningOpen] = useState(false);

  if (loading) {
    return (
      <div className="card animate-pulse space-y-3">
        <div className="flex items-center gap-2"><div className="skeleton h-6 w-16 rounded" /><div className="skeleton h-4 w-32 rounded" /></div>
        <div className="space-y-1"><div className="skeleton h-4 w-48 rounded" /><div className="skeleton h-4 w-56 rounded" /><div className="skeleton h-4 w-40 rounded" /><div className="skeleton h-4 w-44 rounded" /><div className="skeleton h-4 w-36 rounded" /></div>
        <div className="skeleton h-3 w-full rounded-full" />
      </div>
    );
  }
  if (error) {
    return (
      <div className="card flex flex-col items-center justify-center py-8 text-center">
        <AlertTriangle className="mb-2 h-8 w-8 text-accent-red" />
        <p className="text-sm font-medium text-accent-red">Analysis Error</p>
        <p className="mt-1 text-xs text-text-muted">{error}</p>
      </div>
    );
  }
  if (!data) return null;

  const { analysis, trade } = data;
  const isBuy = analysis.llm_decision === "BUY" || (trade && (trade as any).decision === "BUY");
  const allFiltersPassed = analysis.step2_passed;
  const llmRun = analysis.step3_passed;

  return (
    <div className="card space-y-3 animate-fade-in">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <span className="rounded bg-accent-blue/10 px-2 py-0.5 font-mono text-sm font-semibold text-accent-blue">{data.ticker}</span>
          <span className={clsx("badge text-xs font-semibold", isBuy ? "bg-accent-green/10 text-accent-green border border-accent-green/30" : "bg-text-muted/10 text-text-muted border border-text-muted/30")}>
            {isBuy ? "BUY" : "NO TRADE"}
          </span>
          {analysis.dead_letter && <span className="badge bg-accent-red/10 text-accent-red border border-accent-red/30 text-xs">DEAD LETTER</span>}
        </div>
        {isBuy ? <TrendingUp className="h-5 w-5 text-accent-green" /> : <TrendingDown className="h-5 w-5 text-text-muted" />}
      </div>

      {/* Pipeline Steps — full cascade */}
      <div>
        <p className="text-xs font-semibold text-text-secondary uppercase tracking-wide mb-1.5">Pipeline</p>
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <StepPill passed={analysis.step1_passed} label="Data Fetch" detail="OHLCV from IBKR → yfinance" />
            <span className="text-xs text-text-muted">5yr daily bars</span>
          </div>
          <div className="flex items-center gap-2">
            <StepPill passed={analysis.step2_passed} label="Filter Cascade" detail="RSI-2 oversold · CHOP trending · SMA200 uptrend" />
            <span className="text-xs text-text-muted">
              {analysis.step2_passed ? "All 3 checks passed" : "One or more filters failed — see indicators below"}
            </span>
          </div>
          <div className="flex items-center gap-2 ml-4">
            <StepPill 
              passed={analysis.rsi2 !== null && analysis.rsi2 < 10 ? true : analysis.rsi2 !== null ? false : null} 
              label={`RSI-2 (thresh <${analysis.rsi2 !== null && analysis.rsi2 < 10 ? "10" : "10"})`} 
              detail="Sector-adapted: Technology = <10 oversold"
            />
            <span className="text-xs text-text-muted font-mono">{analysis.rsi2?.toFixed(2)}</span>
          </div>
          <div className="flex items-center gap-2 ml-4">
            <StepPill 
              passed={analysis.chop === null ? null : analysis.chop < 38.2} 
              label="CHOP (< 38.2)"
              detail="Choppiness Index: <38.2 = trending, >61.8 = choppy"
            />
            <span className="text-xs text-text-muted font-mono">{analysis.chop?.toFixed(2)}</span>
          </div>
          <div className="flex items-center gap-2 ml-4">
            <StepPill 
              passed={analysis.sma200 === null || analysis.price === null ? null : analysis.price > analysis.sma200} 
              label="Price > SMA200"
              detail="Uptrend confirmation"
            />
            <span className="text-xs text-text-muted font-mono">
              ${analysis.price?.toFixed(2)} vs ${analysis.sma200?.toFixed(2)}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <StepPill 
              passed={analysis.step3_passed} 
              label="LLM Analysis" 
              detail={allFiltersPassed ? "DeepSeek structured output" : "Skipped — filters didn't pass"}
            />
            <span className="text-xs text-text-muted">
              {!allFiltersPassed ? "(skipped — cascade failed)" : analysis.step3_passed ? "Complete" : "Failed"}
            </span>
          </div>
        </div>
      </div>

      {/* Error message */}
      {analysis.error_message && (
        <div className="flex items-start gap-1.5 rounded bg-accent-red/5 border border-accent-red/20 p-2">
          <AlertTriangle className="h-3.5 w-3.5 text-accent-red mt-0.5 shrink-0" />
          <span className="text-xs text-accent-red">{analysis.error_message}</span>
        </div>
      )}

      {/* Indicator Values */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <IndicatorVal label="RSI-14" value={analysis.rsi2} warnBelow={30} warnAbove={70} />
        <IndicatorVal label="CHOP" value={analysis.chop} warnAbove={62} />
        <IndicatorVal label="SMA 200" value={analysis.sma200} prefix="$" />
        <IndicatorVal label="Price" value={analysis.price} prefix="$" />
      </div>

      {/* Confidence */}
      {analysis.llm_confidence !== null && <ConfidenceBar score={analysis.llm_confidence} />}

      {/* Trade details (if BUY) */}
      {trade && isBuy && (
        <div className="rounded bg-surface-elevated p-3 space-y-2">
          <p className="text-xs font-semibold text-text-secondary uppercase tracking-wide">Trade Proposal</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            <div><span className="text-text-muted">Entry</span><p className="font-mono font-semibold text-text-primary">${(trade as any).proposed_price?.toFixed(2)}</p></div>
            <div><span className="text-text-muted">Stop Loss</span><p className="font-mono font-semibold text-accent-red">${(trade as any).stop_loss?.toFixed(2)}</p></div>
            <div><span className="text-text-muted">Take Profit</span><p className="font-mono font-semibold text-accent-green">${(trade as any).take_profit?.toFixed(2)}</p></div>
            <div className="flex items-center gap-1"><Target className="h-3 w-3 text-text-muted" /><span className="text-text-muted">R/R</span><p className="font-mono font-semibold text-text-primary">{(trade as any).risk_reward_ratio?.toFixed(2)}</p></div>
          </div>
          <div className="text-xs"><span className="text-text-muted">Position: </span><span className="font-mono font-semibold">{(trade as any).position_size_pct?.toFixed(1)}%</span></div>
          <div className="text-xs"><span className="text-text-muted">Exit: </span><span className="text-text-secondary">{(trade as any).exit_condition}</span></div>
        </div>
      )}

      {/* No-trade explanation */}
      {!isBuy && !allFiltersPassed && (
        <div className="rounded bg-surface-elevated border border-surface-border p-3 flex items-start gap-2">
          <Info className="h-4 w-4 text-accent-yellow shrink-0 mt-0.5" />
          <div className="text-xs text-text-secondary">
            <p className="font-medium text-text-primary mb-1">No Entry Signal</p>
            <p>The filter cascade blocked this ticker — it's not in a Momentum-Dip oversold setup. This is the strategy working correctly: it only enters when conditions align. Try a ticker in a sharp sell-off for a potential BUY signal.</p>
          </div>
        </div>
      )}

      {/* LLM Reasoning */}
      {analysis.raw_llm_reasoning && (
        <div>
          <button onClick={() => setReasoningOpen(!reasoningOpen)} className="flex w-full items-center justify-between rounded px-2 py-1.5 text-xs font-medium text-text-secondary hover:bg-surface-elevated transition-colors">
            <span className="flex items-center gap-1.5"><BarChart3 className="h-3.5 w-3.5" />LLM Reasoning</span>
            {reasoningOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>
          {reasoningOpen && <div className="mt-1 rounded bg-surface-elevated p-3 text-xs leading-relaxed text-text-secondary animate-slide-in"><pre className="whitespace-pre-wrap font-sans">{analysis.raw_llm_reasoning}</pre></div>}
        </div>
      )}
    </div>
  );
}

function IndicatorVal({ label, value, prefix = "", suffix = "", warnBelow, warnAbove }: { label: string; value: number | null; prefix?: string; suffix?: string; warnBelow?: number; warnAbove?: number }) {
  const warn = (warnBelow !== undefined && value !== null && value < warnBelow) || (warnAbove !== undefined && value !== null && value > warnAbove);
  return (
    <div className={clsx("rounded border px-2 py-1.5", warn ? "border-accent-red/30 bg-accent-red/5" : "border-surface-border bg-surface-elevated")}>
      <p className="text-xs text-text-muted">{label}</p>
      <p className={clsx("text-sm font-mono font-semibold", warn ? "text-accent-red" : "text-text-primary")}>{value !== null ? `${prefix}${value.toFixed(2)}${suffix}` : "—"}</p>
    </div>
  );
}
