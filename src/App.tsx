import React, { useState, useEffect } from 'react';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ChevronRight,
  Code2,
  Compass,
  Cpu,
  Download,
  Flame,
  Layers,
  Play,
  RefreshCw,
  Sliders,
  Terminal as TerminalIcon,
  TrendingDown,
  TrendingUp,
  XCircle,
  Zap,
} from 'lucide-react';

interface StrategyInfo {
  name: string;
  configYaml: string;
  readme: string;
}

interface LeaderboardRow {
  Strategy: string;
  Trades: string;
  'Win Rate %': string;
  'Net PnL ($)': string;
  'Profit Factor': string;
  'Expectancy (R)': string;
  'Drift Ratio (x)': string;
  'P(Pass) %': string;
  'P(Breach) %': string;
  'Crit Slip (S*)': string;
  Status: string;
}

export default function App() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [selectedStrategy, setSelectedStrategy] = useState<string>('orb_5m_binary');
  const [propFirm, setPropFirm] = useState<string>('configs/prop_firm/apex_50k_trailing_mtm.yaml');
  const [execution, setExecution] = useState<string>('configs/execution/cme_globex_default.yaml');
  const [instrument, setInstrument] = useState<string>('configs/instruments/mnq.yaml');
  const [activeTab, setActiveTab] = useState<'dashboard' | 'deathtree' | 'zoo' | 'friction' | 'regime' | 'code' | 'logs'>('dashboard');

  const [loading, setLoading] = useState<boolean>(false);
  const [auditData, setAuditData] = useState<any>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderboardRow[]>([]);
  const [terminalOutput, setTerminalOutput] = useState<string>('');
  const [testOutput, setTestOutput] = useState<string>('');
  const [activeVisualTab, setActiveVisualTab] = useState<'master' | 'cone' | 'decay' | 'excursion'>('master');

  // Load initial data
  useEffect(() => {
    fetchStrategies();
    loadArtifact('orb_5m_binary');
    fetchLeaderboard();
  }, []);

  const fetchStrategies = async () => {
    try {
      const res = await fetch('/api/strategies');
      const data = await res.json();
      if (data.strategies) {
        setStrategies(data.strategies);
      }
    } catch (err) {
      console.error('Failed to fetch strategies:', err);
    }
  };

  const loadArtifact = async (strat: string) => {
    try {
      const res = await fetch(`/api/artifacts/${strat}`);
      if (res.ok) {
        const data = await res.json();
        setAuditData(data);
      }
    } catch (err) {
      console.error('Failed to load artifact:', err);
    }
  };

  const fetchLeaderboard = async () => {
    try {
      const res = await fetch('/api/benchmark');
      const data = await res.json();
      if (data.leaderboard) {
        setLeaderboard(data.leaderboard);
      }
    } catch (err) {
      console.error('Failed to fetch leaderboard:', err);
    }
  };

  const handleRunAudit = async () => {
    setLoading(true);
    setTerminalOutput(`[AlphaForge] Initializing audit for ${selectedStrategy}...\n`);
    try {
      const res = await fetch('/api/run-audit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          strategy: selectedStrategy,
          propFirm,
          execution,
          instrument,
          timeframe: '5m',
          mcIterations: 10000,
        }),
      });
      const data = await res.json();
      if (data.success) {
        setAuditData(data.metrics);
        setTerminalOutput(data.stdout);
        fetchLeaderboard();
      } else {
        setTerminalOutput(`Error: ${data.error}\n${data.stderr || ''}`);
      }
    } catch (err: any) {
      setTerminalOutput(`Network Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleRunTests = async () => {
    setLoading(true);
    setActiveTab('logs');
    try {
      const res = await fetch('/api/run-tests');
      const data = await res.json();
      setTestOutput(data.output);
    } catch (err: any) {
      setTestOutput(`Failed to run tests: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const summary = auditData?.summary || {};
  const excursion = auditData?.excursion || {};
  const lossTaxonomy = auditData?.loss_taxonomy || {};
  const friction = auditData?.friction_frontier || {};
  const propStatus = auditData?.prop_firm || {};
  const regimes = auditData?.regimes || {};
  const monteCarlo = auditData?.monte_carlo || {};

  const driftRatio = excursion.drift_ratio ?? 0;
  const isDisqualified = excursion.is_alpha_disqualified ?? true;
  const isPass = propStatus.status === 'PASSED';
  const isBreached = propStatus.status?.includes('BREACH');

  return (
    <div className="min-h-screen bg-[#0B0F19] text-gray-100 flex flex-col font-sans selection:bg-cyan-500 selection:text-black">
      {/* Top Institutional Header */}
      <header className="border-b border-gray-800 bg-[#111827]/90 backdrop-blur px-6 py-3.5 flex flex-wrap items-center justify-between gap-4 sticky top-0 z-50">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded bg-gradient-to-br from-cyan-500 to-emerald-500 flex items-center justify-center font-black text-black text-sm shadow-lg shadow-cyan-500/20">
            AF
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold tracking-wider text-sm text-gray-100">ALPHAFORGE</span>
              <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-gray-800 text-cyan-400 border border-gray-700">
                v2.4 INSTITUTIONAL RIG
              </span>
            </div>
            <p className="text-[11px] text-gray-400 font-mono">
              CME Globex Futures // Intraday MTM Trailing Ratchet Diagnostics
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Strategy Select */}
          <div className="flex items-center bg-[#1A2234] border border-gray-700 rounded px-2.5 py-1 text-xs">
            <span className="text-gray-400 mr-2 font-mono text-[11px]">ALPHA:</span>
            <select
              value={selectedStrategy}
              onChange={(e) => {
                setSelectedStrategy(e.target.value);
                loadArtifact(e.target.value);
              }}
              className="bg-transparent text-cyan-400 font-semibold focus:outline-none cursor-pointer"
            >
              {strategies.map((s) => (
                <option key={s.name} value={s.name} className="bg-gray-900 text-gray-200">
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          {/* Prop Firm Select */}
          <div className="flex items-center bg-[#1A2234] border border-gray-700 rounded px-2.5 py-1 text-xs">
            <span className="text-gray-400 mr-2 font-mono text-[11px]">PROP EVAL:</span>
            <select
              value={propFirm}
              onChange={(e) => setPropFirm(e.target.value)}
              className="bg-transparent text-emerald-400 font-semibold focus:outline-none cursor-pointer"
            >
              <option value="configs/prop_firm/apex_50k_trailing_mtm.yaml" className="bg-gray-900 text-gray-200">
                Apex 50k Trailing MTM ($2.5k)
              </option>
              <option value="configs/prop_firm/topstep_50k_eod.yaml" className="bg-gray-900 text-gray-200">
                Topstep 50k EOD ($2k)
              </option>
              <option value="configs/prop_firm/mff_50k_static.yaml" className="bg-gray-900 text-gray-200">
                MFFU 50k Static ($2k)
              </option>
            </select>
          </div>

          {/* Friction Select */}
          <div className="flex items-center bg-[#1A2234] border border-gray-700 rounded px-2.5 py-1 text-xs">
            <span className="text-gray-400 mr-2 font-mono text-[11px]">FRICTION:</span>
            <select
              value={execution}
              onChange={(e) => setExecution(e.target.value)}
              className="bg-transparent text-amber-400 font-semibold focus:outline-none cursor-pointer"
            >
              <option value="configs/execution/cme_globex_default.yaml" className="bg-gray-900 text-gray-200">
                CME Globex Default (1.0 tick slip + trade-through)
              </option>
              <option value="configs/execution/zero_friction_audit.yaml" className="bg-gray-900 text-gray-200">
                Zero Friction Audit (0.0 slip)
              </option>
            </select>
          </div>

          {/* Buttons */}
          <button
            onClick={handleRunAudit}
            disabled={loading}
            className="flex items-center gap-1.5 bg-cyan-500 hover:bg-cyan-400 text-black px-3 py-1.5 rounded text-xs font-bold transition shadow-lg shadow-cyan-500/20 disabled:opacity-50 cursor-pointer"
          >
            {loading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5 fill-black" />}
            RUN AUDIT
          </button>

          <button
            onClick={handleRunTests}
            disabled={loading}
            className="flex items-center gap-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 px-2.5 py-1.5 rounded text-xs font-mono border border-gray-700 transition cursor-pointer"
          >
            <TerminalIcon className="w-3.5 h-3.5 text-gray-400" />
            PYTEST RIG
          </button>
        </div>
      </header>

      {/* KPI Ticker Ribbon */}
      <div className="bg-[#0e1422] border-b border-gray-800/80 px-6 py-2.5 grid grid-cols-2 sm:grid-cols-4 md:grid-cols-8 gap-3 text-xs">
        <div className="border-r border-gray-800/80 pr-2">
          <div className="text-[10px] text-gray-400 uppercase font-mono">Realized Net PnL</div>
          <div className={`font-mono font-bold text-sm ${(summary.total_net_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            ${(summary.total_net_pnl || 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </div>
        </div>

        <div className="border-r border-gray-800/80 pr-2">
          <div className="text-[10px] text-gray-400 uppercase font-mono">Directional Drift</div>
          <div className="flex items-center gap-1 font-mono font-bold text-sm">
            <span className={driftRatio >= 1.5 ? 'text-emerald-400' : 'text-red-400'}>
              {driftRatio.toFixed(2)}x
            </span>
            <span className={`text-[9px] px-1 rounded uppercase ${driftRatio >= 1.5 ? 'bg-emerald-950 text-emerald-300' : 'bg-red-950 text-red-300'}`}>
              {driftRatio >= 1.5 ? 'EDGE' : 'DISQUALIFIED'}
            </span>
          </div>
        </div>

        <div className="border-r border-gray-800/80 pr-2">
          <div className="text-[10px] text-gray-400 uppercase font-mono">Win Rate / N</div>
          <div className="font-mono font-bold text-sm text-gray-200">
            {summary.win_rate_pct ?? 0}% <span className="text-gray-500 font-normal">({summary.total_trades ?? 0}T)</span>
          </div>
        </div>

        <div className="border-r border-gray-800/80 pr-2">
          <div className="text-[10px] text-gray-400 uppercase font-mono">Expectancy (R)</div>
          <div className={`font-mono font-bold text-sm ${(summary.expectancy_r || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {(summary.expectancy_r || 0) > 0 ? '+' : ''}{(summary.expectancy_r || 0).toFixed(3)}R
          </div>
        </div>

        <div className="border-r border-gray-800/80 pr-2">
          <div className="text-[10px] text-gray-400 uppercase font-mono">Profit Factor</div>
          <div className="font-mono font-bold text-sm text-amber-400">
            {summary.profit_factor ?? 0}
          </div>
        </div>

        <div className="border-r border-gray-800/80 pr-2">
          <div className="text-[10px] text-gray-400 uppercase font-mono">Critical Slip (S*)</div>
          <div className="font-mono font-bold text-sm text-cyan-400">
            {friction.critical_slippage_s_star ?? 'N/A'} ticks
          </div>
        </div>

        <div className="border-r border-gray-800/80 pr-2">
          <div className="text-[10px] text-gray-400 uppercase font-mono">MC P(Pass) / P(Breach)</div>
          <div className="font-mono font-bold text-sm text-gray-200">
            <span className="text-emerald-400">{monteCarlo.prob_pass_pct ?? 0}%</span> / <span className="text-red-400">{monteCarlo.prob_breach_pct ?? 0}%</span>
          </div>
        </div>

        <div>
          <div className="text-[10px] text-gray-400 uppercase font-mono">Prop Account Status</div>
          <div className="flex items-center gap-1 font-mono font-bold text-xs">
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] ${
                isPass
                  ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                  : isBreached
                  ? 'bg-red-500/20 text-red-400 border border-red-500/40'
                  : 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
              }`}
            >
              {propStatus.status || 'ACTIVE'}
            </span>
          </div>
        </div>
      </div>

      {/* Main Tab Navigation */}
      <div className="border-b border-gray-800 bg-[#111827] px-6 flex items-center gap-1 text-xs font-mono">
        <button
          onClick={() => setActiveTab('dashboard')}
          className={`px-4 py-3 border-b-2 font-semibold flex items-center gap-1.5 transition cursor-pointer ${
            activeTab === 'dashboard'
              ? 'border-cyan-400 text-cyan-400 bg-gray-800/40'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <BarChart3 className="w-4 h-4" />
          EXECUTIVE 6-PANEL DASHBOARD
        </button>

        <button
          onClick={() => setActiveTab('deathtree')}
          className={`px-4 py-3 border-b-2 font-semibold flex items-center gap-1.5 transition cursor-pointer ${
            activeTab === 'deathtree'
              ? 'border-red-400 text-red-400 bg-gray-800/40'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <Flame className="w-4 h-4" />
          THE ALGORITHMIC DEATH TREE
        </button>

        <button
          onClick={() => setActiveTab('zoo')}
          className={`px-4 py-3 border-b-2 font-semibold flex items-center gap-1.5 transition cursor-pointer ${
            activeTab === 'zoo'
              ? 'border-emerald-400 text-emerald-400 bg-gray-800/40'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <Layers className="w-4 h-4" />
          BENCHMARK ZOO LEADERBOARD
        </button>

        <button
          onClick={() => setActiveTab('friction')}
          className={`px-4 py-3 border-b-2 font-semibold flex items-center gap-1.5 transition cursor-pointer ${
            activeTab === 'friction'
              ? 'border-amber-400 text-amber-400 bg-gray-800/40'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <Sliders className="w-4 h-4" />
          FRICTION FRONTIER & S*
        </button>

        <button
          onClick={() => setActiveTab('regime')}
          className={`px-4 py-3 border-b-2 font-semibold flex items-center gap-1.5 transition cursor-pointer ${
            activeTab === 'regime'
              ? 'border-purple-400 text-purple-400 bg-gray-800/40'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <Compass className="w-4 h-4" />
          REGIME ATTRIBUTION
        </button>

        <button
          onClick={() => setActiveTab('code')}
          className={`px-4 py-3 border-b-2 font-semibold flex items-center gap-1.5 transition cursor-pointer ${
            activeTab === 'code'
              ? 'border-cyan-400 text-cyan-400 bg-gray-800/40'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <Code2 className="w-4 h-4" />
          STRATEGY SPEC & ISOLATION
        </button>

        <button
          onClick={() => setActiveTab('logs')}
          className={`px-4 py-3 border-b-2 font-semibold flex items-center gap-1.5 transition cursor-pointer ${
            activeTab === 'logs'
              ? 'border-gray-300 text-gray-200 bg-gray-800/40'
              : 'border-transparent text-gray-400 hover:text-gray-200'
          }`}
        >
          <TerminalIcon className="w-4 h-4" />
          TERMINAL LOGS
        </button>
      </div>

      {/* Main Workspace Body */}
      <main className="flex-1 p-6 overflow-y-auto">
        {/* TAB 1: EXECUTIVE 6-PANEL DASHBOARD & COMPONENT PLOTS */}
        {activeTab === 'dashboard' && (
          <div className="space-y-6">
            {/* Visual View Switcher */}
            <div className="flex items-center justify-between bg-[#111827] border border-gray-800 rounded-lg p-2">
              <div className="flex items-center gap-2 text-xs font-mono">
                <button
                  onClick={() => setActiveVisualTab('master')}
                  className={`px-3 py-1.5 rounded transition ${
                    activeVisualTab === 'master' ? 'bg-cyan-500 text-black font-bold' : 'text-gray-400 hover:text-gray-200'
                  }`}
                >
                  Master 6-Panel Executive Dashboard
                </button>
                <button
                  onClick={() => setActiveVisualTab('cone')}
                  className={`px-3 py-1.5 rounded transition ${
                    activeVisualTab === 'cone' ? 'bg-cyan-500 text-black font-bold' : 'text-gray-400 hover:text-gray-200'
                  }`}
                >
                  Monte Carlo Survival Cone
                </button>
                <button
                  onClick={() => setActiveVisualTab('decay')}
                  className={`px-3 py-1.5 rounded transition ${
                    activeVisualTab === 'decay' ? 'bg-cyan-500 text-black font-bold' : 'text-gray-400 hover:text-gray-200'
                  }`}
                >
                  Slippage Decay Curve (S*)
                </button>
                <button
                  onClick={() => setActiveVisualTab('excursion')}
                  className={`px-3 py-1.5 rounded transition ${
                    activeVisualTab === 'excursion' ? 'bg-cyan-500 text-black font-bold' : 'text-gray-400 hover:text-gray-200'
                  }`}
                >
                  Time-Decay Excursion Profile
                </button>
              </div>

              <div className="text-xs text-gray-400 font-mono flex items-center gap-2">
                <span>Resolution: High-DPI Institutional Vector</span>
              </div>
            </div>

            {/* Render Selected Image */}
            <div className="bg-[#111827] border border-gray-800 rounded-xl p-4 flex flex-col items-center shadow-2xl">
              {activeVisualTab === 'master' && (
                <div className="w-full">
                  <div className="flex items-center justify-between pb-3 mb-3 border-b border-gray-800">
                    <div className="text-sm font-bold tracking-wide text-gray-200 font-mono">
                      MASTER 6-PANEL EXECUTIVE AUDIT // {selectedStrategy.toUpperCase()}
                    </div>
                    <span className="text-xs text-cyan-400 font-mono">
                      Generated at: reports/visuals/dashboards/{selectedStrategy}_master_dashboard.png
                    </span>
                  </div>
                  <img
                    src={`/api/visuals/dashboards/${selectedStrategy}_master_dashboard.png?t=${Date.now()}`}
                    alt="Master Executive Dashboard"
                    className="w-full rounded-lg border border-gray-800/80 shadow-inner max-h-[820px] object-contain mx-auto"
                    onError={(e: any) => {
                      e.target.style.display = 'none';
                    }}
                  />
                </div>
              )}

              {activeVisualTab === 'cone' && (
                <div className="w-full">
                  <div className="flex items-center justify-between pb-3 mb-3 border-b border-gray-800">
                    <div className="text-sm font-bold tracking-wide text-gray-200 font-mono">
                      MONTE CARLO EQUITY PERCENTILE SURVIVAL CONE (10,000 PATHS)
                    </div>
                    <span className="text-xs text-cyan-400 font-mono">
                      Path-Dependent MTM Trailing Floor Envelope
                    </span>
                  </div>
                  <img
                    src={`/api/visuals/components/${selectedStrategy}_monte_carlo_cone.png?t=${Date.now()}`}
                    alt="Monte Carlo Survival Cone"
                    className="w-full rounded-lg border border-gray-800/80 shadow-inner max-h-[700px] object-contain mx-auto"
                  />
                </div>
              )}

              {activeVisualTab === 'decay' && (
                <div className="w-full">
                  <div className="flex items-center justify-between pb-3 mb-3 border-b border-gray-800">
                    <div className="text-sm font-bold tracking-wide text-gray-200 font-mono">
                      FRICTION FRONTIER // SLIPPAGE DECAY CURVE & S* BREAK-EVEN
                    </div>
                    <span className="text-xs text-amber-400 font-mono">
                      Critical Slippage: {friction.critical_slippage_s_star} ticks
                    </span>
                  </div>
                  <img
                    src={`/api/visuals/components/${selectedStrategy}_slippage_decay.png?t=${Date.now()}`}
                    alt="Slippage Decay Curve"
                    className="w-full rounded-lg border border-gray-800/80 shadow-inner max-h-[700px] object-contain mx-auto"
                  />
                </div>
              )}

              {activeVisualTab === 'excursion' && (
                <div className="w-full">
                  <div className="flex items-center justify-between pb-3 mb-3 border-b border-gray-800">
                    <div className="text-sm font-bold tracking-wide text-gray-200 font-mono">
                      TIME-DECAY EXCURSION PROFILE // HOLDING TIME (BARS) VS MFE_R
                    </div>
                    <span className="text-xs text-purple-400 font-mono">
                      Median Time to Peak: {excursion.median_time_to_peak_mfe} bars
                    </span>
                  </div>
                  <img
                    src={`/api/visuals/components/${selectedStrategy}_time_decay_excursion.png?t=${Date.now()}`}
                    alt="Time Decay Excursion"
                    className="w-full rounded-lg border border-gray-800/80 shadow-inner max-h-[700px] object-contain mx-auto"
                  />
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 2: THE ALGORITHMIC DEATH TREE */}
        {activeTab === 'deathtree' && (
          <div className="space-y-6">
            <div className="bg-[#111827] border border-gray-800 rounded-xl p-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-base font-bold text-gray-100 flex items-center gap-2 font-mono">
                    <Flame className="w-5 h-5 text-red-400" />
                    THE ALGORITHMIC "DEATH TREE" (LOSS TAXONOMY)
                  </h3>
                  <p className="text-xs text-gray-400 mt-1">
                    Mutual exclusivity failure-mode attribution isolating alpha edge flaws from trade management and execution friction.
                  </p>
                </div>
                <div className="text-right font-mono text-xs">
                  <span className="text-gray-400">Total Analyzed Losses: </span>
                  <span className="text-red-400 font-bold text-sm">{lossTaxonomy.total_losses ?? 0}</span>
                </div>
              </div>

              {/* Loss Taxonomy Cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mt-6">
                {/* Immediate Flush */}
                <div className="bg-[#161f30] border border-red-900/40 rounded-lg p-4 relative overflow-hidden">
                  <div className="absolute top-0 left-0 w-1 h-full bg-red-500" />
                  <div className="text-xs font-mono font-bold text-red-400 uppercase tracking-wider mb-1">
                    Immediate Flush
                  </div>
                  <div className="text-[11px] text-gray-400 mb-3">
                    Exits at Stop-Loss within 6 bars with MFE &lt; 0.35R. Indicates toxic timing or adverse auction entry.
                  </div>
                  <div className="flex items-baseline justify-between font-mono pt-2 border-t border-gray-800">
                    <span className="text-2xl font-bold text-gray-100">
                      {lossTaxonomy.breakdown?.['Immediate Flush']?.count ?? 0}
                    </span>
                    <span className="text-xs text-red-400">
                      {lossTaxonomy.breakdown?.['Immediate Flush']?.percentage ?? 0}% of losses
                    </span>
                  </div>
                  <div className="text-[11px] text-gray-500 font-mono mt-1">
                    Total: -${(lossTaxonomy.breakdown?.['Immediate Flush']?.total_loss_dollars ?? 0).toLocaleString()}
                  </div>
                </div>

                {/* Trapped Trade */}
                <div className="bg-[#161f30] border border-amber-900/40 rounded-lg p-4 relative overflow-hidden">
                  <div className="absolute top-0 left-0 w-1 h-full bg-amber-500" />
                  <div className="text-xs font-mono font-bold text-amber-400 uppercase tracking-wider mb-1">
                    Trapped Trade
                  </div>
                  <div className="text-[11px] text-gray-400 mb-3">
                    Attained MFE &ge; 0.80R before collapsing into a loss. Exposes unrealized round-trips & greedy take-profit geometry.
                  </div>
                  <div className="flex items-baseline justify-between font-mono pt-2 border-t border-gray-800">
                    <span className="text-2xl font-bold text-gray-100">
                      {lossTaxonomy.breakdown?.['Trapped Trade']?.count ?? 0}
                    </span>
                    <span className="text-xs text-amber-400">
                      {lossTaxonomy.breakdown?.['Trapped Trade']?.percentage ?? 0}% of losses
                    </span>
                  </div>
                  <div className="text-[11px] text-gray-500 font-mono mt-1">
                    Total: -${(lossTaxonomy.breakdown?.['Trapped Trade']?.total_loss_dollars ?? 0).toLocaleString()}
                  </div>
                </div>

                {/* Friction Drain */}
                <div className="bg-[#161f30] border border-purple-900/40 rounded-lg p-4 relative overflow-hidden">
                  <div className="absolute top-0 left-0 w-1 h-full bg-purple-500" />
                  <div className="text-xs font-mono font-bold text-purple-400 uppercase tracking-wider mb-1">
                    Friction Drain
                  </div>
                  <div className="text-[11px] text-gray-400 mb-3">
                    Gross PnL &gt; 0, but Net PnL &le; 0 due to commissions & slippage. Stop distance is too narrow relative to spread.
                  </div>
                  <div className="flex items-baseline justify-between font-mono pt-2 border-t border-gray-800">
                    <span className="text-2xl font-bold text-gray-100">
                      {lossTaxonomy.breakdown?.['Friction Drain']?.count ?? 0}
                    </span>
                    <span className="text-xs text-purple-400">
                      {lossTaxonomy.breakdown?.['Friction Drain']?.percentage ?? 0}% of losses
                    </span>
                  </div>
                  <div className="text-[11px] text-gray-500 font-mono mt-1">
                    Total: -${(lossTaxonomy.breakdown?.['Friction Drain']?.total_loss_dollars ?? 0).toLocaleString()}
                  </div>
                </div>

                {/* Structural Invalidation */}
                <div className="bg-[#161f30] border border-cyan-900/40 rounded-lg p-4 relative overflow-hidden">
                  <div className="absolute top-0 left-0 w-1 h-full bg-cyan-500" />
                  <div className="text-xs font-mono font-bold text-cyan-400 uppercase tracking-wider mb-1">
                    Structural Invalidation
                  </div>
                  <div className="text-[11px] text-gray-400 mb-3">
                    Orderly stop violation where trade hypothesis was cleanly invalidated without trapping or instant flushes.
                  </div>
                  <div className="flex items-baseline justify-between font-mono pt-2 border-t border-gray-800">
                    <span className="text-2xl font-bold text-gray-100">
                      {lossTaxonomy.breakdown?.['Structural Invalidation']?.count ?? 0}
                    </span>
                    <span className="text-xs text-cyan-400">
                      {lossTaxonomy.breakdown?.['Structural Invalidation']?.percentage ?? 0}% of losses
                    </span>
                  </div>
                  <div className="text-[11px] text-gray-500 font-mono mt-1">
                    Total: -${(lossTaxonomy.breakdown?.['Structural Invalidation']?.total_loss_dollars ?? 0).toLocaleString()}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: BENCHMARK ZOO LEADERBOARD */}
        {activeTab === 'zoo' && (
          <div className="space-y-6">
            <div className="bg-[#111827] border border-gray-800 rounded-xl p-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-base font-bold text-gray-100 flex items-center gap-2 font-mono">
                    <Layers className="w-5 h-5 text-emerald-400" />
                    ALPHAFORGE BENCHMARK ZOO // INSTITUTIONAL LEADERBOARD
                  </h3>
                  <p className="text-xs text-gray-400 mt-1">
                    Standardized evaluation under identical CME Globex micro execution rules and Apex 50k Trailing MTM constraints.
                  </p>
                </div>
                <button
                  onClick={fetchLeaderboard}
                  className="flex items-center gap-1.5 text-xs font-mono bg-gray-800 hover:bg-gray-700 px-3 py-1.5 rounded border border-gray-700 cursor-pointer"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  REFRESH LEADERBOARD
                </button>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left font-mono text-xs">
                  <thead className="bg-[#182133] text-gray-400 uppercase text-[10px] tracking-wider border-b border-gray-800">
                    <tr>
                      <th className="py-3 px-3">Strategy</th>
                      <th className="py-3 px-3">Trades</th>
                      <th className="py-3 px-3">Win Rate</th>
                      <th className="py-3 px-3">Net PnL ($)</th>
                      <th className="py-3 px-3">Profit Factor</th>
                      <th className="py-3 px-3">Expectancy (R)</th>
                      <th className="py-3 px-3">Drift Ratio (x)</th>
                      <th className="py-3 px-3">P(Pass) %</th>
                      <th className="py-3 px-3">P(Breach) %</th>
                      <th className="py-3 px-3">Crit Slip (S*)</th>
                      <th className="py-3 px-3">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800">
                    {leaderboard.map((row, i) => (
                      <tr key={i} className="hover:bg-gray-800/40 transition">
                        <td className="py-3 px-3 font-bold text-gray-200 flex items-center gap-2">
                          <span className="w-4 h-4 rounded-full bg-gray-800 flex items-center justify-center text-[10px] text-gray-400">
                            {i + 1}
                          </span>
                          {row.Strategy}
                        </td>
                        <td className="py-3 px-3 text-gray-300">{row.Trades}</td>
                        <td className="py-3 px-3 text-gray-300">{row['Win Rate %']}%</td>
                        <td className={`py-3 px-3 font-semibold ${parseFloat(row['Net PnL ($)']) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          ${parseFloat(row['Net PnL ($)']).toLocaleString()}
                        </td>
                        <td className="py-3 px-3 text-amber-400">{row['Profit Factor']}</td>
                        <td className={`py-3 px-3 ${parseFloat(row['Expectancy (R)']) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          {parseFloat(row['Expectancy (R)']) > 0 ? '+' : ''}{row['Expectancy (R)']}R
                        </td>
                        <td className="py-3 px-3 font-bold">
                          <span className={parseFloat(row['Drift Ratio (x)']) >= 1.5 ? 'text-emerald-400' : 'text-red-400'}>
                            {row['Drift Ratio (x)']}x
                          </span>
                        </td>
                        <td className="py-3 px-3 text-emerald-400 font-semibold">{row['P(Pass) %']}%</td>
                        <td className="py-3 px-3 text-red-400 font-semibold">{row['P(Breach) %']}%</td>
                        <td className="py-3 px-3 text-cyan-400">{row['Crit Slip (S*)']}</td>
                        <td className="py-3 px-3">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              row.Status === 'VIABLE'
                                ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                                : 'bg-red-950 text-red-300 border border-red-800'
                            }`}
                          >
                            {row.Status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-4 text-[11px] text-gray-500 font-mono">
                * Alpha Qualification Rule: Directional Drift Ratio must be &ge; 1.50x to avoid immediate disqualification.
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: FRICTION FRONTIER & S* */}
        {activeTab === 'friction' && (
          <div className="space-y-6">
            <div className="bg-[#111827] border border-gray-800 rounded-xl p-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-base font-bold text-gray-100 flex items-center gap-2 font-mono">
                    <Sliders className="w-5 h-5 text-amber-400" />
                    FRICTION FRONTIER & CRITICAL SLIPPAGE (S*)
                  </h3>
                  <p className="text-xs text-gray-400 mt-1">
                    Sensitivity analysis re-evaluating expectancy across slippage increments (0.0 to 3.0 ticks per side).
                  </p>
                </div>
                <div className="font-mono text-xs text-right">
                  <span className="text-gray-400">Critical Slippage S*: </span>
                  <span className="text-cyan-400 font-bold text-sm">{friction.critical_slippage_s_star} ticks</span>
                </div>
              </div>

              <div className="overflow-x-auto mt-4">
                <table className="w-full text-left font-mono text-xs">
                  <thead className="bg-[#182133] text-gray-400 uppercase text-[10px] tracking-wider border-b border-gray-800">
                    <tr>
                      <th className="py-3 px-3">Slippage (Ticks)</th>
                      <th className="py-3 px-3">Slippage (Pts)</th>
                      <th className="py-3 px-3">Net PnL ($)</th>
                      <th className="py-3 px-3">Expectancy ($/Trade)</th>
                      <th className="py-3 px-3">Expectancy (R)</th>
                      <th className="py-3 px-3">Win Rate %</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800">
                    {friction.frontier_table?.map((row: any, i: number) => (
                      <tr key={i} className="hover:bg-gray-800/40 transition">
                        <td className="py-3 px-3 font-bold text-gray-200">{row.slippage_ticks} ticks</td>
                        <td className="py-3 px-3 text-gray-400">{row.slippage_pts} pts</td>
                        <td className={`py-3 px-3 font-semibold ${row.total_net_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          ${row.total_net_pnl.toLocaleString()}
                        </td>
                        <td className={`py-3 px-3 ${row.expectancy_dollars >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          ${row.expectancy_dollars.toFixed(2)}
                        </td>
                        <td className={`py-3 px-3 ${row.expectancy_r >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          {row.expectancy_r > 0 ? '+' : ''}{row.expectancy_r.toFixed(3)}R
                        </td>
                        <td className="py-3 px-3 text-gray-300">{row.win_rate_pct}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* TAB 5: REGIME ATTRIBUTION */}
        {activeTab === 'regime' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Session Window */}
              <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
                <h4 className="font-mono text-sm font-bold text-gray-200 mb-3 flex items-center gap-2">
                  <Compass className="w-4 h-4 text-purple-400" />
                  INTRADAY AUCTION WINDOWS
                </h4>
                <div className="space-y-2.5">
                  {Object.entries(regimes.by_session_window || {}).map(([window, data]: [string, any]) => (
                    <div key={window} className="bg-[#182133] p-3 rounded border border-gray-800/80 font-mono text-xs flex items-center justify-between">
                      <div>
                        <div className="text-gray-300 font-semibold">{window}</div>
                        <div className="text-[11px] text-gray-500">
                          {data.trade_count} trades | Win Rate: {data.win_rate_pct}%
                        </div>
                      </div>
                      <div className="text-right">
                        <div className={`font-bold ${data.total_net_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          ${data.total_net_pnl.toLocaleString()}
                        </div>
                        <div className="text-[11px] text-gray-400">
                          {data.expectancy_r > 0 ? '+' : ''}{data.expectancy_r}R
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Day of Week */}
              <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
                <h4 className="font-mono text-sm font-bold text-gray-200 mb-3 flex items-center gap-2">
                  <Activity className="w-4 h-4 text-cyan-400" />
                  DAY OF WEEK ATTRIBUTION
                </h4>
                <div className="space-y-2.5">
                  {Object.entries(regimes.by_day_of_week || {}).map(([day, data]: [string, any]) => (
                    <div key={day} className="bg-[#182133] p-3 rounded border border-gray-800/80 font-mono text-xs flex items-center justify-between">
                      <div>
                        <div className="text-gray-300 font-semibold">{day}</div>
                        <div className="text-[11px] text-gray-500">
                          {data.trade_count} trades | Win Rate: {data.win_rate_pct}%
                        </div>
                      </div>
                      <div className="text-right">
                        <div className={`font-bold ${data.total_net_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          ${data.total_net_pnl.toLocaleString()}
                        </div>
                        <div className="text-[11px] text-gray-400">
                          {data.expectancy_r > 0 ? '+' : ''}{data.expectancy_r}R
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 6: STRATEGY SPEC & ISOLATION */}
        {activeTab === 'code' && (
          <div className="space-y-6 font-mono text-xs">
            <div className="bg-[#111827] border border-gray-800 rounded-xl p-6">
              <h3 className="text-sm font-bold text-gray-200 mb-2 flex items-center gap-2">
                <Code2 className="w-4 h-4 text-cyan-400" />
                PLUG-AND-PLAY STRATEGY ISOLATION: `src/strategies/{selectedStrategy}/`
              </h3>
              <p className="text-xs text-gray-400 mb-4">
                Self-contained strategy folder auto-discovered via reflection. Consumes immutable BarEvents and emits TradeSetups.
              </p>

              {strategies.find((s) => s.name === selectedStrategy)?.configYaml && (
                <div className="mb-4">
                  <div className="text-gray-400 text-[11px] uppercase mb-1">Local Config (`config.yaml`):</div>
                  <pre className="bg-[#0e1422] p-4 rounded border border-gray-800 text-cyan-300 overflow-x-auto text-[11px] leading-relaxed">
                    {strategies.find((s) => s.name === selectedStrategy)?.configYaml}
                  </pre>
                </div>
              )}

              {strategies.find((s) => s.name === selectedStrategy)?.readme && (
                <div>
                  <div className="text-gray-400 text-[11px] uppercase mb-1">Documentation (`README.md`):</div>
                  <pre className="bg-[#0e1422] p-4 rounded border border-gray-800 text-gray-300 overflow-x-auto text-[11px] leading-relaxed">
                    {strategies.find((s) => s.name === selectedStrategy)?.readme}
                  </pre>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 7: TERMINAL LOGS & PYTEST */}
        {activeTab === 'logs' && (
          <div className="space-y-6 font-mono text-xs">
            {testOutput && (
              <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-emerald-400 font-bold flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4" />
                    PYTEST RIG EXECUTION OUTPUT
                  </h4>
                </div>
                <pre className="bg-[#0e1422] p-4 rounded border border-gray-800 text-gray-300 overflow-x-auto leading-relaxed text-[11px]">
                  {testOutput}
                </pre>
              </div>
            )}

            <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
              <h4 className="text-cyan-400 font-bold flex items-center gap-2 mb-2">
                <TerminalIcon className="w-4 h-4" />
                CLI AUDIT STDOUT / TRACE LOGS
              </h4>
              <pre className="bg-[#0e1422] p-4 rounded border border-gray-800 text-gray-300 overflow-x-auto leading-relaxed text-[11px]">
                {terminalOutput || 'No active terminal logs. Run an audit to see live diagnostics.'}
              </pre>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
