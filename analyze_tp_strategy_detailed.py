"""
تحلیل دقیق استراتژی TP1 و TP2
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

# Group messages by symbol and process chronologically
symbol_messages = defaultdict(list)

for message in data.get('messages', []):
    timestamp = message.get('timestamp', '')
    msg_data = message.get('data', {}).get('data', [])
    if not msg_data:
        continue
    
    for order in msg_data:
        symbol = order.get('symbol', '')
        if symbol:
            symbol_messages[symbol].append({
                'timestamp': timestamp,
                'order': order
            })

# Sort messages by timestamp for each symbol
for symbol in symbol_messages:
    symbol_messages[symbol].sort(key=lambda x: x['timestamp'])

# Process each symbol
signals = []

for symbol, messages in symbol_messages.items():
    signal = {
        'symbol': symbol,
        'side': '',
        'entry_price': 0,
        'entry_qty': 0,
        'tp1_price': 0,
        'tp2_price': 0,
        'sl_price': 0,
        'tp1_qty': 0,  # 40%
        'tp2_qty': 0,  # 60%
        'events': [],  # List of events (TP1, TP2, SL)
    }
    
    # Process messages chronologically
    for msg in messages:
        order = msg['order']
        order_status = order.get('orderStatus', '')
        stop_order_type = order.get('stopOrderType', '')
        side = order.get('side', '')
        qty = safe_float(order.get('qty', 0))
        trigger_price = safe_float(order.get('triggerPrice', 0))
        closed_pnl = safe_float(order.get('closedPnl', 0))
        avg_price = safe_float(order.get('avgPrice', 0))
        cum_exec_qty = safe_float(order.get('cumExecQty', 0))
        timestamp = msg['timestamp']
        
        if side:
            signal['side'] = side
        
        # Track entry
        if order_status == "Filled" and stop_order_type == "" and avg_price > 0:
            if signal['entry_price'] == 0:
                signal['entry_price'] = avg_price
                signal['entry_qty'] = cum_exec_qty
                signal['tp1_qty'] = cum_exec_qty * 0.4
                signal['tp2_qty'] = cum_exec_qty * 0.6
        
        # Track TP prices from PartialTakeProfit orders
        if stop_order_type == "PartialTakeProfit" and trigger_price > 0:
            if signal['tp1_price'] == 0:
                signal['tp1_price'] = trigger_price
            elif signal['tp2_price'] == 0:
                # Determine which is TP1 and which is TP2 based on price
                if signal['side'] == "Buy":
                    # For Buy: TP1 < TP2 (lower price = TP1, higher = TP2)
                    if trigger_price < signal['tp1_price']:
                        signal['tp2_price'] = signal['tp1_price']
                        signal['tp1_price'] = trigger_price
                    else:
                        signal['tp2_price'] = trigger_price
                else:  # Sell
                    # For Sell: TP1 > TP2 (higher price = TP1, lower = TP2)
                    if trigger_price > signal['tp1_price']:
                        signal['tp2_price'] = signal['tp1_price']
                        signal['tp1_price'] = trigger_price
                    else:
                        signal['tp2_price'] = trigger_price
        
        # Track SL price
        if stop_order_type == "StopLoss" and trigger_price > 0:
            if signal['sl_price'] == 0:
                signal['sl_price'] = trigger_price
        
        # Track filled TP orders
        if order_status == "Filled" and stop_order_type == "PartialTakeProfit":
            # Identify TP1 or TP2
            tolerance = 0.001
            tp_level = None
            
            if signal['tp1_price'] > 0 and abs(trigger_price - signal['tp1_price']) / signal['tp1_price'] < tolerance:
                tp_level = "TP1"
            elif signal['tp2_price'] > 0 and abs(trigger_price - signal['tp2_price']) / signal['tp2_price'] < tolerance:
                tp_level = "TP2"
            else:
                # If we can't identify, use sequence (first = TP1)
                tp1_count = sum(1 for e in signal['events'] if e['type'] == 'TP1')
                tp2_count = sum(1 for e in signal['events'] if e['type'] == 'TP2')
                if tp1_count == 0:
                    tp_level = "TP1"
                elif tp2_count == 0:
                    tp_level = "TP2"
            
            if tp_level:
                signal['events'].append({
                    'type': tp_level,
                    'timestamp': timestamp,
                    'exec_price': avg_price if avg_price > 0 else trigger_price,
                    'exec_qty': cum_exec_qty,
                    'closed_pnl': closed_pnl,
                })
        
        # Track filled SL orders
        if order_status == "Filled" and stop_order_type == "StopLoss":
            signal['events'].append({
                'type': 'SL',
                'timestamp': timestamp,
                'exec_price': avg_price if avg_price > 0 else trigger_price,
                'exec_qty': cum_exec_qty,
                'closed_pnl': closed_pnl,
            })
    
    if signal['entry_price'] > 0:
        signals.append(signal)

# Calculate results
current_strategy_results = {
    'total_signals': len(signals),
    'tp1_only': 0,
    'tp2_reached': 0,
    'sl_before_tp1': 0,
    'sl_after_tp1': 0,
    'total_pnl': 0.0,
    'total_pnl_tp1': 0.0,
    'total_pnl_tp2': 0.0,
    'total_pnl_sl': 0.0,
    'signals_detail': []
}

alternative_strategy_results = {
    'total_signals': len(signals),
    'tp1_reached': 0,
    'sl_before_tp1': 0,
    'sl_after_tp1': 0,
    'total_pnl': 0.0,
    'total_pnl_tp1': 0.0,
    'total_pnl_sl': 0.0,
    'signals_detail': []
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
    
    # Find events
    tp1_event = next((e for e in signal['events'] if e['type'] == 'TP1'), None)
    tp2_event = next((e for e in signal['events'] if e['type'] == 'TP2'), None)
    sl_event = next((e for e in signal['events'] if e['type'] == 'SL'), None)
    
    # Determine event order
    events_ordered = sorted(signal['events'], key=lambda x: x['timestamp'])
    
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
    
    if sl_event and (not tp1_event or sl_event['timestamp'] < tp1_event['timestamp']):
        # SL before TP1
        current_strategy_results['sl_before_tp1'] += 1
        current_detail['outcome'] = 'SL before TP1'
        if sl_event['closed_pnl'] != 0:
            current_pnl = sl_event['closed_pnl']
            current_detail['sl_pnl'] = sl_event['closed_pnl']
        else:
            current_pnl = calculate_pnl(entry_price, sl_event['exec_price'], entry_qty, side)
            current_detail['sl_pnl'] = current_pnl
        current_strategy_results['total_pnl_sl'] += current_pnl
        
    elif tp1_event:
        # TP1 was hit
        if tp1_event['closed_pnl'] != 0:
            tp1_pnl = tp1_event['closed_pnl']
        else:
            tp1_pnl = calculate_pnl(entry_price, tp1_event['exec_price'], tp1_qty, side)
        current_pnl += tp1_pnl
        current_detail['tp1_pnl'] = tp1_pnl
        current_strategy_results['total_pnl_tp1'] += tp1_pnl
        
        if tp2_event and tp2_event['timestamp'] > tp1_event['timestamp']:
            # TP2 was also hit
            current_strategy_results['tp2_reached'] += 1
            current_detail['outcome'] = 'TP1 + TP2'
            if tp2_event['closed_pnl'] != 0:
                tp2_pnl = tp2_event['closed_pnl']
            else:
                tp2_pnl = calculate_pnl(entry_price, tp2_event['exec_price'], tp2_qty, side)
            current_pnl += tp2_pnl
            current_detail['tp2_pnl'] = tp2_pnl
            current_strategy_results['total_pnl_tp2'] += tp2_pnl
        elif sl_event and sl_event['timestamp'] > tp1_event['timestamp']:
            # SL after TP1
            current_strategy_results['sl_after_tp1'] += 1
            current_detail['outcome'] = 'TP1 + SL'
            if sl_event['closed_pnl'] != 0:
                # closedPnl is for remaining qty (60%)
                sl_pnl = sl_event['closed_pnl']
            else:
                sl_pnl = calculate_pnl(entry_price, sl_event['exec_price'], tp2_qty, side)
            current_pnl += sl_pnl
            current_detail['sl_pnl'] = sl_pnl
            current_strategy_results['total_pnl_sl'] += sl_pnl
        else:
            # Only TP1, position still open
            current_strategy_results['tp1_only'] += 1
            current_detail['outcome'] = 'TP1 only (open)'
    
    current_detail['pnl'] = current_pnl
    current_strategy_results['total_pnl'] += current_pnl
    current_strategy_results['signals_detail'].append(current_detail)
    
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
        alternative_strategy_results['sl_before_tp1'] += 1
        alt_detail['outcome'] = 'SL before TP1'
        if sl_event['closed_pnl'] != 0:
            alt_pnl = sl_event['closed_pnl']
            alt_detail['sl_pnl'] = sl_event['closed_pnl']
        else:
            alt_pnl = calculate_pnl(entry_price, sl_event['exec_price'], entry_qty, side)
            alt_detail['sl_pnl'] = alt_pnl
        alternative_strategy_results['total_pnl_sl'] += alt_pnl
        
    elif tp1_event:
        # TP1 was hit - take 100% at TP1
        alternative_strategy_results['tp1_reached'] += 1
        alt_detail['outcome'] = 'TP1 (100%)'
        # Calculate PnL for full quantity at TP1
        if tp1_event['closed_pnl'] != 0:
            # Scale the closedPnl from 40% to 100%
            alt_pnl = tp1_event['closed_pnl'] * (entry_qty / tp1_qty) if tp1_qty > 0 else 0
        else:
            alt_pnl = calculate_pnl(entry_price, tp1_event['exec_price'], entry_qty, side)
        alt_detail['tp1_pnl'] = alt_pnl
        alternative_strategy_results['total_pnl_tp1'] += alt_pnl
    
    alt_detail['pnl'] = alt_pnl
    alternative_strategy_results['total_pnl'] += alt_pnl
    alternative_strategy_results['signals_detail'].append(alt_detail)

# Print detailed results
print("=" * 100)
print("Detailed Analysis of TP1 and TP2 Strategies")
print("=" * 100)
print()

print("Current Strategy: 40% TP1 + 60% TP2")
print("-" * 100)
print(f"Total Signals: {current_strategy_results['total_signals']}")
print(f"Signals that reached TP1: {current_strategy_results['tp1_only'] + current_strategy_results['tp2_reached']}")
print(f"  - Only TP1 (TP2 not reached): {current_strategy_results['tp1_only']}")
print(f"  - Reached TP2: {current_strategy_results['tp2_reached']}")
print(f"Signals that hit SL:")
print(f"  - Before TP1: {current_strategy_results['sl_before_tp1']}")
print(f"  - After TP1: {current_strategy_results['sl_after_tp1']}")
print()
print(f"Total PnL: {current_strategy_results['total_pnl']:.2f} USDT")
print(f"  - From TP1: {current_strategy_results['total_pnl_tp1']:.2f} USDT")
print(f"  - From TP2: {current_strategy_results['total_pnl_tp2']:.2f} USDT")
print(f"  - From SL: {current_strategy_results['total_pnl_sl']:.2f} USDT")
print()

print("\nSignal Details (Current Strategy):")
print("-" * 100)
for detail in current_strategy_results['signals_detail']:
    print(f"{detail['symbol']:12} | {detail['outcome']:20} | "
          f"PnL: {detail['pnl']:8.2f} | "
          f"TP1: {detail['tp1_pnl']:8.2f} | "
          f"TP2: {detail['tp2_pnl']:8.2f} | "
          f"SL: {detail['sl_pnl']:8.2f}")

print()
print("\nAlternative Strategy: 100% TP1")
print("-" * 100)
print(f"Total Signals: {alternative_strategy_results['total_signals']}")
print(f"Signals that reached TP1: {alternative_strategy_results['tp1_reached']}")
print(f"Signals that hit SL:")
print(f"  - Before TP1: {alternative_strategy_results['sl_before_tp1']}")
print(f"  - After TP1: {alternative_strategy_results['sl_after_tp1']}")
print()
print(f"Total PnL: {alternative_strategy_results['total_pnl']:.2f} USDT")
print(f"  - From TP1: {alternative_strategy_results['total_pnl_tp1']:.2f} USDT")
print(f"  - From SL: {alternative_strategy_results['total_pnl_sl']:.2f} USDT")
print()

print("\nSignal Details (Alternative Strategy):")
print("-" * 100)
for detail in alternative_strategy_results['signals_detail']:
    print(f"{detail['symbol']:12} | {detail['outcome']:20} | "
          f"PnL: {detail['pnl']:8.2f} | "
          f"TP1: {detail['tp1_pnl']:8.2f} | "
          f"SL: {detail['sl_pnl']:8.2f}")

print()
print("=" * 100)
print("Comparison")
print("=" * 100)
diff = alternative_strategy_results['total_pnl'] - current_strategy_results['total_pnl']
diff_pct = (diff / abs(current_strategy_results['total_pnl']) * 100) if current_strategy_results['total_pnl'] != 0 else 0

print(f"PnL Difference: {diff:+.2f} USDT ({diff_pct:+.2f}%)")
if diff > 0:
    print(f"\n✓ 100% TP1 strategy is BETTER! ({diff:.2f} USDT more profit)")
    print(f"  You would have made {diff:.2f} USDT more by using 100% TP1")
elif diff < 0:
    print(f"\n✓ Current strategy (40% TP1 + 60% TP2) is BETTER! ({abs(diff):.2f} USDT more profit)")
    print(f"  Current strategy saved you {abs(diff):.2f} USDT")
else:
    print("\n= Both strategies have the same result")

print()
print("=" * 100)
