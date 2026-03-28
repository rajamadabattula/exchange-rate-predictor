"""
decision.py — Combines indicators into a clear SEND / WAIT signal with reasoning.
"""

from dataclasses import dataclass
from enum import Enum

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from src.predictor import Indicators


class Signal(Enum):
    SEND_NOW  = "SEND NOW"
    WAIT      = "WAIT"
    MONITOR   = "MONITOR"


@dataclass
class Decision:
    signal:  Signal
    reasons: list[str]
    summary: str


def decide(ind: Indicators) -> Decision:
    """
    Uses a dynamic target (48h average + 0.5) instead of a fixed threshold.
    This keeps the target relevant as the market moves.
    """
    rate      = ind.current_rate
    rsi       = ind.rsi_14
    trend     = ind.trend_label
    pred24    = ind.predicted_24h
    threshold = ind.dynamic_target          # ← dynamic, updates every hour
    reasons: list[str] = []

    # ── Context lines shown in dashboard ──────────────────────────────────────
    reasons.append(f"Current rate   : {rate:.4f} INR/USD")
    reasons.append(f"Dynamic target : {threshold:.4f}  (48h avg {ind.ma_48h:.4f} + 0.5)")
    reasons.append(f"RSI (14)       : {rsi:.1f}  {'Overbought' if rsi >= config.RSI_OVERBOUGHT else 'Normal' if rsi > config.RSI_OVERSOLD else 'Oversold'}")
    reasons.append(f"Trend          : {trend.capitalize()} ({ind.trend_slope:+.5f}/hr)")
    reasons.append(f"Forecast 24h   : {pred24:.4f}  (R²={ind.confidence:.2f})")
    reasons.append(f"Forecast 48h   : {ind.predicted_48h:.4f}")

    # ── Decision logic ────────────────────────────────────────────────────────
    if rate >= threshold:
        drop_predicted = pred24 < rate - 0.10

        if rsi >= config.RSI_OVERBOUGHT and trend == "falling":
            signal  = Signal.SEND_NOW
            summary = (
                f"Rate {rate:.2f} is above target {threshold:.2f}. RSI overbought ({rsi:.0f}) "
                f"and trend is falling — high chance of a drop. Send now."
            )
        elif rsi >= config.RSI_OVERBOUGHT:
            signal  = Signal.SEND_NOW
            summary = (
                f"Rate {rate:.2f} is above target {threshold:.2f}. RSI ({rsi:.0f}) signals "
                f"overbought conditions — a correction is likely. Good time to send."
            )
        elif drop_predicted and trend == "falling":
            signal  = Signal.SEND_NOW
            summary = (
                f"Rate {rate:.2f} is above target {threshold:.2f}. Forecast drops to "
                f"{pred24:.2f} in 24h. Lock in this rate now."
            )
        elif trend == "sideways":
            signal  = Signal.SEND_NOW
            summary = (
                f"Rate {rate:.2f} is above target {threshold:.2f} and moving sideways. "
                f"No strong upside expected. Safe to send now."
            )
        elif trend == "rising" and rsi < 60:
            signal  = Signal.WAIT
            summary = (
                f"Rate {rate:.2f} is above target {threshold:.2f} but still rising "
                f"with RSI room ({rsi:.0f}). Forecast: {pred24:.2f} in 24h. "
                f"Consider waiting for a better rate."
            )
        else:
            signal  = Signal.SEND_NOW
            summary = (
                f"Rate {rate:.2f} is above target {threshold:.2f}. Conditions acceptable. Send now."
            )

    elif rate >= threshold - 0.5:
        signal  = Signal.MONITOR
        summary = (
            f"Rate {rate:.2f} is close to target {threshold:.2f}. "
            f"Forecast 24h: {pred24:.2f}. Watch closely."
        )
    else:
        gap    = threshold - rate
        signal = Signal.WAIT
        summary = (
            f"Rate {rate:.2f} is {gap:.2f} below the dynamic target of {threshold:.2f}. "
            f"Forecast 24h: {pred24:.2f}. Wait for a better window."
        )

    return Decision(signal=signal, reasons=reasons, summary=summary)


def format_message(decision: Decision, ind: Indicators, is_summary: bool = False) -> str:
    """Format a conversational Telegram message — reads like advice, not a data dump."""
    from datetime import datetime, timezone
    time_str = datetime.now(timezone.utc).strftime("%b %d · %H:%M UTC")

    rate    = ind.current_rate
    target  = ind.dynamic_target
    pred24  = ind.predicted_24h
    pred48  = ind.predicted_48h
    rsi     = ind.rsi_14
    trend   = ind.trend_label

    prefix = "📋 *3-Hour Update*\n\n" if is_summary else ""

    if decision.signal == Signal.SEND_NOW:
        rsi_note = (
            f"RSI is at {rsi:.0f} — the rate is overbought and a drop is likely."
            if rsi >= 70 else
            f"The trend is turning and forecast shows a dip to {pred24:.2f} in 24h."
        )
        msg = (
            f"{prefix}"
            f"🟢 *Send your money now.*\n\n"
            f"The rate is *{rate:.2f}* — above your target of {target:.2f}.\n"
            f"{rsi_note}\n\n"
            f"Lock in this rate before it drops.\n\n"
            f"_Forecast → 24h: {pred24:.2f}  |  48h: {pred48:.2f}_"
        )

    elif decision.signal == Signal.MONITOR:
        msg = (
            f"{prefix}"
            f"🟡 *Almost there — stay close.*\n\n"
            f"Rate is *{rate:.2f}*, just {target - rate:.2f} below your target of {target:.2f}.\n"
            f"Forecast shows it could reach {pred24:.2f} in the next 24 hours.\n\n"
            f"Don't send yet — check back soon.\n\n"
            f"_Forecast → 24h: {pred24:.2f}  |  48h: {pred48:.2f}_"
        )

    else:  # WAIT
        if pred24 > target:
            outlook = f"Good news — it's predicted to hit {pred24:.2f} in 24h, which is above your target. Patience."
        elif pred48 > target:
            outlook = f"It may reach {pred48:.2f} in 48h. Hold off for now."
        else:
            outlook = f"No strong target window in the next 48h. Keep monitoring."

        msg = (
            f"{prefix}"
            f"🔴 *Don't send yet.*\n\n"
            f"Rate is *{rate:.2f}* — {target - rate:.2f} below your target of {target:.2f}.\n"
            f"Trend is {trend}, RSI is {rsi:.0f}.\n\n"
            f"{outlook}\n\n"
            f"_Forecast → 24h: {pred24:.2f}  |  48h: {pred48:.2f}_"
        )

    return msg + f"\n\n_Checked at {time_str}_"
