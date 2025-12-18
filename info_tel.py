import os
from pybit.unified_trading import HTTP
from telethon import TelegramClient, events
from dotenv import load_dotenv

load_dotenv()

# ---------------- CONFIG ---------------- #
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # بات توکن

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY_DEMO")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET_DEMO")
IS_DEMO = True

# ---------------- BYBIT CLIENT ---------------- #
session = HTTP(demo=IS_DEMO, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

# ---------------- TELEGRAM CLIENT ---------------- #
client = TelegramClient('bot', TELEGRAM_API_ID, TELEGRAM_API_HASH)

# ---------------- HELPER FUNCTIONS ---------------- #
def get_open_positions():
    """لیست پوزیشن‌های باز"""
    res = session.get_positions(category="linear")
    open_positions = []
    for p in res["result"]["list"]:
        if float(p["size"]) > 0:
            open_positions.append({
                "symbol": p["symbol"],
                "side": "Buy" if p["side"].lower() == "buy" else "Sell",
                "size": p["size"],
                "entry_price": p["entryPrice"],
                "liq_price": p["liqPrice"],
                "unrealized_pnl": p["unrealisedPnl"]
            })
    return open_positions

def get_closed_positions():
    """لیست پوزیشن‌های بسته (آخرین 50 معامله)"""
    res = session.get_execution_list(category="linear", limit=50)
    closed_positions = []
    for e in res["result"]["list"]:
        if e["execType"].lower() == "trade":
            closed_positions.append({
                "symbol": e["symbol"],
                "side": "Buy" if e["side"].lower() == "buy" else "Sell",
                "size": e["execQty"],
                "price": e["execPrice"],
                "realized_pnl": float(e.get("closedPnl", 0.0))
            })
    return closed_positions

# ---------------- COMMAND HANDLER ---------------- #
@client.on(events.NewMessage(pattern="/positions"))
async def positions_handler(event):
    try:
        open_pos = get_open_positions()
        msg = "📊 **Open Positions:**\n"
        if not open_pos:
            msg += "No open positions.\n"
        else:
            for p in open_pos:
                msg += (
                    f"Symbol: {p['symbol']}\n"
                    f"Side: {p['side']}\n"
                    f"Size: {p['size']}\n"
                    f"Entry: {p['entry_price']}\n"
                    f"Unrealized PnL: {p['unrealized_pnl']}\n"
                    f"Liq Price: {p['liq_price']}\n"
                    "-------------------------\n"
                )

        closed_pos = get_closed_positions()
        msg += "\n✅ **Closed Positions (last 50):**\n"
        if not closed_pos:
            msg += "No closed positions.\n"
        else:
            for p in closed_pos:
                msg += (
                    f"Symbol: {p['symbol']}\n"
                    f"Side: {p['side']}\n"
                    f"Size: {p['size']}\n"
                    f"Price: {p['price']}\n"
                    f"Realized PnL: {p['realized_pnl']}\n"
                    "-------------------------\n"
                )

        await event.respond(msg)

    except Exception as e:
        await event.respond(f"[ERROR] Failed to fetch positions: {e}")


# ---------------- RUN ---------------- #
async def main():
    print("Bot (info_tel) is running...")
    await client.start(bot_token=TELEGRAM_BOT_TOKEN)
    await client.run_until_disconnected()
