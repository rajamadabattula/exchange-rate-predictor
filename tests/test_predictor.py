"""
Tests for compute_rsi() in src/predictor.py

RSI rules:
  - Not enough data          → returns 50.0 (neutral)
  - Only gains (rising)      → returns 100.0
  - Only losses (falling)    → returns 0.0
  - Alternating movement     → returns something in the neutral band (30–70)
  - Value always 0–100       → boundary check
"""

import pandas as pd
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.predictor import compute_rsi


def _series(values: list[float]) -> pd.Series:
    return pd.Series(values, dtype=float)


class TestComputeRSI:

    def test_not_enough_data_returns_neutral(self):
        """Fewer than period+1 points → 50.0 (no signal either way)."""
        series = _series([94.0, 94.5, 95.0])   # only 3 points, period=14
        assert compute_rsi(series) == 50.0

    def test_exactly_at_boundary_returns_neutral(self):
        """Exactly period points (15 - 1 = 14) still not enough → 50.0."""
        series = _series([float(i) for i in range(14)])
        assert compute_rsi(series) == 50.0

    def test_all_gains_returns_100(self):
        """Steadily rising series — no losses → RSI = 100."""
        series = _series([float(i) for i in range(30)])   # 0,1,2,...,29
        assert compute_rsi(series) == 100.0

    def test_all_losses_returns_zero(self):
        """Steadily falling series — no gains → RSI = 0."""
        series = _series([float(30 - i) for i in range(30)])   # 30,29,...,1
        assert compute_rsi(series) == 0.0

    def test_alternating_is_neutral(self):
        """Up-down-up-down pattern → RSI near 50 (neutral band)."""
        values = []
        base = 94.0
        for i in range(30):
            base += 0.1 if i % 2 == 0 else -0.1
            values.append(round(base, 4))
        rsi = compute_rsi(_series(values))
        assert 30.0 <= rsi <= 70.0, f"Expected neutral RSI, got {rsi}"

    def test_output_always_in_valid_range(self):
        """RSI must always be between 0 and 100."""
        import random
        random.seed(42)
        values = [94.0 + random.uniform(-1, 1) for _ in range(50)]
        rsi = compute_rsi(_series(values))
        assert 0.0 <= rsi <= 100.0

    def test_custom_period(self):
        """Passing a custom period is respected — 5-period RSI on 10 points."""
        series = _series([float(i) for i in range(10)])
        rsi = compute_rsi(series, period=5)
        assert rsi == 100.0   # all gains → 100

    def test_return_type_is_float(self):
        """Return value is always a Python float."""
        series = _series([float(i) for i in range(30)])
        assert isinstance(compute_rsi(series), float)
