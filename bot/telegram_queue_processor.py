import asyncio
from zoneinfo import ZoneInfo
from telethon import events

from config import TARGET_CHANNEL, open_positions
from bybit_client import calculate_fixed_trade, is_position_open
from regex_utils import parse_signal, is_signal_message
from errors import send_error_to_telegram
from api import set_leverage_safe, place_market_order, set_trading_stop
from clients import telClient

# ---------------- TELEGRAM QUEUE ---------------- #
telegram_queue = asyncio.Queue()


# ---------------- HELPER FUNCTIONS ---------------- #
def set_sl_tp_partial(
    symbol: str,
    position_idx: int,
    tp1: float,
    sl1: float,
    tp2: float,
    sl2: float,
    qty: float,
):
    """
    Set the Stop Loss for the entire position and two partial Take Profits (TP1 and TP2).

    :param symbol: Symbol like 'BTCUSDT'
    :param position_idx: Position index (0 for one-way, 1/2 for hedge)
    :param tp1: Take Profit price for first half
    :param sl1: Stop Loss for first half
    :param tp2: Take Profit price for second half
    :param sl2: Stop Loss for second half
    :param qty: Total position quantity
    """
    try:
        # Set partial TP/SL for first half
        set_trading_stop(
            symbol=symbol,
            tpslMode="Partial",
            positionIdx=position_idx,
            takeProfit=str(tp1),
            stopLoss=str(sl1),
            tpSize=str(qty / 2),
            slSize=str(qty / 2),
        )

        # Set partial TP/SL for second half
        set_trading_stop(
            symbol=symbol,
            tpslMode="Partial",
            positionIdx=position_idx,
            takeProfit=str(tp2),
            stopLoss=str(sl2),
            tpSize=str(qty / 2),
            slSize=str(qty / 2),
        )

        print(f"[INFO] SL and Partial TPs set for {symbol}")

    except Exception as e:
        print(f"[ERROR] Failed to set SL/TP for {symbol}: {e}")


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
        # sl=str(signal["sl"]),
        # tp=str(
        #     signal["targets"][0]  # temporary, main TP replaced by partial logic below
        # ),
    )

    open_positions.add(symbol)

    if signal["side"] == "Buy":
        sl2 = signal["entry"] * (1 + 0.0011)
    else:  # Sell
        sl2 = signal["entry"] * (1 - 0.0011)

    set_trading_stop(
        symbol=symbol,
        tpslMode="Partial",
        positionIdx=0,
        takeProfit=signal["targets"][0],
        stopLoss=str(signal["sl"]),
        slSize=str(qty / 2),
        tpSize=str(qty / 2),
    )

    set_trading_stop(
        symbol=symbol,
        tpslMode="Partial",
        positionIdx=0,
        takeProfit=signal["targets"][1],
        stopLoss=None,
        tpSize=str(qty / 2),
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


async def handle_ws_message(item):
    """
    Handle WebSocket messages from Bybit: new order, cancel, close position, or SL/TP updates.
    Formats message and sends to Telegram channel.
    """
    ws_type = item.get("msg_type")
    data = item.get("data")
    symbol = item.get("symbol")
    size = float(data.get("qty", 0))
    price = data.get("price")
    avg_price = data.get("avgPrice")
    closed_pnl = item.get("closed_pnl")
    take_profit = data.get("takeProfit")
    stop_loss = data.get("stopLoss")
    stop_order_type = data.get("stopOrderType")
    tpsl_mode = data.get("tpslMode")
    create_type = data.get("createType")

    # ---------------- Check if this message is related to set_trading_stop ----------------
    if stop_order_type in ["TakeProfit", "StopLoss", "PartialTakeProfit"]:
        side = data.get("side")
        text = (
            f"⚡ SL/TP Update Detected\n\n"
            f"Symbol: {symbol}\n"
            f"Side: {size}\n"
            f"Qty: {size}\n"
            f"SL: {stop_loss or '—'}\n"
            f"TP: {take_profit or '—'}\n"
            f"Mode: {tpsl_mode}\n"
            f"Type: {stop_order_type}\n"
            f"CreatedBy: {create_type}\n"
            f"OrderID: {data.get('orderId')}"
        )

    # ---------------- Regular WebSocket messages ----------------
    elif ws_type == "new_order":
        fee_multiplier = 0.0011
        if side.lower() == "buy":
            sl2 = price * (1 + fee_multiplier)
        else:
            sl2 = price * (1 - fee_multiplier)
            
        # set SL2 base on filled price + fee(2*0.0005)
        set_trading_stop(
            symbol=symbol,
            tpslMode="Partial",
            positionIdx=0,
            takeProfit=None,
            stopLoss=str(sl2),
            slSize=str(size / 2),
        )
        text = (
            f"📤 New Order Filled\n\n"
            f"Symbol: {symbol}\nSide: {data.get('side')}\nQty: {size}\n"
            f"Price: {price}\nAvgPrice: {avg_price}\nSL: {stop_loss or '—'}\n"
            f"TP: {take_profit or '—'}\nOrderID: {data.get('orderId')}"
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
