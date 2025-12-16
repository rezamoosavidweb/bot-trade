from telethon import TelegramClient, events
import re
import asyncio
from telethon.errors import FloodWaitError
from datetime import datetime, timedelta, timezone
import calendar
from zoneinfo import ZoneInfo
iran_tz = ZoneInfo("Asia/Tehran")

# --- تنظیمات ---
api_id = 27396957
api_hash = '53e16a90d89a28a0a67bb95ca3dff324'

source_channel = 'CryptoSignalsGolden'   # کانالی که می‌خواهید بررسی شود
target_channel = -1002383929199          # کانال مقصد
last_days = 300                           # تعداد روز گذشته برای بررسی
net_total_over_days = 0.0
loss_total_over_days = 0.0
profit_count = 0.0

# --- regex سیگنال و درصد ---
SIGNAL_REGEX = re.compile(
    r"""
    (Long|Short)\s+.*?
    Lev\s*x\d+.*?
    Entry:\s*[\d.]+\s*-\s*           
    Stop\s*Loss:\s*[\d.]+.*?
    Targets:\s*         
    (?:[\d.]+\s*-\s*)+[\d.]+
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE
)

PERCENT_REGEX = re.compile(r'([+-]?\d+(?:\.\d+)?)\s*%')

def extract_percent(text: str):
    match = PERCENT_REGEX.search(text)
    if match:
        return float(match.group(1))
    return None

def is_signal_message(text: str) -> bool:
    if not text:
        return False
    return bool(SIGNAL_REGEX.search(text))

def format_date(dt: datetime):
    day_name = calendar.day_name[dt.weekday()]
    return f"{dt.date()} / {day_name}"

async def safe_send_message(client, channel, text):
    while True:
        try:
            await client.send_message(channel, text)
            await asyncio.sleep(1.5)
            break
        except FloodWaitError as e:
            wait_time = e.seconds + 5
            print(f"Flood detected. Sleeping {wait_time} seconds...")
            await asyncio.sleep(wait_time)

def build_report(signals: dict, day_label: str):
    global net_total_over_days
    global profit_count
    global loss_total_over_days
    total_profit = 0.0
    total_loss = 0.0

    report = f"📊 Signal Report for {day_label}\n\n"

    for data in signals.values():
        profit = data["profit"]
        loss = data["loss"]
        date = data["date"]

        if profit is None and loss is None:
            continue

        if profit is not None:
            total_profit += profit
            profit_count += 1
            status = f"🟢 PROFIT {profit:.2f}%"
        else:
            total_loss += loss
            status = f"🔴 LOSS {loss:.2f}%"
        local_time = date.astimezone(iran_tz)
        
        report += (
            f"{local_time}\n"
            f"{status}\n"
            f"Signal:\n{data['text']}\n"
            f"{'-'*30}\n"
        )
    # جمع کردن در متغیر گلوبال
    net_day = total_profit - total_loss
    net_total_over_days += net_day 
    loss_total_over_days += total_loss 
    report += (
        f"\n✅ Total Profit: {total_profit:.2f}%\n"
        f"❌ Total Loss: {total_loss:.2f}%\n"
        f"📈 Net Result: {(net_day):.2f}%"
    )
    return report

# --- پردازش سیگنال‌های یک روز ---
async def process_signals_for_date(day: datetime):
    signals = {}
    day_start = datetime(day.year, day.month, day.day,0, 0, 0, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    batch_size=200
    # جمع‌آوری سیگنال‌ها و replyها
    async for msg in client.iter_messages(source_channel, offset_date = day_end ,limit = batch_size):
        if not msg.message:
            continue
        if not (day_start <= msg.date < day_end):
            continue

        # سیگنال
        if is_signal_message(msg.message):
            signals[msg.id] = {
                "text": msg.message,
                "date": msg.date,
                "profit": None,
                "loss": None,
                "replies": []
            }
        
    async for msg in client.iter_messages(source_channel, offset_date = day_end ,limit = batch_size):
        if not msg.message:
            continue
        if not (day_start <= msg.date < day_end):
            continue

        parent_id = msg.reply_to_msg_id
        if not parent_id or parent_id not in signals:
            continue


        percent = extract_percent(msg.message)
        if percent is None:
            continue

        text = msg.message.lower()

        # 🟥 Stop Loss
        if any(k in text for k in ["stop loss", "stopped", "sl"]):
            signals[parent_id]["loss"] = abs(percent)

        # 🟢 Profit / TP
        elif any(k in text for k in ["profit", "target"]):
            current = signals[parent_id]["profit"]
            signals[parent_id]["profit"] = (
                percent if current is None else max(current, percent)
            )

        signals[parent_id]["replies"].append(msg.message)

    return signals

# --- main loop ---
async def main():
    today = datetime.now(timezone.utc).date()

    for delta in range(last_days):
        day_to_check = today - timedelta(days=delta)
        day_label = f"{day_to_check} / {calendar.day_name[day_to_check.weekday()]}"

        print(f"Processing signals for {day_label} ...")
        signals = await process_signals_for_date(day_to_check)

        if not signals:
            await safe_send_message(client, target_channel, f"❗ No signals found for {day_label}")
            continue

        report = build_report(signals, day_label)
        # await safe_send_message(client, target_channel, report)
        print(f"✅ Report sent for {day_label}")
        print(f"{delta} days / profit_count{profit_count} / Total Minimum Net '{(profit_count * 15.06)-loss_total_over_days}' / Total Minimum Profit '{profit_count*15.06}' / Total Loss{loss_total_over_days}  / Total Maximum Profit{net_total_over_days:.2f}%\n\n")
    
    await safe_send_message(client, target_channel, f"TOTAL in {last_days} days: {net_total_over_days:.2f}%")

# --- اجرای کلاینت ---
client = TelegramClient('session_name', api_id, api_hash)
with client:
    client.loop.run_until_complete(main())
