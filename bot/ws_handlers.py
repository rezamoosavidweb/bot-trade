import asyncio
import json
import os
import traceback
from datetime import datetime
from threading import Lock
from errors import send_error_to_telegram
from logger import log_print


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
        log_print(f"[WS][DEBUG] Attempting to save WS message to {WS_DATA_FILE}")

        with _ws_file_lock:
            # Read existing data
            if os.path.exists(WS_DATA_FILE):
                try:
                    with open(WS_DATA_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    log_print(
                        f"[WS][DEBUG] Loaded existing file with {len(data.get('messages', []))} messages"
                    )
                except (json.JSONDecodeError, IOError) as e:
                    # If file is corrupted or has errors, start fresh
                    log_print(
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

            log_print(f"[WS][SUCCESS] Saved WS message to {WS_DATA_FILE}")

    except Exception as e:
        # On error, print full traceback
        error_trace = traceback.format_exc()
        log_print(f"[WS][ERROR] Failed to save WS message to JSON: {e}")
        log_print(f"[WS][ERROR] Traceback: {error_trace}")


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

            # Extract the actual message data
            # WebSocket message from Bybit has structure: { "topic": "...", "data": [...], "id": "...", "creationTime": ... }
            # When saved to JSON, it's wrapped: { "timestamp": "...", "data": { "topic": "...", "data": [...] } }
            # So we need to handle both cases
            if "data" in msg and isinstance(msg.get("data"), list):
                # Direct WebSocket message format from Bybit
                orders = msg.get("data", [])
                raw_message = msg
            elif "data" in msg and isinstance(msg.get("data"), dict):
                # JSON file format (wrapped with timestamp)
                message_data = msg.get("data", {})
                orders = message_data.get("data", [])
                raw_message = message_data  # Use the inner data dict as raw_message
            else:
                log_print(f"[WS][WARN] Invalid message format: {type(msg.get('data'))}")
                return

            if not orders:
                print("[WS][WARN] No orders in message")
                return

            log_print(
                f"[WS][INFO] Processing {len(orders)} order(s) in WebSocket message"
            )

            # Send entire message with all orders data to queue
            # This will be processed as a single message in handle_ws_message
            asyncio.run_coroutine_threadsafe(
                telegram_queue.put(
                    {
                        "type": "ws",
                        "msg_type": "ws_message",  # Generic type for full message
                        "raw_message": raw_message,  # Full WebSocket message
                        "orders": orders,  # All orders in the message
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
