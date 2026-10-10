import time
import datetime as dt
from live.config import ASSETS, APEX_RULES
from live.notifier import TelegramNotifier
from live.state_manager import StateManager
from live.engine import evaluate_signal, fetch_5m_data
from live.reporter import generate_daily_chart

def get_eastern_time():
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=4)

def run():
    notifier = TelegramNotifier()
    state_mgr = StateManager()

    notifier.notify_startup(
        state_mgr.state["balance"],
        state_mgr.state["floor"],
        state_mgr.get_cushion()
    )

    active_trade = None
    traded_today = {k: None for k in ASSETS.keys()}

    while True:
        now_et = get_eastern_time()
        time_str = now_et.strftime("%H:%M")
        today_date = now_et.date()
        today_str = str(today_date)

        # 1. GESTIÓN DE POSICIÓN ACTIVA
        if active_trade:
            cfg = ASSETS[active_trade["sym"]]
            df = fetch_5m_data(cfg["ticker"])
            if df is not None:
                last_bar = df.iloc[-1]
                h, l, c = last_bar["high"], last_bar["low"], last_bar["close"]

                hit_stop = (h >= active_trade["stop"]) if active_trade["side"] == "SELL" else (l <= active_trade["stop"])
                hit_target = (l <= active_trade["target"]) if active_trade["side"] == "SELL" else (h >= active_trade["target"])
                timeout = time_str >= "15:55"

                if hit_stop or hit_target or timeout:
                    reason = "TAKE_PROFIT" if hit_target else ("STOP_LOSS" if hit_stop else "EOD_TIMEOUT")
                    exit_price = active_trade["target"] if hit_target else (active_trade["stop"] if hit_stop else c)

                    pts = (active_trade["entry"] - exit_price) if active_trade["side"] == "SELL" else (exit_price - active_trade["entry"])
                    comm = APEX_RULES["cme_commission_rt"] * active_trade["ctos"] * 2.0
                    net_pnl = (pts * cfg["pt_val"] * active_trade["ctos"]) - comm
                    mfe = max((active_trade["entry"] - l) if active_trade["side"] == "SELL" else (h - active_trade["entry"]), 0.0) * cfg["pt_val"] * active_trade["ctos"]

                    result = state_mgr.update_on_trade_close(
                        active_trade["sym"], net_pnl, mfe, exit_price, reason, active_trade
                    )
                    notifier.notify_trade_closed(result)
                    active_trade = None

        # 2. VIGILANCIA EN VENTANAS RTH (08:15 a 11:35 ET)
        elif "08:15" <= time_str <= "11:35":
            for sym, cfg in ASSETS.items():
                if traded_today[sym] != today_date:
                    sig = evaluate_signal(sym, cfg, state_mgr)
                    if sig:
                        active_trade = sig
                        traded_today[sym] = today_date
                        notifier.notify_trade_opened(sig)
                        break
            time.sleep(30)

        # 3. GENERACIÓN Y ENVÍO DE REPORTE GRÁFICO NOCTURNO (16:15 ET / 22:15 CET)
        if time_str >= "16:15" and state_mgr.state.get("last_summary_date") != today_str:
            chart_path = generate_daily_chart(state_mgr.state)
            summary = state_mgr.get_daily_metrics(today_str)
            notifier.notify_daily_summary(summary, chart_path)
            state_mgr.state["last_summary_date"] = today_str
            state_mgr.save()

        time.sleep(30)

if __name__ == "__main__":
    run()
