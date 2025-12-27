from clients import bybitClient
from pybit.exceptions import InvalidRequestError


def get_wallet_balance():
    wallet = bybitClient.get_wallet_balance(accountType="UNIFIED")
    return wallet
def get_account_info():
    wallet = bybitClient.get_account_info()
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


def get_positions(symbol: str | None = None, settleCoin: str | None = None):
    if not symbol and not settleCoin:
        raise ValueError("Either symbol or settleCoin must be provided")

    params = {"category": "linear"}

    if symbol:
        params["symbol"] = symbol
    if settleCoin:
        params["settleCoin"] = settleCoin

    res = bybitClient.get_positions(**params)
    return res.get("result", {}).get("list", [])


def get_pending_orders(settleCoin: str):
    res = bybitClient.get_open_orders(
        category="linear",
        settleCoin=settleCoin,
        openOnly=0,
        limit=20,
    )
    if isinstance(res, dict):
        return res.get("result", {}).get("list", [])
    return []


def get_closed_pnl():
    res = bybitClient.get_closed_pnl(category="linear", limit=10)
    if isinstance(res, dict):
        return res.get("result", {}).get("list", [])
    return []


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


from clients import bybitClient


def close_all_positions(settleCoin="USDT"):
    """
    Close all open positions for the given settleCoin (e.g., USDT) in linear contracts.
    Uses reduce-only market orders to safely close positions.
    """
    # ۱. گرفتن تمام پوزیشن‌های باز
    res = bybitClient.get_positions(category="linear", settleCoin=settleCoin)
    positions_list = res.get("result", {}).get("list", [])

    if not positions_list:
        print("No open positions to close.")
        return []

    closed_positions = []

    for pos in positions_list:
        symbol = pos.get("symbol")
        side = pos.get("side")
        size = float(pos.get("size", 0))

        if size == 0:
            continue  # پوزیشن صفر را نادیده می‌گیریم

        # تعیین جهت مخالف برای بستن پوزیشن
        close_side = "Sell" if side == "Buy" else "Buy"

        try:
            # ثبت سفارش مارکت reduce-only برای بستن پوزیشن
            order = bybitClient.place_order(
                category="linear",
                symbol=symbol,
                side=close_side,
                orderType="Market",
                qty=str(size),
                reduceOnly=True,  # مهم: تضمین بستن پوزیشن
            )

            closed_positions.append(
                {"symbol": symbol, "side": side, "size": size, "orderResult": order}
            )

            print(f"Closed position {symbol} | {side} | size: {size}")

        except Exception as e:
            print(f"❌ Failed to close position {symbol}: {e}")
            closed_positions.append(
                {"symbol": symbol, "side": side, "size": size, "error": str(e)}
            )

    return closed_positions


def cancel_all_orders(settleCoin="USDT"):
    return bybitClient.cancel_all_orders(category="linear", settleCoin=settleCoin)
