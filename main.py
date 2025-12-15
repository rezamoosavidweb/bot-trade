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
    f"get_wallet_balance UNIFIED, BTC: {session.get_wallet_balance(accountType='UNIFIED', coin='BTC')}"
)
print(session.get_transaction_log(coin="BTC"))