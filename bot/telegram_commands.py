from telethon import events, Button
from clients import telClient

def register_command_handlers():
    @telClient.on(events.NewMessage(pattern=r"^/start$"))
    async def start_handler(event):
        # دکمه‌ها
        buttons = [
            [Button.inline("📊 Positions")],
            [Button.inline("🛑 Cancel Orders")],
            [Button.inline("❌ Close Positions")],
        ]

        # با send_message مستقیم روی chat_id پیام می‌فرستیم
        await telClient.send_message(
            entity=event.chat_id,
            message="📌 Welcome! Choose an action:",
            buttons=buttons  # اینجا مهمه
        )

    @telClient.on(events.NewMessage)
    async def menu_handler(event):
        text = event.raw_text

        if text == "📊 Positions":
            await telClient.send_message(event.chat_id, "You pressed Positions!")
        elif text == "🛑 Cancel Orders":
            await telClient.send_message(event.chat_id, "You pressed Cancel Orders!")
        elif text == "❌ Close Positions":
            await telClient.send_message(event.chat_id, "You pressed Close Positions!")
