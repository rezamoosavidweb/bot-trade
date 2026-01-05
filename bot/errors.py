import traceback
from datetime import datetime
from clients import telClient
from config import TARGET_CHANNEL
from logger import log_print


async def send_error_to_telegram(error: Exception, context: str = ""):
    """Send formatted error message to Telegram."""
    try:
        tb = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
        msg = (
            "🚨 **BOT ERROR**\n\n"
            f"🕒 Time: {datetime.datetime.utcnow()} UTC\n"
            f"📍 Context: {context}\n\n"
            f"❌ Type: {type(error).__name__}\n"
            f"📝 Message: {str(error)}\n\n"
            f"📌 Traceback:\n"
            f"```{tb[-3500:]}```"
        )
        await telClient.send_message(TARGET_CHANNEL, msg)
    except Exception as e:
        log_print("[FATAL] Failed to send error to Telegram:", e)
