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
    print(f"wallet: {wallet}")
    coins = wallet["result"]["list"][0]["coin"]
    for c in coins:
        if c["coin"] == "USDT":
            # استفاده از walletBalance به جای availableToWithdraw
            val = c.get("walletBalance") or c.get("totalAvailableBalance") or 0.0
            try:
                return float(val)
            except:
                return 0.0
    return 0.0


# -------------------- NORMALIZE QUANTITY ----------------- #
def normalize_qty(qty, step):
    precision = len(str(step).split(".")[1]) if "." in str(step) else 0
    qty = int(qty / step) * step
    return round(qty, precision)


# -------------------- CALCULATE QUANTITY ----------------- #
def calculate_risk_qty(symbol, entry, sl):
    info = get_symbol_info(symbol)
    balance = get_usdt_balance()

    risk_amount = balance * RISK_PERCENT
    sl_distance = abs(entry - sl)

    if sl_distance <= 0:
        return None

    raw_qty = risk_amount / sl_distance
    qty = normalize_qty(raw_qty, info["qty_step"])

    print(f"qty:{qty}", f"min_qt:{info["min_qty"]}")
    # min qty
    if qty < info["min_qty"]:
        return None

    # min notional
    if qty * entry < info["min_notional"]:
        return None

    return qty


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


# -------------------- PARSE SIGNAL ----------------- #
def parse_signal(text):
    symbol_match = re.search(r"#\s*([A-Z0-9]+)\s*/\s*(USDT|USDC|USD)", text, re.I)
    side_match = re.search(r"(Long|Short)", text, re.I)
    entry_match = re.search(r"Entry:\s*([\d.]+)", text)
    sl_match = re.search(r"Stop\s*Loss:\s*([\d.]+)", text)
    targets = [float(x) for x in re.findall(r"Targets:\s*([^\n]+)", text)[0].split("-")]

    if not all([symbol_match, side_match, entry_match, sl_match]):
        return None

    symbol = symbol_match.group(1).upper() + symbol_match.group(2).upper()
    side = "Buy" if side_match.group(1).lower() == "long" else "Sell"

    return {
        "symbol": symbol,
        "side": side,
        "entry": float(entry_match.group(1)),
        "sl": float(sl_match.group(1)),
        "targets": targets,
    }


# -------------------- SIGNAL HANDLER ----------------- #
async def handle_signal(message):
    text = message.message
    signal = parse_signal(text)

    if not signal:
        print("❌ Invalid signal")
        return

    symbol = signal["symbol"]

    if symbol in open_positions:
        print(f"⛔ Already in position: {symbol}")
        return

    qty = calculate_risk_qty(symbol, signal["entry"], signal["sl"])
    print({qty})
    if not qty:
        print("❌ Qty calculation failed")
        return

    print(f"🚀 OPEN {symbol} | qty={qty}")

    order = session.place_order(
        category=order_category,
        symbol=symbol,
        side=signal["side"],
        price=signal["entry"],
        orderType="Limit",
        timeInForce="PostOnly",
        qty=str(qty),
    )

    open_positions.add(symbol)
    session.set_trading_stop(
        category="linear",
        symbol=symbol,
        tpslMode="Full",
        price=signal["targets[0]"],
        stopLoss=str(signal["sl"]),
        positionIdx=0,
    )
    #send opended Order to target channel here


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
