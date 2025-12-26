import asyncio
import json
from redis.asyncio import Redis

from api import (
    get_all_linear_instruments,
    get_transaction_log,
    get_single_instrument,
)

redis: Redis | None = None
REDIS_AVAILABLE = False


# ---------------- INIT REDIS ---------------- #
async def init_redis():
    global redis, REDIS_AVAILABLE
    try:
        redis = Redis(
            host="localhost",
            port=6379,
            db=0,
            decode_responses=True,
        )
        await redis.ping()
        REDIS_AVAILABLE = True
        print("[CACHE] Redis connected")
    except Exception as e:
        redis = None
        REDIS_AVAILABLE = False
        print(f"[CACHE][WARN] Redis disabled: {e}")


# ---------------- KEYS ---------------- #
SYMBOL_INFO_KEY = "bybit:symbol_info"
TRANSACTION_LOG_KEY = "bybit:transaction_log"


# ---------------- CACHE CORE ---------------- #
async def set_cache(key: str, value: dict, expire: int = 3600):
    await redis.set(key, json.dumps(value), ex=expire)


async def get_cache(key: str):
    data = await redis.get(key)
    return json.loads(data) if data else None


# ---------------- SYMBOL CACHE (ALL) ---------------- #
async def refresh_symbol_info():
    """
    Fetch ALL linear symbols from Bybit (with pagination handled internally)
    and cache them in Redis.
    """
    try:
        instruments = get_all_linear_instruments()

        symbols_data = {}
        for item in instruments:
            symbols_data[item["symbol"]] = {
                "min_qty": float(item["lotSizeFilter"]["minOrderQty"]),
                "max_order_qty": float(item["lotSizeFilter"]["maxOrderQty"]),
                "qty_step": float(item["lotSizeFilter"]["qtyStep"]),
                "min_notional": float(item["lotSizeFilter"]["minNotionalValue"]),
                "tick_size": float(item["priceFilter"]["tickSize"]),
                "max_leverage": float(item["leverageFilter"]["maxLeverage"]),
            }
        if REDIS_AVAILABLE:
            await set_cache(SYMBOL_INFO_KEY, symbols_data, expire=3600)
            print(f"[CACHE] {len(symbols_data)} symbols cached")
        else:
            print(f"[CACHE]][WARN] cached is disabled! for get_all_linear_instruments!")

    except Exception as e:
        print(f"[CACHE][ERROR] refresh_symbol_info failed: {e}")


# ---------------- TRANSACTION LOG CACHE ---------------- #
async def refresh_transaction_log(limit=50):
    try:
        res = get_transaction_log(limit=limit)
        if REDIS_AVAILABLE:
            await set_cache(
                TRANSACTION_LOG_KEY,
                res.get("result", {}),
                expire=3600,
            )
            print("[CACHE] Transaction log cached")
        else:
            print("[CACHE][WARN] cached is disabled!")
    except Exception as e:
        print(f"[CACHE][ERROR] refresh_transaction_log failed: {e}")


# ---------------- PERIODIC REFRESH ---------------- #
async def periodic_refresh(interval_seconds=3600 * 10):
    """
    - Warmup cache on startup
    - Refresh periodically
    """
    await refresh_symbol_info()
    await refresh_transaction_log()

    if REDIS_AVAILABLE:
        while True:
            await asyncio.sleep(interval_seconds)
            await refresh_symbol_info()
            await refresh_transaction_log()
    else:
        print("[CACHE][WARN] cached is disabled in periodic_refresh")


# ---------------- SYMBOL HELPER ---------------- #
async def get_symbol_info(symbol: str):
    """
    Read symbol info from Redis.
    Fallback to API only if Redis is empty or symbol missing.
    """
    if REDIS_AVAILABLE:
        symbols = await get_cache(SYMBOL_INFO_KEY)
        if symbols and symbol in symbols:
            return symbols[symbol]

    # ---- fallback (rare) ----
    print(f"[CACHE][MISS] {symbol}, fetching from API")
    item = get_single_instrument(symbol)

    info = {
        "min_qty": float(item["lotSizeFilter"]["minOrderQty"]),
        "max_order_qty": float(item["lotSizeFilter"]["maxOrderQty"]),
        "qty_step": float(item["lotSizeFilter"]["qtyStep"]),
        "min_notional": float(item["lotSizeFilter"]["minNotionalValue"]),
        "tick_size": float(item["priceFilter"]["tickSize"]),
        "max_leverage": float(item["leverageFilter"]["maxLeverage"]),
    }

    # Update full cache async (non-blocking)
    if REDIS_AVAILABLE:
        asyncio.create_task(refresh_symbol_info())
    return info
