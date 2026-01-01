from telethon import TelegramClient
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re
import asyncio
from collections import defaultdict

# --- تنظیمات ---
api_id = 27396957
api_hash = "53e16a90d89a28a0a67bb95ca3dff324"

source_channel = "CryptoSignalsGolden"  # کانالی که می‌خواهید بررسی شود


def is_vip_signal(text: str) -> bool:
    """Check if message is a VIP signal"""
    if not text:
        return False
    vip_keywords = [
        "Details visible for #VIP members",
        "🔑 Details visible for #VIP",
        "VIP members",
    ]
    return any(keyword in text for keyword in vip_keywords)


def is_free_signal(text: str) -> bool:
    """Check if message is a free signal (has symbol and entry/sl/targets)"""
    if not text:
        return False

    # Check for symbol pattern
    symbol_pattern = r"#\s*([A-Z0-9]+)\s*/\s*(USDT|USDC|USD)"
    if not re.search(symbol_pattern, text, re.I):
        return False

    # Check for entry, SL, targets (free signals have these visible)
    has_entry = bool(re.search(r"Entry[:\s]*[\d.]+", text, re.I))
    has_sl = bool(re.search(r"Stop\s*Loss[:\s]*[\d.]+", text, re.I))
    has_targets = bool(re.search(r"Targets?[:\s]*[\d.]+", text, re.I))

    # If it's not VIP and has signal details, it's free
    return not is_vip_signal(text) and (has_entry or has_sl or has_targets)


def extract_symbol_from_signal(text: str) -> str:
    """Extract symbol from signal message"""
    symbol_match = re.search(r"#\s*([A-Z0-9]+)\s*/\s*(USDT|USDC|USD)", text, re.I)
    if symbol_match:
        return symbol_match.group(1).upper() + symbol_match.group(2).upper()
    return None


def parse_tp_from_reply(text: str) -> int:
    """Parse which TP was reached from reply message"""
    if not text:
        return None

    # Check for TP3 first (most specific)
    tp3_patterns = [
        r"Target\s*3\s*reached",
        r"TP3\s*reached",
        r"🎯\s*TP3",
        r"TP\s*3",
    ]

    # Check for TP2
    tp2_patterns = [
        r"Target\s*2\s*reached",
        r"TP2\s*reached",
        r"🎯\s*TP2",
        r"TP\s*2",
    ]

    # Check for TP1
    tp1_patterns = [
        r"Target\s*1\s*reached",
        r"TP1\s*reached",
        r"🎯\s*TP1",
        r"TP\s*1",
    ]

    # Check for position closed
    closed_patterns = [
        r"Position\s*closed",
        r"Position\s*Close",
        r"Closed",
        r"🔒",
        r"Position\s*بسته",
    ]

    text_lower = text.lower()

    # Check in order: TP3, TP2, TP1, closed
    if any(re.search(pattern, text_lower, re.I) for pattern in tp3_patterns):
        return 3
    elif any(re.search(pattern, text_lower, re.I) for pattern in tp2_patterns):
        return 2
    elif any(re.search(pattern, text_lower, re.I) for pattern in tp1_patterns):
        return 1
    elif any(re.search(pattern, text_lower, re.I) for pattern in closed_patterns):
        return "closed"

    return None


async def analyze_concurrent_signals():
    """Analyze concurrent signals from last 6 months"""
    client = TelegramClient("session_name", api_id, api_hash)

    await client.start()

    # Calculate date 6 months ago
    six_months_ago = datetime.now(ZoneInfo("Asia/Tehran")) - timedelta(days=180)

    print(
        f"🔍 Searching for signals from {six_months_ago.strftime('%Y-%m-%d')} to now..."
    )

    # Dictionary to track signals: {message_id: {symbol, start_time, end_time, type}}
    signals = {}
    # Dictionary to track replies: {reply_to_msg_id: {tp_reached, time}}
    replies = {}

    # Track all messages to find replies
    all_messages = []

    # First pass: collect all signals and their replies
    async for message in client.iter_messages(
        source_channel, offset_date=six_months_ago
    ):
        if not message.message:
            continue

        text = message.message
        msg_id = message.id
        msg_date = message.date.astimezone(ZoneInfo("Asia/Tehran"))

        # Check if it's a VIP signal
        if is_vip_signal(text):
            symbol = extract_symbol_from_signal(text)
            if symbol:
                signals[msg_id] = {
                    "symbol": symbol,
                    "start_time": msg_date,
                    "end_time": None,
                    "type": "VIP",
                    "tp_reached": None,
                }
                print(
                    f"📊 Found VIP signal: {symbol} at {msg_date.strftime('%Y-%m-%d %H:%M:%S')}"
                )

        # Check if it's a free signal
        elif is_free_signal(text):
            symbol = extract_symbol_from_signal(text)
            if symbol:
                signals[msg_id] = {
                    "symbol": symbol,
                    "start_time": msg_date,
                    "end_time": None,
                    "type": "Free",
                    "tp_reached": None,
                }
                print(
                    f"📊 Found Free signal: {symbol} at {msg_date.strftime('%Y-%m-%d %H:%M:%S')}"
                )

        # Check if it's a reply to a signal (for VIP signals)
        if message.reply_to:
            # Try different ways to get reply_to message ID
            reply_to_id = None
            if hasattr(message.reply_to, "reply_to_msg_id"):
                reply_to_id = message.reply_to.reply_to_msg_id
            elif hasattr(message.reply_to, "id"):
                reply_to_id = message.reply_to.id

            if reply_to_id:
                tp_reached = parse_tp_from_reply(text)
                if tp_reached:
                    replies[msg_id] = {
                        "reply_to": reply_to_id,
                        "tp_reached": tp_reached,
                        "time": msg_date,
                    }
                    if reply_to_id in signals:
                        print(
                            f"   ↳ Reply found for signal {reply_to_id}: TP{tp_reached} reached at {msg_date.strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                    else:
                        print(
                            f"   ↳ Reply found (signal not tracked): TP{tp_reached} at {msg_date.strftime('%Y-%m-%d %H:%M:%S')}"
                        )

        all_messages.append(message)

    print(f"\n✅ Total signals found: {len(signals)}")
    print(f"✅ Total replies found: {len(replies)}")

    # Second pass: update signal end times based on replies
    # Sort replies by time to process in chronological order
    sorted_replies = sorted(replies.items(), key=lambda x: x[1]["time"])

    for reply_msg_id, reply_data in sorted_replies:
        signal_id = reply_data["reply_to"]
        if signal_id in signals:
            tp_reached = reply_data["tp_reached"]
            # Only update if TP3 reached or position closed (or if no end time set yet)
            if tp_reached == 3 or tp_reached == "closed":
                if (
                    signals[signal_id]["end_time"] is None
                    or reply_data["time"] < signals[signal_id]["end_time"]
                ):
                    signals[signal_id]["end_time"] = reply_data["time"]
                    signals[signal_id]["tp_reached"] = tp_reached
                    print(
                        f"   ✓ Signal {signal_id} ({signals[signal_id]['symbol']}) ended at {reply_data['time'].strftime('%Y-%m-%d %H:%M:%S')}"
                    )

    # For signals without end time, assume they're still open (use current time)
    current_time = datetime.now(ZoneInfo("Asia/Tehran"))
    for signal_id, signal_data in signals.items():
        if signal_data["end_time"] is None:
            signal_data["end_time"] = current_time

    # Calculate concurrent signals
    print("\n📈 Calculating concurrent signals...")

    # Create time intervals for each signal
    intervals = []
    for signal_id, signal_data in signals.items():
        intervals.append(
            {
                "signal_id": signal_id,
                "symbol": signal_data["symbol"],
                "start": signal_data["start_time"],
                "end": signal_data["end_time"],
                "type": signal_data["type"],
            }
        )

    # Sort by start time
    intervals.sort(key=lambda x: x["start"])

    # Find maximum concurrent signals
    max_concurrent = 0
    max_concurrent_time = None
    max_concurrent_signals = []

    # For each signal, check how many others overlap
    for i, interval in enumerate(intervals):
        concurrent_count = 1  # Count itself
        concurrent_signals = [interval["symbol"]]

        for j, other_interval in enumerate(intervals):
            if i != j:
                # Check if intervals overlap
                if (
                    other_interval["start"] <= interval["end"]
                    and other_interval["end"] >= interval["start"]
                ):
                    concurrent_count += 1
                    concurrent_signals.append(other_interval["symbol"])

        if concurrent_count > max_concurrent:
            max_concurrent = concurrent_count
            max_concurrent_time = interval["start"]
            max_concurrent_signals = concurrent_signals[:]

    # Calculate maximum capital needed
    max_capital = max_concurrent * 300

    # Print results
    print("\n" + "=" * 60)
    print("📊 RESULTS")
    print("=" * 60)
    print(
        f"\n📅 Analysis Period: {six_months_ago.strftime('%Y-%m-%d')} to {datetime.now(ZoneInfo('Asia/Tehran')).strftime('%Y-%m-%d')}"
    )
    print(f"\n📈 Total Signals Found:")
    print(f"   • VIP Signals: {sum(1 for s in signals.values() if s['type'] == 'VIP')}")
    print(
        f"   • Free Signals: {sum(1 for s in signals.values() if s['type'] == 'Free')}"
    )
    print(f"   • Total: {len(signals)}")

    print(f"\n🎯 Maximum Concurrent Signals:")
    print(f"   • Count: {max_concurrent}")
    print(
        f"   • Time: {max_concurrent_time.strftime('%Y-%m-%d %H:%M:%S') if max_concurrent_time else 'N/A'}"
    )
    print(
        f"   • Symbols: {', '.join(max_concurrent_signals[:10])}{'...' if len(max_concurrent_signals) > 10 else ''}"
    )

    print(f"\n💰 Maximum Capital Required:")
    print(f"   • Per Trade: $300")
    print(f"   • Maximum Concurrent Trades: {max_concurrent}")
    print(f"   • Total Capital Needed: ${max_capital:,}")

    # Additional statistics
    print(f"\n📊 Additional Statistics:")

    # Average signal duration
    durations = []
    for signal_data in signals.values():
        if signal_data["end_time"] and signal_data["start_time"]:
            duration = (
                signal_data["end_time"] - signal_data["start_time"]
            ).total_seconds() / 3600  # hours
            durations.append(duration)

    if durations:
        avg_duration = sum(durations) / len(durations)
        print(f"   • Average Signal Duration: {avg_duration:.2f} hours")
        print(f"   • Longest Signal Duration: {max(durations):.2f} hours")
        print(f"   • Shortest Signal Duration: {min(durations):.2f} hours")

    # Signals that reached TP3
    tp3_count = sum(1 for s in signals.values() if s["tp_reached"] == 3)
    closed_count = sum(1 for s in signals.values() if s["tp_reached"] == "closed")
    print(f"   • Signals Reached TP3: {tp3_count}")
    print(f"   • Signals Closed: {closed_count}")

    await client.disconnect()

    return {
        "total_signals": len(signals),
        "max_concurrent": max_concurrent,
        "max_capital": max_capital,
        "max_concurrent_time": max_concurrent_time,
        "max_concurrent_signals": max_concurrent_signals,
    }


if __name__ == "__main__":
    print("🚀 Starting concurrent signals analysis...")
    result = asyncio.run(analyze_concurrent_signals())
    print("\n✅ Analysis completed!")
