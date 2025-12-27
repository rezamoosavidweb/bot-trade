# ws_handlers.py
import asyncio
from errors import send_error_to_telegram
from config import TARGET_CHANNEL


def order_callback_ws(loop, telegram_queue):
    def _callback(msg):
        try:
            data = msg["data"][0]
            print(f"data:{data}\n\n")
            symbol_ws = data.get("symbol")
            size = float(data.get("size", 0))
            closed_pnl = float(data.get("closedPnl", 0))
            takeProfit = float(data.get("takeProfit") or 0)
            stopLoss = float(data.get("stopLoss") or 0)

            is_closed = (
                data.get("reduceOnly") in (True, "True")
                and data.get("closeOnTrigger") in (True, "True")
            ) or closed_pnl != 0

            asyncio.run_coroutine_threadsafe(
                telegram_queue.put({
                    "type": "ws",             # مشخص کردن نوع پیام
                    "symbol": symbol_ws,
                    "size": size,
                    "closed_pnl": closed_pnl,
                    "takeProfit": takeProfit,
                    "stopLoss": stopLoss,
                    "data": data,
                    "is_closed": is_closed,
                }),
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
