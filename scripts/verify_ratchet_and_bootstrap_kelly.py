#!/usr/bin/env python3
"""
Simulación de crecimiento y ruina bajo ratchet de Apex (MFE/MAE intratrade).

Principios:
- Una sola función de ratchet compartida por tests y simulación.
- Remuestreo por bloques de sesiones (no por fechas sueltas, no por columnas).
- Orden intratrade explícito: 'mfe_first' (optimista) y 'mae_first' (pesimista).
- Halt (parada operativa) distinto de breach (ruina).
- Criterio de selección de tamaño definido antes de la simulación.
"""
from pathlib import Path
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Parámetros de cuenta (Apex 50k, según la especificación del proyecto)
# ---------------------------------------------------------------------------
START_BAL = 50_000.0
BUFFER = 2_000.0
INIT_FLOOR = START_BAL - BUFFER      # 48.000
LOCK_HWM = START_BAL + 2_600.0       # 52.600
LOCK_FLOOR = START_BAL + 100.0       # 50.100
TARGET_BAL = START_BAL + 3_000.0     # 53.000 (no se usa en la regla de ruina)

# Regla de corte
CUT_SCALE_DD = 500.0                 # 25% del buffer -> reducir tamaño
CUT_SCALE = 0.5
HALT_DD = 1_000.0                    # 50% del buffer -> halt permanente

# ---------------------------------------------------------------------------
# 1. Función única de ratchet
# ---------------------------------------------------------------------------
def ratchet_floor(floor: float, hwm_equity: float) -> float:
    """Piso trailing con bloqueo permanente. Nunca baja."""
    if hwm_equity >= LOCK_HWM:
        candidate = LOCK_FLOOR
    else:
        candidate = hwm_equity - BUFFER
    return max(floor, candidate)


def apply_trade(bal: float, floor: float, mfe_d: float, mae_d: float,
                pnl_d: float, order: str = "mae_first"):
    """
    Aplica un trade. Devuelve (bal_nuevo, floor_nuevo, breach).

    order='mfe_first': el precio sube (MFE) antes de bajar (MAE).
                       El floor sube antes de evaluar el trough.
    order='mae_first': el precio baja (MAE) antes de subir (MFE).
                       El trough se evalúa contra el floor previo.
    En ambos casos, el cierre se evalúa contra el floor resultante.
    """
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
    if new_bal <= floor:
        return new_bal, floor, True
    return new_bal, floor, False


# ---------------------------------------------------------------------------
# 2. Tests de borde
# ---------------------------------------------------------------------------
def run_unit_tests():
    checks = []

    # Trough exactamente igual al floor -> breach (<=)
    b, f, br = apply_trade(50_000, 48_000, mfe_d=0, mae_d=2_000, pnl_d=0, order="mae_first")
    checks.append(("trough == floor -> breach", br is True))

    # Trough 1 centavo por encima del floor -> no breach
    b, f, br = apply_trade(50_000, 48_000, mfe_d=0, mae_d=1_999.99, pnl_d=0, order="mae_first")
    checks.append(("trough 1c sobre floor -> vivo", br is False))

    # MFE que no supera el HWM previo: el floor no sube
    b, f, br = apply_trade(50_000, 48_000, mfe_d=0, mae_d=0, pnl_d=0, order="mfe_first")
    checks.append(("sin MFE -> floor igual", f == 48_000))

    # Orden: MAE primero, floor previo. Con el floor que subiría por MFE,
    # el trough quedaría por debajo del nuevo floor pero por encima del previo.
    # mae_first -> vivo; mfe_first -> breach.
    b1, f1, br1 = apply_trade(50_000, 48_000, mfe_d=1_000, mae_d=1_500, pnl_d=0, order="mae_first")
    b2, f2, br2 = apply_trade(50_000, 48_000, mfe_d=1_000, mae_d=1_500, pnl_d=0, order="mfe_first")
    checks.append(("orden mae_first: vivo", br1 is False))
    checks.append(("orden mfe_first: breach", br2 is True))

    # Bloqueo: HWM >= 52.600 -> floor 50.100
    f = ratchet_floor(48_000, 52_600)
    checks.append(("lock en 52.600 -> floor 50.100", f == 50_100))

    # Ratchet nunca baja
    f = ratchet_floor(49_500, 50_000)
    checks.append(("floor nunca baja", f == 49_500))

    print("=" * 80)
    print("TESTS DE BORDE DEL RATCHET")
    print("=" * 80)
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print("=" * 80 + "\n")
    assert all(ok for _, ok in checks), "Tests de ratchet fallidos: no ejecutar simulación"


# ---------------------------------------------------------------------------
# 3. Datos y remuestreo por bloques de sesiones
# ---------------------------------------------------------------------------
def load_trades(csv_path: Path, modules=("PDH_SWEEP",)) -> dict:
    df = pd.read_csv(csv_path)
    df = df[df["module"].isin(modules)].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.sort_values(["date", "entry_time"])
    by_day = {d: g.to_dict("records") for d, g in df.groupby("date")}
    return by_day


def sample_session_blocks(days: list, n_sessions: int, block_len: int,
                          rng: np.random.Generator) -> list:
    """
    Bloques contiguos de días (bootstrap por bloques) hasta cubrir n_sessions.
    Preserva dependencia temporal corta de rachas.
    """
    n = len(days)
    out = []
    while len(out) < n_sessions:
        start = rng.integers(0, n)
        for k in range(block_len):
            out.append(days[(start + k) % n])
            if len(out) == n_sessions:
                break
    return out


# ---------------------------------------------------------------------------
# 4. Simulación de una trayectoria
# ---------------------------------------------------------------------------
def simulate_path(sessions: list, by_day: dict, risk_d: float,
                  order: str, cut_enabled: bool):
    """
    Devuelve dict con: status ('vivo' | 'breach' | 'halt'), bal_final,
    y log del mínimo de balance relativo al buffer.
    """
    bal = START_BAL
    floor = INIT_FLOOR
    peak_bal = START_BAL
    status = "vivo"

    for d in sessions:
        for t in by_day.get(d, []):
            dd = peak_bal - bal
            if cut_enabled and dd >= HALT_DD:
                return {"status": "halt", "bal": bal}

            scale = CUT_SCALE if (cut_enabled and dd >= CUT_SCALE_DD) else 1.0
            r = risk_d * scale
            pnl_d = t["r_net_1t"] * r
            mfe_d = (t["mfe_pts"] / t["stop_pts"]) * r
            mae_d = (t["mae_pts"] / t["stop_pts"]) * r

            bal, floor, breach = apply_trade(bal, floor, mfe_d, mae_d, pnl_d, order)
            if breach:
                return {"status": "breach", "bal": bal}
            peak_bal = max(peak_bal, bal)

    return {"status": "vivo", "bal": bal}


# ---------------------------------------------------------------------------
# 5. Malla de tamaños y métricas
# ---------------------------------------------------------------------------
def evaluate_grid(by_day, risk_pcts, n_paths=5_000, n_sessions=250,
                  block_len=5, seed=42, orders=("mae_first", "mfe_first"),
                  cut_enabled=True):
    rng = np.random.default_rng(seed)
    days = sorted(by_day.keys())
    years = n_sessions / 252.0
    rows = []

    for pct in risk_pcts:
        risk_d = pct * BUFFER
        for order in orders:
            n_breach = n_halt = 0
            log_growth = []
            for _ in range(n_paths):
                sess = sample_session_blocks(days, n_sessions, block_len, rng)
                res = simulate_path(sess, by_day, risk_d, order, cut_enabled)
                if res["status"] == "breach":
                    n_breach += 1
                elif res["status"] == "halt":
                    n_halt += 1
                else:
                    g = res["bal"] / START_BAL
                    if g > 0:
                        log_growth.append(np.log(g) / years)
            lg = np.array(log_growth) if log_growth else np.array([np.nan])
            rows.append({
                "risk_pct_buffer": pct * 100,
                "risk_usd": risk_d,
                "orden": order,
                "p_breach_%": 100 * n_breach / n_paths,
                "p_halt_%": 100 * n_halt / n_paths,
                "cagr_mediana_cond_vivo_%": 100 * (np.exp(np.nanmedian(lg)) - 1),
                "cagr_p5_cond_vivo_%": 100 * (np.exp(np.nanpercentile(lg, 5)) - 1),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 6. Ejecución
# ---------------------------------------------------------------------------
def main():
    csv_path = Path("data/processed/ouroboros_trade_log_pdh_h1_granular.csv")
    if not csv_path.exists():
        raise SystemExit(f"No existe {csv_path}")

    run_unit_tests()

    by_day = load_trades(csv_path, modules=("PDH_SWEEP",))
    n_trades = sum(len(v) for v in by_day.values())
    print(f"Trades PDH_SWEEP usados: {n_trades} en {len(by_day)} sesiones\n")

    # Malla fijada de antemano. El criterio de selección también.
    risk_pcts = [0.0025, 0.005, 0.0075, 0.01, 0.015]
    table = evaluate_grid(by_day, risk_pcts, n_paths=5_000)

    pd.set_option("display.width", 200)
    print(table.round(3).to_string(index=False))

    # Criterio fijado antes de ver resultados: máximo CAGR mediano condicionado
    # a vivo, con breach en orden pesimista (mae_first) <= 1%.
    pess = table[table["orden"] == "mae_first"]
    ok = pess[pess["p_breach_%"] <= 1.0]
    print("\nCriterio: máx CAGR mediano (vivo) con breach(mae_first) <= 1%")
    if ok.empty:
        print("  Ningún tamaño de la malla cumple el criterio.")
    else:
        best = ok.loc[ok["cagr_mediana_cond_vivo_%"].idxmax()]
        print(f"  Tamaño candidato: {best['risk_pct_buffer']:.2f}% del buffer "
              f"(${best['risk_usd']:.2f} por R)")

    table.to_csv("reports/tables/ratchet_growth_grid.csv", index=False)


if __name__ == "__main__":
    main()