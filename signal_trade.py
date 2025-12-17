import re
import asyncio
from telethon import TelegramClient, events
from pybit.unified_trading import HTTP, WebSocketTrading
import os
from dotenv import load_dotenv


load_dotenv()

# -------- MODE FLAGS --------
is_demo = True

# -------- API KEYS --------
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")

SOURCE_CHANNEL = os.getenv("SOURCE_CHANNEL")
TARGET_CHANNEL = int(os.getenv("TARGET_CHANNEL"))
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
BYBIT_API_KEY_DEMO = os.getenv("BYBIT_API_KEY_DEMO")
BYBIT_API_SECRET_DEMO = os.getenv("BYBIT_API_SECRET_DEMO")


# -------- SELECT API KEYS --------
if is_demo:
    selected_api_key = BYBIT_API_KEY_DEMO
    selected_api_secret = BYBIT_API_SECRET_DEMO
    mode_name = "demo"
    selected_symbol = "BTCUSDT"
    coin = "BTC"
    selected_source_channel = TARGET_CHANNEL

else:
    selected_api_key = BYBIT_API_KEY
    selected_api_secret = BYBIT_API_SECRET
    selected_symbol = "BTCUSDT"
    coin = "BTC"
    mode_name = "live"
    selected_source_channel = TARGET_CHANNEL


# ---------------- REGEX ---------------- #
SIGNAL_REGEX = re.compile(
    r"""
    (Long|Short)\s+.*?
    Lev\s*x\d+.*?
    Entry:\s*[\d.]+\s*-\s*           
    Stop\s*Loss:\s*[\d.]+.*?
    Targets:\s*         
    (?:[\d.]+\s*-\s*)+[\d.]+
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)


def is_signal_message(text: str) -> bool:
    if not text:
        return False
    return bool(SIGNAL_REGEX.search(text))


# ---------------- BYBIT CLIENT ---------------- #
session = HTTP(api_key=selected_api_key, api_secret=selected_api_secret)


# ---------------- SIGNAL HANDLER ---------------- #
async def handle_signal(message):
    text = message.message

    side_match = re.search(r"(Long|Short)", text, re.IGNORECASE)
    leverage_match = re.search(r"Lev\s*x(\d+)", text)
    entry_match = re.search(r"Entry:\s*([\d.]+)\s*-\s*([\d.]+)", text)
    sl_match = re.search(r"Stop\s*Loss:\s*([\d.]+)", text)
    targets_match = re.findall(r"Targets:\s*((?:[\d.]+\s*-\s*)*[\d.]+)", text)

    if not (
        side_match and leverage_match and entry_match and sl_match and targets_match
    ):
        return

    side = side_match.group(1).capitalize()
    leverage = int(leverage_match.group(1)) // 2
    if leverage > 15:
        leverage = 15

    entry_price = float(entry_match.group(1))
    sl_price = float(sl_match.group(1))
    targets = [float(t) for t in re.findall(r"[\d.]+", targets_match[0])]

    symbol = "BTCUSDT"  # می‌توانید از متن سیگنال بگیرید
    qty = 1  # حجم پوزیشن (می‌توان محاسبه شود)

    # ----------- باز کردن پوزیشن ----------- #
    order = session.place_order(
        category="linear",
        symbol=symbol,
        side=side,
        orderType="Market",
        qty=qty,
        leverage=leverage,
    )
    print("Order created:", order)

    # ----------- ثبت SL کل پوزیشن ----------- #
    sl_resp = session.set_trading_stop(
        category="linear",
        symbol=symbol,
        tpslMode="Full",
        stopLoss=str(sl_price),
        positionIdx=0,
    )
    print("SL set:", sl_resp)

    # ----------- ثبت TP1 برای 50٪ ----------- #
    tp1_resp = session.set_trading_stop(
        category="linear",
        symbol=symbol,
        tpslMode="Partial",
        takeProfit=str(targets[0]),
        tpSize="0.5",
        positionIdx=0,
    )
    print("TP1 set:", tp1_resp)

    # ----------- وب‌سوکت برای گوش دادن به وضعیت سفارش ----------- #
    def order_callback(msg):
        try:
            data = msg["data"][0]
            if (
                data["orderStatus"] == "Filled"
                and float(data.get("cumExecQty", 0)) >= 0.5 * qty
            ):
                # ست کردن TP2 برای 30٪ حجم باقی مانده
                session.set_trading_stop(
                    category="linear",
                    symbol=symbol,
                    tpslMode="Partial",
                    takeProfit=str(targets[1]),
                    tpSize="0.3",
                    positionIdx=0,
                )
                # ست کردن TP3 برای 100٪ باقی مانده
                session.set_trading_stop(
                    category="linear",
                    symbol=symbol,
                    tpslMode="Partial",
                    takeProfit=str(targets[2]),
                    tpSize="0.2",
                    positionIdx=0,
                )
                print("TP2 and TP3 set")
        except Exception as e:
            print("WebSocket callback error:", e)

    ws = WebSocketTrading(api_key=selected_api_key, api_secret=selected_api_secret)
    ws.order_stream(order_callback)


# ---------------- TELETHON ---------------- #
client = TelegramClient("session_name", TELEGRAM_API_ID, TELEGRAM_API_HASH)


@client.on(events.NewMessage(chats=selected_source_channel))
async def new_message_handler(event):
    print('new event')
    if is_signal_message(event.message.message):
        await handle_signal(event.message)


# ---------------- RUN ---------------- #
async def main():
    await client.start()
    print("Bot is running...")
    await client.run_until_disconnected()


asyncio.run(main())
