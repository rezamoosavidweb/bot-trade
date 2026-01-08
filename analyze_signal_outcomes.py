"""
تحلیل نتایج هر سیگنال
تعیین اینکه هر سیگنال به TP1، TP2، SL اولیه، یا SL آپدیت شده بعد از TP1 رسیده است
"""

import json
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional
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

# Collect all events
all_events = []

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
        order_id = order.get('orderId', '')
        
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
                all_events.append({
                    'symbol': symbol,
                    'timestamp': timestamp,
                    'type': event_type,
                    'side': side,
                    'stop_order_type': stop_order_type,
                    'qty': qty,
                    'trigger_price': trigger_price,
                    'closed_pnl': closed_pnl,
                    'avg_price': avg_price,
                    'exec_qty': cum_exec_qty,
                    'order_id': order_id,
                })

# Sort all events by timestamp
all_events.sort(key=lambda x: x['timestamp'])

# Group events by position (entry-based grouping)
# Each position starts with an ENTRY event
positions = []
current_position = None

for event in all_events:
    if event['type'] == "ENTRY":
        # Start a new position
        if current_position:
            positions.append(current_position)
        current_position = {
            'symbol': event['symbol'],
            'entry_timestamp': event['timestamp'],
            'entry_price': event['avg_price'],
            'entry_qty': event['exec_qty'],
            'side': event['side'],
            'entry_order_id': event['order_id'],
            'events': [event],
        }
    elif current_position and event['symbol'] == current_position['symbol']:
        # Add event to current position if it's for the same symbol
        # and happened after entry
        if event['timestamp'] >= current_position['entry_timestamp']:
            current_position['events'].append(event)
        # If event happened before entry, it's from a previous position - ignore it
    elif current_position and event['symbol'] != current_position['symbol']:
        # Different symbol - close current position and start new one
        positions.append(current_position)
        current_position = None

# Add last position
if current_position:
    positions.append(current_position)

# Process each position
signals_data = []

for position in positions:
    signal = {
        'symbol': position['symbol'],
        'side': position['side'],
        'entry_price': position['entry_price'],
        'entry_qty': position['entry_qty'],
        'entry_timestamp': position['entry_timestamp'],
        'tp1_price': 0,
        'tp2_price': 0,
        'tp1_qty': 0,
        'tp2_qty': 0,
        'tp1_hit': False,
        'tp2_hit': False,
        'sl_initial_hit': False,
        'sl_updated_hit': False,
        'tp1_timestamp': '',
        'tp2_timestamp': '',
        'sl_initial_timestamp': '',
        'sl_updated_timestamp': '',
        'tp1_pnl': 0.0,
        'tp2_pnl': 0.0,
        'sl_initial_pnl': 0.0,
        'sl_updated_pnl': 0.0,
        'tp1_exec_price': 0.0,
        'tp2_exec_price': 0.0,
        'sl_initial_exec_price': 0.0,
        'sl_updated_exec_price': 0.0,
        'outcome': '',
        'events_sequence': [],
    }
    
    signal['tp1_qty'] = position['entry_qty'] * 0.4
    signal['tp2_qty'] = position['entry_qty'] * 0.6
    
    # Process events in order
    tp_events = []
    sl_events = []
    
    for event in position['events']:
        if event['type'] == "ENTRY":
            signal['events_sequence'].append({
                'type': 'ENTRY',
                'timestamp': event['timestamp'],
                'price': event['avg_price'],
                'qty': event['exec_qty'],
                'order_id': event['order_id'],
            })
        elif event['type'] == "TP":
            tp_events.append(event)
            signal['events_sequence'].append({
                'type': 'TP',
                'timestamp': event['timestamp'],
                'trigger_price': event['trigger_price'],
                'exec_price': event['avg_price'],
                'exec_qty': event['exec_qty'],
                'closed_pnl': event['closed_pnl'],
                'order_id': event['order_id'],
            })
            # Track TP prices from trigger_price
            if event['trigger_price'] > 0:
                if signal['tp1_price'] == 0:
                    signal['tp1_price'] = event['trigger_price']
                elif signal['tp2_price'] == 0:
                    signal['tp2_price'] = event['trigger_price']
        elif event['type'] == "SL":
            sl_events.append(event)
            signal['events_sequence'].append({
                'type': 'SL',
                'timestamp': event['timestamp'],
                'trigger_price': event['trigger_price'],
                'exec_price': event['avg_price'],
                'exec_qty': event['exec_qty'],
                'closed_pnl': event['closed_pnl'],
                'order_id': event['order_id'],
            })
    
    # Sort TP and SL events by timestamp
    tp_events_sorted = sorted(tp_events, key=lambda x: x['timestamp'])
    sl_events_sorted = sorted(sl_events, key=lambda x: x['timestamp'])
    
    # Identify TP1 and TP2
    tp1_event = None
    tp2_event = None
    
    if len(tp_events_sorted) > 0:
        tp1_event = tp_events_sorted[0]
        signal['tp1_hit'] = True
        signal['tp1_timestamp'] = tp1_event['timestamp']
        signal['tp1_exec_price'] = tp1_event['avg_price']
        signal['tp1_pnl'] = tp1_event['closed_pnl']
        
        if len(tp_events_sorted) > 1:
            tp2_event = tp_events_sorted[1]
            signal['tp2_hit'] = True
            signal['tp2_timestamp'] = tp2_event['timestamp']
            signal['tp2_exec_price'] = tp2_event['avg_price']
            signal['tp2_pnl'] = tp2_event['closed_pnl']
    
    # Identify SL events
    if len(sl_events_sorted) > 0:
        sl_event = sl_events_sorted[0]
        
        # Check if SL happened before or after TP1
        if not tp1_event or sl_event['timestamp'] < tp1_event['timestamp']:
            # SL before TP1 (initial SL)
            signal['sl_initial_hit'] = True
            signal['sl_initial_timestamp'] = sl_event['timestamp']
            signal['sl_initial_exec_price'] = sl_event['avg_price']
            signal['sl_initial_pnl'] = sl_event['closed_pnl']
        else:
            # SL after TP1 (updated SL)
            signal['sl_updated_hit'] = True
            signal['sl_updated_timestamp'] = sl_event['timestamp']
            signal['sl_updated_exec_price'] = sl_event['avg_price']
            signal['sl_updated_pnl'] = sl_event['closed_pnl']
    
    # Determine outcome
    if signal['sl_initial_hit']:
        signal['outcome'] = 'SL_Initial'
    elif signal['tp1_hit'] and signal['tp2_hit']:
        signal['outcome'] = 'TP1_TP2'
    elif signal['tp1_hit'] and signal['sl_updated_hit']:
        signal['outcome'] = 'TP1_SL_Updated'
    elif signal['tp1_hit']:
        signal['outcome'] = 'TP1_Only'
    else:
        signal['outcome'] = 'Open'
    
    signals_data.append(signal)

# Create summary statistics
summary = {
    'total_signals': len(signals_data),
    'tp1_reached': sum(1 for s in signals_data if s['tp1_hit']),
    'tp2_reached': sum(1 for s in signals_data if s['tp2_hit']),
    'sl_initial_hit': sum(1 for s in signals_data if s['sl_initial_hit']),
    'sl_updated_hit': sum(1 for s in signals_data if s['sl_updated_hit']),
    'outcomes': {
        'SL_Initial': sum(1 for s in signals_data if s['outcome'] == 'SL_Initial'),
        'TP1_TP2': sum(1 for s in signals_data if s['outcome'] == 'TP1_TP2'),
        'TP1_SL_Updated': sum(1 for s in signals_data if s['outcome'] == 'TP1_SL_Updated'),
        'TP1_Only': sum(1 for s in signals_data if s['outcome'] == 'TP1_Only'),
        'Open': sum(1 for s in signals_data if s['outcome'] == 'Open'),
    }
}

# Prepare output data
output_data = {
    'analysis_date': datetime.now().isoformat(),
    'summary': summary,
    'signals': signals_data
}

# Save to JSON file
output_file = 'signal_outcomes.json'
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(output_data, f, indent=2, ensure_ascii=False)

# Print summary
print("=" * 100)
print("Signal Outcomes Analysis")
print("=" * 100)
print()
print(f"Total Signals Analyzed: {summary['total_signals']}")
print()
print("Outcomes Summary:")
print("-" * 100)
print(f"  SL Initial (before TP1):        {summary['outcomes']['SL_Initial']:3d}")
print(f"  TP1 Only (TP2 not reached):    {summary['outcomes']['TP1_Only']:3d}")
print(f"  TP1 + SL Updated (after TP1):  {summary['outcomes']['TP1_SL_Updated']:3d}")
print(f"  TP1 + TP2:                      {summary['outcomes']['TP1_TP2']:3d}")
print(f"  Open (no TP/SL hit yet):        {summary['outcomes']['Open']:3d}")
print()
print("Event Counts:")
print("-" * 100)
print(f"  TP1 Reached:     {summary['tp1_reached']:3d}")
print(f"  TP2 Reached:     {summary['tp2_reached']:3d}")
print(f"  SL Initial Hit:  {summary['sl_initial_hit']:3d}")
print(f"  SL Updated Hit:  {summary['sl_updated_hit']:3d}")
print()
print(f"Results saved to: {output_file}")
print()
print("=" * 100)
print("Signal Details:")
print("=" * 100)
print(f"{'Symbol':<12} | {'Side':<4} | {'Outcome':<20} | {'TP1':<5} | {'TP2':<5} | {'SL Init':<7} | {'SL Upd':<7}")
print("-" * 100)

for signal in signals_data:
    tp1_str = "Yes" if signal['tp1_hit'] else "No"
    tp2_str = "Yes" if signal['tp2_hit'] else "No"
    sl_init_str = "Yes" if signal['sl_initial_hit'] else "No"
    sl_upd_str = "Yes" if signal['sl_updated_hit'] else "No"
    
    print(f"{signal['symbol']:<12} | {signal['side']:<4} | {signal['outcome']:<20} | "
          f"{tp1_str:<5} | {tp2_str:<5} | {sl_init_str:<7} | {sl_upd_str:<7}")

print()
print("=" * 100)
