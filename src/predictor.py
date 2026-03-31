"""
predictor.py — Computes RSI, Bollinger Bands, trend, signal strength,
               and a 48-hour linear forecast from historical USD/INR rate data.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Data classes
# -----------------------------------------------------------------------------

@dataclass
class Indicators:
    current_rate:         float
    rsi_14:               float          # RSI over last 14 periods
    trend_slope:          float          # Positive = rising, negative = falling
    trend_label:          str            # "rising" | "falling" | "sideways"
    ma_24h:               float          # 24-hour moving average
    ma_48h:               float          # 48-hour moving average
    dynamic_target:       float          # 48h average + 0.5 — updates every hour
    predicted_24h:        float          # Predicted rate 24 hours from now
    predicted_48h:        float          # Predicted rate 48 hours from now
    confidence:           float          # R² of the linear regression (0–1)
    bb_upper:             float = 0.0    # Bollinger upper band (20-period, 2σ)
    bb_lower:             float = 0.0    # Bollinger lower band
    bb_pct:               float = 0.5    # 0 = at lower band, 1 = at upper, >1 = above
    signal_strength:      int   = 0      # 0–100: how many indicators agree on a drop
    forecast_uncertainty: float = 0.0   # ±1σ of regression residuals


# -----------------------------------------------------------------------------
# Indicators
# -----------------------------------------------------------------------------

def compute_rsi(series: pd.Series, period: int = 14) -> float:
    """Compute RSI for the last `period` data points."""
    if len(series) < period + 1:
        return 50.0  # Not enough data — neutral
    delta    = series.diff().dropna()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.rolling(window=period).mean().iloc[-1]
    avg_loss = loss.rolling(window=period).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs  = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi), 2)


def compute_trend(series: pd.Series, window: int = 24) -> tuple[float, str]:
    """
    Fit a linear regression over the last `window` points.
    Returns (slope_per_hour, label).
    """
    data = series.iloc[-window:].reset_index(drop=True)
    if len(data) < 4:
        return 0.0, "sideways"
    X = np.arange(len(data)).reshape(-1, 1)
    y = data.values
    model = LinearRegression().fit(X, y)
    slope = float(model.coef_[0])
    if slope > 0.005:
        label = "rising"
    elif slope < -0.005:
        label = "falling"
    else:
        label = "sideways"
    return round(slope, 6), label


def compute_bollinger(series: pd.Series, window: int = 20) -> tuple[float, float, float]:
    """
    Compute Bollinger Bands (20-period, 2 standard deviations).
    Returns (upper_band, lower_band, pct_b).
    pct_b: 0 = at lower band, 1 = at upper band, >1 = above upper band.
    """
    if len(series) < window:
        mid = float(series.mean())
        return round(mid, 4), round(mid, 4), 0.5
    recent = series.iloc[-window:]
    mid    = float(recent.mean())
    std    = float(recent.std())
    upper  = round(mid + 2 * std, 4)
    lower  = round(mid - 2 * std, 4)
    curr   = float(series.iloc[-1])
    band   = upper - lower
    pct    = round((curr - lower) / band, 4) if band > 0 else 0.5
    return upper, lower, pct


def compute_signal_strength(rsi: float, trend: str, bb_pct: float) -> int:
    """
    Score 0–100 indicating how strongly multiple indicators agree that
    the rate is at a peak and likely to drop (SEND NOW confidence).

    Requires ≥2 signals to reach 50+ (the SEND NOW threshold):
      RSI ≥ 70          → +35 (overbought)
      RSI 60–70         → +15
      BB ≥ upper band   → +35 (statistically extended)
      BB 80–100%        → +15
      Trend falling     → +30
      Trend sideways    → +15
    """
    score = 0
    if rsi >= 70:              score += 35
    elif rsi >= 60:            score += 15
    if bb_pct >= 1.0:          score += 35
    elif bb_pct >= 0.8:        score += 15
    if trend == "falling":     score += 30
    elif trend == "sideways":  score += 15
    return min(score, 100)


def forecast_rates(df: pd.DataFrame, hours_ahead: int = config.FORECAST_HOURS) -> tuple[float, float, float, float]:
    """
    Use linear regression on the last 7 days (168 hours) of data
    to forecast the rate at +24h and +48h from now.

    Returns (predicted_24h, predicted_48h, r_squared, uncertainty).
    uncertainty = ±1σ of regression residuals (realistic error range).
    """
    window = min(168, len(df))
    data   = df["rate"].iloc[-window:].reset_index(drop=True)
    if len(data) < 12:
        last = float(data.iloc[-1])
        return last, last, 0.0, 0.0
    X = np.arange(len(data)).reshape(-1, 1)
    y = data.values
    model       = LinearRegression().fit(X, y)
    r2          = float(model.score(X, y))
    n           = len(data)
    pred24      = float(model.predict([[n + 23]])[0])
    pred48      = float(model.predict([[n + 47]])[0])
    residuals   = y - model.predict(X).flatten()
    uncertainty = float(np.std(residuals))
    return round(pred24, 4), round(pred48, 4), round(r2, 4), round(uncertainty, 4)


# -----------------------------------------------------------------------------
# Main analysis
# -----------------------------------------------------------------------------

def analyse(df: pd.DataFrame) -> Indicators | None:
    """
    Run all indicators on the loaded rate DataFrame.
    Returns an Indicators object, or None if data is insufficient.
    """
    if df.empty or len(df) < 20:
        logger.warning("Not enough data to compute indicators (%d rows).", len(df))
        return None

    series       = df["rate"]
    current_rate = float(series.iloc[-1])
    rsi          = compute_rsi(series)
    slope, label = compute_trend(series)
    ma_24h       = round(float(series.iloc[-24:].mean()), 4)
    ma_48h       = round(float(series.iloc[-48:].mean()), 4)
    dynamic_target = round(ma_48h + 0.5, 4)
    bb_upper, bb_lower, bb_pct = compute_bollinger(series)
    pred24, pred48, confidence, uncertainty = forecast_rates(df)
    strength = compute_signal_strength(rsi, label, bb_pct)

    indicators = Indicators(
        current_rate         = round(current_rate, 4),
        rsi_14               = rsi,
        trend_slope          = slope,
        trend_label          = label,
        ma_24h               = ma_24h,
        ma_48h               = ma_48h,
        dynamic_target       = dynamic_target,
        predicted_24h        = pred24,
        predicted_48h        = pred48,
        confidence           = confidence,
        bb_upper             = bb_upper,
        bb_lower             = bb_lower,
        bb_pct               = bb_pct,
        signal_strength      = strength,
        forecast_uncertainty = uncertainty,
    )
    logger.info(
        "Analysis — Rate: %.4f | RSI: %.1f | Trend: %s | BB%%: %.0f%% | "
        "Signal: %d/100 | Pred24h: %.4f (±%.4f)",
        current_rate, rsi, label, bb_pct * 100,
        strength, pred24, uncertainty,
    )
    return indicators


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from src.fetcher import load_rates
    df = load_rates()
    result = analyse(df)
    if result:
        print(result)
