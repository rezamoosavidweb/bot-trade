import asyncio
from clients import telClient
from telegram_client import (
    process_telegram_queue,
    register_telegram_handlers,
)
from ws_handlers import (
    order_callback_ws,
)
from config import (
    main_loop,
    IS_DEMO,
    SELECTED_API_KEY,
    SELECTED_API_SECRET,
    SELECTED_SOURCE_CHANNEL,
)
from pybit.unified_trading import WebSocket
from errors import send_error_to_telegram
from cache import periodic_refresh, init_redis


async def main():
    # Initialization Redis and Start periodic refresh (every 1 hour)
    await init_redis()
    asyncio.create_task(periodic_refresh(interval_seconds=3600))

    # Start Telegram Client
    await telClient.start()
    print("[INFO] Telegram client started")

    # Register Telegram message handler
    register_telegram_handlers(source_channel=SELECTED_SOURCE_CHANNEL)

    # Start Telegram processing queue
    asyncio.create_task(process_telegram_queue())

    # Handle global exceptions
    def handle_global_exception(loop, context):
        error = context.get("exception")
        if error:
            asyncio.create_task(send_error_to_telegram(error, context="GLOBAL"))

    loop = asyncio.get_event_loop()
    loop.set_exception_handler(handle_global_exception)

    # Start Bybit WebSocket
    ws = WebSocket(
        api_key=SELECTED_API_KEY,
        api_secret=SELECTED_API_SECRET,
        demo=IS_DEMO,
        testnet=False,
        channel_type="private",
    )
    ws.order_stream(
        lambda msg: asyncio.run_coroutine_threadsafe(order_callback_ws(msg), main_loop)
    )

    # Run until Telegram client disconnected
    await telClient.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
