"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { createChart, type IChartApi, type ISeriesApi, ColorType, type Time, type LineWidth } from "lightweight-charts";
import { Loader2, AlertTriangle, BarChart3, Eye, EyeOff } from "lucide-react";
import clsx from "clsx";

// ─── Types ─────────────────────────────────────────────────────────────

interface OHLCV { time: string; open: number; high: number; low: number; close: number; volume: number; }

async function fetchOHLCV(ticker: string): Promise<OHLCV[]> {
  const res = await fetch(`/api/v1/data/${ticker}/ohlcv?period=5y`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const json = await res.json();
  return json.data as OHLCV[];
}

// ─── Indicators ────────────────────────────────────────────────────────

function SMA(v: number[], p: number): (number | null)[] { const r: (number | null)[] = []; for (let i = 0; i < v.length; i++) { if (i < p - 1) r.push(null); else { let s = 0; for (let j = i - p + 1; j <= i; j++) s += v[j]; r.push(+(s / p).toFixed(4)); } } return r; }
function EMA(v: number[], p: number): (number | null)[] { const r: (number | null)[] = []; const k = 2 / (p + 1); for (let i = 0; i < v.length; i++) { if (i === 0) r.push(v[0]); else if (i < p - 1) r.push(null); else { const prev = r[i - 1] ?? v[i - 1]; r.push(+(v[i] * k + prev * (1 - k)).toFixed(4)); } } return r; }

function BB(v: number[], p: number, m: number) { const mid = SMA(v, p); const up: (number | null)[] = [], lo: (number | null)[] = []; for (let i = 0; i < v.length; i++) { if (mid[i] === null) { up.push(null); lo.push(null); } else { let ss = 0; const st = i - p + 1; for (let j = st; j <= i; j++) ss += (v[j] - mid[i]!) ** 2; const sd = Math.sqrt(ss / p); up.push(+(mid[i]! + m * sd).toFixed(4)); lo.push(+(mid[i]! - m * sd).toFixed(4)); } } return { upper: up, middle: mid, lower: lo }; }

function RSI(v: number[], p: number): (number | null)[] { const r: (number | null)[] = []; let ag = 0, al = 0; for (let i = 0; i < v.length; i++) { if (i < p) r.push(null); else if (i === p) { let g = 0, l = 0; for (let j = 1; j <= p; j++) { const d = v[j] - v[j - 1]; if (d >= 0) g += d; else l -= d; } ag = g / p; al = l / p; r.push(al === 0 ? 100 : +(100 - 100 / (1 + ag / al)).toFixed(2)); } else { const d = v[i] - v[i - 1]; ag = (ag * (p - 1) + (d >= 0 ? d : 0)) / p; al = (al * (p - 1) + (d < 0 ? -d : 0)) / p; r.push(al === 0 ? 100 : +(100 - 100 / (1 + ag / al)).toFixed(2)); } } return r; }

function MACD(v: number[]) { const e12 = EMA(v, 12), e26 = EMA(v, 26); const line: (number | null)[] = []; for (let i = 0; i < v.length; i++) { if (e12[i] !== null && e26[i] !== null) line.push(+(e12[i]! - e26[i]!).toFixed(4)); else line.push(null); } const sigVals = line.filter((x): x is number => x !== null); const sigRaw = EMA(sigVals, 9); const sig: (number | null)[] = []; let si = 0; let nullCount = 0; for (let i = 0; i < line.length; i++) { if (line[i] === null) { sig.push(null); nullCount++; } else { sig.push(sigRaw[si] ?? sigRaw[sigRaw.length - 1]); si++; } } const hist = line.map((l, i) => (l !== null && sig[i] !== null ? +(l - sig[i]!).toFixed(4) : null)); return { line, signal: sig, histogram: hist }; }

// ─── Colors / Layout ───────────────────────────────────────────────────

const BG = "#161b22", GRID_C = "#21262d", TXT = "#8b949e", BDR = "#30363d";
const LAY = { background: { type: ColorType.Solid, color: BG }, textColor: TXT, fontSize: 11, fontFamily: "JetBrains Mono, monospace" };
const G = { vertLines: { color: GRID_C }, horzLines: { color: GRID_C } };
const CH = { mode: 0 as const, vertLine: { color: "#484f58", style: 2 as const, width: 1 as const, labelBackgroundColor: "#30363d", labelVisible: false }, horzLine: { color: "#484f58", style: 2 as const, width: 1 as const, labelBackgroundColor: "#30363d", labelVisible: false } };
const TS = { borderColor: BDR, timeVisible: false };

function syncTS(charts: IChartApi[]) { const subs: (() => void)[] = []; charts.forEach((c, i) => { const h = (r: { from: Time; to: Time } | null) => { if (!r) return; charts.forEach((o, j) => { if (j !== i) o.timeScale().setVisibleRange(r); }); }; c.timeScale().subscribeVisibleTimeRangeChange(h); subs.push(() => c.timeScale().unsubscribeVisibleTimeRangeChange(h)); }); return () => subs.forEach((u) => u()); }

// ─── Component ─────────────────────────────────────────────────────────

interface ChartWidgetProps { ticker: string; height?: number; }

export function ChartWidget({ ticker, height = 600 }: ChartWidgetProps) {
  const priceRef = useRef<HTMLDivElement>(null);
  const macdRef = useRef<HTMLDivElement>(null);
  const rsiRef = useRef<HTMLDivElement>(null);

  const charts = useRef<IChartApi[]>([]);
  const unsyncRef = useRef<(() => void) | null>(null);

  // Series refs for toggles
  const s20 = useRef<ISeriesApi<"Line"> | null>(null);
  const s50 = useRef<ISeriesApi<"Line"> | null>(null);
  const s200 = useRef<ISeriesApi<"Line"> | null>(null);
  const e20 = useRef<ISeriesApi<"Line"> | null>(null);
  const bbU = useRef<ISeriesApi<"Line"> | null>(null);
  const bbL = useRef<ISeriesApi<"Line"> | null>(null);
  const volS = useRef<ISeriesApi<"Histogram"> | null>(null);
  const ml = useRef<ISeriesApi<"Line"> | null>(null);
  const ms = useRef<ISeriesApi<"Line"> | null>(null);
  const mh = useRef<ISeriesApi<"Histogram"> | null>(null);
  const rl = useRef<ISeriesApi<"Line"> | null>(null);
  const ob = useRef<ISeriesApi<"Line"> | null>(null);
  const os = useRef<ISeriesApi<"Line"> | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [tSMA20, setSMA20] = useState(false);
  const [tSMA50, setSMA50] = useState(true);
  const [tSMA200, setSMA200] = useState(true);
  const [tEMA20, setEMA20] = useState(false);
  const [tBB, setBB] = useState(false);
  const [tVol, setVol] = useState(true);
  const [tMACD, setMACD] = useState(true);
  const [tRSI, setRSI] = useState(true);
  const [tOBOS, setOBOS] = useState(true);

  const build = useCallback(async () => {
    const [pr, mr, rr] = [priceRef.current, macdRef.current, rsiRef.current];
    const _t0 = performance.now();
    if (!pr || !mr || !rr) return;
    unsyncRef.current?.(); charts.current.forEach((c) => c.remove()); charts.current = [];
    setLoading(true); setError(null);

    try {
      const d = await fetchOHLCV(ticker);
      console.log(`⏱ fetchOHLCV: ${(performance.now() - _t0).toFixed(0)}ms`); const _t1 = performance.now();
      const cl = d.map((x) => x.close), ti = d.map((x) => x.time as Time);
      const w = pr.clientWidth; if (w === 0) return;
      const pH = Math.round(height * 0.55), mH = Math.round(height * 0.2), rH = height - pH - mH - 16;

      function mk(el: HTMLDivElement, h: number, rps: { borderColor: string; autoScale?: boolean } = { borderColor: BDR }) {
        const c = createChart(el, { layout: LAY, grid: G, crosshair: CH, timeScale: TS, rightPriceScale: rps, autoSize: true, width: w, height: h });
        charts.current.push(c); return c;
      }
      const tl = (vals: (number | null)[], i: number) => vals[i] !== null ? { time: ti[i], value: vals[i]! } : null;

      // ── PRICE chart with volume overlay ──────────────────────────────
      const sma20 = SMA(cl, 20), sma50 = SMA(cl, 50), sma200 = SMA(cl, 200), ema20 = EMA(cl, 20);
      const bb = BB(cl, 20, 2); const macd = MACD(cl); const rsi14 = RSI(cl, 14);
      console.log(`⏱ indicators: ${(performance.now() - _t1).toFixed(0)}ms`); const _t2 = performance.now();

      const pChart = mk(pr, pH);
      const candles = pChart.addCandlestickSeries({ upColor: "#00c853", downColor: "#ff1744", borderUpColor: "#00c853", borderDownColor: "#ff1744", wickUpColor: "#00c853", wickDownColor: "#ff1744", lastValueVisible: false, priceLineVisible: false });
      candles.setData(d.map((x) => ({ time: x.time as Time, open: x.open, high: x.high, low: x.low, close: x.close })));

      const addL = (vals: (number | null)[], color: string, _title: string, lw: LineWidth = 1) => {
        const s = pChart.addLineSeries({ color, lineWidth: lw, priceLineVisible: false, lastValueVisible: false });
        s.setData(vals.map((_, i) => tl(vals, i)).filter(Boolean) as { time: Time; value: number }[]); return s;
      };
      const addL2 = (vals: (number | null)[], color: string, _title: string, lw: LineWidth = 1, scaleId?: string) => {
        const s = pChart.addLineSeries({ color, lineWidth: lw, priceLineVisible: false, lastValueVisible: false, priceScaleId: scaleId || "right" });
        s.setData(vals.map((_, i) => tl(vals, i)).filter(Boolean) as { time: Time; value: number }[]); return s;
      };

      s20.current = addL(sma20, "#ffab40", "SMA 20");
      s50.current = addL(sma50, "#ff6e40", "SMA 50");
      s200.current = addL(sma200, "#2979ff", "SMA 200");
      e20.current = addL(ema20, "#00e5ff", "EMA 20");
      bbU.current = addL(bb.upper, "rgba(156,39,176,0.5)", "BB Upper", 1);
      bbL.current = addL(bb.lower, "rgba(156,39,176,0.5)", "BB Lower", 1);

      // Volume as overlay on separate price scale
      const volColors = d.map((x, i) => (i > 0 && x.close >= d[i - 1].close ? "rgba(0,200,83,0.35)" : "rgba(255,23,68,0.35)"));
      volS.current = pChart.addHistogramSeries({
        priceScaleId: "volume",
        priceFormat: { type: "volume" },
        priceLineVisible: false,
        lastValueVisible: false,
      });
      volS.current.setData(d.map((x, i) => ({ time: x.time as Time, value: x.volume, color: volColors[i] })));
      pChart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });

      pChart.timeScale().fitContent();

      // ── MACD chart ───────────────────────────────────────────────
      const mChart = mk(mr, mH, { borderColor: BDR, autoScale: true });
      ml.current = mChart.addLineSeries({ color: "#2979ff", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      ms.current = mChart.addLineSeries({ color: "#ff6e40", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      mh.current = mChart.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false });
      ml.current.setData(macd.line.map((_, i) => tl(macd.line, i)).filter(Boolean) as { time: Time; value: number }[]);
      ms.current.setData(macd.signal.map((_, i) => tl(macd.signal, i)).filter(Boolean) as { time: Time; value: number }[]);
      const hdata = macd.histogram.map((v, i) => v !== null ? { time: ti[i], value: v, color: v >= 0 ? "rgba(0,200,83,0.5)" : "rgba(255,23,68,0.5)" } : null).filter(Boolean) as { time: Time; value: number; color: string }[];
      mh.current.setData(hdata);

      // ── RSI chart ───────────────────────────────────────────────
      const rChart = mk(rr, rH, { borderColor: BDR, autoScale: true });
      rl.current = rChart.addLineSeries({ color: "#7c4dff", lineWidth: 2 as LineWidth, priceLineVisible: false, lastValueVisible: false });
      rl.current.setData(rsi14.map((_, i) => tl(rsi14, i)).filter(Boolean) as { time: Time; value: number }[]);
      ob.current = rChart.addLineSeries({ color: "#ff1744", lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false });
      os.current = rChart.addLineSeries({ color: "#00c853", lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false });
      if (rsi14.some((v) => v !== null)) {
        const ft = ti[rsi14.findIndex((v) => v !== null)], lt = ti[ti.length - 1];
        ob.current.setData([{ time: ft, value: 70 }, { time: lt, value: 70 }]);
        os.current.setData([{ time: ft, value: 30 }, { time: lt, value: 30 }]);
      }

      unsyncRef.current = syncTS([pChart, mChart, rChart]);
      console.log(`⏱ chart-render: ${(performance.now() - _t2).toFixed(0)}ms`); console.log(`⏱ TOTAL build: ${(performance.now() - _t0).toFixed(0)}ms`);
      setLoading(false);
    } catch (err) { setError(err instanceof Error ? err.message : "Chart render failed"); setLoading(false); }
  }, [ticker, height]);

  // ── Toggles ────────────────────────────────────────────────────────
  useEffect(() => { s20.current?.applyOptions({ visible: tSMA20 }); }, [tSMA20]);
  useEffect(() => { s50.current?.applyOptions({ visible: tSMA50 }); }, [tSMA50]);
  useEffect(() => { s200.current?.applyOptions({ visible: tSMA200 }); }, [tSMA200]);
  useEffect(() => { e20.current?.applyOptions({ visible: tEMA20 }); }, [tEMA20]);
  useEffect(() => { bbU.current?.applyOptions({ visible: tBB }); bbL.current?.applyOptions({ visible: tBB }); }, [tBB]);
  useEffect(() => { volS.current?.applyOptions({ visible: tVol }); }, [tVol]);
  useEffect(() => {
    ml.current?.applyOptions({ visible: tMACD });
    ms.current?.applyOptions({ visible: tMACD });
    mh.current?.applyOptions({ visible: tMACD });
    // Hide only the MACD container + border, NOT the parent
    if (macdRef.current) {
      macdRef.current.style.display = tMACD ? "" : "none";
      const prev = macdRef.current.previousElementSibling as HTMLElement | null;
      if (prev?.classList.contains("border-t")) prev.style.display = tMACD ? "" : "none";
    }
  }, [tMACD]);
  useEffect(() => { rl.current?.applyOptions({ visible: tRSI }); }, [tRSI]);
  useEffect(() => { ob.current?.applyOptions({ visible: tOBOS }); os.current?.applyOptions({ visible: tOBOS }); }, [tOBOS]);

  // ── Mount ──────────────────────────────────────────────────────────
  useEffect(() => {
    const raf = requestAnimationFrame(() => requestAnimationFrame(() => { build(); }));
    const onResize = () => { const w = priceRef.current?.clientWidth; if (w) charts.current.forEach((c) => c.applyOptions({ width: w })); };
    window.addEventListener("resize", onResize);
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", onResize); unsyncRef.current?.(); charts.current.forEach((c) => c.remove()); };
  }, [build]);

  function TBtn({ label, color, active, onClick }: { label: string; color: string; active: boolean; onClick: () => void }) {
    return <button onClick={onClick} className={clsx("flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium transition-colors border", active ? "border-opacity-30 bg-opacity-10" : "border-transparent bg-surface-elevated text-text-muted hover:text-text-secondary")} style={active ? { borderColor: color, backgroundColor: color + "18", color } : undefined}><span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: active ? color : "#484f58" }} />{active ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}{label}</button>;
  }

  return (
    <div className="card">
      <div className="mb-3 flex items-center justify-between flex-wrap gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-text-primary">
          <BarChart3 className="h-4 w-4 text-accent-blue" />{ticker}<span className="text-xs font-normal text-text-muted">— 1D · 5Y</span>
        </h3>
        <div className="flex items-center gap-1 flex-wrap">
          <TBtn label="SMA 20" color="#ffab40" active={tSMA20} onClick={() => setSMA20(!tSMA20)} />
          <TBtn label="SMA 50" color="#ff6e40" active={tSMA50} onClick={() => setSMA50(!tSMA50)} />
          <TBtn label="SMA 200" color="#2979ff" active={tSMA200} onClick={() => setSMA200(!tSMA200)} />
          <TBtn label="EMA 20" color="#00e5ff" active={tEMA20} onClick={() => setEMA20(!tEMA20)} />
          <TBtn label="BB" color="#9c27b0" active={tBB} onClick={() => setBB(!tBB)} />
          <TBtn label="Vol" color="#8b949e" active={tVol} onClick={() => setVol(!tVol)} />
          <span className="text-text-muted text-xs">|</span>
          <TBtn label="MACD" color="#2979ff" active={tMACD} onClick={() => setMACD(!tMACD)} />
          <TBtn label="RSI-14" color="#7c4dff" active={tRSI} onClick={() => setRSI(!tRSI)} />
          <TBtn label="70/30" color="#c0c0c0" active={tOBOS} onClick={() => setOBOS(!tOBOS)} />
        </div>
      </div>

      <div style={{ position: "relative", minHeight: height }}>
        <div ref={priceRef} className="tv-chart-container" />
        <div className="my-1 border-t border-surface-border" />
        <div ref={macdRef} className="tv-chart-container" />
        <div className="my-1 border-t border-surface-border" />
        <div ref={rsiRef} className="tv-chart-container" />
        {loading && <div className="absolute inset-0 flex items-center justify-center bg-[#161b22]/80 z-10"><Loader2 className="h-6 w-6 animate-spin text-text-muted" /></div>}
        {error && <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-[#161b22]/90 z-10"><AlertTriangle className="h-6 w-6 text-accent-red" /><p className="text-sm text-accent-red">Chart Error</p><p className="text-xs text-text-muted">{error}</p><button onClick={build} className="mt-2 rounded bg-surface-elevated px-3 py-1 text-xs text-text-secondary hover:bg-surface-border">Retry</button></div>}
      </div>
    </div>
  );
}

export function ChartWidgetSkeleton({ height = 600 }: { height?: number }) {
  return <div className="card animate-pulse"><div className="mb-3 skeleton h-5 w-48 rounded" /><div className="skeleton rounded" style={{ height }} /></div>;
}
