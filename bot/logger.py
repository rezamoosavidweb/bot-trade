"""
Logging utility with timestamp support and JSON file storage.
"""

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from threading import Lock

# Lock for thread-safe file operations
_log_file_lock = Lock()
# File path in project root directory
LOGS_DATA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "logs_data.json"
)


def get_timestamp() -> str:
    """Get current timestamp in Asia/Tehran timezone."""
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    return now.strftime("%Y-%m-%d %H:%M:%S")


def save_log_to_json(level: str, message: str, context: str = ""):
    """
    Save log message to JSON file.
    Each log entry is added to the logs array.
    """
    try:
        with _log_file_lock:
            # Read existing data
            if os.path.exists(LOGS_DATA_FILE):
                try:
                    with open(LOGS_DATA_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except (json.JSONDecodeError, IOError):
                    data = {"logs": []}
            else:
                data = {"logs": []}

            # Add timestamp to log entry
            log_entry = {
                "timestamp": datetime.now(ZoneInfo("Asia/Tehran")).isoformat(),
                "level": level,
                "message": message,
                "context": context,
            }

            # Add new log entry to array
            data["logs"].append(log_entry)

            # Keep only last 10000 logs to prevent file from growing too large
            if len(data["logs"]) > 10000:
                data["logs"] = data["logs"][-10000:]

            # Save file
            with open(LOGS_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    except Exception as e:
        # Don't fail if logging fails, just print error
        print(f"[LOGGER][ERROR] Failed to save log to JSON: {e}")


def log_print(*args, **kwargs):
    """
    Print with timestamp prefix and save to JSON file.
    Usage: log_print("message") instead of print("message")
    """
    timestamp = get_timestamp()
    # Get the message from args
    if args:
        # Add timestamp to the first argument
        message = f"[{timestamp}] {args[0]}"
        new_args = (message,) + args[1:]
        print(*new_args, **kwargs)

        # Determine log level from message
        msg_str = str(args[0]).upper()
        if "[ERROR]" in msg_str or "[FATAL]" in msg_str:
            level = "ERROR"
        elif "[WARN]" in msg_str:
            level = "WARN"
        elif "[INFO]" in msg_str or "[SUCCESS]" in msg_str:
            level = "INFO"
        elif "[DEBUG]" in msg_str:
            level = "DEBUG"
        else:
            level = "INFO"

        # Save to JSON
        save_log_to_json(level, str(args[0]), context="")
    else:
        print(f"[{timestamp}]", **kwargs)
        save_log_to_json("INFO", "", context="")
