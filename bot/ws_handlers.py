# ws_handlers.py
import asyncio
from errors import send_error_to_telegram


def order_callback_ws(loop, telegram_queue):
    """
    Thread-safe callback for Bybit WebSocket order updates.
    Sends detailed order info to the telegram_queue.
    """

    def _callback(msg):
        try:
            data = msg["data"][0]
            print(f"data :\n{data}\n\n")
            symbol_ws = data.get("symbol")
            size = float(data.get("size", 0))
            closed_pnl = float(data.get("closedPnl", 0))
            takeProfit = float(data.get("takeProfit") or 0)
            stopLoss = float(data.get("stopLoss") or 0)

            # is_closed according to your formula
            is_closed = (
                data.get("reduceOnly") in [True, "True"]
                and data.get("closeOnTrigger") in [True, "True"]
            ) or closed_pnl != 0

            # Put all relevant info in the queue
            asyncio.run_coroutine_threadsafe(
                telegram_queue.put(
                    {
                        "type": "ws",
                        "symbol": symbol_ws,
                        "size": size,
                        "closed_pnl": closed_pnl,
                        "takeProfit": takeProfit,
                        "stopLoss": stopLoss,
                        "is_closed": is_closed,
                        "data": {
                            "category": data.get("category"),
                            "orderId": data.get("orderId"),
                            "orderLinkId": data.get("orderLinkId"),
                            "side": data.get("side"),
                            "positionIdx": data.get("positionIdx"),
                            "orderStatus": data.get("orderStatus"),
                            "createType": data.get("createType"),
                            "cancelType": data.get("cancelType"),
                            "rejectReason": data.get("rejectReason"),
                            "price": data.get("price"),
                            "avgPrice": data.get("avgPrice"),
                            "qty": data.get("qty"),
                            "leavesQty": data.get("leavesQty"),
                            "cumExecQty": data.get("cumExecQty"),
                            "cumExecValue": data.get("cumExecValue"),
                            "cumFeeDetail": data.get("cumFeeDetail"),
                            "orderType": data.get("orderType"),
                            "timeInForce": data.get("timeInForce"),
                            "lastPriceOnCreated": data.get("lastPriceOnCreated"),
                            "tpslMode": data.get("tpslMode"),
                            "tpLimitPrice": data.get("tpLimitPrice"),
                            "slLimitPrice": data.get("slLimitPrice"),
                            "tpTriggerBy": data.get("tpTriggerBy"),
                            "slTriggerBy": data.get("slTriggerBy"),
                            "triggerDirection": data.get("triggerDirection"),
                            "createdTime": data.get("createdTime"),
                            "updatedTime": data.get("updatedTime"),
                        },
                    }
                ),
                loop,
            )

        except Exception as e:
            asyncio.run_coroutine_threadsafe(
                send_error_to_telegram(
                    error=e,
                    context="WS order callback",
                ),
                loop,
            )

    return _callback
