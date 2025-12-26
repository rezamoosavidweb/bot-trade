import asyncio
import json
from redis.asyncio import Redis
from bybit_client import session

# ---------------- REDIS CLIENT ---------------- #
redis = Redis(host="localhost", port=6379, db=0, decode_responses=True)

# ---------------- KEYS ---------------- #
SYMBOL_INFO_KEY = "bybit:symbol_info"
TRANSACTION_LOG_KEY = "bybit:transaction_log"


# ---------------- CACHE FUNCTIONS ---------------- #
async def set_cache(key: str, value: dict, expire: int = 3600):
    """Set value in Redis with optional expiration (default 1h)."""
    await redis.set(key, json.dumps(value), ex=expire)


async def get_cache(key: str):
    """Get value from Redis, return None if not found."""
    data = await redis.get(key)
    if not data:
        return None
    return json.loads(data)


# ---------------- REFRESH ALL SYMBOL INFO ---------------- #
async def refresh_symbol_info():
    """Fetch all symbols info from Bybit with pagination and store in Redis."""
    try:
        symbols_data = {}
        cursor = None

        while True:
            res = session.get_instruments_info(
                category="linear", limit=200, cursor=cursor
            )
            for item in res["result"]["list"]:
                symbols_data[item["symbol"]] = {
                    "min_qty": float(item["lotSizeFilter"]["minOrderQty"]),
                    "max_order_qty": float(item["lotSizeFilter"]["maxOrderQty"]),
                    "qty_step": float(item["lotSizeFilter"]["qtyStep"]),
                    "min_notional": float(item["lotSizeFilter"]["minNotionalValue"]),
                    "tick_size": float(item["priceFilter"]["tickSize"]),
                    "max_leverage": float(item["leverageFilter"]["maxLeverage"]),
                }
            # Check if more pages exist
            cursor = res["result"].get("nextPageCursor")
            if not cursor:
                break

        await set_cache(SYMBOL_INFO_KEY, symbols_data, expire=3600)
        print(f"[INFO] Cached {len(symbols_data)} symbols in Redis")
    except Exception as e:
        print(f"[ERROR] Failed to refresh symbol info: {e}")


# ---------------- REFRESH TRANSACTION LOG ---------------- #
async def refresh_transaction_log(limit=50):
    """Fetch latest transaction log and store in Redis."""
    try:
        res = session.get_transaction_log(
            accountType="UNIFIED", category="linear", limit=limit
        )
        await set_cache(TRANSACTION_LOG_KEY, res.get("result", {}), expire=3600)
        print("[INFO] Transaction log cached in Redis")
    except Exception as e:
        print(f"[ERROR] Failed to refresh transaction log: {e}")


# ---------------- PERIODIC REFRESH ---------------- #
async def periodic_refresh(interval_seconds=3600 * 10):
    """Continuously refresh symbol info and transaction log."""
    # Refresh once at startup
    await refresh_symbol_info()
    await refresh_transaction_log()

    # Then loop periodically
    while True:
        await asyncio.sleep(interval_seconds)
        await refresh_symbol_info()
        await refresh_transaction_log()


# ---------------- HELPER FUNCTION ---------------- #
async def get_symbol_info(symbol: str):
    """Get symbol info from Redis, fallback to Bybit API if not cached."""
    symbols = await get_cache(SYMBOL_INFO_KEY)
    if symbols and symbol in symbols:
        return symbols[symbol]

    # fallback: fetch single symbol from Bybit
    res = session.get_instruments_info(category="linear", symbol=symbol)
    item = res["result"]["list"][0]
    info = {
        "min_qty": float(item["lotSizeFilter"]["minOrderQty"]),
        "max_order_qty": float(item["lotSizeFilter"]["maxOrderQty"]),
        "qty_step": float(item["lotSizeFilter"]["qtyStep"]),
        "min_notional": float(item["lotSizeFilter"]["minNotionalValue"]),
        "tick_size": float(item["priceFilter"]["tickSize"]),
        "max_leverage": float(item["leverageFilter"]["maxLeverage"]),
    }
    # update cache
    await refresh_symbol_info()
    return info
