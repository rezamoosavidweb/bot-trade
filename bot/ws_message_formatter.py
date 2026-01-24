"""
WebSocket Message Formatter
Handles formatting and processing of Bybit WebSocket order messages.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from config import (
    TARGET_CHANNEL,
    FIXED_MARGIN_USDT,
    SL_UPDATE_DELAY_MINUTES,
)
from clients import telClient
from api import get_positions, set_trading_stop, amend_order, get_sl_order_id
from capital_tracker import track_position_closed, track_rejected_order
from liquidity_analyzer import update_order_fill, get_24h_ticker
from logger import log_print
from cache import (
    get_open_positions,
    add_open_position,
    remove_open_position,
    get_position_entry_time,
    set_position_entry_time,
    remove_position_entry_time,
    get_position_tp_prices,
    remove_position_tp_prices,
    get_position_remaining_sizes,
    subtract_position_remaining_size,
    remove_position_remaining_size,
    set_pending_sl_update,
    get_pending_sl_update,
    remove_pending_sl_update,
    get_pending_sl_updates,
    get_position_entry_times,
)


# ---------------- ENUMS ---------------- #
ORDER_STATUS = {
    "New": "✅ Order placed successfully",
    "PartiallyFilled": "⏳ Partially filled",
    "Untriggered": "⏸️ Conditional order created (not triggered)",
    "Rejected": "❌ Order rejected",
    "PartiallyFilledCanceled": "⚠️ Partially filled then cancelled",
    "Filled": "✅ Order filled",
    "Cancelled": "❌ Order cancelled",
    "Triggered": "🎯 Conditional order triggered",
    "Deactivated": "🔴 Order deactivated",
}

CREATE_TYPE = {
    "CreateByUser": "👤 User",
    "CreateByFutureSpread": "📊 Spread order",
    "CreateByAdminClosing": "👨‍💼 Admin closing",
    "CreateBySettle": "📅 Settlement",
    "CreateByStopOrder": "🛑 Stop order",
    "CreateByTakeProfit": "🎯 Take profit",
    "CreateByPartialTakeProfit": "🎯 Partial take profit",
    "CreateByStopLoss": "🛑 Stop loss",
    "CreateByPartialStopLoss": "🛑 Partial stop loss",
    "CreateByTrailingStop": "📉 Trailing stop",
    "CreateByTrailingProfit": "📈 Trailing profit",
    "CreateByLiq": "💥 Liquidation",
    "CreateByTakeOver_PassThrough": "⚡ Takeover",
    "CreateByAdl_PassThrough": "🔄 ADL",
    "CreateByBlock_PassThrough": "🔷 Block trade",
    "CreateByBlockTradeMovePosition_PassThrough": "📍 Position move",
    "CreateByClosing": "🔒 Closing",
    "CreateByFGridBot": "🤖 Grid bot",
    "CloseByFGridBot": "🤖 Grid bot close",
    "CreateByTWAP": "⏱️ TWAP",
    "CreateByTVSignal": "📺 TradingView",
    "CreateByMmRateClose": "💹 MM rate",
    "CreateByMartingaleBot": "🎰 Martingale bot",
    "CloseByMartingaleBot": "🎰 Martingale close",
    "CreateByIceBerg": "🧊 Iceberg",
    "CreateByArbitrage": "⚖️ Arbitrage",
    "CreateByDdh": "📊 Delta hedge",
    "CreateByBboOrder": "📈 BBO order",
}

CANCEL_TYPE = {
    "CancelByUser": "👤 User cancelled",
    "CancelByReduceOnly": "🔄 Reduce-only",
    "CancelByPrepareLiq": "💥 Prevent liquidation",
    "CancelAllBeforeLiq": "💥 Prevent liquidation (all)",
    "CancelByPrepareAdl": "🔄 ADL preparation",
    "CancelAllBeforeAdl": "🔄 ADL preparation (all)",
    "CancelByAdmin": "👨‍💼 Admin",
    "CancelBySettle": "📅 Settlement",
    "CancelByTpSlTsClear": "🧹 TP/SL cleared",
    "CancelBySmp": "⚡ SMP",
    "CancelByDCP": "🔴 DCP",
    "CancelByRebalance": "⚖️ Rebalance",
    "CancelByOCOTpCanceledBySlTriggered": "🛑 TP cancelled (SL triggered)",
    "CancelByOCOSlCanceledByTpTriggered": "🎯 SL cancelled (TP triggered)",
}

POSITION_IDX = {
    0: "One-way",
    1: "Hedge (Buy)",
    2: "Hedge (Sell)",
}

REJECT_REASON = {
    "EC_NoError": "✅ No error",
    "EC_Others": "❌ Other error",
    "EC_UnknownMessageType": "❓ Unknown message type",
    "EC_MissingClOrdID": "❌ Missing ClOrdID",
    "EC_MissingOrigClOrdID": "❌ Missing OrigClOrdID",
    "EC_ClOrdIDOrigClOrdIDAreTheSame": "❌ Duplicate ClOrdID",
    "EC_DuplicatedClOrdID": "❌ Duplicated ClOrdID",
    "EC_OrigClOrdIDDoesNotExist": "❌ OrigClOrdID not found",
    "EC_TooLateToCancel": "⏰ Too late to cancel",
    "EC_UnknownOrderType": "❓ Unknown order type",
    "EC_UnknownSide": "❓ Unknown side",
    "EC_UnknownTimeInForce": "❓ Unknown time in force",
    "EC_WronglyRouted": "❌ Wrongly routed",
    "EC_MarketOrderPriceIsNotZero": "❌ Market order price must be zero",
    "EC_LimitOrderInvalidPrice": "❌ Invalid limit price",
    "EC_NoEnoughQtyToFill": "❌ Insufficient quantity",
    "EC_NoImmediateQtyToFill": "⏳ No immediate fill available",
    "EC_PerCancelRequest": "🔄 Cancel request",
    "EC_MarketOrderCannotBePostOnly": "❌ Market order cannot be post-only",
    "EC_PostOnlyWillTakeLiquidity": "❌ Post-only would take liquidity",
    "EC_CancelReplaceOrder": "🔄 Cancel/replace order",
    "EC_InvalidSymbolStatus": "❌ Invalid symbol status",
    "EC_CancelForNoFullFill": "❌ Cancelled (no full fill)",
    "EC_BySelfMatch": "🔄 Self-match",
    "EC_InCallAuctionStatus": "⏰ Call auction status",
    "EC_QtyCannotBeZero": "❌ Quantity cannot be zero",
    "EC_MarketOrderNoSupportTIF": "❌ Market order TIF not supported",
    "EC_ReachMaxTradeNum": "❌ Max trade number reached",
    "EC_InvalidPriceScale": "❌ Invalid price scale",
    "EC_BitIndexInvalid": "❌ Invalid bit index",
    "EC_StopBySelfMatch": "🛑 Stop by self-match",
    "EC_InvalidSmpType": "❌ Invalid SMP type",
    "EC_CancelByMMP": "🔄 Cancelled by MMP",
    "EC_InvalidUserType": "❌ Invalid user type",
    "EC_InvalidMirrorOid": "❌ Invalid mirror order ID",
    "EC_InvalidMirrorUid": "❌ Invalid mirror user ID",
    "EC_EcInvalidQty": "❌ Invalid quantity",
    "EC_InvalidAmount": "❌ Invalid amount",
    "EC_LoadOrderCancel": "🔄 Load order cancel",
    "EC_MarketQuoteNoSuppSell": "❌ Market quote sell not supported",
    "EC_DisorderOrderID": "❌ Disorder order ID",
    "EC_InvalidBaseValue": "❌ Invalid base value",
    "EC_LoadOrderCanMatch": "✅ Load order can match",
    "EC_SecurityStatusFail": "🔒 Security status failed",
    "EC_ReachRiskPriceLimit": "⚠️ Risk price limit reached",
    "EC_OrderNotExist": "❌ Order does not exist",
    "EC_CancelByOrderValueZero": "🔄 Cancelled (value zero)",
    "EC_CancelByMatchValueZero": "🔄 Cancelled (match value zero)",
    "EC_ReachMarketPriceLimit": "⚠️ Market price limit reached",
}


# ---------------- HELPER FUNCTIONS ---------------- #
def format_status(status: str) -> str:
    """Format order status with emoji."""
    return ORDER_STATUS.get(status, f"❓ {status}")


def format_create_type(create_type: str) -> str:
    """Format create type with emoji."""
    return CREATE_TYPE.get(create_type, f"❓ {create_type}")


def format_cancel_type(cancel_type: str) -> str:
    """Format cancel type with emoji."""
    return CANCEL_TYPE.get(cancel_type, f"❓ {cancel_type}")


def format_position_idx(position_idx: int) -> str:
    """Format position index."""
    return POSITION_IDX.get(position_idx, f"❓ {position_idx}")


def format_reject_reason(reason: str) -> str:
    """Format reject reason."""
    return REJECT_REASON.get(reason, f"❓ {reason}")


async def identify_tp_sl_level(
    symbol: str, stop_order_type: str, trigger_price: float
) -> str:
    """
    Identify which TP or SL level this is (TP1, TP2, TP3, SL, SL2, SL3).

    :param symbol: Trading symbol
    :param stop_order_type: Order type (TakeProfit, PartialTakeProfit, StopLoss, PartialStopLoss)
    :param trigger_price: Trigger price
    :return: TP/SL identifier (e.g., "TP1", "SL2", "SL", etc.)
    """
    current_time = datetime.now(ZoneInfo("Asia/Tehran")).strftime("%Y-%m-%d %H:%M:%S")

    log_print(
        f"[TP1_TRACK][{current_time}][{symbol}] identify_tp_sl_level called: "
        f"stop_order_type={stop_order_type}, trigger_price={trigger_price}"
    )

    if not trigger_price or trigger_price == 0:
        # If trigger price is not available, return general type
        result = (
            "TP"
            if "Partial" not in stop_order_type
            else (
                "Partial TP"
                if "TakeProfit" in stop_order_type
                else "SL" if "Partial" not in stop_order_type else "Partial SL"
            )
        )
        log_print(
            f"[TP1_TRACK][{current_time}][{symbol}] ⚠️ Trigger price is 0 or invalid, returning: {result}"
        )
        return result

    tp_info = await get_position_tp_prices(symbol)
    if not tp_info:
        # If TP info is not available, return general type
        result = (
            "TP"
            if "Partial" not in stop_order_type
            else (
                "Partial TP"
                if "TakeProfit" in stop_order_type
                else "SL" if "Partial" not in stop_order_type else "Partial SL"
            )
        )
        log_print(
            f"[TP1_TRACK][{current_time}][{symbol}] ⚠️ TP info not found in cache, returning: {result}"
        )
        return result

    tolerance = 0.001  # 0.1% tolerance (increased to handle small price differences)

    log_print(
        f"[TP1_TRACK][{current_time}][{symbol}] TP info found: {tp_info}, tolerance={tolerance}"
    )

    # For TakeProfit
    if "TakeProfit" in stop_order_type:
        tp1_price = tp_info.get("tp1", 0)
        tp2_price = tp_info.get("tp2", 0)
        tp3_price = tp_info.get("tp3")

        log_print(
            f"[TP1_TRACK][{current_time}][{symbol}] Comparing trigger_price={trigger_price} with "
            f"tp1={tp1_price}, tp2={tp2_price}, tp3={tp3_price}"
        )

        if tp1_price and abs(trigger_price - tp1_price) / tp1_price < tolerance:
            diff_pct = abs(trigger_price - tp1_price) / tp1_price * 100
            log_print(
                f"[TP1_TRACK][{current_time}][{symbol}] ✅ MATCHED TP1! "
                f"trigger={trigger_price}, tp1={tp1_price}, diff={diff_pct:.4f}%"
            )
            return "TP1"
        elif tp2_price and abs(trigger_price - tp2_price) / tp2_price < tolerance:
            diff_pct = abs(trigger_price - tp2_price) / tp2_price * 100
            log_print(
                f"[TP1_TRACK][{current_time}][{symbol}] ✅ MATCHED TP2! "
                f"trigger={trigger_price}, tp2={tp2_price}, diff={diff_pct:.4f}%"
            )
            return "TP2"
        elif tp3_price and abs(trigger_price - tp3_price) / tp3_price < tolerance:
            diff_pct = abs(trigger_price - tp3_price) / tp3_price * 100
            log_print(
                f"[TP1_TRACK][{current_time}][{symbol}] ✅ MATCHED TP3! "
                f"trigger={trigger_price}, tp3={tp3_price}, diff={diff_pct:.4f}%"
            )
            return "TP3"
        else:
            # Calculate differences for logging
            diffs = []
            if tp1_price:
                diff_pct = abs(trigger_price - tp1_price) / tp1_price * 100
                diffs.append(f"tp1_diff={diff_pct:.4f}%")
            if tp2_price:
                diff_pct = abs(trigger_price - tp2_price) / tp2_price * 100
                diffs.append(f"tp2_diff={diff_pct:.4f}%")
            if tp3_price:
                diff_pct = abs(trigger_price - tp3_price) / tp3_price * 100
                diffs.append(f"tp3_diff={diff_pct:.4f}%")

            result = "TP" if "Partial" not in stop_order_type else "Partial TP"
            log_print(
                f"[TP1_TRACK][{current_time}][{symbol}] ❌ NO MATCH! trigger={trigger_price}, "
                f"{', '.join(diffs)}, tolerance={tolerance*100:.2f}%, returning: {result}"
            )
            return result

    # For StopLoss
    if "StopLoss" in stop_order_type:
        entry_price = tp_info.get("entry", 0)
        sl_price = tp_info.get("sl", 0)
        side = tp_info.get("side", "")
        tp2_price = tp_info.get("tp2", 0)

        # Check initial SL
        if sl_price and abs(trigger_price - sl_price) / sl_price < tolerance:
            return "SL"

        # Check SL2 (entry * (1±0.0011))
        if entry_price > 0:
            if side == "Buy":
                expected_sl2 = entry_price * (1 + 0.0011)
            else:
                expected_sl2 = entry_price * (1 - 0.0011)

            if abs(trigger_price - expected_sl2) / expected_sl2 < tolerance:
                return "SL2"

        # Check SL3 (TP2 * (1±0.0011))
        if tp2_price > 0:
            if side == "Buy":
                expected_sl3 = tp2_price * (1 + 0.0011)
            else:
                expected_sl3 = tp2_price * (1 - 0.0011)

            if abs(trigger_price - expected_sl3) / expected_sl3 < tolerance:
                return "SL3"

        # If none matched, return general type
        return "SL" if "Partial" not in stop_order_type else "Partial SL"

    return stop_order_type


def safe_float(value, default=0.0):
    """Safely convert value to float."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


async def notify_redis_symbol_removed(symbol: str, reason: str):
    """Send Telegram message when symbol is removed from Redis (position closed)."""
    try:
        msg = (
            f"🔄 **Redis updated:** `{symbol}` removed from cache\n"
            f"_(position fully closed – {reason})_"
        )
        await telClient.send_message(TARGET_CHANNEL, msg)
    except Exception as e:
        log_print(f"[WARN] Failed to send Redis-update notification: {e}")


async def on_tp_filled_update_remaining_and_maybe_remove(
    symbol: str, filled_qty: float, log_prefix: str = ""
) -> bool:
    """
    On TP Filled: subtract filled_qty from Redis remaining size (no API).
    If remaining <= 0, remove symbol from Redis and track closed.
    Independent of TP1/TP2/TP3; Redis-only.
    """
    try:
        closed = await subtract_position_remaining_size(symbol, filled_qty)
        if not closed:
            return False
        log_print(
            f"[TP1_TRACK]{log_prefix}[{symbol}] ✅ Position fully closed (remaining=0), "
            "removing from Redis cache"
        )
        await remove_open_position(symbol)
        await remove_position_entry_time(symbol)
        await remove_position_tp_prices(symbol)
        await remove_pending_sl_update(symbol)
        track_position_closed(symbol)
        await notify_redis_symbol_removed(symbol, "TP")
        return True
    except Exception as e:
        log_print(
            f"[TP1_TRACK]{log_prefix}[{symbol}] ❌ Error on TP fill update/remove: {e}"
        )
        return False


def format_fee_detail(cum_fee_detail: dict) -> str:
    """Format cumulative fee detail."""
    if not cum_fee_detail:
        return "—"
    fees = []
    for currency, amount in cum_fee_detail.items():
        fees.append(f"{amount} {currency}")
    return ", ".join(fees) if fees else "—"


# ---------------- MESSAGE FORMATTERS ---------------- #
async def format_new_order_filled(data: dict) -> str:
    """Format message for new order filled."""
    symbol = data.get("symbol", "—")
    side = data.get("side", "—")
    order_type = data.get("orderType", "—")
    order_status = data.get("orderStatus", "—")
    qty = safe_float(data.get("qty", 0))
    price = safe_float(data.get("price", 0))
    avg_price = safe_float(data.get("avgPrice", 0))
    cum_exec_qty = safe_float(data.get("cumExecQty", 0))
    cum_exec_value = safe_float(data.get("cumExecValue", 0))
    cum_exec_fee = safe_float(data.get("cumExecFee", 0))
    fee_detail = format_fee_detail(data.get("cumFeeDetail", {}))
    stop_loss = data.get("stopLoss") or "—"
    take_profit = data.get("takeProfit") or "—"
    order_id = data.get("orderId", "—")
    create_type = format_create_type(data.get("createType", "—"))
    position_idx = format_position_idx(data.get("positionIdx", 0))
    reject_reason = format_reject_reason(data.get("rejectReason", "EC_NoError"))

    emoji = "📤" if order_status == "Filled" else "⏳"

    # Track order execution for liquidity analysis
    if order_id != "—" and order_status in ["Filled", "PartiallyFilled"]:
        fill_percentage = (cum_exec_qty / qty * 100) if qty > 0 else 0
        execution_price = avg_price if avg_price > 0 else price

        # Calculate slippage if we have expected price (from liquidity metrics)
        slippage = None
        # Note: Slippage calculation would need expected price from order placement

        update_order_fill(
            order_id=str(order_id),
            fill_percentage=fill_percentage,
            execution_price=execution_price,
            slippage=slippage,
        )

    text = (
        f"{emoji} **Order Filled**\n\n"
        f"```\n"
        f"Symbol: {symbol}\n"
        f"Side: {side}\n"
        f"Order Type: {order_type}\n"
        f"Status: {format_status(order_status)}\n"
        f"Position Mode: {position_idx}\n\n"
        f"Quantity: {qty:,.4f}\n"
        f"Price: {price:,.4f}\n"
        f"Avg Price: {avg_price:,.4f}\n"
        f"Executed Qty: {cum_exec_qty:,.4f}\n"
        f"Executed Value: {cum_exec_value:,.2f}\n"
        f"Fee: {cum_exec_fee:,.8f}\n"
        f"Fee Detail: {fee_detail}\n\n"
        f"Stop Loss: {stop_loss}\n"
        f"Take Profit: {take_profit}\n\n"
        f"Created By: {create_type}\n"
        f"Reject Reason: {reject_reason}\n"
        f"Order ID: {order_id}\n"
        f"```"
    )
    return text


async def format_sl_tp_created(data: dict) -> str:
    """Format message for SL/TP order created (Untriggered)."""
    # For information only - usually not displayed
    symbol = data.get("symbol", "—")
    stop_order_type = data.get("stopOrderType", "—")
    order_status = data.get("orderStatus", "—")
    qty = safe_float(data.get("qty", 0))
    trigger_price = safe_float(data.get("triggerPrice", 0))
    create_type = format_create_type(data.get("createType", "—"))
    order_id = data.get("orderId", "—")

    # Only show simple message if Untriggered
    if order_status == "Untriggered":
        tp_sl_emoji = "🎯" if "TakeProfit" in stop_order_type else "🛑"

        # Identify which TP or SL this is
        tp_sl_level = identify_tp_sl_level(symbol, stop_order_type, trigger_price)

        text = (
            f"{tp_sl_emoji} **{tp_sl_level} Created**\n\n"
            f"```\n"
            f"Symbol: {symbol}\n"
            f"Type: {stop_order_type}\n"
            f"Level: {tp_sl_level}\n"
            f"Status: {format_status(order_status)}\n"
            f"Quantity: {qty:,.4f}\n"
            f"Trigger Price: {trigger_price:,.4f}\n"
            f"Created By: {create_type}\n"
            f"Order ID: {order_id}\n"
            f"```"
        )
        return text
    return None


async def format_sl_tp_triggered(data: dict) -> str:
    """Format message for SL/TP order triggered."""
    symbol = data.get("symbol", "—")
    stop_order_type = data.get("stopOrderType", "—")
    order_status = data.get("orderStatus", "—")
    side = data.get("side", "—")
    qty = safe_float(data.get("qty", 0))
    price = safe_float(data.get("price", 0))
    avg_price = safe_float(data.get("avgPrice", 0))
    trigger_price = safe_float(data.get("triggerPrice", 0))
    cum_exec_qty = safe_float(data.get("cumExecQty", 0))
    cum_exec_value = safe_float(data.get("cumExecValue", 0))
    cum_exec_fee = safe_float(data.get("cumExecFee", 0))
    fee_detail = format_fee_detail(data.get("cumFeeDetail", {}))
    closed_pnl = safe_float(data.get("closedPnl", 0))
    order_id = data.get("orderId", "—")
    create_type = format_create_type(data.get("createType", "—"))
    tpsl_mode = data.get("tpslMode", "—")

    emoji = "🎯" if "TakeProfit" in stop_order_type else "🛑"

    # Identify which TP or SL this is
    tp_sl_level = identify_tp_sl_level(symbol, stop_order_type, trigger_price)

    text = (
        f"{emoji} **{tp_sl_level} Triggered**\n\n"
        f"```\n"
        f"Symbol: {symbol}\n"
        f"Side: {side}\n"
        f"Type: {stop_order_type}\n"
        f"Level: {tp_sl_level}\n"
        f"Status: {format_status(order_status)}\n"
        f"Mode: {tpsl_mode}\n\n"
        f"Quantity: {qty:,.4f}\n"
        f"Trigger Price: {trigger_price:,.4f}\n"
        f"Executed Price: {price:,.4f}\n"
        f"Avg Price: {avg_price:,.4f}\n"
        f"Executed Qty: {cum_exec_qty:,.4f}\n"
        f"Executed Value: {cum_exec_value:,.2f}\n"
        f"Fee: {cum_exec_fee:,.8f}\n"
        f"Fee Detail: {fee_detail}\n"
    )

    if closed_pnl != 0:
        pnl_emoji = "🟢" if closed_pnl > 0 else "🔴"
        text += f"{pnl_emoji} Closed PnL: {closed_pnl:,.2f}\n"

    text += f"\nCreated By: {create_type}\n" f"Order ID: {order_id}\n" f"```"
    return text


async def format_order_cancelled(data: dict) -> str:
    """Format message for order cancelled."""
    symbol = data.get("symbol", "—")
    side = data.get("side", "—")
    order_status = data.get("orderStatus", "—")
    stop_order_type = data.get("stopOrderType", "")
    qty = safe_float(data.get("qty", 0))
    price = safe_float(data.get("price", 0))
    avg_price = safe_float(data.get("avgPrice", 0))
    trigger_price = safe_float(data.get("triggerPrice", 0))
    cum_exec_qty = safe_float(data.get("cumExecQty", 0))
    cancel_type = format_cancel_type(data.get("cancelType", "—"))
    order_id = data.get("orderId", "—")
    create_type = format_create_type(data.get("createType", "—"))

    # If it's an SL/TP order, show special message
    if stop_order_type:
        emoji = "🎯" if "TakeProfit" in stop_order_type else "🛑"

        # Identify which TP or SL this is
        tp_sl_level = identify_tp_sl_level(symbol, stop_order_type, trigger_price)

        title = f"{emoji} **{tp_sl_level} Cancelled**"
    else:
        title = "❌ **Order Cancelled**"

    text = (
        f"{title}\n\n"
        f"```\n"
        f"Symbol: {symbol}\n"
        f"Side: {side}\n"
        f"Status: {format_status(order_status)}\n"
    )

    if stop_order_type:
        text += f"Type: {stop_order_type}\n"
        if trigger_price > 0:
            text += f"Level: {tp_sl_level}\n"
            text += f"Trigger Price: {trigger_price:,.4f}\n"

    text += f"Quantity: {qty:,.4f}\n" f"Executed Qty: {cum_exec_qty:,.4f}\n"

    if price > 0:
        text += f"Price: {price:,.4f}\n"
    if avg_price > 0:
        text += f"Avg Price: {avg_price:,.4f}\n"

    text += (
        f"\nCancel Reason: {cancel_type}\n"
        f"Created By: {create_type}\n"
        f"Order ID: {order_id}\n"
        f"```"
    )
    return text


async def format_position_closed(data: dict, closed_pnl: float) -> str:
    """Format message for position closed."""
    symbol = data.get("symbol", "—")
    side = data.get("side", "—")
    order_status = data.get("orderStatus", "—")
    qty = safe_float(data.get("qty", 0))
    price = safe_float(data.get("price", 0))
    avg_price = safe_float(data.get("avgPrice", 0))
    cum_exec_qty = safe_float(data.get("cumExecQty", 0))
    cum_exec_value = safe_float(data.get("cumExecValue", 0))
    cum_exec_fee = safe_float(data.get("cumExecFee", 0))
    fee_detail = format_fee_detail(data.get("cumFeeDetail", {}))
    order_id = data.get("orderId", "—")
    create_type = format_create_type(data.get("createType", "—"))

    pnl_emoji = "🟢" if closed_pnl > 0 else "🔴"

    text = (
        f"🔒 **Position Closed**\n\n"
        f"```\n"
        f"Symbol: {symbol}\n"
        f"Side: {side}\n"
        f"Status: {format_status(order_status)}\n"
        f"Size: {qty:,.4f}\n"
        f"Executed Qty: {cum_exec_qty:,.4f}\n"
        f"Price: {price:,.4f}\n"
        f"Avg Price: {avg_price:,.4f}\n"
        f"Executed Value: {cum_exec_value:,.2f}\n"
        f"Fee: {cum_exec_fee:,.8f}\n"
        f"Fee Detail: {fee_detail}\n"
        f"{pnl_emoji} Closed PnL: {closed_pnl:,.2f}\n\n"
        f"Created By: {create_type}\n"
        f"Order ID: {order_id}\n"
        f"```"
    )
    return text


# ---------------- SL UPDATE AFTER TP1 ---------------- #
# Track pending SL updates (symbol -> entry_time)
# pending_sl_updates is now stored in Redis via cache.py functions


async def set_sl_after_tp1(symbol: str, tp_data: dict):
    """
    Set SL for remaining position after TP1 is triggered.

    SL calculation (break-even + fee protection):
    - For Buy (Long): entry * (1 + 0.0015) - sets SL 0.15% ABOVE entry
    - For Sell (Short): entry * (1 - 0.0015) - sets SL 0.15% BELOW entry

    Validation:
    - For signals with small entry-to-TP1 distance, validates that SL is:
      * Below TP1 and below entry for Buy orders
      * Above TP1 and above entry for Sell orders
    - If validation fails, adjusts SL to be 0.1% below/above TP1 accordingly

    Only sets SL if SL_UPDATE_DELAY_MINUTES have passed since entry time.
    If not, schedules a job to check after the remaining time.
    """
    current_time = datetime.now(ZoneInfo("Asia/Tehran")).strftime("%Y-%m-%d %H:%M:%S")
    log_print(
        f"[TP1_TRACK][{current_time}][{symbol}] 🚀 set_sl_after_tp1 called with tp_data: "
        f"orderId={tp_data.get('orderId', 'N/A')}, orderStatus={tp_data.get('orderStatus', 'N/A')}, "
        f"closeOnTrigger={tp_data.get('closeOnTrigger', False)}, reduceOnly={tp_data.get('reduceOnly', False)}"
    )

    try:
        # Check if SL_UPDATE_DELAY_MINUTES have passed since entry time
        entry_time = await get_position_entry_time(symbol)
        if not entry_time:
            log_print(
                f"[TP1_TRACK][{current_time}][{symbol}] ❌ Entry time not found, cannot verify {SL_UPDATE_DELAY_MINUTES}-minute rule"
            )
            return

        time_elapsed = datetime.now(ZoneInfo("Asia/Tehran")) - entry_time
        time_elapsed_minutes = time_elapsed.total_seconds() / 60.0

        log_print(
            f"[TP1_TRACK][{current_time}][{symbol}] Entry time: {entry_time.strftime('%Y-%m-%d %H:%M:%S')}, "
            f"Time elapsed: {time_elapsed_minutes:.2f} minutes"
        )

        # Get position info
        positions = get_positions(symbol=symbol)
        if not positions:
            log_print(
                f"[TP1_TRACK][{current_time}][{symbol}] ❌ Position not found via API, cannot set SL"
            )
            return

        position = positions[0]
        side = position.get("side", "")
        size = float(position.get("size", 0))

        log_print(
            f"[TP1_TRACK][{current_time}][{symbol}] Position found: side={side}, size={size}"
        )

        if size == 0:
            log_print(
                f"[TP1_TRACK][{current_time}][{symbol}] ❌ Position already closed (size=0), cannot set SL"
            )
            return

        # Get entry price from stored data
        tp_info = await get_position_tp_prices(symbol)
        if not tp_info:
            log_print(
                f"[TP1_TRACK][{current_time}][{symbol}] ❌ TP info not found in cache, cannot set SL"
            )
            return

        entry_price = float(tp_info.get("entry", 0))
        if entry_price == 0:
            log_print(
                f"[TP1_TRACK][{current_time}][{symbol}] ❌ Entry price is 0, cannot set SL"
            )
            return

        log_print(
            f"[TP1_TRACK][{current_time}][{symbol}] TP info: entry={entry_price}, side={tp_info.get('side', 'N/A')}"
        )

        # Get TP1 price for validation (we want SL between entry and TP1)
        tp1_price = float(tp_info.get("tp1", 0))

        # Calculate new SL price for break-even (including fees)
        # Fee structure: ~0.055% per trade = 0.11% round-trip
        # Adding 0.05% safety margin to ensure break-even
        # Total margin needed: 0.11% + 0.05% = 0.16%
        fee_margin = 0.0016  # 0.16% to cover fees + safety margin

        if side == "Buy":
            # For Long positions: SL should be BELOW entry for break-even
            # When price goes down and hits SL, we close at entry - fee_margin
            # This ensures break-even after fees when SL is hit
            new_sl_price = entry_price * (1 - fee_margin)
        else:  # Sell
            # For Short positions: SL should be ABOVE entry for break-even
            # When price goes up and hits SL, we close at entry + fee_margin
            # This ensures break-even after fees when SL is hit
            new_sl_price = entry_price * (1 + fee_margin)

        # Validate and adjust SL for signals with small entry-to-TP1 distance
        # Problem: When entry and TP1 are very close, the calculated SL might
        # go beyond TP1, which could cause immediate stop loss trigger
        if tp1_price > 0:
            if side == "Buy":
                # For Buy: Ensure SL is BETWEEN TP1 and entry
                #  - Below entry (break-even + fee)
                #  - Not below TP1 (should be above TP1 but below entry)
                if new_sl_price < tp1_price:
                    # If calculated SL is below TP1, adjust to be slightly above TP1
                    # This ensures we're still in profit zone after TP1
                    new_sl_price = tp1_price * (1 + 0.0005)  # 0.05% above TP1
                    log_print(
                        f"[TP1_TRACK][{current_time}][{symbol}] ⚠️ Calculated SL was below TP1 "
                        f"({tp1_price:.6f}), adjusting to {new_sl_price:.6f} (0.05% above TP1)"
                    )
                else:
                    log_print(
                        f"[TP1_TRACK][{current_time}][{symbol}] ✅ SL in valid Buy range "
                        f"(tp1={tp1_price:.6f} < SL={new_sl_price:.6f} < entry={entry_price:.6f})"
                    )
            else:  # Sell
                # For Sell: Ensure SL is BETWEEN entry and TP1
                #  - Above entry (break-even + fee)
                #  - Not above TP1 (should be below TP1 but above entry)
                if new_sl_price > tp1_price:
                    # If calculated SL is above TP1, adjust to be slightly below TP1
                    # This ensures we're still in profit zone after TP1
                    new_sl_price = tp1_price * (1 - 0.0005)  # 0.05% below TP1
                    log_print(
                        f"[TP1_TRACK][{current_time}][{symbol}] ⚠️ Calculated SL was above TP1 "
                        f"({tp1_price:.6f}), adjusting to {new_sl_price:.6f} (0.05% below TP1)"
                    )
                else:
                    log_print(
                        f"[TP1_TRACK][{current_time}][{symbol}] ✅ SL in valid Sell range "
                        f"(tp1={tp1_price:.6f} < SL={new_sl_price:.6f} < entry={entry_price:.6f})"
                    )

        log_print(
            f"[TP1_TRACK][{current_time}][{symbol}] Calculated new SL: {new_sl_price:.6f} "
            f"(entry={entry_price:.6f}, tp1={tp1_price:.6f}, side={side})"
        )

        # Check if SL_UPDATE_DELAY_MINUTES have passed
        if time_elapsed_minutes >= SL_UPDATE_DELAY_MINUTES:
            # Required time has passed, update SL immediately
            log_print(
                f"[TP1_TRACK][{current_time}][{symbol}] ✅ {SL_UPDATE_DELAY_MINUTES} minutes passed ({time_elapsed_minutes:.2f} min), "
                f"updating SL immediately to {new_sl_price:.6f}"
            )
            await update_sl_price(
                symbol, new_sl_price, entry_price, side, size, time_elapsed_minutes
            )
        else:
            # Required time has not passed, schedule a job
            remaining_minutes = SL_UPDATE_DELAY_MINUTES - time_elapsed_minutes
            log_print(
                f"[TP1_TRACK][{current_time}][{symbol}] ⏰ Only {time_elapsed_minutes:.2f} minutes elapsed "
                f"(need {SL_UPDATE_DELAY_MINUTES} min), scheduling SL update in {remaining_minutes:.2f} minutes"
            )

            # Store pending update
            await set_pending_sl_update(
                symbol,
                {
                    "entry_time": entry_time,
                    "new_sl_price": new_sl_price,
                    "entry_price": entry_price,
                    "side": side,
                },
            )

            # Schedule async task to check after remaining time
            import asyncio

            # Get the current event loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # If no loop is running, create a new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Create task in the current event loop with proper error handling
            async def scheduled_task_wrapper():
                """Wrapper to ensure exceptions are logged."""
                try:
                    await schedule_sl_update_after_delay(symbol, remaining_minutes)
                except Exception as task_error:
                    log_print(
                        f"[ERROR] Scheduled SL update task failed for {symbol}: {task_error}"
                    )
                    import traceback

                    traceback.print_exc()
                    # Remove from pending updates on error
                    await remove_pending_sl_update(symbol)

            task = asyncio.create_task(scheduled_task_wrapper())
            log_print(
                f"[INFO] Created async task for SL update: {symbol}, task_id={id(task)}, delay={remaining_minutes:.1f} minutes"
            )

            await telClient.send_message(
                TARGET_CHANNEL,
                f"⏰ **SL Update Scheduled**\n\n"
                f"```\n"
                f"Symbol: {symbol}\n"
                f"TP1 Triggered: ✅\n"
                f"Time elapsed: {time_elapsed_minutes:.1f} minutes\n"
                f"Required: {SL_UPDATE_DELAY_MINUTES} minutes\n"
                f"SL will be updated in: {remaining_minutes:.1f} minutes\n"
                f"New SL Price: {new_sl_price:,.4f}\n"
                f"```",
            )

    except Exception as e:
        error_time = datetime.now(ZoneInfo("Asia/Tehran")).strftime("%Y-%m-%d %H:%M:%S")
        log_print(
            f"[TP1_TRACK][{error_time}][{symbol}] ❌ ERROR in set_sl_after_tp1: {e}"
        )
        import traceback

        traceback.print_exc()
        await telClient.send_message(
            TARGET_CHANNEL,
            f"⚠️ **Error Setting SL**\n\n" f"Symbol: {symbol}\n" f"Error: {str(e)}",
        )


async def schedule_sl_update_after_delay(symbol: str, delay_minutes: float):
    """
    Schedule SL update after a delay.
    Checks if position is still open before updating.
    """
    start_time = datetime.now(ZoneInfo("Asia/Tehran")).strftime("%Y-%m-%d %H:%M:%S")
    log_print(
        f"[TP1_TRACK][{start_time}][{symbol}] ⏰ schedule_sl_update_after_delay started: "
        f"delay={delay_minutes:.2f} minutes"
    )

    try:
        # Convert minutes to seconds
        delay_seconds = delay_minutes * 60
        import asyncio

        log_print(
            f"[TP1_TRACK][{start_time}][{symbol}] Waiting {delay_seconds:.0f} seconds "
            f"({delay_minutes:.2f} minutes) before checking SL update"
        )
        await asyncio.sleep(delay_seconds)

        check_time = datetime.now(ZoneInfo("Asia/Tehran")).strftime("%Y-%m-%d %H:%M:%S")
        log_print(
            f"[TP1_TRACK][{check_time}][{symbol}] ✅ Delay completed, checking SL update"
        )

        # Check if update is still pending
        pending_update = await get_pending_sl_update(symbol)
        if not pending_update:
            log_print(
                f"[TP1_TRACK][{check_time}][{symbol}] ⚠️ SL update was cancelled or already processed"
            )
            return

        log_print(
            f"[TP1_TRACK][{check_time}][{symbol}] Pending SL update found: {pending_update}"
        )

        # Check if position is still open
        positions = get_positions(symbol=symbol)
        if not positions:
            log_print(
                f"[TP1_TRACK][{check_time}][{symbol}] ❌ Position not found via API, skipping SL update"
            )
            await remove_pending_sl_update(symbol)
            return

        position = positions[0]
        size = float(position.get("size", 0))
        if size == 0:
            log_print(
                f"[TP1_TRACK][{check_time}][{symbol}] ❌ Position closed (size=0), skipping SL update"
            )
            await remove_pending_sl_update(symbol)
            return

        log_print(
            f"[TP1_TRACK][{check_time}][{symbol}] ✅ Position still open: size={size}, "
            f"side={position.get('side', 'N/A')}"
        )

        # Get update info
        update_info = await get_pending_sl_update(symbol)
        if not update_info:
            log_print(f"[TP1_TRACK][{check_time}][{symbol}] ❌ Update info not found")
            return

        new_sl_price = update_info["new_sl_price"]
        entry_price = update_info["entry_price"]
        side = update_info["side"]

        log_print(
            f"[TP1_TRACK][{check_time}][{symbol}] Update info: new_sl={new_sl_price:.6f}, "
            f"entry={entry_price:.6f}, side={side}"
        )

        # Check if SL_UPDATE_DELAY_MINUTES have passed
        entry_time = await get_position_entry_time(symbol)
        if entry_time:
            time_elapsed = datetime.now(ZoneInfo("Asia/Tehran")) - entry_time
            time_elapsed_minutes = time_elapsed.total_seconds() / 60.0

            log_print(
                f"[TP1_TRACK][{check_time}][{symbol}] Entry time: {entry_time.strftime('%Y-%m-%d %H:%M:%S')}, "
                f"Time elapsed: {time_elapsed_minutes:.2f} minutes"
            )

            if time_elapsed_minutes >= SL_UPDATE_DELAY_MINUTES:
                # Update SL
                log_print(
                    f"[TP1_TRACK][{check_time}][{symbol}] ✅ {SL_UPDATE_DELAY_MINUTES} minutes passed, updating SL now"
                )
                await update_sl_price(
                    symbol, new_sl_price, entry_price, side, size, time_elapsed_minutes
                )
                await remove_pending_sl_update(symbol)
                log_print(
                    f"[TP1_TRACK][{check_time}][{symbol}] ✅ SL update completed and pending update removed"
                )
            else:
                log_print(
                    f"[TP1_TRACK][{check_time}][{symbol}] ⚠️ Still less than {SL_UPDATE_DELAY_MINUTES} minutes "
                    f"({time_elapsed_minutes:.2f} min), skipping SL update"
                )
        else:
            log_print(
                f"[TP1_TRACK][{check_time}][{symbol}] ❌ Entry time not found, skipping SL update"
            )
            await remove_pending_sl_update(symbol)

    except Exception as e:
        error_time = datetime.now(ZoneInfo("Asia/Tehran")).strftime("%Y-%m-%d %H:%M:%S")
        log_print(
            f"[TP1_TRACK][{error_time}][{symbol}] ❌ ERROR in schedule_sl_update_after_delay: {e}"
        )
        import traceback

        traceback.print_exc()
        await remove_pending_sl_update(symbol)


async def update_sl_price(
    symbol: str,
    new_sl_price: float,
    entry_price: float,
    side: str,
    size: float,
    time_elapsed_minutes: float,
):
    """
    Update SL price using amend_order.
    """
    current_time = datetime.now(ZoneInfo("Asia/Tehran")).strftime("%Y-%m-%d %H:%M:%S")
    log_print(
        f"[TP1_TRACK][{current_time}][{symbol}] 🔄 update_sl_price called: "
        f"new_sl={new_sl_price:.6f}, entry={entry_price:.6f}, side={side}, "
        f"size={size}, elapsed={time_elapsed_minutes:.2f} min"
    )

    try:
        # Add small delay to ensure SL order is available in open orders list
        import asyncio

        log_print(
            f"[TP1_TRACK][{current_time}][{symbol}] Waiting 1 second for SL order to be available..."
        )
        await asyncio.sleep(1.0)  # Wait 1 second for order to be available

        # Try to get existing SL order ID and amend it
        log_print(
            f"[TP1_TRACK][{current_time}][{symbol}] Getting SL order ID (retry_count=3)..."
        )
        sl_order_id = get_sl_order_id(symbol, positionIdx=0, retry_count=3)

        if sl_order_id:
            log_print(
                f"[TP1_TRACK][{current_time}][{symbol}] ✅ SL order found: orderId={sl_order_id}, "
                f"attempting to amend..."
            )
            # Update existing SL order using amend
            # For conditional orders (TP/SL), we need to update triggerPrice
            try:
                amend_order(
                    symbol=symbol,
                    orderId=sl_order_id,
                    triggerPrice=new_sl_price,  # Update trigger price for conditional SL order (will be converted to string in amend_order)
                    slTriggerBy="MarkPrice",  # Use MarkPrice to avoid micro-spikes in LastPrice
                )
                log_print(
                    f"[TP1_TRACK][{current_time}][{symbol}] ✅ SL updated via amend: "
                    f"new_sl={new_sl_price:.6f}, entry={entry_price:.6f}, side={side}, "
                    f"size={size}, orderId={sl_order_id}"
                )
            except Exception as e:
                log_print(
                    f"[TP1_TRACK][{current_time}][{symbol}] ⚠️ Failed to amend SL order {sl_order_id}, "
                    f"trying set_trading_stop fallback: {e}"
                )
                import traceback

                traceback.print_exc()
                # Fallback to set_trading_stop if amend fails
                set_trading_stop(
                    symbol=symbol,
                    positionIdx=0,
                    tpslMode="Partial",
                    sl=str(new_sl_price),
                    slSize=str(size),
                )
                log_print(
                    f"[TP1_TRACK][{current_time}][{symbol}] ✅ SL set via set_trading_stop fallback: "
                    f"new_sl={new_sl_price:.6f}, entry={entry_price:.6f}, side={side}, size={size}"
                )
        else:
            log_print(
                f"[TP1_TRACK][{current_time}][{symbol}] ⚠️ SL order ID not found, "
                f"using set_trading_stop to create new SL"
            )
            # No existing SL order, use set_trading_stop to create new one
            set_trading_stop(
                symbol=symbol,
                positionIdx=0,
                tpslMode="Partial",
                sl=str(new_sl_price),
                slSize=str(size),
            )
            log_print(
                f"[TP1_TRACK][{current_time}][{symbol}] ✅ SL created via set_trading_stop: "
                f"new_sl={new_sl_price:.6f}, entry={entry_price:.6f}, side={side}, size={size}"
            )

        # Notify Telegram
        await telClient.send_message(
            TARGET_CHANNEL,
            f"🛡️ **SL Updated After TP1**\n\n"
            f"```\n"
            f"Symbol: {symbol}\n"
            f"Side: {side}\n"
            f"Entry Price: {entry_price:,.4f}\n"
            f"New SL Price: {new_sl_price:,.4f}\n"
            f"Remaining Size: {size:,.4f}\n"
            f"Time elapsed: {time_elapsed_minutes:.1f} minutes\n"
            f"```",
        )

    except Exception as e:
        log_print(f"[ERROR] Failed to update SL price for {symbol}: {e}")
        import traceback

        traceback.print_exc()
        await telClient.send_message(
            TARGET_CHANNEL,
            f"⚠️ **Error Updating SL**\n\n" f"Symbol: {symbol}\n" f"Error: {str(e)}",
        )


# ---------------- FORMAT FULL WS MESSAGE ---------------- #
async def format_full_ws_message(raw_message: dict, orders: list) -> str:
    """
    Format complete WebSocket message with all orders data.
    Returns a single formatted message string.
    """
    topic = raw_message.get("topic", "order")
    creation_time = raw_message.get("creationTime", "")
    msg_id = raw_message.get("id", "")

    # Format creation time
    creation_time_str = "-"
    if creation_time:
        try:
            timestamp_ms = int(creation_time)
            timestamp_s = timestamp_ms / 1000.0
            dt_utc = datetime.fromtimestamp(timestamp_s, tz=ZoneInfo("UTC"))
            dt_iran = dt_utc.astimezone(ZoneInfo("Asia/Tehran"))
            creation_time_str = dt_iran.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError, OSError):
            creation_time_str = str(creation_time)

    text = f"📡 **WebSocket Message**\n\n"
    text += f"```\n"
    text += f"Topic: {topic}\n"
    text += f"ID: {msg_id}\n"
    text += f"Time: {creation_time_str}\n"
    text += f"Orders Count: {len(orders)}\n"
    text += f"```\n\n"

    # Format each order
    for idx, order in enumerate(orders, 1):
        symbol = order.get("symbol", "-")
        side = order.get("side", "-")
        order_status = order.get("orderStatus", "-")
        order_id = order.get("orderId", "-")
        order_type = order.get("orderType", "-")
        stop_order_type = order.get("stopOrderType", "")
        qty = safe_float(order.get("qty", 0))
        price = safe_float(order.get("price", 0))
        avg_price = safe_float(order.get("avgPrice", 0))
        trigger_price = safe_float(order.get("triggerPrice", 0))
        cum_exec_qty = safe_float(order.get("cumExecQty", 0))
        cum_exec_value = safe_float(order.get("cumExecValue", 0))
        cum_exec_fee = safe_float(order.get("cumExecFee", 0))
        closed_pnl = safe_float(order.get("closedPnl", 0))
        create_type = format_create_type(order.get("createType", "-"))
        cancel_type = format_cancel_type(order.get("cancelType", "UNKNOWN"))
        reject_reason = format_reject_reason(order.get("rejectReason", "EC_NoError"))
        created_time = order.get("createdTime", "")
        updated_time = order.get("updatedTime", "")

        # Format timestamps
        created_time_str = format_timestamp(created_time) if created_time else "-"
        updated_time_str = format_timestamp(updated_time) if updated_time else "-"

        # Determine emoji based on order type
        if stop_order_type:
            emoji = (
                "🎯"
                if "TakeProfit" in stop_order_type
                else "🛑" if "StopLoss" in stop_order_type else "📋"
            )
        elif order_status == "Filled":
            emoji = "✅"
        elif order_status in ["Cancelled", "Deactivated"]:
            emoji = "❌"
        elif order_status == "Rejected":
            emoji = "⚠️"
        else:
            emoji = "📋"

        text += f"{emoji} **Order #{idx}:**\n"
        text += f"```\n"
        text += f"Symbol: {symbol}\n"
        text += f"Side: {side}\n"
        text += f"Order ID: {order_id}\n"
        text += f"Status: {format_status(order_status)}\n"

        if stop_order_type:
            text += f"Stop Order Type: {stop_order_type}\n"

        text += f"Order Type: {order_type}\n"
        text += f"Quantity: {qty:,.4f}\n"

        if price > 0:
            text += f"Price: {price:,.4f}\n"
        if avg_price > 0:
            text += f"Avg Price: {avg_price:,.4f}\n"
        if trigger_price > 0:
            text += f"Trigger Price: {trigger_price:,.4f}\n"

        if cum_exec_qty > 0:
            text += f"Executed Qty: {cum_exec_qty:,.4f}\n"
        if cum_exec_value > 0:
            text += f"Executed Value: {cum_exec_value:,.2f}\n"
        if cum_exec_fee > 0:
            text += f"Fee: {cum_exec_fee:,.8f}\n"
        if closed_pnl != 0:
            pnl_emoji = "🟢" if closed_pnl > 0 else "🔴"
            text += f"{pnl_emoji} Closed PnL: {closed_pnl:,.2f}\n"

        # Additional fields
        take_profit = safe_float(order.get("takeProfit", 0))
        stop_loss = safe_float(order.get("stopLoss", 0))
        if take_profit > 0:
            text += f"Take Profit: {take_profit:,.4f}\n"
        if stop_loss > 0:
            text += f"Stop Loss: {stop_loss:,.4f}\n"

        text += f"Created By: {create_type}\n"
        if cancel_type != "UNKNOWN":
            text += f"Cancel Type: {cancel_type}\n"
        if reject_reason != "✅ No error":
            text += f"Reject Reason: {reject_reason}\n"

        text += f"Created Time: {created_time_str}\n"
        if updated_time_str != created_time_str:
            text += f"Updated Time: {updated_time_str}\n"

        text += f"```\n\n"

    return text


def format_timestamp(timestamp_str):
    """Format timestamp (milliseconds) to readable date/time."""
    if not timestamp_str or timestamp_str == "" or timestamp_str == "-":
        return "-"
    try:
        timestamp_ms = int(timestamp_str)
        timestamp_s = timestamp_ms / 1000.0
        dt_utc = datetime.fromtimestamp(timestamp_s, tz=ZoneInfo("UTC"))
        dt_iran = dt_utc.astimezone(ZoneInfo("Asia/Tehran"))
        return dt_iran.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OSError):
        return str(timestamp_str)


# ---------------- MAIN HANDLER ---------------- #
async def handle_ws_message(item: dict):
    """
    Handle WebSocket messages from Bybit.
    Formats and sends appropriate messages to Telegram.
    """
    entry_time = datetime.now(ZoneInfo("Asia/Tehran")).strftime("%Y-%m-%d %H:%M:%S")
    msg_type = item.get("msg_type", "unknown")
    log_print(
        f"[TP1_TRACK][{entry_time}] ========== handle_ws_message called: msg_type={msg_type} =========="
    )

    # Check if this is a full message with all orders
    if item.get("msg_type") == "ws_message":
        # Format and send complete message with all orders
        raw_message = item.get("raw_message", {})
        orders = item.get("orders", [])

        if orders:
            try:
                text = await format_full_ws_message(raw_message, orders)
                await telClient.send_message(TARGET_CHANNEL, text)
            except Exception as e:
                # Log error but continue processing
                log_print(f"[ERROR] Error formatting/sending WebSocket message: {e}")
                import traceback

                traceback.print_exc()

            # Check if any TP1 was triggered and update SL if needed
            # Use try-except to prevent errors from blocking message sending
            current_time = datetime.now(ZoneInfo("Asia/Tehran")).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            log_print(
                f"[TP1_TRACK][{current_time}] Processing {len(orders)} order(s) for TP1 check"
            )

            for idx, order in enumerate(orders):
                try:
                    order_status = order.get("orderStatus", "")
                    stop_order_type = order.get("stopOrderType", "")
                    symbol = order.get("symbol", "")
                    order_id = order.get("orderId", "N/A")

                    log_print(
                        f"[TP1_TRACK][{current_time}][{symbol}] Order #{idx+1}/{len(orders)}: "
                        f"orderId={order_id}, orderStatus={order_status}, "
                        f"stopOrderType={stop_order_type}"
                    )

                    # Handle StopLoss orders that close the position
                    if (
                        order_status == "Filled"
                        and stop_order_type == "StopLoss"
                        and order.get("closeOnTrigger")
                        and order.get("reduceOnly")
                    ):
                        # StopLoss filled and closed the position - remove from Redis
                        log_print(
                            f"[TP1_TRACK][{current_time}][{symbol}] 🛑 StopLoss Filled - Position closed, "
                            f"removing from tracking"
                        )
                        await remove_open_position(symbol)
                        await remove_position_entry_time(symbol)
                        await remove_position_tp_prices(symbol)
                        await remove_position_remaining_size(symbol)
                        await remove_pending_sl_update(symbol)
                        track_position_closed(symbol)
                        await notify_redis_symbol_removed(symbol, "SL")

                    elif order_status in [
                        "Filled",
                        "Triggered",
                    ] and stop_order_type in [
                        "TakeProfit",
                        "PartialTakeProfit",
                    ]:
                        trigger_price = safe_float(order.get("triggerPrice", 0))
                        log_print(
                            f"[TP1_TRACK][{current_time}][{symbol}] ✅ TP order detected: "
                            f"status={order_status}, type={stop_order_type}, triggerPrice={trigger_price}"
                        )

                        tp_level = await identify_tp_sl_level(
                            symbol, stop_order_type, trigger_price
                        )

                        log_print(
                            f"[TP1_TRACK][{current_time}][{symbol}] TP level identified: {tp_level}"
                        )

                        if tp_level == "TP1":
                            log_print(
                                f"[TP1_TRACK][{current_time}][{symbol}] 🎯 TP1 CONFIRMED! "
                                f"Calling set_sl_after_tp1..."
                            )
                            # TP1 triggered, set SL after SL_UPDATE_DELAY_MINUTES
                            await set_sl_after_tp1(symbol, order)
                            # Note: Don't remove position from Redis here - TP1 only partially closes the position
                            # Position will be removed when StopLoss is hit or position is fully closed
                        else:
                            log_print(
                                f"[TP1_TRACK][{current_time}][{symbol}] ⚠️ Not TP1 (got {tp_level}), "
                                f"skipping SL update"
                            )
                        # On Filled TP: subtract filled qty from Redis remaining; remove if closed (no API)
                        if order_status == "Filled":
                            filled_qty = safe_float(
                                order.get("cumExecQty") or order.get("qty", 0)
                            )
                            await on_tp_filled_update_remaining_and_maybe_remove(
                                symbol, filled_qty, f"[{current_time}] "
                            )
                    else:
                        log_print(
                            f"[TP1_TRACK][{current_time}][{symbol}] ⏭️ Skipped: "
                            f"orderStatus={order_status}, stopOrderType={stop_order_type} "
                            f"(not a filled/triggered TP order or closing SL order)"
                        )
                except Exception as e:
                    # Log error but don't block message sending
                    current_time_err = datetime.now(ZoneInfo("Asia/Tehran")).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    symbol_err = (
                        order.get("symbol", "UNKNOWN")
                        if "order" in locals()
                        else "UNKNOWN"
                    )
                    log_print(
                        f"[TP1_TRACK][{current_time_err}][{symbol_err}] ❌ ERROR processing TP1 check "
                        f"for order {order.get('orderId', 'unknown')}: {e}"
                    )
                    import traceback

                    traceback.print_exc()
        return

    # Legacy handling for individual orders (backward compatibility)
    legacy_time = datetime.now(ZoneInfo("Asia/Tehran")).strftime("%Y-%m-%d %H:%M:%S")
    ws_type = item.get("msg_type")
    data = item.get("data", {})
    symbol = item.get("symbol", "")
    closed_pnl = item.get("closed_pnl", 0.0)

    log_print(
        f"[TP1_TRACK][{legacy_time}] ========== Legacy handler branch ========== "
        f"ws_type={ws_type}, symbol={symbol}"
    )

    order_status = data.get("orderStatus", "")
    stop_order_type = data.get("stopOrderType", "")
    create_type = data.get("createType", "")

    log_print(
        f"[TP1_TRACK][{legacy_time}][{symbol}] Legacy handler data: "
        f"orderStatus={order_status}, stopOrderType={stop_order_type}, "
        f"createType={create_type}, closedPnl={closed_pnl}"
    )

    # Show message for SL/TP orders that have been created (Untriggered)
    # Only for createType related to SL/TP created by the system
    if order_status == "Untriggered" and stop_order_type:
        log_print(
            f"[TP1_TRACK][{legacy_time}][{symbol}] Untriggered order detected, checking createType..."
        )
        # Show message for SL/TP that have been created
        sl_tp_create_types = [
            "CreateByPartialTakeProfit",
            "CreateByStopLoss",
            "CreateByTakeProfit",
            "CreateByPartialStopLoss",
        ]
        # If ws_type == "sl_tp_created" or createType is appropriate, show message
        if ws_type == "sl_tp_created" or create_type in sl_tp_create_types:
            text = await format_sl_tp_created(data)
            if text:
                await telClient.send_message(TARGET_CHANNEL, text)
                return  # Message sent, no need to continue

        # If createType is not appropriate, return (don't show message)
        return

    # Handle different message types based on ws_type
    if ws_type == "new_order":
        log_print(
            f"[TP1_TRACK][{legacy_time}][{symbol}] Legacy handler: new_order type"
        )
        text = await format_new_order_filled(data)
        await telClient.send_message(TARGET_CHANNEL, text)
        log_print(
            f"[TP1_TRACK][{legacy_time}][{symbol}] Legacy handler: new_order message sent"
        )

    elif ws_type == "close_position":
        log_print(
            f"[TP1_TRACK][{legacy_time}][{symbol}] Legacy handler: close_position type, "
            f"removing from tracking..."
        )
        # Remove symbol from open_positions and related data
        await remove_open_position(symbol)
        await remove_position_entry_time(symbol)
        await remove_position_tp_prices(symbol)
        await remove_position_remaining_size(symbol)
        # Track position closed for capital tracking
        track_position_closed(symbol)
        await notify_redis_symbol_removed(symbol, "close_position")
        text = await format_position_closed(data, closed_pnl)
        await telClient.send_message(TARGET_CHANNEL, text)
        log_print(
            f"[TP1_TRACK][{legacy_time}][{symbol}] Legacy handler: close_position processed, "
            f"removed from cache, closedPnl={closed_pnl}"
        )

    elif ws_type == "cancel_order":
        log_print(
            f"[TP1_TRACK][{legacy_time}][{symbol}] Legacy handler: cancel_order type"
        )
        text = await format_order_cancelled(data)
        await telClient.send_message(TARGET_CHANNEL, text)
        log_print(
            f"[TP1_TRACK][{legacy_time}][{symbol}] Legacy handler: cancel_order message sent"
        )

    elif ws_type == "sl_tp_triggered":
        # SL/TP triggered
        current_time = datetime.now(ZoneInfo("Asia/Tehran")).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        log_print(
            f"[TP1_TRACK][{current_time}][{symbol}] Legacy handler: sl_tp_triggered detected"
        )

        text = await format_sl_tp_triggered(data)
        if text:
            await telClient.send_message(TARGET_CHANNEL, text)

            # Check if TP1 was triggered and update SL if needed
            stop_order_type = data.get("stopOrderType", "")
            order_status = data.get("orderStatus", "")
            trigger_price = safe_float(data.get("triggerPrice", 0))

            log_print(
                f"[TP1_TRACK][{current_time}][{symbol}] Legacy handler TP check: "
                f"stopOrderType={stop_order_type}, orderStatus={order_status}, "
                f"triggerPrice={trigger_price}"
            )

            # Handle StopLoss orders that close the position
            if (
                order_status == "Filled"
                and stop_order_type == "StopLoss"
                and data.get("closeOnTrigger")
                and data.get("reduceOnly")
            ):
                # StopLoss filled and closed the position - remove from Redis
                log_print(
                    f"[TP1_TRACK][{current_time}][{symbol}] 🛑 Legacy handler: StopLoss Filled - Position closed, "
                    f"removing from tracking"
                )
                await remove_open_position(symbol)
                await remove_position_entry_time(symbol)
                await remove_position_tp_prices(symbol)
                await remove_position_remaining_size(symbol)
                await remove_pending_sl_update(symbol)
                track_position_closed(symbol)
                await notify_redis_symbol_removed(symbol, "SL")

            elif stop_order_type in ["TakeProfit", "PartialTakeProfit"]:
                tp_level = await identify_tp_sl_level(
                    symbol, stop_order_type, trigger_price
                )

                log_print(
                    f"[TP1_TRACK][{current_time}][{symbol}] Legacy handler TP level: {tp_level}"
                )

                if tp_level == "TP1":
                    log_print(
                        f"[TP1_TRACK][{current_time}][{symbol}] 🎯 Legacy handler: TP1 CONFIRMED! "
                        f"Calling set_sl_after_tp1..."
                    )
                    # TP1 triggered, set SL after SL_UPDATE_DELAY_MINUTES
                    await set_sl_after_tp1(symbol, data)
                    # Note: Don't remove position from Redis here - TP1 only partially closes the position
                    # Position will be removed when StopLoss is hit or position is fully closed
                else:
                    log_print(
                        f"[TP1_TRACK][{current_time}][{symbol}] ⚠️ Legacy handler: Not TP1 "
                        f"(got {tp_level}), skipping SL update"
                    )
                # On Filled TP: subtract filled qty from Redis remaining; remove if closed (no API)
                if order_status == "Filled":
                    filled_qty = safe_float(
                        data.get("cumExecQty") or data.get("qty", 0)
                    )
                    await on_tp_filled_update_remaining_and_maybe_remove(
                        symbol, filled_qty, f"[{current_time}] "
                    )

    elif ws_type == "sl_tp_created":
        log_print(
            f"[TP1_TRACK][{legacy_time}][{symbol}] Legacy handler: sl_tp_created type"
        )
        # SL/TP created (Untriggered) - for information only
        text = await format_sl_tp_created(data)
        if text:
            await telClient.send_message(TARGET_CHANNEL, text)
            log_print(
                f"[TP1_TRACK][{legacy_time}][{symbol}] Legacy handler: sl_tp_created message sent"
            )

    elif ws_type == "rejected" or order_status == "Rejected":
        symbol = data.get("symbol", "—")
        reject_reason_str = data.get("rejectReason", "EC_Others")
        reject_reason = format_reject_reason(reject_reason_str)
        order_id = data.get("orderId", "—")

        # Track rejected order if it's due to insufficient balance
        track_rejected_order(symbol, reject_reason_str, FIXED_MARGIN_USDT)

        text = (
            f"❌ **Order Rejected**\n\n"
            f"```\n"
            f"Symbol: {symbol}\n"
            f"Reason: {reject_reason}\n"
            f"Order ID: {order_id}\n"
            f"```"
        )
        await telClient.send_message(TARGET_CHANNEL, text)

    # Fallback: handle by order_status if ws_type is "other"
    elif ws_type == "other":
        log_print(
            f"[TP1_TRACK][{legacy_time}][{symbol}] Legacy handler: other type, "
            f"orderStatus={order_status}"
        )
        if order_status == "Filled":
            if data.get("reduceOnly"):
                log_print(
                    f"[TP1_TRACK][{legacy_time}][{symbol}] Legacy handler (other): "
                    f"Filled with reduceOnly=True, position closed by market order"
                )
                # Position closed by market order
                await remove_open_position(symbol)
                await remove_position_entry_time(symbol)
                await remove_position_tp_prices(symbol)
                await remove_position_remaining_size(symbol)
                # Track position closed for capital tracking
                track_position_closed(symbol)
                await notify_redis_symbol_removed(symbol, "market close")
                text = await format_position_closed(data, closed_pnl)
                await telClient.send_message(TARGET_CHANNEL, text)
                log_print(
                    f"[TP1_TRACK][{legacy_time}][{symbol}] Legacy handler (other): "
                    f"Position closed message sent, closedPnl={closed_pnl}"
                )
            else:
                log_print(
                    f"[TP1_TRACK][{legacy_time}][{symbol}] Legacy handler (other): "
                    f"Filled without reduceOnly, new order filled"
                )
                # New order filled
                text = await format_new_order_filled(data)
                await telClient.send_message(TARGET_CHANNEL, text)
                log_print(
                    f"[TP1_TRACK][{legacy_time}][{symbol}] Legacy handler (other): "
                    f"New order filled message sent"
                )
        elif stop_order_type and order_status in ["Filled", "Triggered"]:
            current_time = datetime.now(ZoneInfo("Asia/Tehran")).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            log_print(
                f"[TP1_TRACK][{current_time}][{symbol}] Legacy handler (other): "
                f"stopOrderType={stop_order_type}, orderStatus={order_status}"
            )

            text = await format_sl_tp_triggered(data)
            if text:
                await telClient.send_message(TARGET_CHANNEL, text)

                # Handle StopLoss orders that close the position
                if (
                    order_status == "Filled"
                    and stop_order_type == "StopLoss"
                    and data.get("closeOnTrigger")
                    and data.get("reduceOnly")
                ):
                    # StopLoss filled and closed the position - remove from Redis
                    log_print(
                        f"[TP1_TRACK][{current_time}][{symbol}] 🛑 Legacy handler (other): StopLoss Filled - Position closed, "
                        f"removing from tracking"
                    )
                    await remove_open_position(symbol)
                    await remove_position_entry_time(symbol)
                    await remove_position_tp_prices(symbol)
                    await remove_position_remaining_size(symbol)
                    await remove_pending_sl_update(symbol)
                    track_position_closed(symbol)
                    await notify_redis_symbol_removed(symbol, "SL")

                # Check if TP1 was triggered and update SL if needed
                elif stop_order_type in ["TakeProfit", "PartialTakeProfit"]:
                    trigger_price = safe_float(data.get("triggerPrice", 0))
                    log_print(
                        f"[TP1_TRACK][{current_time}][{symbol}] Legacy handler (other) TP check: "
                        f"triggerPrice={trigger_price}"
                    )

                    tp_level = await identify_tp_sl_level(
                        symbol, stop_order_type, trigger_price
                    )

                    log_print(
                        f"[TP1_TRACK][{current_time}][{symbol}] Legacy handler (other) TP level: {tp_level}"
                    )

                    if tp_level == "TP1":
                        log_print(
                            f"[TP1_TRACK][{current_time}][{symbol}] 🎯 Legacy handler (other): TP1 CONFIRMED! "
                            f"Calling set_sl_after_tp1..."
                        )
                        # TP1 triggered, set SL after SL_UPDATE_DELAY_MINUTES
                        await set_sl_after_tp1(symbol, data)
                        # Note: Don't remove position from Redis here - TP1 only partially closes the position
                        # Position will be removed when StopLoss is hit or position is fully closed
                    else:
                        log_print(
                            f"[TP1_TRACK][{current_time}][{symbol}] ⚠️ Legacy handler (other): Not TP1 "
                            f"(got {tp_level}), skipping SL update"
                        )
                    # On Filled TP: subtract filled qty from Redis remaining; remove if closed (no API)
                    if order_status == "Filled":
                        filled_qty = safe_float(
                            data.get("cumExecQty") or data.get("qty", 0)
                        )
                        await on_tp_filled_update_remaining_and_maybe_remove(
                            symbol, filled_qty, f"[{current_time}] "
                        )


# ---------------- DEBUG FUNCTION ---------------- #
# برای اجرای این تابع و مشاهده داده‌های Redis، می‌توانید آن را در یک command handler یا
# به صورت مستقیم در کد فراخوانی کنید:
#
# مثال استفاده:
#   from ws_message_formatter import debug_redis_data
#   await debug_redis_data()
#
# یا در یک telegram command:
#   @telClient.on(events.NewMessage(pattern=r"^/debug_redis$"))
#   async def debug_redis_handler(event):
#       result = await debug_redis_data()
#       await event.respond(result)
async def debug_redis_data() -> str:
    """
    نمایش تمام داده‌های مربوط به پوزیشن‌های باز و schedule های SL از Redis.

    Returns:
        str: متن فرمت شده با تمام اطلاعات Redis
    """
    current_time = datetime.now(ZoneInfo("Asia/Tehran")).strftime("%Y-%m-%d %H:%M:%S")
    log_print(
        f"[DEBUG_REDIS][{current_time}] ========== Fetching Redis data =========="
    )

    result_lines = []
    result_lines.append("=" * 60)
    result_lines.append(f"📊 Redis Data Report - {current_time}")
    result_lines.append("=" * 60)
    result_lines.append("")

    try:
        # 1. Open Positions
        result_lines.append("🔵 OPEN POSITIONS:")
        result_lines.append("-" * 60)
        open_positions = await get_open_positions()
        if open_positions:
            for symbol in sorted(open_positions):
                result_lines.append(f"  ✅ {symbol}")
        else:
            result_lines.append("  (empty)")
        result_lines.append("")

        # 2. Position Entry Times
        result_lines.append("⏰ POSITION ENTRY TIMES:")
        result_lines.append("-" * 60)
        entry_times = await get_position_entry_times()
        if entry_times:
            for symbol, entry_time_str in sorted(entry_times.items()):
                try:
                    # Parse ISO string to datetime
                    entry_time = datetime.fromisoformat(entry_time_str).replace(
                        tzinfo=ZoneInfo("Asia/Tehran")
                    )
                    time_elapsed = datetime.now(ZoneInfo("Asia/Tehran")) - entry_time
                    elapsed_minutes = time_elapsed.total_seconds() / 60.0
                    result_lines.append(
                        f"  {symbol}: {entry_time.strftime('%Y-%m-%d %H:%M:%S')} "
                        f"(elapsed: {elapsed_minutes:.1f} min)"
                    )
                except Exception as e:
                    result_lines.append(
                        f"  {symbol}: {entry_time_str} (parse error: {e})"
                    )
        else:
            result_lines.append("  (empty)")
        result_lines.append("")

        # 3. Remaining Sizes (Redis-only, no API)
        result_lines.append("📐 REMAINING SIZES:")
        result_lines.append("-" * 60)
        remaining_sizes = await get_position_remaining_sizes()
        if remaining_sizes:
            for sym, size in sorted(remaining_sizes.items()):
                result_lines.append(f"  {sym}: {size}")
        else:
            result_lines.append("  (empty)")
        result_lines.append("")

        # 4. TP Prices
        result_lines.append("🎯 TP PRICES:")
        result_lines.append("-" * 60)
        tp_prices_all = await get_position_tp_prices()
        if tp_prices_all:
            for symbol, tp_info in sorted(tp_prices_all.items()):
                result_lines.append(f"  {symbol}:")
                result_lines.append(f"    Entry: {tp_info.get('entry', 'N/A')}")
                result_lines.append(f"    TP1: {tp_info.get('tp1', 'N/A')}")
                result_lines.append(f"    TP2: {tp_info.get('tp2', 'N/A')}")
                if tp_info.get("tp3"):
                    result_lines.append(f"    TP3: {tp_info.get('tp3', 'N/A')}")
                result_lines.append(f"    SL: {tp_info.get('sl', 'N/A')}")
                result_lines.append(f"    Side: {tp_info.get('side', 'N/A')}")
        else:
            result_lines.append("  (empty)")
        result_lines.append("")

        # 5. Pending SL Updates (Scheduled)
        result_lines.append("⏳ PENDING SL UPDATES (Scheduled):")
        result_lines.append("-" * 60)
        pending_updates = await get_pending_sl_updates()
        if pending_updates:
            for symbol, update_info in sorted(pending_updates.items()):
                result_lines.append(f"  {symbol}:")
                entry_time_str = update_info.get("entry_time", "")
                try:
                    if isinstance(entry_time_str, str):
                        entry_time = datetime.fromisoformat(entry_time_str).replace(
                            tzinfo=ZoneInfo("Asia/Tehran")
                        )
                    else:
                        entry_time = entry_time_str

                    time_elapsed = datetime.now(ZoneInfo("Asia/Tehran")) - entry_time
                    elapsed_minutes = time_elapsed.total_seconds() / 60.0
                    remaining_minutes = max(
                        0, SL_UPDATE_DELAY_MINUTES - elapsed_minutes
                    )

                    result_lines.append(
                        f"    Entry Time: {entry_time.strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    result_lines.append(f"    Elapsed: {elapsed_minutes:.1f} minutes")
                    result_lines.append(
                        f"    Remaining: {remaining_minutes:.1f} minutes"
                    )
                except Exception as e:
                    result_lines.append(
                        f"    Entry Time: {entry_time_str} (parse error: {e})"
                    )

                result_lines.append(
                    f"    New SL Price: {update_info.get('new_sl_price', 'N/A')}"
                )
                result_lines.append(
                    f"    Entry Price: {update_info.get('entry_price', 'N/A')}"
                )
                result_lines.append(f"    Side: {update_info.get('side', 'N/A')}")
        else:
            result_lines.append("  (empty)")
        result_lines.append("")

        result_lines.append("=" * 60)

        result_text = "\n".join(result_lines)
        log_print(f"[DEBUG_REDIS][{current_time}] Redis data fetched successfully")
        return result_text

    except Exception as e:
        error_msg = f"❌ Error fetching Redis data: {e}"
        log_print(f"[DEBUG_REDIS][{current_time}] {error_msg}")
        import traceback

        traceback.print_exc()
        return error_msg
