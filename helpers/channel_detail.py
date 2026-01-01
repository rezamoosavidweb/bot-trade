from telethon import TelegramClient
from dotenv import load_dotenv
import os


load_dotenv()
# -------- API KEYS --------
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
client = TelegramClient("session", TELEGRAM_API_ID, TELEGRAM_API_HASH)


async def main():
    channel = await client.get_entity("https://t.me/MyTestTrade")
    print(channel.id)


client.start()
client.loop.run_until_complete(main())
