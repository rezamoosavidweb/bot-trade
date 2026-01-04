"""
Delete messages from a Telegram channel within a date range.

Usage:
    python delete_channel_messages.py <channel_username_or_id> [start_date] [end_date]

Examples:
    # Delete all messages from channel
    python delete_channel_messages.py @my_channel

    # Delete messages from specific date range
    python delete_channel_messages.py @my_channel 2024-01-01 2024-01-31

    # Delete from start of channel to specific date
    python delete_channel_messages.py @my_channel None 2024-01-31

    # Delete from specific date to end
    python delete_channel_messages.py @my_channel 2024-01-01 None
"""

import asyncio
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from telethon import TelegramClient
from telethon.errors import FloodWaitError, MessageDeleteForbiddenError
from dotenv import load_dotenv
import os

load_dotenv()

# Telegram credentials
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")

# Timezone
TIMEZONE = ZoneInfo("Asia/Tehran")


def parse_date(date_str: str) -> datetime | None:
    """
    Parse date string to datetime object.

    Supported formats:
    - YYYY-MM-DD
    - YYYY-MM-DD HH:MM:SS
    - None or "None" for no limit
    """
    if not date_str or date_str.lower() == "none":
        return None

    try:
        # Try with time
        if " " in date_str or "T" in date_str:
            if "T" in date_str:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            else:
                dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        else:
            # Date only - set to start of day
            dt = datetime.strptime(date_str, "%Y-%m-%d")

        # Convert to timezone
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TIMEZONE)

        return dt
    except ValueError as e:
        print(f"❌ Error parsing date '{date_str}': {e}")
        print("   Expected format: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS")
        return None


async def delete_messages_in_range(
    client: TelegramClient,
    channel: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
):
    """
    Delete messages from a channel within a date range.

    Args:
        client: Telegram client
        channel: Channel username or ID
        start_date: Start date (None = from beginning)
        end_date: End date (None = to end)
    """
    try:
        # Get channel entity
        print(f"📡 Connecting to channel: {channel}")
        entity = await client.get_entity(channel)
        print(f"✅ Connected to: {entity.title} (@{entity.username or 'N/A'})")

        # Convert dates to timestamps for filtering
        min_id = 0
        max_id = 0

        if start_date:
            print(f"📅 Start date: {start_date.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        else:
            print("📅 Start date: Beginning of channel")

        if end_date:
            print(f"📅 End date: {end_date.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        else:
            print("📅 End date: Latest message")

        print("\n🔍 Scanning messages...")

        # Collect message IDs to delete
        messages_to_delete = []
        total_scanned = 0

        async for message in client.iter_messages(entity):
            total_scanned += 1

            if total_scanned % 100 == 0:
                print(
                    f"   Scanned {total_scanned} messages, found {len(messages_to_delete)} to delete..."
                )

            # Check date range
            msg_date = message.date

            if start_date and msg_date < start_date:
                # Before start date - stop if we're going backwards
                # (messages are iterated newest first)
                continue

            if end_date and msg_date > end_date:
                # After end date - skip
                continue

            # Within range - add to delete list
            messages_to_delete.append(message.id)

        print(f"\n📊 Summary:")
        print(f"   Total messages scanned: {total_scanned}")
        print(f"   Messages to delete: {len(messages_to_delete)}")

        if not messages_to_delete:
            print("✅ No messages to delete in the specified range.")
            return

        # Confirm deletion
        print(f"\n⚠️  WARNING: About to delete {len(messages_to_delete)} messages!")
        confirm = input("   Type 'yes' to confirm: ")

        if confirm.lower() != "yes":
            print("❌ Deletion cancelled.")
            return

        # Delete messages in batches
        print(f"\n🗑️  Deleting messages...")
        deleted_count = 0
        failed_count = 0

        # Delete in batches of 100 (Telegram limit)
        batch_size = 100
        for i in range(0, len(messages_to_delete), batch_size):
            batch = messages_to_delete[i : i + batch_size]

            try:
                await client.delete_messages(entity, batch)
                deleted_count += len(batch)
                print(
                    f"   ✅ Deleted {deleted_count}/{len(messages_to_delete)} messages..."
                )

                # Small delay to avoid rate limits
                await asyncio.sleep(0.5)

            except FloodWaitError as e:
                print(f"   ⏳ Rate limit: Waiting {e.seconds} seconds...")
                await asyncio.sleep(e.seconds)
                # Retry this batch
                try:
                    await client.delete_messages(entity, batch)
                    deleted_count += len(batch)
                    print(
                        f"   ✅ Deleted {deleted_count}/{len(messages_to_delete)} messages..."
                    )
                except Exception as retry_error:
                    print(f"   ❌ Failed to delete batch after retry: {retry_error}")
                    failed_count += len(batch)

            except MessageDeleteForbiddenError:
                print(f"   ⚠️  Some messages cannot be deleted (not admin or too old)")
                failed_count += len(batch)

            except Exception as e:
                print(f"   ❌ Error deleting batch: {e}")
                failed_count += len(batch)

        print(f"\n✅ Deletion complete!")
        print(f"   Deleted: {deleted_count}")
        print(f"   Failed: {failed_count}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


async def main():
    """Main function."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    channel = sys.argv[1]
    start_date_str = sys.argv[2] if len(sys.argv) > 2 else None
    end_date_str = sys.argv[3] if len(sys.argv) > 3 else None

    # Parse dates
    start_date = parse_date(start_date_str) if start_date_str else None
    end_date = parse_date(end_date_str) if end_date_str else None

    if start_date_str and start_date is None:
        print("❌ Invalid start date format")
        sys.exit(1)

    if end_date_str and end_date is None:
        print("❌ Invalid end date format")
        sys.exit(1)

    # Validate date range
    if start_date and end_date and start_date > end_date:
        print("❌ Start date must be before end date")
        sys.exit(1)

    # Create client
    client = TelegramClient("delete_session", TELEGRAM_API_ID, TELEGRAM_API_HASH)

    try:
        await client.start()
        print("✅ Connected to Telegram\n")

        await delete_messages_in_range(client, channel, start_date, end_date)

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        await client.disconnect()
        print("\n👋 Disconnected")


if __name__ == "__main__":
    asyncio.run(main())
