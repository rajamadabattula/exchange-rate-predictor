# USD → INR Rate Predictor

![Rate Check](https://github.com/rajamadabattula/exchange-rate-predictor/actions/workflows/scheduler.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.14-blue)

A personal finance tool that monitors the USD/INR exchange rate, predicts the best time to send money internationally, and delivers plain-English alerts via Telegram — powered by technical indicators, a multi-model forecaster, and an optional LLM-powered advisor.

---

🔴 **[Live Dashboard → exchange-rate-predictor.streamlit.app](https://exchange-rate-predictor.streamlit.app/)**

---

## The Story Behind This Project

I came from India to the US for my Master's degree. Like most international students, I carry debt back home — and every month, I face the same stressful question: *when do I send money?*

The exchange rate is unpredictable. Some days it's good, some days it isn't. And the apps we use for international transfers lock in the rate the moment you hit send — there's no going back.

A week before building this, I sent money at a rate that was ₹3 per dollar lower than it became just days later. That's thousands of rupees lost in a single transfer. For someone managing student debt across two currencies, that's not a rounding error — it genuinely hurts.

I had the data skills. I had the tools. So instead of guessing, I built this.

This dashboard watches the USD/INR rate around the clock, predicts where it's heading, and tells you in plain English — *send now* or *wait*. No charts to interpret. No finance degree required. Just a clear signal when the time is right.

Built for myself. Useful for every international student sending money home.

---

## What Makes This Different

Most exchange rate tools show you a chart and leave you to figure it out. This one tells you what to do.

- Fetches **live USD/INR data** from Google Finance (via Google Sheets `=GOOGLEFINANCE`) — real-time, every minute
- Computes a **rolling target** — 75th percentile of the last 72 hours — so it's always calibrated to recent price action, not a stale weekly lock
- **Six forecast models** compete every run — Linear Regression, Gradient Boosting, Exponential Smoothing, ARIMA, Purchasing Power Parity, and Relative Economic Strength — the most accurate one wins
- Requires **≥ 2 technical indicators to agree** before firing SEND NOW — no false signals from a single condition
- Sends a **Telegram alert** the moment it's a good time to send — written as a personal advisor, not a data dump
- Tracks its own **prediction accuracy** over time so you know how much to trust it
- Runs a **Streamlit dashboard** that auto-refreshes every minute with interactive charts and a 3-button Q&A advisor

---

## System Architecture

```
Google Finance (via Google Sheets =GOOGLEFINANCE)  ← Primary, real-time
Alpha Vantage API                                   ← Fallback 1 (25 req/day)
open.er-api.com                                     ← Fallback 2 (daily, no key)
Yahoo Finance (yfinance)                            ← Last resort
        │
        ▼
  fetcher.py          ← Fetches live rate every hour (GitHub Actions) /
        │               every minute (dashboard auto-refresh)
        ▼
  PostgreSQL          ← Supabase cloud database — stores rates,
  (Supabase)            predictions, alert state, weekly targets
        │
        ▼
  predictor.py        ← RSI (14), Bollinger Bands (20-period),
        │               trend slope, Signal Strength (0–100),
        │               multi-model forecast: Linear / GBM / ExpSmooth / ARIMA / PPP / RelStrength
        ▼
  decision.py         ← SEND NOW / MONITOR / WAIT
                        (requires rate ≥ target AND signal strength ≥ 50)
        │
    ┌───┴────────────────┐
    ▼                    ▼
alerter.py          dashboard.py
(Telegram Bot)      (Streamlit UI — Streamlit Community Cloud)
    │                    │
    ▼                    ▼
Your phone          Browser (any device)

accuracy.py         ← Scores past predictions against actual rates
advisor.py          ← Q&A: send in 1hr / tomorrow / best time
```

---

## Technical Highlights

- **Real-time Google Finance rate** — Google Sheets `=GOOGLEFINANCE("CURRENCY:USDINR")` gives the same rate as Google Search, updated every minute
- **6-model forecasting with auto-selection** — Linear Regression, Gradient Boosting, Exponential Smoothing, ARIMA, Purchasing Power Parity, and Relative Economic Strength are compared on a 24h holdout every run; the winner is used automatically
- **Signal Strength gate** — SEND NOW only fires when ≥ 2 of: RSI overbought, Bollinger Band extended, trend falling
- **Rolling 72h target** — 75th percentile of the last 72 hours, updates every run, always calibrated to recent price action
- **Cloud-native, zero maintenance** — GitHub Actions runs hourly; Streamlit Community Cloud hosts the dashboard; Supabase stores all data
- **Closed-loop accuracy tracking** — predictions are stored and scored against real outcomes
- **Alert deduplication** — fires immediately on signal change + 3-hour periodic summaries; no spam
- **Modular design** — each component is independently testable and replaceable

---

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3.14 |
| Primary data source | Google Sheets (`=GOOGLEFINANCE`) |
| Fallback sources | Alpha Vantage → open.er-api.com → Yahoo Finance (yfinance) |
| Storage | PostgreSQL on Supabase |
| Forecast models | `scikit-learn` GradientBoosting + LinearRegression, `statsmodels` ExponentialSmoothing + ARIMA, PPP, Relative Econ Strength |
| Technical indicators | RSI (14), Bollinger Bands (20-period, 2σ), linear trend slope |
| Scheduling | GitHub Actions (hourly) + Streamlit auto-refresh (every minute) |
| Alerts | `python-telegram-bot` |
| Dashboard | `Streamlit` + `Plotly` (Streamlit Community Cloud) |
| AI Advisor _(optional)_ | Anthropic Claude API (`claude-haiku`) |

---

## How the Signal Works

### Target Rate
Two modes — whichever is active is shown in the dashboard header:

**Manual (recommended):** Set your own target from the dashboard. Saved to the database, persists until you change it. Overrides everything.

**Auto (fallback):**
```
Target = 85th percentile of the last 72 hours of rates
```
"Send when the rate is in the top 15% of the last 3 days." Updates every run, no weekly lock.

### Signal Strength (0–100)
Three indicators vote. Each contributes points toward a 0–100 score:

| Indicator | Condition | Points |
|---|---|---|
| RSI (14) | ≥ 70 (overbought) | +35 |
| RSI (14) | 60–70 | +15 |
| Bollinger Band | Rate above upper band (2σ) | +35 |
| Bollinger Band | Rate at 80–100% of band | +15 |
| Trend | Falling | +30 |
| Trend | Sideways | +15 |

**SEND NOW requires: rate ≥ target AND signal strength ≥ 35 (≥ 1 indicator agrees)**

### Decision Rules
| Condition | Signal |
|---|---|
| Rate ≥ target AND signal strength ≥ 35 | **SEND NOW** |
| Rate ≥ target AND signal strength < 35 | **MONITOR** (rate is good but may still rise) |
| Rate within 0.50 of target | **MONITOR** |
| Rate below target | **WAIT** |

### Forecast Models
Every run, all six models are trained and evaluated on the last 24 hours of actual data:

| Model | Approach |
|---|---|
| **Gradient Boosting** | Lag features (1h, 2h, 3h, 6h, 12h, 24h, 48h), rolling mean/std, momentum |
| **Exponential Smoothing** | Holt-Winters with additive trend and damping |
| **Linear Regression** | Trend extrapolation on last 7 days |
| **ARIMA(1,1,1)** | Differenced autoregressive econometric model |
| **Purchasing Power Parity** | Inflation differential (India CPI − US CPI) projected forward |
| **Relative Economic Strength** | Interest rate parity (RBI repo − Fed funds rate) projected forward |

The model with the lowest 24h holdout error is used for that run's forecast. The dashboard shows all six scores so you can see which is winning.

---

## Dashboard Features

| Feature | Description |
|---|---|
| Live rate header | Current rate (4 decimal places), MST + UTC timestamp, vs 24h average |
| Signal banner | Green / amber / grey with one-line plain-English reason |
| Auto-refresh | Fetches live rate from Google Finance every 60 seconds |
| 72h area chart | Smooth spline, 48h forecast with ±uncertainty, target line, range slider |
| Signal Strength metric | 0–100 score showing how many indicators agree |
| Bollinger Band position | Where rate sits within its statistical normal range |
| Manual target | Set your own target rate — saved to DB, overrides auto calculation |
| Model comparison | All 6 model errors shown with visual bars — active model highlighted green |
| 3-button advisor | Ask: send in an hour / tomorrow / best time — with Send to Telegram |
| Accuracy tracker | Mean absolute error (24h/48h), % within ±0.5, SEND NOW accuracy |
| Explainer panel | Expandable guide: RSI, Bollinger Bands, Signal Strength, target |
| Per-user Telegram | Anyone can enter their own Chat ID — alerts go only to them |

---

## Cloud Deployment

The system runs fully in the cloud — no local machine needed after setup.

| Component | Platform | Cost |
|---|---|---|
| Database | Supabase (PostgreSQL) | Free tier |
| Scheduler | GitHub Actions (hourly cron) | Free tier (~720 min/month) |
| Dashboard | Streamlit Community Cloud | Free |
| Rate source | Google Sheets + GOOGLEFINANCE | Free |

---

## Project Structure
```
exchange/
├── src/
│   ├── fetcher.py      # Rate fetching (Google Sheets primary + 3 fallbacks) + PostgreSQL storage
│   ├── predictor.py    # RSI, Bollinger Bands, multi-model forecast, signal strength
│   ├── decision.py     # Signal logic + Telegram message formatting
│   ├── alerter.py      # Telegram bot + alert state (stored in PostgreSQL)
│   ├── advisor.py      # Q&A: send in 1hr / tomorrow / best time
│   ├── accuracy.py     # Save predictions + score against actuals
│   ├── db.py           # PostgreSQL connection factory
│   └── dashboard.py    # Streamlit UI (desktop + mobile responsive)
├── logs/
│   └── exchange.log    # Rotating log (auto-created)
├── .streamlit/
│   └── config.toml     # Light theme configuration
├── .github/
│   └── workflows/
│       └── scheduler.yml  # GitHub Actions hourly cron
├── .env                # Your credentials (never committed — see .gitignore)
├── .env.example        # Template — copy to .env and fill in values
├── config.py           # All configuration loaded from .env
├── scheduler.py        # Main entry point (fetch → predict → decide → alert)
└── requirements.txt
```

---

## Setup

### 1. Clone and install
```bash
git clone https://github.com/rajamadabattula/exchange-rate-predictor.git
cd exchange-rate-predictor
pip install -r requirements.txt
```

### 2. Configure credentials
```bash
cp .env.example .env
```

Fill in `.env`:
```
TELEGRAM_BOT_TOKEN=your_token_from_botfather
TELEGRAM_CHAT_ID=your_telegram_chat_id
DATABASE_URL=postgresql://...your_supabase_connection_string...
GOOGLE_SPREADSHEET_ID=your_google_sheet_id
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}  # single-line JSON
ALPHAVANTAGE_API_KEY=your_key                               # optional fallback
ANTHROPIC_API_KEY=your_key                                  # optional AI advisor
```

### 3. Set up Google Sheets (primary rate source)
1. Create a Google Sheet with `=GOOGLEFINANCE("CURRENCY:USDINR")` in cell A1
2. Create a Google Cloud service account with Sheets API enabled
3. Share the sheet with the service account email as Editor
4. Run `encode_creds.py` to convert the JSON key to a single-line string for `.env`

### 4. Run locally
```bash
# Terminal 1 — scheduler (fetches every minute)
python scheduler.py

# Terminal 2 — dashboard
python -m streamlit run src/dashboard.py
```

---

## Configuration Reference

| Key | Value | Description |
|---|---|---|
| `FETCH_INTERVAL_MINUTES` | 1 | Local scheduler fetch interval |
| `ALERT_INTERVAL_HOURS` | 3 | Periodic Telegram summary frequency |
| `HISTORY_DAYS` | 90 | Days of historical data used for analysis |
| `FORECAST_HOURS` | 48 | Prediction horizon |
| `RSI_OVERBOUGHT` | 70 | RSI threshold for overbought signal |
| `RSI_OVERSOLD` | 30 | RSI threshold for oversold signal |
| `SIGNAL_STRENGTH_GATE` | 35 | Min score (0–100) required to fire SEND NOW |
| `TARGET_PERCENTILE` | 85 | Auto target = this percentile of recent rates |
| `TARGET_WINDOW_HOURS` | 72 | Rolling window for auto target calculation |
| `US_INTEREST_RATE` | 4.33 | Fed funds effective rate (%) — update periodically |
| `INDIA_INTEREST_RATE` | 6.25 | RBI repo rate (%) — update periodically |
| `US_INFLATION_RATE` | 2.8 | US annual CPI (%) — update periodically |
| `INDIA_INFLATION_RATE` | 4.9 | India annual CPI (%) — update periodically |

---

## Known Limitations

- **Model limits** — all six models (technical, econometric, and parity-based) capture different aspects of rate behaviour but cannot predict macro events: RBI/Fed policy decisions, geopolitical news, or financial year-end effects. These cause sudden rate moves that no model can reliably forecast.
- **Mid-market rates** — Google Finance and all fallback sources show the mid-market rate. Actual transfer rates from providers include a spread. Always verify on your transfer service before sending.
- **GitHub Actions cron delays** — GitHub's free tier may delay hourly runs by a few minutes during peak usage. The dashboard auto-refresh (every 60 seconds) is unaffected.

---

## Disclaimer

This tool is for personal use and informational purposes only. It is not financial advice. Exchange rate predictions carry inherent uncertainty. Always verify rates with your transfer provider before sending.
