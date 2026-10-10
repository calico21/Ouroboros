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
  Cpu
} from 'lucide-react';

interface MetricSet {
  total_trades: number;
  win_rate: number;
  profit_factor: number;
  expectancy_r: number;
  ci_95: string;
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

export default function Batch1DiscoveryView() {
  const [report, setReport] = useState<DiscoveryReport | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [running, setRunning] = useState<boolean>(false);
  const [selectedKey, setSelectedKey] = useState<string>('portfolio');
  const [hoveredStep, setHoveredStep] = useState<number | null>(null);
  const [terminalLogs, setTerminalLogs] = useState<string>('');

  const fetchReport = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/batch1/report');
      const data = await res.json();
      if (data.success && data.report) {
        setReport(data.report);
      }
    } catch (err) {
      console.error('Failed to load batch 1 report:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReport();
  }, []);

  const handleRunAudit = async () => {
    try {
      setRunning(true);
      setTerminalLogs('Ejecutando motor de descubrimiento masivo y 50,000 paths Monte Carlo...');
      const res = await fetch('/api/batch1/run', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        if (data.report) setReport(data.report);
        if (data.stdout) setTerminalLogs(data.stdout);
      } else {
        setTerminalLogs(`Error: ${data.error || 'Execution failed'}`);
      }
    } catch (err: any) {
      setTerminalLogs(`Error de red: ${err.message}`);
    } finally {
      setRunning(false);
    }
  };

  if (loading && !report) {
    return (
      <div className="flex flex-col items-center justify-center p-16 space-y-4">
        <RefreshCw className="w-8 h-8 text-neutral-400 animate-spin" />
        <span className="text-sm font-medium text-neutral-400">Cargando telemetría de descubrimiento Batch 1...</span>
      </div>
    );
  }

  const currentSleeve = report?.sleeves[selectedKey];

  return (
    <div className="space-y-6">
      {/* Top Banner & Account Rules KPI Strip */}
      <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-neutral-800">
          <div>
            <div className="flex items-center gap-2 text-xs text-neutral-400 mb-1">
              <span>Apex Trader Funding 50k Rig</span>
              <span aria-hidden="true">·</span>
              <span>Vectorized Discovery</span>
              <span aria-hidden="true">·</span>
              <span>50,000 Monte Carlo Paths</span>
            </div>
            <h2 className="text-xl font-bold tracking-tight text-white">
              TEST MASIVO: BATCH 1 — Auditoría Forense y Monte Carlo Ratchet
            </h2>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleRunAudit}
              disabled={running}
              className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white rounded-lg transition-colors whitespace-nowrap ${
                running ? 'bg-neutral-700 cursor-not-allowed' : 'bg-emerald-600 hover:bg-emerald-500'
              }`}
            >
              {running ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Calculando 50,000 Paths...</span>
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 fill-current" />
                  <span>Ejecutar Test Batch 1</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Rig Invariants KPI Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-6">
          <div className="bg-neutral-950/60 border border-neutral-800/80 p-3.5 rounded-lg">
            <div className="text-xs text-neutral-400">Capital Nominal</div>
            <div className="text-lg font-bold font-mono tabular-nums text-white mt-0.5">$50,000.00</div>
            <div className="text-[11px] text-neutral-500 mt-1">Colchón Real: $2,000.00</div>
          </div>

          <div className="bg-neutral-950/60 border border-neutral-800/80 p-3.5 rounded-lg">
            <div className="text-xs text-neutral-400">Profit Target Apex</div>
            <div className="text-lg font-bold font-mono tabular-nums text-emerald-400 mt-0.5">$53,000.00</div>
            <div className="text-[11px] text-neutral-500 mt-1">Hurdle: +$3,000.00</div>
          </div>

          <div className="bg-neutral-950/60 border border-neutral-800/80 p-3.5 rounded-lg">
            <div className="text-xs text-neutral-400">Congelación Apex ($52.6k)</div>
            <div className="text-lg font-bold font-mono tabular-nums text-amber-400 mt-0.5">$50,100.00</div>
            <div className="text-[11px] text-neutral-500 mt-1">Floor permanente $2.5k cushion</div>
          </div>

          <div className="bg-neutral-950/60 border border-neutral-800/80 p-3.5 rounded-lg">
            <div className="text-xs text-neutral-400">Fricción CME Deductible</div>
            <div className="text-lg font-bold font-mono tabular-nums text-neutral-300 mt-0.5">$1.24 RT + 1 tick</div>
            <div className="text-[11px] text-neutral-500 mt-1">Resolución Stop-First</div>
          </div>
        </div>
      </div>

      {/* Sleeve Selector Tabs */}
      <div className="flex items-center gap-2 overflow-x-auto p-1 bg-neutral-900 border border-neutral-800 rounded-lg">
        {[
          { id: 'portfolio', label: 'Portfolio Multiactivo (Sleeves 1+2+3)', tag: 'Ensemble' },
          { id: 'sleeve_1', label: 'Sleeve 1: Macro Regime Pullback (MYM/MES)', tag: 'Swing' },
          { id: 'sleeve_2', label: 'Sleeve 2: Session Liquidity Sweep & VWAP (MNQ)', tag: 'Auction' },
          { id: 'sleeve_3', label: 'Sleeve 3: Squeeze Expansion Breakout (MES/MNQ)', tag: 'Volatility' },
        ].map((tab) => {
          const isSelected = selectedKey === tab.id;
          const slData = report?.sleeves[tab.id];
          const isApproved = slData?.monte_carlo.verdict.includes('APROBADA');

          return (
            <button
              key={tab.id}
              onClick={() => setSelectedKey(tab.id)}
              className={`flex items-center gap-2 px-4 py-2 text-xs font-medium rounded-md transition-all whitespace-nowrap ${
                isSelected
                  ? 'bg-neutral-800 text-white shadow-sm'
                  : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/40'
              }`}
            >
              <span>{tab.label}</span>
              <span className="text-[10px] text-neutral-500 font-mono">[{tab.tag}]</span>
              {slData && (
                <span
                  className={`text-[10px] font-mono px-1.5 py-0.2 rounded ${
                    isApproved ? 'bg-emerald-950/80 text-emerald-400 border border-emerald-800/60' : 'bg-red-950/80 text-red-400 border border-red-800/60'
                  }`}
                >
                  {isApproved ? 'APROBADA' : 'RECHAZADA'}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {currentSleeve && (
        <div className="space-y-6">
          {/* Executive Verdict Banner */}
          <div
            className={`border rounded-xl p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 ${
              currentSleeve.monte_carlo.verdict.includes('APROBADA')
                ? 'bg-emerald-950/30 border-emerald-800/60 text-emerald-200'
                : 'bg-red-950/30 border-red-800/60 text-red-200'
            }`}
          >
            <div className="flex items-center gap-3">
              {currentSleeve.monte_carlo.verdict.includes('APROBADA') ? (
                <CheckCircle2 className="w-6 h-6 text-emerald-400 shrink-0" />
              ) : (
                <XCircle className="w-6 h-6 text-red-400 shrink-0" />
              )}
              <div>
                <div className="text-xs uppercase tracking-wider text-neutral-400">Veredicto Oficial Apex 50k</div>
                <div className="text-lg font-bold text-white mt-0.5">{currentSleeve.monte_carlo.verdict}</div>
              </div>
            </div>

            <div className="flex items-center gap-6 text-xs font-mono tabular-nums">
              <div>
                <span className="text-neutral-400">P(Pass): </span>
                <span className="text-emerald-400 font-bold">{currentSleeve.monte_carlo.p_pass}%</span>
              </div>
              <div>
                <span className="text-neutral-400">P(Breach): </span>
                <span
                  className={`font-bold ${
                    currentSleeve.monte_carlo.p_breach < 5.0 ? 'text-emerald-400' : 'text-red-400'
                  }`}
                >
                  {currentSleeve.monte_carlo.p_breach}%
                </span>
                <span className="text-neutral-500 text-[10px]"> (Límite: &lt;5%)</span>
              </div>
              <div>
                <span className="text-neutral-400">P50 Mediana: </span>
                <span className="text-white font-bold">{currentSleeve.monte_carlo.p50_trades} trades</span>
                <span className="text-neutral-400"> ({currentSleeve.monte_carlo.median_months} meses)</span>
              </div>
            </div>
          </div>

          {/* Interactive 50,000 Monte Carlo Ratchet Visualizer */}
          <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
            <div className="flex items-center justify-between pb-4 border-b border-neutral-800 mb-4">
              <div>
                <h3 className="text-sm font-semibold text-white">
                  Simulación Monte Carlo Apex (50,000 Paths MTM Ratchet)
                </h3>
                <p className="text-xs text-neutral-400 mt-0.5">
                  Trayectorias muestreadas con Trailing Floor dinámico intradiario y congelación permanente en $50,100
                </p>
              </div>

              <div className="flex items-center gap-4 text-xs font-mono text-neutral-400">
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-0.5 bg-emerald-400 inline-block" /> Target ($53,000)
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-0.5 bg-amber-400 inline-block" /> Freeze Floor ($50,100)
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-0.5 bg-red-400 inline-block" /> Breach Initial ($48,000)
                </span>
              </div>
            </div>

            {/* SVG Trajectory Chart */}
            <div className="relative w-full h-80 bg-neutral-950/80 rounded-lg p-3 border border-neutral-800 overflow-hidden">
              <svg className="w-full h-full" viewBox="0 0 800 300" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="targetGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#10b981" stopOpacity="0.2" />
                    <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
                  </linearGradient>
                </defs>

                {/* Grid Lines */}
                <line x1="0" y1="30" x2="800" y2="30" stroke="#10b981" strokeDasharray="3 3" strokeWidth="1" />
                <line x1="0" y1="130" x2="800" y2="130" stroke="#f59e0b" strokeDasharray="3 3" strokeWidth="1" />
                <line x1="0" y1="150" x2="800" y2="150" stroke="#52525b" strokeDasharray="2 2" strokeWidth="0.8" />
                <line x1="0" y1="270" x2="800" y2="270" stroke="#ef4444" strokeDasharray="3 3" strokeWidth="1" />

                {/* Y-Axis Labels */}
                <text x="10" y="25" fill="#10b981" fontSize="10" fontFamily="monospace">
                  $53,000 Target (+3k)
                </text>
                <text x="10" y="125" fill="#f59e0b" fontSize="10" fontFamily="monospace">
                  $50,100 Freeze Floor
                </text>
                <text x="10" y="145" fill="#a1a1aa" fontSize="10" fontFamily="monospace">
                  $50,000 Balance Inicial
                </text>
                <text x="10" y="265" fill="#ef4444" fontSize="10" fontFamily="monospace">
                  $48,000 Suelo Inicial (Breach)
                </text>

                {/* Sample Paths */}
                {currentSleeve.monte_carlo.sample_curves.map((curve, idx) => {
                  const pts = curve.equity.map((val, stepIdx) => {
                    const x = (stepIdx / 60) * 800;
                    // Scale: y=30 for 53000, y=270 for 48000 (range 5000)
                    const normalized = (val - 48000) / 5500;
                    const y = Math.max(10, Math.min(290, 270 - normalized * 240));
                    return `${x},${y}`;
                  }).join(' ');

                  const floorPts = curve.floor.map((val, stepIdx) => {
                    const x = (stepIdx / 60) * 800;
                    const normalized = (val - 48000) / 5500;
                    const y = Math.max(10, Math.min(290, 270 - normalized * 240));
                    return `${x},${y}`;
                  }).join(' ');

                  return (
                    <g key={idx}>
                      <polyline
                        points={pts}
                        fill="none"
                        stroke={curve.passed ? '#34d399' : curve.breached ? '#f87171' : '#60a5fa'}
                        strokeWidth="1"
                        strokeOpacity="0.35"
                      />
                      <polyline
                        points={floorPts}
                        fill="none"
                        stroke="#f59e0b"
                        strokeWidth="0.8"
                        strokeOpacity="0.2"
                      />
                    </g>
                  );
                })}
              </svg>
            </div>
          </div>

          {/* Forensic Audit Tearsheet Table (IS vs OOS) */}
          <div className="bg-neutral-900 border border-neutral-800 rounded-xl overflow-hidden">
            <div className="p-5 border-b border-neutral-800">
              <h3 className="text-sm font-semibold text-white">Tabla de Auditoría Forense Econométrica</h3>
              <p className="text-xs text-neutral-400 mt-0.5">
                Partición temporal estricta: In-Sample (2022-2023) vs Out-of-Sample (2024-2026) con deducción completa de fricción CME
              </p>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-neutral-950/80 text-neutral-400 border-b border-neutral-800">
                    <th className="py-3 px-4 font-semibold">Métrica de Auditoría</th>
                    <th className="py-3 px-4 font-semibold">In-Sample (2022–2023)</th>
                    <th className="py-3 px-4 font-semibold">Out-of-Sample (2024–2026)</th>
                    <th className="py-3 px-4 font-semibold">Muestra Completa</th>
                    <th className="py-3 px-4 font-semibold">Criterio Institucional</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-800/60 font-mono tabular-nums text-neutral-300">
                  <tr className="hover:bg-neutral-800/30">
                    <td className="py-3 px-4 font-sans text-neutral-200">Operaciones Totales (N)</td>
                    <td className="py-3 px-4 text-white font-bold">{currentSleeve.in_sample.total_trades}</td>
                    <td className="py-3 px-4 text-white font-bold">{currentSleeve.out_of_sample.total_trades}</td>
                    <td className="py-3 px-4 text-white">{currentSleeve.full_sample.total_trades}</td>
                    <td className="py-3 px-4 font-sans text-neutral-400">Mínimo N ≥ 50 operaciones</td>
                  </tr>

                  <tr className="hover:bg-neutral-800/30">
                    <td className="py-3 px-4 font-sans text-neutral-200">Win Rate (%)</td>
                    <td className="py-3 px-4">{currentSleeve.in_sample.win_rate}%</td>
                    <td className="py-3 px-4">{currentSleeve.out_of_sample.win_rate}%</td>
                    <td className="py-3 px-4 text-white font-semibold">{currentSleeve.full_sample.win_rate}%</td>
                    <td className="py-3 px-4 font-sans text-neutral-400">Estabilidad temporal</td>
                  </tr>

                  <tr className="hover:bg-neutral-800/30">
                    <td className="py-3 px-4 font-sans text-neutral-200">Profit Factor (Neto de Fricción)</td>
                    <td className="py-3 px-4">{currentSleeve.in_sample.profit_factor}</td>
                    <td className="py-3 px-4">{currentSleeve.out_of_sample.profit_factor}</td>
                    <td className="py-3 px-4 text-emerald-400 font-semibold">{currentSleeve.full_sample.profit_factor}</td>
                    <td className="py-3 px-4 font-sans text-neutral-400">PF &gt; 1.0 post-comisiones</td>
                  </tr>

                  <tr className="hover:bg-neutral-800/30">
                    <td className="py-3 px-4 font-sans text-neutral-200">Expectativa E[R]</td>
                    <td className="py-3 px-4">{currentSleeve.in_sample.expectancy_r} R</td>
                    <td className="py-3 px-4">{currentSleeve.out_of_sample.expectancy_r} R</td>
                    <td className="py-3 px-4 text-white font-semibold">{currentSleeve.full_sample.expectancy_r} R</td>
                    <td className="py-3 px-4 font-sans text-neutral-400">E[R] &gt; 0.0R</td>
                  </tr>

                  <tr className="hover:bg-neutral-800/30">
                    <td className="py-3 px-4 font-sans text-neutral-200">Bootstrap 95% CI de E[R]</td>
                    <td className="py-3 px-4 text-neutral-400">{currentSleeve.in_sample.ci_95}</td>
                    <td className="py-3 px-4 text-neutral-400">{currentSleeve.out_of_sample.ci_95}</td>
                    <td className="py-3 px-4 text-neutral-300">{currentSleeve.full_sample.ci_95}</td>
                    <td className="py-3 px-4 font-sans text-neutral-400">Significancia estadística</td>
                  </tr>

                  <tr className="hover:bg-neutral-800/30">
                    <td className="py-3 px-4 font-sans text-neutral-200">Max Drawdown ($ / R)</td>
                    <td className="py-3 px-4">${currentSleeve.in_sample.max_dd_dollars} ({currentSleeve.in_sample.max_dd_r}R)</td>
                    <td className="py-3 px-4">${currentSleeve.out_of_sample.max_dd_dollars} ({currentSleeve.out_of_sample.max_dd_r}R)</td>
                    <td className="py-3 px-4 text-red-400 font-semibold">${currentSleeve.full_sample.max_dd_dollars} ({currentSleeve.full_sample.max_dd_r}R)</td>
                    <td className="py-3 px-4 font-sans text-neutral-400">MaxDD &lt; $2,000 en 1R</td>
                  </tr>

                  <tr className="hover:bg-neutral-800/30">
                    <td className="py-3 px-4 font-sans text-neutral-200">Ratio Sortino Anualizado</td>
                    <td className="py-3 px-4">{currentSleeve.in_sample.sortino}</td>
                    <td className="py-3 px-4">{currentSleeve.out_of_sample.sortino}</td>
                    <td className="py-3 px-4 text-emerald-400 font-semibold">{currentSleeve.full_sample.sortino}</td>
                    <td className="py-3 px-4 font-sans text-neutral-400">Penalización de volatilidad negativa</td>
                  </tr>

                  <tr className="hover:bg-neutral-800/30">
                    <td className="py-3 px-4 font-sans text-neutral-200">PnL Neto Acumulado ($)</td>
                    <td className="py-3 px-4">${currentSleeve.in_sample.net_pnl.toLocaleString()}</td>
                    <td className="py-3 px-4">${currentSleeve.out_of_sample.net_pnl.toLocaleString()}</td>
                    <td className="py-3 px-4 text-emerald-400 font-bold">${currentSleeve.full_sample.net_pnl.toLocaleString()}</td>
                    <td className="py-3 px-4 font-sans text-neutral-400">Ganancia real post-fricción</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Trade Log Samples */}
          <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-5">
            <h3 className="text-sm font-semibold text-white mb-3">Muestra de Operaciones Ejecutadas Recientes</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-neutral-800 text-neutral-400">
                    <th className="py-2 px-3">Fecha/Hora</th>
                    <th className="py-2 px-3">Activo</th>
                    <th className="py-2 px-3">Lado</th>
                    <th className="py-2 px-3">Entrada</th>
                    <th className="py-2 px-3">Salida</th>
                    <th className="py-2 px-3">Net PnL</th>
                    <th className="py-2 px-3">R-Multiple</th>
                    <th className="py-2 px-3">Razón Salida</th>
                    <th className="py-2 px-3">Partición</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-800/50 font-mono tabular-nums text-neutral-300">
                  {currentSleeve.trade_samples.map((t, idx) => (
                    <tr key={idx} className="hover:bg-neutral-800/30">
                      <td className="py-2 px-3 text-neutral-400">{t.entry_time.slice(0, 16)}</td>
                      <td className="py-2 px-3 text-white font-medium">{t.symbol}</td>
                      <td className="py-2 px-3">
                        <span className={t.side === 'LONG' ? 'text-emerald-400' : 'text-amber-400'}>{t.side}</span>
                      </td>
                      <td className="py-2 px-3">{t.entry_price.toFixed(2)}</td>
                      <td className="py-2 px-3">{t.exit_price.toFixed(2)}</td>
                      <td className={`py-2 px-3 font-semibold ${t.net_pnl > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        ${t.net_pnl.toFixed(2)}
                      </td>
                      <td className={`py-2 px-3 ${t.r_multiple > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {t.r_multiple.toFixed(2)}R
                      </td>
                      <td className="py-2 px-3 font-sans text-neutral-400">{t.exit_reason}</td>
                      <td className="py-2 px-3 font-sans">
                        <span className={t.is_sample === 'OOS' ? 'text-amber-400 font-semibold' : 'text-neutral-500'}>
                          {t.is_sample}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Terminal Output if run triggered */}
      {terminalLogs && (
        <div className="bg-neutral-950 border border-neutral-800 rounded-xl p-4 font-mono text-xs text-neutral-300">
          <div className="flex items-center gap-2 pb-2 mb-2 border-b border-neutral-800 text-neutral-500 text-[11px]">
            <Cpu className="w-3.5 h-3.5" />
            <span>Salida de Consola: scripts/run_batch1_discovery.py</span>
          </div>
          <pre className="whitespace-pre-wrap overflow-x-auto max-h-48 text-[11px] text-neutral-400 leading-relaxed">
            {terminalLogs}
          </pre>
        </div>
      )}
    </div>
  );
}
