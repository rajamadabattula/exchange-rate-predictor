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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_targets (
                date   TEXT PRIMARY KEY,
                target DOUBLE PRECISION NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
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
    """Return the latest USD/INR rate.
    Primary: Google Sheets (=GOOGLEFINANCE, real-time).
    Fallback 1: Alpha Vantage (25 requests/day).
    Fallback 2: open.er-api.com (daily, no key).
    Fallback 3: Yahoo Finance.
    """
    import requests as _req

    # Primary — Google Sheets with =GOOGLEFINANCE("CURRENCY:USDINR")
    if config.GOOGLE_SERVICE_ACCOUNT_JSON and config.GOOGLE_SPREADSHEET_ID:
        try:
            import json
            import gspread
            from google.oauth2.service_account import Credentials
            from datetime import timedelta

            creds_dict = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
            scopes = ["https://www.googleapis.com/auth/spreadsheets"]
            creds  = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            client = gspread.authorize(creds)
            sheet  = client.open_by_key(config.GOOGLE_SPREADSHEET_ID).sheet1
            value  = sheet.acell("A1").value
            if value:
                rate = round(float(str(value).replace(",", "")), 4)
                # Write fetch timestamp to B1 (UTC + IST)
                now_utc = datetime.now(timezone.utc)
                now_mst = now_utc + timedelta(hours=-7)
                timestamp = (
                    f"Fetched: {now_mst.strftime('%d %b %Y %H:%M')} MST"
                    f"  /  {now_utc.strftime('%d %b %Y %H:%M')} UTC"
                )
                try:
                    sheet.update("B1", [[timestamp]])
                except Exception:
                    pass  # write failure doesn't affect rate
                logger.info("Current rate fetched (Google Sheets): %.4f", rate)
                return rate
        except Exception as exc:
            logger.warning("Google Sheets failed, falling back: %s", exc)

    # Fallback 1 — Alpha Vantage real-time forex rate
    if config.ALPHAVANTAGE_API_KEY and not config.ALPHAVANTAGE_API_KEY.startswith("your_"):
        try:
            url  = (
                "https://www.alphavantage.co/query"
                "?function=CURRENCY_EXCHANGE_RATE"
                "&from_currency=USD&to_currency=INR"
                f"&apikey={config.ALPHAVANTAGE_API_KEY}"
            )
            resp = _req.get(url, timeout=10)
            data = resp.json().get("Realtime Currency Exchange Rate", {})
            rate = data.get("5. Exchange Rate")
            if rate:
                rate = round(float(rate), 4)
                logger.info("Current rate fetched (Alpha Vantage): %.4f", rate)
                return rate
        except Exception as exc:
            logger.warning("Alpha Vantage failed, falling back: %s", exc)

    # Fallback 2 — open.er-api (daily, no key)
    try:
        resp = _req.get("https://open.er-api.com/v6/latest/USD", timeout=8)
        if resp.status_code == 200:
            rate = round(float(resp.json()["rates"]["INR"]), 4)
            logger.info("Current rate fetched (open.er-api fallback): %.4f", rate)
            return rate
    except Exception as exc:
        logger.warning("open.er-api failed: %s", exc)

    # Fallback 3 — Yahoo Finance
    try:
        ticker = yf.Ticker(config.TICKER)
        data   = ticker.history(period="1d", interval="1m")
        if not data.empty:
            rate = round(float(data["Close"].iloc[-1]), 4)
            logger.info("Current rate fetched (yfinance last resort): %.4f", rate)
            return rate
    except Exception as exc:
        logger.error("All rate sources failed: %s", exc)

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
# Weekly target — locked once per week (resets every Monday midnight MST)
# -----------------------------------------------------------------------------

def get_weekly_target(ma_48h: float) -> float:
    """
    Return this week's target rate. Calculated once at the first run of each MST week
    as (48h moving average + 0.20) and stored in the DB.
    Stays fixed for the entire week — resets Monday midnight MST.
    """
    from datetime import timedelta
    now_mst  = datetime.now(timezone.utc) - timedelta(hours=7)
    # Monday of the current MST week (weekday() = 0 for Monday)
    monday   = now_mst - timedelta(days=now_mst.weekday())
    today    = monday.strftime("%Y-%m-%d")   # key = Monday date of this week
    conn  = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT target FROM daily_targets WHERE date = %s", (today,))
        row = cur.fetchone()
        if row:
            return round(row[0], 4)
        # First run today — calculate and store
        target = round(ma_48h + 0.20, 4)
        cur.execute(
            "INSERT INTO daily_targets (date, target) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (today, target)
        )
        conn.commit()
        logger.info("New daily target set for %s: %.4f", today, target)
        return target
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# Manual target — user-set override stored in DB, persists until changed
# -----------------------------------------------------------------------------

def get_manual_target() -> float | None:
    """Return the user's manually set target, or None if not set."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = 'manual_target'")
        row = cur.fetchone()
        return float(row[0]) if row else None
    finally:
        conn.close()


def set_manual_target(target: float | None) -> None:
    """Store (or clear) the manual target in the DB."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        if target is None:
            cur.execute("DELETE FROM settings WHERE key = 'manual_target'")
        else:
            cur.execute(
                "INSERT INTO settings (key, value) VALUES ('manual_target', %s) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                (str(target),)
            )
        conn.commit()
    finally:
        conn.close()


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
