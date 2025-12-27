from telethon import events, Button
from clients import telClient
from api import (
    cancel_all_orders,
    get_positions,
    get_pending_orders,
    get_closed_pnl,
    close_all_positions,
)

def register_command_handlers():
    @telClient.on(events.NewMessage(pattern=r"^/start$"))
    async def start_handler(event):
        chat = await event.get_chat()

        # Inline buttons زیر پیام
        buttons = [
            [Button.inline("📊 Positions", b"positions")],
            [Button.inline("🛑 Cancel Orders", b"cancel")],
            [Button.inline("❌ Close Positions", b"close_positions")],
        ]

        await telClient.send_message(
            chat,
            "📌 Welcome! Choose an action:",
            buttons=buttons
        )

    @telClient.on(events.CallbackQuery)
    async def callback_handler(event):
        data = event.data.decode("utf-8")
        try:
            if data == "positions":
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
                await event.edit(msg)

            elif data == "cancel":
                cancel_all_orders(settleCoin="USDT")
                await event.edit("🛑 All USDT orders cancelled")

            elif data == "close_positions":
                results = close_all_positions(settleCoin="USDT")
                if not results:
                    await event.edit("📌 No open positions to close.")
                    return
                msg = "✅ Closed positions:\n\n"
                for r in results:
                    msg += f"{r['symbol']} | {r['side']} | {r['size']}\n"
                await event.edit(msg)

        except Exception as e:
            await event.edit(f"❌ Error: {e}")
