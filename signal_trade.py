import re
import asyncio
from telethon import TelegramClient, events
from pybit.unified_trading import HTTP, WebSocket
import os
from dotenv import load_dotenv
import traceback
import datetime
from zoneinfo import ZoneInfo
import time

load_dotenv()


try:
    main_loop = asyncio.get_running_loop()
except RuntimeError:
    main_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(main_loop)

# -------- MODE FLAGS --------
is_demo = True

# -------- API KEYS --------
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")

# SOURCE_CHANNEL = int(os.getenv("TARGET_CHANNEL"))
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
MAX_POSITION_USDT = 100  # حتی بهتر

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

    res = session.get_instruments_info(category="linear", symbol=symbol)
    item = res["result"]["list"][0]

    info = {
        "min_qty": float(item["lotSizeFilter"]["minOrderQty"]),
        "max_order_qty": float(item["lotSizeFilter"]["maxOrderQty"]),
        "qty_step": float(item["lotSizeFilter"]["qtyStep"]),
        "min_notional": float(item["lotSizeFilter"]["minNotionalValue"]),
        "tick_size": float(item["priceFilter"]["tickSize"]),
        "max_leverage": float(item["leverageFilter"]["maxLeverage"]),
    }

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

# ---------------- GET OPEN POSITION ---------------- #
def is_position_open(symbol):
    try:
        res = session.get_positions(
            category="linear",
            symbol=symbol,
        )
        positions = res["result"]["list"]
        if not positions:
            return False

        size = float(positions[0]["size"])
        return size != 0
    except Exception as e:
        print(f"[WARN] position check failed: {e}")
        return False

# ---------------- GET TRANSACTIONS LOG ---------------- #
async def get_last_transactions(symbol: str, limit: int = 5):
    """
    گرفتن آخرین transaction ها برای یک symbol
    """
    end_time = int(time.time() * 1000)
    start_time = end_time - 7 * 24 * 60 * 60 * 1000  # 7 روز

    resp = session.get_transaction_log(
        accountType="UNIFIED",
        category="linear",
        currency="USDT",
        startTime=start_time,
        endTime=end_time,
        limit=50,
    )

    transactions = resp.get("result", {}).get("list", [])
    
    # فقط symbol مورد نظر
    symbol_txs = [tx for tx in transactions if tx.get("symbol") == symbol]

    # جدیدترین → قدیمی‌ترین
    symbol_txs.sort(
        key=lambda x: int(x.get("transactionTime", 0)),
        reverse=True
    )

    return symbol_txs[:limit]



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

    if sl_distance <= 0 or entry <= 0:
        return None

    # qty based on risk
    raw_qty = (risk_amount * MAX_LEVERAGE) / (sl_distance * entry)
    qty = normalize_qty(raw_qty, info["qty_step"])

    # 🧠 cap based on order limit
    qty = min(qty, info["max_order_qty"])

    # 🧠 cap based on position USDT
    qty_cap_by_usdt = MAX_POSITION_USDT / entry
    qty = min(qty, qty_cap_by_usdt)

    qty = normalize_qty(qty, info["qty_step"])

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

        try:
            # ================= POSITION CLOSED =================
            if is_closed:
                open_positions.discard(symbol_ws)

                # ---------- stats ----------
                stats["total"] += 1
                stats["pnl"] += closed_pnl
                if closed_pnl > 0:
                    stats["win"] += 1
                else:
                    stats["loss"] += 1

                # ⏳ صبر برای Sync شدن Transaction Log در Bybit
                await asyncio.sleep(2)

                # ---------- get last transactions ----------
                transactions_data = await get_last_transactions(
                    symbol=symbol_ws,
                    limit=2
                )

                # ---------- header message ----------
                header_msg = (
                    f"✅ **POSITION CLOSED**\n\n"
                    "```\n"
                    f"Symbol: {symbol_ws}\n"
                    f"Closed PnL: {closed_pnl}\n"
                    f"Take Profit: {takeProfit}\n"
                    f"Stop Loss: {stopLoss}\n\n"
                    f"Total Trades: {stats['total']}\n"
                    f"Wins: {stats['win']}\n"
                    f"Losses: {stats['loss']}\n"
                    f"Total PnL: {stats['pnl']:.2f}\n"
                    "```"
                )

                await client.send_message(TARGET_CHANNEL, header_msg)

                # ---------- loop on transactions ----------
                for idx, tx in enumerate(transactions_data, start=1):
                    cash_flow = float(tx.get("cashFlow", 0))
                    funding = float(tx.get("funding", 0))
                    fee = float(tx.get("fee", 0))
                    change = float(tx.get("change", 0))

                    tx_msg = (
                        f"📄 **Transaction #{idx}**\n\n"
                        "```\n"
                        f"Type: {tx.get('type')}\n"
                        f"Side: {tx.get('side')}\n"
                        f"Qty: {tx.get('qty')}\n"
                        f"Price: {tx.get('tradePrice')}\n"
                        f"Cash Flow: {cash_flow}\n"
                        f"Funding: {funding}\n"
                        f"Fee: {fee}\n"
                        f"Change: {change}\n"
                        f"Balance After: {tx.get('cashBalance')}\n"
                        f"Order ID: {tx.get('orderId')}\n"
                        f"Trade ID: {tx.get('tradeId')}\n"
                        f"Time: {tx.get('transactionTime')}\n"
                        "```"
                    )

                    await client.send_message(TARGET_CHANNEL, tx_msg)
                    await asyncio.sleep(0.2)  # جلوگیری از flood

            # ================= ACTIVE / NEW ORDER =================
            else:
                msg_text = (
                    f"⏳ **WS New / Active Order**\n\n"
                    "```\n"
                    f"Symbol: {symbol_ws}\n"
                    f"Order ID: {data['orderId']}\n"
                    f"Side: {data['side']}\n"
                    f"Type: {data['orderType']} / {data.get('stopOrderType', '-')}\n"
                    f"Status: {data['orderStatus']}\n"
                    f"Qty: {data['qty']}\n"
                    f"Filled Qty: {data['cumExecQty']}\n"
                    f"Price: {data.get('price')}\n"
                    f"Avg Price: {data.get('avgPrice', '-')}\n"
                    f"Take Profit: {takeProfit}\n"
                    f"Stop Loss: {stopLoss}\n"
                    f"Reduce Only: {data.get('reduceOnly')}\n"
                    f"Created At: {data.get('createdTime')}\n"
                    "```"
                )

                await client.send_message(TARGET_CHANNEL, msg_text)

        except Exception as e:
            print("[ERROR] Telegram send failed:", e)

        telegram_queue.task_done()

# ---------------- CLOSED ORDER CALLBACK ---------------- #
def order_callback_ws(msg):
    try:
        data = msg["data"][0]
        symbol_ws = data.get("symbol")
        size = float(data.get("size", 0))
        closed_pnl = float(data.get("closedPnl", 0))
        takeProfit = float(data.get("takeProfit") or 0)
        stopLoss = float(data.get("stopLoss") or 0)

        # print(f"✅ WS data: {data}")
        print(f"✅ WS message: symbol_ws:{symbol_ws} / size:{size} / closed_pnl:{closed_pnl}")

        # تشخیص اینکه پوزیشن بسته شده است یا خیر
        is_closed = (
            (data.get("reduceOnly") in [True, "True"] and data.get("closeOnTrigger") in [True, "True"])
            or float(data.get("closedPnl", 0)) != 0
        )

        
        asyncio.run_coroutine_threadsafe(
            telegram_queue.put({
                "symbol": symbol_ws,
                "size": size,
                "closed_pnl": closed_pnl,
                "takeProfit": takeProfit,
                "stopLoss": stopLoss,
                "data": data,
                "is_closed": is_closed,
            }),
            main_loop
        )

    except Exception as e:
        asyncio.run_coroutine_threadsafe(
            send_error_to_telegram(e, context="WS position callback"),
            main_loop
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
        tb = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
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

        # ---------- بررسی وضعیت واقعی پوزیشن ----------
        position_open = is_position_open(symbol)
        if symbol in open_positions or position_open:
            # اگر پوزیشن در Bybit باز است ولی open_positions محلی خالی بود، آن را اضافه می‌کنیم
            open_positions.add(symbol)
            print(f"[INFO] Already in position: {symbol}")
            await client.send_message(
                TARGET_CHANNEL,
                f"ℹ️ Ignore Signal. Already have an open position for {symbol}"
            )
            return

        # ---------- محاسبه مقدار سفارش ----------
        qty = calculate_risk_qty(symbol, signal["entry"], signal["sl"])
        if not qty:
            print("[WARN] Qty calculation failed")
            return

        print(f"[INFO] Opening {symbol} | qty={qty}")

        # ---------- ثبت سفارش بازار ----------
        order = session.place_order(
            category=order_category,
            symbol=symbol,
            side=signal["side"],
            orderType="Market",
            qty=str(qty),
            stopLoss=str(signal["sl"]),
            takeProfit=str(signal["targets"][0])
            # price=signal["entry"],
            # leverage=MAX_LEVERAGE,
        )

        # ثبت موفق → به cache اضافه شود
        open_positions.add(symbol)

        # ---------- تنظیم SL و اولین TP ----------
        # session.set_trading_stop(
        #     category=order_category,
        #     symbol=symbol,
        #     tpslMode="Full",
        #     stopLoss=str(signal["sl"]),
        #     takeProfit=str(signal["targets"][0]),
        #     positionIdx=0,
        # )

        print(
            f"[SUCCESS] Order placed: {symbol} | qty={qty} | SL={signal['sl']} | TP={signal['targets'][0]}"
        )

        # ---------- ارسال اطلاعات به تلگرام ----------
        await client.send_message(
            TARGET_CHANNEL,
            f"🚀 New Order Placed:\n"
            f"Symbol: {symbol}\n"
            f"Side: {signal['side']}\n"
            f"Entry: {signal['entry']}\n"
            f"Qty: {qty}\n"
            f"SL: {signal['sl']}\n"
            f"TP: {signal['targets'][0]}"
        )

    except Exception as e:
        await send_error_to_telegram(e, context="handle_signal")


# ---------------- HANDLE NEW MESSAGE ---------------- #
@client.on(events.NewMessage(chats=selected_source_channel))
async def new_message_handler(event):
    print("[INFO] New event received")

    message_text = event.message.message or ""
    msg_time = event.message.date.astimezone(ZoneInfo("Asia/Tehran"))
    formatted_time = msg_time.strftime("%Y-%m-%d | %H:%M:%S")

    if is_signal_message(message_text):
        print("[INFO] Signal detected")

        await client.send_message(
            TARGET_CHANNEL,
            (
                "📡 **New Signal Message Detected**\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "📨 **Original Message:**\n"
                "```\n"
                f"{message_text}\n\n"
                f"⏰ **Time:** `{formatted_time}`\n"
                "```"
            ),
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
                f"{message_text}\n\n"
                f"⏰ **Time:** `{formatted_time}`\n"
                "```"
            ),
        )


# ---------------- RUN ---------------- #
async def main():
    await client.start()
    print("[INFO] Telegram client started")
    global main_loop
    main_loop = asyncio.get_event_loop()

    # وب‌سوکت
    WSPrivate = WebSocket(
        demo=is_demo,
        testnet=False,
        channel_type="private",
        api_key=selected_api_key,
        api_secret=selected_api_secret,
        # trace_logging=True 
    )
    WSPrivate.order_stream(order_callback_ws)

    def handle_global_exception(loop, context):
        error = context.get("exception")
        if error:
            asyncio.create_task(send_error_to_telegram(error, context="GLOBAL"))

    loop = asyncio.get_event_loop()
    loop.set_exception_handler(handle_global_exception)
    # start processing queue
    asyncio.create_task(process_telegram_queue())

    await client.run_until_disconnected()
