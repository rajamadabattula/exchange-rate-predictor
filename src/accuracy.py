"""
accuracy.py — Saves predictions to DB and computes historical accuracy metrics.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.predictor import Indicators
from src.db import get_conn

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Save predictions
# -----------------------------------------------------------------------------

def save_prediction(ind: Indicators, signal: str) -> None:
    """
    Store the current 24h and 48h predictions so we can score them later.
    Called every scheduler run.
    """
    now     = datetime.now(timezone.utc).replace(tzinfo=None)
    t24     = now + timedelta(hours=24)
    t48     = now + timedelta(hours=48)

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.executemany(
            """INSERT INTO predictions
               (created_at, forecast_time, predicted_rate, signal, dynamic_target)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (created_at, forecast_time) DO NOTHING""",
            [
                (now, t24, ind.predicted_24h, signal, ind.dynamic_target),
                (now, t48, ind.predicted_48h, signal, ind.dynamic_target),
            ]
        )
        conn.commit()
    finally:
        conn.close()
    logger.debug("Saved predictions: 24h=%s → %.4f, 48h=%s → %.4f",
                 t24, ind.predicted_24h, t48, ind.predicted_48h)


# -----------------------------------------------------------------------------
# Compute accuracy
# -----------------------------------------------------------------------------

@dataclass
class AccuracyReport:
    total_scored:       int     # predictions where forecast_time has passed
    mae_24h:            float   # mean absolute error for 24h forecasts
    mae_48h:            float   # mean absolute error for 48h forecasts
    within_half_24h:    float   # % of 24h predictions within ±0.5 of actual
    within_half_48h:    float   # % of 48h predictions within ±0.5 of actual
    signal_correct:     int     # SEND NOW was right (rate dropped within 24h)
    signal_wrong:       int     # SEND NOW was wrong (rate rose >0.3 within 24h)
    signal_accuracy:    float   # % correct out of all scored SEND NOW signals
    df_chart:           pd.DataFrame  # predicted vs actual for chart


def compute_accuracy() -> AccuracyReport | None:
    """
    Score all past predictions by comparing to actual rates.
    Only scores predictions where forecast_time is at least 1 hour in the past.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT p.created_at, p.forecast_time, p.predicted_rate,
                   p.signal, p.dynamic_target, r.rate AS actual_rate
            FROM predictions p
            LEFT JOIN LATERAL (
                SELECT rate FROM rates
                WHERE timestamp <= p.forecast_time
                ORDER BY timestamp DESC
                LIMIT 1
            ) r ON true
            WHERE p.forecast_time <= NOW()
            ORDER BY p.forecast_time ASC
        """)
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
    finally:
        conn.close()
    preds = pd.DataFrame(rows, columns=cols)

    if preds.empty or preds["actual_rate"].isna().all():
        return None

    preds = preds.dropna(subset=["actual_rate"])
    if len(preds) < 3:
        return None

    preds["created_at"]    = pd.to_datetime(preds["created_at"],    utc=True)
    preds["forecast_time"] = pd.to_datetime(preds["forecast_time"], utc=True)
    preds["error"]         = (preds["predicted_rate"] - preds["actual_rate"]).abs()

    preds["horizon"] = (preds["forecast_time"] - preds["created_at"]).dt.total_seconds() / 3600
    p24 = preds[preds["horizon"].between(20, 28)]
    p48 = preds[preds["horizon"].between(44, 52)]

    mae_24h    = round(p24["error"].mean(), 4) if not p24.empty else 0.0
    mae_48h    = round(p48["error"].mean(), 4) if not p48.empty else 0.0
    within_24h = round((p24["error"] <= 0.5).mean() * 100, 1) if not p24.empty else 0.0
    within_48h = round((p48["error"] <= 0.5).mean() * 100, 1) if not p48.empty else 0.0

    send_now = p24[p24["signal"] == "SEND NOW"].copy()
    signal_correct = signal_wrong = 0
    if not send_now.empty:
        correct_mask   = send_now["actual_rate"] < send_now["predicted_rate"]
        signal_correct = int(correct_mask.sum())
        signal_wrong   = int((~correct_mask).sum())

    total_send_now  = signal_correct + signal_wrong
    signal_accuracy = round((signal_correct / total_send_now) * 100, 1) if total_send_now > 0 else 0.0

    chart = p24.tail(50)[["forecast_time", "predicted_rate", "actual_rate"]].copy()
    chart = chart.rename(columns={
        "forecast_time":  "Time",
        "predicted_rate": "Predicted",
        "actual_rate":    "Actual",
    })

    return AccuracyReport(
        total_scored    = len(preds),
        mae_24h         = mae_24h,
        mae_48h         = mae_48h,
        within_half_24h = within_24h,
        within_half_48h = within_48h,
        signal_correct  = signal_correct,
        signal_wrong    = signal_wrong,
        signal_accuracy = signal_accuracy,
        df_chart        = chart,
    )
