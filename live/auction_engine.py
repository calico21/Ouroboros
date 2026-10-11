import numpy as np
import pandas as pd
from datetime import time, datetime
from typing import Dict, Any, Tuple, Optional, List
import pytz


class AuctionEngine:
    """
    Motor Cuantitativo de Subasta Institucional y Microestructura v3.0.
    Implementa:
      1. Perfiles de Subasta Dalton 70% Value Area (VAH, VAL, POC) y Extremos Macro (PDH, PDL).
      2. VWAP Intradía Acumulado con Bandas de Volatilidad Rolling +/- 1.5 sigma.
      3. Clasificación de Régimen (TREND vs BALANCED):
         - En TREND: Bloquea fades contra-tendencia; permite setups de continuación de apertura.
         - En BALANCED: Ejecuta Dalton Value Area Traverse y barridos PDH/PDL con SMT Divergence.
      4. Detección Intermercado SMT (NQ vs ES / QQQ vs SPY).
    """

    def __init__(self, tz_str: str = "America/New_York"):
        self.tz = pytz.timezone(tz_str)
        self.levels: Dict[str, Any] = {
            "pdh_primary": np.nan,
            "pdl_primary": np.nan,
            "pdc_primary": np.nan,
            "vah_primary": np.nan,
            "val_primary": np.nan,
            "poc_primary": np.nan,
            "pdh_ref": np.nan,
            "pdl_ref": np.nan,
            "pdc_ref": np.nan,
            "vah_ref": np.nan,
            "val_ref": np.nan,
            "poc_ref": np.nan,
            "prev_date": None
        }

    def compute_prior_day_profiles(
        self,
        df_primary: Any,
        df_ref: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Calcula niveles de subasta del día anterior sin sesgo de anticipación (RTH: 09:30 - 16:00 EST).
        """
        if df_primary is None:
            return self.levels

        if isinstance(df_primary, list):
            if not df_primary:
                return self.levels
            df_primary = pd.DataFrame(df_primary)

        if df_ref is not None and isinstance(df_ref, list):
            if df_ref:
                df_ref = pd.DataFrame(df_ref)
            else:
                df_ref = None

        if df_primary.empty:
            return self.levels

        def filter_rth(df: pd.DataFrame) -> pd.DataFrame:
            df_work = df.copy()
            if not isinstance(df_work.index, pd.DatetimeIndex):
                if "timestamp" in df_work.columns:
                    df_work.index = pd.to_datetime(df_work["timestamp"])
                elif "t" in df_work.columns:
                    df_work.index = pd.to_datetime(df_work["t"])

            if df_work.index.tz is None:
                df_work.index = df_work.index.tz_localize(self.tz, ambiguous="NaT")
            else:
                df_work.index = df_work.index.tz_convert(self.tz)

            df_work["date"] = df_work.index.date
            df_work["time"] = df_work.index.time
            # Regular Trading Hours (RTH): 09:30 - 16:00 EST
            return df_work[(df_work["time"] >= time(9, 30)) & (df_work["time"] <= time(16, 0))].copy()

        rth_p = filter_rth(df_primary)
        dates_p = sorted(rth_p["date"].unique())
        if len(dates_p) < 2:
            return self.levels

        prev_d = dates_p[-2]  # Última sesión RTH completamente cerrada
        sub_p = rth_p[rth_p["date"] == prev_d]

        # Normalizar nombres de columnas a minúsculas
        c_col = "close" if "close" in sub_p.columns else "c"
        h_col = "high" if "high" in sub_p.columns else "h"
        l_col = "low" if "low" in sub_p.columns else "l"

        pdh_p = float(sub_p[h_col].max())
        pdl_p = float(sub_p[l_col].min())
        pdc_p = float(sub_p[c_col].iloc[-1])
        typ_p = (pdh_p + pdl_p + pdc_p) / 3.0
        rng_p = pdh_p - pdl_p

        self.levels["pdh_primary"] = pdh_p
        self.levels["pdl_primary"] = pdl_p
        self.levels["pdc_primary"] = pdc_p
        self.levels["vah_primary"] = typ_p + 0.35 * rng_p
        self.levels["val_primary"] = typ_p - 0.35 * rng_p
        self.levels["poc_primary"] = (pdh_p + pdl_p + 2.0 * pdc_p) / 4.0
        self.levels["prev_date"] = prev_d

        # Aliases para compatibilidad con scripts existentes QQQ/SPY
        self.levels["pdh_qqq"] = pdh_p
        self.levels["pdl_qqq"] = pdl_p
        self.levels["vah_qqq"] = self.levels["vah_primary"]
        self.levels["val_qqq"] = self.levels["val_primary"]

        if df_ref is not None and not df_ref.empty:
            rth_r = filter_rth(df_ref)
            dates_r = sorted(rth_r["date"].unique())
            if prev_d in dates_r:
                sub_r = rth_r[rth_r["date"] == prev_d]
                c_r = "close" if "close" in sub_r.columns else "c"
                h_r = "high" if "high" in sub_r.columns else "h"
                l_r = "low" if "low" in sub_r.columns else "l"
                pdh_r = float(sub_r[h_r].max())
                pdl_r = float(sub_r[l_r].min())
                pdc_r = float(sub_r[c_r].iloc[-1])
                typ_r = (pdh_r + pdl_r + pdc_r) / 3.0
                rng_r = pdh_r - pdl_r

                self.levels["pdh_ref"] = pdh_r
                self.levels["pdl_ref"] = pdl_r
                self.levels["pdc_ref"] = pdc_r
                self.levels["vah_ref"] = typ_r + 0.35 * rng_r
                self.levels["val_ref"] = typ_r - 0.35 * rng_r
                self.levels["poc_ref"] = (pdh_r + pdl_r + 2.0 * pdc_r) / 4.0

                self.levels["pdh_spy"] = pdh_r
                self.levels["pdl_spy"] = pdl_r
                self.levels["vah_spy"] = self.levels["vah_ref"]
                self.levels["val_spy"] = self.levels["val_ref"]

        return self.levels

    def compute_vwap_bands(self, df_today: pd.DataFrame) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Calcula el VWAP intradía acumulado y las bandas +/- 1.5 sigma."""
        c_col = "close" if "close" in df_today.columns else "c"
        h_col = "high" if "high" in df_today.columns else "h"
        l_col = "low" if "low" in df_today.columns else "l"
        v_col = "volume" if "volume" in df_today.columns else "v"

        tp = (df_today[h_col] + df_today[l_col] + df_today[c_col]) / 3.0
        vol = df_today[v_col].replace(0, 1.0)
        cum_vol = vol.cumsum()
        vwap = (tp * vol).cumsum() / cum_vol

        dev2 = (tp - vwap) ** 2
        vwap_std = np.sqrt((dev2 * vol).cumsum() / cum_vol)
        upper_band = vwap + 1.5 * vwap_std
        lower_band = vwap - 1.5 * vwap_std

        return vwap, upper_band, lower_band

    def detect_regime(
        self,
        df_today: pd.DataFrame,
        vwap: pd.Series,
        upper_band: pd.Series,
        lower_band: pd.Series,
        atr14: float
    ) -> str:
        """
        Determina si el mercado se encuentra en modo TREND o BALANCED.
        Criterio TREND:
          - Price action sostenido fuera de las bandas +/- 1.5 sigma con apertura direccional
            más allá de VAH/VAL o PDH/PDL y expansión de rango.
        """
        if len(df_today) < 4:
            return "BALANCED"

        c_col = "close" if "close" in df_today.columns else "c"
        o_col = "open" if "open" in df_today.columns else "o"
        h_col = "high" if "high" in df_today.columns else "h"
        l_col = "low" if "low" in df_today.columns else "l"

        today_open = df_today[o_col].iloc[0]
        cur_c = df_today[c_col].iloc[-2]  # Vela cerrada
        prev_c = df_today[c_col].iloc[-3]
        cur_vwap = vwap.iloc[-2]
        cur_upper = upper_band.iloc[-2]
        cur_lower = lower_band.iloc[-2]

        vah = self.levels.get("vah_primary", np.nan)
        val = self.levels.get("val_primary", np.nan)
        pdh = self.levels.get("pdh_primary", np.nan)
        pdl = self.levels.get("pdl_primary", np.nan)

        # Bullish TREND Drive: Abre o empuja fuerte por encima de VAH/PDH y sostiene sobre +1.5 sigma
        bullish_drive = (
            (cur_c > cur_upper or (cur_c > cur_vwap and prev_c > cur_upper)) and
            (cur_c > vah if not np.isnan(vah) else True) and
            (cur_c - today_open > 0.8 * atr14)
        )

        # Bearish TREND Drive: Abre o empuja fuerte por debajo de VAL/PDL y sostiene bajo -1.5 sigma
        bearish_drive = (
            (cur_c < cur_lower or (cur_c < cur_vwap and prev_c < cur_lower)) and
            (cur_c < val if not np.isnan(val) else True) and
            (today_open - cur_c > 0.8 * atr14)
        )

        if bullish_drive or bearish_drive:
            return "TREND"

        return "BALANCED"

    def evaluate_signal(
        self,
        df_primary: pd.DataFrame,
        df_ref: Optional[pd.DataFrame] = None,
        asset_config: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Evalúa la vela previa cerrada con la estrategia Apex Sprint Champion v3.0:
          - En TREND: Bloquea fades; permite setups de continuación con el impulso de apertura.
          - En BALANCED: Ejecuta Dalton Value Area Traverse y PDH/PDL sweeps con confirmación SMT.
        """
        if df_primary is None or len(df_primary) < 15:
            return None

        # Asegurar cálculo de niveles del día anterior si aún no están listos
        if np.isnan(self.levels["pdh_primary"]):
            self.compute_prior_day_profiles(df_primary, df_ref)
            if np.isnan(self.levels["pdh_primary"]):
                return None

        # Preparar datos del día de hoy
        df_p = df_primary.copy()
        c_col = "close" if "close" in df_p.columns else "c"
        o_col = "open" if "open" in df_p.columns else "o"
        h_col = "high" if "high" in df_p.columns else "h"
        l_col = "low" if "low" in df_p.columns else "l"
        v_col = "volume" if "volume" in df_p.columns else "v"

        if not isinstance(df_p.index, pd.DatetimeIndex):
            df_p.index = pd.to_datetime(df_p["timestamp" if "timestamp" in df_p.columns else "t"])
        if df_p.index.tz is None:
            df_p.index = df_p.index.tz_localize(self.tz, ambiguous="NaT")
        else:
            df_p.index = df_p.index.tz_convert(self.tz)

        df_p["date"] = df_p.index.date
        today_date = df_p["date"].iloc[-1]
        df_today = df_p[df_p["date"] == today_date].copy()
        if len(df_today) < 3:
            return None

        # ATR-14
        tr = np.maximum(
            df_today[h_col] - df_today[l_col],
            np.abs(df_today[h_col] - df_today[c_col].shift(1))
        )
        atr14 = float(tr.rolling(14, min_periods=3).mean().iloc[-2])
        if np.isnan(atr14) or atr14 <= 0:
            atr14 = float(asset_config.get("sl_pts", 20.0)) if asset_config else 20.0

        # VWAP y Bandas +/- 1.5 sigma
        vwap, upper_band, lower_band = self.compute_vwap_bands(df_today)

        # Vela cerrada analizada (índice -2)
        bar = df_today.iloc[-2]
        c_bar = float(bar[c_col])
        o_bar = float(bar[o_col])
        h_bar = float(bar[h_col])
        l_bar = float(bar[l_col])
        bar_time_str = bar.name.strftime("%H:%M")

        cur_vwap = float(vwap.iloc[-2])
        cur_upper = float(upper_band.iloc[-2])
        cur_lower = float(lower_band.iloc[-2])
        today_open = float(df_today[o_col].iloc[0])

        vah_p = self.levels["vah_primary"]
        val_p = self.levels["val_primary"]
        pdh_p = self.levels["pdh_primary"]
        pdl_p = self.levels["pdl_primary"]

        # Detección de Régimen
        regime = self.detect_regime(df_today, vwap, upper_band, lower_band, atr14)

        # SMT Divergence Intermercado
        is_smt_bearish = False
        is_smt_bullish = False

        if df_ref is not None and not df_ref.empty and not np.isnan(self.levels["pdh_ref"]):
            df_r = df_ref.copy()
            c_r = "close" if "close" in df_r.columns else "c"
            h_r = "high" if "high" in df_r.columns else "h"
            l_r = "low" if "low" in df_r.columns else "l"
            if not isinstance(df_r.index, pd.DatetimeIndex):
                df_r.index = pd.to_datetime(df_r["timestamp" if "timestamp" in df_r.columns else "t"])
            if df_r.index.tz is None:
                df_r.index = df_r.index.tz_localize(self.tz, ambiguous="NaT")
            else:
                df_r.index = df_r.index.tz_convert(self.tz)

            df_r["date"] = df_r.index.date
            df_r_today = df_r[df_r["date"] == today_date]
            if len(df_r_today) >= 3:
                bar_r = df_r_today.iloc[-2]
                h_ref = float(bar_r[h_r])
                l_ref = float(bar_r[l_r])
                vah_r = self.levels["vah_ref"]
                val_r = self.levels["val_ref"]
                pdh_r = self.levels["pdh_ref"]
                pdl_r = self.levels["pdl_ref"]

                q_swept_h = (h_bar > vah_p) or (h_bar > pdh_p)
                r_swept_h = (h_ref > vah_r) or (h_ref > pdh_r)
                is_smt_bearish = (q_swept_h and not r_swept_h) or (r_swept_h and not q_swept_h)

                q_swept_l = (l_bar < val_p) or (l_bar < pdl_p)
                r_swept_l = (l_ref < val_r) or (l_ref < pdl_r)
                is_smt_bullish = (q_swept_l and not r_swept_l) or (r_swept_l and not q_swept_l)

        side = None
        trigger = ""
        is_smt = False

        # =====================================================================
        # 1. RÉGIMEN TREND (Bloquear Mean-Reversion; Setup de Continuación)
        # =====================================================================
        if regime == "TREND":
            # Si el mercado está en Bullish TREND: NUNCA ponerse corto en extremos.
            # Buscar pullbacks hacia VWAP / Lower Band que respetan la tendencia.
            if c_bar > cur_vwap and l_bar <= (cur_vwap + 0.5 * (cur_upper - cur_vwap)) and c_bar > o_bar:
                side = "BUY"
                trigger = "TREND_OPENING_DRIVE_BULL_CONTINUATION"
                is_smt = is_smt_bullish
            # Si el mercado está en Bearish TREND: NUNCA ponerse largo en extremos.
            # Buscar rebotes hacia VWAP / Upper Band que fallan.
            elif c_bar < cur_vwap and h_bar >= (cur_vwap - 0.5 * (cur_vwap - cur_lower)) and c_bar < o_bar:
                side = "SELL"
                trigger = "TREND_OPENING_DRIVE_BEAR_CONTINUATION"
                is_smt = is_smt_bearish

        # =====================================================================
        # 2. RÉGIMEN BALANCED (Dalton Value Area Traverse & PDH/PDL Sweeps)
        # =====================================================================
        else:
            # A. Dalton 70% Value Area Traverse
            # Rechazo bajista en VAH: penetra por encima de VAH y reingresa por debajo con cierre bajo VWAP
            if (h_bar > vah_p or today_open > vah_p) and c_bar < vah_p and c_bar < cur_vwap:
                if c_bar <= cur_upper:
                    side = "SELL"
                    trigger = "BALANCED_VAH_TRAVERSE_SHORT"
                    is_smt = is_smt_bearish

            # Rechazo alcista en VAL: penetra por debajo de VAL y reingresa por encima con cierre sobre VWAP
            elif (l_bar < val_p or today_open < val_p) and c_bar > val_p and c_bar > cur_vwap:
                if c_bar >= cur_lower:
                    side = "BUY"
                    trigger = "BALANCED_VAL_TRAVERSE_LONG"
                    is_smt = is_smt_bullish

            # B. Macro Liquidity Sweeps (PDH / PDL)
            if side is None:
                # Barrido PDH Short
                if h_bar > pdh_p and c_bar < pdh_p and c_bar < cur_vwap:
                    side = "SELL"
                    trigger = "BALANCED_PDH_SWEEP_SHORT"
                    is_smt = is_smt_bearish
                # Barrido PDL Long
                elif l_bar < pdl_p and c_bar > pdl_p and c_bar > cur_vwap:
                    side = "BUY"
                    trigger = "BALANCED_PDL_SWEEP_LONG"
                    is_smt = is_smt_bullish

        if side is None:
            return None

        # Parámetros de parada y objetivo
        sl_pts = float(asset_config.get("sl_pts", 20.0)) if asset_config else 20.0
        tp_pts = float(asset_config.get("tp_pts", 48.0)) if asset_config else 48.0
        tick = float(asset_config.get("tick", 0.25)) if asset_config else 0.25

        if side == "BUY":
            entry = c_bar + tick
            stop = entry - sl_pts
            target = entry + tp_pts
        else:
            entry = c_bar - tick
            stop = entry + sl_pts
            target = entry - tp_pts

        return {
            "side": side,
            "entry": round(entry, 4),
            "stop": round(stop, 4),
            "target": round(target, 4),
            "sl_dist": sl_pts,
            "tp_dist": tp_pts,
            "time": bar_time_str,
            "trigger": trigger,
            "regime": regime,
            "is_smt": is_smt,
            "atr": atr14
        }
