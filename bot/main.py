import asyncio
from telegram_client import client, process_telegram_queue, register_telegram_handlers
from config import main_loop, IS_DEMO, SELECTED_API_KEY, SELECTED_API_SECRET
from pybit.unified_trading import WebSocket
from errors import send_error_to_telegram
from config import open_positions

async def main():
    await client.start()
    print("[INFO] Telegram client started")
    register_telegram_handlers(source_channel=IS_DEMO)

    # start processing queue
    asyncio.create_task(process_telegram_queue())

    # start Bybit websocket
    ws = WebSocket(
        demo=IS_DEMO,
        api_key=SELECTED_API_KEY,
        api_secret=SELECTED_API_SECRET,
        channel_type="private",
    )
    ws.order_stream(lambda msg: asyncio.run_coroutine_threadsafe(..., main_loop))

    def handle_global_exception(loop, context):
        error = context.get("exception")
        if error:
            asyncio.create_task(send_error_to_telegram(error, context="GLOBAL"))

    loop = asyncio.get_event_loop()
    loop.set_exception_handler(handle_global_exception)

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
