# =============================================================================
# Exchange Rate Predictor — Configuration
# =============================================================================
# Credentials are loaded from a .env file — never hardcode them here.
# Copy .env.example to .env and fill in your values.

from dotenv import load_dotenv
import os

load_dotenv()

# --- Telegram (loaded from .env) ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# --- Claude AI (loaded from .env) ---
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL       = "claude-haiku-4-5-20251001"   # fast + cheap for Q&A

# --- Scheduler ---
FETCH_INTERVAL_MINUTES  = 15    # Fetch new rate every 15 minutes
ALERT_INTERVAL_HOURS    = 3     # Send summary alert every 3 hours

# --- Database (loaded from .env) ---
DATABASE_URL      = os.getenv("DATABASE_URL", "")

# --- Data ---
HISTORY_DAYS      = 90          # Days of historical data to use
FORECAST_HOURS    = 48          # Hours ahead to forecast
TICKER            = "USDINR=X"  # Yahoo Finance USD/INR ticker
LOG_PATH          = "logs/exchange.log"

# --- Signal Thresholds ---
RSI_OVERBOUGHT    = 70          # RSI above this = likely to drop
RSI_OVERSOLD      = 30          # RSI below this = likely to rise
