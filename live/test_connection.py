import asyncio
from live.alpaca_client import AlpacaClient
from live.telegram_notifier import TelegramNotifier

async def run_diagnostics():
    print("=" * 60)
    print("      OUROBOROS LIVE DIAGNOSTIC SUITE")
    print("=" * 60)

    # 1. Test Telegram
    print("\n[1/3] Probando notificador de Telegram...")
    notifier = TelegramNotifier()
    await notifier.send_message("🧪 *Test de Diagnóstico Ouroboros*: Conexión de Telegram verificada correctamente.")
    print("      -> Mensaje de prueba enviado. Revisa tu chat.")

    # 2. Test Alpaca Auth
    print("\n[2/3] Autenticando con Alpaca Paper Trading...")
    client = AlpacaClient()
    try:
        acc = await client.get_account()
        print(f"      -> Conexión EXITOSA.")
        print(f"      -> Estado de cuenta: {acc.get('status')}")
        print(f"      -> Capital simulado: \${float(acc.get('equity', 0)):,.2f}")
        print(f"      -> Buying power:     \${float(acc.get('buying_power', 0)):,.2f}")
    except Exception as e:
        print(f"      -> ERROR al conectar con Alpaca: {e}")
        print("      -> Verifica que ALPACA_API_KEY y ALPACA_SECRET_KEY en .env sean correctas.")
        return

    # 3. Test Market Data Feed
    print("\n[3/3] Probando descarga de barras 5m (QQQ / SPY via IEX)...")
    bars_q = await client.get_bars("QQQ", limit=5)
    bars_s = await client.get_bars("SPY", limit=5)
    print(f"      -> Barras recibidas QQQ: {len(bars_q)} | SPY: {len(bars_s)}")
    if bars_q:
        print(f"      -> Último precio QQQ: \${bars_q[-1]['c']} | Timestamp: {bars_q[-1]['t']}")

    print("\n" + "=" * 60)
    print("      TODOS LOS SISTEMAS OPERATIVOS (Listo para operar)")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_diagnostics())
