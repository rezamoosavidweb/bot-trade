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
    tp: float | None = None,
    sl: float | None = None,
    tpSize: float | None = None,
    slSize: float | None = None,
    tpOrderType: str = "Market",
    slOrderType: str = "Market",
):
    """
    Set Take Profit / Stop Loss / Trailing Stop for a position.
    Supports both Full and Partial modes.

    :param symbol: Trading symbol (e.g., BTCUSDT)
    :param positionIdx: 0 = one-way, 1/2 = hedge-mode
    :param tpslMode: 'Full' for full position, 'Partial' for partial
    :param takeProfit: TP price
    :param stopLoss: SL price
    :param tpSize: Quantity for partial TP
    :param slSize: Quantity for partial SL
    :param tpOrderType: 'Market' or 'Limit' for TP
    :param slOrderType: 'Market' or 'Limit' for SL
    """

    payload = {
        "category": "linear",
        "symbol": symbol,
        "positionIdx": positionIdx,
        "tpslMode": tpslMode,
        "takeProfit": str(tp) if tp is not None else None,
        "stopLoss": str(sl) if sl is not None else None,
        "tpSize": str(tpSize) if tpSize is not None else None,
        "slSize": str(slSize) if slSize is not None else None,
        "tpOrderType": tpOrderType,
        "slOrderType": slOrderType,
    }

    payload = {k: v for k, v in payload.items() if v is not None}

    return bybitClient.set_trading_stop(**payload)


# ---------------- AMEND ORDER (UPDATE TP/SL) ---------------- #
def amend_order(
    symbol: str,
    orderId: str | None = None,
    orderLinkId: str | None = None,
    qty: float | None = None,
    price: float | None = None,
    triggerPrice: float | None = None,
    takeProfit: float | None = None,
    stopLoss: float | None = None,
    tpTriggerBy: str | None = None,
    slTriggerBy: str | None = None,
    triggerBy: str | None = None,
    tpslMode: str | None = None,
    tpLimitPrice: float | None = None,
    slLimitPrice: float | None = None,
    orderIv: float | None = None,
):
    """
    Amend an existing order (including TP/SL conditional orders).
    Use this to update existing TP/SL orders instead of set_trading_stop.

    :param symbol: Trading symbol (e.g., BTCUSDT)
    :param orderId: Order ID (either orderId or orderLinkId required)
    :param orderLinkId: Order Link ID (either orderId or orderLinkId required)
    :param qty: Order quantity after modification
    :param price: Order price after modification
    :param triggerPrice: Trigger price after modification
    :param takeProfit: Take profit price after modification (pass "0" to cancel)
    :param stopLoss: Stop loss price after modification (pass "0" to cancel)
    :param tpTriggerBy: Price type to trigger take profit
    :param slTriggerBy: Price type to trigger stop loss
    :param tpslMode: TP/SL mode (Full or Partial)
    :param tpLimitPrice: Limit order price when TP is triggered
    :param slLimitPrice: Limit order price when SL is triggered
    """
    if not orderId and not orderLinkId:
        raise ValueError("Either orderId or orderLinkId must be provided")

    payload = {
        "category": "linear",
        "symbol": symbol,
        "orderId": orderId,
        "orderLinkId": orderLinkId,
        "qty": str(qty) if qty is not None else None,
        "price": str(price) if price is not None else None,
        "triggerPrice": str(triggerPrice) if triggerPrice is not None else None,
        "takeProfit": str(takeProfit) if takeProfit is not None else None,
        "stopLoss": str(stopLoss) if stopLoss is not None else None,
        "tpTriggerBy": tpTriggerBy,
        "slTriggerBy": slTriggerBy,
        "triggerBy": triggerBy,
        "tpslMode": tpslMode,
        "tpLimitPrice": str(tpLimitPrice) if tpLimitPrice is not None else None,
        "slLimitPrice": str(slLimitPrice) if slLimitPrice is not None else None,
        "orderIv": str(orderIv) if orderIv is not None else None,
    }

    payload = {k: v for k, v in payload.items() if v is not None}

    return bybitClient.amend_order(**payload)


def get_sl_order_id(symbol: str, positionIdx: int = 0, retry_count: int = 3):
    """
    Get the order ID of the existing SL order for a position.
    Returns orderId if found, None otherwise.
    Retries up to retry_count times with delay to handle timing issues.
    """
    import time
    
    for attempt in range(retry_count):
        try:
            res = bybitClient.get_open_orders(
                category="linear",
                symbol=symbol,
                openOnly=0,
                limit=50,
            )
            orders = res.get("result", {}).get("list", [])
            
            for order in orders:
                stop_order_type = order.get("stopOrderType", "")
                order_status = order.get("orderStatus", "")
                order_position_idx = order.get("positionIdx", 0)
                
                # Find untriggered SL order for this position
                # Accept both StopLoss (Full mode) and PartialStopLoss (Partial mode)
                if (
                    stop_order_type in ["StopLoss", "PartialStopLoss"]
                    and order_status == "Untriggered"
                    and order_position_idx == positionIdx
                ):
                    order_id = order.get("orderId")
                    if order_id:
                        print(f"[INFO] Found SL order ID for {symbol}: {order_id} (attempt {attempt + 1})")
                        return order_id
            
            # If not found and not last attempt, wait and retry
            if attempt < retry_count - 1:
                wait_time = (attempt + 1) * 0.5  # 0.5s, 1s, 1.5s
                print(f"[INFO] SL order not found for {symbol}, retrying in {wait_time}s (attempt {attempt + 1}/{retry_count})")
                time.sleep(wait_time)
            else:
                print(f"[WARN] SL order not found for {symbol} after {retry_count} attempts")
        
        except Exception as e:
            print(f"[WARN] Failed to get SL order ID for {symbol} (attempt {attempt + 1}): {e}")
            if attempt < retry_count - 1:
                time.sleep((attempt + 1) * 0.5)
    
    return None
