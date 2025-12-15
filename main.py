from pybit.unified_trading import HTTP
from dotenv import load_dotenv
import os
import json
from datetime import datetime

# Load environment variables from .env file
load_dotenv()

# Set demo mode (True = demo, False = live)
is_demo = False

# Load API keys from environment variables
api_key = os.getenv("BYBIT_API_KEY")
api_secret = os.getenv("BYBIT_API_SECRET")
api_key_demo = os.getenv("BYBIT_API_KEY_DEMO")
api_secret_demo = os.getenv("BYBIT_API_SECRET_DEMO")

# Choose correct API keys based on demo mode
if is_demo:
    selected_api_key = api_key_demo
    selected_api_secret = api_secret_demo
else:
    selected_api_key = api_key
    selected_api_secret = api_secret

# ---------- Initialize Bybit HTTP session ----------
session = HTTP(
    demo=is_demo,            # Use demo flag if in demo mode
    api_key=selected_api_key,
    api_secret=selected_api_secret,
)

# ---------- Helper function to save JSON ----------
def save_json(filename: str, data: dict, demo_mode: bool):
    # Determine folder based on demo or live mode
    folder = "responses/demo" if demo_mode else "responses/live"
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
transaction_log = session.get_transaction_log(coin="BTC")
instruments_info = session.get_instruments_info(category="linear")
fee_rates = session.get_fee_rates(category="linear")
# Uncomment and use a valid symbol for demo/live
# fee_rates = session.get_fee_rates(category="linear", symbol="BTCUSDT")

# ---------- Save responses ----------
save_json(f"account_info_{timestamp}.json", account_info, is_demo)
save_json(f"wallet_balance_BTC_{timestamp}.json", wallet_balance, is_demo)
save_json(f"transaction_log_BTC_{timestamp}.json", transaction_log, is_demo)
save_json(f"instruments_info_linear_{timestamp}.json", instruments_info, is_demo)
save_json(f"fee_rates_{timestamp}.json", fee_rates, is_demo)
# save_json(f"fee_rates_linear_BTCUSDT_{timestamp}.json", fee_rates, is_demo)
