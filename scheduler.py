"""
scheduler.py — Main entry point. Runs the fetch → predict → decide → alert loop.

Usage:
    python scheduler.py           # Start the scheduler (runs until stopped)
    python scheduler.py --setup   # Discover and print your Telegram Chat ID
    python scheduler.py --now     # Run one check immediately and exit
"""

import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

import config
from src.fetcher   import bootstrap, fetch_current_rate, save_current_rate, load_rates
from src.predictor import analyse
from src.decision  import decide, format_message
from src.alerter   import send_message, should_send_alert, record_alert, get_chat_id
from src.accuracy  import save_prediction


# -----------------------------------------------------------------------------
# Logging setup
# -----------------------------------------------------------------------------

def setup_logging() -> None:
    Path("logs").mkdir(exist_ok=True)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    file_handler = RotatingFileHandler(config.LOG_PATH, maxBytes=2_000_000, backupCount=3)
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])


# -----------------------------------------------------------------------------
# Core job
# -----------------------------------------------------------------------------

def run_check() -> None:
    """One full fetch → predict → decide → (maybe) alert cycle."""
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Running scheduled check at %s UTC", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))

    # 1. Fetch and store current rate
    rate = fetch_current_rate()
    if rate is None:
        logger.warning("Skipping this cycle — could not fetch current rate.")
        return
    save_current_rate(rate)

    # 2. Load history and compute indicators
    df = load_rates()
    indicators = analyse(df)
    if indicators is None:
        logger.warning("Skipping this cycle — insufficient data for analysis.")
        return

    # 3. Make a decision
    decision = decide(indicators)
    logger.info("Signal: %s | %s", decision.signal.value, decision.summary)

    # 4. Save prediction for future accuracy scoring
    save_prediction(indicators, decision.signal.value)

    # 5. Send alert if conditions are met
    if should_send_alert(decision.signal.value):
        # is_summary=True when signal is NOT SEND NOW (i.e. it's a periodic update)
        is_summary = decision.signal.value != "SEND NOW"
        message = format_message(decision, indicators, is_summary=is_summary)
        sent    = send_message(message)
        if sent:
            record_alert(decision.signal.value)
    else:
        logger.info("Alert suppressed — within quiet window.")


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------

def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    # Handle CLI flags
    if "--setup" in sys.argv:
        print("\nFetching your Telegram Chat ID...\n")
        cid = get_chat_id()
        if cid:
            print(f"Chat ID found: {cid}")
            print(f'\nAdd this line to config.py:\n  TELEGRAM_CHAT_ID = "{cid}"\n')
        else:
            print("No chat ID found. Send any message to your Telegram bot first, then run this again.")
        return

    if "--now" in sys.argv:
        logger.info("Running a single check (--now mode).")
        bootstrap()
        run_check()
        return

    # Normal mode: bootstrap + start scheduler
    logger.info("Starting Exchange Rate Predictor...")
    bootstrap()
    run_check()  # Run once immediately on start

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        run_check,
        trigger="interval",
        minutes=config.FETCH_INTERVAL_MINUTES,
        id="rate_check",
        name="USD/INR Rate Check",
    )
    logger.info(
        "Scheduler started. Checking every %d minutes. Press Ctrl+C to stop.",
        config.FETCH_INTERVAL_MINUTES,
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped by user.")


if __name__ == "__main__":
    main()
