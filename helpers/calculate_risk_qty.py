def calculate_risk_qty(symbol, entry, sl):
    info = get_symbol_info(symbol)
    balance = get_usdt_balance()

    risk_amount = balance * RISK_PERCENT
    sl_distance = abs(entry - sl)

    if sl_distance <= 0:
        return None

    raw_qty = risk_amount / sl_distance
    qty = normalize_qty(raw_qty, info["qty_step"])

    # min qty
    if qty < info["min_qty"]:
        return None

    # min notional
    if qty * entry < info["min_notional"]:
        return None

    return qty
