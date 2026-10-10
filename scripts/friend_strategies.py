import numpy as np
import pandas as pd

BARS_PER_DAY = 78

def _day_pos(df: pd.DataFrame) -> np.ndarray:
    """Posición de cada barra dentro de su día (0..77)."""
    return df.groupby(df.index.normalize()).cumcount().to_numpy()

def intraday_momentum_close(df_rth: pd.DataFrame,
                            first_bar: int = 5,    # barra 09:55-10:00
                            signal_bar: int = 71,  # barra 15:25-15:30, entrada Open 15:30
                            lookback: int = 6,     # 30 min para el nivel del stop
                            target_r: float = 3.0) -> list[dict]:
    """
    H1 (parámetros fijos, sin barridos): momentum intradía (Gao, Han, Li, Zhou 2018).
    Lado = signo del retorno desde pdc hasta el cierre de las 10:00.
    Posición 15:30 -> 15:55 (cierre forzoso del arnés).
    target_r alto a propósito: la salida real es la de tiempo.
    """
    pos = _day_pos(df_rth)
    high = df_rth["high"].to_numpy()
    low = df_rth["low"].to_numpy()
    close = df_rth["close"].to_numpy()
    pdc = df_rth["pdc"].to_numpy()

    signals = []
    for i in np.flatnonzero(pos == signal_bar):
        day_start = i - signal_bar
        if day_start < 0:
            continue
        j = day_start + first_bar
        r = close[j] / pdc[j] - 1.0
        if not np.isfinite(r) or r == 0.0:
            continue
        s = slice(i - lookback + 1, i + 1)
        signals.append({
            "idx": int(i),
            "side": 1 if r > 0 else -1,
            "sig_high": float(high[s].max()),
            "sig_low": float(low[s].min()),
            "target_r": target_r,
        })
    return signals

def placebo_random_side(df_rth: pd.DataFrame, seed: int = 7, **kw) -> list[dict]:
    """
    Control: mismo timing y mismos niveles que H1, lado aleatorio (semilla fija).
    Si H1 no supera claramente a esto, no hay edge, solo deriva alcista o fricción.
    """
    rng = np.random.default_rng(seed)
    sigs = intraday_momentum_close(df_rth, **kw)
    for s in sigs:
        s["side"] = int(rng.choice([-1, 1]))
    return sigs
