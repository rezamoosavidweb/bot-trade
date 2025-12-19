import re
import asyncio
from telethon import TelegramClient, events
from pybit.unified_trading import HTTP, WebSocket
import os
from dotenv import load_dotenv
import traceback
import datetime

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
settleCoin = "USDT"
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


# ---------------- TELETHON ---------------- #
client = TelegramClient("session_name", TELEGRAM_API_ID, TELEGRAM_API_HASH)

telegram_queue = asyncio.Queue()

async def process_telegram_queue():
    while True:
        item = await telegram_queue.get()
        symbol_ws = item["symbol"]
        closed_pnl = item["closed_pnl"]
        data = item["data"]
        is_closed = item["is_closed"]
        takeProfit = item["takeProfit"]
        stopLoss = item["stopLoss"]
        
        if is_closed:
            open_positions.discard(symbol_ws)
            stats["total"] += 1
            stats["pnl"] += closed_pnl
            if closed_pnl > 0:
                stats["win"] += 1
            else:
                stats["loss"] += 1

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
        else:
            await client.send_message(
                TARGET_CHANNEL,
                "⏳ **Get new message (WS)**\n\n"
                f"Symbol: {data['symbol']}\n"
                f"Side: {data['side']}\n"
                f"Type: {data['orderType']} / {data.get('stopOrderType', '-')}\n"
                f"Status: {data['orderStatus']}\n"
                f"Time in Force: {data['timeInForce']}\n\n"
                f"Qty: {data['qty']}\n"
                f"Limit Price: {data['price']}\n"
                f"Trigger Price: {data.get('triggerPrice', '-')}\n"
                f"Take Profit: {takeProfit}\n"
                f"Stop Loss: {stopLoss}\n"
                f"Filled: {data['cumExecQty']} / {data['qty']}\n\n"
                f"Last Price on Create: {data.get('lastPriceOnCreated', '-')}\n\n"
                f"Order ID:\n{data['orderId']}\n\n"
                f"Created At: {data['createdTime']}"
            )

        telegram_queue.task_done()

# ---------------- CLOSED ORDER CALLBACK (Refactored) ---------------- #
def closed_position_callback(msg):
    try:
        data = msg["data"][0]
        symbol_ws = data.get("symbol")
        size = float(data.get("size", 0))
        closed_pnl = float(data.get("closedPnl", 0))
        takeProfit = float(data["takeProfit"])
        stopLoss = float(data["stopLoss"])
        print(f"✅ Message on WS is received: {symbol_ws} / {size} / {closed_pnl} / {stopLoss}/ {takeProfit}")
        
        
        telegram_queue.put_nowait({
            "symbol": symbol_ws,
            "size": size,
            "closed_pnl": closed_pnl,
            "takeProfit": takeProfit,
            "stopLoss": stopLoss,
            "data": data,
            "is_closed": symbol_ws in open_positions and size == 0
        })

    except Exception as e:
        asyncio.get_event_loop().create_task(
            send_error_to_telegram(e, context="WS position callback")
        )

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



async def send_error_to_telegram(error: Exception, context: str = ""):
    try:
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        msg = (
            "🚨 **BOT ERROR**\n\n"
            f"🕒 Time: {datetime.datetime.utcnow()} UTC\n"
            f"📍 Context: {context}\n\n"
            f"❌ Type: {type(error).__name__}\n"
            f"📝 Message: {str(error)}\n\n"
            f"📌 Traceback:\n"
            f"```{tb[-3500:]}```"
        )
        await client.send_message(TARGET_CHANNEL, msg)
    except Exception as e:
        print("[FATAL] Failed to send error to Telegram:", e)


# ---------------- HANDLE SIGNAL ---------------- #
async def handle_signal(message):
    try:
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
            orderType="Market",
            qty=str(qty),
            # price=signal["entry"],
            # leverage=MAX_LEVERAGE,
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
    except Exception as e:
        await send_error_to_telegram(e, context="handle_signal")


# ---------------- HANDLE NEW MESSAGE ---------------- #
@client.on(events.NewMessage(chats=selected_source_channel))
async def new_message_handler(event):
    print("[INFO] New event received")

    message_text = event.message.message or ""

    if is_signal_message(message_text):
        print("[INFO] Signal detected")

        await client.send_message(
            TARGET_CHANNEL,
            (
                "📡 **New Signal Message Detected**\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "📨 **Original Message:**\n"
                "```\n"
                f"{message_text}\n"
                "```"
            )
        )

        try:
            await handle_signal(event.message)
        except Exception as e:
            await send_error_to_telegram(e, context="handle_signal")

    else:
        await client.send_message(
            TARGET_CHANNEL,
            (
                "⛔ **Non-Signal Message Received**\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "📨 **Message Content:**\n"
                "```\n"
                f"{message_text}\n"
                "```"
            )
        )



# ---------------- RUN ---------------- #
async def main():
    await client.start()
    print("[INFO] Telegram client started")

    # وب‌سوکت
    WSPrivate = WebSocket(
        demo=is_demo,
        testnet=False,
        channel_type="private",
        api_key=selected_api_key,
        api_secret=selected_api_secret,
    )
    WSPrivate.order_stream(closed_position_callback)
    
    def handle_global_exception(loop, context):
        error = context.get("exception")
        if error:
            asyncio.create_task(
                send_error_to_telegram(error, context="GLOBAL")
            )
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(handle_global_exception)
    # start processing queue
    asyncio.create_task(process_telegram_queue())

    await client.run_until_disconnected()
