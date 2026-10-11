import json
from pathlib import Path
from typing import Optional, Dict, Any
import pandas as pd
from live.config import APEX_RULES

STATE_FILE = Path("reports/paper_account_state.json")
JOURNAL_FILE = Path("reports/paper_trading_journal.csv")


class StateManager:
    """
    Gestor de Estado Cuantitativo de Cuenta Apex Trader Funding 50k.
    Implementa:
      - Trailing Drawdown ratchet automático de $2,500 sobre High Water Mark.
      - Congelación perpetua del suelo en $50,100 una vez HWM cruza $52,600.
      - Control Óptimo de Tamaño de Posición DP_V1_ADAPTIVE (3, 5, 7, 8, 10 contratos).
    """

    def __init__(self, state_file: Optional[Path] = None, journal_file: Optional[Path] = None):
        self.state_file = state_file or STATE_FILE
        self.journal_file = journal_file or JOURNAL_FILE
        self.state = self._load_or_init()

    def _load_or_init(self) -> Dict[str, Any]:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Validación de llaves mínimas
                    if "balance" in data and "floor" in data and "hwm" in data:
                        return data
            except Exception:
                pass

        return {
            "balance": float(APEX_RULES["starting_balance"]),
            "floor": float(APEX_RULES["initial_floor"]),
            "hwm": float(APEX_RULES["starting_balance"]),
            "frozen": False,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "last_summary_date": "",
            "sessions_remaining": 21
        }

    def save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=4)

    def get_cushion(self) -> float:
        """Retorna la distancia actual de seguridad al suelo de liquidación D_t."""
        return float(self.state["balance"] - self.state["floor"])

    def update_floating_equity(self, floating_equity: float) -> None:
        """Actualiza el HWM vivo durante la posición y ajusta el trailing floor."""
        if floating_equity > self.state["hwm"]:
            self.state["hwm"] = round(floating_equity, 2)

        if self.state["hwm"] >= APEX_RULES["lock_hwm"]:
            self.state["floor"] = float(APEX_RULES["lock_floor"])
            self.state["frozen"] = True
        elif not self.state["frozen"]:
            calc_floor = self.state["hwm"] - APEX_RULES["buffer"]
            self.state["floor"] = max(self.state["floor"], round(calc_floor, 2))

        self.save()

    def compute_position_size(
        self,
        is_smt_confirmed: bool = False,
        sessions_remaining: Optional[int] = None
    ) -> int:
        """
        Calcula el tamaño de posición óptimo bajo la política DP_V1_ADAPTIVE:
          1. Floor congelado o cercanía de cierre ($52,600+ o ganancia >= $1,800) -> 10 unidades.
          2. SMT Divergence institucional confirmada -> 10 unidades.
          3. Urgencia endgame (k <= 5 sesiones) -> 10 unidades (o 8 si gap <= $800).
          4. Clamp defensivo multietapa:
             - Cojín D_t < $1,200 -> 3 unidades.
             - Cojín D_t in [$1,200, $1,500) -> 5 unidades.
          5. Aceleración de tracción (ganancia >= $600) -> 8 unidades.
          6. Stride base inicial -> 7 unidades.
        """
        d_t = self.get_cushion()
        profit = self.state["balance"] - APEX_RULES["starting_balance"]
        k = sessions_remaining if sessions_remaining is not None else self.state.get("sessions_remaining", 21)
        gap = (APEX_RULES["profit_target"] - APEX_RULES["starting_balance"]) - profit

        # 1. Floor Freeze o cercanía de meta
        if self.state.get("frozen", False) or self.state["hwm"] >= APEX_RULES["lock_hwm"] or profit >= 1800.0:
            return 10

        # 2. SMT Conviction Sprint
        if is_smt_confirmed:
            return 10

        # 3. Urgencia de cierre de horizonte (evitar ruina por timeout)
        if k <= 5:
            return 10 if gap > 800.0 else 8
        if k <= 7:
            return 10 if gap > 1200.0 else 8

        # 4. Clamps defensivos
        if d_t < 1200.0:
            return 3
        if d_t < 1500.0:
            return 5

        # 5. Aceleración de tracción
        if profit >= 600.0:
            return 8

        # 6. Stride base
        return 7

    def update_on_trade_close(
        self,
        sym: str,
        net_pnl: float,
        mfe_usd: float,
        exit_price: float,
        reason: str,
        trade_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Actualiza el balance tras cerrar operación y aplica las reglas de trailing Apex."""
        intra_peak = max(self.state["balance"] + mfe_usd, self.state["balance"] + net_pnl)
        if intra_peak > self.state["hwm"]:
            self.state["hwm"] = round(intra_peak, 2)

        if self.state["hwm"] >= APEX_RULES["lock_hwm"]:
            self.state["floor"] = float(APEX_RULES["lock_floor"])
            self.state["frozen"] = True
        elif not self.state["frozen"]:
            calc_floor = self.state["hwm"] - APEX_RULES["buffer"]
            self.state["floor"] = max(self.state["floor"], round(calc_floor, 2))

        self.state["balance"] = round(self.state["balance"] + net_pnl, 2)
        if self.state["balance"] > self.state["hwm"]:
            self.state["hwm"] = self.state["balance"]

        self.state["total_trades"] += 1
        is_win = net_pnl > 0
        if is_win:
            self.state["wins"] += 1
        else:
            self.state["losses"] += 1

        self.save()
        self._append_journal(sym, net_pnl, exit_price, reason, trade_data)

        return {
            "sym": sym,
            "net_pnl": net_pnl,
            "exit": exit_price,
            "reason": reason,
            "is_win": is_win,
            "balance": self.state["balance"],
            "floor": self.state["floor"],
            "hwm": self.state["hwm"],
            "cushion": self.get_cushion(),
            "frozen": self.state["frozen"]
        }

    def _append_journal(
        self,
        sym: str,
        net_pnl: float,
        exit_price: float,
        reason: str,
        trade_data: Dict[str, Any]
    ) -> None:
        self.journal_file.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": pd.Timestamp.now().isoformat(),
            "symbol": sym,
            "side": trade_data.get("side", ""),
            "entry_time": trade_data.get("time", ""),
            "entry_price": trade_data.get("entry", 0.0),
            "exit_price": exit_price,
            "stop_loss": trade_data.get("stop", 0.0),
            "take_profit": trade_data.get("target", 0.0),
            "units": trade_data.get("ctos", trade_data.get("units", 1)),
            "net_pnl": round(net_pnl, 2),
            "exit_reason": reason,
            "balance_after": round(self.state["balance"], 2),
            "floor_after": round(self.state["floor"], 2),
            "hwm_after": round(self.state["hwm"], 2),
            "cushion_after": round(self.get_cushion(), 2),
            "regime": trade_data.get("regime", "BALANCED"),
            "is_smt": trade_data.get("is_smt", False)
        }
        df_new = pd.DataFrame([record])
        if not self.journal_file.exists():
            df_new.to_csv(self.journal_file, index=False)
        else:
            df_new.to_csv(self.journal_file, mode="a", header=False, index=False)

    def get_daily_metrics(self, today_str: str) -> Dict[str, Any]:
        if not self.journal_file.exists():
            return {
                "date": today_str,
                "trades_today": 0,
                "wins": 0,
                "losses": 0,
                "daily_pnl": 0.0,
                "balance": self.state["balance"],
                "cushion": self.get_cushion(),
                "floor": self.state["floor"],
                "total_trades": self.state["total_trades"],
                "wr": 0.0
            }

        try:
            df = pd.read_csv(self.journal_file)
            df["date"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d")
            df_today = df[df["date"] == today_str]

            n_today = len(df_today)
            pnl_today = float(df_today["net_pnl"].sum()) if n_today > 0 else 0.0
            wins_today = len(df_today[df_today["net_pnl"] > 0])
            losses_today = len(df_today[df_today["net_pnl"] <= 0])

            wr = (self.state["wins"] / self.state["total_trades"] * 100.0) if self.state["total_trades"] > 0 else 0.0
            return {
                "date": today_str,
                "trades_today": n_today,
                "wins": wins_today,
                "losses": losses_today,
                "daily_pnl": pnl_today,
                "balance": self.state["balance"],
                "cushion": self.get_cushion(),
                "floor": self.state["floor"],
                "total_trades": self.state["total_trades"],
                "wr": wr
            }
        except Exception:
            return {
                "date": today_str,
                "trades_today": 0,
                "wins": 0,
                "losses": 0,
                "daily_pnl": 0.0,
                "balance": self.state["balance"],
                "cushion": self.get_cushion(),
                "floor": self.state["floor"],
                "total_trades": self.state["total_trades"],
                "wr": 0.0
            }
