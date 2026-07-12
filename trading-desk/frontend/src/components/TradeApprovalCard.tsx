"use client";

import { useState } from "react";
import { useTradingStore } from "@/store";
import type { Trade } from "@/store/types";
import {
  ChevronDown,
  ChevronUp,
  Check,
  X,
  TrendingUp,
  TrendingDown,
  Loader2,
  BarChart3,
  AlertTriangle,
  Target,
  Activity,
} from "lucide-react";
import clsx from "clsx";

// ─── Status badge ───────────────────────────────────────────────────

function StatusBadge({ status }: { status: Trade["status"] }) {
  const styles: Record<Trade["status"], string> = {
    PENDING: "bg-accent-yellow/10 text-accent-yellow border border-accent-yellow/30",
    APPROVED: "bg-accent-green/10 text-accent-green border border-accent-green/30",
    REJECTED: "bg-accent-red/10 text-accent-red border border-accent-red/30",
    EXECUTED: "bg-accent-blue/10 text-accent-blue border border-accent-blue/30",
    FAILED: "bg-accent-red/10 text-accent-red border border-accent-red/30",
    EXPIRED: "bg-text-muted/10 text-text-muted border border-text-muted/30",
  };

  return (
    <span className={clsx("badge", styles[status])}>{status}</span>
  );
}

// ─── Indicator Pill ────────────────────────────────────────────────

function IndicatorPill({
  label,
  value,
  good,
  bad,
}: {
  label: string;
  value: number | null;
  good?: boolean;
  bad?: boolean;
}) {
  const color = good
    ? "text-accent-green border-accent-green/30 bg-accent-green/5"
    : bad
      ? "text-accent-red border-accent-red/30 bg-accent-red/5"
      : "text-text-secondary border-surface-border bg-surface-elevated";

  return (
    <div
      className={clsx(
        "flex items-center gap-1.5 rounded border px-2 py-1",
        color,
      )}
      title={label}
    >
      <span className="text-xs text-text-muted">{label}</span>
      <span className="text-xs font-semibold font-mono">
        {value !== null ? value.toFixed(2) : "—"}
      </span>
    </div>
  );
}

// ─── Confidence Bar ────────────────────────────────────────────────

function ConfidenceBar({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(100, score * 100));
  const color =
    pct >= 70
      ? "bg-accent-green"
      : pct >= 40
        ? "bg-accent-yellow"
        : "bg-accent-red";

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-text-muted">Confidence</span>
      <div className="flex-1 h-1.5 rounded-full bg-surface-elevated overflow-hidden">
        <div
          className={clsx("h-full rounded-full transition-all duration-500", color)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs font-mono text-text-secondary">{pct}%</span>
    </div>
  );
}

// ─── Main Component ────────────────────────────────────────────────

interface TradeApprovalCardProps {
  trade: Trade;
}

export function TradeApprovalCard({ trade }: TradeApprovalCardProps) {
  const [reasoningOpen, setReasoningOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState<"approve" | "reject" | null>(null);

  const approveTrade = useTradingStore((s) => s.approveTrade);
  const rejectTrade = useTradingStore((s) => s.rejectTrade);

  const isPending = trade.status === "PENDING";
  const indicators = {
    rsi_2: trade.rsi_2_value,
    chop: trade.chop_value,
    sma_200: trade.sma_200_value,
  };

  const handleApprove = async () => {
    setActionLoading("approve");
    await approveTrade(trade.id);
    setActionLoading(null);
  };

  const handleReject = async () => {
    setActionLoading("reject");
    await rejectTrade(trade.id);
    setActionLoading(null);
  };

  return (
    <div className="card animate-fade-in space-y-3">
      {/* Header row */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <span className="rounded bg-accent-blue/10 px-2 py-0.5 font-mono text-sm font-semibold text-accent-blue">
            {trade.ticker}
          </span>
          <span className="text-sm text-text-muted">{trade.strategy}</span>
          <StatusBadge status={trade.status} />
        </div>
        {trade.decision === "BUY" ? (
          <TrendingUp className="h-5 w-5 text-accent-green" />
        ) : (
          <TrendingDown className="h-5 w-5 text-accent-red" />
        )}
      </div>

      {/* Price & Position */}
      <div className="flex flex-wrap gap-4 text-sm">
        {trade.proposed_price !== null && (
          <div>
            <span className="text-text-muted">Entry</span>
            <p className="font-mono font-semibold text-text-primary">
              ${trade.proposed_price.toFixed(2)}
            </p>
          </div>
        )}
        {trade.position_size_pct !== null && (
          <div>
            <span className="text-text-muted">Position</span>
            <p className="font-mono font-semibold text-text-primary">
              {trade.position_size_pct.toFixed(1)}%
            </p>
          </div>
        )}
        {trade.stop_loss !== null && (
          <div>
            <span className="text-text-muted">Stop Loss</span>
            <p className="font-mono font-semibold text-primary">
              ${trade.stop_loss.toFixed(2)}
            </p>
          </div>
        )}
        {trade.take_profit !== null && (
          <div>
            <span className="text-text-muted">Take Profit</span>
            <p className="font-mono font-semibold text-primary">
              ${trade.take_profit.toFixed(2)}
            </p>
          </div>
        )}
        {trade.risk_reward_ratio !== null && (
          <div className="flex items-center gap-1">
            <Target className="h-3.5 w-3.5 text-text-muted" />
            <span className="text-text-muted">R/R</span>
            <span className="font-mono font-semibold text-text-primary">
              {trade.risk_reward_ratio.toFixed(2)}
            </span>
          </div>
        )}
      </div>

      {/* Technical indicators */}
      <div className="flex flex-wrap gap-1.5">
        <IndicatorPill
          label="RSI-2"
          value={indicators.rsi_2}
          good={indicators.rsi_2 !== null && indicators.rsi_2 < 30}
          bad={indicators.rsi_2 !== null && indicators.rsi_2 > 70}
        />
        <IndicatorPill
          label="CHOP"
          value={indicators.chop}
          good={indicators.chop !== null && indicators.chop < 38}
          bad={indicators.chop !== null && indicators.chop > 62}
        />
        <IndicatorPill
          label="SMA200"
          value={indicators.sma_200}
          good={indicators.sma_200 !== null && trade.proposed_price !== null && trade.proposed_price > indicators.sma_200}
          bad={indicators.sma_200 !== null && trade.proposed_price !== null && trade.proposed_price <= indicators.sma_200}
        />
      </div>

      {/* Confidence bar */}
      {trade.confidence !== null && (
        <ConfidenceBar score={trade.confidence} />
      )}

      {/* LLM Reasoning */}
      {trade.reasoning && (
        <div>
          <button
            onClick={() => setReasoningOpen(!reasoningOpen)}
            className="flex w-full items-center justify-between rounded px-2 py-1.5 text-xs font-medium text-text-secondary hover:bg-surface-elevated transition-colors"
          >
            <span className="flex items-center gap-1.5">
              <BarChart3 className="h-3.5 w-3.5" />
              LLM Reasoning
            </span>
            {reasoningOpen ? (
              <ChevronUp className="h-3.5 w-3.5" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5" />
            )}
          </button>
          {reasoningOpen && (
            <div className="mt-1 rounded bg-surface-elevated p-3 text-xs leading-relaxed text-text-secondary animate-slide-in">
              <pre className="whitespace-pre-wrap font-sans">
                {trade.reasoning}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-2 pt-1">
        <button
          onClick={handleApprove}
          disabled={!isPending || actionLoading !== null}
          className={clsx(
            "flex flex-1 items-center justify-center gap-1.5 rounded-md py-2 text-sm font-semibold transition-all",
            isPending
              ? "bg-accent-green/10 text-accent-green hover:bg-accent-green/20 active:bg-accent-green/30"
              : "bg-surface-elevated text-text-muted cursor-not-allowed",
            actionLoading === "approve" && "opacity-60",
          )}
        >
          {actionLoading === "approve" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Check className="h-4 w-4" />
          )}
          Approve
        </button>
        <button
          onClick={handleReject}
          disabled={!isPending || actionLoading !== null}
          className={clsx(
            "flex flex-1 items-center justify-center gap-1.5 rounded-md py-2 text-sm font-semibold transition-all",
            isPending
              ? "bg-accent-red/10 text-accent-red hover:bg-accent-red/20 active:bg-accent-red/30"
              : "bg-surface-elevated text-text-muted cursor-not-allowed",
            actionLoading === "reject" && "opacity-60",
          )}
        >
          {actionLoading === "reject" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <X className="h-4 w-4" />
          )}
          Reject
        </button>
      </div>
    </div>
  );
}

// ─── Skeleton Loading ───────────────────────────────────────────────

export function TradeApprovalCardSkeleton() {
  return (
    <div className="card animate-pulse space-y-3">
      <div className="flex items-center gap-2">
        <div className="skeleton h-5 w-16 rounded" />
        <div className="skeleton h-4 w-24 rounded" />
        <div className="skeleton h-5 w-20 rounded-full" />
      </div>
      <div className="flex gap-4">
        <div className="skeleton h-10 w-20 rounded" />
        <div className="skeleton h-10 w-20 rounded" />
      </div>
      <div className="flex gap-1.5">
        <div className="skeleton h-6 w-20 rounded" />
        <div className="skeleton h-6 w-20 rounded" />
        <div className="skeleton h-6 w-24 rounded" />
      </div>
      <div className="skeleton h-3 w-full rounded-full" />
      <div className="skeleton h-8 w-full rounded" />
      <div className="flex gap-2">
        <div className="skeleton h-10 flex-1 rounded-md" />
        <div className="skeleton h-10 flex-1 rounded-md" />
      </div>
    </div>
  );
}

// ─── Empty State ────────────────────────────────────────────────────

export function TradeApprovalCardEmpty() {
  return (
    <div className="card flex flex-col items-center justify-center py-12 text-center animate-fade-in">
      <Activity className="mb-3 h-10 w-10 text-text-muted" />
      <p className="text-sm font-medium text-text-secondary">
        No pending trades
      </p>
      <p className="mt-1 text-xs text-text-muted">
        New trade signals will appear here for review.
      </p>
    </div>
  );
}

// ─── Error State ────────────────────────────────────────────────────

export function TradeApprovalCardError({ message }: { message: string }) {
  return (
    <div className="card flex flex-col items-center justify-center py-8 text-center animate-fade-in">
      <AlertTriangle className="mb-3 h-8 w-8 text-accent-red" />
      <p className="text-sm font-medium text-accent-red">Error</p>
      <p className="mt-1 text-xs text-text-muted">{message}</p>
    </div>
  );
}
