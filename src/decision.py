"""
decision.py — Combines indicators into a clear SEND / WAIT signal with reasoning.

Signal Strength gate:
  SEND NOW  requires rate >= target AND signal_strength >= 50
            (at least 2 indicators agree the rate is at a peak)
  MONITOR   rate near target, or rate above target but signals still mixed
  WAIT      rate below target — no point sending yet
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


def _bb_label(bb_pct: float) -> str:
    if bb_pct >= 1.0:   return "Above upper band — statistically extended"
    if bb_pct >= 0.8:   return f"{bb_pct*100:.0f}% — approaching upper band"
    if bb_pct >= 0.5:   return f"{bb_pct*100:.0f}% — mid range"
    return f"{bb_pct*100:.0f}% — near lower band"


def _strength_label(s: int) -> str:
    if s >= 67:  return "High"
    if s >= 34:  return "Medium"
    return "Low"


def decide(ind: Indicators) -> Decision:
    """
    Uses a dynamic target (75th percentile of last 72h rates).
    Requires signal_strength ≥ 50 (≥ 2 indicators) before firing SEND NOW.
    """
    rate      = ind.current_rate
    rsi       = ind.rsi_14
    trend     = ind.trend_label
    pred24    = ind.predicted_24h
    pred48    = ind.predicted_48h
    threshold = ind.dynamic_target
    strength  = ind.signal_strength
    unc       = ind.forecast_uncertainty
    reasons: list[str] = []

    # ── Context lines shown in dashboard ──────────────────────────────────────
    reasons.append(f"Current rate    : {rate:.4f} INR/USD")
    reasons.append(f"Dynamic target  : {threshold:.4f}  (75th pct of 72h range)")
    reasons.append(f"RSI (14)        : {rsi:.1f}  {'Overbought ↓' if rsi >= config.RSI_OVERBOUGHT else 'Normal' if rsi > config.RSI_OVERSOLD else 'Oversold ↑'}")
    reasons.append(f"Trend           : {trend.capitalize()} ({ind.trend_slope:+.5f}/hr)")
    reasons.append(f"Bollinger Band  : {_bb_label(ind.bb_pct)}")
    reasons.append(f"Signal Strength : {strength}/100  ({_strength_label(strength)})")
    reasons.append(f"Forecast 24h    : {pred24:.4f}  (±{unc:.4f})")
    reasons.append(f"Forecast 48h    : {pred48:.4f}")

    # ── Decision logic ────────────────────────────────────────────────────────
    if rate >= threshold:
        if strength >= 50:
            # Multiple indicators agree the rate is at or near a peak
            if rsi >= config.RSI_OVERBOUGHT and trend == "falling":
                summary = (
                    f"Rate {rate:.2f} is above target {threshold:.2f}. RSI overbought ({rsi:.0f}) "
                    f"and trend is falling — multiple signals confirm this is a peak. Send now."
                )
            elif ind.bb_pct >= 1.0:
                summary = (
                    f"Rate {rate:.2f} is above target {threshold:.2f} and above the Bollinger upper band "
                    f"— statistically extended. Signal strength {strength}/100. Good time to send."
                )
            elif rsi >= config.RSI_OVERBOUGHT:
                summary = (
                    f"Rate {rate:.2f} is above target {threshold:.2f}. RSI ({rsi:.0f}) is overbought "
                    f"and {strength}/100 signals agree. A correction is likely. Send now."
                )
            else:
                summary = (
                    f"Rate {rate:.2f} is above target {threshold:.2f}. "
                    f"{strength}/100 signal strength — conditions favour sending now."
                )
            signal = Signal.SEND_NOW

        else:
            # Rate is above target but signals are mixed — market still has momentum
            summary = (
                f"Rate {rate:.2f} is above target {threshold:.2f} but signals are mixed "
                f"(strength {strength}/100). The rate may still rise. Monitor closely."
            )
            signal = Signal.MONITOR

    elif rate >= threshold - 0.5:
        summary = (
            f"Rate {rate:.2f} is close to target {threshold:.2f} "
            f"({threshold - rate:.2f} away). Forecast 24h: {pred24:.2f}. Watch closely."
        )
        signal = Signal.MONITOR

    else:
        gap = threshold - rate
        # ── Falling trap: rate is heading lower — current rate is the best in 48h ──
        if trend == "falling" and pred24 < rate and pred48 < rate:
            summary = (
                f"Rate {rate:.2f} is {gap:.2f} below target {threshold:.2f}, but the trend is "
                f"falling and forecasts show further decline "
                f"(24h: {pred24:.2f}, 48h: {pred48:.2f}). "
                f"Current rate is the best available in the next 48h. Send now to avoid further loss."
            )
            signal = Signal.SEND_NOW
        else:
            if pred24 > threshold:
                outlook = f"Forecast suggests it may reach {pred24:.2f} in 24h — above target. Patience."
            elif pred48 > threshold:
                outlook = f"Forecast shows a possible window around {pred48:.2f} in 48h. Hold off for now."
            else:
                outlook = "No clear target window in the next 48h. Keep monitoring."
            summary = (
                f"Rate {rate:.2f} is {gap:.2f} below the dynamic target of {threshold:.2f}. "
                f"{outlook}"
            )
            signal = Signal.WAIT

    return Decision(signal=signal, reasons=reasons, summary=summary)


def format_message(decision: Decision, ind: Indicators, is_summary: bool = False) -> str:
    """Format a conversational Telegram message — reads like advice, not a data dump."""
    from datetime import datetime, timezone
    time_str = datetime.now(timezone.utc).strftime("%b %d · %H:%M UTC")

    rate      = ind.current_rate
    target    = ind.dynamic_target
    pred24    = ind.predicted_24h
    pred48    = ind.predicted_48h
    rsi       = ind.rsi_14
    trend     = ind.trend_label
    strength  = ind.signal_strength
    unc       = ind.forecast_uncertainty

    prefix = "📋 *1-Hour Update*\n\n" if is_summary else ""

    if decision.signal == Signal.SEND_NOW:
        if rate < target:
            # Falling trap — rate won't reach target, send before it falls further
            msg = (
                f"{prefix}"
                f"🟠 *Send now — rate is falling.*\n\n"
                f"Rate is *{rate:.2f}* — {target - rate:.2f} below your target of {target:.2f}.\n"
                f"Trend is falling. Forecast: 24h → {pred24:.2f}  |  48h → {pred48:.2f}.\n\n"
                f"The target is unlikely to be reached. *This is the best rate in the next 48h.*\n"
                f"Send now to avoid locking in an even lower rate later.\n\n"
                f"_Forecast → 24h: {pred24:.2f} ±{unc:.2f}  |  48h: {pred48:.2f}_"
            )
        else:
            if rsi >= 70:
                reason = f"RSI is at {rsi:.0f} — the rate is overbought and a drop is likely."
            elif ind.bb_pct >= 1.0:
                reason = f"The rate is above its Bollinger upper band — statistically extended."
            else:
                reason = f"Trend is {trend} and {strength}/100 indicators agree this is a peak."
            msg = (
                f"{prefix}"
                f"🟢 *Send your money now.*\n\n"
                f"The rate is *{rate:.2f}* — above your target of {target:.2f}.\n"
                f"{reason}\n\n"
                f"Signal strength: *{strength}/100* ({_strength_label(strength)})\n"
                f"Lock in this rate before it drops.\n\n"
                f"_Forecast → 24h: {pred24:.2f} ±{unc:.2f}  |  48h: {pred48:.2f}_"
            )

    elif decision.signal == Signal.MONITOR:
        if rate >= target:
            note = f"Rate is above target but signals are mixed ({strength}/100). May still rise."
        else:
            note = f"Rate is {target - rate:.2f} below target. Getting closer."
        msg = (
            f"{prefix}"
            f"🟡 *Watch closely.*\n\n"
            f"Rate is *{rate:.2f}*, target is {target:.2f}.\n"
            f"{note}\n\n"
            f"_Forecast → 24h: {pred24:.2f} ±{unc:.2f}  |  48h: {pred48:.2f}_"
        )

    else:  # WAIT
        if pred24 > target:
            outlook = f"Forecast shows it may reach {pred24:.2f} in 24h — above target. Patience."
        elif pred48 > target:
            outlook = f"A window may open around {pred48:.2f} in 48h. Hold off for now."
        else:
            outlook = "No strong window in the next 48h. Keep monitoring."
        msg = (
            f"{prefix}"
            f"🔴 *Don't send yet.*\n\n"
            f"Rate is *{rate:.2f}* — {target - rate:.2f} below your target of {target:.2f}.\n"
            f"Trend is {trend}, RSI is {rsi:.0f}.\n\n"
            f"{outlook}\n\n"
            f"_Forecast → 24h: {pred24:.2f} ±{unc:.2f}  |  48h: {pred48:.2f}_"
        )

    return (
        msg
        + f"\n\n_Checked at {time_str}_"
        + "\n\n⚠️ _Trend-based model only. Cannot predict news or policy events._"
    )
