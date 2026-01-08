import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from telethon import events
from telethon.errors import FloodWaitError
from clients import telClient
from logger import log_print, LOGS_DATA_FILE


from api import (
    get_wallet_balance,
    cancel_all_orders,
    get_positions,
    get_pending_orders,
    get_closed_pnl,
    close_all_positions,
    close_position_by_symbol,
    get_account_info,
    get_transaction_log,
    set_trading_stop,
    amend_order,
    get_sl_order_id,
)
from cache import (
    remove_open_position,
    remove_position_entry_time,
    remove_position_tp_prices,
    remove_pending_sl_update,
    refresh_transaction_log,
)
from capital_tracker import get_capital_report
from liquidity_analyzer import get_liquidity_report, analyze_symbol_liquidity
from ws_message_formatter import debug_redis_data


def safe_float(value, default=0.0):
    """Safely convert value to float, handling empty strings and None."""
    if value is None or value == "" or value == "-":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def format_timestamp(timestamp_str):
    """Format timestamp (milliseconds) to readable date/time."""
    if not timestamp_str or timestamp_str == "" or timestamp_str == "-":
        return "-"
    try:
        timestamp_ms = int(timestamp_str)
        timestamp_s = timestamp_ms / 1000.0
        dt_utc = datetime.fromtimestamp(timestamp_s, tz=ZoneInfo("UTC"))
        dt_iran = dt_utc.astimezone(ZoneInfo("Asia/Tehran"))
        return dt_iran.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OSError):
        return timestamp_str


# Global flag to cancel transaction sending
cancel_transaction_sending = False


def register_command_handlers():

    # ---------- /start ----------
    @telClient.on(events.NewMessage(pattern=r"^/start$"))
    async def start_handler(event):
        message = (
            "📌 Welcome! Choose an action:\n\n"
            "📊 Positions: /positions\n"
            "👤 Account Info: /account\n"
            "💰 Wallet Balance: /wallet\n"
            "🛑 Cancel Orders: /cancel\n"
            "❌ Close Positions: /close_positions\n"
            "🔴 Close Symbol: /close SYMBOL\n"
            "   Example: /close BTCUSDT\n"
            "📄 Capital Report: /capital_report\n"
            "📄 Transactions: /transactions [limit] or [start_date] [end_date] [limit]\n"
            "   Example: /transactions 100 or /transactions 2025-01-05 2025-01-06\n"
            "🛑 Cancel Waiting: /cancel_waiting\n"
            "📊 Liquidity Report: /liquidity_report\n"
            "📋 Logs: /logs SYMBOL START_DATE [START_TIME] [END_DATE] [END_TIME]\n"
            "   Example: /logs BTCUSDT 2025-01-05 08:00 20:00\n"
            "🔍 Redis Data: /debug_redis\n"
            "✏️ Amend TP/SL: /amend SYMBOL sl=VALUE tp=VALUE\n"
            "   Example: /amend BTCUSDT sl=50000 tp=52000\n"
            "🧹 Clear Position Cache: /clear_position SYMBOL\n"
            "   Example: /clear_position BTCUSDT\n"
            "🧹 Clear Schedule Cache: /clear_schedule SYMBOL\n"
            "   Example: /clear_schedule BTCUSDT\n"
            "🧹 Clear All Cache: /clear_all SYMBOL\n"
            "   Example: /clear_all BTCUSDT\n"
        )
        await event.respond(message)

    # ---------- /positions ----------
    @telClient.on(events.NewMessage(pattern=r"^/positions$"))
    async def positions_handler(event):
        try:
            # Helper function to format prices with appropriate decimal places
            def format_price(price_str, default="-"):
                if (
                    not price_str
                    or price_str == ""
                    or price_str == "0"
                    or price_str == "0.00"
                ):
                    return default
                try:
                    price = float(price_str)
                    if price == 0:
                        return default
                    # Determine decimal places based on price magnitude
                    if price >= 1000:
                        return f"{price:,.2f}"
                    elif price >= 1:
                        return f"{price:,.4f}"
                    else:
                        return f"{price:,.6f}"
                except (ValueError, TypeError):
                    return default

            msg = "📊 **Open Positions:**\n\n"

            # Get pending orders first (needed for TP extraction in Partial TP mode)
            pending = get_pending_orders(settleCoin="USDT")

            positions = get_positions(settleCoin="USDT")
            if not positions:
                msg += "No open positions.\n"
            else:
                # Count valid positions first
                valid_positions = [
                    p for p in positions if safe_float(p.get("size", 0)) > 0
                ]
                position_count = 0

                for p in valid_positions:
                    position_count += 1

                    size = safe_float(p.get("size", 0))
                    symbol = p.get("symbol", "-")
                    side = p.get("side", "-")
                    avg_price = safe_float(p.get("avgPrice", 0))
                    mark_price = safe_float(p.get("markPrice", 0))
                    unrealised_pnl = safe_float(p.get("unrealisedPnl", 0))
                    leverage = p.get("leverage", "-")
                    liq_price = p.get("liqPrice", "")
                    take_profit = p.get("takeProfit", "")
                    stop_loss = p.get("stopLoss", "")
                    created_time = p.get("createdTime", "")
                    position_value = safe_float(p.get("positionValue", 0))

                    # Format timestamp
                    created_time_str = format_timestamp(created_time)

                    # Format size
                    size_str = f"{size:,.4f}" if size > 0 else "-"

                    # Format entry price
                    entry_str = format_price(str(avg_price)) if avg_price > 0 else "-"

                    # Format mark price
                    mark_str = format_price(str(mark_price)) if mark_price > 0 else "-"

                    # Format TP - Check pending orders for Partial TP
                    tp_str = format_price(take_profit) if take_profit else "-"

                    # If TP is empty, try to get from pending orders (Partial TP mode)
                    if not take_profit or take_profit == "" or take_profit == "0":
                        # Get pending orders for this symbol
                        symbol_pending_orders = [
                            o
                            for o in pending
                            if o.get("symbol") == symbol
                            and o.get("stopOrderType") == "PartialTakeProfit"
                        ]

                        if symbol_pending_orders:
                            # Extract trigger prices and sort them
                            tp_prices = []
                            for tp_order in symbol_pending_orders:
                                trigger = tp_order.get("trigger_price") or tp_order.get(
                                    "triggerPrice"
                                )
                                if trigger and trigger != "-" and trigger != "0":
                                    try:
                                        tp_prices.append(float(trigger))
                                    except (ValueError, TypeError):
                                        pass

                            if tp_prices:
                                # Sort TP prices (ascending for Buy, descending for Sell)
                                tp_prices.sort(reverse=(side == "Sell"))
                                # Format as "TP1 / TP2" or "TP1, TP2, TP3"
                                tp_str = " / ".join(
                                    [format_price(str(tp)) for tp in tp_prices]
                                )

                    # Format SL
                    sl_str = format_price(stop_loss) if stop_loss else "-"

                    # Format Liq price
                    liq_str = format_price(liq_price) if liq_price else "-"

                    # Format PnL
                    pnl_emoji = (
                        "🟢"
                        if unrealised_pnl > 0
                        else "🔴" if unrealised_pnl < 0 else "⚪"
                    )
                    pnl_str = (
                        f"{unrealised_pnl:,.2f}" if unrealised_pnl != 0 else "0.00"
                    )

                    # Format position value
                    value_str = f"{position_value:,.2f}" if position_value > 0 else "-"

                    # Build position message
                    msg += (
                        f"**{symbol}** ({side})\n"
                        f"Size: {size_str}\n"
                        f"Entry: {entry_str}\n"
                        f"Mark: {mark_str}\n"
                        f"TP: {tp_str}\n"
                        f"SL: {sl_str}\n"
                        f"Liq: {liq_str}\n"
                        f"Leverage: {leverage}x\n"
                        f"Value: {value_str} USDT\n"
                        f"{pnl_emoji} PnL: {pnl_str} USDT\n"
                        f"Time: {created_time_str}\n"
                    )

                    # Add separator between positions (except for the last one)
                    if position_count < len(valid_positions):
                        msg += "─────────────────────\n"

            msg += "\n\=============================\n"
            msg += "⏳ **Pending Orders:**\n"
            if not pending:
                msg += "No pending orders.\n"
            else:
                order_count = 0
                for o in pending:
                    order_count += 1
                    symbol = o.get("symbol", "-")
                    side = o.get("side", "-")
                    qty = safe_float(o.get("qty", 0))
                    price = o.get("price", "-")
                    trigger_price = o.get("trigger_price", "-")
                    order_type = o.get("orderType", "-")
                    stop_order_type = o.get("stopOrderType", "-")

                    # Format qty
                    qty_str = f"{qty:,.4f}" if qty > 0 else "-"

                    # Format price
                    price_str = (
                        format_price(price)
                        if price and price != "-" and price != "0"
                        else "-"
                    )

                    # Format trigger price
                    trigger_str = (
                        format_price(trigger_price)
                        if trigger_price and trigger_price != "-"
                        else "-"
                    )

                    # Determine order type display
                    order_type_display = (
                        stop_order_type
                        if stop_order_type and stop_order_type != "-"
                        else order_type
                    )

                    msg += (
                        f"**{symbol}** ({side})\n"
                        f"Type: {order_type_display}\n"
                        f"Qty: {qty_str}\n"
                        f"Price: {price_str}\n"
                        f"Trigger: {trigger_str}\n"
                    )

                    # Add separator between orders (except for the last one)
                    if order_count < len(pending):
                        msg += "─────────────────────\n\n"

            pnl = get_closed_pnl()
            msg += "\n✅ **Closed PnL:**\n\n"
            if not pnl:
                msg += "No closed PnL.\n"
            else:
                for p in pnl[:10]:
                    closed_pnl = safe_float(p.get("closedPnl", 0))
                    symbol = p.get("symbol", "-")
                    if closed_pnl == 0:
                        continue  # Skip zero PnL entries
                    emoji = "🟢" if closed_pnl > 0 else "🔴"
                    msg += f"{emoji} {symbol} | {closed_pnl:,.2f}\n"

            await event.respond(msg)

        except Exception as e:
            await event.respond(f"❌ Error: {e}")

    # ---------- /account ----------
    @telClient.on(events.NewMessage(pattern=r"^/account$"))
    async def account_handler(event):
        try:
            info = get_account_info()

            msg = (
                "👤 **Account Info**\n\n"
                f"UID: {info.get('uid','-')}\n"
                f"Account Type: {info.get('accountType','-')}\n"
                f"Status: {info.get('status','-')}\n"
            )

            await event.respond(msg)

        except Exception as e:
            await event.respond(f"❌ Error getting account info: {e}")

    # ---------- /wallet ----------
    @telClient.on(events.NewMessage(pattern=r"^/wallet$"))
    async def wallet_handler(event):
        try:
            data = get_wallet_balance()

            coins = data.get("result", {}).get("list", [])
            if not coins:
                await event.respond("💰 Wallet data not found.")
                return

            coins = coins[0].get("coin", [])
            if not coins:
                await event.respond("💰 Wallet is empty.")
                return

            msg = "💰 **Wallet Balance**\n\n"

            for c in coins:
                symbol = c.get("coin")
                equity = float(c.get("equity", 0))
                wallet = float(c.get("walletBalance", 0))
                usd_value = float(c.get("usdValue", 0))
                pnl = float(c.get("cumRealisedPnl", 0))

                if equity == 0 and wallet == 0:
                    continue

                msg += f"🪙 **{symbol}**\n"

                if wallet:
                    msg += f"Wallet: {wallet:,.4f}\n"
                if equity:
                    msg += f"Equity: {equity:,.4f}\n"
                if usd_value:
                    msg += f"USD Value: {usd_value:,.2f}\n"
                if pnl:
                    emoji = "🟢" if pnl > 0 else "🔴"
                    msg += f"{emoji} PnL: {pnl:,.2f}\n"

                msg += "\n"

            await event.respond(msg)

        except Exception as e:
            await event.respond(f"❌ Error getting wallet balance: {e}")

    # ---------- /cancel ----------
    @telClient.on(events.NewMessage(pattern=r"^/cancel$"))
    async def cancel_handler(event):
        try:
            cancel_all_orders(settleCoin="USDT")
            await event.respond("🛑 All USDT orders cancelled")
        except Exception as e:
            await event.respond(f"❌ Error cancelling orders: {e}")

    # ---------- /close_positions ----------
    @telClient.on(events.NewMessage(pattern=r"^/close_positions$"))
    async def close_positions_handler(event):
        try:
            results = close_all_positions(settleCoin="USDT")
            if not results:
                await event.respond("📌 No open positions to close.")
                return

            # Remove closed positions from open_positions
            closed_symbols = [r["symbol"] for r in results]
            for symbol in closed_symbols:
                await remove_open_position(symbol)

            # Update transaction log cache
            try:
                await refresh_transaction_log()
            except Exception as cache_error:
                print(f"[WARN] Failed to refresh transaction log cache: {cache_error}")

            msg = "✅ Closed positions:\n\n"
            for r in results:
                msg += f"{r['symbol']} | {r['side']} | {r['size']}\n"

            msg += f"\n🔄 Cache updated. Removed {len(closed_symbols)} symbol(s) from open positions."

            await event.respond(msg)

        except Exception as e:
            await event.respond(f"❌ Error closing positions: {e}")

    # ---------- /close SYMBOL ----------
    @telClient.on(events.NewMessage(pattern=r"^/close (.+)$"))
    async def close_symbol_handler(event):
        try:
            symbol = event.pattern_match.group(1).strip().upper()

            if not symbol:
                await event.respond(
                    "❌ Please provide a symbol. Example: /close BTCUSDT"
                )
                return

            results = close_position_by_symbol(symbol)

            if not results:
                await event.respond(f"📌 No open positions for {symbol} to close.")
                return

            # Remove closed positions from open_positions
            closed_symbols = [r["symbol"] for r in results]
            for closed_symbol in closed_symbols:
                await remove_open_position(closed_symbol)

            # Update transaction log cache
            try:
                await refresh_transaction_log()
            except Exception as cache_error:
                print(f"[WARN] Failed to refresh transaction log cache: {cache_error}")

            msg = f"✅ Closed positions for {symbol}:\n\n"
            for r in results:
                if "error" in r:
                    msg += f"❌ {r['symbol']} | {r['side']} | {r['size']} | Error: {r['error']}\n"
                else:
                    msg += f"✅ {r['symbol']} | {r['side']} | {r['size']}\n"

            msg += f"\n🔄 Cache updated. Removed {len(closed_symbols)} symbol(s) from open positions."

            await event.respond(msg)

        except Exception as e:
            await event.respond(f"❌ Error closing position: {e}")

    @telClient.on(events.NewMessage(pattern=r"^/transactions(?: (.+))?$"))
    async def transactions_handler(event):
        global cancel_transaction_sending
        cancel_transaction_sending = False  # Reset cancel flag

        try:
            # Parse command arguments: /transactions [start_date] [end_date] [limit]
            # Format: /transactions 2025-01-05 2025-01-06 100
            # Or: /transactions 100 (just limit)
            args = event.pattern_match.group(1)
            start_date = None
            end_date = None
            limit = 50  # Default limit

            if args:
                parts = args.strip().split()
                if len(parts) == 1:
                    # Only limit provided
                    try:
                        limit = int(parts[0])
                    except ValueError:
                        await event.respond(
                            "❌ Invalid format. Use:\n"
                            "`/transactions` - Last 50 transactions\n"
                            "`/transactions 100` - Last 100 transactions\n"
                            "`/transactions 2025-01-05 2025-01-06` - Transactions in date range\n"
                            "`/transactions 2025-01-05 2025-01-06 100` - Transactions in date range with limit"
                        )
                        return
                elif len(parts) == 2:
                    # Start and end date
                    start_date = parts[0]
                    end_date = parts[1]
                elif len(parts) == 3:
                    # Start date, end date, and limit
                    start_date = parts[0]
                    end_date = parts[1]
                    try:
                        limit = int(parts[2])
                    except ValueError:
                        await event.respond("❌ Invalid limit. Must be a number.")
                        return
                else:
                    await event.respond(
                        "❌ Invalid format. Use:\n"
                        "`/transactions` - Last 50 transactions\n"
                        "`/transactions 100` - Last 100 transactions\n"
                        "`/transactions 2025-01-05 2025-01-06` - Transactions in date range\n"
                        "`/transactions 2025-01-05 2025-01-06 100` - Transactions in date range with limit"
                    )
                    return

            # Send initial message
            await event.respond("📄 Fetching transactions...")

            # Prepare API parameters
            start_time_ms = None
            end_time_ms = None

            # Parse date range if provided
            if start_date and end_date:
                try:
                    # Parse dates (assuming format: YYYY-MM-DD)
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(
                        hour=0, minute=0, second=0, tzinfo=ZoneInfo("Asia/Tehran")
                    )
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
                        hour=23, minute=59, second=59, tzinfo=ZoneInfo("Asia/Tehran")
                    )

                    # Convert to UTC for API
                    start_utc = start_dt.astimezone(ZoneInfo("UTC"))
                    end_utc = end_dt.astimezone(ZoneInfo("UTC"))
                    start_time_ms = int(start_utc.timestamp() * 1000)
                    end_time_ms = int(end_utc.timestamp() * 1000)

                    # Check API limit: endTime - startTime <= 7 days
                    days_diff = (end_time_ms - start_time_ms) / (1000 * 60 * 60 * 24)
                    if days_diff > 7:
                        await event.respond(
                            f"❌ Date range exceeds 7 days limit. Maximum allowed: 7 days.\n"
                            f"Your range: {days_diff:.1f} days"
                        )
                        return
                except ValueError as e:
                    await event.respond(
                        f"❌ Invalid date format. Use YYYY-MM-DD format.\nError: {e}"
                    )
                    return
            elif start_date:
                # Only start_date provided - API will return startTime to startTime+24 hours
                try:
                    start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(
                        hour=0, minute=0, second=0, tzinfo=ZoneInfo("Asia/Tehran")
                    )
                    start_utc = start_dt.astimezone(ZoneInfo("UTC"))
                    start_time_ms = int(start_utc.timestamp() * 1000)
                except ValueError as e:
                    await event.respond(
                        f"❌ Invalid date format. Use YYYY-MM-DD format.\nError: {e}"
                    )
                    return
            elif end_date:
                # Only end_date provided - API will return endTime-24 hours to endTime
                try:
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
                        hour=23, minute=59, second=59, tzinfo=ZoneInfo("Asia/Tehran")
                    )
                    end_utc = end_dt.astimezone(ZoneInfo("UTC"))
                    end_time_ms = int(end_utc.timestamp() * 1000)
                except ValueError as e:
                    await event.respond(
                        f"❌ Invalid date format. Use YYYY-MM-DD format.\nError: {e}"
                    )
                    return

            # Ensure limit is within API range [1, 50]
            api_limit = min(max(1, limit), 50)

            # Fetch transactions with pagination if needed
            all_results = []
            cursor = None
            max_pages = 10  # Limit pagination to prevent too many requests

            for page in range(max_pages):
                res = get_transaction_log(
                    limit=api_limit,
                    startTime=start_time_ms,
                    endTime=end_time_ms,
                    cursor=cursor,
                )

                if isinstance(res, dict):
                    page_results = res.get("result", {}).get("list", [])
                    all_results.extend(page_results)

                    # Check if there are more pages
                    next_cursor = res.get("result", {}).get("nextPageCursor")
                    if not next_cursor or len(page_results) < api_limit:
                        break
                    cursor = next_cursor
                else:
                    break

                # If we got fewer results than limit, we're done
                if len(page_results) < api_limit:
                    break

            if not all_results:
                await event.respond(
                    "📌 No transactions found for the specified criteria."
                )
                return

            # Sort by transaction time (newest first)
            all_results.sort(
                key=lambda x: int(x.get("transactionTime", 0)), reverse=True
            )

            # Apply user's limit after fetching (in case they want fewer than what we fetched)
            if limit and len(all_results) > limit:
                results = all_results[:limit]
            else:
                results = all_results

            total_count = len(results)
            await event.respond(f"📊 Found {total_count} transaction(s). Sending...")

            # Send transactions one by one with proper error handling
            sent_count = 0
            for idx, tx in enumerate(results, start=1):
                # Check if cancellation was requested
                if cancel_transaction_sending:
                    await event.respond(
                        f"🛑 Sending cancelled by user.\n"
                        f"📊 Sent {sent_count}/{total_count} transactions before cancellation."
                    )
                    cancel_transaction_sending = False  # Reset flag
                    return

                # Prepare message content first
                cash_flow = float(tx.get("cashFlow", 0))
                funding = float(tx.get("funding", 0))
                fee = float(tx.get("fee", 0))
                change = float(tx.get("change", 0))

                # Determine emoji based on positive or negative value
                cash_flow_emoji = (
                    "🟢" if cash_flow > 0 else "🔴" if cash_flow < 0 else "⚪"
                )
                change_emoji = "🟢" if change > 0 else "🔴" if change < 0 else "⚪"

                # Convert transactionTime to Iran timezone (UTC+3:30)
                transaction_time_str = tx.get("transactionTime", "")
                formatted_time = transaction_time_str
                if transaction_time_str:
                    try:
                        # transactionTime is in milliseconds
                        timestamp_ms = int(transaction_time_str)
                        timestamp_s = timestamp_ms / 1000.0
                        dt_utc = datetime.fromtimestamp(timestamp_s, tz=ZoneInfo("UTC"))
                        dt_iran = dt_utc.astimezone(ZoneInfo("Asia/Tehran"))
                        formatted_time = dt_iran.strftime(
                            "%Y-%m-%d %H:%M:%S (UTC+3:30)"
                        )
                    except (ValueError, TypeError, OSError) as e:
                        # If conversion fails, use original value
                        formatted_time = transaction_time_str
                        log_print(f"[WARN] Failed to convert transactionTime: {e}")

                tx_msg = (
                    f"📄 **Transaction #{idx}/{total_count}**\n\n"
                    "```\n"
                    f"Symbol: {tx.get('symbol')}\n"
                    f"Type: {tx.get('type')}\n"
                    f"Side: {tx.get('side')}\n"
                    f"Qty: {tx.get('qty')}\n"
                    f"Price: {tx.get('tradePrice')}\n"
                    f"{cash_flow_emoji} Cash Flow (PNL): {cash_flow}\n"
                    f"Funding: {funding}\n"
                    f"Fee: {fee}\n"
                    f"{change_emoji} Change: {change}\n"
                    f"Balance After: {tx.get('cashBalance')}\n"
                    f"Order ID: {tx.get('orderId')}\n"
                    f"Trade ID: {tx.get('tradeId')}\n"
                    f"Time: {formatted_time}\n"
                    "```"
                )

                # Try to send with retry logic
                max_retries = 3
                retry_count = 0
                sent = False

                while retry_count < max_retries and not sent:
                    try:
                        await event.respond(tx_msg)
                        sent_count += 1
                        sent = True

                        # Increased delay to avoid flood limits (2.5 seconds between messages)
                        await asyncio.sleep(2.5)

                    except FloodWaitError as e:
                        # If we hit a flood wait, wait for the required time + buffer
                        wait_time = e.seconds + 2
                        log_print(
                            f"[WARN] Flood wait detected for transaction {idx}. Waiting {wait_time} seconds..."
                        )
                        if retry_count == 0:
                            await event.respond(
                                f"⏳ Rate limit reached. Waiting {wait_time} seconds before continuing..."
                            )
                        await asyncio.sleep(wait_time)
                        retry_count += 1

                    except Exception as tx_error:
                        log_print(
                            f"[ERROR] Error sending transaction {idx} (attempt {retry_count + 1}): {tx_error}"
                        )
                        retry_count += 1
                        if retry_count < max_retries:
                            await asyncio.sleep(2.5)
                        else:
                            await event.respond(
                                f"⚠️ Failed to send transaction #{idx} after {max_retries} attempts. Skipping..."
                            )
                            await asyncio.sleep(2.5)
                            break

            # Send completion message
            if not cancel_transaction_sending:
                await event.respond(
                    f"✅ Completed! Sent {sent_count}/{total_count} transactions."
                )
            cancel_transaction_sending = False  # Reset flag

        except Exception as e:
            await event.respond(f"❌ Error getting transactions: {e}")
            cancel_transaction_sending = False  # Reset flag on error

    # ---------- /cancel_waiting ----------
    @telClient.on(events.NewMessage(pattern=r"^/cancel_waiting$"))
    async def cancel_waiting_handler(event):
        global cancel_transaction_sending
        cancel_transaction_sending = True
        await event.respond(
            "🛑 Cancellation requested. Transaction sending will stop after current message."
        )

    # ---------- /capital_report ----------
    @telClient.on(events.NewMessage(pattern=r"^/capital_report$"))
    async def capital_report_handler(event):
        try:
            report = get_capital_report()
            await event.respond(report)
        except Exception as e:
            await event.respond(f"❌ Error generating capital report: {e}")

    # ---------- /liquidity_report ----------
    @telClient.on(events.NewMessage(pattern=r"^/liquidity_report$"))
    async def liquidity_report_handler(event):
        try:
            report = get_liquidity_report()
            await event.respond(report)
        except Exception as e:
            await event.respond(f"❌ Error generating liquidity report: {e}")

    # ---------- /logs ----------
    @telClient.on(events.NewMessage(pattern=r"^/logs(?: (.+))?$"))
    async def logs_handler(event):
        try:
            import json
            import os

            # Parse command arguments: /logs [symbol] [start_date] [start_time] [end_date] [end_time]
            # Format: /logs BTCUSDT 2025-01-05 08:00 2025-01-05 20:00
            # Or: /logs BTCUSDT 2025-01-05 (all day)
            args = event.pattern_match.group(1)

            if not args:
                await event.respond(
                    "❌ Please provide symbol and date range.\n\n"
                    "**Usage:**\n"
                    "`/logs SYMBOL START_DATE [START_TIME] [END_DATE] [END_TIME]`\n\n"
                    "**Examples:**\n"
                    "`/logs BTCUSDT 2025-01-05` - All logs for BTCUSDT on 2025-01-05\n"
                    "`/logs BTCUSDT 2025-01-05 08:00 20:00` - Logs from 08:00 to 20:00 on 2025-01-05\n"
                    "`/logs BTCUSDT 2025-01-05 08:00 2025-01-06 20:00` - Logs from 2025-01-05 08:00 to 2025-01-06 20:00"
                )
                return

            parts = args.strip().split()
            if len(parts) < 2:
                await event.respond(
                    "❌ Invalid format. Please provide at least symbol and start date.\n\n"
                    "**Usage:**\n"
                    "`/logs SYMBOL START_DATE [START_TIME] [END_DATE] [END_TIME]`"
                )
                return

            symbol = parts[0].upper()
            start_date = parts[1]
            start_time = parts[2] if len(parts) > 2 else "00:00"
            end_date = parts[3] if len(parts) > 3 else start_date
            end_time = parts[4] if len(parts) > 4 else "23:59"

            # Parse dates and times
            try:
                start_dt = datetime.strptime(
                    f"{start_date} {start_time}", "%Y-%m-%d %H:%M"
                ).replace(tzinfo=ZoneInfo("Asia/Tehran"))
                end_dt = datetime.strptime(
                    f"{end_date} {end_time}", "%Y-%m-%d %H:%M"
                ).replace(tzinfo=ZoneInfo("Asia/Tehran"))
            except ValueError as e:
                await event.respond(
                    f"❌ Invalid date/time format. Use YYYY-MM-DD and HH:MM format.\nError: {e}"
                )
                return

            if start_dt > end_dt:
                await event.respond("❌ Start date/time must be before end date/time.")
                return

            # Read logs from file
            if not os.path.exists(LOGS_DATA_FILE):
                await event.respond("❌ Log file not found. No logs available yet.")
                return

            try:
                with open(LOGS_DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                await event.respond(f"❌ Error reading log file: {e}")
                return

            logs = data.get("logs", [])
            if not logs:
                await event.respond("📌 No logs found in file.")
                return

            # Filter logs by symbol and time range
            filtered_logs = []
            for log_entry in logs:
                # Check if symbol is in message
                message = log_entry.get("message", "").upper()
                if symbol not in message:
                    continue

                # Check timestamp
                timestamp_str = log_entry.get("timestamp", "")
                if not timestamp_str:
                    continue

                try:
                    log_dt = datetime.fromisoformat(timestamp_str)
                    if log_dt.tzinfo is None:
                        # Assume Asia/Tehran if no timezone
                        log_dt = log_dt.replace(tzinfo=ZoneInfo("Asia/Tehran"))
                    else:
                        # Convert to Asia/Tehran
                        log_dt = log_dt.astimezone(ZoneInfo("Asia/Tehran"))

                    if start_dt <= log_dt <= end_dt:
                        filtered_logs.append(log_entry)
                except (ValueError, TypeError) as e:
                    # Skip invalid timestamps
                    continue

            if not filtered_logs:
                await event.respond(
                    f"📌 No logs found for {symbol} between {start_date} {start_time} and {end_date} {end_time}."
                )
                return

            # Sort by timestamp (oldest first)
            filtered_logs.sort(key=lambda x: x.get("timestamp", ""))

            total_count = len(filtered_logs)
            await event.respond(
                f"📋 Found {total_count} log entries for {symbol}.\n"
                f"📅 Period: {start_date} {start_time} to {end_date} {end_time}\n"
                f"Sending logs..."
            )

            # Send logs in batches (group by 10 to avoid too many messages)
            batch_size = 10
            sent_count = 0

            for i in range(0, total_count, batch_size):
                batch = filtered_logs[i : i + batch_size]
                log_messages = []

                for log_entry in batch:
                    timestamp = log_entry.get("timestamp", "")
                    level = log_entry.get("level", "INFO")
                    message = log_entry.get("message", "")

                    # Format timestamp for display
                    try:
                        log_dt = datetime.fromisoformat(timestamp)
                        if log_dt.tzinfo is None:
                            log_dt = log_dt.replace(tzinfo=ZoneInfo("Asia/Tehran"))
                        else:
                            log_dt = log_dt.astimezone(ZoneInfo("Asia/Tehran"))
                        formatted_time = log_dt.strftime("%Y-%m-%d %H:%M:%S")
                    except (ValueError, TypeError):
                        formatted_time = timestamp

                    # Level emoji
                    level_emoji = {
                        "ERROR": "🔴",
                        "WARN": "⚠️",
                        "INFO": "ℹ️",
                        "DEBUG": "🔍",
                    }.get(level, "ℹ️")

                    log_messages.append(
                        f"{level_emoji} [{formatted_time}] {level}\n{message}"
                    )

                log_text = "\n\n".join(log_messages)
                log_text = f"📋 **Logs for {symbol}** ({i+1}-{min(i+batch_size, total_count)}/{total_count})\n\n```\n{log_text}\n```"

                try:
                    await event.respond(log_text)
                    sent_count += len(batch)
                    await asyncio.sleep(1)  # Small delay to avoid rate limits
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds + 2)
                    await event.respond(log_text)
                    sent_count += len(batch)
                except Exception as e:
                    log_print(f"[ERROR] Error sending log batch: {e}")
                    continue

            await event.respond(
                f"✅ Completed! Sent {sent_count}/{total_count} log entries for {symbol}."
            )

        except Exception as e:
            await event.respond(f"❌ Error retrieving logs: {e}")
            log_print(f"[ERROR] Error in logs_handler: {e}")
            import traceback

            traceback.print_exc()

    # ---------- /debug_redis ----------
    @telClient.on(events.NewMessage(pattern=r"^/debug_redis$"))
    async def debug_redis_handler(event):
        """
        Display all data related to open positions and SL schedules from Redis.
        """
        try:
            await event.respond("⏳ Fetching Redis data...")

            result = await debug_redis_data()

            # Telegram has a message length limit (4096 characters)
            # Split into chunks if needed
            max_length = 4000  # Leave some margin

            if len(result) <= max_length:
                await event.respond(f"```\n{result}\n```")
            else:
                # Split into chunks
                lines = result.split("\n")
                current_chunk = []
                current_length = 0
                chunk_num = 1
                total_chunks = (len(result) // max_length) + 1

                for line in lines:
                    line_length = len(line) + 1  # +1 for newline

                    if current_length + line_length > max_length:
                        # Send current chunk
                        chunk_text = "\n".join(current_chunk)
                        await event.respond(
                            f"```\n{chunk_text}\n```\n"
                            f"📄 Part {chunk_num}/{total_chunks}"
                        )
                        chunk_num += 1
                        current_chunk = [line]
                        current_length = line_length
                    else:
                        current_chunk.append(line)
                        current_length += line_length

                # Send remaining chunk
                if current_chunk:
                    chunk_text = "\n".join(current_chunk)
                    await event.respond(
                        f"```\n{chunk_text}\n```\n"
                        f"📄 Part {chunk_num}/{total_chunks}"
                    )

            log_print("[INFO] Redis debug data sent successfully")

        except Exception as e:
            error_msg = f"❌ Error fetching Redis data: {e}"
            await event.respond(error_msg)
            log_print(f"[ERROR] Error in debug_redis_handler: {e}")
            import traceback

            traceback.print_exc()

    # ---------- /clear_position ----------
    @telClient.on(events.NewMessage(pattern=r"^/clear_position\s+([A-Za-z0-9]+)$"))
    async def clear_position_handler(event):
        """
        Clear position data from Redis:
        - open_positions
        - position_entry_time
        - position_tp_prices
        """
        try:
            symbol = event.pattern_match.group(1).upper()
            await remove_open_position(symbol)
            await remove_position_entry_time(symbol)
            await remove_position_tp_prices(symbol)
            await event.respond(
                f"🧹 Position data cleared for {symbol} (open_positions, entry_time, tp_prices)."
            )
        except Exception as e:
            await event.respond(f"❌ Error clearing position data: {e}")

    # ---------- /clear_schedule ----------
    @telClient.on(events.NewMessage(pattern=r"^/clear_schedule\s+([A-Za-z0-9]+)$"))
    async def clear_schedule_handler(event):
        """
        Clear pending SL schedules (pending_sl_update) from Redis.
        """
        try:
            symbol = event.pattern_match.group(1).upper()
            await remove_pending_sl_update(symbol)
            await event.respond(
                f"🧹 Pending SL schedule cleared for {symbol} (pending_sl_update)."
            )
        except Exception as e:
            await event.respond(f"❌ Error clearing pending schedule: {e}")

    # ---------- /clear_all ----------
    @telClient.on(events.NewMessage(pattern=r"^/clear_all\s+([A-Za-z0-9]+)$"))
    async def clear_all_handler(event):
        """
        Clear both position data and SL schedule for a symbol simultaneously.
        """
        try:
            symbol = event.pattern_match.group(1).upper()
            await remove_open_position(symbol)
            await remove_position_entry_time(symbol)
            await remove_position_tp_prices(symbol)
            await remove_pending_sl_update(symbol)
            await event.respond(
                f"🧹 All cached data cleared for {symbol} "
                "(open_positions, entry_time, tp_prices, pending_sl_update)."
            )
        except Exception as e:
            await event.respond(f"❌ Error clearing all cached data: {e}")

    # ---------- /amend ----------
    @telClient.on(events.NewMessage(pattern=r"^/amend(?: (.+))?$"))
    async def amend_handler(event):
        """
        Update SL/TP for an open position or its TP/SL orders.

        Usage examples:
        - /amend BTCUSDT sl=50000
        - /amend BTCUSDT tp=52000
        - /amend BTCUSDT sl=50000 tp=52000

        Notes:
        - Works on the CURRENT open position (one-way mode, positionIdx=0).
        - Uses set_trading_stop for full-position TP/SL updates.
        """
        try:
            args = event.pattern_match.group(1)
            if not args:
                await event.respond(
                    "❌ Please provide symbol and new SL/TP values.\n\n"
                    "**Format:**\n"
                    "`/amend SYMBOL sl=VALUE tp=VALUE`\n\n"
                    "**Examples:**\n"
                    "`/amend BTCUSDT sl=50000`\n"
                    "`/amend BTCUSDT tp=52000`\n"
                    "`/amend BTCUSDT sl=50000 tp=52000`"
                )
                return

            parts = args.strip().split()
            if len(parts) < 2:
                await event.respond(
                    "❌ Invalid format.\n"
                    "**Correct format:** `/amend SYMBOL sl=VALUE tp=VALUE`"
                )
                return

            symbol = parts[0].upper()
            sl_value = None
            tp_value = None

            for p in parts[1:]:
                if "=" not in p:
                    continue
                key, val = p.split("=", 1)
                key = key.lower().strip()
                val = val.strip()
                if not val:
                    continue
                try:
                    fval = float(val)
                except ValueError:
                    await event.respond(f"❌ Invalid value for `{key}`: `{val}`")
                    return

                if key in ["sl", "stoploss", "stop_loss"]:
                    sl_value = fval
                elif key in ["tp", "takeprofit", "take_profit"]:
                    tp_value = fval

            if sl_value is None and tp_value is None:
                await event.respond(
                    "❌ No valid SL or TP value found.\n"
                    "Example: `/amend BTCUSDT sl=50000 tp=52000`"
                )
                return

            # Get current position to know size and side
            positions = get_positions(symbol=symbol)
            position = None
            for p in positions:
                size = safe_float(p.get("size", 0))
                if size > 0:
                    position = p
                    break

            if not position:
                await event.respond(f"❌ No open position found for {symbol}.")
                return

            size = safe_float(position.get("size", 0))
            side = position.get("side", "-")

            # Use set_trading_stop to update full-position TP/SL
            kwargs = {}
            if tp_value is not None:
                kwargs["tp"] = tp_value
            if sl_value is not None:
                kwargs["sl"] = sl_value

            set_trading_stop(
                symbol=symbol,
                positionIdx=0,
                tpslMode="Full",
                tpSize=size if tp_value is not None else None,
                slSize=size if sl_value is not None else None,
                **kwargs,
            )

            msg = (
                f"✅ **Amend Sent**\n\n"
                f"```\n"
                f"Symbol: {symbol}\n"
                f"Side: {side}\n"
                f"Size: {size}\n"
            )
            if sl_value is not None:
                msg += f"New SL: {sl_value}\n"
            if tp_value is not None:
                msg += f"New TP: {tp_value}\n"
            msg += "```\n"

            await event.respond(msg)

        except Exception as e:
            await event.respond(f"❌ Error in /amend: {e}")
            log_print(f"[ERROR] Error in amend_handler: {e}")
            import traceback

            traceback.print_exc()
