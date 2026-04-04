"""
predictor.py — Computes RSI, Bollinger Bands, trend, signal strength,
               and a 48-hour forecast using the best of 3 models:
               1. Linear Regression (baseline)
               2. Gradient Boosting with feature engineering (GBM)
               3. Exponential Smoothing (Holt-Winters)

Models are compared on a 24h holdout every run. The winner is used
for the actual forecast. All model predictions are logged for comparison.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import GradientBoostingRegressor

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
    dynamic_target:       float          # 85th percentile of last 72h rates
    predicted_24h:        float          # Predicted rate 24 hours from now
    predicted_48h:        float          # Predicted rate 48 hours from now
    confidence:           float          # Reserved (model score)
    bb_upper:             float = 0.0    # Bollinger upper band (20-period, 2σ)
    bb_lower:             float = 0.0    # Bollinger lower band
    bb_pct:               float = 0.5    # 0 = at lower band, 1 = at upper, >1 = above
    signal_strength:      int   = 0      # 0–100: how many indicators agree on a drop
    forecast_uncertainty: float = 0.0   # ±1σ of model residuals
    model_used:           str   = ""     # which model won: "GBM" | "Linear" | "ExpSmooth"
    model_scores:         dict  = None   # {model: holdout_error} for all 3 models

    def __post_init__(self):
        if self.model_scores is None:
            self.model_scores = {}


# -----------------------------------------------------------------------------
# Technical indicators
# -----------------------------------------------------------------------------

def compute_rsi(series: pd.Series, period: int = 14) -> float:
    """Compute RSI for the last `period` data points."""
    if len(series) < period + 1:
        return 50.0
    delta    = series.diff().dropna()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.rolling(window=period).mean().iloc[-1]
    avg_loss = loss.rolling(window=period).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs  = avg_gain / avg_loss
    return round(float(100 - (100 / (1 + rs))), 2)


def compute_trend(series: pd.Series, window: int = 24) -> tuple[float, str]:
    """Fit linear regression over last `window` points. Returns (slope, label)."""
    data = series.iloc[-window:].reset_index(drop=True)
    if len(data) < 4:
        return 0.0, "sideways"
    X     = np.arange(len(data)).reshape(-1, 1)
    slope = float(LinearRegression().fit(X, data.values).coef_[0])
    label = "rising" if slope > 0.005 else "falling" if slope < -0.005 else "sideways"
    return round(slope, 6), label


def compute_bollinger(series: pd.Series, window: int = 20) -> tuple[float, float, float]:
    """Bollinger Bands (20-period, 2σ). Returns (upper, lower, pct_b)."""
    if len(series) < window:
        mid = float(series.mean())
        return round(mid, 4), round(mid, 4), 0.5
    recent = series.iloc[-window:]
    mid    = float(recent.mean())
    std    = float(recent.std())
    upper  = round(mid + 2 * std, 4)
    lower  = round(mid - 2 * std, 4)
    band   = upper - lower
    pct    = round((float(series.iloc[-1]) - lower) / band, 4) if band > 0 else 0.5
    return upper, lower, pct


def compute_signal_strength(rsi: float, trend: str, bb_pct: float) -> int:
    """Score 0–100: how many indicators agree the rate is at a peak."""
    score = 0
    if rsi >= 70:              score += 35
    elif rsi >= 60:            score += 15
    if bb_pct >= 1.0:          score += 35
    elif bb_pct >= 0.8:        score += 15
    if trend == "falling":     score += 30
    elif trend == "sideways":  score += 15
    return min(score, 100)


# -----------------------------------------------------------------------------
# Feature engineering
# -----------------------------------------------------------------------------

def _build_features(series: pd.Series) -> pd.DataFrame:
    """
    Build ML feature matrix from rate series.
    All features use past data only (shift ≥ 1) to avoid leakage.
    """
    s = series.reset_index(drop=True)
    df = pd.DataFrame()

    n = len(s)
    # Only include lags where we'll still have 50+ training samples after dropna
    for lag in [1, 2, 3, 6, 12, 24, 48, 168]:
        if n > lag + 50:
            df[f"lag_{lag}h"] = s.shift(lag)

    # Rolling statistics — trend and volatility
    df["roll_mean_6h"]  = s.shift(1).rolling(6,  min_periods=3).mean()
    df["roll_mean_24h"] = s.shift(1).rolling(24, min_periods=12).mean()
    df["roll_std_24h"]  = s.shift(1).rolling(24, min_periods=12).std()
    df["roll_std_6h"]   = s.shift(1).rolling(6,  min_periods=3).std()

    # Momentum — rate of change
    df["roc_1h"]  = s.diff(1)
    df["roc_6h"]  = s.diff(6)
    df["roc_24h"] = s.diff(24)

    return df


# -----------------------------------------------------------------------------
# Individual model forecasters
# -----------------------------------------------------------------------------

def _linear_forecast(series: pd.Series, hours: int) -> tuple[float, float]:
    """Linear regression on last 168h. Returns (prediction, uncertainty)."""
    data = series.iloc[-168:].reset_index(drop=True) if len(series) >= 168 else series.reset_index(drop=True)
    if len(data) < 12:
        return round(float(series.iloc[-1]), 4), 0.0
    X         = np.arange(len(data)).reshape(-1, 1)
    y         = data.values
    model     = LinearRegression().fit(X, y)
    pred      = float(model.predict([[len(data) + hours - 1]])[0])
    unc       = float(np.std(y - model.predict(X).flatten()))
    return round(pred, 4), round(unc, 4)


def _gbm_forecast(series: pd.Series, hours: int) -> tuple[float, float]:
    """
    Gradient Boosting with lag/rolling features.
    Trains a direct model to predict `hours` ahead.
    Returns (prediction, uncertainty).
    """
    features = _build_features(series)
    features["target"] = series.reset_index(drop=True).shift(-hours)
    features = features.dropna()

    if len(features) < 50:
        return round(float(series.iloc[-1]), 4), 0.0

    X = features.drop(columns=["target"]).values
    y = features["target"].values

    model = GradientBoostingRegressor(
        n_estimators=100, max_depth=4,
        learning_rate=0.1, subsample=0.8,
        random_state=42, n_iter_no_change=10,
    )
    model.fit(X, y)

    residuals = y - model.predict(X)
    unc       = float(np.std(residuals))

    # Predict from latest known features (fill any NaN from short lags)
    latest = _build_features(series).iloc[[-1]].ffill().fillna(0)
    pred   = float(model.predict(latest.values)[0])

    return round(pred, 4), round(unc, 4)


def _ppp_forecast(series: pd.Series, hours: int) -> tuple[float, float]:
    """
    Purchasing Power Parity (relative PPP) forecast.
    Projects the expected rate drift from the inflation differential between
    India and the US.  Higher Indian inflation → INR depreciates at that rate.
    """
    current = float(series.iloc[-1])
    annual_depreciation = (config.INDIA_INFLATION_RATE - config.US_INFLATION_RATE) / 100
    pred = current * (1 + annual_depreciation) ** (hours / 8760)
    unc  = float(series.iloc[-24:].std()) if len(series) >= 24 else 0.0
    return round(pred, 4), round(unc, 4)


def _relative_strength_forecast(series: pd.Series, hours: int) -> tuple[float, float]:
    """
    Relative Economic Strength / Covered Interest Rate Parity forecast.
    The higher-yield currency (INR) depreciates at the interest-rate differential
    to prevent risk-free arbitrage.
    """
    current = float(series.iloc[-1])
    rate_differential = (config.INDIA_INTEREST_RATE - config.US_INTEREST_RATE) / 100
    pred = current * (1 + rate_differential) ** (hours / 8760)
    unc  = float(series.iloc[-24:].std()) if len(series) >= 24 else 0.0
    return round(pred, 4), round(unc, 4)


def _arima_forecast(series: pd.Series, hours: int) -> tuple[float, float]:
    """
    ARIMA(1,1,1) econometric model.
    Differenced (d=1) for non-stationarity, with AR and MA terms.
    """
    try:
        from statsmodels.tsa.arima.model import ARIMA
        data = series.iloc[-168:] if len(series) >= 168 else series
        if len(data) < 24:
            return round(float(series.iloc[-1]), 4), 0.0
        model = ARIMA(data.values, order=(1, 1, 1)).fit()
        pred  = float(model.forecast(steps=hours)[-1])
        unc   = float(np.std(model.resid))
        return round(pred, 4), round(unc, 4)
    except Exception as exc:
        logger.warning("ARIMA failed: %s", exc)
        return round(float(series.iloc[-1]), 4), 0.0


def _exp_smoothing_forecast(series: pd.Series, hours: int) -> tuple[float, float]:
    """
    Holt-Winters Exponential Smoothing with additive trend and damping.
    Returns (prediction, uncertainty).
    """
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        data  = series.iloc[-168:] if len(series) >= 168 else series
        model = ExponentialSmoothing(
            data.values,
            trend="add",
            damped_trend=True,
        ).fit(optimized=True)
        pred  = float(model.forecast(hours)[-1])
        unc   = float(np.std(data.values - model.fittedvalues))
        return round(pred, 4), round(unc, 4)
    except Exception as exc:
        logger.warning("ExpSmoothing failed: %s", exc)
        return round(float(series.iloc[-1]), 4), 0.0


# -----------------------------------------------------------------------------
# Model comparison + selection
# -----------------------------------------------------------------------------

def _compare_models(series: pd.Series) -> dict[str, float]:
    """
    Quick holdout: train on all but last 24h, predict 24h ahead, measure error.
    Returns {model_name: absolute_error}.
    """
    if len(series) < 100:
        return {}

    holdout   = 24
    train     = series.iloc[:-holdout]
    actual_24 = float(series.iloc[-holdout])

    errors: dict[str, float] = {}

    for name, fn in [
        ("Linear",      _linear_forecast),
        ("GBM",         _gbm_forecast),
        ("ExpSmooth",   _exp_smoothing_forecast),
        ("PPP",         _ppp_forecast),
        ("RelStrength", _relative_strength_forecast),
        ("ARIMA",       _arima_forecast),
    ]:
        try:
            pred, _ = fn(train, 24)
            errors[name] = round(abs(pred - actual_24), 4)
        except Exception:
            errors[name] = 999.0

    return errors


def forecast_rates(df: pd.DataFrame) -> tuple[float, float, float, float, str, dict]:
    """
    Run all 3 models, compare on 24h holdout, use winner for final forecast.
    Returns (predicted_24h, predicted_48h, confidence, uncertainty, model_name).
    """
    series = df["rate"]

    if len(series) < 20:
        last = float(series.iloc[-1])
        return last, last, 0.0, 0.0, "Linear", {}

    # ── Compare all models on holdout ────────────────────────────────────────
    errors = _compare_models(series)
    if errors:
        winner = min(errors, key=lambda k: errors[k])
        logger.info(
            "MODEL COMPARISON (24h holdout error) → Linear: %.4f | GBM: %.4f | ExpSmooth: %.4f | "
            "PPP: %.4f | RelStrength: %.4f | ARIMA: %.4f | Winner: %s",
            errors.get("Linear", 999), errors.get("GBM", 999), errors.get("ExpSmooth", 999),
            errors.get("PPP", 999), errors.get("RelStrength", 999), errors.get("ARIMA", 999), winner,
        )
    else:
        winner = "GBM"

    # ── Forecast with winner on full series ──────────────────────────────────
    _model_fn_map = {
        "Linear":      _linear_forecast,
        "GBM":         _gbm_forecast,
        "ExpSmooth":   _exp_smoothing_forecast,
        "PPP":         _ppp_forecast,
        "RelStrength": _relative_strength_forecast,
        "ARIMA":       _arima_forecast,
    }
    fn = _model_fn_map.get(winner, _linear_forecast)
    pred24, unc24 = fn(series, 24)
    pred48, unc48 = fn(series, 48)

    # Also log all 6 predictions for full visibility
    try:
        forecasts = {name: _model_fn_map[name](series, 24)[0] for name in _model_fn_map}
        logger.info(
            "ALL MODEL FORECASTS (24h) → Linear: %.4f | GBM: %.4f | ExpSmooth: %.4f | "
            "PPP: %.4f | RelStrength: %.4f | ARIMA: %.4f | Using: %s=%.4f",
            forecasts["Linear"], forecasts["GBM"], forecasts["ExpSmooth"],
            forecasts["PPP"], forecasts["RelStrength"], forecasts["ARIMA"],
            winner, pred24,
        )
    except Exception:
        pass

    uncertainty = round((unc24 + unc48) / 2, 4)
    return pred24, pred48, 0.0, uncertainty, winner, errors


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
    # Rolling percentile target — self-adjusting, no weekly lock
    window         = getattr(config, "TARGET_WINDOW_HOURS", 72)
    percentile     = getattr(config, "TARGET_PERCENTILE", 85)
    series_window  = series.iloc[-window:] if len(series) >= window else series
    dynamic_target = round(float(np.percentile(series_window, percentile)), 4)
    bb_upper, bb_lower, bb_pct = compute_bollinger(series)
    pred24, pred48, confidence, uncertainty, model_used, model_scores = forecast_rates(df)
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
        model_used           = model_used,
        model_scores         = model_scores,
    )
    logger.info(
        "Analysis — Rate: %.4f | RSI: %.1f | Trend: %s | BB%%: %.0f%% | "
        "Signal: %d/100 | Model: %s | Pred24h: %.4f (±%.4f)",
        current_rate, rsi, label, bb_pct * 100,
        strength, model_used, pred24, uncertainty,
    )
    return indicators


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from src.fetcher import load_rates
    df = load_rates()
    result = analyse(df)
    if result:
        print(f"\nModel used: {result.model_used}")
        print(f"Forecast 24h: {result.predicted_24h} (±{result.forecast_uncertainty})")
        print(f"Forecast 48h: {result.predicted_48h}")
