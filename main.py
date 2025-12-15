from pybit.unified_trading import HTTP
from dotenv import load_dotenv
import os

load_dotenv()

api_key = os.getenv("BYBIT_API_KEY")
api_secret = os.getenv("BYBIT_API_SECRET")
testnet = os.getenv("TESTNET") == "true"

session = HTTP(
    testnet=True,
    api_key="xxxxxxxxxxxxxxxxxx",
    api_secret="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
)
print(f"get_account_info:{session.get_account_info()}")
print(
    f"get_wallet_balance / UNIFIED, BTC: {session.get_wallet_balance(accountType='UNIFIED', coin='BTC')}"
)
print(f"session.get_transaction_log / BTC: {session.get_transaction_log(coin='BTC')}")
print(f"get_instruments_info / linear: {session.get_instruments_info(category='linear')}")
print(f"get_fee_rates / linear,DASHUSDT: {session.get_fee_rates(category="linear",symbol='DASHUSDT')}")