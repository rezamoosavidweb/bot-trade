import asyncio
from telethon import TelegramClient, events
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TARGET_CHANNEL, main_loop
from config import open_positions, stats
from signals import parse_signal
from bybit_client import session, calculate_fixed_trade, is_position_open
from errors import send_error_to_telegram
import datetime
from zoneinfo import ZoneInfo

client = TelegramClient("session_name", TELEGRAM_API_ID, TELEGRAM_API_HASH)
telegram_queue = asyncio.Queue()

# ---------------- QUEUE PROCESSOR ---------------- #
async def process_telegram_queue():
    while True:
        item = await telegram_queue.get()
        try:
            # handle position closed / active
            # same logic as your original process_telegram_queue function
            ...
        except Exception as e:
            print("[ERROR] Telegram send failed:", e)
        telegram_queue.task_done()

# ---------------- NEW MESSAGE HANDLER ---------------- #
def register_telegram_handlers(source_channel):
    @client.on(events.NewMessage(chats=source_channel))
    async def new_message_handler(event):
        message_text = event.message.message or ""
        msg_time = event.message.date.astimezone(ZoneInfo("Asia/Tehran"))
        formatted_time = msg_time.strftime("%Y-%m-%d | %H:%M:%S")

        if parse_signal(message_text):
            print("[INFO] Signal detected")
            # forward to queue
            await telegram_queue.put(event.message)
        else:
            print("[INFO] Non-signal message ignored")
