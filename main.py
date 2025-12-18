import asyncio

# Import فایل‌ها به عنوان ماژول
import signal_trade
import info_tel

async def main():
    # اجرای همزمان هر دو main
    await asyncio.gather(
        signal_trade.main(),
        info_tel.main()
    )

if __name__ == "__main__":
    asyncio.run(main())
