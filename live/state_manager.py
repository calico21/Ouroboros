import json
from pathlib import Path
import pandas as pd
from live.config import APEX_RULES

STATE_FILE = Path("reports/paper_account_state.json")
JOURNAL_FILE = Path("reports/paper_trading_journal.csv")

class StateManager:
    def __init__(self):
        self.state = self._load_or_init()

    def _load_or_init(self):
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "balance": APEX_RULES["starting_balance"],
            "floor": APEX_RULES["initial_floor"],
            "hwm": APEX_RULES["starting_balance"],
            "frozen": False,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "last_summary_date": ""
        }

    def save(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=4)

    def get_cushion(self):
        return self.state["balance"] - self.state["floor"]

    def update_on_trade_close(self, sym, net_pnl, mfe_usd, exit_price, reason, trade_data):
        intra_peak = self.state["balance"] + mfe_usd
        if intra_peak >= APEX_RULES["lock_hwm"]:
            self.state["floor"] = APEX_RULES["lock_floor"]
            self.state["frozen"] = True
        elif not self.state["frozen"]:
            self.state["floor"] = max(self.state["floor"], intra_peak - APEX_RULES["buffer"])

        self.state["balance"] += net_pnl
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
            "cushion": self.get_cushion(),
            "frozen": self.state["frozen"]
        }

    def _append_journal(self, sym, net_pnl, exit_price, reason, trade_data):
        JOURNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": pd.Timestamp.now().isoformat(),
            "symbol": sym,
            "side": trade_data["side"],
            "entry_time": trade_data["time"],
            "entry_price": trade_data["entry"],
            "exit_price": exit_price,
            "stop_loss": trade_data["stop"],
            "take_profit": trade_data["target"],
            "contracts": trade_data["ctos"],
            "net_pnl": round(net_pnl, 2),
            "exit_reason": reason,
            "balance_after": round(self.state["balance"], 2),
            "floor_after": round(self.state["floor"], 2),
            "cushion_after": round(self.get_cushion(), 2)
        }
        df_new = pd.DataFrame([record])
        if not JOURNAL_FILE.exists():
            df_new.to_csv(JOURNAL_FILE, index=False)
        else:
            df_new.to_csv(JOURNAL_FILE, mode="a", header=False, index=False)

    def get_daily_metrics(self, today_str):
        if not JOURNAL_FILE.exists():
            return {"date": today_str, "trades_today": 0, "wins": 0, "losses": 0, "daily_pnl": 0.0,
                    "balance": self.state["balance"], "cushion": self.get_cushion(), "floor": self.state["floor"],
                    "total_trades": self.state["total_trades"], "wr": 0.0}
        df = pd.read_csv(JOURNAL_FILE)
        df["date"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d")
        df_today = df[df["date"] == today_str]
        
        n_today = len(df_today)
        pnl_today = df_today["net_pnl"].sum() if n_today > 0 else 0.0
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
