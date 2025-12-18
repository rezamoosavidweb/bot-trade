import os
from pybit.unified_trading import HTTP
from telethon import TelegramClient, events
from dotenv import load_dotenv

load_dotenv()

# ---------------- CONFIG ---------------- #
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # بات توکن
settleCoin = "USDT"
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY_DEMO")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET_DEMO")
IS_DEMO = True

# ---------------- BYBIT CLIENT ---------------- #
session = HTTP(demo=IS_DEMO, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

# ---------------- TELEGRAM CLIENT ---------------- #
client = TelegramClient("bot", TELEGRAM_API_ID, TELEGRAM_API_HASH)


# ---------------- HELPER FUNCTIONS ---------------- #
def get_open_positions():
    """لیست پوزیشن‌های باز"""
    print("get open positions called")

    res = session.get_positions(category="linear", settleCoin=settleCoin)

    open_positions = []
    for p in res["result"]["list"]:
        size = float(p.get("size", 0))
        if size <= 0:
            continue

        open_positions.append(
            {
                "symbol": p.get("symbol"),
                "side": p.get("side"),
                "size": size,
                "entry_price": float(p.get("avgPrice", 0)),
                "liq_price": p.get("liqPrice", "-"),
                "unrealized_pnl": float(p.get("unrealisedPnl", 0)),
                "mark_price": float(p.get("markPrice", 0)),
                "leverage": p.get("leverage"),
            }
        )

    return open_positions



def get_profit_loos():
    """Query user's closed profit and loss records"""
    res = session.get_closed_pnl(category="linear", limit=50)

    profit_loss = []

    items = res.get("result", {}).get("list", [])
    for p in items:
        closed_size = float(p.get("closedSize", 0))
        if closed_size <= 0:
            continue

        profit_loss.append(
            {
                "symbol": p.get("symbol"),
                "side": p.get("side"),
                "size": closed_size,
                "entry_price": float(p.get("avgEntryPrice", 0)),
                "exit_price": float(p.get("avgExitPrice", 0)),
                "closed_pnl": float(p.get("closedPnl", 0)),
                "open_fee": float(p.get("openFee", 0)),
                "close_fee": float(p.get("closeFee", 0)),
                "leverage": p.get("leverage"),
                "time": p.get("updatedTime"),
            }
        )

    return profit_loss



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

        profits_losses = get_profit_loos()
        msg += "\n✅ **Closed Profit & Loss (last 50):**\n"

        if not profits_losses:
            msg += "No closed profit and loss records.\n"
        else:
            for p in profits_losses:
                emoji = "🟢" if p["closed_pnl"] > 0 else "🔴"
                msg += (
                    f"{emoji} Symbol: {p['symbol']}\n"
                    f"Side: {p['side']} | Lev: {p['leverage']}x\n"
                    f"Size: {p['size']}\n"
                    f"Entry: {p['entry_price']} → Exit: {p['exit_price']}\n"
                    f"PnL: {p['closed_pnl']}\n"
                    f"Fees: {p['open_fee'] + p['close_fee']}\n"
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
