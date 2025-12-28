import asyncio
from errors import send_error_to_telegram


def order_callback_ws(loop, telegram_queue):
    """
    Thread-safe WS callback with loop and telegram_queue injection.
    Determines type of WS message: New Order, Cancel Order, Close Position.
    """

    def _callback(msg):
        try:
            data = msg["data"][0]
            

            # مقادیر اصلی
            symbol_ws = data.get("symbol")
            size = float(data.get("qty", 0))
            closed_pnl = float(data.get("closedPnl", 0))
            takeProfit = float(data.get("takeProfit") or 0)
            stopLoss = float(data.get("stopLoss") or 0)
            reduceOnly = data.get("reduceOnly") in [True, "True"]
            closeOnTrigger = data.get("closeOnTrigger") in [True, "True"]
            createType = data.get("createType", "")
            orderStatus = data.get("orderStatus", "")

            # تعیین نوع پیام
            if orderStatus == "Deactivated" and reduceOnly and closeOnTrigger:
                msg_type = "cancel_order"
            elif reduceOnly and orderStatus == "Filled" and not closeOnTrigger:
                msg_type = "close_position"
            elif not reduceOnly and orderStatus == "Filled":
                msg_type = "new_order"
            else:
                msg_type = "other"

            # ارسال به صف تلگرام
            asyncio.run_coroutine_threadsafe(
                telegram_queue.put(
                    {
                        "type": "ws",
                        "msg_type": msg_type,
                        "symbol": symbol_ws,
                        "size": size,
                        "closed_pnl": closed_pnl,
                        "takeProfit": takeProfit,
                        "stopLoss": stopLoss,
                        "data": data,
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
