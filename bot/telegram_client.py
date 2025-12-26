import asyncio
from telethon import TelegramClient, events
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TARGET_CHANNEL
from config import open_positions, stats
from bybit_client import session, calculate_fixed_trade, is_position_open
from regex_utils import parse_signal, is_signal_message
from errors import send_error_to_telegram
import datetime
from zoneinfo import ZoneInfo

# ---------------- TELEGRAM CLIENT ---------------- #
client = TelegramClient("session_name", TELEGRAM_API_ID, TELEGRAM_API_HASH)
telegram_queue = asyncio.Queue()


# ---------------- QUEUE PROCESSOR ---------------- #
async def process_telegram_queue():
    """Process queued Telegram signals and handle Bybit orders."""
    while True:
        message = await telegram_queue.get()
        try:
            text = message.message
            signal = parse_signal(text)
            if not signal:
                print("[WARN] Invalid signal")
                telegram_queue.task_done()
                continue

            symbol = signal["symbol"]

            # Check open positions locally and in Bybit
            position_open = is_position_open(symbol)
            if symbol in open_positions or position_open:
                open_positions.add(symbol)
                print(f"[INFO] Already in position: {symbol}")
                await client.send_message(
                    TARGET_CHANNEL,
                    f"ℹ️ Ignore Signal. Already have an open position for {symbol}",
                )
                telegram_queue.task_done()
                continue

            # Calculate fixed trade
            trade = calculate_fixed_trade(symbol, signal["entry"], signal["sl"])
            if not trade:
                print("[WARN] Trade calculation failed")
                telegram_queue.task_done()
                continue

            qty = trade["qty"]
            leverage = trade["leverage"]

            # Set leverage
            try:
                session.set_leverage(
                    category="linear",
                    symbol=symbol,
                    buyLeverage=str(leverage),
                    sellLeverage=str(leverage),
                )
            except Exception as e:
                # Ignore "leverage not modified" error
                if "leverage not modified" in str(e):
                    print(f"[INFO] Leverage already set for {symbol}, skipping...")
                else:
                    # Other errors should be reported
                    await client.send_message(
                        TARGET_CHANNEL,
                        f"ℹ️ Catch Error on setLeverage for {symbol}. error: {e}",
                    )
                    raise e

            # Place market order
            session.place_order(
                category="linear",
                symbol=symbol,
                side=signal["side"],
                orderType="Market",
                qty=str(qty),
                stopLoss=str(signal["sl"]),
                takeProfit=str(signal["targets"][0]),
            )

            open_positions.add(symbol)

            print(
                f"[SUCCESS] Order placed: {symbol} | leverage={leverage} | qty={qty} | SL={signal['sl']} | TP={signal['targets'][0]}"
            )

            # Send info to Telegram
            await client.send_message(
                TARGET_CHANNEL,
                f"🚀 New Order Placed:\n"
                f"Symbol: {symbol}\n"
                f"Side: {signal['side']}\n"
                f"Entry: {signal['entry']}\n"
                f"Qty: {qty}\n"
                f"SL: {signal['sl']}\n"
                f"TP: {signal['targets'][0]}",
                f"Leverage: {leverage}",
            )

        except Exception as e:
            await send_error_to_telegram(e, context="process_telegram_queue")
        finally:
            telegram_queue.task_done()


# ---------------- NEW MESSAGE HANDLER ---------------- #
def register_telegram_handlers(source_channel):
    """Register handler for incoming Telegram messages."""

    @client.on(events.NewMessage(chats=source_channel))
    async def new_message_handler(event):
        message_text = event.message.message or ""
        msg_time = event.message.date.astimezone(ZoneInfo("Asia/Tehran"))
        formatted_time = msg_time.strftime("%Y-%m-%d | %H:%M:%S")

        if is_signal_message(message_text):
            print("[INFO] Signal detected")
            # await client.send_message(
            #     TARGET_CHANNEL,
            #     (
            #         "📡 **New Signal Message Detected**\n"
            #         "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            #         "📨 **Original Message:**\n"
            #         "```\n"
            #         f"{message_text}\n\n"
            #         f"⏰ **Time:** `{formatted_time}`\n"
            #         "```"
            #     ),
            # )
            await telegram_queue.put(event.message)
        else:
            print("[INFO] Non-signal message ignored")
