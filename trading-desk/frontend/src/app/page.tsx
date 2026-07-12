"use client";

import { useEffect, useState, useCallback } from "react";
import dynamic from "next/dynamic";
import { useTradingStore } from "@/store";
import { useWebSocket } from "@/hooks/useWebSocket";
import { LiveTickerTape, EventLogOverlay } from "@/components/LiveTickerTape";
import { TradeApprovalCard, TradeApprovalCardSkeleton, TradeApprovalCardEmpty, TradeApprovalCardError } from "@/components/TradeApprovalCard";
import { ChartWidgetSkeleton } from "@/components/ChartWidget";
import { PipelineResultsCard } from "@/components/PipelineResultsCard";
import { Activity, Search, RefreshCw, AlertTriangle, Shield, ServerCrash, BarChart3 } from "lucide-react";

// Lazy-load chart — lightweight-charts is ~200KB gzipped, keep it out of page.js
const ChartWidget = dynamic(
  () => import("@/components/ChartWidget").then((mod) => mod.ChartWidget),
  { ssr: false, loading: () => <ChartWidgetSkeleton height={550} /> }
);

export default function WarRoomPage() {
  const [eventLogOpen, setEventLogOpen] = useState(false);
  const [tickerInput, setTickerInput] = useState("");
  const [chartTicker, setChartTicker] = useState<string | null>("SPY");

  const trades = useTradingStore((s) => s.trades);
  const pendingTrades = useTradingStore((s) => s.pendingTrades);
  const events = useTradingStore((s) => s.events);
  const wsStatus = useTradingStore((s) => s.wsStatus);
  const loading = useTradingStore((s) => s.loading);
  const error = useTradingStore((s) => s.error);
  const fetchPendingTrades = useTradingStore((s) => s.fetchPendingTrades);
  const analyzeTicker = useTradingStore((s) => s.analyzeTicker);
  const clearError = useTradingStore((s) => s.clearError);

  // Pipeline results
  const activeTicker = useTradingStore((s) => s.activeTicker);
  const analysisResult = useTradingStore((s) => s.analysisResult);
  const analysisLoading = useTradingStore((s) => s.analysisLoading);
  const analysisError = useTradingStore((s) => s.analysisError);

  useWebSocket();

  useEffect(() => { fetchPendingTrades(); }, [fetchPendingTrades]);

  const handleAnalyze = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    const ticker = tickerInput.trim().toUpperCase();
    if (!ticker) return;
    analyzeTicker(ticker);
    setChartTicker(ticker);
    setTickerInput("");
  }, [tickerInput, analyzeTicker]);

  const handleRefresh = useCallback(() => { fetchPendingTrades(); }, [fetchPendingTrades]);

  const approvedCount = trades.filter((t) => t.status === "APPROVED").length;
  const rejectedCount = trades.filter((t) => t.status === "REJECTED").length;
  const warningCount = events.filter((e) => e.event === "SYSTEM_WARNING").length;

  return (
    <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 lg:px-8">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-blue/10"><Activity className="h-5 w-5 text-accent-blue" /></div>
          <div><h1 className="text-lg font-bold text-text-primary">AI Trading Desk</h1><p className="text-xs text-text-muted">War Room</p></div>
        </div>
        <div className="flex items-center gap-3">
          <span className={`inline-block h-2 w-2 rounded-full ${wsStatus === "connected" ? "bg-accent-green shadow-[0_0_6px_rgba(0,200,83,0.5)]" : wsStatus === "connecting" ? "bg-accent-yellow animate-pulse-dot" : "bg-accent-red"}`} />
          <span className="text-xs text-text-muted">{wsStatus === "connected" ? "System Live" : wsStatus === "connecting" ? "Connecting…" : "Offline"}</span>
          <button onClick={handleRefresh} disabled={loading} className="rounded-md bg-surface-elevated p-2 text-text-muted hover:bg-surface-border hover:text-text-primary transition-colors disabled:opacity-50" title="Refresh"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /></button>
        </div>
      </header>

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard icon={<Activity className="h-4 w-4" />} label="Pending" value={pendingTrades().length} color="text-accent-yellow" />
        <StatCard icon={<Shield className="h-4 w-4" />} label="Approved" value={approvedCount} color="text-accent-green" />
        <StatCard icon={<ServerCrash className="h-4 w-4" />} label="Rejected" value={rejectedCount} color="text-accent-red" />
        <StatCard icon={<AlertTriangle className="h-4 w-4" />} label="Warnings" value={warningCount} color={warningCount > 0 ? "text-accent-yellow" : "text-text-muted"} />
      </div>

      {error && <div className="mb-4 flex items-center gap-2 rounded-lg border border-accent-red/30 bg-accent-red/5 px-4 py-2 text-sm"><AlertTriangle className="h-4 w-4 text-accent-red shrink-0" /><span className="flex-1 text-accent-red">{error}</span><button onClick={clearError} className="rounded p-1 text-accent-red/60 hover:bg-accent-red/10">✕</button></div>}

      <form onSubmit={handleAnalyze} className="mb-4 flex gap-2">
        <div className="relative flex-1"><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" /><input type="text" value={tickerInput} onChange={(e) => setTickerInput(e.target.value.toUpperCase())} placeholder="Enter ticker to analyze (e.g. AAPL)" className="w-full rounded-lg border border-surface-border bg-surface-card py-2.5 pl-10 pr-4 text-sm text-text-primary placeholder-text-muted outline-none focus:border-accent-blue/50 focus:ring-1 focus:ring-accent-blue/20 transition-colors" maxLength={10} /></div>
        <button type="submit" disabled={!tickerInput.trim() || loading} className="rounded-lg bg-accent-blue/10 px-5 py-2.5 text-sm font-semibold text-accent-blue hover:bg-accent-blue/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">{analysisLoading ? <RefreshCw className="h-4 w-4 animate-spin" /> : "Analyze"}</button>
      </form>

      <div className="mb-4"><LiveTickerTape onToggleLog={() => setEventLogOpen(true)} /></div>
      <EventLogOverlay open={eventLogOpen} onClose={() => setEventLogOpen(false)} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-1 space-y-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-text-primary"><Activity className="h-4 w-4 text-accent-yellow" />Pending Trades{pendingTrades().length > 0 && <span className="badge bg-accent-yellow/10 text-accent-yellow">{pendingTrades().length}</span>}</h2>
          {loading && pendingTrades().length === 0 && <div className="space-y-3"><TradeApprovalCardSkeleton /><TradeApprovalCardSkeleton /></div>}
          {!loading && error && pendingTrades().length === 0 && <TradeApprovalCardError message={error} />}
          {!loading && !error && pendingTrades().length === 0 && <TradeApprovalCardEmpty />}
          {pendingTrades().map((trade, idx) => <div key={trade.id} style={{ animationDelay: `${idx * 80}ms` }}><TradeApprovalCard trade={trade} /></div>)}

          {/* Pipeline Results Card — shown after analysis */}
          {activeTicker && (
            <div className="mt-4">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-text-primary mb-2"><BarChart3 className="h-4 w-4 text-accent-blue" />Pipeline — {activeTicker}</h2>
              <PipelineResultsCard data={analysisResult} loading={analysisLoading} error={analysisError} />
            </div>
          )}
        </div>

        <div className="lg:col-span-2 space-y-3">
          {chartTicker ? <ChartWidget key={chartTicker} ticker={chartTicker} height={550} /> : <ChartWidgetSkeleton height={550} />}
          <div className="flex flex-wrap gap-2">
            {["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA"].map((t) => (
              <button key={t} onClick={() => { setChartTicker(t); fetch(`/api/v1/data/${t}/ohlcv?period=5y`).catch(() => {}); }} className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${chartTicker === t ? "bg-accent-blue/15 text-accent-blue border border-accent-blue/30" : "bg-surface-elevated text-text-secondary border border-surface-border hover:bg-surface-border hover:text-text-primary"}`}>{t}</button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: number; color: string }) {
  return <div className="card flex items-center gap-3 py-3"><div className={color}>{icon}</div><div><p className="text-xs text-text-muted">{label}</p><p className={`text-lg font-bold font-mono ${color}`}>{value}</p></div></div>;
}
