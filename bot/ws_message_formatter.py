"""
WebSocket Message Formatter
Handles formatting and processing of Bybit WebSocket order messages.
"""

from datetime import datetime, timedelta
from config import (
    open_positions,
    position_entry_times,
    position_tp_prices,
    TARGET_CHANNEL,
    FIXED_MARGIN_USDT,
)
from clients import telClient
from api import get_positions, set_trading_stop, amend_order, get_sl_order_id
from capital_tracker import track_position_closed, track_rejected_order
from liquidity_analyzer import update_order_fill, get_24h_ticker


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


def identify_tp_sl_level(
    symbol: str, stop_order_type: str, trigger_price: float
) -> str:
    """
    Identify which TP or SL level this is (TP1, TP2, TP3, SL, SL2, SL3).

    :param symbol: Trading symbol
    :param stop_order_type: Order type (TakeProfit, PartialTakeProfit, StopLoss, PartialStopLoss)
    :param trigger_price: Trigger price
    :return: TP/SL identifier (e.g., "TP1", "SL2", "SL", etc.)
    """
    if not trigger_price or trigger_price == 0:
        # If trigger price is not available, return general type
        if "TakeProfit" in stop_order_type:
            return "TP" if "Partial" not in stop_order_type else "Partial TP"
        else:
            return "SL" if "Partial" not in stop_order_type else "Partial SL"

    tp_info = position_tp_prices.get(symbol)
    if not tp_info:
        # If TP info is not available, return general type
        if "TakeProfit" in stop_order_type:
            return "TP" if "Partial" not in stop_order_type else "Partial TP"
        else:
            return "SL" if "Partial" not in stop_order_type else "Partial SL"

    tolerance = 0.0001  # 0.01% tolerance

    # For TakeProfit
    if "TakeProfit" in stop_order_type:
        tp1_price = tp_info.get("tp1", 0)
        tp2_price = tp_info.get("tp2", 0)
        tp3_price = tp_info.get("tp3")

        if tp1_price and abs(trigger_price - tp1_price) / tp1_price < tolerance:
            return "TP1"
        elif tp2_price and abs(trigger_price - tp2_price) / tp2_price < tolerance:
            return "TP2"
        elif tp3_price and abs(trigger_price - tp3_price) / tp3_price < tolerance:
            return "TP3"
        else:
            return "TP" if "Partial" not in stop_order_type else "Partial TP"

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


# ---------------- SL2 SETTER AFTER TP1 ---------------- #
async def set_sl2_after_tp1(symbol: str, tp_data: dict):
    """
    Set SL2 for remaining position after TP1 is triggered.
    Only sets SL2 if 30 minutes have passed since entry time.

    Logic:
    - If current price > TP1 + 0.25%: SL2 = TP1 + 0.11%
    - Otherwise: SL2 = TP1
    """
    try:
        # Check if 30 minutes have passed since entry time
        entry_time = position_entry_times.get(symbol)
        if not entry_time:
            print(
                f"[WARN] Entry time not found for {symbol}, cannot verify 30-minute rule"
            )
            return

        time_elapsed = datetime.now() - entry_time
        if time_elapsed < timedelta(minutes=30):
            print(
                f"[INFO] SL2 skipped for {symbol}: Only {time_elapsed.total_seconds()/60:.1f} minutes elapsed (need 30 minutes)"
            )
            await telClient.send_message(
                TARGET_CHANNEL,
                f"⏰ **SL2 Skipped**\n\n"
                f"```\n"
                f"Symbol: {symbol}\n"
                f"Reason: Less than 30 minutes since entry\n"
                f"Time elapsed: {time_elapsed.total_seconds()/60:.1f} minutes\n"
                f"Required: 30 minutes\n"
                f"```",
            )
            return

        positions = get_positions(symbol=symbol)
        if not positions:
            print(f"[WARN] Position not found for {symbol}, cannot set SL2")
            return

        position = positions[0]
        side = position.get("side", "")
        size = float(position.get("size", 0))

        if size == 0:
            print(f"[WARN] Invalid position data for {symbol}, cannot set SL2")
            return

        # Get TP1 price from stored data
        tp_info = position_tp_prices.get(symbol)
        if not tp_info:
            print(f"[WARN] TP info not found for {symbol}, cannot set SL2")
            return

        tp1_price = tp_info.get("tp1", 0)
        if tp1_price == 0:
            print(f"[WARN] TP1 price not found for {symbol}, cannot set SL2")
            return

        # Get current market price
        ticker = get_24h_ticker(symbol)
        if not ticker:
            print(f"[WARN] Failed to get current price for {symbol}, cannot set SL2")
            return

        current_price = ticker.get("lastPrice", 0)
        if current_price == 0:
            print(f"[WARN] Invalid current price for {symbol}, cannot set SL2")
            return

        # Calculate TP1 + 0.25% threshold
        if side == "Buy":
            tp1_threshold = tp1_price * (1 + 0.0025)  # TP1 + 0.25%
            # If current price > TP1 + 0.25%, set SL = TP1 + 0.11%
            # Otherwise, set SL = TP1
            if current_price > tp1_threshold:
                sl2_price = tp1_price * (1 + 0.0011)  # TP1 + 0.11%
            else:
                sl2_price = tp1_price  # TP1
        else:  # Sell
            tp1_threshold = tp1_price * (1 - 0.0025)  # TP1 - 0.25%
            # If current price < TP1 - 0.25%, set SL = TP1 - 0.11%
            # Otherwise, set SL = TP1
            if current_price < tp1_threshold:
                sl2_price = tp1_price * (1 - 0.0011)  # TP1 - 0.11%
            else:
                sl2_price = tp1_price  # TP1

        # Try to get existing SL order ID and amend it
        sl_order_id = get_sl_order_id(symbol, positionIdx=0)

        if sl_order_id:
            # Update existing SL order using amend
            try:
                amend_order(
                    symbol=symbol,
                    orderId=sl_order_id,
                    stopLoss=str(sl2_price),
                    slTriggerBy="LastPrice",
                )
                print(
                    f"[INFO] SL2 updated via amend for {symbol}: {sl2_price:.4f} (TP1: {tp1_price:.4f}, current: {current_price:.4f}, side: {side}, size: {size})"
                )
            except Exception as e:
                print(
                    f"[WARN] Failed to amend SL order for {symbol}, trying set_trading_stop: {e}"
                )
                # Fallback to set_trading_stop if amend fails
                set_trading_stop(
                    symbol=symbol,
                    positionIdx=0,
                    tpslMode="Partial",
                    sl=str(sl2_price),
                    slSize=str(size),
                )
                print(
                    f"[INFO] SL2 set via set_trading_stop for {symbol}: {sl2_price:.4f} (TP1: {tp1_price:.4f}, current: {current_price:.4f}, side: {side}, size: {size})"
                )
        else:
            # No existing SL order, use set_trading_stop to create new one
            set_trading_stop(
                symbol=symbol,
                positionIdx=0,
                tpslMode="Partial",
                sl=str(sl2_price),
                slSize=str(size),
            )
            print(
                f"[INFO] SL2 set for {symbol}: {sl2_price:.4f} (TP1: {tp1_price:.4f}, current: {current_price:.4f}, side: {side}, size: {size})"
            )

        # Notify Telegram
        await telClient.send_message(
            TARGET_CHANNEL,
            f"🛡️ **SL2 Set After TP1**\n\n"
            f"```\n"
            f"Symbol: {symbol}\n"
            f"Side: {side}\n"
            f"TP1 Price: {tp1_price:,.4f}\n"
            f"Current Price: {current_price:,.4f}\n"
            f"SL2 Price: {sl2_price:,.4f}\n"
            f"Remaining Size: {size:,.4f}\n"
            f"Time elapsed: {time_elapsed.total_seconds()/60:.1f} minutes\n"
            f"```",
        )

    except Exception as e:
        print(f"[ERROR] Failed to set SL2 for {symbol}: {e}")
        import traceback

        traceback.print_exc()
        await telClient.send_message(
            TARGET_CHANNEL,
            f"⚠️ **Error Setting SL2**\n\n" f"Symbol: {symbol}\n" f"Error: {str(e)}",
        )


# ---------------- SL3 SETTER AFTER TP2 ---------------- #
async def set_sl3_after_tp2(symbol: str, tp_data: dict):
    """
    Set SL3 for remaining position after TP2 is triggered.
    SL3 is only set if 30 minutes have passed since entry time.
    SL3 = TP2 * (1 + 0.0011) for Buy
    SL3 = TP2 * (1 - 0.0011) for Sell
    """
    try:
        # Check if 30 minutes have passed since entry time
        entry_time = position_entry_times.get(symbol)
        if not entry_time:
            print(
                f"[WARN] Entry time not found for {symbol}, cannot verify 30-minute rule"
            )
            return

        time_elapsed = datetime.now() - entry_time
        if time_elapsed < timedelta(minutes=30):
            print(
                f"[INFO] SL3 skipped for {symbol}: Only {time_elapsed.total_seconds()/60:.1f} minutes elapsed (need 30 minutes)"
            )
            await telClient.send_message(
                TARGET_CHANNEL,
                f"⏰ **SL3 Skipped**\n\n"
                f"```\n"
                f"Symbol: {symbol}\n"
                f"Reason: Price reached TP2 too quickly\n"
                f"Time elapsed: {time_elapsed.total_seconds()/60:.1f} minutes\n"
                f"Required: 30 minutes\n"
                f"```",
            )
            return

        positions = get_positions(symbol=symbol)
        if not positions:
            print(f"[WARN] Position not found for {symbol}, cannot set SL3")
            return

        position = positions[0]
        side = position.get("side", "")
        size = float(position.get("size", 0))

        # Get TP2 from triggered price or stored data
        tp2_price = float(tp_data.get("triggerPrice", 0))
        if tp2_price == 0:
            # If triggerPrice is not available, use position_tp_prices
            tp_info = position_tp_prices.get(symbol)
            if tp_info:
                tp2_price = tp_info.get("tp2", 0)
            if tp2_price == 0:
                # If still not found, use avgPrice
                tp2_price = float(position.get("avgPrice", 0))

        if tp2_price == 0 or size == 0:
            print(f"[WARN] Invalid position data for {symbol}, cannot set SL3")
            return

        # Calculate SL3 based on TP2
        if side == "Buy":
            sl3_price = tp2_price * (1 + 0.0011)
        else:  # Sell
            sl3_price = tp2_price * (1 - 0.0011)

        # Try to get existing SL order ID and amend it
        sl_order_id = get_sl_order_id(symbol, positionIdx=0)

        if sl_order_id:
            # Update existing SL order using amend
            try:
                amend_order(
                    symbol=symbol,
                    orderId=sl_order_id,
                    stopLoss=str(sl3_price),
                    slTriggerBy="LastPrice",
                )
                print(
                    f"[INFO] SL3 updated via amend for {symbol}: {sl3_price:.4f} (TP2: {tp2_price:.4f}, side: {side}, size: {size})"
                )
            except Exception as e:
                print(
                    f"[WARN] Failed to amend SL order for {symbol}, trying set_trading_stop: {e}"
                )
                # Fallback to set_trading_stop if amend fails
                set_trading_stop(
                    symbol=symbol,
                    positionIdx=0,
                    tpslMode="Partial",
                    sl=str(sl3_price),
                    slSize=str(size),
                )
                print(
                    f"[INFO] SL3 set via set_trading_stop for {symbol}: {sl3_price:.4f} (TP2: {tp2_price:.4f}, side: {side}, size: {size})"
                )
        else:
            # No existing SL order, use set_trading_stop to create new one
            set_trading_stop(
                symbol=symbol,
                positionIdx=0,
                tpslMode="Partial",
                sl=str(sl3_price),
                slSize=str(size),
            )
            print(
                f"[INFO] SL3 set for {symbol}: {sl3_price:.4f} (TP2: {tp2_price:.4f}, side: {side}, size: {size})"
            )

        # Notify Telegram
        await telClient.send_message(
            TARGET_CHANNEL,
            f"🛡️ **SL3 Set After TP2**\n\n"
            f"```\n"
            f"Symbol: {symbol}\n"
            f"Side: {side}\n"
            f"TP2 Price: {tp2_price:,.4f}\n"
            f"SL3 Price: {sl3_price:,.4f}\n"
            f"Remaining Size: {size:,.4f}\n"
            f"Time elapsed: {time_elapsed.total_seconds()/60:.1f} minutes\n"
            f"```",
        )

    except Exception as e:
        print(f"[ERROR] Failed to set SL3 for {symbol}: {e}")
        await telClient.send_message(
            TARGET_CHANNEL,
            f"⚠️ **Error Setting SL3**\n\n" f"Symbol: {symbol}\n" f"Error: {str(e)}",
        )


# ---------------- MAIN HANDLER ---------------- #
async def handle_ws_message(item: dict):
    """
    Handle WebSocket messages from Bybit.
    Formats and sends appropriate messages to Telegram.
    """
    ws_type = item.get("msg_type")
    data = item.get("data", {})
    symbol = item.get("symbol", "")
    closed_pnl = item.get("closed_pnl", 0.0)

    order_status = data.get("orderStatus", "")
    stop_order_type = data.get("stopOrderType", "")
    create_type = data.get("createType", "")

    # Show message for SL/TP orders that have been created (Untriggered)
    # Only for createType related to SL/TP created by the system
    if order_status == "Untriggered" and stop_order_type:
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
        text = await format_new_order_filled(data)
        await telClient.send_message(TARGET_CHANNEL, text)

    elif ws_type == "close_position":
        # Remove symbol from open_positions and related data
        open_positions.discard(symbol)
        position_entry_times.pop(symbol, None)
        position_tp_prices.pop(symbol, None)
        # Track position closed for capital tracking
        track_position_closed(symbol)
        text = await format_position_closed(data, closed_pnl)
        await telClient.send_message(TARGET_CHANNEL, text)

    elif ws_type == "cancel_order":
        text = await format_order_cancelled(data)
        await telClient.send_message(TARGET_CHANNEL, text)

    elif ws_type == "sl_tp_triggered":
        # SL/TP triggered
        text = await format_sl_tp_triggered(data)
        if text:
            await telClient.send_message(TARGET_CHANNEL, text)
            # If position closed, remove from open_positions and related data
            if data.get("closeOnTrigger") and data.get("reduceOnly"):
                open_positions.discard(symbol)
                position_entry_times.pop(symbol, None)
                position_tp_prices.pop(symbol, None)
                # Track position closed for capital tracking
                track_position_closed(symbol)

        # If TP1 or TP2 (PartialTakeProfit) triggered, set SL2 or SL3
        stop_order_type = data.get("stopOrderType", "")
        if stop_order_type == "PartialTakeProfit":
            # Identify which TP was triggered using trigger price
            trigger_price = safe_float(data.get("triggerPrice", 0))
            tp_level = identify_tp_sl_level(symbol, stop_order_type, trigger_price)

            if tp_level == "TP1":
                # TP1 triggered, set SL2
                await set_sl2_after_tp1(symbol, data)
            elif tp_level == "TP2":
                # TP2 triggered, set SL3
                await set_sl3_after_tp2(symbol, data)
            # TP3 doesn't need SL update (position should be closed or near closing)

    elif ws_type == "sl_tp_created":
        # SL/TP created (Untriggered) - for information only
        text = await format_sl_tp_created(data)
        if text:
            await telClient.send_message(TARGET_CHANNEL, text)

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
        if order_status == "Filled":
            if data.get("reduceOnly"):
                # Position closed by market order
                open_positions.discard(symbol)
                position_entry_times.pop(symbol, None)
                position_tp_prices.pop(symbol, None)
                # Track position closed for capital tracking
                track_position_closed(symbol)
                text = await format_position_closed(data, closed_pnl)
                await telClient.send_message(TARGET_CHANNEL, text)
            else:
                # New order filled
                text = await format_new_order_filled(data)
                await telClient.send_message(TARGET_CHANNEL, text)
        elif stop_order_type and order_status in ["Filled", "Triggered"]:
            text = await format_sl_tp_triggered(data)
            if text:
                await telClient.send_message(TARGET_CHANNEL, text)
                if data.get("closeOnTrigger") and data.get("reduceOnly"):
                    open_positions.discard(symbol)
                    position_entry_times.pop(symbol, None)
                    position_tp_prices.pop(symbol, None)
