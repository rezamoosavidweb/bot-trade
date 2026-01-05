import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from redis.asyncio import Redis

from api import (
    get_all_linear_instruments,
    get_transaction_log,
    get_single_instrument,
)
from logger import log_print


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
        log_print("[CACHE] Redis connected")
    except Exception as e:
        redis = None
        REDIS_AVAILABLE = False
        log_print(f"[CACHE][WARN] Redis disabled: {e}")


# ---------------- KEYS ---------------- #
SYMBOL_INFO_KEY = "bybit:symbol_info"
TRANSACTION_LOG_KEY = "bybit:transaction_log"
OPEN_POSITIONS_KEY = "bot:open_positions"
POSITION_ENTRY_TIMES_KEY = "bot:position_entry_times"
POSITION_TP_PRICES_KEY = "bot:position_tp_prices"
PENDING_SL_UPDATES_KEY = "bot:pending_sl_updates"


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
            log_print(f"[CACHE] {len(symbols_data)} symbols cached")
        else:
            log_print(
                f"[CACHE]][WARN] cached is disabled! for get_all_linear_instruments!"
            )

    except Exception as e:
        log_print(f"[CACHE][ERROR] refresh_symbol_info failed: {e}")


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
            log_print("[CACHE] Transaction log cached")
        else:
            log_print("[CACHE][WARN] cached is disabled!")
    except Exception as e:
        log_print(f"[CACHE][ERROR] refresh_transaction_log failed: {e}")


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
        log_print("[CACHE][WARN] cached is disabled in periodic_refresh")


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
    log_print(f"[CACHE][MISS] {symbol}, fetching from API")
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


# ---------------- POSITION TRACKING ---------------- #
async def add_open_position(symbol: str):
    """Add symbol to open positions set in Redis."""
    if not REDIS_AVAILABLE:
        return
    try:
        positions = await get_open_positions()
        if positions is None:
            positions = set()
        else:
            positions = set(positions)
        positions.add(symbol)
        await set_cache(OPEN_POSITIONS_KEY, list(positions), expire=86400 * 7)  # 7 days
    except Exception as e:
        log_print(f"[CACHE][ERROR] Failed to add open position {symbol}: {e}")


async def remove_open_position(symbol: str):
    """Remove symbol from open positions set in Redis."""
    if not REDIS_AVAILABLE:
        return
    try:
        positions = await get_open_positions()
        if positions is None:
            return
        positions = set(positions)
        positions.discard(symbol)
        await set_cache(OPEN_POSITIONS_KEY, list(positions), expire=86400 * 7)
    except Exception as e:
        log_print(f"[CACHE][ERROR] Failed to remove open position {symbol}: {e}")


async def get_open_positions():
    """Get all open positions from Redis."""
    if not REDIS_AVAILABLE:
        return set()
    try:
        positions = await get_cache(OPEN_POSITIONS_KEY)
        return set(positions) if positions else set()
    except Exception as e:
        log_print(f"[CACHE][ERROR] Failed to get open positions: {e}")
        return set()


async def is_position_open(symbol: str) -> bool:
    """Check if symbol is in open positions."""
    positions = await get_open_positions()
    return symbol in positions


async def set_position_entry_time(symbol: str, entry_time: datetime):
    """Set entry time for a position in Redis."""
    if not REDIS_AVAILABLE:
        return
    try:
        entry_times = await get_position_entry_times()
        if entry_times is None:
            entry_times = {}
        entry_times[symbol] = entry_time.isoformat()
        await set_cache(POSITION_ENTRY_TIMES_KEY, entry_times, expire=86400 * 7)
    except Exception as e:
        log_print(f"[CACHE][ERROR] Failed to set entry time for {symbol}: {e}")


async def get_position_entry_time(symbol: str) -> datetime | None:
    """Get entry time for a position from Redis."""
    if not REDIS_AVAILABLE:
        return None
    try:
        entry_times = await get_position_entry_times()
        if entry_times and symbol in entry_times:
            from zoneinfo import ZoneInfo

            return datetime.fromisoformat(entry_times[symbol]).replace(
                tzinfo=ZoneInfo("Asia/Tehran")
            )
        return None
    except Exception as e:
        log_print(f"[CACHE][ERROR] Failed to get entry time for {symbol}: {e}")
        return None


async def remove_position_entry_time(symbol: str):
    """Remove entry time for a position from Redis."""
    if not REDIS_AVAILABLE:
        return
    try:
        entry_times = await get_position_entry_times()
        if entry_times and symbol in entry_times:
            entry_times.pop(symbol, None)
            await set_cache(POSITION_ENTRY_TIMES_KEY, entry_times, expire=86400 * 7)
    except Exception as e:
        log_print(f"[CACHE][ERROR] Failed to remove entry time for {symbol}: {e}")


async def get_position_entry_times():
    """Get all position entry times from Redis."""
    if not REDIS_AVAILABLE:
        return {}
    try:
        entry_times = await get_cache(POSITION_ENTRY_TIMES_KEY)
        return entry_times if entry_times else {}
    except Exception as e:
        log_print(f"[CACHE][ERROR] Failed to get position entry times: {e}")
        return {}


async def set_position_tp_prices(symbol: str, tp_prices: dict):
    """Set TP prices for a position in Redis."""
    if not REDIS_AVAILABLE:
        return
    try:
        tp_data = await get_position_tp_prices()
        if tp_data is None:
            tp_data = {}
        tp_data[symbol] = tp_prices
        await set_cache(POSITION_TP_PRICES_KEY, tp_data, expire=86400 * 7)
    except Exception as e:
        log_print(f"[CACHE][ERROR] Failed to set TP prices for {symbol}: {e}")


async def get_position_tp_prices(symbol: str = None):
    """Get TP prices for a position or all positions from Redis."""
    if not REDIS_AVAILABLE:
        return {} if symbol is None else None
    try:
        tp_data = await get_cache(POSITION_TP_PRICES_KEY)
        if tp_data is None:
            return {} if symbol is None else None
        if symbol is None:
            return tp_data
        return tp_data.get(symbol)
    except Exception as e:
        log_print(f"[CACHE][ERROR] Failed to get TP prices: {e}")
        return {} if symbol is None else None


async def remove_position_tp_prices(symbol: str):
    """Remove TP prices for a position from Redis."""
    if not REDIS_AVAILABLE:
        return
    try:
        tp_data = await get_position_tp_prices()
        if tp_data and symbol in tp_data:
            tp_data.pop(symbol, None)
            await set_cache(POSITION_TP_PRICES_KEY, tp_data, expire=86400 * 7)
    except Exception as e:
        log_print(f"[CACHE][ERROR] Failed to remove TP prices for {symbol}: {e}")


async def set_pending_sl_update(symbol: str, update_info: dict):
    """Set pending SL update info for a symbol in Redis."""
    if not REDIS_AVAILABLE:
        return
    try:
        # Convert datetime to ISO string if present
        if "entry_time" in update_info and isinstance(
            update_info["entry_time"], datetime
        ):
            update_info = update_info.copy()
            update_info["entry_time"] = update_info["entry_time"].isoformat()

        pending_updates = await get_pending_sl_updates()
        if pending_updates is None:
            pending_updates = {}
        pending_updates[symbol] = update_info
        await set_cache(PENDING_SL_UPDATES_KEY, pending_updates, expire=86400 * 7)
    except Exception as e:
        log_print(f"[CACHE][ERROR] Failed to set pending SL update for {symbol}: {e}")


async def get_pending_sl_update(symbol: str) -> dict | None:
    """Get pending SL update info for a symbol from Redis."""
    if not REDIS_AVAILABLE:
        return None
    try:
        pending_updates = await get_pending_sl_updates()
        if pending_updates and symbol in pending_updates:
            update_info = pending_updates[symbol].copy()
            # Convert ISO string back to datetime if present
            if "entry_time" in update_info:
                from zoneinfo import ZoneInfo

                update_info["entry_time"] = datetime.fromisoformat(
                    update_info["entry_time"]
                ).replace(tzinfo=ZoneInfo("Asia/Tehran"))
            return update_info
        return None
    except Exception as e:
        log_print(f"[CACHE][ERROR] Failed to get pending SL update for {symbol}: {e}")
        return None


async def get_pending_sl_updates():
    """Get all pending SL updates from Redis."""
    if not REDIS_AVAILABLE:
        return {}
    try:
        pending_updates = await get_cache(PENDING_SL_UPDATES_KEY)
        return pending_updates if pending_updates else {}
    except Exception as e:
        log_print(f"[CACHE][ERROR] Failed to get pending SL updates: {e}")
        return {}


async def remove_pending_sl_update(symbol: str):
    """Remove pending SL update for a symbol from Redis."""
    if not REDIS_AVAILABLE:
        return
    try:
        pending_updates = await get_pending_sl_updates()
        if pending_updates and symbol in pending_updates:
            pending_updates.pop(symbol, None)
            await set_cache(PENDING_SL_UPDATES_KEY, pending_updates, expire=86400 * 7)
    except Exception as e:
        log_print(
            f"[CACHE][ERROR] Failed to remove pending SL update for {symbol}: {e}"
        )
