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
        chat = await event.get_chat()  # گرفتن چت فعلی

        buttons = [
            [Button.text("📊 Positions")],
            [Button.text("🛑 Cancel Orders")],
            [Button.text("❌ Close Positions")],
        ]

        # ارسال پیام جدید به جای event.respond
        await telClient.send_message(
            chat,
            "📌 Welcome! Choose an action:",
            buttons=buttons,
            parse_mode='md'
        )

    @telClient.on(events.NewMessage)
    async def menu_handler(event):
        text = event.raw_text
        try:
            if text == "📊 Positions":
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
                await telClient.send_message(event.chat_id, msg, parse_mode='md')

            elif text == "🛑 Cancel Orders":
                cancel_all_orders(settleCoin="USDT")
                await telClient.send_message(event.chat_id, "🛑 All USDT orders cancelled")

            elif text == "❌ Close Positions":
                results = close_all_positions(settleCoin="USDT")
                if not results:
                    await telClient.send_message(event.chat_id, "📌 No open positions to close.")
                    return
                msg = "✅ Closed positions:\n\n"
                for r in results:
                    msg += f"{r['symbol']} | {r['side']} | {r['size']}\n"
                await telClient.send_message(event.chat_id, msg)

        except Exception as e:
            await telClient.send_message(event.chat_id, f"❌ Error: {e}")
