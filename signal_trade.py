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

# -------- CONSTANTS --------
POSITION_USDT = 50
order_category = "linear"
RISK_PERCENT = 0.01  # 1% risk per trade
MAX_LEVERAGE = 15

symbol_cache = {}  # cache instruments info
open_positions = set()  # جلوگیری از ترید تکراری
stats = {
    "total": 0,
    "win": 0,
    "loss": 0,
    "pnl": 0.0,
}


# -------- SELECT API KEYS --------
if is_demo:
    selected_api_key = BYBIT_API_KEY_DEMO
    selected_api_secret = BYBIT_API_SECRET_DEMO
    mode_name = "demo"
    selected_source_channel = TARGET_CHANNEL

else:
    selected_api_key = BYBIT_API_KEY
    selected_api_secret = BYBIT_API_SECRET
    mode_name = "live"
    selected_source_channel = TARGET_CHANNEL

print(
    "==================== Env =============================\n"
    f"selected_api_key: {selected_api_key}\n"
    f"selected_api_secret: {selected_api_secret}\n"
    f"mode_name: {mode_name}\n"
    f"selected_source_channel: {selected_source_channel}\n"
    "=====================================================\n"
)
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


# -------------------- BYBIT CLIENT -------------------- #
session = HTTP(demo=is_demo, api_key=selected_api_key, api_secret=selected_api_secret)


# -------------------- SIMBOL INSRUMENTS ---------------- #
def get_symbol_info(symbol):
    if symbol in symbol_cache:
        return symbol_cache[symbol]

    res = session.get_instruments_info(category=order_category, symbol=symbol)

    item = res["result"]["list"][0]

    info = {
        "min_qty": float(item["lotSizeFilter"]["minOrderQty"]),
        "qty_step": float(item["lotSizeFilter"]["qtyStep"]),
        "min_notional": float(item["lotSizeFilter"]["minNotionalValue"]),
        "tick_size": float(item["priceFilter"]["tickSize"]),
        "max_leverage": float(item["leverageFilter"]["maxLeverage"]),
    }
    print(symbol, info)
    symbol_cache[symbol] = info
    return info


# -------------------- GET BALANCE ---------------------- #
def get_usdt_balance():
    wallet = session.get_wallet_balance(accountType="UNIFIED")
    coins = wallet["result"]["list"][0]["coin"]
    for c in coins:
        if c["coin"] == "USDT":
            return float(c["availableToWithdraw"])
    return 0.0


# -------------------- CALCULATE QUANTITY ----------------- #
def calculate_qty(symbol, entry, sl):
    info = get_symbol_info(symbol)
    balance = get_usdt_balance()

    risk_amount = balance * RISK_PERCENT
    sl_distance = abs(entry - sl)

    if sl_distance == 0:
        return None

    raw_qty = risk_amount / sl_distance

    # truncate to step
    step = info["qty_step"]
    qty = int(raw_qty / step) * step

    # enforce min qty
    if qty < info["min_qty"]:
        return None

    # enforce min notional
    if qty * entry < info["min_notional"]:
        return None
    print(
        {
            "============================",
            f"balance: {balance}\n"
            f"risk_amount: {risk_amount}\n"
            f"sl_distance: {sl_distance}\n"
            f"raw_qty: {raw_qty}\n"
            f"step: {step}\n"
            f"qty: {qty}\n"
            "============================",
        }
    )
    return round(qty, 8)


# -------------------- CLOSED ORDER HANDLER ----------------- #
def closed_position_callback(msg):
    try:
        data = msg["data"][0]

        symbol_ws = data.get("symbol")
        size = float(data.get("size", 0))
        closed_pnl = float(data.get("closedPnl", 0))

        # پوزیشن کاملاً بسته شده
        if symbol_ws in open_positions and size == 0:
            open_positions.discard(symbol_ws)

            stats["total"] += 1
            stats["pnl"] += closed_pnl
            if closed_pnl > 0:
                stats["win"] += 1
            else:
                stats["loss"] += 1

            print(f"✅ Position closed: {symbol_ws} | PnL: {closed_pnl}")
            print("📊 Stats:", stats)

    except Exception as e:
        print("Position WS error:", e)


# -------------------- SIGNAL HANDLER ----------------- #
async def handle_signal(message):
    text = message.message

    # ----------- SYMBOL FIRST ----------- #
    symbol_match = re.search(
        r"#\s*([A-Z0-9]+)\s*/\s*(USDT|USDC|USD)", text, re.IGNORECASE
    )

    if not symbol_match:
        print("❌ Symbol not found")
        return

    base = symbol_match.group(1).upper()
    quote = symbol_match.group(2).upper()
    symbol = f"{base}{quote}"

    # ----------- DUPLICATE POSITION CHECK ----------- #
    if symbol in open_positions:
        print(f"⛔ Already in position: {symbol}")
        return

    # ----------- CONTINUE PARSING ----------- #
    side_match = re.search(r"(Long|Short)", text, re.IGNORECASE)
    leverage_match = re.search(r"Lev\s*x(\d+)", text)
    entry_match = re.search(r"Entry:\s*([\d.]+)", text)
    sl_match = re.search(r"Stop\s*Loss:\s*([\d.]+)", text)
    targets_match = re.findall(r"[\d.]+", text)

    if not (side_match and leverage_match and entry_match and sl_match):
        print("❌ Incomplete signal")
        return

    if symbol_match:
        base = symbol_match.group(1).upper()
        quote = symbol_match.group(2).upper()
        symbol = f"{base}{quote}"  # FILUSDT
        coin = base  # FIL
    else:
        symbol = None
        coin = None

    if not (
        side_match and leverage_match and entry_match and sl_match and targets_match
    ):
        return

    raw_side = side_match.group(1).lower()

    if raw_side == "long":
        side = "Buy"
    elif raw_side == "short":
        side = "Sell"
    else:
        return
    leverage = int(leverage_match.group(1)) // 2
    if leverage > 15:
        leverage = 15

    entry_price = float(entry_match.group(1))
    sl_price = float(sl_match.group(1))
    targets = [float(t) for t in re.findall(r"[\d.]+", targets_match[0])]

    raw_qty = POSITION_USDT / entry_price
    qty = round(raw_qty, 3)
    print(
        "=================== will open orde ==================\n"
        f"order_category: {order_category}\n"
        f"side: {side}\n"
        f"leverage: {leverage}\n"
        f"entry_match: {entry_match}\n"
        f"sl_price: {sl_price}\n"
        f"targets: {targets}\n"
        f"symbol: {symbol}\n"
        f"qty: {qty}\n"
        "=====================================================\n"
    )
    # ----------- باز کردن پوزیشن ----------- #
    order = session.place_order(
        category=order_category,
        symbol=symbol,
        side=side,
        orderType="Market",
        qty=qty,
        leverage=leverage,
    )
    print("Order created:", order)
    open_positions.add(symbol)

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
            closed_position_callback(msg)
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
    print("new event")
    if is_signal_message(event.message.message):
        print("is signal")
        await handle_signal(event.message)


# ---------------- RUN ---------------- #
async def main():
    await client.start()
    print("Bot is running...")
    await client.run_until_disconnected()


asyncio.run(main())
