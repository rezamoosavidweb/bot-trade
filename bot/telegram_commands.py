import asyncio
from telethon import events
from telethon.errors import FloodWaitError
from clients import telClient
from api import (
    get_wallet_balance,
    cancel_all_orders,
    get_positions,
    get_pending_orders,
    get_closed_pnl,
    close_all_positions,
    get_account_info,
    get_transaction_log,
)
from config import open_positions
from cache import refresh_transaction_log
from capital_tracker import get_capital_report

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
            "📄 Capital Report: /capital_report\n"
            "📄 Transactions: /transactions\n"
            "🛑 Cancel Waiting: /cancel_waiting\n"
        )
        await event.respond(message)

    # ---------- /positions ----------
    @telClient.on(events.NewMessage(pattern=r"^/positions$"))
    async def positions_handler(event):
        try:
            msg = "📊 **Open Positions:**\n\n"

            positions = get_positions(settleCoin="USDT")
            if not positions:
                msg += "No open positions.\n"
            else:
                for p in positions:
                    msg += (
                        f"Symbol: {p.get('symbol','-')}\n"
                        f"Side: {p.get('side','-')}\n"
                        f"Size: {p.get('size',0)}\n"
                        f"Entry: {p.get('entry_price',0)}\n"
                        f"PnL: {p.get('unrealized_pnl',0)}\n"
                        f"Liq: {p.get('liq_price','-')}\n"
                        "----------------------\n"
                    )

            pending = get_pending_orders(settleCoin="USDT")
            msg += "\n⏳ **Pending Orders:**\n\n"
            if not pending:
                msg += "No pending orders.\n"
            else:
                for o in pending:
                    msg += (
                        f"{o.get('symbol','-')} | {o.get('side','-')} | {o.get('qty',0)}\n"
                        f"Price: {o.get('price','-')} | Trigger: {o.get('trigger_price','-')}\n"
                        "----------------------\n"
                    )

            pnl = get_closed_pnl()
            msg += "\n✅ **Closed PnL:**\n\n"
            if not pnl:
                msg += "No closed PnL.\n"
            else:
                for p in pnl[:10]:
                    emoji = "🟢" if p.get("closed_pnl", 0) > 0 else "🔴"
                    msg += f"{emoji} {p.get('symbol','-')} | {p.get('closed_pnl',0)}\n"

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
                open_positions.discard(symbol)

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

    @telClient.on(events.NewMessage(pattern=r"^/transactions$"))
    async def transactions_handler(event):
        global cancel_transaction_sending
        cancel_transaction_sending = False  # Reset cancel flag

        try:
            # Send initial message
            await event.respond("📄 Fetching transactions...")

            res = get_transaction_log(limit=50)
            if isinstance(res, dict):
                results = res.get("result", {}).get("list", [])
            else:
                results = []
            if not results:
                await event.respond("📌 No transactions found.")
                return

            total_count = len(results)
            await event.respond(f"📊 Found {total_count} transactions. Sending...")

            # Sort by transaction time (newest first)
            results.sort(key=lambda x: int(x.get("transactionTime", 0)), reverse=True)

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
                    f"Time: {tx.get('transactionTime')}\n"
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
                        print(
                            f"[WARN] Flood wait detected for transaction {idx}. Waiting {wait_time} seconds..."
                        )
                        if retry_count == 0:
                            await event.respond(
                                f"⏳ Rate limit reached. Waiting {wait_time} seconds before continuing..."
                            )
                        await asyncio.sleep(wait_time)
                        retry_count += 1

                    except Exception as tx_error:
                        print(
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
