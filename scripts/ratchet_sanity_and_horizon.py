#!/usr/bin/env python3
"""
Prueba de cordura del simulador de ratchet + horizonte de 10 años + malla ampliada.

  1. Tests de borde del ratchet. Si fallan, no se simula.
  2. Prueba de cordura SIN regla de corte: el caso con E[R] negativo debe romper
     cuentas con frecuencia clara. Si no rompe, el simulador no detecta ruina.
  3. Simulación sobre PDH_SWEEP a ~10 años, muestreo iid y por bloques de 20 trades.
  4. Criterio fijado de antemano: máxima mediana de log-crecimiento con
     P(breach 10 años) <= 5%.
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Parámetros de cuenta
# ---------------------------------------------------------------------------
START_BAL = 50_000.0
BUFFER = 2_000.0
INIT_FLOOR = START_BAL - BUFFER
LOCK_HWM = START_BAL + 2_600.0
LOCK_FLOOR = START_BAL + 100.0

CUT_SCALE_DD = 500.0      # 25% del buffer -> reducir tamaño
CUT_SCALE = 0.5
HALT_DD = 1_000.0         # 50% del buffer -> halt permanente

YEARS = 10.0
TRADES_PER_YEAR_OBS = None   # se calcula desde el log (ver main)
BREACH_LIMIT_10Y = 5.0       # %
N_PATHS = 20_000
BLOCK_LEN = 20
RISK_GRID_PCT = [0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03, 0.05, 0.07, 0.10, 0.15]


# ---------------------------------------------------------------------------
# 1. Ratchet compartido
# ---------------------------------------------------------------------------
def ratchet_floor(floor: float, hwm_equity: float) -> float:
    candidate = LOCK_FLOOR if hwm_equity >= LOCK_HWM else hwm_equity - BUFFER
    return max(floor, candidate)


def apply_trade(bal, floor, mfe_d, mae_d, pnl_d, order="mae_first"):
    if order == "mfe_first":
        floor = ratchet_floor(floor, bal + mfe_d)
        if bal - mae_d <= floor:
            return bal, floor, True
    elif order == "mae_first":
        if bal - mae_d <= floor:
            return bal, floor, True
        floor = ratchet_floor(floor, bal + mfe_d)
    else:
        raise ValueError(order)

    new_bal = bal + pnl_d
    floor = ratchet_floor(floor, new_bal)
    return new_bal, floor, new_bal <= floor


def run_edge_tests():
    checks = [
        ("trough == floor -> breach",
         apply_trade(50_000, 48_000, 0, 2_000, 0, "mae_first")[2] is True),
        ("trough 1c sobre floor -> vivo",
         apply_trade(50_000, 48_000, 0, 1_999.99, 0, "mae_first")[2] is False),
        ("sin MFE -> floor igual",
         apply_trade(50_000, 48_000, 0, 0, 0, "mfe_first")[1] == 48_000),
        ("mae_first: vivo",
         apply_trade(50_000, 48_000, 1_000, 1_500, 0, "mae_first")[2] is False),
        ("mfe_first: breach",
         apply_trade(50_000, 48_000, 1_000, 1_500, 0, "mfe_first")[2] is True),
        ("lock 52.600 -> floor 50.100",
         ratchet_floor(48_000, 52_600) == 50_100),
        ("floor nunca baja",
         ratchet_floor(49_500, 50_000) == 49_500),
    ]
    print("=" * 80)
    print("1. TESTS DE BORDE DEL RATCHET")
    print("=" * 80)
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if not all(ok for _, ok in checks):
        sys.exit("Tests de ratchet fallidos. No se simula.")
    print()


# ---------------------------------------------------------------------------
# 2. Simulación de trayectoria
# ---------------------------------------------------------------------------
def simulate_path(trade_stream, risk_d, order="mae_first", cut_enabled=True):
    """
    trade_stream: lista de dicts con pnl_R, mfe_R, mae_R.
    Devuelve (status, balance_final, n_trades_ejecutados).
    status in {'vivo', 'breach', 'halt'}.
    """
    bal = START_BAL
    floor = INIT_FLOOR
    peak_bal = START_BAL
    n = 0
    for t in trade_stream:
        dd = peak_bal - bal
        if cut_enabled and dd >= HALT_DD:
            return "halt", bal, n
        scale = CUT_SCALE if (cut_enabled and dd >= CUT_SCALE_DD) else 1.0
        r = risk_d * scale
        bal, floor, breach = apply_trade(
            bal, floor,
            mfe_d=t["mfe_R"] * r,
            mae_d=t["mae_R"] * r,
            pnl_d=t["pnl_R"] * r,
            order=order,
        )
        n += 1
        if breach:
            return "breach", bal, n
        peak_bal = max(peak_bal, bal)
    return "vivo", bal, n


# ---------------------------------------------------------------------------
# 3. Prueba de cordura (SIN regla de corte: debe detectar breach)
# ---------------------------------------------------------------------------
def sanity_check(risk_pct=0.02, n_paths=5_000, n_trades=125, seed=7):
    rng = np.random.default_rng(seed)
    risk_d = risk_pct * BUFFER
    print("=" * 80)
    print(f"2. PRUEBA DE CORDURA (sin regla de corte, riesgo {risk_pct*100:.1f}% buffer)")
    print("=" * 80)

    cases = [
        ("E[R] = -0.26R  (debe romper con frecuencia)", 0.60, -1.10, 1.00),
        ("E[R] = +0.10R  (debe sobrevivir casi siempre)", 0.50, -1.00, 1.20),
    ]
    ok_negative = False
    breach_neg = None
    breach_pos = None
    for label, p_loss, loss_R, win_R in cases:
        counts = {"vivo": 0, "breach": 0, "halt": 0}
        for _ in range(n_paths):
            wins = rng.random(n_trades) >= p_loss
            pnl = np.where(wins, win_R, loss_R)
            stream = [
                {"pnl_R": float(x), "mfe_R": max(float(x), 0.0), "mae_R": max(-float(x), 0.0)}
                for x in pnl
            ]
            status, _, _ = simulate_path(stream, risk_d, order="mae_first", cut_enabled=False)
            counts[status] += 1
        p_breach = counts["breach"] / n_paths * 100
        print(f"  {label}")
        print(f"    vivo={counts['vivo']/n_paths*100:.1f}%  breach={p_breach:.1f}%")
        e_r = (1.0 - p_loss) * win_R + p_loss * loss_R
        if e_r < 0:
            breach_neg = p_breach
        else:
            breach_pos = p_breach

    if breach_neg is None or breach_pos is None or breach_neg <= breach_pos + 5.0:
        sys.exit("Prueba de cordura FALLIDA: el caso negativo no separa del positivo. "
                 "No usar los resultados del simulador.")
    print("  -> Prueba de cordura superada: el caso negativo rompe significativamente más.\n")


# ---------------------------------------------------------------------------
# 4. Datos reales y muestreo
# ---------------------------------------------------------------------------
def load_pdh_pool(csv_path: Path):
    df = pd.read_csv(csv_path)
    df = df[df["module"] == "PDH_SWEEP"].copy()
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    df = df.sort_values("entry_time").reset_index(drop=True)

    pool = [
        {
            "pnl_R": float(r["r_net_1t"]),
            "mfe_R": float(r["mfe_pts"]) / float(r["stop_pts"]),
            "mae_R": float(r["mae_pts"]) / float(r["stop_pts"]),
        }
        for _, r in df.iterrows()
    ]
    span_years = (df["entry_time"].max() - df["entry_time"].min()).days / 365.25
    return pool, span_years


def draw_iid(pool, n_trades, rng):
    idx = rng.integers(0, len(pool), size=n_trades)
    return [pool[i] for i in idx]


def draw_blocks(pool, n_trades, block_len, rng):
    n = len(pool)
    out = []
    while len(out) < n_trades:
        s = int(rng.integers(0, n))
        for k in range(block_len):
            out.append(pool[(s + k) % n])
            if len(out) == n_trades:
                break
    return out


# ---------------------------------------------------------------------------
# 5. Malla a horizonte fijo
# ---------------------------------------------------------------------------
def evaluate_grid(pool, n_trades, sampler, label, seed=42):
    rng = np.random.default_rng(seed)
    rows = []
    for pct in RISK_GRID_PCT:
        risk_d = pct * BUFFER
        counts = {"vivo": 0, "breach": 0, "halt": 0}
        logg = []
        for _ in range(N_PATHS):
            stream = sampler(pool, n_trades, rng)
            status, bal, _ = simulate_path(stream, risk_d, order="mae_first", cut_enabled=True)
            counts[status] += 1
            if status in ("vivo", "halt") and bal > 0:
                logg.append(np.log(bal / START_BAL) / YEARS)
        lg = np.array(logg) if logg else np.array([0.0])
        rows.append({
            "muestreo": label,
            "riesgo_%buffer": pct * 100,
            "riesgo_usd": risk_d,
            "p_breach_10y_%": 100 * counts["breach"] / N_PATHS,
            "p_halt_10y_%": 100 * counts["halt"] / N_PATHS,
            "cagr_mediana_%": 100 * (np.exp(np.median(lg)) - 1),
            "mediana_log_crec": float(np.median(lg)),
        })
    return pd.DataFrame(rows)


def pick_candidate(table: pd.DataFrame):
    ok = table[table["p_breach_10y_%"] <= BREACH_LIMIT_10Y]
    if ok.empty:
        return None
    return ok.loc[ok["mediana_log_crec"].idxmax()]


# ---------------------------------------------------------------------------
# 6. Main
# ---------------------------------------------------------------------------
def main():
    csv_path = Path("data/processed/ouroboros_trade_log_pdh_h1_granular.csv")
    if not csv_path.exists():
        sys.exit(f"No existe {csv_path}")

    run_edge_tests()

    pool, span_years = load_pdh_pool(csv_path)
    trades_per_year = len(pool) / span_years
    n_trades = int(round(trades_per_year * YEARS))
    print(f"Pool PDH: {len(pool)} trades en {span_years:.2f} años "
          f"({trades_per_year:.1f}/año).")
    print(f"Trades simulados por trayectoria a {YEARS:.0f} años: {n_trades}\n")

    sanity_check(n_trades=n_trades)

    t_iid = evaluate_grid(pool, n_trades, draw_iid, "iid")
    t_blk = evaluate_grid(pool, n_trades,
                          lambda p, n, r: draw_blocks(p, n, BLOCK_LEN, r),
                          f"bloques_{BLOCK_LEN}")
    table = pd.concat([t_iid, t_blk], ignore_index=True)

    pd.set_option("display.width", 220)
    print("3. RESULTADOS A 10 AÑOS (mae_first, pesimista, con regla de corte)")
    print("=" * 90)
    print(table.round(3).to_string(index=False))

    print(f"\n4. CRITERIO (fijado de antemano): máx mediana log-crec con "
          f"P(breach 10y) <= {BREACH_LIMIT_10Y}%")
    for label in ["iid", f"bloques_{BLOCK_LEN}"]:
        cand = pick_candidate(table[table["muestreo"] == label])
        if cand is None:
            print(f"  [{label}] Ningún tamaño cumple el criterio.")
        else:
            print(f"  [{label}] Candidato: {cand['riesgo_%buffer']:.2f}% buffer "
                  f"(${cand['riesgo_usd']:.2f}/R), CAGR mediano {cand['cagr_mediana_%']:.2f}%, "
                  f"P(breach 10y) {cand['p_breach_10y_%']:.2f}%")

    Path("reports/tables").mkdir(parents=True, exist_ok=True)
    table.to_csv("reports/tables/ratchet_horizon_grid.csv", index=False)
    print("\nTabla guardada en reports/tables/ratchet_horizon_grid.csv")


if __name__ == "__main__":
    main()