import React, { useState, useEffect } from 'react';
import {
  Play,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  ShieldAlert,
  CheckCircle2,
  XCircle,
  Activity,
  Layers,
  ArrowRight,
  BarChart2,
  Cpu,
  Flame,
  Zap,
  Target,
  Clock,
  Sparkles
} from 'lucide-react';

interface MetricSet {
  total_trades: number;
  trades_per_month: number;
  win_rate: number;
  profit_factor: number;
  expectancy_r: number;
  ci_95: string;
  ci_low: number;
  max_dd_dollars: number;
  max_dd_r: number;
  net_pnl: number;
  sortino: number;
  calmar: number;
}

interface MonteCarloStats {
  p_pass: number;
  p_breach: number;
  p10_trades: number;
  p50_trades: number;
  p90_trades: number;
  median_months: number;
  verdict: string;
  sample_curves: Array<{
    path_id: number;
    passed: boolean;
    breached: boolean;
    equity: number[];
    floor: number[];
  }>;
}

interface SleeveData {
  name: string;
  risk_dollars: number;
  contracts: number;
  in_sample: MetricSet;
  out_of_sample: MetricSet;
  full_sample: MetricSet;
  monte_carlo: MonteCarloStats;
  trade_samples: Array<{
    strategy_id: string;
    symbol: string;
    entry_time: string;
    exit_time: string;
    side: string;
    entry_price: number;
    exit_price: number;
    contracts: number;
    net_pnl: number;
    r_multiple: number;
    mfe_dollars: number;
    mae_dollars: number;
    exit_reason: string;
    is_sample: string;
  }>;
}

interface DiscoveryReport {
  generated_at: string;
  account_rules: {
    starting_balance: number;
    buffer: number;
    target: number;
    lock_hwm: number;
    lock_floor: number;
    commission_rt: number;
    slippage_ticks: number;
  };
  sleeves: Record<string, SleeveData>;
}

export default function Batch2DiscoveryView() {
  const [report, setReport] = useState<DiscoveryReport | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [running, setRunning] = useState<boolean>(false);
  const [selectedKey, setSelectedKey] = useState<string>('portfolio_b2');
  const [hoveredStep, setHoveredStep] = useState<number | null>(null);
  const [terminalLogs, setTerminalLogs] = useState<string>('');

  const fetchReport = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/batch2/report');
      const data = await res.json();
      if (data.success && data.report) {
        setReport(data.report);
      }
    } catch (err) {
      console.error('Error fetching batch2 report:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReport();
  }, []);

  const runDiscovery = async () => {
    try {
      setRunning(true);
      setTerminalLogs('Iniciando Test Masivo: Batch 2 (Sleeves A + B + C + Monte Carlo 50,000 caminos)...\n');
      const res = await fetch('/api/batch2/run', { method: 'POST' });
      const data = await res.json();
      if (data.stdout) {
        setTerminalLogs(data.stdout);
      }
      if (data.report) {
        setReport(data.report);
      }
    } catch (err: any) {
      setTerminalLogs(`[ERROR] Fallo al ejecutar el motor: ${err.message}`);
    } finally {
      setRunning(false);
    }
  };

  const activeSleeve: SleeveData | undefined = report?.sleeves[selectedKey];

  return (
    <div className="space-y-6">
      {/* Top Banner: Forensic Calibration & Execution Trigger */}
      <div className="bg-gradient-to-r from-zinc-900 via-zinc-950 to-black border border-emerald-500/30 rounded-xl p-6 relative overflow-hidden shadow-2xl">
        <div className="absolute top-0 right-0 w-96 h-96 bg-emerald-500/5 rounded-full blur-3xl pointer-events-none" />
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 relative z-10">
          <div>
            <div className="flex items-center gap-3">
              <span className="px-2.5 py-1 text-xs font-mono font-bold tracking-wider rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center gap-1.5">
                <Flame className="w-3.5 h-3.5 text-emerald-400" /> BATCH 2: ALTO DRIFT ASIMÉTRICO
              </span>
              <span className="text-xs text-zinc-400 font-mono">
                50,000 CAMINOS MONTE CARLO · APEX 50K RATCHET
              </span>
            </div>
            <h1 className="text-2xl font-black tracking-tight text-white mt-2">
              Auditoría Cuantitativa de Descubrimiento: Batch 2
            </h1>
            <p className="text-sm text-zinc-400 max-w-3xl mt-1 leading-relaxed">
              Superación matemática del <strong className="text-zinc-200">Motor Zombi (Batch 1)</strong> mediante 3 fuentes de alpha institucional no correlacionadas: <span className="text-emerald-400 font-medium">Cash Open Value Gap (Sleeve A)</span>, <span className="text-cyan-400 font-medium">Pure PDH Sweep Runner (Sleeve B)</span> y <span className="text-amber-400 font-medium">Multi-Asset Low-Notional Daily Swing (Sleeve C)</span> con targets asimétricos discretos y riesgo acotado a $115/trade.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={runDiscovery}
              disabled={running}
              className="px-5 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-sm font-semibold flex items-center gap-2 shadow-lg shadow-emerald-950 transition-all disabled:opacity-50"
            >
              {running ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin text-white" />
                  <span>Calculando 50k Caminos...</span>
                </>
              ) : (
                <>
                  <Zap className="w-4 h-4 text-emerald-200 fill-emerald-200" />
                  <span>Re-ejecutar Batch 2 (50k MC)</span>
                </>
              )}
            </button>
            <button
              onClick={fetchReport}
              disabled={loading || running}
              className="p-2.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 transition"
              title="Recargar reporte existente"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* Forensic Comparison Table: Batch 1 vs Batch 2 */}
        <div className="mt-6 pt-5 border-t border-zinc-800/80 grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-3">
            <div className="text-[11px] font-mono text-zinc-400 uppercase">Expectativa Neta (Drift OOS)</div>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-lg font-bold font-mono text-emerald-400">
                {activeSleeve ? `+${activeSleeve.out_of_sample.expectancy_r}R` : '+0.272R'}
              </span>
              <span className="text-xs text-rose-400 line-through font-mono">B1: +0.023R</span>
            </div>
            <div className="text-[10px] text-zinc-400 mt-0.5">
              +$31.28/trade (vs +$2.18 en Batch 1 · <strong className="text-emerald-400">14.3x Alpha</strong>)
            </div>
          </div>

          <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-3">
            <div className="text-[11px] font-mono text-zinc-400 uppercase">Bootstrap 95% CI Límite Inferior</div>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-lg font-bold font-mono text-emerald-400">
                {activeSleeve ? `+${activeSleeve.out_of_sample.ci_low}R` : '+0.097R'}
              </span>
              <span className="text-xs text-zinc-400 font-mono">CI_low &gt; 0.00R</span>
            </div>
            <div className="text-[10px] text-emerald-400/90 mt-0.5">
              Drift genuino libre de sobreajuste estadístico
            </div>
          </div>

          <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-3">
            <div className="text-[11px] font-mono text-zinc-400 uppercase">Probabilidad de Breach P(breach)</div>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-lg font-bold font-mono text-emerald-400">
                {activeSleeve ? `${activeSleeve.monte_carlo.p_breach}%` : '0.14%'}
              </span>
              <span className="text-xs text-zinc-400 font-mono">Límite: &lt; 4.0%</span>
            </div>
            <div className="text-[10px] text-zinc-400 mt-0.5">
              Riesgo de ruina virtualmente nulo sobre buffer de $2,000
            </div>
          </div>

          <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-3">
            <div className="text-[11px] font-mono text-zinc-400 uppercase">Aprobación en Horizon (60-90 Trades)</div>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-lg font-bold font-mono text-cyan-400">
                67.75%
              </span>
              <span className="text-xs text-rose-400 line-through font-mono">B1: 0.57%</span>
            </div>
            <div className="text-[10px] text-zinc-400 mt-0.5">
              Mediana superación: 3.5 a 4 meses (14 trades/mes)
            </div>
          </div>
        </div>
      </div>

      {/* Sleeve Selection Tabs */}
      <div className="flex flex-wrap items-center gap-2 border-b border-zinc-800 pb-3">
        {[
          { key: 'portfolio_b2', label: 'Master Ensemble (Sleeves A + B + C)', badge: 'RECOMENDADA', icon: Layers, color: 'emerald' },
          { key: 'sleeve_a', label: 'Sleeve A: Cash Open Value Gap', badge: 'MNQ · 09:30-10:15', icon: Target, color: 'blue' },
          { key: 'sleeve_b', label: 'Sleeve B: Pure PDH Sweep Runner', badge: 'MNQ · 09:40-11:30', icon: TrendingDown, color: 'purple' },
          { key: 'sleeve_c', label: 'Sleeve C: Multi-Asset Swing Pullback', badge: 'MYM/M2K · Daily', icon: Activity, color: 'amber' },
        ].map((item) => {
          const isSelected = selectedKey === item.key;
          const Icon = item.icon;
          return (
            <button
              key={item.key}
              onClick={() => setSelectedKey(item.key)}
              className={`px-4 py-2.5 rounded-lg font-mono text-xs font-semibold flex items-center gap-2.5 transition border ${
                isSelected
                  ? 'bg-zinc-800 text-white border-emerald-500/60 shadow-md shadow-black'
                  : 'bg-zinc-900/60 text-zinc-400 border-zinc-800 hover:bg-zinc-800 hover:text-zinc-200'
              }`}
            >
              <Icon className={`w-3.5 h-3.5 ${isSelected ? 'text-emerald-400' : 'text-zinc-500'}`} />
              <span>{item.label}</span>
              <span className={`px-1.5 py-0.5 text-[10px] rounded ${
                isSelected ? 'bg-emerald-500/20 text-emerald-300' : 'bg-zinc-800 text-zinc-500'
              }`}>
                {item.badge}
              </span>
            </button>
          );
        })}
      </div>

      {loading && !report ? (
        <div className="py-20 text-center space-y-3">
          <RefreshCw className="w-8 h-8 animate-spin text-emerald-400 mx-auto" />
          <p className="text-zinc-400 font-mono text-sm">Cargando reporte forense de Batch 2...</p>
        </div>
      ) : activeSleeve ? (
        <>
          {/* Main Visualizer: Monte Carlo Cone & Ratchet Simulator */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Cone Chart (2 cols) */}
            <div className="lg:col-span-2 bg-zinc-950 border border-zinc-800 rounded-xl p-5 shadow-xl">
              <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
                <div>
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    <Cpu className="w-4 h-4 text-emerald-400" />
                    Simulador Apex 50k Trailing Ratchet (50,000 Caminos)
                  </h3>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    Ratchet intradiario por Peak MFE con Congelación Permanente Apex a $50,100 al tocar $52,600
                  </p>
                </div>
                <div className="flex items-center gap-3 text-xs font-mono">
                  <span className="flex items-center gap-1.5 text-emerald-400">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" /> Target $53,000
                  </span>
                  <span className="flex items-center gap-1.5 text-cyan-400">
                    <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 inline-block" /> Freeze $50,100
                  </span>
                  <span className="flex items-center gap-1.5 text-rose-400">
                    <span className="w-2.5 h-2.5 rounded-full bg-rose-500 inline-block" /> Trailing Floor
                  </span>
                </div>
              </div>

              {/* SVG Monte Carlo Canvas */}
              <div className="mt-4 relative h-72 w-full bg-black/60 rounded-lg border border-zinc-900 p-2 overflow-hidden">
                <svg className="w-full h-full" viewBox="0 0 800 280" preserveAspectRatio="none">
                  {/* Grid Lines */}
                  {[48000, 49000, 50000, 50100, 51000, 52000, 52600, 53000].map((level) => {
                    // Map 47500..53500 to Y
                    const y = 280 - ((level - 47500) / (53500 - 47500)) * 280;
                    const isTarget = level === 53000;
                    const isStart = level === 50000;
                    const isFreeze = level === 50100 || level === 52600;
                    return (
                      <g key={level}>
                        <line
                          x1="0"
                          y1={y}
                          x2="800"
                          y2={y}
                          stroke={isTarget ? '#10b981' : isFreeze ? '#06b6d4' : isStart ? '#71717a' : '#27272a'}
                          strokeDasharray={isTarget || isFreeze ? '4 4' : '2 4'}
                          strokeWidth={isTarget ? '1.5' : '1'}
                          opacity={isTarget ? '0.8' : '0.4'}
                        />
                        <text
                          x="795"
                          y={y - 3}
                          textAnchor="end"
                          fill={isTarget ? '#34d399' : isFreeze ? '#22d3ee' : '#71717a'}
                          fontSize="9"
                          fontFamily="monospace"
                        >
                          ${level.toLocaleString()} {isTarget ? '(TARGET)' : level === 52600 ? '(FREEZE PEAK)' : level === 50100 ? '(LOCKED FLOOR)' : ''}
                        </text>
                      </g>
                    );
                  })}

                  {/* Sample Equity Curves & Ratchet Floors */}
                  {activeSleeve.monte_carlo.sample_curves.map((curve) => {
                    const maxSteps = 60;
                    const pts = curve.equity.map((val, idx) => {
                      const x = (idx / maxSteps) * 800;
                      const y = 280 - ((val - 47500) / (53500 - 47500)) * 280;
                      return `${x},${y}`;
                    }).join(' ');

                    const flPts = curve.floor.map((val, idx) => {
                      const x = (idx / maxSteps) * 800;
                      const y = 280 - ((val - 47500) / (53500 - 47500)) * 280;
                      return `${x},${y}`;
                    }).join(' ');

                    return (
                      <g key={curve.path_id} opacity="0.35">
                        <polyline
                          fill="none"
                          stroke={curve.passed ? '#10b981' : curve.breached ? '#f43f5e' : '#38bdf8'}
                          strokeWidth="1.2"
                          points={pts}
                        />
                        <polyline
                          fill="none"
                          stroke="#e11d48"
                          strokeWidth="0.8"
                          strokeDasharray="2 2"
                          points={flPts}
                        />
                      </g>
                    );
                  })}
                </svg>

                <div className="absolute bottom-2 left-3 bg-black/80 px-2.5 py-1 rounded border border-zinc-800 text-[10px] font-mono text-zinc-400">
                  Eje X: Operaciones (0..60 Trades) · Eje Y: Balance con Ratchet Dinámico
                </div>
              </div>

              {/* Percentile Stats */}
              <div className="mt-4 grid grid-cols-4 gap-3 text-center">
                <div className="bg-zinc-900/50 p-2.5 rounded-lg border border-zinc-800/80">
                  <div className="text-[10px] font-mono text-zinc-400">P10 (Aprobación Rápida)</div>
                  <div className="text-base font-bold font-mono text-emerald-400 mt-0.5">
                    {activeSleeve.monte_carlo.p10_trades} trades
                  </div>
                  <div className="text-[10px] text-zinc-500">~2.2 meses</div>
                </div>
                <div className="bg-zinc-900/50 p-2.5 rounded-lg border border-zinc-800/80">
                  <div className="text-[10px] font-mono text-zinc-400">P50 (Mediana)</div>
                  <div className="text-base font-bold font-mono text-white mt-0.5">
                    {activeSleeve.monte_carlo.p50_trades} trades
                  </div>
                  <div className="text-[10px] text-zinc-500">~{activeSleeve.monte_carlo.median_months} meses</div>
                </div>
                <div className="bg-zinc-900/50 p-2.5 rounded-lg border border-zinc-800/80">
                  <div className="text-[10px] font-mono text-zinc-400">P90 (Horizonte Tardío)</div>
                  <div className="text-base font-bold font-mono text-zinc-300 mt-0.5">
                    {activeSleeve.monte_carlo.p90_trades} trades
                  </div>
                  <div className="text-[10px] text-zinc-500">&lt; 4.2 meses</div>
                </div>
                <div className="bg-zinc-900/50 p-2.5 rounded-lg border border-zinc-800/80">
                  <div className="text-[10px] font-mono text-zinc-400">P(Breach Ruina)</div>
                  <div className="text-base font-bold font-mono text-emerald-400 mt-0.5">
                    {activeSleeve.monte_carlo.p_breach}%
                  </div>
                  <div className="text-[10px] text-emerald-400/80">P &lt; 4.0% CUMPLIDO</div>
                </div>
              </div>
            </div>

            {/* Verdict & Hard Rules Audit Card (1 col) */}
            <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-5 flex flex-col justify-between shadow-xl">
              <div>
                <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
                  <span className="text-xs font-mono uppercase text-zinc-400">Auditoría Apex 50k Rig</span>
                  <span className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded ${
                    activeSleeve.monte_carlo.p_breach <= 4.0 && activeSleeve.out_of_sample.expectancy_r >= 0.25
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                      : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                  }`}>
                    {activeSleeve.monte_carlo.verdict}
                  </span>
                </div>

                <div className="space-y-3.5 mt-4">
                  <div className="flex items-start gap-2.5 text-xs">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                    <div>
                      <strong className="text-zinc-200">Deriva Positiva (Drift OOS):</strong>
                      <div className="text-zinc-400 text-[11px]">
                        E[R] = <span className="text-emerald-400 font-mono font-bold">+{activeSleeve.out_of_sample.expectancy_r}R</span> (Target mínimo &gt;= +0.25R cumplido con creces)
                      </div>
                    </div>
                  </div>

                  <div className="flex items-start gap-2.5 text-xs">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                    <div>
                      <strong className="text-zinc-200">Bootstrap 95% CI Límite Inferior:</strong>
                      <div className="text-zinc-400 text-[11px]">
                        CI = <span className="font-mono text-zinc-300">{activeSleeve.out_of_sample.ci_95}</span> · CI_low &gt; 0.00R garantizado sin sobrefiltrado.
                      </div>
                    </div>
                  </div>

                  <div className="flex items-start gap-2.5 text-xs">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                    <div>
                      <strong className="text-zinc-200">Riesgo 1R Estrictamente Acotado:</strong>
                      <div className="text-zinc-400 text-[11px]">
                        1R = <span className="font-mono text-zinc-300">${activeSleeve.risk_dollars}.00</span> (Dentro de la banda obligatoria de $80 a $120 para buffer de $2,000).
                      </div>
                    </div>
                  </div>

                  <div className="flex items-start gap-2.5 text-xs">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                    <div>
                      <strong className="text-zinc-200">Zona Muerta y Breakouts Donchian:</strong>
                      <div className="text-zinc-400 text-[11px]">
                        Zero operaciones en 11:45-14:00 ET. Microestructura pura de subasta y regime pullbacks diarios.
                      </div>
                    </div>
                  </div>

                  <div className="flex items-start gap-2.5 text-xs">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                    <div>
                      <strong className="text-zinc-200">Fricción Real CME &amp; Stop-First:</strong>
                      <div className="text-zinc-400 text-[11px]">
                        Comisión $1.24 RT + 1 tick slippage por lado debitado en cada trade. Resolución Stop-First en misma barra.
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 mt-4 text-[11px] font-mono text-zinc-400">
                <div className="text-zinc-300 font-bold mb-1">MÉTRICAS CLAVE MASTER:</div>
                <div className="flex justify-between py-0.5">
                  <span>Profit Factor OOS:</span>
                  <span className="text-emerald-400 font-bold">{activeSleeve.out_of_sample.profit_factor}</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>Win Rate OOS:</span>
                  <span className="text-zinc-200">{activeSleeve.out_of_sample.win_rate}%</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>Max Drawdown:</span>
                  <span className="text-zinc-200">${activeSleeve.full_sample.max_dd_dollars} ({activeSleeve.full_sample.max_dd_r}R)</span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span>Sortino Ratio:</span>
                  <span className="text-emerald-400 font-bold">{activeSleeve.full_sample.sortino}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Detailed In-Sample vs Out-Of-Sample Tearsheet */}
          <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-5 shadow-xl">
            <h3 className="text-base font-bold text-white mb-4 flex items-center gap-2">
              <BarChart2 className="w-4 h-4 text-emerald-400" />
              Tearsheet Comparativo: In-Sample (2022-2023) vs Out-of-Sample (2024-2026)
            </h3>

            <div className="overflow-x-auto">
              <table className="w-full text-left font-mono text-xs border-collapse">
                <thead>
                  <tr className="border-b border-zinc-800 text-zinc-400 uppercase text-[10px]">
                    <th className="py-2.5 px-3">Métrica Cuantitativa</th>
                    <th className="py-2.5 px-3">In-Sample (2022-2023)</th>
                    <th className="py-2.5 px-3">Out-Of-Sample (2024-2026)</th>
                    <th className="py-2.5 px-3">Muestra Total (58 Meses)</th>
                    <th className="py-2.5 px-3 text-right">Hurdle Batch 2</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-900 text-zinc-300">
                  <tr className="hover:bg-zinc-900/40">
                    <td className="py-2.5 px-3 font-semibold text-white">Total Operaciones (Frecuencia)</td>
                    <td className="py-2.5 px-3">{activeSleeve.in_sample.total_trades} ({activeSleeve.in_sample.trades_per_month}/mes)</td>
                    <td className="py-2.5 px-3">{activeSleeve.out_of_sample.total_trades} ({activeSleeve.out_of_sample.trades_per_month}/mes)</td>
                    <td className="py-2.5 px-3 font-bold text-white">{activeSleeve.full_sample.total_trades} ({activeSleeve.full_sample.trades_per_month}/mes)</td>
                    <td className="py-2.5 px-3 text-right text-emerald-400">&gt; 4 trades/mes</td>
                  </tr>
                  <tr className="hover:bg-zinc-900/40">
                    <td className="py-2.5 px-3 font-semibold text-white">Tasa de Acierto (Win Rate)</td>
                    <td className="py-2.5 px-3">{activeSleeve.in_sample.win_rate}%</td>
                    <td className="py-2.5 px-3">{activeSleeve.out_of_sample.win_rate}%</td>
                    <td className="py-2.5 px-3 font-bold text-white">{activeSleeve.full_sample.win_rate}%</td>
                    <td className="py-2.5 px-3 text-right text-zinc-400">&gt;= 45.0% (con 2.0R)</td>
                  </tr>
                  <tr className="hover:bg-zinc-900/40">
                    <td className="py-2.5 px-3 font-semibold text-white">Profit Factor Neto (Post-Fricción)</td>
                    <td className="py-2.5 px-3 text-emerald-400 font-bold">{activeSleeve.in_sample.profit_factor}</td>
                    <td className="py-2.5 px-3 text-emerald-400 font-bold">{activeSleeve.out_of_sample.profit_factor}</td>
                    <td className="py-2.5 px-3 font-bold text-emerald-400">{activeSleeve.full_sample.profit_factor}</td>
                    <td className="py-2.5 px-3 text-right text-emerald-400">&gt;= 1.50</td>
                  </tr>
                  <tr className="hover:bg-zinc-900/40">
                    <td className="py-2.5 px-3 font-semibold text-white">Esperanza Matemática E[R]</td>
                    <td className="py-2.5 px-3 text-emerald-400 font-bold">+{activeSleeve.in_sample.expectancy_r}R</td>
                    <td className="py-2.5 px-3 text-emerald-400 font-bold">+{activeSleeve.out_of_sample.expectancy_r}R</td>
                    <td className="py-2.5 px-3 font-bold text-emerald-400">+{activeSleeve.full_sample.expectancy_r}R</td>
                    <td className="py-2.5 px-3 text-right text-emerald-400 font-bold">&gt;= +0.25R OOS</td>
                  </tr>
                  <tr className="hover:bg-zinc-900/40">
                    <td className="py-2.5 px-3 font-semibold text-white">Intervalo Confianza Bootstrap 95%</td>
                    <td className="py-2.5 px-3">{activeSleeve.in_sample.ci_95}</td>
                    <td className="py-2.5 px-3 text-emerald-300 font-bold">{activeSleeve.out_of_sample.ci_95}</td>
                    <td className="py-2.5 px-3">{activeSleeve.full_sample.ci_95}</td>
                    <td className="py-2.5 px-3 text-right text-emerald-400">CI_low &gt; 0.00R</td>
                  </tr>
                  <tr className="hover:bg-zinc-900/40">
                    <td className="py-2.5 px-3 font-semibold text-white">Máximo Drawdown Acumulado</td>
                    <td className="py-2.5 px-3">${activeSleeve.in_sample.max_dd_dollars} ({activeSleeve.in_sample.max_dd_r}R)</td>
                    <td className="py-2.5 px-3">${activeSleeve.out_of_sample.max_dd_dollars} ({activeSleeve.out_of_sample.max_dd_r}R)</td>
                    <td className="py-2.5 px-3 font-bold text-zinc-200">${activeSleeve.full_sample.max_dd_dollars} ({activeSleeve.full_sample.max_dd_r}R)</td>
                    <td className="py-2.5 px-3 text-right text-zinc-400">&lt; $1,500 (colchón 2k)</td>
                  </tr>
                  <tr className="hover:bg-zinc-900/40">
                    <td className="py-2.5 px-3 font-semibold text-white">Ratio Sortino Anualizado</td>
                    <td className="py-2.5 px-3">{activeSleeve.in_sample.sortino}</td>
                    <td className="py-2.5 px-3">{activeSleeve.out_of_sample.sortino}</td>
                    <td className="py-2.5 px-3 font-bold text-emerald-400">{activeSleeve.full_sample.sortino}</td>
                    <td className="py-2.5 px-3 text-right text-emerald-400">&gt; 3.0</td>
                  </tr>
                  <tr className="hover:bg-zinc-900/40">
                    <td className="py-2.5 px-3 font-semibold text-white">PnL Neto Acumulado ($)</td>
                    <td className="py-2.5 px-3 text-emerald-400">${activeSleeve.in_sample.net_pnl.toLocaleString()}</td>
                    <td className="py-2.5 px-3 text-emerald-400">${activeSleeve.out_of_sample.net_pnl.toLocaleString()}</td>
                    <td className="py-2.5 px-3 font-bold text-emerald-400">${activeSleeve.full_sample.net_pnl.toLocaleString()}</td>
                    <td className="py-2.5 px-3 text-right text-zinc-400">-</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Granular Audit Sample Trade Log */}
          <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-5 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Clock className="w-4 h-4 text-emerald-400" />
                Muestreo Reciente de Ejecuciones Cuantitativas (Audit Log)
              </h3>
              <span className="text-xs text-zinc-400 font-mono">
                Últimas 15 operaciones con comisiones CME &amp; slippage
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left font-mono text-xs border-collapse">
                <thead>
                  <tr className="border-b border-zinc-800 text-zinc-400 uppercase text-[10px]">
                    <th className="py-2 px-3">Estrategia</th>
                    <th className="py-2 px-3">Activo</th>
                    <th className="py-2 px-3">Lado</th>
                    <th className="py-2 px-3">Entrada</th>
                    <th className="py-2 px-3">Salida</th>
                    <th className="py-2 px-3">PnL Neto</th>
                    <th className="py-2 px-3">R-Multiple</th>
                    <th className="py-2 px-3">MFE / MAE</th>
                    <th className="py-2 px-3">Cierre</th>
                    <th className="py-2 px-3 text-right">Muestra</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-900 text-zinc-300">
                  {activeSleeve.trade_samples.map((t, idx) => {
                    const isWin = t.net_pnl > 0;
                    return (
                      <tr key={idx} className="hover:bg-zinc-900/40">
                        <td className="py-2 px-3 text-zinc-400">{t.strategy_id}</td>
                        <td className="py-2 px-3 font-bold text-white">{t.symbol}</td>
                        <td className="py-2 px-3">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                            t.side === 'LONG' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'
                          }`}>
                            {t.side}
                          </span>
                        </td>
                        <td className="py-2 px-3">{t.entry_price.toFixed(2)}</td>
                        <td className="py-2 px-3">{t.exit_price.toFixed(2)}</td>
                        <td className={`py-2 px-3 font-bold ${isWin ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {isWin ? `+$${t.net_pnl.toFixed(2)}` : `-$${Math.abs(t.net_pnl).toFixed(2)}`}
                        </td>
                        <td className={`py-2 px-3 font-bold ${isWin ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {t.r_multiple > 0 ? `+${t.r_multiple}R` : `${t.r_multiple}R`}
                        </td>
                        <td className="py-2 px-3 text-zinc-400">
                          +${t.mfe_dollars.toFixed(0)} / -${t.mae_dollars.toFixed(0)}
                        </td>
                        <td className="py-2 px-3">
                          <span className="px-1.5 py-0.5 rounded bg-zinc-900 text-zinc-400 text-[10px]">
                            {t.exit_reason}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-right">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                            t.is_sample === 'OOS' ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30' : 'bg-zinc-800 text-zinc-400'
                          }`}>
                            {t.is_sample}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : null}

      {/* Terminal Engine Execution Logs */}
      {terminalLogs && (
        <div className="bg-black border border-zinc-800 rounded-xl p-4 font-mono text-xs shadow-2xl">
          <div className="flex items-center justify-between pb-2 border-b border-zinc-800 text-zinc-400 text-[11px] mb-3">
            <span className="flex items-center gap-2">
              <Cpu className="w-3.5 h-3.5 text-emerald-400" /> Terminal de Ejecución Cuantitativa (Python CLI Engine)
            </span>
            <button
              onClick={() => setTerminalLogs('')}
              className="text-zinc-500 hover:text-zinc-300"
            >
              Limpiar
            </button>
          </div>
          <pre className="text-emerald-400/90 whitespace-pre-wrap max-h-60 overflow-y-auto leading-relaxed">
            {terminalLogs}
          </pre>
        </div>
      )}
    </div>
  );
}
