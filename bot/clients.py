from pybit.unified_trading import HTTP
from config import (
    IS_DEMO,
    SELECTED_API_KEY,
    SELECTED_API_SECRET,
    BYBIT_API_KEY,
    BYBIT_API_SECRET,
)
import asyncio
from telethon import TelegramClient
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH


# ---------------- BYBIT CLIENT (DEMO) ---------------- #
# Used for trading operations (place orders, set leverage, etc.)
bybitClient = HTTP(
    demo=IS_DEMO,
    api_key=SELECTED_API_KEY,
    api_secret=SELECTED_API_SECRET,
)

# ---------------- BYBIT CLIENT (LIVE) ---------------- #
# Used for liquidity analysis only (order book, ticker, etc.)
# This uses real market data even when trading in demo mode
bybitClientLive = HTTP(
    demo=False,  # Always use live for real market data
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET,
)


# ---------------- TELEGRAM CLIENT ---------------- #
telClient = TelegramClient("session_name", TELEGRAM_API_ID, TELEGRAM_API_HASH)
telegram_queue = asyncio.Queue()
