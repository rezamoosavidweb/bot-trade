def normalize_qty(qty, step):
    precision = len(str(step).split(".")[1]) if "." in str(step) else 0
    qty = int(qty / step) * step
    return round(qty, precision)
