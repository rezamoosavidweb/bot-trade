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
from logger import log_print
from decimal import Decimal, ROUND_DOWN, InvalidOperation


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
        log_print(f"[WARN] position check failed: {e}")
        return False


# ---------------- TRADE CALCULATION ---------------- #
def normalize_qty(qty, step):
    """Adjust quantity based on step size."""
    try:
        step_dec = Decimal(str(step))
        qty_dec = Decimal(str(qty))
        if step_dec <= 0:
            return float(qty)
        normalized = (qty_dec / step_dec).to_integral_value(rounding=ROUND_DOWN) * step_dec
        # Quantize to step's decimal places (e.g. 0.1 -> 1 decimal)
        normalized = normalized.quantize(step_dec, rounding=ROUND_DOWN)
        return float(normalized)
    except (InvalidOperation, ValueError, TypeError):
        # Fallback to previous float-based behavior
        precision = len(str(step).split(".")[1]) if "." in str(step) else 0
        qty = int(float(qty) / float(step)) * float(step)
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
