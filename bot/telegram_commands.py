from telethon import events
from clients import telClient
from api import (
    cancel_all_orders,
    get_positions,
    get_pending_orders,
    get_closed_pnl,
    close_all_positions,
)


def register_command_handlers():
    # ---------- /start ----------
    @telClient.on(events.NewMessage(pattern=r"^/start$"))
    async def start_handler(event):
        chat = await event.get_chat()

        message = (
            "📌 Welcome! Choose an action:\n"
            "📊 Get Positions: /positions\n"
            "🛑 Cancel Orders: /cancel\n"
            "❌ Close active positions: /close_positions\n"
        )

        # [Button.inline("🛑 Cancel Orders", b"cancel")],
        # [Button.inline("❌ Close Positions", b"close_positions")],

        await telClient.send_message(chat, message)

    # ---------- /positions ----------
    @telClient.on(events.NewMessage(pattern=r"^/positions$"))
    async def positions_handler(event):
        try:
            print("call /positions")
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

    @telClient.on(events.NewMessage(pattern=r"^/positions$"))
    async def positions_handler(event):
        try:
            print("call /positions")
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

    # ---------- /cancel ----------
    @telClient.on(events.NewMessage(pattern=r"^/cancel$"))
    async def cancel_handler(event):
        try:
            print("call /cancel")
            orders = cancel_all_orders(settleCoin="USDT")
            await event.respond("🛑 All USDT orders cancelled")
        except Exception as e:
            await event.respond(f"❌ Error cancelling orders: {e}")

    # ---------- /close_positions ----------
    @telClient.on(events.NewMessage(pattern=r"^/close_positions$"))
    async def close_positions_handler(event):
        try:
            print("call /close_positions")
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
