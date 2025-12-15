def process_message(text: str):
    numbers = re.findall(r'([+-]?\d+\.\d+)%', text)
    numbers = [float(n) for n in numbers]

    if not numbers:
        return "عدد پیدا نشد."

    positives = [n for n in numbers if n > 0]
    negatives = [n for n in numbers if n < 0]

    if not positives:
        return "عدد مثبت وجود ندارد."

    min_positive = min(positives)
    positives = [n if n <= 20 else min_positive for n in positives]

    total_positive = sum(positives)
    total_negative = sum(negatives)
    total = total_positive + total_negative

    result = (
        f"تعداد اعداد مثبت: {len(positives)}\n"
        f"تعداد اعداد منفی: {len(negatives)}\n"
        f"جمع اعداد مثبت: {total_positive:.2f}%\n"
        f"جمع اعداد منفی: {total_negative:.2f}%\n"
        f"سود نهایی: {total:.2f}%"
    )
    print(result)
    return result

process_message(f"📈 Last 24 hours results - #December13
LTCUSDT     :+14.57% 🟢
ENSUSDT     :+21.76% 🟢
LTCUSDT     :-28.40% 🚫
LINKUSDT    :-28.84% 🚫
SOLUSDT     :-30.10% 🚫
KASUSDT     :+38.30% 🟢
TONUSDT     :-30.56% 🚫
ASTERUSDT   :-30.44% 🚫
JUPUSDT     :+46.53% 🟢
TRUMPUSDT   :+15.10% 🟢
CAKEUSDT    :+44.38% 🟢
XPLUSDT     :+40.00% 🟢
INJUSDT     :+23.74% 🟢
APTUSDT     :+22.61% 🟢
ENSUSDT     :+30.11% 🟢
TRUMPUSDT   :+30.27% 🟢
FETUSDT     :+32.12% 🟢
HBARUSDT    :+46.82% 🟢
💰 Total Profit: 406.31% profit
💹 Average Profit/Trade: 31.25%
📡 Signal Calls: 18 calls
📊 Win Rate: 72.22%
🟢 Profit Trades: 13
🚫 Loss Trades: 5
Seize this opportunity now! Join us to level up your crypto trading!")