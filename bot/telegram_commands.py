import asyncio
from telethon import events
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
            "📄 Transactions: /transactions\n"
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

            msg = "✅ Closed positions:\n\n"
            for r in results:
                msg += f"{r['symbol']} | {r['side']} | {r['size']}\n"

            await event.respond(msg)

        except Exception as e:
            await event.respond(f"❌ Error closing positions: {e}")

    @telClient.on(events.NewMessage(pattern=r"^/transactions$"))
    async def transactions_handler(event):
        try:
            res = get_transaction_log(limit=30)
            if isinstance(res, dict):
                results = res.get("result", {}).get("list", [])
            else:
                results = []

            if not results:
                await event.respond("📌 No transactions found.")
                return

            # Sort by transaction time (newest first)
            results.sort(key=lambda x: int(x.get("transactionTime", 0)), reverse=True)

            # Send transactions one by one to avoid message length limits
            for idx, tx in enumerate(results, start=1):
                cash_flow = float(tx.get("cashFlow", 0))
                funding = float(tx.get("funding", 0))
                fee = float(tx.get("fee", 0))
                change = float(tx.get("change", 0))

                tx_msg = (
                    f"📄 **Transaction #{idx}**\n\n"
                    "```\n"
                    f"Symbol: {tx.get('symbol')}\n"
                    f"Type: {tx.get('type')}\n"
                    f"Side: {tx.get('side')}\n"
                    f"Qty: {tx.get('qty')}\n"
                    f"Price: {tx.get('tradePrice')}\n"
                    f"Cash Flow: {cash_flow}\n"
                    f"Funding: {funding}\n"
                    f"Fee: {fee}\n"
                    f"Change: {change}\n"
                    f"Balance After: {tx.get('cashBalance')}\n"
                    f"Order ID: {tx.get('orderId')}\n"
                    f"Trade ID: {tx.get('tradeId')}\n"
                    f"Time: {tx.get('transactionTime')}\n"
                    "```"
                )

                await event.respond(tx_msg)
                # Small delay to avoid flood limits
                await asyncio.sleep(0.2)

        except Exception as e:
            await event.respond(f"❌ Error getting transactions: {e}")
