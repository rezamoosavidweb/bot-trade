"""
Liquidity Analyzer Module
Analyzes order book depth, volume, and execution quality to predict real account behavior.
"""

import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from threading import Lock
from typing import Dict, List, Optional, Tuple
from config import IS_DEMO

# Lock for thread-safe file operations
_liquidity_file_lock = Lock()
LIQUIDITY_DATA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "liquidity_tracking.json"
)


def load_liquidity_data():
    """Load liquidity tracking data from JSON file."""
    try:
        with _liquidity_file_lock:
            if os.path.exists(LIQUIDITY_DATA_FILE):
                with open(LIQUIDITY_DATA_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
    except Exception as e:
        print(f"[LIQUIDITY_ANALYZER][ERROR] Failed to load data: {e}")

    # Return default structure
    return {
        "order_executions": [],  # Track order execution details
        "symbol_liquidity": {},  # Cache liquidity metrics per symbol
        "daily_stats": {},  # Daily aggregated stats
    }


def save_liquidity_data(data):
    """Save liquidity tracking data to JSON file."""
    try:
        with _liquidity_file_lock:
            with open(LIQUIDITY_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[LIQUIDITY_ANALYZER][ERROR] Failed to save data: {e}")


def get_order_book_depth(symbol: str, limit: int = 25) -> Optional[Dict]:
    """
    Get order book depth from Bybit API.

    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")
        limit: Number of price levels to retrieve (default 25)

    Returns:
        Dict with 'bids' and 'asks' lists, or None if error
    """
    try:
        from clients import bybitClient

        response = bybitClient.get_orderbook(
            category="linear", symbol=symbol, limit=limit
        )

        if response.get("retCode") == 0:
            result = response.get("result", {})
            return {
                "bids": result.get("b", []),  # Buy orders (price, size)
                "asks": result.get("a", []),  # Sell orders (price, size)
                "timestamp": result.get("ts", 0),
            }
    except Exception as e:
        print(f"[LIQUIDITY_ANALYZER][ERROR] Failed to get order book for {symbol}: {e}")

    return None


def get_24h_ticker(symbol: str) -> Optional[Dict]:
    """
    Get 24h ticker statistics including volume.

    Args:
        symbol: Trading symbol

    Returns:
        Dict with volume and price data, or None if error
    """
    try:
        from clients import bybitClient

        response = bybitClient.get_tickers(category="linear", symbol=symbol)

        if response.get("retCode") == 0:
            result = response.get("result", {}).get("list", [])
            if result:
                ticker = result[0]
                return {
                    "volume24h": float(ticker.get("volume24h", 0)),
                    "turnover24h": float(ticker.get("turnover24h", 0)),
                    "lastPrice": float(ticker.get("lastPrice", 0)),
                    "highPrice24h": float(ticker.get("highPrice24h", 0)),
                    "lowPrice24h": float(ticker.get("lowPrice24h", 0)),
                }
    except Exception as e:
        print(f"[LIQUIDITY_ANALYZER][ERROR] Failed to get ticker for {symbol}: {e}")

    return None


def calculate_liquidity_metrics(symbol: str, order_qty: float, side: str) -> Dict:
    """
    Calculate liquidity metrics for a given order.

    Args:
        symbol: Trading symbol
        order_qty: Order quantity
        side: "Buy" or "Sell"

    Returns:
        Dict with liquidity metrics
    """
    order_book = get_order_book_depth(symbol, limit=50)
    ticker = get_24h_ticker(symbol)

    if not order_book or not ticker:
        return {
            "available": False,
            "reason": "Failed to fetch market data",
        }

    current_price = ticker["lastPrice"]
    volume_24h = ticker["volume24h"]

    # Calculate available liquidity on the order book side
    if side == "Buy":
        # For buy orders, we look at asks (sell side)
        orders = order_book["asks"]
        order_side = "asks"
    else:
        # For sell orders, we look at bids (buy side)
        orders = order_book["bids"]
        order_side = "bids"

    # Calculate cumulative liquidity up to order_qty
    cumulative_qty = 0.0
    cumulative_value = 0.0
    price_levels_used = 0
    max_slippage = 0.0

    for price_str, size_str in orders:
        price = float(price_str)
        size = float(size_str)

        if cumulative_qty >= order_qty:
            break

        remaining_qty = order_qty - cumulative_qty
        qty_to_take = min(size, remaining_qty)

        cumulative_qty += qty_to_take
        cumulative_value += qty_to_take * price
        price_levels_used += 1

        # Calculate slippage (difference from current price)
        if side == "Buy":
            slippage = ((price - current_price) / current_price) * 100
        else:
            slippage = ((current_price - price) / current_price) * 100

        max_slippage = max(max_slippage, slippage)

    # Average execution price
    avg_execution_price = (
        cumulative_value / cumulative_qty if cumulative_qty > 0 else current_price
    )

    # Calculate fill percentage
    fill_percentage = (cumulative_qty / order_qty) * 100 if order_qty > 0 else 0

    # Liquidity score (0-100)
    # Based on: fill percentage, price levels needed, volume ratio
    volume_ratio = (order_qty / volume_24h) * 100 if volume_24h > 0 else 0
    liquidity_score = min(100, fill_percentage * 0.7 + (100 - volume_ratio) * 0.3)

    return {
        "available": True,
        "symbol": symbol,
        "side": side,
        "order_qty": order_qty,
        "current_price": current_price,
        "avg_execution_price": avg_execution_price,
        "fill_percentage": fill_percentage,
        "price_levels_needed": price_levels_used,
        "max_slippage_percent": max_slippage,
        "volume_24h": volume_24h,
        "order_to_volume_ratio": volume_ratio,
        "liquidity_score": liquidity_score,
        "estimated_fill_time_seconds": price_levels_used * 0.1,  # Rough estimate
        "timestamp": datetime.now(ZoneInfo("Asia/Tehran")).isoformat(),
    }


def track_order_execution(
    symbol: str,
    side: str,
    qty: float,
    order_id: str,
    order_type: str = "Market",
    liquidity_metrics: Optional[Dict] = None,
):
    """
    Track order execution details for analysis.

    Args:
        symbol: Trading symbol
        side: "Buy" or "Sell"
        qty: Order quantity
        order_id: Order ID from exchange
        order_type: Order type (Market, Limit, etc.)
        liquidity_metrics: Pre-calculated liquidity metrics
    """
    data = load_liquidity_data()
    now = datetime.now(ZoneInfo("Asia/Tehran"))

    execution_record = {
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "order_id": order_id,
        "order_type": order_type,
        "placed_at": now.isoformat(),
        "filled_at": None,
        "fill_percentage": None,
        "execution_price": None,
        "slippage": None,
        "liquidity_metrics": liquidity_metrics,
        "is_demo": IS_DEMO,
    }

    data["order_executions"].append(execution_record)
    save_liquidity_data(data)

    print(f"[LIQUIDITY_ANALYZER] Order tracked: {symbol} {side} {qty} (ID: {order_id})")


def update_order_fill(
    order_id: str,
    fill_percentage: float,
    execution_price: float,
    slippage: float = None,
):
    """
    Update order execution with fill details.

    Args:
        order_id: Order ID
        fill_percentage: Percentage of order filled (0-100)
        execution_price: Average execution price
        slippage: Slippage percentage (optional)
    """
    data = load_liquidity_data()
    now = datetime.now(ZoneInfo("Asia/Tehran"))

    # Find the most recent order with this ID
    for execution in reversed(data["order_executions"]):
        if execution["order_id"] == order_id and execution["filled_at"] is None:
            execution["filled_at"] = now.isoformat()
            execution["fill_percentage"] = fill_percentage
            execution["execution_price"] = execution_price
            execution["slippage"] = slippage
            save_liquidity_data(data)
            print(
                f"[LIQUIDITY_ANALYZER] Order filled: {order_id} ({fill_percentage:.1f}% @ ${execution_price:.2f})"
            )
            return

    print(f"[LIQUIDITY_ANALYZER][WARN] Order ID {order_id} not found for update")


def analyze_symbol_liquidity(symbol: str, typical_order_qty: float) -> Dict:
    """
    Analyze liquidity for a symbol and provide recommendations.

    Args:
        symbol: Trading symbol
        typical_order_qty: Typical order quantity for this symbol

    Returns:
        Dict with analysis and recommendations
    """
    # Calculate metrics for both buy and sell
    buy_metrics = calculate_liquidity_metrics(symbol, typical_order_qty, "Buy")
    sell_metrics = calculate_liquidity_metrics(symbol, typical_order_qty, "Sell")

    if not buy_metrics.get("available") or not sell_metrics.get("available"):
        return {
            "symbol": symbol,
            "status": "error",
            "message": "Failed to analyze liquidity",
        }

    # Determine worst case (higher slippage)
    worst_slippage = max(
        buy_metrics.get("max_slippage_percent", 0),
        sell_metrics.get("max_slippage_percent", 0),
    )

    worst_fill = min(
        buy_metrics.get("fill_percentage", 0),
        sell_metrics.get("fill_percentage", 0),
    )

    avg_liquidity_score = (
        buy_metrics.get("liquidity_score", 0) + sell_metrics.get("liquidity_score", 0)
    ) / 2

    # Recommendations
    recommendations = []
    risk_level = "LOW"

    if worst_fill < 50:
        risk_level = "HIGH"
        recommendations.append(
            f"⚠️ Low liquidity: Only {worst_fill:.1f}% of order can be filled immediately"
        )
        recommendations.append("💡 Consider: Split order into smaller parts")
        recommendations.append("💡 Consider: Use limit orders with better prices")
    elif worst_fill < 80:
        risk_level = "MEDIUM"
        recommendations.append(f"⚠️ Moderate liquidity: {worst_fill:.1f}% fill expected")
        recommendations.append("💡 Consider: Monitor execution closely")

    if worst_slippage > 0.5:
        recommendations.append(
            f"⚠️ High slippage risk: Up to {worst_slippage:.2f}% slippage"
        )
        if risk_level == "LOW":
            risk_level = "MEDIUM"

    if avg_liquidity_score < 50:
        recommendations.append("💡 Low liquidity score - consider alternative symbols")

    return {
        "symbol": symbol,
        "status": "ok",
        "risk_level": risk_level,
        "buy_metrics": buy_metrics,
        "sell_metrics": sell_metrics,
        "worst_case": {
            "slippage_percent": worst_slippage,
            "fill_percentage": worst_fill,
        },
        "liquidity_score": avg_liquidity_score,
        "recommendations": recommendations,
        "timestamp": datetime.now(ZoneInfo("Asia/Tehran")).isoformat(),
    }


def get_liquidity_report() -> str:
    """Generate a comprehensive liquidity analysis report."""
    data = load_liquidity_data()
    now = datetime.now(ZoneInfo("Asia/Tehran"))

    # Get recent orders
    recent_orders = [
        ex
        for ex in data["order_executions"]
        if datetime.fromisoformat(ex["placed_at"]) > now - timedelta(days=7)
    ]

    # Analyze execution quality
    total_orders = len(recent_orders)
    filled_orders = [o for o in recent_orders if o.get("filled_at")]
    partial_fills = [o for o in filled_orders if o.get("fill_percentage", 100) < 100]

    avg_slippage = 0.0
    if filled_orders:
        slippages = [o.get("slippage", 0) for o in filled_orders if o.get("slippage")]
        avg_slippage = sum(slippages) / len(slippages) if slippages else 0.0

    # Group by symbol
    symbol_stats = {}
    for order in recent_orders:
        symbol = order["symbol"]
        if symbol not in symbol_stats:
            symbol_stats[symbol] = {
                "total": 0,
                "filled": 0,
                "partial": 0,
                "avg_slippage": 0.0,
            }

        symbol_stats[symbol]["total"] += 1
        if order.get("filled_at"):
            symbol_stats[symbol]["filled"] += 1
            if order.get("fill_percentage", 100) < 100:
                symbol_stats[symbol]["partial"] += 1

    report = (
        f"📊 **Liquidity Analysis Report**\n\n"
        f"📅 **Last 7 Days:**\n"
        f"   • Total Orders: {total_orders}\n"
        f"   • Filled Orders: {len(filled_orders)}\n"
        f"   • Partial Fills: {len(partial_fills)}\n"
        f"   • Avg Slippage: {avg_slippage:.3f}%\n\n"
    )

    if symbol_stats:
        report += f"📈 **By Symbol:**\n"
        for symbol, stats in symbol_stats.items():
            partial_rate = (
                (stats["partial"] / stats["filled"] * 100) if stats["filled"] > 0 else 0
            )
            report += (
                f"   • {symbol}: {stats['total']} orders, "
                f"{stats['filled']} filled, "
                f"{stats['partial']} partial ({partial_rate:.1f}%)\n"
            )

    report += (
        f"\n💡 **Note:** This analysis is based on {'DEMO' if IS_DEMO else 'LIVE'} account data.\n"
        f"In live trading, liquidity may vary significantly.\n"
    )

    return report
