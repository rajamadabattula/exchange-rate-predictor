"""
Tests for decide() in src/decision.py

Covers every branch of the decision logic:
  1. Rate above target + RSI overbought + trend falling  → SEND NOW (strongest)
  2. Rate above target + RSI overbought                  → SEND NOW
  3. Rate above target + forecast drop + trend falling   → SEND NOW
  4. Rate above target + trend sideways                  → SEND NOW
  5. Rate above target + trend rising + RSI < 60         → WAIT
  6. Rate within 0.5 of target                           → MONITOR
  7. Rate well below target                              → WAIT
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.predictor import Indicators
from src.decision  import decide, Signal


def make_indicators(**overrides) -> Indicators:
    """Build a default Indicators object and apply any field overrides."""
    defaults = dict(
        current_rate   = 95.0,
        rsi_14         = 50.0,
        trend_slope    = 0.001,
        trend_label    = "sideways",
        ma_24h         = 94.5,
        ma_48h         = 94.0,
        dynamic_target = 94.5,    # 48h avg (94.0) + 0.5
        predicted_24h  = 94.8,
        predicted_48h  = 94.9,
        confidence     = 0.75,
    )
    defaults.update(overrides)
    return Indicators(**defaults)


class TestDecide:

    # ── SEND NOW cases ────────────────────────────────────────────────────────

    def test_send_now_overbought_and_falling(self):
        """Strongest signal: above target + RSI ≥ 70 + falling trend."""
        ind = make_indicators(rsi_14=75.0, trend_label="falling")
        dec = decide(ind)
        assert dec.signal == Signal.SEND_NOW

    def test_send_now_overbought_sideways(self):
        """RSI ≥ 70 alone triggers SEND NOW regardless of trend."""
        ind = make_indicators(rsi_14=72.0, trend_label="sideways")
        dec = decide(ind)
        assert dec.signal == Signal.SEND_NOW

    def test_send_now_forecast_drop_and_falling(self):
        """Forecast drops > 0.10 below current rate + falling trend → SEND NOW."""
        ind = make_indicators(
            current_rate  = 95.0,
            predicted_24h = 94.7,   # 0.3 drop
            trend_label   = "falling",
            rsi_14        = 55.0,
        )
        dec = decide(ind)
        assert dec.signal == Signal.SEND_NOW

    def test_send_now_sideways_trend(self):
        """Sideways trend above target → lock it in."""
        ind = make_indicators(trend_label="sideways", rsi_14=55.0)
        dec = decide(ind)
        assert dec.signal == Signal.SEND_NOW

    # ── WAIT cases ────────────────────────────────────────────────────────────

    def test_wait_rising_trend_low_rsi(self):
        """Rate above target but still rising with RSI < 60 → WAIT (may go higher)."""
        ind = make_indicators(
            trend_label   = "rising",
            rsi_14        = 50.0,
            predicted_24h = 95.5,   # forecast higher
        )
        dec = decide(ind)
        assert dec.signal == Signal.WAIT

    def test_wait_rate_below_target(self):
        """Rate clearly below target → always WAIT."""
        ind = make_indicators(
            current_rate   = 93.0,
            dynamic_target = 94.5,
        )
        dec = decide(ind)
        assert dec.signal == Signal.WAIT

    def test_wait_summary_mentions_gap(self):
        """WAIT message should mention the gap to the target."""
        ind = make_indicators(current_rate=93.0, dynamic_target=94.5)
        dec = decide(ind)
        assert "1.50" in dec.summary or "below" in dec.summary.lower()

    # ── MONITOR case ──────────────────────────────────────────────────────────

    def test_monitor_when_rate_close_to_target(self):
        """Rate within 0.5 of target → MONITOR."""
        ind = make_indicators(current_rate=94.2, dynamic_target=94.5)
        dec = decide(ind)
        assert dec.signal == Signal.MONITOR

    def test_monitor_boundary_exactly_half(self):
        """Rate exactly 0.5 below target → still MONITOR."""
        ind = make_indicators(current_rate=94.0, dynamic_target=94.5)
        dec = decide(ind)
        assert dec.signal == Signal.MONITOR

    # ── Structure checks ──────────────────────────────────────────────────────

    def test_decision_has_reasons(self):
        """Every decision must include reasoning lines."""
        ind = make_indicators()
        dec = decide(ind)
        assert len(dec.reasons) >= 4

    def test_decision_has_summary(self):
        """Summary must be a non-empty string."""
        ind = make_indicators()
        dec = decide(ind)
        assert isinstance(dec.summary, str) and len(dec.summary) > 10
