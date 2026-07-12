"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { createChart, type IChartApi, type Time, ColorType } from "lightweight-charts";
import { BarChart3, Eye, EyeOff, Loader2 } from "lucide-react";
import clsx from "clsx";

// ─── Data Fetch ──────────────────────────────────────────────────────────

interface OHLCV { time: string; open: number; high: number; low: number; close: number; volume: number; }

async function fetchOHLCV(ticker: string): Promise<OHLCV[]> {
  const res = await fetch(`/api/v1/data/${ticker}/ohlcv?period=1y`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const json = await res.json();
  return json.data as OHLCV[];
}

// ─── Indicators (pure functions) ────────────────────────────────────────

function SMA(v: number[], p: number): (number | null)[] {
  const r: (number | null)[] = [];
  for (let i = 0; i < v.length; i++) {
    if (i < p - 1) { r.push(null); continue; }
    let s = 0; for (let j = i - p + 1; j <= i; j++) s += v[j];
    r.push(+(s / p).toFixed(4));
  }
  return r;
}

function BB(v: number[], period: number, multiplier: number) {
  const mid = SMA(v, period);
  const up: (number | null)[] = [], lo: (number | null)[] = [];
  for (let i = 0; i < v.length; i++) {
    if (mid[i] === null) { up.push(null); lo.push(null); }
    else {
      let ss = 0; const st = i - period + 1;
      for (let j = st; j <= i; j++) ss += (v[j] - mid[i]!) ** 2;
      const sd = Math.sqrt(ss / period);
      up.push(+(mid[i]! + multiplier * sd).toFixed(4));
      lo.push(+(mid[i]! - multiplier * sd).toFixed(4));
    }
  }
  return { upper: up, middle: mid, lower: lo };
}

// ─── Config ─────────────────────────────────────────────────────────────

const BG = "#161b22", GRID_C = "#21262d", TXT = "#8b949e", BDR = "#30363d";
const LAY = { background: { type: ColorType.Solid, color: BG }, textColor: TXT, fontSize: 10, fontFamily: "JetBrains Mono, monospace" };
const G = { vertLines: { color: GRID_C }, horzLines: { color: GRID_C } };
const CH = { mode: 0 as const, vertLine: { color: "#484f58", style: 2 as const, width: 1 as const, labelBackgroundColor: "#30363d", labelVisible: false }, horzLine: { color: "#484f58", style: 2 as const, width: 1 as const, labelBackgroundColor: "#30363d", labelVisible: false } };
const TS = { borderColor: BDR, timeVisible: false, rightOffset: 5 };

// ─── Component ──────────────────────────────────────────────────────────

interface StrategyChartProps {
  ticker: string;
  height?: number;
  /** Show volume histogram below candlesticks */
  showVolume?: boolean;
}

export function StrategyChart({ ticker, height = 320, showVolume = true }: StrategyChartProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);

  // Toggle refs
  const sma20 = useRef<any>(null);
  const sma50 = useRef<any>(null);
  const sma200 = useRef<any>(null);
  const bbU = useRef<any>(null);
  const bbL = useRef<any>(null);
  const bbM = useRef<any>(null);
  const volS = useRef<any>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showSMA20, setShowSMA20] = useState(false);
  const [showSMA50, setShowSMA50] = useState(true);
  const [showSMA200, setShowSMA200] = useState(true);
  const [showBB, setShowBB] = useState(true);
  const [showVol, setShowVol] = useState(showVolume);

  const build = useCallback(async () => {
    const el = chartRef.current;
    if (!el) return;
    chart.current?.remove();
    chart.current = null;
    setLoading(true);
    setError(null);

    try {
      const data = await fetchOHLCV(ticker);
      if (data.length < 20) { setError("Not enough data"); setLoading(false); return; }

      const closes = data.map((d) => d.close);
      const times = data.map((d) => d.time as Time);

      // Compute indicators
      const s20 = SMA(closes, 20);
      const s50 = SMA(closes, 50);
      const s200 = SMA(closes, 200);
      const bb = BB(closes, 20, 2);

      const w = el.clientWidth || 600;
      const c = createChart(el, { layout: LAY, grid: G, crosshair: CH, timeScale: TS, rightPriceScale: { borderColor: BDR, autoScale: true }, autoSize: true, width: w, height });
      chart.current = c;

      // Candlesticks
      const candleSeries = c.addCandlestickSeries({
        upColor: "#00c853", downColor: "#ff1744",
        borderUpColor: "#00c853", borderDownColor: "#ff1744",
        wickUpColor: "#00c853", wickDownColor: "#ff1744",
        lastValueVisible: false, priceLineVisible: false,
      });
      candleSeries.setData(data.map((d) => ({ time: d.time as Time, open: d.open, high: d.high, low: d.low, close: d.close })));

      const mkLine = (vals: (number | null)[], color: string, lw: number = 1) => {
        const s = c.addLineSeries({ color, lineWidth: lw as any, priceLineVisible: false, lastValueVisible: false });
        s.setData(vals.map((v, i) => (v !== null ? { time: times[i], value: v } : null)).filter(Boolean) as any);
        return s;
      };

      sma20.current = mkLine(s20, "#ffab40", 1);
      sma50.current = mkLine(s50, "#ff6e40", 1);
      sma200.current = mkLine(s200, "#2979ff", 2);
      bbU.current = mkLine(bb.upper, "rgba(156,39,176,0.5)", 1);
      bbM.current = mkLine(bb.middle, "rgba(156,39,176,0.3)", 1);
      bbL.current = mkLine(bb.lower, "rgba(156,39,176,0.5)", 1);

      // Volume overlay
      if (showVol) {
        volS.current = c.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "volume", lastValueVisible: false, priceLineVisible: false });
        c.priceScale("volume").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 }, visible: false });
        volS.current.setData(data.map((d) => {
          const isUp = d.close >= d.open;
          return { time: d.time as Time, value: d.volume, color: isUp ? "rgba(0,200,83,0.3)" : "rgba(255,23,68,0.3)" };
        }));
      }

      // Apply toggle visibility
      sma20.current?.applyOptions({ visible: showSMA20 });
      sma50.current?.applyOptions({ visible: showSMA50 });
      sma200.current?.applyOptions({ visible: showSMA200 });
      bbU.current?.applyOptions({ visible: showBB });
      bbM.current?.applyOptions({ visible: showBB });
      bbL.current?.applyOptions({ visible: showBB });

      c.timeScale().fitContent();
      setLoading(false);
    } catch (e: any) {
      setError(e.message || "Chart error");
      setLoading(false);
    }
  }, [ticker, height, showSMA20, showSMA50, showSMA200, showBB, showVol]);

  useEffect(() => { build(); }, [build]);

  useEffect(() => {
    sma20.current?.applyOptions({ visible: showSMA20 });
  }, [showSMA20]);
  useEffect(() => {
    sma50.current?.applyOptions({ visible: showSMA50 });
  }, [showSMA50]);
  useEffect(() => {
    sma200.current?.applyOptions({ visible: showSMA200 });
  }, [showSMA200]);
  useEffect(() => {
    bbU.current?.applyOptions({ visible: showBB });
    bbM.current?.applyOptions({ visible: showBB });
    bbL.current?.applyOptions({ visible: showBB });
  }, [showBB]);

  function TBtn({ label, color, active, onClick }: { label: string; color: string; active: boolean; onClick: () => void }) {
    return (
      <button onClick={onClick} className={clsx("flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium transition-colors border",
        active ? "border-opacity-30 bg-opacity-10" : "border-transparent bg-surface-elevated text-text-muted hover:text-text-secondary"
      )} style={active ? { borderColor: color, backgroundColor: color + "18", color } : undefined}>
        <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ backgroundColor: active ? color : "#484f58" }} />
        {active ? <Eye className="h-2.5 w-2.5" /> : <EyeOff className="h-2.5 w-2.5" />}
        {label}
      </button>
    );
  }

  return (
    <div className="rounded-lg border border-surface-border bg-surface-card p-3">
      <div className="flex items-center justify-between mb-2 flex-wrap gap-1">
        <span className="flex items-center gap-1.5 text-[10px] font-semibold text-text-secondary">
          <BarChart3 className="h-3 w-3 text-accent-blue" />
          {ticker} — 1Y Daily
        </span>
        <div className="flex items-center gap-1 flex-wrap">
          <TBtn label="SMA20" color="#ffab40" active={showSMA20} onClick={() => setShowSMA20(!showSMA20)} />
          <TBtn label="SMA50" color="#ff6e40" active={showSMA50} onClick={() => setShowSMA50(!showSMA50)} />
          <TBtn label="SMA200" color="#2979ff" active={showSMA200} onClick={() => setShowSMA200(!showSMA200)} />
          <TBtn label="BB(20,2)" color="#9c27b0" active={showBB} onClick={() => setShowBB(!showBB)} />
          <TBtn label="Vol" color="#8b949e" active={showVol} onClick={() => setShowVol(!showVol)} />
        </div>
      </div>
      <div style={{ position: "relative", height }}>
        <div ref={chartRef} className="tv-chart-container" />
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-[#161b22]/80 z-10">
            <Loader2 className="h-5 w-5 animate-spin text-text-muted" />
          </div>
        )}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center bg-[#161b22]/90 z-10">
            <p className="text-xs text-accent-red">{error}</p>
          </div>
        )}
      </div>
    </div>
  );
}
