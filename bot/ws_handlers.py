import asyncio
import json
import os
from datetime import datetime
from threading import Lock
from errors import send_error_to_telegram

# Lock for thread-safe file operations
_ws_file_lock = Lock()
WS_DATA_FILE = "ws_data.json"


def save_ws_message_to_json(msg_data: dict):
    """
    ذخیره پیام WebSocket در فایل JSON.
    هر پیام جدید به آرایه messages اضافه می‌شود.
    """
    try:
        with _ws_file_lock:
            # خواندن داده‌های موجود
            if os.path.exists(WS_DATA_FILE):
                try:
                    with open(WS_DATA_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except (json.JSONDecodeError, IOError):
                    # اگر فایل خراب است یا خطا دارد، از اول شروع می‌کنیم
                    data = {"messages": []}
            else:
                data = {"messages": []}

            # اضافه کردن timestamp به پیام
            message_with_timestamp = {
                "timestamp": datetime.now().isoformat(),
                "data": msg_data,
            }

            # اضافه کردن پیام جدید به آرایه
            data["messages"].append(message_with_timestamp)

            # ذخیره فایل
            with open(WS_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    except Exception as e:
        # در صورت خطا، فقط لاگ می‌کنیم تا callback اصلی متوقف نشود
        print(f"[WS][ERROR] Failed to save WS message to JSON: {e}")


def order_callback_ws(loop, telegram_queue):
    """
    Thread-safe WS callback with loop and telegram_queue injection.
    Determines type of WS message: New Order, Cancel Order, Close Position.
    """

    def _callback(msg):
        try:
            # ذخیره کل پیام WebSocket در فایل JSON
            save_ws_message_to_json(msg)

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
