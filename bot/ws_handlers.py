import asyncio
import json
import os
import traceback
from datetime import datetime
from threading import Lock
from errors import send_error_to_telegram

# Lock for thread-safe file operations
_ws_file_lock = Lock()
# File path in project root directory
WS_DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ws_data.json")


def save_ws_message_to_json(msg_data: dict):
    """
    Save WebSocket message to JSON file.
    Each new message is added to the messages array.
    """
    try:
        print(f"[WS][DEBUG] Attempting to save WS message to {WS_DATA_FILE}")

        with _ws_file_lock:
            # Read existing data
            if os.path.exists(WS_DATA_FILE):
                try:
                    with open(WS_DATA_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    print(
                        f"[WS][DEBUG] Loaded existing file with {len(data.get('messages', []))} messages"
                    )
                except (json.JSONDecodeError, IOError) as e:
                    # If file is corrupted or has errors, start fresh
                    print(
                        f"[WS][WARN] Error reading existing file, starting fresh: {e}"
                    )
                    data = {"messages": []}
            else:
                print(f"[WS][DEBUG] File does not exist, creating new file")
                data = {"messages": []}

            # Add timestamp to message
            message_with_timestamp = {
                "timestamp": datetime.now().isoformat(),
                "data": msg_data,
            }

            # Add new message to array
            data["messages"].append(message_with_timestamp)
            print(f"[WS][DEBUG] Added message, total messages: {len(data['messages'])}")

            # Save file
            with open(WS_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            print(f"[WS][SUCCESS] Saved WS message to {WS_DATA_FILE}")

    except Exception as e:
        # On error, print full traceback
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

            # Save entire WebSocket message to JSON file
            save_ws_message_to_json(msg)

            # Process all orders in message (not just first order)
            orders = msg.get("data", [])
            if not orders:
                print("[WS][WARN] No orders in message")
                return

            # Process each order separately
            for data in orders:
                # Main values
                symbol_ws = data.get("symbol")
                size = float(data.get("qty", 0))
                closed_pnl = float(data.get("closedPnl", 0))
                takeProfit = float(data.get("takeProfit") or 0)
                stopLoss = float(data.get("stopLoss") or 0)
                reduceOnly = data.get("reduceOnly") in [True, "True"]
                closeOnTrigger = data.get("closeOnTrigger") in [True, "True"]
                createType = data.get("createType", "")
                orderStatus = data.get("orderStatus", "")
                stopOrderType = data.get("stopOrderType", "")

                # Determine message type with more precision
                if orderStatus in ["Cancelled", "Deactivated"]:
                    msg_type = "cancel_order"
                elif orderStatus == "Filled":
                    # If reduceOnly, position is closed (whether closeOnTrigger or not)
                    if reduceOnly:
                        if stopOrderType in [
                            "TakeProfit",
                            "StopLoss",
                            "PartialTakeProfit",
                            "PartialStopLoss",
                        ]:
                            # SL/TP triggered
                            msg_type = "sl_tp_triggered"
                        else:
                            # Position closed by market order
                            msg_type = "close_position"
                    elif stopOrderType in [
                        "TakeProfit",
                        "StopLoss",
                        "PartialTakeProfit",
                        "PartialStopLoss",
                    ]:
                        # SL/TP triggered (rare case)
                        msg_type = "sl_tp_triggered"
                    else:
                        # New order filled
                        msg_type = "new_order"
                elif orderStatus == "Untriggered" and stopOrderType:
                    # SL/TP created but not triggered yet
                    msg_type = "sl_tp_created"
                elif orderStatus == "Rejected":
                    msg_type = "rejected"
                else:
                    msg_type = "other"

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
