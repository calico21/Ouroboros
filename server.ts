import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';
import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs';

const execAsync = promisify(exec);
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function startServer() {
  const app = express();
  const PORT = 3000;

  app.use(express.json());

  // Serve generated visuals directly
  app.use('/api/visuals', express.static(path.join(__dirname, 'reports', 'visuals')));

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

      const tablePath = path.join(__dirname, 'reports', 'tables', `${strategy}_plateau_sweep.csv`);
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

      res.json({ sweep: rows, stdout });
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

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`AlphaForge Server running at http://0.0.0.0:${PORT}`);
  });
}

startServer();
