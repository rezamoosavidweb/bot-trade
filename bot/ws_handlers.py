import asyncio
from config import main_loop, TARGET_CHANNEL
from errors import send_error_to_telegram

def order_callback_ws(telegram_queue):
    """
    Factory function that returns a WS callback
    with access to telegram_queue.
    """

    def _callback(msg):
        try:
            data = msg["data"][0]

            symbol_ws = data.get("symbol")
            size = float(data.get("size", 0))
            closed_pnl = float(data.get("closedPnl", 0))
            takeProfit = float(data.get("takeProfit") or 0)
            stopLoss = float(data.get("stopLoss") or 0)

            print(
                f"✅ WS message: symbol:{symbol_ws} "
                f"size:{size} closed_pnl:{closed_pnl}"
            )

            # detect closed position
            is_closed = (
                data.get("reduceOnly") in [True, "True"]
                and data.get("closeOnTrigger") in [True, "True"]
            ) or closed_pnl != 0

            asyncio.run_coroutine_threadsafe(
                telegram_queue.put(
                    {
                        "symbol": symbol_ws,
                        "size": size,
                        "closed_pnl": closed_pnl,
                        "takeProfit": takeProfit,
                        "stopLoss": stopLoss,
                        "data": data,
                        "is_closed": is_closed,
                    }
                ),
                main_loop,
            )

        except Exception as e:
            asyncio.run_coroutine_threadsafe(
                send_error_to_telegram(
                    client=None,  # اگر خواستی بعداً تزریق می‌کنیم
                    target_channel=TARGET_CHANNEL,
                    error=e,
                    context="WS order callback",
                ),
                main_loop,
            )

    return _callback
