# USD → INR Rate Predictor

![Rate Check](https://github.com/rajamadabattula/exchange-rate-predictor/actions/workflows/scheduler.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.14-blue)
![Tests](https://img.shields.io/badge/tests-33%20passing-brightgreen)

A personal finance tool that monitors the USD/INR exchange rate, predicts the best time to send money internationally, and delivers plain-English alerts via Telegram — powered by technical indicators, linear regression, and an optional LLM-powered advisor.

---

🔴 **[Live Dashboard → exchange-rate-predictor.streamlit.app](https://exchange-rate-predictor.streamlit.app/)**

---

## The Story Behind This Project

I came from India to the US for my Master's degree. Like most international students, I carry debt back home — and every month, I face the same stressful question: *when do I send money?*

The exchange rate is unpredictable. Some days it's good, some days it isn't. And the apps we use for international transfers lock in the rate the moment you hit send — there's no going back.

A week before building this, I sent money at a rate that was $3 lower than it became just days later. That's thousands of rupees lost in a single transfer. For someone managing student debt across two currencies, that's not a rounding error — it genuinely hurts.

I had the data skills. I had the tools. So instead of guessing, I built this.

This dashboard watches the USD/INR rate around the clock, predicts where it's heading, and tells you in plain English — *send now* or *wait*. No charts to interpret. No finance degree required. Just a clear signal when the time is right.

I built it for myself. But every international student sending money home faces the exact same problem. If this helps even one person avoid a bad transfer day, it was worth building.

---

---

## What Makes This Different

Most exchange rate tools show you a chart and leave you to figure it out. This one tells you what to do.

- Fetches live USD/INR data every 15 minutes from Yahoo Finance
- Computes a **dynamic target** that adjusts with the market (48h average + 0.5)
- Predicts the rate 24 and 48 hours ahead using RSI, trend analysis, and linear regression
- Sends a **Telegram alert** the moment it is a good time to send — written as a personal advisor, not a data dump
- Tracks its own **prediction accuracy** over time so you know how much to trust it
- Runs a **Streamlit dashboard** with interactive charts, indicators, and a 3-button Q&A advisor

---

## System Architecture

```
Yahoo Finance (yfinance)
        │
        ▼
  fetcher.py          ← Pulls live + historical USD/INR rates every 15 min
        │
        ▼
  rates.db (SQLite)   ← Stores all historical rates + predictions
        │
        ▼
  predictor.py        ← RSI (14), trend slope, linear regression 48h forecast
        │
        ▼
  decision.py         ← SEND NOW / MONITOR / WAIT signal logic
        │
    ┌───┴────────────────┐
    ▼                    ▼
alerter.py          dashboard.py
(Telegram Bot)      (Streamlit UI)
    │                    │
    ▼                    ▼
Your phone          Browser (localhost)

accuracy.py         ← Scores past predictions against actual rates
advisor.py          ← Answers: send now? tomorrow? best time?
```

---

## Technical Highlights

- **No paid APIs** — 100% free stack (Yahoo Finance, Telegram Bot API, SQLite)
- **Dynamic target rate** — self-adjusting threshold based on recent market data
- **Closed-loop accuracy tracking** — predictions are stored and scored against real outcomes
- **Advisor Q&A** — 3 natural-language questions answered with context-aware reasoning
- **Mobile-responsive dashboard** — works on phone browser via local network
- **Alert deduplication** — no spam; fires immediately on signal change + 3-hour summaries
- **Modular design** — each component is independently testable and replaceable

---

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3.14 |
| Data source | `yfinance` (Yahoo Finance) |
| Storage | SQLite via `sqlite3` |
| Prediction | `scikit-learn` LinearRegression + `pandas` RSI |
| Scheduling | `APScheduler` |
| Alerts | `python-telegram-bot` |
| Dashboard | `Streamlit` + `Plotly` |
| AI Advisor _(optional)_ | Anthropic Claude API (`claude-haiku`) |

---

## Setup

### 1. Clone and install
```bash
git clone <your-repo-url>
cd exchange
pip install -r requirements.txt
```

### 2. Configure
Copy the example credentials file and fill in your values:
```bash
cp .env.example .env
```

Open `.env` and set:
```
TELEGRAM_BOT_TOKEN=your_token_from_botfather
TELEGRAM_CHAT_ID=your_telegram_chat_id
ANTHROPIC_API_KEY=your_anthropic_api_key   # optional — enables AI-powered advisor
```

**Get a free Telegram bot in 2 minutes:**
- Open Telegram → search `@BotFather` → `/newbot`
- Copy the token into `.env`
- Send any message to your bot, then run:

```bash
python scheduler.py --setup
```
Copy the Chat ID printed and paste it into `.env`.

> **Never commit `.env`** — it is already in `.gitignore`.

### 3. Run
```bash
# Terminal 1 — start the scheduler
python scheduler.py

# Terminal 2 — open the dashboard
python -m streamlit run src/dashboard.py
```

Open **http://localhost:8501** in your browser.
On your phone (same WiFi): use the **Network URL** printed in the terminal.

---

## How the Signal Works

### Dynamic Target
```
Target = 48h average rate + 0.5
```
Updates every hour. If the market moves, the target moves with it.

### Decision Rules (in priority order)
| Condition | Signal |
|---|---|
| Rate ≥ target AND RSI ≥ 70 AND trend falling | **SEND NOW** (strongest) |
| Rate ≥ target AND RSI ≥ 70 | **SEND NOW** |
| Rate ≥ target AND forecast drops in 24h | **SEND NOW** |
| Rate ≥ target AND trend sideways | **SEND NOW** |
| Rate ≥ target AND trend rising AND RSI < 60 | **WAIT** (might go higher) |
| Rate within 0.5 of target | **MONITOR** |
| Rate below target | **WAIT** |

### RSI Explained
RSI (Relative Strength Index) measures how fast the rate is moving:
- **Above 70** — Overbought. Rate rose too fast, likely to drop. Best time to send.
- **30–70** — Normal movement
- **Below 30** — Oversold. Rate fell hard, likely to recover. Wait.

---

## Dashboard Features

| Feature | Description |
|---|---|
| Live rate header | Current rate, change vs 24h average, dynamic target |
| Signal banner | Green / amber / grey with one-line plain-English reason |
| 72h area chart | Smooth spline, 48h forecast, target line, range slider. All times UTC. |
| Indicator table | RSI, trend, moving averages, model confidence |
| 3-button advisor | Ask: send in an hour / tomorrow / best time — with Send to Telegram |
| Accuracy tracker | Mean absolute error (24h/48h), % within ±0.5, SEND NOW accuracy |
| Explainer panel | Expandable guide explaining RSI, signals, and chart elements |

---

## Project Structure
```
exchange/
├── src/
│   ├── fetcher.py      # Data fetching + SQLite storage
│   ├── predictor.py    # RSI, trend, 48h linear forecast, dynamic target
│   ├── decision.py     # Signal logic + Telegram message formatting
│   ├── alerter.py      # Telegram bot + alert state (no spam logic)
│   ├── advisor.py      # Q&A: send in 1hr / tomorrow / best time
│   ├── accuracy.py     # Save predictions + score against actuals
│   └── dashboard.py    # Streamlit UI (desktop + mobile responsive)
├── data/
│   └── rates.db        # SQLite database (auto-created on first run)
├── logs/
│   └── exchange.log    # Rotating log (auto-created)
├── .streamlit/
│   └── config.toml     # Light theme configuration
├── .env                # Your credentials (never committed — see .gitignore)
├── .env.example        # Template — copy to .env and fill in values
├── config.py           # Loads credentials from .env via python-dotenv
├── scheduler.py        # Main entry point
└── requirements.txt
```

---

## Configuration Reference

| Key | Default | Description |
|---|---|---|
| `FETCH_INTERVAL_MINUTES` | 15 | How often to fetch and store the live rate |
| `ALERT_INTERVAL_HOURS` | 3 | Periodic Telegram summary frequency |
| `HISTORY_DAYS` | 90 | Days of data used for analysis |
| `FORECAST_HOURS` | 48 | Prediction horizon |
| `RSI_OVERBOUGHT` | 70 | RSI threshold for overbought signal |
| `RSI_OVERSOLD` | 30 | RSI threshold for oversold signal |

---

## Known Limitations

- **Hourly data delay** — Yahoo Finance forex hourly data has a ~6–9 hour lag. Live rate is always current; historical bars may have a gap. The 15-minute fetch fills this over time.
- **Model simplicity** — Linear regression captures trend but not sudden news-driven spikes (central bank decisions, geopolitical events). Accuracy is tracked so you can evaluate it yourself.
- **Single data source** — Yahoo Finance mirrors the mid-market Google exchange rate. Actual transfer rates from providers include a spread.

---

## Disclaimer

This tool is for personal use and informational purposes only. It is not financial advice. Exchange rate predictions carry inherent uncertainty. Always verify rates with your transfer provider before sending.
