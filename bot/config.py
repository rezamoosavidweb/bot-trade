import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

# ---------------- Event Loop ---------------- #
try:
    main_loop = asyncio.get_running_loop()
except RuntimeError:
    main_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(main_loop)

# ---------------- MODE ---------------- #
IS_DEMO = True

# ---------------- API KEYS ---------------- #
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
SOURCE_CHANNEL = os.getenv("SOURCE_CHANNEL")
# SOURCE_CHANNEL = int(os.getenv("TARGET_CHANNEL"))
TARGET_CHANNEL = int(os.getenv("TARGET_CHANNEL"))

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
BYBIT_API_KEY_DEMO = os.getenv("BYBIT_API_KEY_DEMO")
BYBIT_API_SECRET_DEMO = os.getenv("BYBIT_API_SECRET_DEMO")

# Select API based on mode
if IS_DEMO:
    SELECTED_API_KEY = BYBIT_API_KEY_DEMO
    SELECTED_API_SECRET = BYBIT_API_SECRET_DEMO
    MODE_NAME = "demo"
else:
    SELECTED_API_KEY = BYBIT_API_KEY
    SELECTED_API_SECRET = BYBIT_API_SECRET
    MODE_NAME = "live"

SELECTED_SOURCE_CHANNEL = SOURCE_CHANNEL

# ---------------- CONSTANTS ---------------- #
POSITION_USDT = 50
ORDER_CATEGORY = "linear"
RISK_PERCENT = 0.01
MAX_LEVERAGE = 15
SETTLE_COIN = "USDT"

# MAX_POSITION_USDT = 2000
FIXED_MARGIN_USDT = 300
MAX_LOSS_USDT = 30
TARGET_PROFIT_USDT = 15

# ---------------- GLOBALS ---------------- #
symbol_cache = {}
open_positions = set()
stats = {"total": 0, "win": 0, "loss": 0, "pnl": 0.0}
