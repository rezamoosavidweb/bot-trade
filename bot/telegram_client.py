import asyncio
from telethon import events
from config import TARGET_CHANNEL
from config import open_positions
from bybit_client import calculate_fixed_trade, is_position_open
from regex_utils import parse_signal, is_signal_message
from errors import send_error_to_telegram
from api import set_leverage_safe, place_market_order
from zoneinfo import ZoneInfo
from clients import telClient

# ---------------- TELEGRAM CLIENT ---------------- #

telegram_queue = asyncio.Queue()


# ---------------- QUEUE PROCESSOR ---------------- #
async def process_telegram_queue():
    """Process queued Telegram signals and handle Bybit orders."""
    while True:
        item = await telegram_queue.get()
        try:
            if item.get("type") == "tg":
                # ---------------- SIGNAL TELEGRAM ---------------- #
                text = item["text"]
                signal = parse_signal(text)
                if not signal:
                    print("[WARN] Invalid signal")
                    continue

                print(
                    f"[INFO] Detect signal / {symbol} / entry:{signal['entry']} / tp:{signal['tp']} / sl:{signal['sl']} / leverage:{signal['leverage']}"
                )
                symbol = signal["symbol"]

                # Check open positions locally and in Bybit
                position_open = await is_position_open(symbol)
                if symbol in open_positions or position_open:
                    open_positions.add(symbol)
                    print(f"[INFO] Already in position: {symbol}")
                    await telClient.send_message(
                        TARGET_CHANNEL,
                        f"ℹ️ Ignore Signal. Already have an open position for {symbol}",
                    )
                    continue

                # Calculate fixed trade
                trade = await calculate_fixed_trade(
                    symbol, signal["entry"], signal["sl"]
                )
                if not trade:
                    print("[WARN] Trade calculation failed")
                    continue

                qty = trade["qty"]
                leverage = trade["leverage"]

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
                    f"[SUCCESS] Order placed: {symbol} | leverage={leverage} | qty={qty} | SL={signal['sl']} | TP={signal['targets'][0]}"
                )

                await telClient.send_message(
                    TARGET_CHANNEL,
                    f"🚀 New Order Placed:\n"
                    f"Symbol: {symbol}\n"
                    f"Side: {signal['side']}\n"
                    f"Entry: {signal['entry']}\n"
                    f"Qty: {qty}\n"
                    f"SL: {signal['sl']}\n"
                    f"TP: {signal['targets'][0]}\n"
                    f"Leverage: {leverage}",
                )

            elif item.get("type") == "ws":
                # ---------------- WEBSOCKET MESSAGE ---------------- #
                symbol = item["symbol"]
                size = item["size"]
                closed_pnl = item["closed_pnl"]
                is_closed = item["is_closed"]

                if is_closed:
                    msg = (
                        f"❌ **Position Closed**\n"
                        f"Symbol: {symbol}\n"
                        f"Size: {size}\n"
                        f"PnL: {closed_pnl}"
                    )
                else:
                    msg = f"📥 **Order Update**\n" f"Symbol: {symbol}\n" f"Size: {size}"

                await telClient.send_message(TARGET_CHANNEL, msg)

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
