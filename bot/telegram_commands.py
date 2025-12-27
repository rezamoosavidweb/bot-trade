from telethon import events
from clients import telClient
from api import cancel_all_orders, get_positions, get_pending_orders, get_profit_loos


def register_command_handlers():
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
                        f"Symbol: {p['symbol']}\n"
                        f"Side: {p['side']}\n"
                        f"Size: {p['size']}\n"
                        f"Entry: {p['entry_price']}\n"
                        f"PnL: {p['unrealized_pnl']}\n"
                        f"Liq: {p['liq_price']}\n"
                        "----------------------\n"
                    )

            pending = get_pending_orders()
            msg += "\n⏳ **Pending Orders:**\n\n"
            msg += "No pending orders.\n" if not pending else ""

            for o in pending:
                msg += (
                    f"{o['symbol']} | {o['side']} | {o['qty']}\n"
                    f"Price: {o['price']} | Trigger: {o['trigger_price']}\n"
                    "----------------------\n"
                )

            pnl = get_profit_loos()
            msg += "\n✅ **Closed PnL:**\n\n"

            for p in pnl[:10]:
                emoji = "🟢" if p["closed_pnl"] > 0 else "🔴"
                msg += f"{emoji} {p['symbol']} | {p['closed_pnl']}\n"

            await event.respond(msg)

        except Exception as e:
            await event.respond(f"❌ Error: {e}")

    # ---------- /cancel ----------
    @telClient.on(events.NewMessage(pattern=r"^/cancel$"))
    async def cancel_handler(event):
        cancel_all_orders()
        await event.respond("🛑 All orders cancelled")
