from pybit.unified_trading import HTTP, WebSocket
from dotenv import load_dotenv
import os
import json
from datetime import datetime

# WebSocket()
# Load environment variables from .env file
load_dotenv()

# -------- MODE FLAGS --------
is_demo = True
is_testnet = False   # ← اگر تست‌نت است True

# -------- API KEYS --------
API_KEY_LIVE = os.getenv("BYBIT_API_KEY")
API_SECRET_LIVE = os.getenv("BYBIT_API_SECRET")

API_KEY_DEMO = os.getenv("BYBIT_API_KEY_DEMO")
API_SECRET_DEMO = os.getenv("BYBIT_API_SECRET_DEMO")

API_KEY_TESTNET = os.getenv("BYBIT_API_KEY_TESTNET")
API_SECRET_TESTNET = os.getenv("BYBIT_API_SECRET_TESTNET")

# -------- SELECT API KEYS --------
if is_demo:
    selected_api_key = API_KEY_DEMO
    selected_api_secret = API_SECRET_DEMO
    mode_name = "demo"
    selected_symbol = "BTCUSDT"
    coin="BTC"
    settleCoin="USDT"

elif is_testnet:
    selected_api_key = API_KEY_TESTNET
    selected_api_secret = API_SECRET_TESTNET
    mode_name = "testnet"
    selected_symbol = "BTCUSDC"
    coin="BTC"
    settleCoin="USDT"

else:
    selected_api_key = API_KEY_LIVE
    selected_api_secret = API_SECRET_LIVE
    selected_symbol = "BTCUSDT"
    coin="BTC"
    mode_name = "live"
    settleCoin="USDT"

print(f"=======================================")
print(f"🔑 Mode: {mode_name}")
print(f"API KEY: {selected_api_key[:6]}****")
print(f"selected_symbol: {selected_symbol}")
print(f"=======================================")



# ---------- Initialize Bybit HTTP session ----------
session = HTTP(
    demo=is_demo,
    testnet=is_testnet,
    api_key=selected_api_key,
    api_secret=selected_api_secret,
)

# ---------- Helper function to save JSON ----------
def save_json(filename: str, data: dict, demo_mode: bool, testnet_mode:bool):
    # Determine folder based on demo or live mode
    if demo_mode:
        folder = "responses/demo"
    elif testnet_mode:
        folder = "responses/testnet"
    else:
        folder = "responses/live"
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, filename)

    # Write data to JSON file
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✅ Saved: {filepath}")


# Get current timestamp for filenames
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# ---------- API calls ----------
account_info = session.get_account_info()
wallet_balance = session.get_wallet_balance(
    accountType="UNIFIED",
    coin="BTC",
)
transaction_log = session.get_transaction_log()
instruments_info = session.get_instruments_info(category="linear")
# fee_rates = session.get_fee_rates(category="linear")
positions_info = session.get_positions(category="linear",settleCoin=settleCoin)
# fee_rates = session.get_fee_rates(category="linear", symbol=selected_symbol)
closed_pnl = session.get_closed_pnl(category="linear")

# ---------- Save responses ----------
save_json(f"account_info.json", account_info, is_demo,is_testnet)
save_json(f"wallet_balance.json", wallet_balance, is_demo,is_testnet)
save_json(f"transaction_log.json", transaction_log, is_demo,is_testnet)
save_json(f"instruments_info_linear.json", instruments_info, is_demo,is_testnet)
save_json(f"closed_pnl.json", closed_pnl, is_demo,is_testnet)
# save_json(f"fee_rates.json", fee_rates, is_demo,is_testnet)
save_json(f"{settleCoin}_positions_info.json", positions_info, is_demo,is_testnet)
