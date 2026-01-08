from pybit.exceptions import InvalidRequestError
from clients import bybitClient
from logger import log_print


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
        log_print("[INFO] No open positions to close.")
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
            log_print(f"[SUCCESS] Closed position {symbol} | {side} | size: {size}")
        except Exception as e:
            log_print(f"[ERROR] Failed to close position {symbol}: {e}")
            closed_positions.append(
                {"symbol": symbol, "side": side, "size": size, "error": str(e)}
            )

    return closed_positions


def close_position_by_symbol(symbol: str):
    """
    Close all open positions for a specific symbol.
    Uses reduce-only market orders to safely close positions.
    
    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")
    
    Returns:
        List of closed positions with their details
    """
    positions_list = get_positions(symbol=symbol)
    
    if not positions_list:
        log_print(f"[INFO] No open positions for {symbol} to close.")
        return []
    
    closed_positions = []
    
    for pos in positions_list:
        pos_symbol = pos.get("symbol")
        side = pos.get("side")
        size = float(pos.get("size", 0))
        
        if size == 0:
            continue  # Ignore empty positions
        
        # Determine opposite side to close position
        close_side = "Sell" if side == "Buy" else "Buy"
        
        try:
            order = bybitClient.place_order(
                category="linear",
                symbol=pos_symbol,
                side=close_side,
                orderType="Market",
                qty=str(size),
                reduceOnly=True,
            )
            closed_positions.append(
                {"symbol": pos_symbol, "side": side, "size": size, "orderResult": order}
            )
            log_print(f"[SUCCESS] Closed position {pos_symbol} | {side} | size: {size}")
        except Exception as e:
            log_print(f"[ERROR] Failed to close position {pos_symbol}: {e}")
            closed_positions.append(
                {"symbol": pos_symbol, "side": side, "size": size, "error": str(e)}
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


def get_transaction_log(
    limit: int = 50,
    startTime: int | None = None,
    endTime: int | None = None,
    currency: str | None = None,
    baseCoin: str | None = None,
    type: str | None = None,
    cursor: str | None = None,
):
    """
    Retrieve transaction log for linear category.

    :param limit: Limit for data size per page. [1, 50]. Default: 20
    :param startTime: The start timestamp (ms)
    :param endTime: The end timestamp (ms)
        - startTime and endTime are not passed, return 24 hours by default
        - Only startTime is passed, return range between startTime and startTime+24 hours
        - Only endTime is passed, return range between endTime-24 hours and endTime
        - If both are passed, the rule is endTime - startTime <= 7 days
    :param currency: Currency, uppercase only
    :param baseCoin: BaseCoin, uppercase only. e.g., BTC of BTCPERP
    :param type: Types of transaction logs
    :param cursor: Cursor. Use the nextPageCursor token from the response to retrieve the next page
    """
    params = {
        "accountType": "UNIFIED",
        "category": "linear",
        "limit": limit,
    }

    if startTime is not None:
        params["startTime"] = startTime
    if endTime is not None:
        params["endTime"] = endTime
    if currency is not None:
        params["currency"] = currency
    if baseCoin is not None:
        params["baseCoin"] = baseCoin
    if type is not None:
        params["type"] = type
    if cursor is not None:
        params["cursor"] = cursor

    return bybitClient.get_transaction_log(**params)


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
    symbol: str,
    side: str,
    qty: float,
    sl: float | None = None,
    tp: float | None = None,
    slTriggerBy: str = "MarkPrice",
    tpTriggerBy: str = "MarkPrice",
):
    """
    Place a market order with optional SL/TP.
    Compatible with legacy code.

    By default, SL/TP triggers are based on MarkPrice to avoid
    micro-spikes in LastPrice causing unexpected triggers.
    """

    payload = {
        "category": "linear",
        "symbol": symbol,
        "side": side,
        "orderType": "Market",
        "qty": str(qty),
        "stopLoss": str(sl) if sl else None,
        "takeProfit": str(tp) if tp else None,
    }

    # Explicitly set trigger types to MarkPrice (can be overridden via args)
    if sl is not None and slTriggerBy:
        payload["slTriggerBy"] = slTriggerBy
    if tp is not None and tpTriggerBy:
        payload["tpTriggerBy"] = tpTriggerBy

    # Remove None values before sending
    payload = {k: v for k, v in payload.items() if v is not None}

    return bybitClient.place_order(**payload)


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
    tpTriggerBy: str | None = "MarkPrice",
    slTriggerBy: str | None = "MarkPrice",
    triggerBy: str | None = None,
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
    :param tpTriggerBy: Price type to trigger TP ('MarkPrice', 'LastPrice', etc.)
    :param slTriggerBy: Price type to trigger SL ('MarkPrice', 'LastPrice', etc.)
    :param triggerBy: Price type to trigger both TP/SL if supported
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
        # Trigger types (default MarkPrice, can be overridden or disabled with None)
        "tpTriggerBy": tpTriggerBy,
        "slTriggerBy": slTriggerBy,
        "triggerBy": triggerBy,
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

    # Build payload according to Bybit API documentation
    # All numeric values must be strings
    # Only include parameters that are not None
    payload = {
        "category": "linear",  # Required: Product type
        "symbol": symbol,  # Required: Symbol name
    }

    # Either orderId or orderLinkId is required
    if orderId:
        payload["orderId"] = orderId
    elif orderLinkId:
        payload["orderLinkId"] = orderLinkId

    # Optional parameters - only add if not None
    if qty is not None:
        payload["qty"] = str(qty)
    if price is not None:
        payload["price"] = str(price)
    if triggerPrice is not None:
        payload["triggerPrice"] = str(triggerPrice)
    if takeProfit is not None:
        # Pass "0" to cancel existing TP, otherwise pass the price as string
        payload["takeProfit"] = "0" if takeProfit == 0 else str(takeProfit)
    if stopLoss is not None:
        # Pass "0" to cancel existing SL, otherwise pass the price as string
        payload["stopLoss"] = "0" if stopLoss == 0 else str(stopLoss)
    if tpTriggerBy is not None:
        payload["tpTriggerBy"] = tpTriggerBy
    if slTriggerBy is not None:
        payload["slTriggerBy"] = slTriggerBy
    if triggerBy is not None:
        payload["triggerBy"] = triggerBy
    if tpslMode is not None:
        payload["tpslMode"] = tpslMode
    if tpLimitPrice is not None:
        payload["tpLimitPrice"] = str(tpLimitPrice)
    if slLimitPrice is not None:
        payload["slLimitPrice"] = str(slLimitPrice)
    if orderIv is not None:
        payload["orderIv"] = str(orderIv)

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
                        log_print(
                            f"[INFO] Found SL order ID for {symbol}: {order_id} (attempt {attempt + 1})"
                        )
                        return order_id

            # If not found and not last attempt, wait and retry
            if attempt < retry_count - 1:
                wait_time = (attempt + 1) * 0.5  # 0.5s, 1s, 1.5s
                print(
                    f"[INFO] SL order not found for {symbol}, retrying in {wait_time}s (attempt {attempt + 1}/{retry_count})"
                )
                time.sleep(wait_time)
            else:
                log_print(
                    f"[WARN] SL order not found for {symbol} after {retry_count} attempts"
                )

        except Exception as e:
            log_print(
                f"[WARN] Failed to get SL order ID for {symbol} (attempt {attempt + 1}): {e}"
            )
            if attempt < retry_count - 1:
                time.sleep((attempt + 1) * 0.5)

    return None
