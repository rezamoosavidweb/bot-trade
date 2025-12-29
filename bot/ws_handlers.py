import asyncio
import json
import os
import traceback
from datetime import datetime
from threading import Lock
from errors import send_error_to_telegram

# Lock for thread-safe file operations
_ws_file_lock = Lock()
# مسیر فایل در root directory پروژه
WS_DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ws_data.json")


def save_ws_message_to_json(msg_data: dict):
    """
    ذخیره پیام WebSocket در فایل JSON.
    هر پیام جدید به آرایه messages اضافه می‌شود.
    """
    try:
        print(f"[WS][DEBUG] Attempting to save WS message to {WS_DATA_FILE}")

        with _ws_file_lock:
            # خواندن داده‌های موجود
            if os.path.exists(WS_DATA_FILE):
                try:
                    with open(WS_DATA_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    print(
                        f"[WS][DEBUG] Loaded existing file with {len(data.get('messages', []))} messages"
                    )
                except (json.JSONDecodeError, IOError) as e:
                    # اگر فایل خراب است یا خطا دارد، از اول شروع می‌کنیم
                    print(
                        f"[WS][WARN] Error reading existing file, starting fresh: {e}"
                    )
                    data = {"messages": []}
            else:
                print(f"[WS][DEBUG] File does not exist, creating new file")
                data = {"messages": []}

            # اضافه کردن timestamp به پیام
            message_with_timestamp = {
                "timestamp": datetime.now().isoformat(),
                "data": msg_data,
            }

            # اضافه کردن پیام جدید به آرایه
            data["messages"].append(message_with_timestamp)
            print(f"[WS][DEBUG] Added message, total messages: {len(data['messages'])}")

            # ذخیره فایل
            with open(WS_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            print(f"[WS][SUCCESS] Saved WS message to {WS_DATA_FILE}")

    except Exception as e:
        # در صورت خطا، traceback کامل را چاپ می‌کنیم
        error_trace = traceback.format_exc()
        print(f"[WS][ERROR] Failed to save WS message to JSON: {e}")
        print(f"[WS][ERROR] Traceback: {error_trace}")


def order_callback_ws(loop, telegram_queue):
    """
    Thread-safe WS callback with loop and telegram_queue injection.
    Determines type of WS message: New Order, Cancel Order, Close Position.
    """

    def _callback(msg):
        try:
            print(f"[WS][DEBUG] Callback received message: {type(msg)}")

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
