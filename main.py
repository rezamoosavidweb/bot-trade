from pybit.unified_trading import HTTP
from dotenv import load_dotenv
import os
import json
from datetime import datetime

load_dotenv()

api_key = os.getenv("BYBIT_API_KEY")
api_secret = os.getenv("BYBIT_API_SECRET")

session = HTTP(
    demo=True,
    api_key=api_key,
    api_secret=api_secret,
)

# ---------- helper function ----------
def save_json(filename: str, data: dict):
    os.makedirs("responses", exist_ok=True)
    filepath = os.path.join("responses", filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✅ Saved: {filepath}")


timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# ---------- API calls ----------
account_info = session.get_account_info()
wallet_balance = session.get_wallet_balance(
    accountType="UNIFIED",
    coin="BTC",
)
transaction_log = session.get_transaction_log(coin="BTC")
instruments_info = session.get_instruments_info(category="linear")
fee_rates = session.get_fee_rates(category="linear", symbol="DASHUSDT")

# ---------- save responses ----------
save_json(f"account_info_{timestamp}.json", account_info)
save_json(f"wallet_balance_BTC_{timestamp}.json", wallet_balance)
save_json(f"transaction_log_BTC_{timestamp}.json", transaction_log)
save_json(f"instruments_info_linear_{timestamp}.json", instruments_info)
save_json(f"fee_rates_linear_DASHUSDT_{timestamp}.json", fee_rates)
