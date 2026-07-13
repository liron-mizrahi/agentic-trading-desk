'use client';

import { useState, useEffect } from 'react';
import { AlertTriangle, TrendingUp } from 'lucide-react';

interface BacktestResult {
  id: number;
  strategy: string;
  start_date: string;
  end_date: string;
  total_return_pct: number;
  annualized_return_pct: number;
  benchmark_return_pct: number;
  alpha_pct?: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  calmar_ratio?: number;
  win_rate_pct: number;
  profit_factor?: number;
  total_trades: number;
  avg_hold_days?: number;
  equity_curve: { date: string; equity: number }[];
  benchmark_curve: { date: string; equity: number }[];
  trades: any[];
  metrics: any;
  sectors?: string[];
  created_at: string;
}

interface Strategy {
  id: string;
  name: string;
  description: string;
  type: string;
  default_sectors: string[];
}

interface Sector {
  id: string;
  name: string;
  etf: string;
}

const STRATEGY_COLORS: Record<string, string> = {
  three_pillar: '#3b82f6',
  momentum_dip: '#ef4444',
  squeeze: '#10b981',
  dual_momentum: '#f59e0b',
  pead: '#8b5cf6',
  benchmark: '#6b7280',
};

const STRATEGY_LABELS: Record<string, string> = {
  three_pillar: 'Three-Pillar',
  momentum_dip: 'Momentum-Dip',
  squeeze: 'Squeeze Breakout',
  dual_momentum: 'Dual Momentum',
  pead: 'PEAD Drift',
  all: 'All Strategies',
};

function MiniEquityChart({ 
  strategyCurve, 
  benchmarkCurve, 
  strategyLabel, 
  height = 200 
}: { 
  strategyCurve: { date: string; equity: number }[];
  benchmarkCurve: { date: string; equity: number }[];
  strategyLabel: string;
  height?: number;
}) {
  if (!strategyCurve || strategyCurve.length < 2) {
    return <div className="h-48 flex items-center justify-center text-gray-500">No data</div>;
  }

  const startEquity = strategyCurve[0]?.equity || 100000;
  const maxEquity = Math.max(
    ...strategyCurve.map(p => p.equity),
    ...(benchmarkCurve || []).map(p => p.equity)
  );
  const minEquity = Math.min(
    ...strategyCurve.map(p => p.equity),
    ...(benchmarkCurve || []).map(p => p.equity)
  );
  const range = maxEquity - minEquity || 1;

  const width = 600;
  const pad = { top: 10, right: 10, bottom: 30, left: 60 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;

  const scaleX = (i: number) => pad.left + (i / (strategyCurve.length - 1)) * chartW;
  const scaleY = (v: number) => pad.top + chartH - ((v - minEquity) / range) * chartH;

  const toPath = (curve: { equity: number }[]) =>
    curve.map((p, i) => `${i === 0 ? 'M' : 'L'}${scaleX(i)},${scaleY(p.equity)}`).join(' ');

  const yTicks = [minEquity, (minEquity + maxEquity) / 2, maxEquity];

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto">
      {/* Grid lines */}
      {yTicks.map(v => (
        <line key={v} x1={pad.left} y1={scaleY(v)} x2={width - pad.right} y2={scaleY(v)}
          stroke="#e5e7eb" strokeWidth="0.5" />
      ))}
      {/* Y-axis labels */}
      {yTicks.map(v => (
        <text key={v} x={pad.left - 5} y={scaleY(v) + 4} textAnchor="end"
          className="fill-gray-500 text-[10px]">
          ${(v / 1000).toFixed(0)}k
        </text>
      ))}
      {/* Benchmark curve */}
      {benchmarkCurve && benchmarkCurve.length > 1 && (
        <path d={toPath(benchmarkCurve)} fill="none" stroke="#9ca3af" strokeWidth="1.5"
          strokeDasharray="4,2" opacity="0.6" />
      )}
      {/* Strategy curve */}
      <path d={toPath(strategyCurve)} fill="none" stroke={STRATEGY_COLORS.three_pillar}
        strokeWidth="2" />
      {/* Labels */}
      <text x={width - pad.right - 50} y={height - 8} className="fill-gray-400 text-[9px]">
        Strategy
      </text>
      <text x={width - pad.right - 90} y={height - 8} className="fill-gray-300 text-[9px]">
        - - SPY
      </text>
    </svg>
  );
}

export default function BacktestPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [sectors, setSectors] = useState<Sector[]>([]);
  const [results, setResults] = useState<BacktestResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [runSuccess, setRunSuccess] = useState<string | null>(null);
  const [selectedResult, setSelectedResult] = useState<number | null>(null);

  // Form state
  const [selectedStrategy, setSelectedStrategy] = useState('three_pillar');
  const [selectedSectors, setSelectedSectors] = useState<string[]>(['Technology']);
  const [startDate, setStartDate] = useState('2024-01-01');
  const [endDate, setEndDate] = useState('2025-12-31');
  const [benchmark, setBenchmark] = useState('SPY');
  const [capital, setCapital] = useState('100000');

  useEffect(() => {
    fetch('/api/backtest/strategies')
      .then(r => r.json())
      .then(d => setStrategies(d.strategies || []));
    fetch('/api/backtest/sectors')
      .then(r => r.json())
      .then(d => setSectors(d.sectors || []));
    loadResults();
  }, []);

  const loadResults = () => {
    fetch('/api/backtest/results?limit=10')
      .then(r => r.json())
      .then(d => setResults(d.results || []));
  };

  const runBacktest = async () => {
    setLoading(true);
    setRunError(null);
    setRunSuccess(null);
    try {
      const res = await fetch('/api/backtest/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          strategy: selectedStrategy,
          sectors: selectedSectors,
          start_date: startDate,
          end_date: endDate,
          benchmark,
          capital: parseFloat(capital),
        }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Backend returned ${res.status}`);
      }
      const data = await res.json();
      if (data.status === 'complete' || data.status === 'queued') {
        setRunSuccess(data.status === 'complete' ? 'Backtest completed — refreshing results...' : 'Backtest queued — check back shortly');
        loadResults();
      } else {
        setRunError('Unexpected response from server');
      }
    } catch (e: any) {
      const msg = e.message || 'Backtest failed';
      setRunError(msg.includes('fetch') ? 'Cannot reach backend — is the server running?' : msg);
    }
    setLoading(false);
  };

  const toggleSector = (sectorId: string) => {
    setSelectedSectors(prev =>
      prev.includes(sectorId)
        ? prev.filter(s => s !== sectorId)
        : [...prev, sectorId]
    );
  };

  const formatPct = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
  const formatNum = (v: number, decimals = 2) => v?.toFixed(decimals) ?? '—';

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <div className="max-w-7xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold mb-2">📊 Strategy Backtesting</h1>
        <p className="text-gray-400 mb-8">
          Time-warp simulation with strict out-of-sample partitioning. Compare strategy performance against SPY benchmark.
        </p>

        {/* ——— Run Panel ——— */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 mb-8">
          <h2 className="text-lg font-semibold mb-4">Run New Backtest</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            {/* Strategy */}
            <div>
              <label className="block text-sm text-gray-400 mb-1">Strategy</label>
              <select
                value={selectedStrategy}
                onChange={e => setSelectedStrategy(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
              >
                {strategies.map(s => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>
            {/* Start Date */}
            <div>
              <label className="block text-sm text-gray-400 mb-1">Start Date</label>
              <input
                type="date"
                value={startDate}
                onChange={e => setStartDate(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            {/* End Date */}
            <div>
              <label className="block text-sm text-gray-400 mb-1">End Date</label>
              <input
                type="date"
                value={endDate}
                onChange={e => setEndDate(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
              />
            </div>
          </div>

          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-2">Sectors</label>
            <div className="flex flex-wrap gap-2">
              {sectors.map(s => (
                <button
                  key={s.id}
                  onClick={() => toggleSector(s.id)}
                  className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                    selectedSectors.includes(s.id)
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                  }`}
                >
                  {s.name} ({s.etf})
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={runBacktest}
            disabled={loading}
            className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-6 py-2 rounded-lg font-medium transition-colors"
          >
            {loading ? '⏳ Running...' : '▶ Run Backtest'}
          </button>

          {runError && (
            <div className="mt-3 flex items-center gap-2 rounded-lg border border-red-800/50 bg-red-900/20 px-4 py-2 text-sm text-red-400">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>{runError}</span>
              <button onClick={() => setRunError(null)} className="ml-auto text-red-400/60 hover:text-red-400">✕</button>
            </div>
          )}
          {runSuccess && (
            <div className="mt-3 flex items-center gap-2 rounded-lg border border-green-800/50 bg-green-900/20 px-4 py-2 text-sm text-green-400">
              <TrendingUp className="h-4 w-4 shrink-0" />
              <span>{runSuccess}</span>
              <button onClick={() => setRunSuccess(null)} className="ml-auto text-green-400/60 hover:text-green-400">✕</button>
            </div>
          )}
        </div>

        {/* ——— Results Table ——— */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden mb-8">
          <div className="px-6 py-4 border-b border-gray-800">
            <h2 className="text-lg font-semibold">Saved Results</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-gray-400 text-left">
                  <th className="px-6 py-3">Strategy</th>
                  <th className="px-6 py-3">Period</th>
                  <th className="px-6 py-3 text-right">Return</th>
                  <th className="px-6 py-3 text-right">vs SPY</th>
                  <th className="px-6 py-3 text-right">Sharpe</th>
                  <th className="px-6 py-3 text-right">Max DD</th>
                  <th className="px-6 py-3 text-right">Win Rate</th>
                  <th className="px-6 py-3 text-right">Trades</th>
                  <th className="px-6 py-3">Verdict</th>
                </tr>
              </thead>
              <tbody>
                {results.map(r => {
                  const alpha = (r.alpha_pct ?? r.total_return_pct - r.benchmark_return_pct);
                  const isGood = alpha > 5 && r.sharpe_ratio > 1 && r.win_rate_pct > 50;
                  const isMarginal = alpha > 0 && r.sharpe_ratio > 0.5;
                  return (
                    <tr
                      key={r.id}
                      onClick={() => setSelectedResult(selectedResult === r.id ? null : r.id)}
                      className={`border-b border-gray-800/50 hover:bg-gray-800/50 cursor-pointer transition-colors ${
                        selectedResult === r.id ? 'bg-gray-800/70' : ''
                      }`}
                    >
                      <td className="px-6 py-3 font-medium">
                        {STRATEGY_LABELS[r.strategy] || r.strategy}
                      </td>
                      <td className="px-6 py-3 text-gray-400">
                        {r.start_date} → {r.end_date}
                      </td>
                      <td className={`px-6 py-3 text-right font-mono ${
                        r.total_return_pct >= 0 ? 'text-green-400' : 'text-red-400'
                      }`}>
                        {formatPct(r.total_return_pct)}
                      </td>
                      <td className={`px-6 py-3 text-right font-mono ${
                        alpha >= 0 ? 'text-green-400' : 'text-red-400'
                      }`}>
                        {formatPct(alpha)}
                      </td>
                      <td className={`px-6 py-3 text-right font-mono ${
                        r.sharpe_ratio >= 1 ? 'text-green-400' : r.sharpe_ratio >= 0 ? 'text-yellow-400' : 'text-red-400'
                      }`}>
                        {formatNum(r.sharpe_ratio)}
                      </td>
                      <td className="px-6 py-3 text-right font-mono text-red-400">
                        -{formatNum(r.max_drawdown_pct)}%
                      </td>
                      <td className="px-6 py-3 text-right font-mono">
                        {formatNum(r.win_rate_pct)}%
                      </td>
                      <td className="px-6 py-3 text-right font-mono text-gray-400">
                        {r.total_trades}
                      </td>
                      <td className="px-6 py-3">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                          isGood ? 'bg-green-900/50 text-green-400' :
                          isMarginal ? 'bg-yellow-900/50 text-yellow-400' :
                          'bg-red-900/50 text-red-400'
                        }`}>
                          {isGood ? '✅ VIABLE' : isMarginal ? '⚠ MARGINAL' : '❌ FAIL'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
                {results.length === 0 && (
                  <tr>
                    <td colSpan={9} className="px-6 py-12 text-center text-gray-500">
                      No backtest results yet. Run one above.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* ——— Expanded Detail ——— */}
        {selectedResult && (() => {
          const r = results.find(x => x.id === selectedResult);
          if (!r) return null;
          const alpha = (r.alpha_pct ?? r.total_return_pct - r.benchmark_return_pct);
          return (
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 mb-8">
              <h3 className="text-lg font-semibold mb-4">
                {STRATEGY_LABELS[r.strategy]} — Detail
              </h3>

              {/* Equity Curve */}
              <div className="mb-6">
                <h4 className="text-sm text-gray-400 mb-2">Equity Curve</h4>
                <MiniEquityChart
                  strategyCurve={r.equity_curve || []}
                  benchmarkCurve={r.benchmark_curve || []}
                  strategyLabel={STRATEGY_LABELS[r.strategy]}
                  height={220}
                />
              </div>

              {/* Metrics Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                {[
                  ['Total Return', formatPct(r.total_return_pct), r.total_return_pct >= 0 ? 'text-green-400' : 'text-red-400'],
                  ['Annualized', `${r.annualized_return_pct.toFixed(2)}%`, 'text-blue-400'],
                  ['vs SPY', formatPct(alpha), alpha >= 0 ? 'text-green-400' : 'text-red-400'],
                  ['Sharpe Ratio', formatNum(r.sharpe_ratio), r.sharpe_ratio >= 1 ? 'text-green-400' : 'text-yellow-400'],
                  ['Max Drawdown', `-${formatNum(r.max_drawdown_pct)}%`, 'text-red-400'],
                  ['Calmar', formatNum(r.calmar_ratio ?? 0), 'text-gray-300'],
                  ['Win Rate', `${formatNum(r.win_rate_pct)}%`, 'text-gray-300'],
                  ['Profit Factor', formatNum(r.profit_factor ?? 0), (r.profit_factor ?? 0) >= 1.5 ? 'text-green-400' : 'text-gray-300'],
                  ['Total Trades', String(r.total_trades), 'text-gray-300'],
                  ['Avg Hold', `${formatNum(r.avg_hold_days ?? 0)}d`, 'text-gray-300'],
                  ['Sectors', (r.sectors || []).join(', ') || 'All', 'text-gray-400'],
                  ['Benchmark', 'SPY Buy & Hold', 'text-gray-400'],
                ].map(([label, value, color]) => (
                  <div key={label as string} className="bg-gray-800/50 rounded-lg p-3">
                    <div className="text-xs text-gray-500 mb-1">{label}</div>
                    <div className={`text-lg font-mono font-semibold ${color}`}>{value}</div>
                  </div>
                ))}
              </div>

              {/* Verdict */}
              <div className={`p-4 rounded-lg mb-6 ${
                alpha > 5 && r.sharpe_ratio > 1 
                  ? 'bg-green-900/30 border border-green-800' 
                  : alpha > 0 
                  ? 'bg-yellow-900/30 border border-yellow-800'
                  : 'bg-red-900/30 border border-red-800'
              }`}>
                <div className="text-sm font-medium mb-1">
                  {alpha > 5 && r.sharpe_ratio > 1 
                    ? '✅ VIABLE — Ready for paper trading' 
                    : alpha > 0 
                    ? '⚠ MARGINAL — Needs parameter tuning'
                    : '❌ FAIL — Strategy does not justify the risk'}
                </div>
                <div className="text-xs text-gray-400">
                  {r.total_trades < 30 
                    ? `⚠ Low trade count (${r.total_trades}) — results may not be statistically significant.`
                    : `${r.total_trades} trades — statistically meaningful sample.`}
                </div>
              </div>

              {/* Trade Log */}
              {r.trades && r.trades.length > 0 && (
                <div>
                  <h4 className="text-sm text-gray-400 mb-2">Trade Log ({r.trades.length})</h4>
                  <div className="max-h-64 overflow-y-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-gray-500 text-left border-b border-gray-800">
                          <th className="py-1 pr-4">Ticker</th>
                          <th className="py-1 pr-4">Entry</th>
                          <th className="py-1 pr-4">Exit</th>
                          <th className="py-1 pr-4 text-right">P&L</th>
                          <th className="py-1 pr-4 text-right">%</th>
                          <th className="py-1">Exit Reason</th>
                        </tr>
                      </thead>
                      <tbody>
                        {r.trades.slice(0, 50).map((t: any, i: number) => (
                          <tr key={i} className="border-b border-gray-800/30">
                            <td className="py-1 pr-4 font-medium">{t.ticker}</td>
                            <td className="py-1 pr-4 text-gray-400">{t.entry_date}</td>
                            <td className="py-1 pr-4 text-gray-400">{t.exit_date}</td>
                            <td className={`py-1 pr-4 text-right font-mono ${t.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              ${t.pnl?.toFixed(2)}
                            </td>
                            <td className={`py-1 pr-4 text-right font-mono ${t.pnl_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              {t.pnl_pct?.toFixed(2)}%
                            </td>
                            <td className="py-1 text-gray-500">{t.exit_reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          );
        })()}
      </div>
    </div>
  );
}
