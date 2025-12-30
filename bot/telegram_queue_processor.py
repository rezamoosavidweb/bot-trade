import asyncio
from zoneinfo import ZoneInfo
from telethon import events

from config import TARGET_CHANNEL, open_positions
from bybit_client import (
    calculate_fixed_trade,
    is_position_open,
    normalize_qty,
    get_symbol_info,
)
from regex_utils import parse_signal, is_signal_message
from errors import send_error_to_telegram
from api import set_leverage_safe, place_market_order, set_trading_stop
from clients import telClient
from ws_message_formatter import handle_ws_message

# ---------------- TELEGRAM QUEUE ---------------- #
telegram_queue = asyncio.Queue()


async def handle_telegram_signal(item):
    """
    Handle incoming Telegram signal messages: validate, calculate trade, place order,
    set leverage, and configure SL/TP using partial TP logic.
    """
    text = item["text"]
    signal = parse_signal(text)
    if not signal:
        print("[WARN] Invalid signal")
        return

    symbol = signal["symbol"]

    # Check if position is already open
    if symbol in open_positions or await is_position_open(symbol):
        open_positions.add(symbol)
        print(f"[INFO] Already in position: {symbol}")
        await telClient.send_message(
            TARGET_CHANNEL,
            f"ℹ️ Ignore Signal. Already have an open position for {symbol}",
        )
        return

    # Calculate trade size and leverage
    trade = await calculate_fixed_trade(symbol, signal["entry"], signal["sl"])
    if not trade:
        print("[WARN] Trade calculation failed")
        return

    qty, leverage = trade["qty"], trade["leverage"]

    print(
        f"[INFO] Detected signal / {symbol} / qty:{qty} / entry:{signal['entry']} "
        f"/ tp1:{signal['targets'][0]} / tp2:{signal['targets'][1]} / sl:{signal['sl']} / leverage:{leverage}"
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
        sl=signal["sl"],  # Todo:after set sl2 to it should be equal with None
        # tp=str(
        #     signal["targets"][0]  # temporary, main TP replaced by partial logic below
        # ),
    )

    open_positions.add(symbol)

    if signal["side"] == "Buy":
        sl2 = signal["entry"] * (1 + 0.0011)
    else:  # Sell
        sl2 = signal["entry"] * (1 - 0.0011)

    # محاسبه TP1 و TP2 به گونه‌ای که کل position بسته شود
    # TP1: نصف اول (یا کمتر اگر qty فرد باشد)
    # TP2: باقی‌مانده (برای اطمینان از بسته شدن کامل position)
    # دریافت qty_step برای normalize کردن
    symbol_info = await get_symbol_info(symbol)
    qty_step = symbol_info.get("qty_step", 1)

    tp1_qty = qty // 2  # تقسیم صحیح (floor)
    tp2_qty = qty - tp1_qty  # باقی‌مانده

    # Normalize کردن qty ها با step size
    tp1_qty = normalize_qty(tp1_qty, qty_step)
    tp2_qty = normalize_qty(tp2_qty, qty_step)

    # اطمینان از اینکه tp1_qty + tp2_qty = qty
    if tp1_qty + tp2_qty != qty:
        # اگر normalize باعث تغییر شد، tp2_qty را تنظیم می‌کنیم
        tp2_qty = normalize_qty(qty - tp1_qty, qty_step)

    set_trading_stop(
        symbol=symbol,
        tpslMode="Partial",
        positionIdx=0,
        tp=signal["targets"][0],
        # sl=None,  # Todo:after set sl2 to it should be equal with signal['sl']
        slSize=str(tp1_qty),
        tpSize=str(tp1_qty),
    )

    set_trading_stop(
        symbol=symbol,
        tpslMode="Partial",
        positionIdx=0,
        tp=signal["targets"][1],
        # sl=None,
        tpSize=str(tp2_qty),  # باقی‌مانده برای اطمینان از بسته شدن کامل
    )

    # Notify Telegram channel
    await telClient.send_message(
        TARGET_CHANNEL,
        f"🚀 New Order Placed:\n"
        f"Symbol: {symbol}\nSide: {signal['side']}\nEntry: {signal['entry']}\n"
        f"Qty: {qty}\nSL: {signal['sl']}\nTP1: {signal['targets'][0]}\nTP2: {signal['targets'][1]}\n"
        f"Leverage: {leverage}",
    )

    print(f"[SUCCESS] Order placed and SL/TP configured for {symbol}")


# handle_ws_message moved to ws_message_formatter.py


# ---------------- QUEUE PROCESSOR ---------------- #
async def process_telegram_queue():
    """
    Continuously process messages in the Telegram queue.
    Supports both Telegram signals and WebSocket messages.
    """
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


# ---------------- TELEGRAM HANDLER REGISTRATION ---------------- #
def register_telegram_handlers(source_channel):
    """
    Register Telegram command and message handlers for signals and commands.
    """

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
