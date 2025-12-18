import re
import asyncio
from telethon import TelegramClient, events
from pybit.unified_trading import HTTP, WebSocket
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
settleCoin="USDT"
symbol_cache = {}
open_positions = set()
stats = {"total": 0, "win": 0, "loss": 0, "pnl": 0.0}

# -------- SELECT API KEYS --------
if is_demo:
    selected_api_key = BYBIT_API_KEY_DEMO
    selected_api_secret = BYBIT_API_SECRET_DEMO
    mode_name = "demo"
    selected_source_channel = SOURCE_CHANNEL
else:
    selected_api_key = BYBIT_API_KEY
    selected_api_secret = BYBIT_API_SECRET
    mode_name = "live"
    selected_source_channel = SOURCE_CHANNEL

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
    r"(Long|Short).*?Lev\s*x\d+.*?Entry:\s*[\d.]+.*?Stop\s*Loss:\s*[\d.]+.*?Targets:\s*(?:[\d.]+\s*-\s*)*[\d.]+",
    re.IGNORECASE | re.DOTALL,
)


def is_signal_message(text: str) -> bool:
    if not text:
        return False
    return bool(SIGNAL_REGEX.search(text))


# ---------------- BYBIT CLIENT ---------------- #
session = HTTP(demo=is_demo, api_key=selected_api_key, api_secret=selected_api_secret)


# ---------------- SYMBOL INFO ---------------- #
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


# ---------------- BALANCE ---------------- #
def get_usdt_balance():
    wallet = session.get_wallet_balance(accountType="UNIFIED")
    coins = wallet["result"]["list"][0]["coin"]
    for c in coins:
        if c["coin"] == "USDT":
            val = c.get("walletBalance") or c.get("totalAvailableBalance") or 0.0
            try:
                return float(val)
            except:
                return 0.0
    return 0.0


# ---------------- QUANTITY CALC ---------------- #
def normalize_qty(qty, step):
    precision = len(str(step).split(".")[1]) if "." in str(step) else 0
    qty = int(qty / step) * step
    return round(qty, precision)


def calculate_risk_qty(symbol, entry, sl):
    info = get_symbol_info(symbol)
    balance = get_usdt_balance()
    risk_amount = balance * RISK_PERCENT
    sl_distance = abs(entry - sl)

    if sl_distance <= 0:
        return None

    raw_qty = risk_amount / sl_distance
    qty = normalize_qty(raw_qty, info["qty_step"])

    print(f"[INFO] qty: {qty}, min_qty: {info['min_qty']}")

    if qty < info["min_qty"]:
        return None
    if qty * entry < info["min_notional"]:
        return None
    return qty


# ---------------- CLOSED ORDER CALLBACK ---------------- #
def closed_position_callback(msg):
    try:
        data = msg["data"][0]
        symbol_ws = data.get("symbol")
        size = float(data.get("size", 0))
        closed_pnl = float(data.get("closedPnl", 0))
        print(f"✅ Message on WS is received: {symbol_ws} / {size} / {closed_pnl}")

        if symbol_ws in open_positions and size == 0:
            open_positions.discard(symbol_ws)
            stats["total"] += 1
            stats["pnl"] += closed_pnl
            if closed_pnl > 0:
                stats["win"] += 1
            else:
                stats["loss"] += 1

            print(f"[INFO] Position closed: {symbol_ws} | PnL: {closed_pnl}")
            print(f"[INFO] Stats: {stats}")

            # Send result to Telegram channel
            async def send_result():
                await client.send_message(
                    TARGET_CHANNEL,
                    f"✅ Position Closed:\n"
                    f"Symbol: {symbol_ws}\n"
                    f"PnL: {closed_pnl}\n"
                    f"Total Trades: {stats['total']}\n"
                    f"Wins: {stats['win']}\n"
                    f"Losses: {stats['loss']}\n"
                    f"Total PnL: {stats['pnl']:.2f}",
                )

            # Run async task from sync function
            asyncio.create_task(send_result())

    except Exception as e:
        print(f"[ERROR] Position WS error: {e}")


# ---------------- PARSE SIGNAL ---------------- #
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


# ---------------- CREATE SIGNAL ---------------- #
WSPrivate = WebSocket(
    demo=is_demo,
    testnet=False,
    channel_type="private",
    api_key=selected_api_key,
    api_secret=selected_api_secret,
    # trace_logging=True
)
WSPrivate.order_stream(closed_position_callback)


# ---------------- HANDLE SIGNAL ---------------- #
async def handle_signal(message):
    text = message.message
    signal = parse_signal(text)
    if not signal:
        print("[WARN] Invalid signal")
        return

    symbol = signal["symbol"]

    if symbol in open_positions:
        print(f"[INFO] Already in position: {symbol}")
        return

    qty = calculate_risk_qty(symbol, signal["entry"], signal["sl"])
    if not qty:
        print("[WARN] Qty calculation failed")
        return

    print(f"[INFO] Opening {symbol} | qty={qty}")

    # Place market order
    order = session.place_order(
        category=order_category,
        symbol=symbol,
        side=signal["side"],
        orderType="limit",
        price=signal["entry"],
        qty=str(qty),
        leverage=MAX_LEVERAGE,
    )
    open_positions.add(symbol)

    # Set SL + first TP
    session.set_trading_stop(
        category=order_category,
        symbol=symbol,
        tpslMode="Full",
        stopLoss=str(signal["sl"]),
        takeProfit=str(signal["targets"][0]),
        positionIdx=0,
    )

    print(
        f"[SUCCESS] Order placed: {symbol} | qty={qty} | SL={signal['sl']} | TP={signal['targets'][0]}"
    )

    # Send order info to Telegram
    await client.send_message(
        TARGET_CHANNEL,
        f"🚀 New Order Placed:\nSymbol: {symbol}\nSide: {signal['side']}\nENR: {signal["entry"]}\nQty: {qty}\nSL: {signal['sl']}\nTP: {signal['targets'][0]}",
    )


# ---------------- TELETHON ---------------- #
client = TelegramClient("session_name", TELEGRAM_API_ID, TELEGRAM_API_HASH)


@client.on(events.NewMessage(chats=selected_source_channel))
async def new_message_handler(event):
    print("[INFO] New event received")
    if is_signal_message(event.message.message):
        print("[INFO] Signal detected")
        await handle_signal(event.message)


# ---------------- RUN ---------------- #
async def main():
    await client.start()
    print("[INFO] Bot is running...")
    await client.run_until_disconnected()


