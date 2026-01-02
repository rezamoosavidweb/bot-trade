"""
Capital Tracker Module
Tracks capital usage in open positions and rejected orders due to insufficient balance.
"""

import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from threading import Lock
from collections import defaultdict
from config import FIXED_MARGIN_USDT, MAX_LOSS_USDT, TARGET_PROFIT_USDT

# Lock for thread-safe file operations
_capital_file_lock = Lock()
CAPITAL_DATA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "capital_tracking.json"
)

# Per trade capital will be imported from config


def load_capital_data():
    """Load capital tracking data from JSON file."""
    try:
        with _capital_file_lock:
            if os.path.exists(CAPITAL_DATA_FILE):
                with open(CAPITAL_DATA_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
    except Exception as e:
        print(f"[CAPITAL_TRACKER][ERROR] Failed to load data: {e}")

    # Return default structure
    return {
        "positions": [],  # List of position events
        "rejected_orders": [],  # List of rejected orders
        "daily_stats": {},  # Daily aggregated stats
        "weekly_stats": {},  # Weekly aggregated stats
        "monthly_stats": {},  # Monthly aggregated stats
    }


def save_capital_data(data):
    """Save capital tracking data to JSON file."""
    try:
        with _capital_file_lock:
            with open(CAPITAL_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[CAPITAL_TRACKER][ERROR] Failed to save data: {e}")


def get_date_key(dt: datetime) -> str:
    """Get date key in format YYYY-MM-DD."""
    return dt.strftime("%Y-%m-%d")


def get_week_key(dt: datetime) -> str:
    """Get week key in format YYYY-WW."""
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def get_month_key(dt: datetime) -> str:
    """Get month key in format YYYY-MM."""
    return dt.strftime("%Y-%m")


def track_position_opened(symbol: str, capital_used: float, margin: float = None):
    """Track when a position is opened.

    Args:
        symbol: Trading symbol
        capital_used: Capital used for this position (USD)
        margin: Actual margin used (optional, for more accurate tracking)
    """
    data = load_capital_data()
    now = datetime.now(ZoneInfo("Asia/Tehran"))

    # Use margin if provided, otherwise use capital_used
    actual_capital = margin if margin is not None else capital_used

    position_event = {
        "symbol": symbol,
        "capital_used": actual_capital,
        "opened_at": now.isoformat(),
        "closed_at": None,
        "duration_seconds": None,
    }

    data["positions"].append(position_event)
    save_capital_data(data)

    print(
        f"[CAPITAL_TRACKER] Position opened: {symbol}, Capital: ${actual_capital:.2f}"
    )


def track_position_closed(symbol: str):
    """Track when a position is closed."""
    data = load_capital_data()
    now = datetime.now(ZoneInfo("Asia/Tehran"))

    # Find the most recent open position for this symbol
    for pos in reversed(data["positions"]):
        if pos["symbol"] == symbol and pos["closed_at"] is None:
            pos["closed_at"] = now.isoformat()
            opened_at = datetime.fromisoformat(pos["opened_at"])
            pos["duration_seconds"] = (now - opened_at).total_seconds()
            save_capital_data(data)
            print(f"[CAPITAL_TRACKER] Position closed: {symbol}")
            return

    print(f"[CAPITAL_TRACKER][WARN] No open position found for {symbol}")


def track_rejected_order(symbol: str, reason: str, capital_needed: float):
    """Track when an order is rejected due to insufficient balance."""
    data = load_capital_data()
    now = datetime.now(ZoneInfo("Asia/Tehran"))

    # Check if rejection is due to insufficient balance
    insufficient_keywords = [
        "insufficient",
        "balance",
        "margin",
        "not enough",
        "funds",
    ]
    is_insufficient = any(
        keyword.lower() in reason.lower() for keyword in insufficient_keywords
    )

    if is_insufficient:
        rejected_order = {
            "symbol": symbol,
            "reason": reason,
            "capital_needed": capital_needed,
            "rejected_at": now.isoformat(),
        }

        data["rejected_orders"].append(rejected_order)
        save_capital_data(data)
        print(
            f"[CAPITAL_TRACKER] Rejected order: {symbol}, Reason: {reason}, Capital needed: ${capital_needed:.2f}"
        )


def calculate_concurrent_capital(
    positions: list, target_time: datetime = None
) -> float:
    """Calculate maximum concurrent capital usage at a given time."""
    if target_time is None:
        target_time = datetime.now(ZoneInfo("Asia/Tehran"))

    if not positions:
        return 0.0

    # Filter positions that were open at target_time
    concurrent_capital = 0.0
    for pos in positions:
        opened_at = datetime.fromisoformat(pos["opened_at"])
        closed_at = (
            datetime.fromisoformat(pos["closed_at"])
            if pos["closed_at"]
            else target_time
        )

        # Check if position was open at target_time
        if opened_at <= target_time <= closed_at:
            concurrent_capital += pos["capital_used"]

    return concurrent_capital


def calculate_stats_for_period(
    positions: list, rejected_orders: list, start_date: datetime, end_date: datetime
) -> dict:
    """Calculate statistics for a given period."""
    stats = {
        "total_positions": 0,
        "total_rejected_orders": 0,
        "max_concurrent_capital": 0.0,
        "avg_concurrent_capital": 0.0,
        "total_capital_hours": 0.0,  # Sum of capital * hours for all positions
    }

    # Filter positions in period
    period_positions = []
    for pos in positions:
        opened_at = datetime.fromisoformat(pos["opened_at"])
        if start_date <= opened_at <= end_date:
            period_positions.append(pos)

    stats["total_positions"] = len(period_positions)

    # Filter rejected orders in period
    period_rejected = []
    for order in rejected_orders:
        rejected_at = datetime.fromisoformat(order["rejected_at"])
        if start_date <= rejected_at <= end_date:
            period_rejected.append(order)

    stats["total_rejected_orders"] = len(period_rejected)

    # Calculate max concurrent capital
    # Sample every hour in the period
    max_concurrent = 0.0
    total_concurrent = 0.0
    sample_count = 0

    current_time = start_date
    while current_time <= end_date:
        concurrent = calculate_concurrent_capital(period_positions, current_time)
        max_concurrent = max(max_concurrent, concurrent)
        total_concurrent += concurrent
        sample_count += 1
        current_time += timedelta(hours=1)

    stats["max_concurrent_capital"] = max_concurrent
    if sample_count > 0:
        stats["avg_concurrent_capital"] = total_concurrent / sample_count

    # Calculate total capital hours (sum of capital * duration for each position)
    total_capital_hours = 0.0
    for pos in period_positions:
        if pos["duration_seconds"]:
            hours = pos["duration_seconds"] / 3600
            total_capital_hours += pos["capital_used"] * hours

    stats["total_capital_hours"] = total_capital_hours

    return stats


def update_aggregated_stats():
    """Update daily, weekly, and monthly aggregated statistics."""
    data = load_capital_data()
    now = datetime.now(ZoneInfo("Asia/Tehran"))

    # Calculate stats for today
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now
    today_key = get_date_key(now)
    data["daily_stats"][today_key] = calculate_stats_for_period(
        data["positions"], data["rejected_orders"], today_start, today_end
    )

    # Calculate stats for this week
    week_start = today_start - timedelta(days=now.weekday())
    week_key = get_week_key(now)
    data["weekly_stats"][week_key] = calculate_stats_for_period(
        data["positions"], data["rejected_orders"], week_start, today_end
    )

    # Calculate stats for this month
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_key = get_month_key(now)
    data["monthly_stats"][month_key] = calculate_stats_for_period(
        data["positions"], data["rejected_orders"], month_start, today_end
    )

    save_capital_data(data)


def get_capital_report() -> str:
    """Generate a comprehensive capital usage report."""
    data = load_capital_data()
    now = datetime.now(ZoneInfo("Asia/Tehran"))

    # Update stats first
    update_aggregated_stats()

    # Get current stats
    today_key = get_date_key(now)
    week_key = get_week_key(now)
    month_key = get_month_key(now)

    today_stats = data["daily_stats"].get(today_key, {})
    week_stats = data["weekly_stats"].get(week_key, {})
    month_stats = data["monthly_stats"].get(month_key, {})

    # Calculate current concurrent capital
    current_concurrent = calculate_concurrent_capital(data["positions"])

    # Calculate recommendation based on historical data
    all_weekly_max = [
        stats.get("max_concurrent_capital", 0)
        for stats in data["weekly_stats"].values()
    ]
    all_monthly_max = [
        stats.get("max_concurrent_capital", 0)
        for stats in data["monthly_stats"].values()
    ]

    historical_max = max(
        all_weekly_max + all_monthly_max + [current_concurrent]
        if (all_weekly_max or all_monthly_max)
        else [current_concurrent]
    )

    report = (
        f"💰 **Capital Usage Report**\n\n"
        f"--------------------------------\n"
        f"```\n"
        f"💵 **FIXED_MARGIN_USDT:** ${FIXED_MARGIN_USDT:.2f}\n"
        f"🔴 **MAX_LOSS_USDT:** ${MAX_LOSS_USDT:.2f}\n"
        f"🎯 **TARGET_PROFIT_USDT:** ${TARGET_PROFIT_USDT:.2f}\n\n"
        f"📊 **Current Status:**\n"
        f"   • Active Positions: {len([p for p in data['positions'] if p['closed_at'] is None])}\n"
        f"   • Current Capital in Use: ${current_concurrent:.2f}\n\n"
        f"📅 **Today ({today_key}):**\n"
        f"   • Positions Opened: {today_stats.get('total_positions', 0)}\n"
        f"   • Rejected Orders: {today_stats.get('total_rejected_orders', 0)}\n"
        f"   • Max Concurrent Capital: ${today_stats.get('max_concurrent_capital', 0):.2f}\n"
        f"   • Avg Concurrent Capital: ${today_stats.get('avg_concurrent_capital', 0):.2f}\n\n"
        f"📆 **This Week ({week_key}):**\n"
        f"   • Positions Opened: {week_stats.get('total_positions', 0)}\n"
        f"   • Rejected Orders: {week_stats.get('total_rejected_orders', 0)}\n"
        f"   • Max Concurrent Capital: ${week_stats.get('max_concurrent_capital', 0):.2f}\n"
        f"   • Avg Concurrent Capital: ${week_stats.get('avg_concurrent_capital', 0):.2f}\n\n"
        f"📆 **This Month ({month_key}):**\n"
        f"   • Positions Opened: {month_stats.get('total_positions', 0)}\n"
        f"   • Rejected Orders: {month_stats.get('total_rejected_orders', 0)}\n"
        f"   • Max Concurrent Capital: ${month_stats.get('max_concurrent_capital', 0):.2f}\n"
        f"   • Avg Concurrent Capital: ${month_stats.get('avg_concurrent_capital', 0):.2f}\n\n"
        f"💡 **Recommendation:**\n"
        f"   • Historical Max Capital: ${historical_max:.2f}\n"
        f"   • Recommended Wallet Balance: ${historical_max * 1.2:.2f} (+20% buffer)\n"
        f"   • Total Rejected Orders (All Time): {len(data['rejected_orders'])}\n"
        f"```\n"
        f"--------------------------------\n"
    )

    return report
