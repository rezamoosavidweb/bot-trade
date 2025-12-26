import re

# ---------------- SIGNAL REGEX ---------------- #
SIGNAL_REGEX = re.compile(
    r"(Long|Short).*?Lev\s*x\d+.*?Entry:\s*[\d.]+.*?Stop\s*Loss:\s*[\d.]+.*?Targets:\s*(?:[\d.]+\s*-\s*)*[\d.]+",
    re.IGNORECASE | re.DOTALL,
)

def is_signal_message(text: str) -> bool:
    """Check if the message matches the signal pattern."""
    if not text:
        return False
    return bool(SIGNAL_REGEX.search(text))

def parse_signal(text: str):
    """Extract symbol, side, entry, stop-loss, and targets from signal text."""
    symbol_match = re.search(r"#\s*([A-Z0-9]+)\s*/\s*(USDT|USDC|USD)", text, re.I)
    side_match = re.search(r"(Long|Short)", text, re.I)
    entry_match = re.search(r"Entry:\s*([\d.]+)", text)
    sl_match = re.search(r"Stop\s*Loss:\s*([\d.]+)", text)
    targets_match = re.findall(r"Targets:\s*([^\n]+)", text)

    if not all([symbol_match, side_match, entry_match, sl_match, targets_match]):
        return None

    symbol = symbol_match.group(1).upper() + symbol_match.group(2).upper()
    side = "Buy" if side_match.group(1).lower() == "long" else "Sell"
    targets = [float(x) for x in targets_match[0].split("-")]

    return {
        "symbol": symbol,
        "side": side,
        "entry": float(entry_match.group(1)),
        "sl": float(sl_match.group(1)),
        "targets": targets,
    }
