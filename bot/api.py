from clients import bybitClient
from pybit.exceptions import InvalidRequestError


def get_wallet_balance():
    wallet = bybitClient.get_wallet_balance(accountType="UNIFIED")
    return wallet


def get_all_linear_instruments(limit=200):
    cursor = None
    instruments = []

    while True:
        res = bybitClient.get_instruments_info(
            category="linear",
            limit=limit,
            cursor=cursor,
        )

        instruments.extend(res["result"]["list"])

        cursor = res["result"].get("nextPageCursor")
        if not cursor:
            break

    return instruments

def get_symbol_positions(symbol):
    return bybitClient.get_positions(
            category="linear",
            symbol=symbol,
        )

def get_transaction_log(limit=50):
    return bybitClient.get_transaction_log(
        accountType="UNIFIED",
        category="linear",
        limit=limit,
    )


def get_single_instrument(symbol: str):
    res = bybitClient.get_instruments_info(
        category="linear",
        symbol=symbol,
        limit=1,
    )
    return res["result"]["list"][0]


def set_leverage_safe(symbol: str, leverage: float):
    try:
        bybitClient.set_leverage(
            category="linear",
            symbol=symbol,
            buyLeverage=str(leverage),
            sellLeverage=str(leverage),
        )
        return True
    except InvalidRequestError as e:
        if "110043" in str(e):
            # leverage not modified
            return False
        raise


def place_market_order(symbol, side, qty, sl, tp):
    return bybitClient.place_order(
        category="linear",
        symbol=symbol,
        side=side,
        orderType="Market",
        qty=str(qty),
        stopLoss=str(sl),
        takeProfit=str(tp),
    )
