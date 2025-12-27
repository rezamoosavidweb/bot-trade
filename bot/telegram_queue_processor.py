import asyncio
from telethon import events
from zoneinfo import ZoneInfo

from config import TARGET_CHANNEL, open_positions
from bybit_client import calculate_fixed_trade, is_position_open
from regex_utils import parse_signal, is_signal_message
from errors import send_error_to_telegram
from api import set_leverage_safe, place_market_order
from clients import telClient

# ---------------- TELEGRAM CLIENT ---------------- #
telegram_queue = asyncio.Queue()


# ---------------- HELPER FUNCTIONS ---------------- #
async def handle_telegram_signal(item):
    text = item["text"]
    signal = parse_signal(text)
    if not signal:
        print("[WARN] Invalid signal")
        return

    symbol = signal["symbol"]

    # Check open positions locally and on Bybit
    if symbol in open_positions or await is_position_open(symbol):
        open_positions.add(symbol)
        print(f"[INFO] Already in position: {symbol}")
        await telClient.send_message(
            TARGET_CHANNEL,
            f"ℹ️ Ignore Signal. Already have an open position for {symbol}",
        )
        return

    # Calculate trade
    trade = await calculate_fixed_trade(symbol, signal["entry"], signal["sl"])
    if not trade:
        print("[WARN] Trade calculation failed")
        return

    qty, leverage = trade["qty"], trade["leverage"]

    print(
        f"[INFO] Detected signal / {symbol} / qty:{qty} / entry:{signal['entry']} "
        f"/ tp:{signal['targets'][0]} / sl:{signal['sl']} / leverage:{leverage}"
    )

    # Set leverage safely
    try:
        set_leverage_safe(symbol=symbol, leverage=str(leverage))
    except Exception as e:
        if "leverage not modified" in str(e):
            print(f"[INFO] Leverage already set for {symbol}, skipping...")
        else:
            await telClient.send_message(
                TARGET_CHANNEL,
                f"⚠️ Error on setLeverage for {symbol}: {e}",
            )
            raise e

    # Place market order
    place_market_order(
        symbol=symbol,
        side=signal["side"],
        qty=str(qty),
        sl=str(signal["sl"]),
        tp=str(signal["targets"][0]),
    )
    open_positions.add(symbol)

    print(
        f"[SUCCESS] Order placed: {symbol} | leverage={leverage} | qty={qty} | "
        f"SL={signal['sl']} | TP={signal['targets'][0]}"
    )

    await telClient.send_message(
        TARGET_CHANNEL,
        f"🚀 New Order Placed:\n"
        f"Symbol: {symbol}\nSide: {signal['side']}\nEntry: {signal['entry']}\n"
        f"Qty: {qty}\nSL: {signal['sl']}\nTP: {signal['targets'][0]}\nLeverage: {leverage}",
    )


async def handle_ws_message(item):
    ws_type = item.get("msg_type")
    data = item.get("data")
    symbol = item.get("symbol")
    size = float(data.get("qty", 0))
    price = data.get("price")
    avg_price = data.get("avgPrice")
    closed_pnl = item.get("closed_pnl")
    take_profit = item.get("takeProfit")
    stop_loss = item.get("stopLoss")

    if ws_type == "new_order":
        text = (
            f"📤 New Order Filled\n\n"
            f"Symbol: {symbol}\nSide: {data.get('side')}\nQty: {size}\n"
            f"Price: {price}\nAvgPrice: {avg_price}\nSL: {stop_loss}\n"
            f"TP: {take_profit}\nOrderID: {data.get('orderId')}"
        )
    elif ws_type == "cancel_order":
        text = (
            f"❌ Order Cancelled\n\n"
            f"Symbol: {symbol}\nQty: {size}\nPrice: {price}\nAvgPrice: {avg_price}\n"
            f"Reason: {data.get('cancelType')}\nOrderID: {data.get('orderId')}"
        )
    elif ws_type == "close_position":
        text = (
            f"🔒 Position Closed\n\n"
            f"Symbol: {symbol}\nSide: {data.get('side')}\nSize: {size}\n"
            f"Price: {price}\nAvgPrice: {avg_price}\nClosed PnL: {closed_pnl}\n"
            f"OrderID: {data.get('orderId')}"
        )
    else:
        text = f"ℹ️ WS Message: {data}"

    await telClient.send_message(TARGET_CHANNEL, text)


# ---------------- QUEUE PROCESSOR ---------------- #
async def process_telegram_queue():
    """Process queued Telegram signals and WebSocket messages."""
    while True:
        item = await telegram_queue.get()
        try:
            if item.get("type") == "tg":
                await handle_telegram_signal(item)
            elif item.get("type") == "ws":
                await handle_ws_message(item)
        except Exception as e:
            await send_error_to_telegram(e, context="process_telegram_queue")
        finally:
            telegram_queue.task_done()


# ---------------- NEW MESSAGE HANDLER ---------------- #
def register_telegram_handlers(source_channel):
    """Register handler for incoming Telegram messages."""

    @telClient.on(events.NewMessage(chats=source_channel))
    async def new_message_handler(event):
        message_text = event.message.message or ""
        msg_time = event.message.date.astimezone(ZoneInfo("Asia/Tehran"))
        formatted_time = msg_time.strftime("%Y-%m-%d | %H:%M:%S")

        if is_signal_message(message_text):
            print(f"[INFO] Signal detected / {formatted_time}")
            await telegram_queue.put(
                {
                    "type": "tg",
                    "event": event.message,
                    "text": message_text,
                    "time": formatted_time,
                }
            )
        else:
            print(f"[INFO] Non-signal message ignored / {formatted_time}")
