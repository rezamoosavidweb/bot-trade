"""
تحلیل نهایی استراتژی TP1 و TP2
مقایسه استراتژی فعلی (40% TP1, 60% TP2) با استراتژی جایگزین (100% TP1)
"""

import json
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import sys
import io

# Set UTF-8 encoding for output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Load the data
with open('ws_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

def safe_float(value):
    """Safely convert to float"""
    try:
        return float(value) if value else 0.0
    except (ValueError, TypeError):
        return 0.0

# Group all messages by symbol and sort by timestamp
symbol_events = defaultdict(list)

for message in data.get('messages', []):
    timestamp = message.get('timestamp', '')
    msg_data = message.get('data', {}).get('data', [])
    if not msg_data:
        continue
    
    for order in msg_data:
        symbol = order.get('symbol', '')
        if not symbol:
            continue
        
        order_status = order.get('orderStatus', '')
        stop_order_type = order.get('stopOrderType', '')
        side = order.get('side', '')
        qty = safe_float(order.get('qty', 0))
        trigger_price = safe_float(order.get('triggerPrice', 0))
        closed_pnl = safe_float(order.get('closedPnl', 0))
        avg_price = safe_float(order.get('avgPrice', 0))
        cum_exec_qty = safe_float(order.get('cumExecQty', 0))
        
        # Store all relevant events
        if order_status == "Filled":
            event_type = None
            if stop_order_type == "":
                event_type = "ENTRY"
            elif stop_order_type == "PartialTakeProfit":
                event_type = "TP"
            elif stop_order_type == "StopLoss":
                event_type = "SL"
            
            if event_type:
                symbol_events[symbol].append({
                    'timestamp': timestamp,
                    'type': event_type,
                    'side': side,
                    'stop_order_type': stop_order_type,
                    'qty': qty,
                    'trigger_price': trigger_price,
                    'closed_pnl': closed_pnl,
                    'avg_price': avg_price,
                    'exec_qty': cum_exec_qty,
                })

# Sort events by timestamp for each symbol
for symbol in symbol_events:
    symbol_events[symbol].sort(key=lambda x: x['timestamp'])

# Process each symbol
signals = []

for symbol, events in symbol_events.items():
    signal = {
        'symbol': symbol,
        'side': '',
        'entry_price': 0,
        'entry_qty': 0,
        'tp1_price': 0,
        'tp2_price': 0,
        'tp1_qty': 0,
        'tp2_qty': 0,
        'tp_events': [],
        'sl_events': [],
    }
    
    # Process events in order
    for event in events:
        if event['type'] == "ENTRY":
            signal['side'] = event['side']
            signal['entry_price'] = event['avg_price']
            signal['entry_qty'] = event['exec_qty']
            signal['tp1_qty'] = event['exec_qty'] * 0.4
            signal['tp2_qty'] = event['exec_qty'] * 0.6
        elif event['type'] == "TP":
            signal['tp_events'].append(event)
            # Track TP prices from trigger_price
            if event['trigger_price'] > 0:
                if signal['tp1_price'] == 0:
                    signal['tp1_price'] = event['trigger_price']
                elif signal['tp2_price'] == 0:
                    signal['tp2_price'] = event['trigger_price']
        elif event['type'] == "SL":
            signal['sl_events'].append(event)
    
    if signal['entry_price'] > 0:
        signals.append(signal)

# Calculate results
current_strategy = {
    'total_signals': len(signals),
    'tp1_only': 0,
    'tp2_reached': 0,
    'sl_before_tp1': 0,
    'sl_after_tp1': 0,
    'total_pnl': 0.0,
    'total_pnl_tp1': 0.0,
    'total_pnl_tp2': 0.0,
    'total_pnl_sl': 0.0,
    'details': []
}

alternative_strategy = {
    'total_signals': len(signals),
    'tp1_reached': 0,
    'sl_before_tp1': 0,
    'sl_after_tp1': 0,
    'total_pnl': 0.0,
    'total_pnl_tp1': 0.0,
    'total_pnl_sl': 0.0,
    'details': []
}

def calculate_pnl(entry: float, exit: float, qty: float, side: str) -> float:
    """Calculate PnL"""
    if side == "Buy":
        return (exit - entry) * qty
    else:  # Sell
        return (entry - exit) * qty

# Process each signal
for signal in signals:
    entry_price = signal['entry_price']
    entry_qty = signal['entry_qty']
    side = signal['side']
    tp1_qty = signal['tp1_qty']
    tp2_qty = signal['tp2_qty']
    
    # Sort TP events by timestamp
    tp_events_sorted = sorted(signal['tp_events'], key=lambda x: x['timestamp'])
    sl_events_sorted = sorted(signal['sl_events'], key=lambda x: x['timestamp'])
    
    # Identify TP1 and TP2
    tp1_event = None
    tp2_event = None
    
    if len(tp_events_sorted) > 0:
        # First TP is TP1
        tp1_event = tp_events_sorted[0]
        if len(tp_events_sorted) > 1:
            # Second TP is TP2
            tp2_event = tp_events_sorted[1]
    
    sl_event = sl_events_sorted[0] if sl_events_sorted else None
    
    # Current strategy analysis
    current_pnl = 0.0
    current_detail = {
        'symbol': signal['symbol'],
        'outcome': '',
        'pnl': 0.0,
        'tp1_pnl': 0.0,
        'tp2_pnl': 0.0,
        'sl_pnl': 0.0,
    }
    
    # Determine outcome
    if sl_event and (not tp1_event or sl_event['timestamp'] < tp1_event['timestamp']):
        # SL before TP1
        current_strategy['sl_before_tp1'] += 1
        current_detail['outcome'] = 'SL before TP1'
        if sl_event['closed_pnl'] != 0:
            current_pnl = sl_event['closed_pnl']
            current_detail['sl_pnl'] = sl_event['closed_pnl']
        else:
            current_pnl = calculate_pnl(entry_price, sl_event['avg_price'], entry_qty, side)
            current_detail['sl_pnl'] = current_pnl
        current_strategy['total_pnl_sl'] += current_pnl
        
    elif tp1_event:
        # TP1 was hit
        if tp1_event['closed_pnl'] != 0:
            tp1_pnl = tp1_event['closed_pnl']
        else:
            tp1_pnl = calculate_pnl(entry_price, tp1_event['avg_price'], tp1_qty, side)
        current_pnl += tp1_pnl
        current_detail['tp1_pnl'] = tp1_pnl
        current_strategy['total_pnl_tp1'] += tp1_pnl
        
        if tp2_event and tp2_event['timestamp'] > tp1_event['timestamp']:
            # TP2 was also hit
            current_strategy['tp2_reached'] += 1
            current_detail['outcome'] = 'TP1 + TP2'
            if tp2_event['closed_pnl'] != 0:
                tp2_pnl = tp2_event['closed_pnl']
            else:
                tp2_pnl = calculate_pnl(entry_price, tp2_event['avg_price'], tp2_qty, side)
            current_pnl += tp2_pnl
            current_detail['tp2_pnl'] = tp2_pnl
            current_strategy['total_pnl_tp2'] += tp2_pnl
        elif sl_event and sl_event['timestamp'] > tp1_event['timestamp']:
            # SL after TP1
            current_strategy['sl_after_tp1'] += 1
            current_detail['outcome'] = 'TP1 + SL'
            if sl_event['closed_pnl'] != 0:
                # closedPnl is for remaining qty (60%)
                sl_pnl = sl_event['closed_pnl']
            else:
                sl_pnl = calculate_pnl(entry_price, sl_event['avg_price'], tp2_qty, side)
            current_pnl += sl_pnl
            current_detail['sl_pnl'] = sl_pnl
            current_strategy['total_pnl_sl'] += sl_pnl
        else:
            # Only TP1, position still open
            current_strategy['tp1_only'] += 1
            current_detail['outcome'] = 'TP1 only (open)'
    
    current_detail['pnl'] = current_pnl
    current_strategy['total_pnl'] += current_pnl
    current_strategy['details'].append(current_detail)
    
    # Alternative strategy analysis (100% TP1)
    alt_pnl = 0.0
    alt_detail = {
        'symbol': signal['symbol'],
        'outcome': '',
        'pnl': 0.0,
        'tp1_pnl': 0.0,
        'sl_pnl': 0.0,
    }
    
    if sl_event and (not tp1_event or sl_event['timestamp'] < tp1_event['timestamp']):
        # SL before TP1
        alternative_strategy['sl_before_tp1'] += 1
        alt_detail['outcome'] = 'SL before TP1'
        if sl_event['closed_pnl'] != 0:
            alt_pnl = sl_event['closed_pnl']
            alt_detail['sl_pnl'] = sl_event['closed_pnl']
        else:
            alt_pnl = calculate_pnl(entry_price, sl_event['avg_price'], entry_qty, side)
            alt_detail['sl_pnl'] = alt_pnl
        alternative_strategy['total_pnl_sl'] += alt_pnl
        
    elif tp1_event:
        # TP1 was hit - take 100% at TP1
        alternative_strategy['tp1_reached'] += 1
        alt_detail['outcome'] = 'TP1 (100%)'
        # Calculate PnL for full quantity at TP1 price
        if tp1_event['closed_pnl'] != 0:
            # Scale the closedPnl from 40% to 100%
            # closedPnl is already calculated for tp1_qty, so scale it
            alt_pnl = tp1_event['closed_pnl'] * (entry_qty / tp1_qty) if tp1_qty > 0 else 0
        else:
            alt_pnl = calculate_pnl(entry_price, tp1_event['avg_price'], entry_qty, side)
        alt_detail['tp1_pnl'] = alt_pnl
        alternative_strategy['total_pnl_tp1'] += alt_pnl
    
    alt_detail['pnl'] = alt_pnl
    alternative_strategy['total_pnl'] += alt_pnl
    alternative_strategy['details'].append(alt_detail)

# Print results
print("=" * 100)
print("Final Analysis: TP1 vs TP2 Strategy Comparison")
print("=" * 100)
print()

print("Current Strategy: 40% TP1 + 60% TP2")
print("-" * 100)
print(f"Total Signals: {current_strategy['total_signals']}")
print(f"Signals that reached TP1: {current_strategy['tp1_only'] + current_strategy['tp2_reached']}")
print(f"  - Only TP1 (TP2 not reached): {current_strategy['tp1_only']}")
print(f"  - Reached TP2: {current_strategy['tp2_reached']}")
print(f"Signals that hit SL:")
print(f"  - Before TP1: {current_strategy['sl_before_tp1']}")
print(f"  - After TP1: {current_strategy['sl_after_tp1']}")
print()
print(f"Total PnL: {current_strategy['total_pnl']:.2f} USDT")
print(f"  - From TP1: {current_strategy['total_pnl_tp1']:.2f} USDT")
print(f"  - From TP2: {current_strategy['total_pnl_tp2']:.2f} USDT")
print(f"  - From SL: {current_strategy['total_pnl_sl']:.2f} USDT")
print()

print("\nSignal Details (Current Strategy):")
print("-" * 100)
print(f"{'Symbol':<12} | {'Outcome':<20} | {'Total PnL':>10} | {'TP1 PnL':>10} | {'TP2 PnL':>10} | {'SL PnL':>10}")
print("-" * 100)
for detail in current_strategy['details']:
    print(f"{detail['symbol']:<12} | {detail['outcome']:<20} | "
          f"{detail['pnl']:>10.2f} | "
          f"{detail['tp1_pnl']:>10.2f} | "
          f"{detail['tp2_pnl']:>10.2f} | "
          f"{detail['sl_pnl']:>10.2f}")

print()
print("\nAlternative Strategy: 100% TP1")
print("-" * 100)
print(f"Total Signals: {alternative_strategy['total_signals']}")
print(f"Signals that reached TP1: {alternative_strategy['tp1_reached']}")
print(f"Signals that hit SL:")
print(f"  - Before TP1: {alternative_strategy['sl_before_tp1']}")
print(f"  - After TP1: {alternative_strategy['sl_after_tp1']}")
print()
print(f"Total PnL: {alternative_strategy['total_pnl']:.2f} USDT")
print(f"  - From TP1: {alternative_strategy['total_pnl_tp1']:.2f} USDT")
print(f"  - From SL: {alternative_strategy['total_pnl_sl']:.2f} USDT")
print()

print("\nSignal Details (Alternative Strategy):")
print("-" * 100)
print(f"{'Symbol':<12} | {'Outcome':<20} | {'Total PnL':>10} | {'TP1 PnL':>10} | {'SL PnL':>10}")
print("-" * 100)
for detail in alternative_strategy['details']:
    print(f"{detail['symbol']:<12} | {detail['outcome']:<20} | "
          f"{detail['pnl']:>10.2f} | "
          f"{detail['tp1_pnl']:>10.2f} | "
          f"{detail['sl_pnl']:>10.2f}")

print()
print("=" * 100)
print("COMPARISON")
print("=" * 100)
diff = alternative_strategy['total_pnl'] - current_strategy['total_pnl']
diff_pct = (diff / abs(current_strategy['total_pnl']) * 100) if current_strategy['total_pnl'] != 0 else 0

print(f"PnL Difference: {diff:+.2f} USDT ({diff_pct:+.2f}%)")
print()
if diff > 0:
    print(f"✓ 100% TP1 strategy is BETTER!")
    print(f"  You would have made {diff:.2f} USDT MORE by using 100% TP1")
    print(f"  Current: {current_strategy['total_pnl']:.2f} USDT")
    print(f"  Alternative: {alternative_strategy['total_pnl']:.2f} USDT")
elif diff < 0:
    print(f"✓ Current strategy (40% TP1 + 60% TP2) is BETTER!")
    print(f"  Current strategy saved you {abs(diff):.2f} USDT")
    print(f"  Current: {current_strategy['total_pnl']:.2f} USDT")
    print(f"  Alternative: {alternative_strategy['total_pnl']:.2f} USDT")
else:
    print("= Both strategies have the same result")

print()
print("=" * 100)
