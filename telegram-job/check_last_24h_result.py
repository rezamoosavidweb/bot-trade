from telethon import TelegramClient, events
import re
import asyncio
from telethon.errors import FloodWaitError, ChatWriteForbiddenError
from datetime import datetime
from zoneinfo import ZoneInfo
import jdatetime

# --- تنظیمات ---
api_id = 27396957
api_hash = "53e16a90d89a28a0a67bb95ca3dff324"


source_channel = -1001448000337 #https://bit.ly/m/AiGoldenCrypto
target_channel = -1003589742902  # MyTestTrade - ID عددی کانال


async def resolve_source_chat(client: TelegramClient, chat):
    """
    تلاش برای resolve کردن کانال/چت ورودی.
    پشتیبانی از: username، @username، لینک t.me، و آیدی عددی (int/str).
    """
    if chat is None:
        return None

    # numeric id as string
    if isinstance(chat, str):
        stripped = chat.strip()
        if stripped.lstrip("-").isdigit():
            chat = int(stripped)

    candidates = []
    if isinstance(chat, str):
        s = chat.strip()
        candidates.append(s)
        # t.me link -> username part
        if "t.me/" in s:
            username = s.split("t.me/", 1)[1].split("/", 1)[0].strip()
            if username:
                candidates.append(username)
                candidates.append(f"@{username.lstrip('@')}")
        # plain username -> @username
        if s and not s.startswith("@") and "://" not in s and "/" not in s:
            candidates.append(f"@{s}")
    else:
        candidates.append(chat)

    last_exc = None
    for cand in candidates:
        try:
            return await client.get_entity(cand)
        except Exception as e:
            last_exc = e
            continue

    print(
        "❌ خطا: کانال/چت مبدا قابل resolve نیست.\n"
        f"   مقدار source_channel: {source_channel!r}\n"
        "   راه‌حل: username صحیح (مثلاً @SomeChannel) یا آیدی عددی کانال (-100...) را وارد کنید.\n"
        f"   جزئیات خطا: {last_exc}"
    )
    return None


async def safe_send_message(client, channel, text):
    """ارسال پیام به صورت امن. در صورت موفقیت True و در صورت خطا False برمی‌گرداند."""
    while True:
        try:
            await client.send_message(channel, text)
            await asyncio.sleep(1.5)  # فاصله امن بین پیام‌ها
            return True
        except FloodWaitError as e:
            wait_time = e.seconds + 5
            print(f"Flood detected. Sleeping {wait_time} seconds...")
            await asyncio.sleep(wait_time)
        except ChatWriteForbiddenError:
            print(
                f"❌ خطا: دسترسی نوشتن در کانال {channel} وجود ندارد. لطفاً مطمئن شوید ربات ادمین کانال است."
            )
            return False
        except Exception as e:
            print(f"❌ خطا در ارسال پیام به {channel}: {e}")
            return False


# --- تابع تبدیل تاریخ میلادی به شمسی ---
def get_persian_date():
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    persian_date = jdatetime.datetime.fromgregorian(datetime=now)
    return persian_date.strftime("%Y/%m/%d")


# --- تابع پردازش پیام ---
def process_message(text: str, message_date=None, return_data=False):
    """
    پردازش پیام و استخراج اطلاعات
    message_date: datetime object تاریخ پیام (اگر None باشد از datetime.now استفاده می‌شود)
    اگر return_data=True باشد، یک دیکشنری با داده‌های خام برمی‌گرداند
    در غیر این صورت، متن فرمت شده را برمی‌گرداند
    """
    print(
        f"================================================\nProcessing profit\n{text}"
    )

    # 🔹 استخراج Win Rate از پیام
    win_rate_match = re.search(r"📊 Win Rate:\s*(\d+\.?\d*)%", text)
    win_rate = float(win_rate_match.group(1)) if win_rate_match else 0.0

    # 🔹 استخراج Signal Calls از پیام
    signal_calls_match = re.search(r"📡 Signal Calls:\s*(\d+)\s*calls", text)
    signal_calls = int(signal_calls_match.group(1)) if signal_calls_match else 0

    # 🔹 استخراج Profit Trades از پیام
    profit_trades_match = re.search(r"🟢 Profit Trades:\s*(\d+)", text)
    profit_trades = int(profit_trades_match.group(1)) if profit_trades_match else 0

    pattern = r"[A-Z]+USDT\s+:\s*([+-]?\d+\.\d+)%"
    numbers = re.findall(pattern, text)
    numbers = [float(n) for n in numbers]

    if not numbers:
        return None

    positives = [n for n in numbers if n > 0]
    negatives = [n for n in numbers if n < 0]

    # 🔹 شمارش اعداد مثبت بالای 20 و 27
    positives_above_20 = [n for n in positives if n > 20]
    positives_above_27 = [n for n in positives if n > 27]
    count_positives_above_20 = len(positives_above_20)
    count_positives_above_27 = len(positives_above_27)
    count_total_positives = len(positives)
    count_total_negatives = len(negatives)
    count_total_numbers = len(numbers)

    # 🔹 محاسبه مجموع اعداد منفی (فقط برای نمایش)
    sum_negatives = sum(negatives)

    # 🔹 محاسبه سود و ضرر بر اساس فرمول جدید
    # ضرر = تعداد اعداد منفی * 32
    loss = count_total_negatives * 32

    profit = (
        (count_total_positives * 1 * 13.2)
        + (count_positives_above_20  * 13.2)
        + (count_positives_above_27 * 13.2)
    )
    all_fee = count_total_numbers * 2
    net_profit = profit - loss - all_fee
    # 🔹 پیدا کردن کوچکترین عدد مثبت <= 20
    valid_small_positives = [n for n in positives if n <= 20]

    if valid_small_positives:
        replacement_value = min(valid_small_positives)
    else:
        replacement_value = 15.0  # اگر همه مثبت‌ها > 20 بودند

    # 🔁 جایگزینی
    final_positives = [n if n <= 20 else replacement_value for n in positives]

    total_positive = sum(final_positives)
    total_negative = sum(negatives)
    total = total_positive + total_negative

    # 🔹 تاریخ میلادی و شمسی
    if message_date:
        # تبدیل تاریخ پیام به timezone تهران
        if message_date.tzinfo is None:
            # اگر timezone ندارد، فرض می‌کنیم UTC است
            message_date = message_date.replace(tzinfo=ZoneInfo("UTC"))
        message_date_tehran = message_date.astimezone(ZoneInfo("Asia/Tehran"))
        gregorian_date = message_date_tehran.strftime("%Y-%m-%d")
        persian_date = jdatetime.datetime.fromgregorian(
            datetime=message_date_tehran
        ).strftime("%Y/%m/%d")
    else:
        # اگر تاریخ داده نشده، از تاریخ فعلی استفاده می‌کنیم
        now = datetime.now(ZoneInfo("Asia/Tehran"))
        gregorian_date = now.strftime("%Y-%m-%d")
        persian_date = get_persian_date()

    # 🔹 داده‌های خام برای محاسبه میانگین
    data = {
        "win_rate": win_rate,  # Win Rate از پیام
        "signal_calls": signal_calls,  # تعداد کل سیگنال‌ها
        "profit_trades": profit_trades,  # تعداد معاملات مثبت
        "count_total_positives": count_total_positives,
        "count_total_negatives": count_total_negatives,
        "count_positives_above_20": count_positives_above_20,
        "count_positives_above_27": count_positives_above_27,
        "sum_negatives": sum_negatives,
        "loss": loss,
        "profit": profit,
        "net_profit": net_profit,
        "count_total_numbers": count_total_numbers,
        "total": total,
        "gregorian_date": gregorian_date,
        "persian_date": persian_date,
    }

    if return_data:
        return data

    # 🔹 متن فرمت شده
    return (
        f"📊 Result Summary\n\n"
        f"🟢 اعداد مثبت نهایی:\n{final_positives}\n\n"
        f"🚫 اعداد منفی:\n{negatives}\n\n"
        f"🟢 تعداد کل اعداد مثبت: {count_total_positives}\n"
        f"📈 تعداد اعداد مثبت بالای 20: {count_positives_above_20}\n"
        f"📈 تعداد اعداد مثبت بالای 27: {count_positives_above_27}\n"
        f"🚫 تعداد معاملات منفی: {count_total_negatives}\n"
        f"➖ مجموع اعداد منفی: {sum_negatives:.2f}%\n\n"
        f"💰 محاسبات:\n"
        f"   • ضرر: {count_total_negatives} × 32 = {loss:.2f}\n"
        f"   • سود: ({count_total_positives} × 0.3 × 13.7) + ({count_positives_above_20} × 0.45 × 13.5) + ({count_positives_above_27} × 0.25 × 13.7) = {profit:.2f}\n"
        f"   • سود خالص: {net_profit:.2f}\n\n"
        f"📅 تاریخ میلادی: {gregorian_date}\n"
        f"📅 تاریخ شمسی: {persian_date}"
    )


# --- تابع محاسبه و ساخت پیام‌های خلاصه 30 پیام ---
def calculate_batch_summaries(results):
    """
    محاسبه و ساخت دو پیام خلاصه برای 30 پیام
    بازمی‌گرداند: (message1, message2) یا (None, None) در صورت خطا
    """
    if not results or len(results) == 0:
        return None, None

    total_messages = len(results)

    # محاسبه net_total (مجموع net_profit همه روزها)
    total_net_profit = sum(r["net_profit"] for r in results)

    # پیدا کردن بزرگترین منفی (کمترین net_profit)
    min_net_profit = min(r["net_profit"] for r in results)
    min_net_profit_date = None
    for r in results:
        if r["net_profit"] == min_net_profit:
            min_net_profit_date = r["persian_date"]
            break

    # پیدا کردن بیشترین سود (بیشترین net_profit)
    max_net_profit = max(r["net_profit"] for r in results)
    max_net_profit_date = None
    for r in results:
        if r["net_profit"] == max_net_profit:
            max_net_profit_date = r["persian_date"]
            break

    # تاریخ اول و آخر
    first_date_persian = results[0]["persian_date"]
    first_date_gregorian = results[0]["gregorian_date"]
    last_date_persian = results[-1]["persian_date"]
    last_date_gregorian = results[-1]["gregorian_date"]

    # پیام اول: لیست 30 تایی
    message1_lines = [
        f"📊 لیست {total_messages} پیام گذشته",
        f"{'='*56}",
        "",
        f"Calls ➤ Win Rate | + | - | +>20 | +>27 | Loss | Profit 🌟 Net 🌟 Date",
        f"{'-'*80}",
    ]

    for i, r in enumerate(results, 1):
        win_rate_val = r["win_rate"]  # استفاده از Win Rate از پیام
        signal_calls = r.get("signal_calls", 0)
        count_pos = r["count_total_positives"]
        count_neg = r["count_total_negatives"]
        count_20 = r["count_positives_above_20"]
        count_27 = r["count_positives_above_27"]
        loss_val = r["loss"]
        profit_val = r["profit"]
        net_val = r["net_profit"]
        message1_lines.append(
            f"{i:2d}. {signal_calls:4d} ➤ {win_rate_val:6.2f}% | {count_pos:2d} | {count_neg:2d} | {count_20:4d} | {count_27:4d} | {loss_val:6.2f} | {profit_val:6.2f} 🌟 {net_val:7.2f} 🌟 ({r['persian_date']})"
        )

    message1 = "\n".join(message1_lines)

    # پیام دوم: خلاصه
    message2_lines = [
        f"📈 خلاصه {total_messages} پیام",
        f"{'='*56}",
        "",
        f"📅 بازه تاریخ:",
        f"   از: {first_date_gregorian} ({first_date_persian})",
        f"   تا: {last_date_gregorian} ({last_date_persian})",
        "",
        f"💰 نتایج:",
        f"   • Net Total: {total_net_profit:.2f}",
        f"   • Max Loss: {min_net_profit:.2f} ({min_net_profit_date})",
        f"   • Max Profit: {max_net_profit:.2f} ({max_net_profit_date})",
    ]
    message2 = "\n".join(message2_lines)

    return message1, message2


# --- ساخت کلاینت ---
client = TelegramClient("session_name", api_id, api_hash)

# --- ذخیره نتایج برای محاسبه میانگین ---
message_results = []  # لیست نتایج 30 پیام گذشته
BATCH_SIZE = 30  # تعداد پیام‌ها برای محاسبه میانگین


# --- پردازش پیام‌های گذشته ---
async def process_old_messages(source_entity):
    global message_results
    async for message in client.iter_messages(source_entity, limit=None):
        text = message.message

        # ⛔ اگر پیام متن نداشت، رد شو
        if not text:
            continue
        # print(text)
        if text.startswith("📈 Last 24 hours results"):
            try:
                # دریافت تاریخ پیام
                msg_date = message.date

                # دریافت داده‌های خام (بدون ارسال پیام)
                data = process_message(text, message_date=msg_date, return_data=True)

                if data:
                    # اضافه کردن داده به لیست
                    message_results.append(data)
                    print(f"✅ پیام پردازش شد. ({len(message_results)}/{BATCH_SIZE})")

                    # بررسی اینکه آیا به 30 پیام رسیدیم
                    if len(message_results) >= BATCH_SIZE:
                        message1, message2 = calculate_batch_summaries(message_results)
                        if message1 and message2:
                            # ارسال پیام اول
                            success1 = await safe_send_message(
                                client, target_channel, message1
                            )
                            if success1:
                                print("✅ پیام اول (لیست 30 تایی) ارسال شد.")

                            # کمی تاخیر بین دو پیام
                            await asyncio.sleep(2)

                            # ارسال پیام دوم
                            success2 = await safe_send_message(
                                client, target_channel, message2
                            )
                            if success2:
                                print("✅ پیام دوم (میانگین کلی) ارسال شد.")
                                print(f"✅ خلاصه {BATCH_SIZE} پیام با موفقیت ارسال شد.")
                        # پاک کردن لیست برای شروع جدید
                        message_results = []
            except Exception as e:
                print(f"❌ خطا در پردازش پیام: {e}")
                continue


async def new_message_handler(event):
    global message_results
    text = event.message.message

    if not text:
        return

    if text.startswith("📈 Last 24 hours results"):
        try:
            # دریافت تاریخ پیام
            msg_date = event.message.date

            # دریافت داده‌های خام (بدون ارسال پیام)
            data = process_message(text, message_date=msg_date, return_data=True)

            if data:
                # اضافه کردن داده به لیست
                message_results.append(data)
                print(f"✅ پیام جدید پردازش شد. ({len(message_results)}/{BATCH_SIZE})")

                # بررسی اینکه آیا به 30 پیام رسیدیم
                if len(message_results) >= BATCH_SIZE:
                    message1, message2 = calculate_batch_summaries(message_results)
                    if message1 and message2:
                        # ارسال پیام اول
                        success1 = await safe_send_message(
                            client, target_channel, message1
                        )
                        if success1:
                            print("✅ پیام اول (لیست 30 تایی) ارسال شد.")

                        # کمی تاخیر بین دو پیام
                        await asyncio.sleep(2)

                        # ارسال پیام دوم
                        success2 = await safe_send_message(
                            client, target_channel, message2
                        )
                        if success2:
                            print("✅ پیام دوم (میانگین کلی) ارسال شد.")
                            print(f"✅ خلاصه {BATCH_SIZE} پیام با موفقیت ارسال شد.")
                    # پاک کردن لیست برای شروع جدید
                    message_results = []
        except Exception as e:
            print(f"❌ خطا در پردازش پیام جدید: {e}")


# --- اجرای کلاینت ---
async def main():
    await client.start()
    source_entity = await resolve_source_chat(client, source_channel)
    if source_entity is None:
        return

    client.add_event_handler(new_message_handler, events.NewMessage(chats=source_entity))

    print("Processing old messages...")
    await process_old_messages(source_entity)
    print("Listening for new messages...")
    await client.run_until_disconnected()


with client:
    client.loop.run_until_complete(main())
