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
            balance = get_wallet_balance()

            msg = "💰 **Wallet Balance**\n\n"

            for coin in balance.get("result", {}).get("list", []):
                msg += (
                    f"{coin.get('coin','-')} | "
                    f"Available: {coin.get('availableToWithdraw','0')} | "
                    f"Equity: {coin.get('equity','0')}\n"
                )

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
