import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from telethon import events
from logger import log_print

from config import (
    TARGET_CHANNEL,
)
from cache import (
    add_open_position,
    is_position_open as is_position_open_redis,
    set_position_entry_time,
    set_position_tp_prices,
    set_position_remaining_size,
)
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
from capital_tracker import track_position_opened
from liquidity_analyzer import (
    analyze_symbol_liquidity,
    track_order_execution,
    calculate_liquidity_metrics,
)
from config import FIXED_MARGIN_USDT

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
        log_print("[WARN] Invalid signal")
        return

    symbol = signal["symbol"]

    # Check if position is already open
    is_open_redis = await is_position_open_redis(symbol)
    is_open_bybit = await is_position_open(symbol)
    if is_open_redis or is_open_bybit:
        await add_open_position(symbol)
        log_print(f"[INFO] Already in position: {symbol}")
        await telClient.send_message(
            TARGET_CHANNEL,
            f"ℹ️ Ignore Signal. Already have an open position for {symbol}",
        )
        return

    # Calculate trade size and leverage
    trade = await calculate_fixed_trade(symbol, signal["entry"], signal["sl"])
    if not trade:
        log_print("[WARN] Trade calculation failed")
        return

    qty, leverage = trade["qty"], trade["leverage"]

    tp_info = f"tp1:{signal['targets'][0]} / tp2:{signal['targets'][1]}"
    if len(signal["targets"]) >= 3:
        tp_info += f" / tp3:{signal['targets'][2]}"
    log_print(
        f"[INFO] Detected signal / {symbol} / qty:{qty} / entry:{signal['entry']} "
        f"/ {tp_info} / sl:{signal['sl']} / leverage:{leverage}"
    )

    # Set leverage safely
    try:
        set_leverage_safe(symbol=symbol, leverage=str(leverage))
    except Exception as e:
        if "leverage not modified" in str(e):
            log_print(f"[INFO] Leverage already set for {symbol}, skipping...")
        else:
            await telClient.send_message(
                TARGET_CHANNEL,
                f"⚠️ Error on setLeverage for {symbol}: {e}",
            )
            raise e

    # Place market order
    try:
        order_result = place_market_order(
            symbol=symbol,
            side=signal["side"],
            qty=str(qty),
            sl=signal["sl"],
        )

        # Extract order ID from result
        order_id = None
        if isinstance(order_result, dict):
            order_id = order_result.get("result", {}).get(
                "orderId"
            ) or order_result.get("result", {}).get("orderLinkId")

        # If order succeeded, track position opened
        await add_open_position(symbol)
        # Track position opened for capital tracking
        track_position_opened(symbol, FIXED_MARGIN_USDT, margin=trade.get("margin"))
    except Exception as e:
        # Track rejected order if it's due to insufficient balance
        error_str = str(e).lower()
        if any(
            keyword in error_str
            for keyword in ["insufficient", "balance", "margin", "not enough", "funds"]
        ):
            from capital_tracker import track_rejected_order

            track_rejected_order(symbol, str(e), FIXED_MARGIN_USDT)
        raise e

    # Store entry time to check 30-minute rule
    await set_position_entry_time(symbol, datetime.now(ZoneInfo("Asia/Tehran")))
    # Store TP prices and entry to identify which TP/SL was triggered
    tp_prices = {
        "entry": signal["entry"],
        "tp1": signal["targets"][0],
        "tp2": signal["targets"][1],
        "sl": signal["sl"],
        "side": signal["side"],
    }
    if len(signal["targets"]) >= 3:
        tp_prices["tp3"] = signal["targets"][2]
    await set_position_tp_prices(symbol, tp_prices)
    await set_position_remaining_size(symbol, qty)

    # Set TP1 and TP2 with distribution 60% and 40%
    # Get qty_step for normalization
    symbol_info = await get_symbol_info(symbol)
    qty_step = symbol_info.get("qty_step", 1)

    # Calculate TP1 (40%) and TP2 (60%)
    # Close the full size on TP1 (do NOT truncate decimals)
    # qty is already normalized in calculate_fixed_trade(), but we re-normalize for safety.
    tp1_qty = qty
    # tp1_qty = int(qty * 0.40)
    # tp2_qty = qty - tp1_qty  # Remaining 40%

    # Normalize qty values with step size
    tp1_qty = normalize_qty(tp1_qty, qty_step)
    # tp2_qty = normalize_qty(tp2_qty, qty_step)

    # Ensure that tp1_qty + tp2_qty = qty
    # if tp1_qty + tp2_qty != qty:
        # If normalization caused changes, adjust tp2_qty
        # tp2_qty = normalize_qty(qty - tp1_qty, qty_step)

    # Set TP1 with 60% of quantity
    set_trading_stop(
        symbol=symbol,
        tpslMode="Partial",
        positionIdx=0,
        tp=signal["targets"][0],
        tpSize=str(tp1_qty),
    )

    # Set TP2 with 40% of quantity
    # set_trading_stop(
    #     symbol=symbol,
    #     tpslMode="Partial",
    #     positionIdx=0,
    #     tp=signal["targets"][1],
    #     tpSize=str(tp2_qty),
    # )

    tp_message = f"TP1: {signal['targets'][0]}\nTP2: {signal['targets'][1]}"

    await telClient.send_message(
        TARGET_CHANNEL,
        f"🚀 New Order Placed:\n"
        f"Symbol: {symbol}\nSide: {signal['side']}\nEntry: {signal['entry']}\n"
        f"Qty: {qty}\nSL: {signal['sl']}\n{tp_message}\n"
        f"Leverage: {leverage}\n"
        f"TP1 Qty: {tp1_qty} (100%)\n",
        # f"TP1 Qty: {tp1_qty} (40%)\nTP2 Qty: {tp2_qty} (60%)",
    )

    log_print(f"[SUCCESS] Order placed and SL/TP configured for {symbol}")


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
            log_print(f"[INFO] Signal detected / {formatted_time}")
            await telegram_queue.put(
                {
                    "type": "tg",
                    "event": event.message,
                    "text": message_text,
                    "time": formatted_time,
                }
            )
        else:
            log_print(f"[INFO] Non-signal message ignored / {formatted_time}")
