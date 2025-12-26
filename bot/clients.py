from pybit.unified_trading import HTTP
from config import IS_DEMO, SELECTED_API_KEY, SELECTED_API_SECRET
import asyncio
from telethon import TelegramClient
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH


# ---------------- BYBIT CLIENT ---------------- #
bybitClient = HTTP(
    demo=IS_DEMO,
    api_key=SELECTED_API_KEY,
    api_secret=SELECTED_API_SECRET,
)


# ---------------- TELEGRAM CLIENT ---------------- #
telClient = TelegramClient("session_name", TELEGRAM_API_ID, TELEGRAM_API_HASH)
telegram_queue = asyncio.Queue()
