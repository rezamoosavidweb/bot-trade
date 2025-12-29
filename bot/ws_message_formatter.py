"""
WebSocket Message Formatter
Handles formatting and processing of Bybit WebSocket order messages.
"""

from config import open_positions
from clients import telClient
from config import TARGET_CHANNEL


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
    # فقط برای اطلاعات - معمولاً نمایش نمی‌دهیم
    symbol = data.get("symbol", "—")
    stop_order_type = data.get("stopOrderType", "—")
    order_status = data.get("orderStatus", "—")
    qty = safe_float(data.get("qty", 0))
    trigger_price = safe_float(data.get("triggerPrice", 0))
    create_type = format_create_type(data.get("createType", "—"))
    order_id = data.get("orderId", "—")

    # فقط اگر Untriggered است، پیام ساده نمایش می‌دهیم
    if order_status == "Untriggered":
        tp_sl_emoji = "🎯" if "TakeProfit" in stop_order_type else "🛑"
        text = (
            f"{tp_sl_emoji} **{stop_order_type} Created**\n\n"
            f"```\n"
            f"Symbol: {symbol}\n"
            f"Type: {stop_order_type}\n"
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

    text = (
        f"{emoji} **{stop_order_type} Triggered**\n\n"
        f"```\n"
        f"Symbol: {symbol}\n"
        f"Side: {side}\n"
        f"Type: {stop_order_type}\n"
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

    # اگر SL/TP order است، پیام خاص نمایش می‌دهیم
    if stop_order_type:
        emoji = "🎯" if "TakeProfit" in stop_order_type else "🛑"
        title = f"{emoji} **{stop_order_type} Cancelled**"
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

    # نمایش پیام برای SL/TP orders که ایجاد شده‌اند (Untriggered)
    # فقط برای createType های مربوط به SL/TP که توسط سیستم ایجاد شده‌اند
    if order_status == "Untriggered" and stop_order_type:
        # نمایش پیام برای SL/TP که ایجاد شده‌اند
        sl_tp_create_types = [
            "CreateByPartialTakeProfit",
            "CreateByStopLoss",
            "CreateByTakeProfit",
            "CreateByPartialStopLoss",
        ]
        # اگر ws_type == "sl_tp_created" است یا createType مناسب است، پیام نمایش می‌دهیم
        if ws_type == "sl_tp_created" or create_type in sl_tp_create_types:
            text = await format_sl_tp_created(data)
            if text:
                await telClient.send_message(TARGET_CHANNEL, text)
                return  # پیام ارسال شد، دیگر نیازی به ادامه نیست

        # اگر createType مناسب نبود، return می‌کنیم (پیام نمایش نمی‌دهیم)
        return

    # Handle different message types based on ws_type
    if ws_type == "new_order":
        text = await format_new_order_filled(data)
        await telClient.send_message(TARGET_CHANNEL, text)

    elif ws_type == "close_position":
        # پاک کردن symbol از open_positions
        open_positions.discard(symbol)
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
            # اگر position بسته شد، از open_positions حذف می‌کنیم
            if data.get("closeOnTrigger") and data.get("reduceOnly"):
                open_positions.discard(symbol)

    elif ws_type == "sl_tp_created":
        # SL/TP created (Untriggered) - فقط برای اطلاعات
        text = await format_sl_tp_created(data)
        if text:
            await telClient.send_message(TARGET_CHANNEL, text)

    elif ws_type == "rejected" or order_status == "Rejected":
        symbol = data.get("symbol", "—")
        reject_reason = format_reject_reason(data.get("rejectReason", "EC_Others"))
        order_id = data.get("orderId", "—")

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
