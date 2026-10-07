import express from 'express';
import http from 'http';
import path from 'path';
import { fileURLToPath } from 'url';
import { exec, spawn, ChildProcess } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';
import { WebSocketServer, WebSocket } from 'ws';

const execAsync = promisify(exec);
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function startServer() {
  const app = express();
  const PORT = 3000;
  const server = http.createServer(app);

  app.use(express.json());

  // WebSocket Server for Real-Time Telemetry
  const wss = new WebSocketServer({ server, path: '/ws/live-telemetry' });

  let liveProcess: ChildProcess | null = null;
  let currentTelemetry: any = {
    type: 'TELEMETRY_UPDATE',
    timestamp: new Date().toISOString(),
    strategy: 'afternoon_trend_continuation',
    is_running: false,
    account: {
      account_id: 'APEX-50K-LIVE',
      starting_balance: 50000.0,
      current_balance: 50000.0,
      unrealized_pnl: 0.0,
      total_equity: 50000.0,
      peak_hwm: 50000.0,
      trailing_floor: 47500.0,
      target_equity: 53000.0,
      floor_locked: false,
      distance_to_floor: 2500.0,
      distance_to_target: 3000.0,
      daily_realized_loss: 0.0,
      daily_unrealized_loss: 0.0,
      daily_loss_limit: 1000.0,
      dll_remaining: 1000.0,
      dll_breached: false,
      floor_breached: false,
      is_halted: false,
      account_status: 'IDLE',
      open_positions_count: 0,
      active_orders_count: 0,
      last_update: new Date().toISOString()
    },
    position: {
      symbol: 'MNQ',
      side: 'FLAT',
      contracts: 0,
      entry_price: 0.0,
      current_price: 20250.0,
      unrealized_pnl: 0.0,
      realized_pnl: 0.0,
      peak_unrealized_pnl: 0.0,
      trough_unrealized_pnl: 0.0,
      mfe_r: 0.0,
      mae_r: 0.0
    },
    active_orders: [],
    recent_fills: [],
    event_logs: [
      { time: new Date().toLocaleTimeString(), message: 'AlphaForge live telemetry stream initialized. Waiting for operator dispatch.' }
    ]
  };

  function broadcastTelemetry(data: any) {
    currentTelemetry = data;
    const msg = JSON.stringify(data);
    for (const client of wss.clients) {
      if (client.readyState === WebSocket.OPEN) {
        client.send(msg);
      }
    }
  }

  wss.on('connection', (ws) => {
    ws.send(JSON.stringify(currentTelemetry));
    ws.on('message', (message) => {
      try {
        const parsed = JSON.parse(message.toString());
        if (parsed.action === 'PING') {
          ws.send(JSON.stringify({ type: 'PONG', timestamp: Date.now() }));
        }
      } catch (err) {
        // ignore malformed message
      }
    });
  });

  // REST API: Get current live execution status
  app.get('/api/live/status', (req, res) => {
    res.json(currentTelemetry);
  });

  // REST API: Start live/paper execution
  app.post('/api/live/start', async (req, res) => {
    try {
      const { strategy = 'afternoon_trend_continuation', speed = 0.2 } = req.body;
      if (liveProcess) {
        liveProcess.kill('SIGTERM');
        liveProcess = null;
      }

      currentTelemetry.is_running = true;
      currentTelemetry.strategy = strategy;
      currentTelemetry.event_logs.push({
        time: new Date().toLocaleTimeString(),
        message: `Dispatched live/paper execution harness for [${strategy}] (speed: ${speed}s/bar). Risk sentinel armed.`
      });
      broadcastTelemetry(currentTelemetry);

      liveProcess = spawn('python3', [
        'scripts/run_live_harness.py',
        '--strategy', strategy,
        '--speed', String(speed),
        '--emit-json'
      ], {
        env: { ...process.env, PYTHONPATH: '.' }
      });

      let stdoutBuf = '';
      liveProcess.stdout?.on('data', (data) => {
        stdoutBuf += data.toString();
        const lines = stdoutBuf.split('\n');
        stdoutBuf = lines.pop() || '';
        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const packet = JSON.parse(line.trim());
            packet.is_running = true;
            broadcastTelemetry(packet);
          } catch {
            // raw text line
          }
        }
      });

      liveProcess.stderr?.on('data', (data) => {
        const text = data.toString().trim();
        if (text) {
          currentTelemetry.event_logs.push({
            time: new Date().toLocaleTimeString(),
            message: `[WARN] ${text.slice(0, 120)}`
          });
          broadcastTelemetry(currentTelemetry);
        }
      });

      liveProcess.on('exit', (code) => {
        liveProcess = null;
        if (currentTelemetry.is_running) {
          currentTelemetry.is_running = false;
          currentTelemetry.event_logs.push({
            time: new Date().toLocaleTimeString(),
            message: `Execution process exited (exit code: ${code}).`
          });
          broadcastTelemetry(currentTelemetry);
        }
      });

      res.json({ success: true, message: `Live execution started for ${strategy}` });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // REST API: Stop live execution (graceful shutdown)
  app.post('/api/live/stop', (req, res) => {
    try {
      if (liveProcess) {
        liveProcess.kill('SIGTERM');
        liveProcess = null;
      }
      currentTelemetry.is_running = false;
      currentTelemetry.position.side = 'FLAT';
      currentTelemetry.position.contracts = 0;
      currentTelemetry.position.unrealized_pnl = 0.0;
      currentTelemetry.active_orders = [];
      currentTelemetry.event_logs.push({
        time: new Date().toLocaleTimeString(),
        message: 'Operator triggered graceful stop. Positions flattened and orders cleared.'
      });
      broadcastTelemetry(currentTelemetry);
      res.json({ success: true, message: 'Live broker stopped' });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // REST API: Emergency Flatten (Immediate Kill-Switch)
  app.post('/api/live/emergency-flatten', (req, res) => {
    try {
      if (liveProcess) {
        liveProcess.kill('SIGKILL');
        liveProcess = null;
      }
      currentTelemetry.is_running = false;
      currentTelemetry.position.side = 'FLAT';
      currentTelemetry.position.contracts = 0;
      currentTelemetry.position.unrealized_pnl = 0.0;
      currentTelemetry.active_orders = [];
      currentTelemetry.account.account_status = 'EMERGENCY_FLATTENED';
      currentTelemetry.event_logs.push({
        time: new Date().toLocaleTimeString(),
        message: '🚨 CRITICAL KILL-SWITCH: Emergency flatten triggered! Hard terminated runner process.'
      });
      broadcastTelemetry(currentTelemetry);
      res.json({ success: true, message: 'Emergency kill switch executed' });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // REST API: Get execution discrepancy audit telemetry
  app.get('/api/discrepancies', (req, res) => {
    try {
      const summaryPath = path.join(__dirname, 'reports', 'telemetry', 'daily_discrepancy_summary.json');
      const jsonlPath = path.join(__dirname, 'reports', 'telemetry', 'execution_discrepancies.jsonl');

      let summary: any = {
        total_orders: 0,
        mean_slippage_ticks: 0,
        total_dollar_friction: 0,
        friction_drag_alert: false,
      };

      if (fs.existsSync(summaryPath)) {
        summary = JSON.parse(fs.readFileSync(summaryPath, 'utf8'));
      }

      let recentRecords: any[] = [];
      if (fs.existsSync(jsonlPath)) {
        const lines = fs.readFileSync(jsonlPath, 'utf8').trim().split('\n').filter(Boolean);
        recentRecords = lines.slice(-20).map(l => {
          try { return JSON.parse(l); } catch { return null; }
        }).filter(Boolean);
      }

      res.json({ summary, recentRecords });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // Serve generated visuals directly
  app.use('/api/visuals', express.static(path.join(__dirname, 'reports', 'visuals')));
  app.use('/api/incubation-visuals', express.static(path.join(__dirname, 'reports', 'incubation')));

  // Get incubation paper replay telemetry and visual report
  app.get('/api/incubation', async (req, res) => {
    try {
      const telemetryPath = path.join(__dirname, 'reports', 'incubation', 'paper_trades_telemetry.json');
      let telemetry = [];
      if (fs.existsSync(telemetryPath)) {
        telemetry = JSON.parse(fs.readFileSync(telemetryPath, 'utf8'));
      }
      res.json({
        telemetry,
        reportImageUrl: `/api/incubation-visuals/afternoon_trend_continuation_incubation_report.png?t=${Date.now()}`
      });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // Run paper incubation replay
  app.post('/api/run-incubation', async (req, res) => {
    try {
      const { strategy = 'afternoon_trend_continuation' } = req.body;
      const { stdout } = await execAsync(`PYTHONPATH=. python3 scripts/run_incubation_paper.py --strategy ${strategy}`);
      const telemetryPath = path.join(__dirname, 'reports', 'incubation', 'paper_trades_telemetry.json');
      let telemetry = [];
      if (fs.existsSync(telemetryPath)) {
        telemetry = JSON.parse(fs.readFileSync(telemetryPath, 'utf8'));
      }
      res.json({
        success: true,
        stdout,
        telemetry,
        reportImageUrl: `/api/incubation-visuals/${strategy}_incubation_report.png?t=${Date.now()}`
      });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // Get consolidated LLM digest
  app.get('/api/digest', async (req, res) => {
    try {
      const digestPath = path.join(__dirname, 'reports', 'llm_digest.md');
      if (!fs.existsSync(digestPath)) {
        await execAsync('PYTHONPATH=. python3 scripts/export_digest.py');
      }
      const content = fs.readFileSync(digestPath, 'utf8');
      res.type('text/markdown').send(content);
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // List strategies
  app.get('/api/strategies', async (req, res) => {
    try {
      const strategiesDir = path.join(__dirname, 'src', 'strategies');
      const dirs = fs.readdirSync(strategiesDir, { withFileTypes: true })
        .filter(d => d.isDirectory() && !d.name.startsWith('__') && !d.name.startsWith('.'))
        .map(d => d.name);

      const strategyList = dirs.map(name => {
        const configPath = path.join(strategiesDir, name, 'config.yaml');
        const readmePath = path.join(strategiesDir, name, 'README.md');
        let config = {};
        let readme = '';
        if (fs.existsSync(configPath)) {
          config = fs.readFileSync(configPath, 'utf8');
        }
        if (fs.existsSync(readmePath)) {
          readme = fs.readFileSync(readmePath, 'utf8');
        }
        return { name, configYaml: config, readme };
      });

      strategyList.push({
        name: 'portfolio_blended',
        configYaml: 'name: portfolio_blended\nstrategies:\n  - orb_5m_binary\n  - afternoon_trend_continuation\nmax_portfolio_contracts: 6\n',
        readme: '# Blended Multi-Strategy Portfolio\nSimulates concurrent execution of Morning ORB and Afternoon Trend Continuation under consolidated Apex 50k Trailing Floor.\n'
      });

      res.json({ strategies: strategyList });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // Get benchmark leaderboard
  app.get('/api/benchmark', async (req, res) => {
    try {
      const leaderboardPath = path.join(__dirname, 'reports', 'tables', 'benchmark_zoo_leaderboard.csv');
      if (fs.existsSync(leaderboardPath)) {
        const csv = fs.readFileSync(leaderboardPath, 'utf8');
        const lines = csv.trim().split('\n');
        const headers = lines[0].split(',');
        const rows = lines.slice(1).map(line => {
          const vals = line.split(',');
          const obj: Record<string, string> = {};
          headers.forEach((h, i) => {
            obj[h.trim()] = vals[i] ? vals[i].trim() : '';
          });
          return obj;
        });
        return res.json({ leaderboard: rows });
      }

      // If not yet run, execute benchmark_zoo.py
      const { stdout } = await execAsync('PYTHONPATH=. python3 scripts/benchmark_zoo.py');
      if (fs.existsSync(leaderboardPath)) {
        const csv = fs.readFileSync(leaderboardPath, 'utf8');
        const lines = csv.trim().split('\n');
        const headers = lines[0].split(',');
        const rows = lines.slice(1).map(line => {
          const vals = line.split(',');
          const obj: Record<string, string> = {};
          headers.forEach((h, i) => {
            obj[h.trim()] = vals[i] ? vals[i].trim() : '';
          });
          return obj;
        });
        return res.json({ leaderboard: rows });
      }
      res.json({ leaderboard: [], output: stdout });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // Get single strategy metrics artifact
  app.get('/api/artifacts/:strategy', async (req, res) => {
    try {
      const { strategy } = req.params;
      const artifactPath = path.join(__dirname, 'reports', 'artifacts', `${strategy}_audit_metrics.json`);
      if (fs.existsSync(artifactPath)) {
        const data = JSON.parse(fs.readFileSync(artifactPath, 'utf8'));
        return res.json(data);
      }
      res.status(404).json({ error: 'Artifact not found' });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // Run audit for a specific strategy with parameters
  app.post('/api/run-audit', async (req, res) => {
    try {
      const {
        strategy = 'orb_5m_binary',
        propFirm = 'configs/prop_firm/apex_50k_trailing_mtm.yaml',
        execution = 'configs/execution/cme_globex_default.yaml',
        instrument = 'configs/instruments/mnq.yaml',
        timeframe = '5m',
        mcIterations = 10000
      } = req.body;

      const cmd = `PYTHONPATH=. python3 scripts/run_audit.py --strategy ${strategy} --prop-firm ${propFirm} --execution ${execution} --instrument ${instrument} --timeframe ${timeframe} --mc-iterations ${mcIterations}`;
      const { stdout, stderr } = await execAsync(cmd);

      const artifactPath = path.join(__dirname, 'reports', 'artifacts', `${strategy}_audit_metrics.json`);
      let metrics = {};
      if (fs.existsSync(artifactPath)) {
        metrics = JSON.parse(fs.readFileSync(artifactPath, 'utf8'));
      }

      res.json({
        success: true,
        metrics,
        stdout,
        dashboardUrl: `/api/visuals/dashboards/${strategy}_master_dashboard.png?t=${Date.now()}`,
        coneUrl: `/api/visuals/components/${strategy}_monte_carlo_cone.png?t=${Date.now()}`,
        slipUrl: `/api/visuals/components/${strategy}_slippage_decay.png?t=${Date.now()}`,
        excursionUrl: `/api/visuals/components/${strategy}_time_decay_excursion.png?t=${Date.now()}`
      });
    } catch (err: any) {
      res.status(500).json({ error: err.message, stderr: err.stderr });
    }
  });

  // Run parameter sensitivity sweep
  app.post('/api/sweep', async (req, res) => {
    try {
      const { strategy = 'orb_5m_binary' } = req.body;
      const cmd = `PYTHONPATH=. python3 scripts/sweep_plateau.py`;
      const { stdout } = await execAsync(cmd);

      const tablePath = path.join(__dirname, 'reports', 'tables', 'orb_full_parameter_sweep.csv');
      const heatmapPath = path.join(__dirname, 'reports', 'tables', 'orb_plateau_rr_vs_timestop.csv');
      
      let rows: any[] = [];
      if (fs.existsSync(tablePath)) {
        const csv = fs.readFileSync(tablePath, 'utf8');
        const lines = csv.trim().split('\n');
        const headers = lines[0].split(',');
        rows = lines.slice(1).map(line => {
          const vals = line.split(',');
          const obj: Record<string, string> = {};
          headers.forEach((h, i) => {
            obj[h.trim()] = vals[i] ? vals[i].trim() : '';
          });
          return obj;
        });
      }

      let heatmapRows: any[] = [];
      if (fs.existsSync(heatmapPath)) {
        const csv = fs.readFileSync(heatmapPath, 'utf8');
        const lines = csv.trim().split('\n');
        const headers = lines[0].split(',');
        heatmapRows = lines.slice(1).map(line => {
          const vals = line.split(',');
          const obj: Record<string, string> = {};
          headers.forEach((h, i) => {
            obj[h.trim()] = vals[i] ? vals[i].trim() : '';
          });
          return obj;
        });
      }

      res.json({ sweep: rows, heatmap: heatmapRows, stdout });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // Get cached sweep results
  app.get('/api/sweep', async (req, res) => {
    try {
      const tablePath = path.join(__dirname, 'reports', 'tables', 'orb_full_parameter_sweep.csv');
      const heatmapPath = path.join(__dirname, 'reports', 'tables', 'orb_plateau_rr_vs_timestop.csv');
      
      let rows: any[] = [];
      if (fs.existsSync(tablePath)) {
        const csv = fs.readFileSync(tablePath, 'utf8');
        const lines = csv.trim().split('\n');
        const headers = lines[0].split(',');
        rows = lines.slice(1).map(line => {
          const vals = line.split(',');
          const obj: Record<string, string> = {};
          headers.forEach((h, i) => {
            obj[h.trim()] = vals[i] ? vals[i].trim() : '';
          });
          return obj;
        });
      }

      let heatmapRows: any[] = [];
      if (fs.existsSync(heatmapPath)) {
        const csv = fs.readFileSync(heatmapPath, 'utf8');
        const lines = csv.trim().split('\n');
        const headers = lines[0].split(',');
        heatmapRows = lines.slice(1).map(line => {
          const vals = line.split(',');
          const obj: Record<string, string> = {};
          headers.forEach((h, i) => {
            obj[h.trim()] = vals[i] ? vals[i].trim() : '';
          });
          return obj;
        });
      }

      res.json({ sweep: rows, heatmap: heatmapRows });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  // Run test suite
  app.get('/api/run-tests', async (req, res) => {
    try {
      const { stdout } = await execAsync('PYTHONPATH=. pytest tests/ -v');
      res.json({ success: true, output: stdout });
    } catch (err: any) {
      res.json({ success: false, output: err.stdout || err.message });
    }
  });

  // In development, hook up Vite middleware
  if (process.env.NODE_ENV !== 'production') {
    const { createServer } = await import('vite');
    const vite = await createServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    app.use(express.static(path.join(__dirname, 'dist')));
    app.get('*', (req, res) => {
      res.sendFile(path.join(__dirname, 'dist', 'index.html'));
    });
  }

  server.listen(PORT, '0.0.0.0', () => {
    console.log(`AlphaForge Server running at http://0.0.0.0:${PORT}`);
  });
}

startServer();
