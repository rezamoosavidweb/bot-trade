from config import (
    IS_DEMO,
    SELECTED_API_KEY,
    SELECTED_API_SECRET,
    MAX_LEVERAGE,
    FIXED_MARGIN_USDT,
    MAX_LOSS_USDT,
)

from cache import get_symbol_info as get_cached_symbol_info
from api import get_wallet_balance, get_positions
import asyncio


# ---------------- SYMBOL INFO ---------------- #
async def get_symbol_info(symbol: str):
    """Fetch symbol info from cache first, fallback to API."""
    return await get_cached_symbol_info(symbol)


# ---------------- BALANCE ---------------- #
async def get_usdt_balance() -> float:
    """Return USDT balance from Bybit."""
    wallet =await get_wallet_balance(accountType="UNIFIED")
    coins = wallet["result"]["list"][0]["coin"]
    for c in coins:
        if c["coin"] == "USDT":
            val = c.get("walletBalance") or c.get("totalAvailableBalance") or 0.0
            try:
                return float(val)
            except:
                return 0.0
    return 0.0


# ---------------- OPEN POSITION ---------------- #
async def is_position_open(symbol: str) -> bool:
    """Check if a symbol has an open position."""
    try:
        res = get_positions(symbol=symbol)
        positions = res["result"]["list"]
        if not positions:
            return False
        return float(positions[0]["size"]) != 0
    except Exception as e:
        print(f"[WARN] position check failed: {e}")
        return False


# ---------------- TRADE CALCULATION ---------------- #
def normalize_qty(qty, step):
    """Adjust quantity based on step size."""
    precision = len(str(step).split(".")[1]) if "." in str(step) else 0
    qty = int(qty / step) * step
    return round(qty, precision)


async def calculate_fixed_trade(symbol, entry, sl):
    """Calculate trade quantity and leverage for a fixed margin strategy."""
    info = await get_symbol_info(symbol)
    sl_distance = abs(entry - sl)
    if sl_distance <= 0:
        return None

    raw_qty = MAX_LOSS_USDT / sl_distance
    qty = normalize_qty(raw_qty, info["qty_step"])
    qty = min(qty, info["max_order_qty"])
    if qty < info["min_qty"]:
        return None

    notional = qty * entry
    if notional < info["min_notional"]:
        return None

    raw_leverage = notional / FIXED_MARGIN_USDT
    leverage = min(raw_leverage, min(info["max_leverage"], MAX_LEVERAGE))
    leverage = round(leverage, 2)

    max_notional = FIXED_MARGIN_USDT * leverage
    if notional > max_notional:
        qty = normalize_qty(max_notional / entry, info["qty_step"])

    if qty < info["min_qty"]:
        return None

    return {
        "qty": qty,
        "leverage": leverage,
        "margin": round((qty * entry) / leverage, 2),
        "max_loss": round(qty * sl_distance, 2),
    }
