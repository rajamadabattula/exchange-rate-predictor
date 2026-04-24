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
FETCH_INTERVAL_MINUTES  = 1     # Fetch new rate every 1 minute
ALERT_INTERVAL_HOURS    = 1     # Send summary alert every 1 hour

# --- Database (loaded from .env) ---
DATABASE_URL          = os.getenv("DATABASE_URL", "")

# --- Alpha Vantage (loaded from .env) ---
ALPHAVANTAGE_API_KEY  = os.getenv("ALPHAVANTAGE_API_KEY", "")

# --- Google Sheets (loaded from .env) ---
GOOGLE_SPREADSHEET_ID          = os.getenv("GOOGLE_SPREADSHEET_ID", "")
GOOGLE_SERVICE_ACCOUNT_JSON    = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")

# --- Data ---
HISTORY_DAYS      = 90          # Days of historical data to use
FORECAST_HOURS    = 48          # Hours ahead to forecast
TICKER            = "USDINR=X"  # Yahoo Finance USD/INR ticker
LOG_PATH          = "logs/exchange.log"

# --- Signal Thresholds ---
RSI_OVERBOUGHT        = 70     # RSI above this = likely to drop
RSI_OVERSOLD          = 30     # RSI below this = likely to rise
SIGNAL_STRENGTH_GATE  = 35     # Min signal strength to fire SEND NOW (0–100)
                                # 35 = at least 1 indicator agrees; 50 = 2 indicators

# --- Target Rate ---
# Manual target can be set from the dashboard (stored in DB, overrides auto).
# If no manual target is set, the auto target is used:
TARGET_PERCENTILE     = 75     # 75th percentile of the last 72h of rates
TARGET_WINDOW_HOURS   = 72     # Rolling window for percentile calculation

# --- Economic Parameters (update a few times per year as conditions change) ---
US_INTEREST_RATE     = 4.33    # Fed funds effective rate (%)
INDIA_INTEREST_RATE  = 6.25    # RBI repo rate (%)
US_INFLATION_RATE    = 2.8     # US annual CPI (%)
INDIA_INFLATION_RATE = 4.9     # India annual CPI (%)
