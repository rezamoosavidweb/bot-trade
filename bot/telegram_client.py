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
    while True:
        item = await telegram_queue.get()
        try:
            if item.get("type") == "tg":
                text = item["text"]
                signal = parse_signal(text)
                if not signal:
                    print("[WARN] Invalid signal")
                    continue

                symbol = signal["symbol"]
                # ادامه پردازش سیگنال تلگرام...
                print(f"[INFO] TG Signal: {symbol}")

            elif item.get("type") == "ws":
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
                    msg = (
                        f"📥 **Order Update**\n"
                        f"Symbol: {symbol}\n"
                        f"Size: {size}"
                    )

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
