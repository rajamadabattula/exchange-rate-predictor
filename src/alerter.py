"""
alerter.py — Sends Telegram alerts and manages alert state (no duplicate spam).
State is stored in the alert_state PostgreSQL table so it persists across
GitHub Actions runs and cloud restarts.
"""

import logging
import os
from datetime import datetime, timezone

import requests

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from src.db import get_conn

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Chat ID discovery
# -----------------------------------------------------------------------------

def get_chat_id() -> str | None:
    """
    Fetch the chat ID of the first user who messaged the bot.
    Run this once after sending /start or any message to your bot.
    """
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get("result"):
            chat_id = str(data["result"][-1]["message"]["chat"]["id"])
            logger.info("Chat ID found: %s", chat_id)
            return chat_id
        logger.warning("No messages found. Send a message to your bot first.")
        return None
    except Exception as exc:
        logger.error("Failed to fetch chat ID: %s", exc)
        return None


# -----------------------------------------------------------------------------
# Sending
# -----------------------------------------------------------------------------

def send_message(text: str, chat_id: str | None = None) -> bool:
    """Send a Markdown-formatted message via Telegram Bot API."""
    cid = chat_id or config.TELEGRAM_CHAT_ID
    if not cid or cid == "YOUR_CHAT_ID_HERE":
        logger.error("Telegram chat ID not configured.")
        return False
    url     = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": cid, "text": text, "parse_mode": "Markdown"}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info("Telegram alert sent successfully.")
            return True
        logger.error("Telegram API error %d: %s", resp.status_code, resp.text)
        return False
    except Exception as exc:
        logger.error("Failed to send Telegram message: %s", exc)
        return False


# -----------------------------------------------------------------------------
# Alert state — stored in PostgreSQL so it persists across runs
# -----------------------------------------------------------------------------

def _load_state() -> dict:
    """Read the current alert state row from the database."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT last_alert_time, last_signal, last_summary_time "
            "FROM alert_state ORDER BY id ASC LIMIT 1"
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        return {"last_alert_time": None, "last_signal": None, "last_summary_time": None}
    return {
        "last_alert_time":   row[0].isoformat() if row[0] else None,
        "last_signal":       row[1],
        "last_summary_time": row[2].isoformat() if row[2] else None,
    }


def _save_state(state: dict) -> None:
    """Upsert the alert state into the database (always keeps a single row)."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM alert_state ORDER BY id ASC LIMIT 1")
        row = cur.fetchone()
        if row is None:
            cur.execute(
                "INSERT INTO alert_state (last_alert_time, last_signal, last_summary_time) "
                "VALUES (%s, %s, %s)",
                (state["last_alert_time"], state["last_signal"], state["last_summary_time"])
            )
        else:
            cur.execute(
                "UPDATE alert_state SET last_alert_time=%s, last_signal=%s, last_summary_time=%s "
                "WHERE id=%s",
                (state["last_alert_time"], state["last_signal"], state["last_summary_time"], row[0])
            )
        conn.commit()
    finally:
        conn.close()


def should_send_alert(signal: str) -> bool:
    """
    Sends an alert when:
    - Signal just changed to SEND NOW (immediate — don't wait)
    - Every 3 hours regardless of signal (summary update)
    """
    state             = _load_state()
    last_signal       = state.get("last_signal")
    last_summary_time = state.get("last_summary_time")
    now               = datetime.now(timezone.utc)

    if signal == "SEND NOW" and last_signal != "SEND NOW":
        return True

    if last_summary_time is None:
        return True
    last_dt = datetime.fromisoformat(last_summary_time)
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    elapsed = (now - last_dt).total_seconds() / 3600
    return elapsed >= config.ALERT_INTERVAL_HOURS


def record_alert(signal: str) -> None:
    """Update state after sending an alert."""
    now = datetime.now(timezone.utc).isoformat()
    _save_state({
        "last_alert_time":   now,
        "last_summary_time": now,
        "last_signal":       signal,
    })


# -----------------------------------------------------------------------------
# CLI helper — run once to auto-configure chat ID
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Fetching your Telegram Chat ID...")
    cid = get_chat_id()
    if cid:
        print(f"\nYour Chat ID is: {cid}")
        print(f'Add this to .env:  TELEGRAM_CHAT_ID="{cid}"')
    else:
        print("Could not find Chat ID. Make sure you have sent a message to your bot first.")
