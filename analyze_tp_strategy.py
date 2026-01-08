"""
تحلیل استراتژی TP1 و TP2
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

# Track positions and their outcomes
positions = {}  # symbol -> position info

def safe_float(value):
    """Safely convert to float"""
    try:
        return float(value) if value else 0.0
    except (ValueError, TypeError):
        return 0.0

# Process all messages chronologically
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
        cum_exec_value = safe_float(order.get('cumExecValue', 0))
        
        # Initialize position tracking
        if symbol not in positions:
            positions[symbol] = {
                'symbol': symbol,
                'side': side,
                'entry_price': 0,
                'total_qty': 0,
                'tp1_price': 0,
                'tp2_price': 0,
                'sl_price': 0,
                'tp1_qty': 0,
                'tp2_qty': 0,
                'tp1_hit': False,
                'tp2_hit': False,
                'sl_hit': False,
                'tp1_pnl': 0,
                'tp2_pnl': 0,
                'sl_pnl': 0,
                'tp1_exec_qty': 0,
                'tp2_exec_qty': 0,
                'sl_exec_qty': 0,
                'tp1_exec_price': 0,
                'tp2_exec_price': 0,
                'sl_exec_price': 0,
                'sl_updated_after_tp1': False,
                'tp_orders': [],  # Track all TP orders to identify TP1 vs TP2
                'sl_orders': [],  # Track SL orders
            }
        
        pos = positions[symbol]
        pos['side'] = side
        
        # Track entry from filled market orders (not stop orders)
        if order_status == "Filled" and stop_order_type == "" and avg_price > 0:
            if pos['entry_price'] == 0:
                pos['entry_price'] = avg_price
            pos['total_qty'] = max(pos['total_qty'], cum_exec_qty)
            # Calculate TP quantities (40% TP1, 60% TP2)
            pos['tp1_qty'] = pos['total_qty'] * 0.4
            pos['tp2_qty'] = pos['total_qty'] * 0.6
        
        # Track TP orders (PartialTakeProfit)
        if stop_order_type == "PartialTakeProfit" and trigger_price > 0:
            tp_order = {
                'trigger_price': trigger_price,
                'qty': qty,
                'status': order_status,
                'closed_pnl': closed_pnl,
                'exec_qty': cum_exec_qty,
                'exec_price': avg_price,
                'timestamp': timestamp
            }
            pos['tp_orders'].append(tp_order)
            
            # Identify TP1 and TP2 based on trigger price
            # For Buy: TP1 < TP2 (higher prices)
            # For Sell: TP1 > TP2 (lower prices)
            if pos['side'] == "Buy":
                # Higher trigger price = TP2, lower = TP1
                if pos['tp1_price'] == 0 or trigger_price < pos['tp1_price']:
                    pos['tp1_price'] = trigger_price
                if pos['tp2_price'] == 0 or trigger_price > pos['tp2_price']:
                    pos['tp2_price'] = trigger_price
            else:  # Sell
                # Lower trigger price = TP2, higher = TP1
                if pos['tp1_price'] == 0 or trigger_price > pos['tp1_price']:
                    pos['tp1_price'] = trigger_price
                if pos['tp2_price'] == 0 or trigger_price < pos['tp2_price']:
                    pos['tp2_price'] = trigger_price
        
        # Track SL orders
        if stop_order_type == "StopLoss":
            sl_order = {
                'trigger_price': trigger_price,
                'qty': qty,
                'status': order_status,
                'closed_pnl': closed_pnl,
                'exec_qty': cum_exec_qty,
                'exec_price': avg_price,
                'timestamp': timestamp
            }
            pos['sl_orders'].append(sl_order)
            
            if trigger_price > 0:
                if pos['sl_price'] == 0:
                    pos['sl_price'] = trigger_price
                else:
                    # This might be an updated SL after TP1
                    pos['sl_updated_after_tp1'] = True
                    pos['sl_price'] = trigger_price
        
        # Track filled TP orders
        if order_status == "Filled" and stop_order_type == "PartialTakeProfit":
            # Identify which TP this is based on trigger price
            tolerance = 0.001
            is_tp1 = False
            is_tp2 = False
            
            if pos['tp1_price'] > 0:
                if abs(trigger_price - pos['tp1_price']) / pos['tp1_price'] < tolerance:
                    is_tp1 = True
            if pos['tp2_price'] > 0:
                if abs(trigger_price - pos['tp2_price']) / pos['tp2_price'] < tolerance:
                    is_tp2 = True
            
            # If we can't identify by price, use order sequence (first = TP1, second = TP2)
            if not is_tp1 and not is_tp2:
                if not pos['tp1_hit']:
                    is_tp1 = True
                elif not pos['tp2_hit']:
                    is_tp2 = True
            
            if is_tp1 and not pos['tp1_hit']:
                pos['tp1_hit'] = True
                pos['tp1_exec_price'] = avg_price if avg_price > 0 else trigger_price
                pos['tp1_exec_qty'] = cum_exec_qty
                # Use closedPnl if available, otherwise calculate
                if closed_pnl != 0:
                    pos['tp1_pnl'] = closed_pnl
                else:
                    # Calculate PnL manually
                    if pos['side'] == "Buy":
                        pos['tp1_pnl'] = (pos['tp1_exec_price'] - pos['entry_price']) * cum_exec_qty
                    else:
                        pos['tp1_pnl'] = (pos['entry_price'] - pos['tp1_exec_price']) * cum_exec_qty
            elif is_tp2 and not pos['tp2_hit']:
                pos['tp2_hit'] = True
                pos['tp2_exec_price'] = avg_price if avg_price > 0 else trigger_price
                pos['tp2_exec_qty'] = cum_exec_qty
                # Use closedPnl if available
                if closed_pnl != 0:
                    pos['tp2_pnl'] = closed_pnl
                else:
                    # Calculate PnL manually
                    if pos['side'] == "Buy":
                        pos['tp2_pnl'] = (pos['tp2_exec_price'] - pos['entry_price']) * cum_exec_qty
                    else:
                        pos['tp2_pnl'] = (pos['entry_price'] - pos['tp2_exec_price']) * cum_exec_qty
        
        # Track filled SL orders
        if order_status == "Filled" and stop_order_type == "StopLoss":
            pos['sl_hit'] = True
            pos['sl_exec_price'] = avg_price if avg_price > 0 else trigger_price
            pos['sl_exec_qty'] = cum_exec_qty
            # Use closedPnl if available
            if closed_pnl != 0:
                pos['sl_pnl'] = closed_pnl
            else:
                # Calculate PnL manually
                if pos['side'] == "Buy":
                    pos['sl_pnl'] = (pos['sl_exec_price'] - pos['entry_price']) * cum_exec_qty
                else:
                    pos['sl_pnl'] = (pos['entry_price'] - pos['sl_exec_price']) * cum_exec_qty

# Now calculate results for each strategy
current_strategy_results = {
    'total_signals': 0,
    'tp1_only': 0,
    'tp2_reached': 0,
    'sl_before_tp1': 0,
    'sl_after_tp1': 0,
    'total_pnl': 0.0,
    'total_pnl_tp1': 0.0,
    'total_pnl_tp2': 0.0,
    'total_pnl_sl': 0.0
}

alternative_strategy_results = {
    'total_signals': 0,
    'tp1_reached': 0,
    'sl_before_tp1': 0,
    'sl_after_tp1': 0,
    'total_pnl': 0.0,
    'total_pnl_tp1': 0.0,
    'total_pnl_sl': 0.0
}

# Process each position
for symbol, pos in positions.items():
    if pos['entry_price'] == 0 or pos['total_qty'] == 0:
        continue  # Skip incomplete positions
    
    entry_price = pos['entry_price']
    total_qty = pos['total_qty']
    side = pos['side']
    
    # Helper function to calculate PnL
    def calculate_pnl(entry: float, exit: float, qty: float, side: str) -> float:
        """Calculate PnL"""
        if side == "Buy":
            return (exit - entry) * qty
        else:  # Sell
            return (entry - exit) * qty
    
    # Current strategy (40% TP1, 60% TP2)
    current_strategy_results['total_signals'] += 1
    
    if pos['sl_hit'] and not pos['tp1_hit']:
        # SL hit before TP1 - lose 100% at SL
        current_strategy_results['sl_before_tp1'] += 1
        sl_pnl = pos['sl_pnl'] if pos['sl_pnl'] != 0 else calculate_pnl(
            entry_price, pos['sl_exec_price'], total_qty, side
        )
        current_strategy_results['total_pnl'] += sl_pnl
        current_strategy_results['total_pnl_sl'] += sl_pnl
        
    elif pos['tp1_hit']:
        # TP1 was hit - take 40% profit at TP1
        tp1_pnl = pos['tp1_pnl'] if pos['tp1_pnl'] != 0 else calculate_pnl(
            entry_price, pos['tp1_exec_price'], pos['tp1_qty'], side
        )
        current_strategy_results['total_pnl'] += tp1_pnl
        current_strategy_results['total_pnl_tp1'] += tp1_pnl
        
        if pos['tp2_hit']:
            # TP2 was also hit - take 60% profit at TP2
            current_strategy_results['tp2_reached'] += 1
            tp2_pnl = pos['tp2_pnl'] if pos['tp2_pnl'] != 0 else calculate_pnl(
                entry_price, pos['tp2_exec_price'], pos['tp2_qty'], side
            )
            current_strategy_results['total_pnl'] += tp2_pnl
            current_strategy_results['total_pnl_tp2'] += tp2_pnl
        elif pos['sl_hit']:
            # SL hit after TP1 - lose 60% at SL
            current_strategy_results['sl_after_tp1'] += 1
            remaining_qty = pos['tp2_qty']  # 60% that didn't reach TP2
            sl_pnl = pos['sl_pnl'] if pos['sl_pnl'] != 0 else calculate_pnl(
                entry_price, pos['sl_exec_price'], remaining_qty, side
            )
            current_strategy_results['total_pnl'] += sl_pnl
            current_strategy_results['total_pnl_sl'] += sl_pnl
        else:
            # TP1 hit but TP2 and SL not hit (position still open with 60% remaining)
            current_strategy_results['tp1_only'] += 1
            # For open positions, we don't count the remaining 60% in PnL
    
    # Alternative strategy (100% TP1)
    alternative_strategy_results['total_signals'] += 1
    
    if pos['sl_hit'] and not pos['tp1_hit']:
        # SL hit before TP1 - lose 100% at SL
        alternative_strategy_results['sl_before_tp1'] += 1
        sl_pnl = pos['sl_pnl'] if pos['sl_pnl'] != 0 else calculate_pnl(
            entry_price, pos['sl_exec_price'], total_qty, side
        )
        alternative_strategy_results['total_pnl'] += sl_pnl
        alternative_strategy_results['total_pnl_sl'] += sl_pnl
        
    elif pos['tp1_hit']:
        # TP1 was hit - take 100% profit at TP1
        alternative_strategy_results['tp1_reached'] += 1
        # Calculate PnL for full quantity at TP1 price
        tp1_pnl = calculate_pnl(
            entry_price, pos['tp1_exec_price'], total_qty, side
        )
        alternative_strategy_results['total_pnl'] += tp1_pnl
        alternative_strategy_results['total_pnl_tp1'] += tp1_pnl
    else:
        # Position still open, no TP1 or SL hit yet
        pass

# Print results
print("=" * 80)
print("Analysis of TP1 and TP2 Strategies")
print("=" * 80)
print()

print("Current Strategy: 40% TP1 + 60% TP2")
print("-" * 80)
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

print("Alternative Strategy: 100% TP1")
print("-" * 80)
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

print("=" * 80)
print("Comparison")
print("=" * 80)
diff = alternative_strategy_results['total_pnl'] - current_strategy_results['total_pnl']
diff_pct = (diff / abs(current_strategy_results['total_pnl']) * 100) if current_strategy_results['total_pnl'] != 0 else 0

print(f"PnL Difference: {diff:+.2f} USDT ({diff_pct:+.2f}%)")
if diff > 0:
    print(f"100% TP1 strategy is better! ({diff:.2f} USDT more profit)")
elif diff < 0:
    print(f"Current strategy (40% TP1 + 60% TP2) is better! ({abs(diff):.2f} USDT more profit)")
else:
    print("Both strategies have the same result")

print()
print("=" * 80)
