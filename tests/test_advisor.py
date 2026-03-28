"""
Tests for send_in_one_hour() in src/advisor.py

Covers all verdict branches:
  - "yes"   : rate above target + RSI ≥ 70 or trend falling
  - "yes"   : rate above target + no strong signal (safe to send)
  - "maybe" : rate above target + rising trend + 1h forecast materially higher
  - "no"    : rate below target
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.predictor import Indicators
from src.advisor   import send_in_one_hour, send_tomorrow, best_time_to_send


def make_indicators(**overrides) -> Indicators:
    defaults = dict(
        current_rate   = 95.0,
        rsi_14         = 50.0,
        trend_slope    = 0.001,
        trend_label    = "sideways",
        ma_24h         = 94.5,
        ma_48h         = 94.0,
        dynamic_target = 94.5,
        predicted_24h  = 94.8,
        predicted_48h  = 94.9,
        confidence     = 0.75,
    )
    defaults.update(overrides)
    return Indicators(**defaults)


class TestSendInOneHour:

    def test_yes_when_overbought(self):
        """RSI ≥ 70 above target → send now."""
        ind = make_indicators(rsi_14=72.0)
        verdict, answer, tg = send_in_one_hour(ind)
        assert verdict == "yes"

    def test_yes_when_trend_falling(self):
        """Falling trend above target → send now."""
        ind = make_indicators(trend_label="falling", rsi_14=55.0)
        verdict, _, _ = send_in_one_hour(ind)
        assert verdict == "yes"

    def test_maybe_when_rising_with_upside(self):
        """Rising trend + 1h forecast meaningfully higher → maybe wait."""
        ind = make_indicators(
            trend_label   = "rising",
            rsi_14        = 50.0,
            predicted_24h = 97.0,   # large predicted rise → pred_1h > rate + 0.05
        )
        verdict, _, _ = send_in_one_hour(ind)
        assert verdict == "maybe"

    def test_no_when_below_target(self):
        """Rate below target → don't send."""
        ind = make_indicators(current_rate=93.0, dynamic_target=94.5)
        verdict, _, _ = send_in_one_hour(ind)
        assert verdict == "no"

    def test_yes_when_above_target_no_strong_signal(self):
        """Above target, sideways, RSI normal → safe yes."""
        ind = make_indicators(trend_label="sideways", rsi_14=50.0)
        verdict, _, _ = send_in_one_hour(ind)
        assert verdict == "yes"

    def test_answer_mentions_rate(self):
        """Dashboard answer must include the current rate."""
        ind = make_indicators()
        _, answer, _ = send_in_one_hour(ind)
        assert "95" in answer   # current_rate = 95.0

    def test_telegram_message_is_nonempty(self):
        """Telegram message must be a non-empty string."""
        ind = make_indicators()
        _, _, tg = send_in_one_hour(ind)
        assert isinstance(tg, str) and len(tg) > 10

    def test_returns_three_values(self):
        """Function always returns exactly (verdict, answer, tg)."""
        ind = make_indicators()
        result = send_in_one_hour(ind)
        assert len(result) == 3


class TestSendTomorrow:

    def test_send_today_when_forecast_drops(self):
        """Rate above target but forecast drops → send today not tomorrow."""
        ind = make_indicators(
            current_rate   = 95.0,
            dynamic_target = 94.5,
            predicted_24h  = 94.0,   # drops > 0.10
        )
        verdict, _, _ = send_tomorrow(ind)
        assert verdict == "now"

    def test_wait_when_forecast_higher_than_today(self):
        """Forecast > current rate and above target → wait for tomorrow."""
        ind = make_indicators(
            current_rate   = 94.4,
            dynamic_target = 94.5,
            predicted_24h  = 95.2,   # higher than today AND above target
        )
        verdict, _, _ = send_tomorrow(ind)
        assert verdict == "wait"

    def test_no_when_forecast_below_target(self):
        """Forecast still below target → neither today nor tomorrow is great."""
        ind = make_indicators(
            current_rate   = 93.0,
            dynamic_target = 94.5,
            predicted_24h  = 93.5,
            predicted_48h  = 93.8,
        )
        verdict, _, _ = send_tomorrow(ind)
        assert verdict == "no"


class TestBestTimeToSend:

    def test_now_when_above_target_and_overbought(self):
        """Peak conditions: above target, RSI ≥ 65, falling → best time is now."""
        ind = make_indicators(rsi_14=68.0, trend_label="falling")
        verdict, answer, _ = best_time_to_send(ind)
        assert verdict == "yes"
        assert "now" in answer.lower()

    def test_wait_when_forecast_24h_above_target(self):
        """Rate below target but 24h forecast above it → best window in 24h."""
        ind = make_indicators(
            current_rate   = 93.5,
            dynamic_target = 94.5,
            predicted_24h  = 95.0,
        )
        verdict, _, _ = best_time_to_send(ind)
        assert verdict == "wait"

    def test_no_window_when_all_forecasts_below_target(self):
        """Nothing good in 48h → no clear window."""
        ind = make_indicators(
            current_rate   = 92.0,
            dynamic_target = 94.5,
            predicted_24h  = 92.5,
            predicted_48h  = 92.8,
        )
        verdict, _, _ = best_time_to_send(ind)
        assert verdict == "no"
