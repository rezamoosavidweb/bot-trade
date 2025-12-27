from pybit.exceptions import InvalidRequestError
from clients import bybitClient


# ---------------- WALLET & ACCOUNT ---------------- #
def get_wallet_balance():
    """Retrieve wallet balance for unified account."""
    return bybitClient.get_wallet_balance(accountType="UNIFIED")


def get_account_info():
    """Retrieve account information."""
    return bybitClient.get_account_info()


# ---------------- INSTRUMENTS ---------------- #
def get_all_linear_instruments(limit: int = 200):
    """Retrieve all linear instruments (futures) from Bybit with pagination support."""
    cursor = None
    instruments = []

    while True:
        res = bybitClient.get_instruments_info(
            category="linear", limit=limit, cursor=cursor
        )
        instruments.extend(res["result"]["list"])
        cursor = res["result"].get("nextPageCursor")
        if not cursor:
            break

    return instruments


def get_single_instrument(symbol: str):
    """Retrieve a single instrument by symbol."""
    res = bybitClient.get_instruments_info(category="linear", symbol=symbol, limit=1)
    return res["result"]["list"][0]


# ---------------- POSITIONS ---------------- #
def get_positions(symbol: str | None = None, settleCoin: str | None = None):
    """
    Retrieve open positions filtered by symbol or settleCoin.
    At least one parameter must be provided.
    """
    if not symbol and not settleCoin:
        raise ValueError("Either symbol or settleCoin must be provided")

    params = {"category": "linear"}
    if symbol:
        params["symbol"] = symbol
    if settleCoin:
        params["settleCoin"] = settleCoin

    res = bybitClient.get_positions(**params)
    return res.get("result", {}).get("list", [])


def close_all_positions(settleCoin="USDT"):
    """
    Close all open positions for the given settleCoin in linear contracts.
    Uses reduce-only market orders to safely close positions.
    """
    res = bybitClient.get_positions(category="linear", settleCoin=settleCoin)
    positions_list = res.get("result", {}).get("list", [])

    if not positions_list:
        print("[INFO] No open positions to close.")
        return []

    closed_positions = []

    for pos in positions_list:
        symbol = pos.get("symbol")
        side = pos.get("side")
        size = float(pos.get("size", 0))

        if size == 0:
            continue  # Ignore empty positions

        # Determine opposite side to close position
        close_side = "Sell" if side == "Buy" else "Buy"

        try:
            order = bybitClient.place_order(
                category="linear",
                symbol=symbol,
                side=close_side,
                orderType="Market",
                qty=str(size),
                reduceOnly=True,
            )
            closed_positions.append(
                {"symbol": symbol, "side": side, "size": size, "orderResult": order}
            )
            print(f"[SUCCESS] Closed position {symbol} | {side} | size: {size}")
        except Exception as e:
            print(f"[ERROR] Failed to close position {symbol}: {e}")
            closed_positions.append(
                {"symbol": symbol, "side": side, "size": size, "error": str(e)}
            )

    return closed_positions


# ---------------- ORDERS ---------------- #
def get_pending_orders(settleCoin: str):
    """Retrieve all pending/open orders for a given settleCoin."""
    res = bybitClient.get_open_orders(
        category="linear", settleCoin=settleCoin, openOnly=0, limit=20
    )
    if isinstance(res, dict):
        return res.get("result", {}).get("list", [])
    return []


def get_closed_pnl(limit: int = 10):
    """Retrieve closed PnL for the account."""
    res = bybitClient.get_closed_pnl(category="linear", limit=limit)
    if isinstance(res, dict):
        return res.get("result", {}).get("list", [])
    return []


def get_transaction_log(limit: int = 50):
    """Retrieve transaction log for linear category."""
    return bybitClient.get_transaction_log(
        accountType="UNIFIED", category="linear", limit=limit
    )


def cancel_all_orders(settleCoin="USDT"):
    """Cancel all open orders for a given settleCoin in linear contracts."""
    return bybitClient.cancel_all_orders(category="linear", settleCoin=settleCoin)


# ---------------- LEVERAGE & ORDER PLACEMENT ---------------- #
def set_leverage_safe(symbol: str, leverage: float):
    """
    Safely set leverage for a symbol.
    If leverage is already set to desired value, returns False.
    """
    try:
        bybitClient.set_leverage(
            category="linear",
            symbol=symbol,
            buyLeverage=str(leverage),
            sellLeverage=str(leverage),
        )
        return True
    except InvalidRequestError as e:
        # Error code 110043 = leverage not modified
        if "110043" in str(e):
            return False
        raise


def place_market_order(
    symbol: str, side: str, qty: float, sl: float | None = None, tp: float | None = None
):
    """
    Place a market order with optional SL/TP.
    Compatible with legacy code.
    """
    return bybitClient.place_order(
        category="linear",
        symbol=symbol,
        side=side,
        orderType="Market",
        qty=str(qty),
        stopLoss=str(sl) if sl else None,
        takeProfit=str(tp) if tp else None,
    )


# ---------------- TRADING STOP (SL/TP) ---------------- #
def set_trading_stop(
    symbol: str,
    positionIdx: int,
    tpslMode: str,
    takeProfit: float | None = None,
    stopLoss: float | None = None,
    tpSize: float | None = None,
    slSize: float | None = None,
    tpOrderType: str = "Market",
    slOrderType: str = "Market",
    tpTriggerBy: str = "LastPrice",
    slTriggerBy: str = "LastPrice",
):
    """
    Set Take Profit / Stop Loss / Trailing Stop for a position.
    Supports both Full and Partial modes according to Bybit v5 API.

    :param symbol: Trading symbol (e.g., BTCUSDT)
    :param positionIdx: 0 = one-way, 1 = hedge Buy, 2 = hedge Sell
    :param tpslMode: 'Full' for full position, 'Partial' for partial
    :param takeProfit: TP price
    :param stopLoss: SL price
    :param tpSize: Quantity for partial TP
    :param slSize: Quantity for partial SL
    :param tpOrderType: 'Market' or 'Limit' for TP
    :param slOrderType: 'Market' or 'Limit' for SL
    :param tpTriggerBy: TP trigger price type
    :param slTriggerBy: SL trigger price type
    """

    payload = {
        "category": "linear",  # required by API
        "symbol": symbol,
        "positionIdx": positionIdx,
        "tpslMode": tpslMode,
        "takeProfit": str(takeProfit) if takeProfit is not None else None,
        "stopLoss": str(stopLoss) if stopLoss is not None else None,
        "tpSize": str(tpSize) if tpSize is not None else None,
        "slSize": str(slSize) if slSize is not None else None,
        "tpOrderType": tpOrderType,
        "slOrderType": slOrderType,
        "tpTriggerBy": tpTriggerBy,
        "slTriggerBy": slTriggerBy,
    }

    # حذف مقادیر None تا API خطا ندهد
    payload = {k: v for k, v in payload.items() if v is not None}

    # فراخوانی دقیق API با دیکشنری
    return bybitClient.v5.position.trading_stop(**payload)
