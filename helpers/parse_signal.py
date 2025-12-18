def parse_signal(text):
    symbol_match = re.search(r"#\s*([A-Z0-9]+)\s*/\s*(USDT|USDC|USD)", text, re.I)
    side_match = re.search(r"(Long|Short)", text, re.I)
    entry_match = re.search(r"Entry:\s*([\d.]+)", text)
    sl_match = re.search(r"Stop\s*Loss:\s*([\d.]+)", text)
    targets = [float(x) for x in re.findall(r"Targets:\s*([^\n]+)", text)[0].split("-")]

    if not all([symbol_match, side_match, entry_match, sl_match]):
        return None

    symbol = symbol_match.group(1).upper() + symbol_match.group(2).upper()
    side = "Buy" if side_match.group(1).lower() == "long" else "Sell"

    return {
        "symbol": symbol,
        "side": side,
        "entry": float(entry_match.group(1)),
        "sl": float(sl_match.group(1)),
        "targets": targets,
    }
