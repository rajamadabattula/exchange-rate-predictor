"""
fetcher.py — Fetches USD/INR exchange rates from Yahoo Finance and stores them in PostgreSQL.
"""

import logging
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from src.db import get_conn

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------

def init_db() -> None:
    """Create tables if they don't exist."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS rates (
                id        SERIAL PRIMARY KEY,
                timestamp TIMESTAMP NOT NULL UNIQUE,
                rate      DOUBLE PRECISION NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id             SERIAL PRIMARY KEY,
                created_at     TIMESTAMP NOT NULL,
                forecast_time  TIMESTAMP NOT NULL,
                predicted_rate DOUBLE PRECISION NOT NULL,
                signal         TEXT,
                dynamic_target DOUBLE PRECISION,
                UNIQUE(created_at, forecast_time)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS alert_state (
                id                SERIAL PRIMARY KEY,
                last_alert_time   TIMESTAMP,
                last_signal       TEXT,
                last_summary_time TIMESTAMP
            )
        """)
        conn.commit()
        logger.info("Database initialised.")
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# Fetching
# -----------------------------------------------------------------------------

def fetch_current_rate() -> float | None:
    """Return the latest USD/INR rate from Yahoo Finance."""
    try:
        ticker = yf.Ticker(config.TICKER)
        data   = ticker.history(period="1d", interval="1m")
        if data.empty:
            logger.warning("Empty response from Yahoo Finance for current rate.")
            return None
        rate = float(data["Close"].iloc[-1])
        logger.info("Current rate fetched: %.4f", rate)
        return rate
    except Exception as exc:
        logger.error("Failed to fetch current rate: %s", exc)
        return None


def fetch_historical_rates(days: int = config.HISTORY_DAYS) -> pd.DataFrame:
    """
    Return a DataFrame with columns [timestamp, rate] for the last `days` days.
    Timestamps are UTC, hourly intervals.
    """
    try:
        ticker = yf.Ticker(config.TICKER)
        data   = ticker.history(period=f"{days}d", interval="1h")
        if data.empty:
            logger.warning("Empty historical data from Yahoo Finance.")
            return pd.DataFrame(columns=["timestamp", "rate"])
        df = data[["Close"]].reset_index()
        df.columns = ["timestamp", "rate"]
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_localize(None)
        df["rate"] = df["rate"].astype(float).round(4)
        logger.info("Fetched %d historical rows (%d days).", len(df), days)
        return df
    except Exception as exc:
        logger.error("Failed to fetch historical data: %s", exc)
        return pd.DataFrame(columns=["timestamp", "rate"])


# -----------------------------------------------------------------------------
# Storage
# -----------------------------------------------------------------------------

def save_rates(df: pd.DataFrame) -> int:
    """
    Insert rows from df into the rates table.
    Skips duplicates (ON CONFLICT DO NOTHING).
    Returns the number of new rows inserted.
    """
    if df.empty:
        return 0
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM rates")
        before = cur.fetchone()[0]
        cur.executemany(
            "INSERT INTO rates (timestamp, rate) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            df[["timestamp", "rate"]].values.tolist()
        )
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM rates")
        after = cur.fetchone()[0]
    finally:
        conn.close()
    inserted = after - before
    logger.info("Saved %d new rate rows to database.", inserted)
    return inserted


def save_current_rate(rate: float) -> None:
    """Insert a single current rate with the current UTC timestamp."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO rates (timestamp, rate) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (now, rate)
        )
        conn.commit()
    finally:
        conn.close()
    logger.debug("Saved current rate %.4f at %s", rate, now)


def load_rates(days: int = config.HISTORY_DAYS) -> pd.DataFrame:
    """Load the last `days` days of rates from PostgreSQL, sorted ascending."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT timestamp, rate FROM rates "
            "WHERE timestamp >= NOW() - (%s || ' days')::INTERVAL "
            "ORDER BY timestamp ASC",
            (str(days),),
        )
        rows = cur.fetchall()
        cols = [desc[0] for desc in cur.description]
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


# -----------------------------------------------------------------------------
# Bootstrap
# -----------------------------------------------------------------------------

def bootstrap() -> None:
    """
    One-time setup: initialise the database and backfill historical data.
    Safe to call every run — skips rows that already exist.
    """
    init_db()

    # Skip expensive backfill if we already have plenty of data
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM rates")
        count = cur.fetchone()[0]
    finally:
        conn.close()

    if count >= 100:
        logger.info("Database already has %d rows — skipping backfill.", count)
        return

    logger.info("Backfilling %d days of historical data...", config.HISTORY_DAYS)
    df = fetch_historical_rates(config.HISTORY_DAYS)
    inserted = save_rates(df)
    logger.info("Bootstrap complete. %d new rows inserted.", inserted)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bootstrap()
    rate = fetch_current_rate()
    print(f"Current USD/INR rate: {rate}")
