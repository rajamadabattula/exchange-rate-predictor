"""
dashboard.py — USD/INR Rate Predictor Dashboard
Run: streamlit run src/dashboard.py
"""

import os
import sys
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from src.fetcher   import bootstrap, load_rates, get_daily_target
from src.predictor import analyse
from src.decision  import decide, format_message, Signal
from src.alerter   import send_message
from src.advisor   import send_in_one_hour, send_tomorrow, best_time_to_send
from src.accuracy  import compute_accuracy

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="USD/INR · Rate Predictor",
    page_icon="💹",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    #MainMenu, footer, header { visibility: hidden; }

    /* ── Desktop layout ── */
    .block-container { padding: 2rem 2.5rem 3rem; max-width: 1200px; }

    .rate-block { margin: 0.25rem 0 1rem; }
    .rate-number {
        font-size: 3rem;
        font-weight: 800;
        color: #111827;
        letter-spacing: -0.02em;
        line-height: 1;
    }
    .rate-sub {
        font-size: 0.85rem;
        color: #6B7280;
        margin-top: 0.4rem;
    }

    .signal-box {
        padding: 1rem 1.25rem;
        border-radius: 10px;
        margin-bottom: 1.5rem;
    }
    .signal-title { font-size: 1rem; font-weight: 700; margin-bottom: 0.3rem; }
    .signal-body  { font-size: 0.875rem; line-height: 1.55; }

    .kv-row {
        display: flex;
        justify-content: space-between;
        padding: 0.55rem 0;
        border-bottom: 1px solid #F3F4F6;
        font-size: 0.85rem;
    }
    .kv-key { color: #6B7280; }
    .kv-val { color: #111827; font-weight: 600; }

    .section-title {
        font-size: 0.7rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #9CA3AF;
        margin-bottom: 0.6rem;
        padding-bottom: 0.4rem;
        border-bottom: 1px solid #E5E7EB;
    }

    /* ── Mobile layout (screens ≤ 768px) ── */
    @media (max-width: 768px) {

        /* Tighter padding on mobile */
        .block-container { padding: 1rem 1rem 2rem !important; }

        /* Rate number slightly smaller */
        .rate-number { font-size: 2.2rem !important; }
        .rate-sub    { font-size: 0.8rem !important; }

        /* Signal box more compact */
        .signal-box  { padding: 0.85rem 1rem !important; margin-bottom: 1rem !important; }
        .signal-title { font-size: 0.95rem !important; }
        .signal-body  { font-size: 0.82rem !important; }

        /* Stack all Streamlit columns to full width */
        [data-testid="column"] {
            width: 100% !important;
            flex: 1 1 100% !important;
            min-width: 100% !important;
            margin-bottom: 0.5rem;
        }

        /* Larger tap targets for buttons */
        [data-testid="baseButton-secondary"],
        [data-testid="baseButton-primary"] {
            min-height: 48px !important;
            font-size: 0.9rem !important;
        }

        /* Metric cards — bigger text for small screens */
        [data-testid="metric-container"] {
            padding: 0.85rem 1rem !important;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.4rem !important;
        }

        /* kv rows wrap on tiny screens */
        .kv-row { flex-wrap: wrap; gap: 0.25rem; }
        .kv-val { text-align: right; }

        /* Chart — reduce height and disable touch interaction on mobile */
        .js-plotly-plot { max-height: 300px; }
        .js-plotly-plot, .js-plotly-plot * { pointer-events: none !important; }
    }
</style>
""", unsafe_allow_html=True)

# ── Telegram setup — always visible on main page ──────────────────────────────

with st.expander("📲 Get Telegram Alerts — Enter your Chat ID here", expanded=True):
    st.markdown(
        "**Step 1:** Search **@Rajam009bot** on Telegram → send it `hi` (activates the bot for you)\n\n"
        "**Step 2:** Message [@userinfobot](https://t.me/userinfobot) on Telegram → it replies with your Chat ID\n\n"
        "**Step 3:** Paste your Chat ID below"
    )
    user_chat_id = st.text_input(
        "Your Telegram Chat ID",
        placeholder="e.g. 123456789",
        label_visibility="collapsed",
    )
    if user_chat_id.strip():
        st.success("✅ Ready — Send buttons are active.")
    else:
        st.caption("Your Chat ID is only stored in your browser session — never saved to any database.")

# ── Why this was built ────────────────────────────────────────────────────────

st.markdown("""
<div style="background:#EFF6FF;border-left:4px solid #2563EB;border-radius:8px;
padding:1.1rem 1.4rem;margin-bottom:1.5rem">
<div style="font-size:0.95rem;font-weight:700;color:#1D4ED8;margin-bottom:0.5rem">
Why this exists</div>
<div style="font-size:0.85rem;color:#1E3A5F;line-height:1.7">
I came from India to the US for my Master's degree. Like most international students, I carry debt
back home — and every month I face the same question: <em>when do I send money?</em><br><br>
A week before building this, I sent money at a rate that was <strong>$3 lower</strong> than it
became just days later. That's thousands of rupees lost in a single transfer.
For someone managing student debt across two currencies, that's not a rounding error —
<strong>it genuinely hurts.</strong><br><br>
So instead of guessing, I built this. It watches the rate around the clock, predicts where it's
heading, and tells you in plain English — <strong>send now</strong> or <strong>wait</strong>.
Built for myself. Useful for every international student sending money home.
</div>
</div>
""", unsafe_allow_html=True)

# ── Data ──────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_data():
    bootstrap()
    df_10d     = load_rates(days=10)   # 10 days for y-axis floor calculation
    df         = load_rates(days=3)    # 72 hours for chart display
    indicators = analyse(df_10d)       # analyse on full 10d for better indicators
    if indicators:
        indicators.dynamic_target = get_daily_target(indicators.ma_48h)
    decision   = decide(indicators) if indicators else None
    last_updated = df_10d["timestamp"].iloc[-1] if not df_10d.empty else None
    return df, df_10d, indicators, decision, last_updated

df, df_10d, ind, dec, last_updated = get_data()


if ind is None or dec is None:
    st.error("Not enough data. Run `python scheduler.py --now` first, then refresh.")
    st.stop()

# Signal colours
SIGNAL_STYLE = {
    Signal.SEND_NOW : {"bg": "#F0FDF4", "border": "#16A34A", "color": "#15803D", "label": "SEND NOW"},
    Signal.MONITOR  : {"bg": "#FFFBEB", "border": "#D97706", "color": "#92400E", "label": "MONITOR"},
    Signal.WAIT     : {"bg": "#F9FAFB", "border": "#6B7280", "color": "#374151", "label": "WAIT"},
}
ss = SIGNAL_STYLE[dec.signal]

rate_vs_avg  = ind.current_rate - ind.ma_24h
delta_sign   = "+" if rate_vs_avg >= 0 else ""
delta_color  = "#16A34A" if rate_vs_avg >= 0 else "#DC2626"

# ── Header ────────────────────────────────────────────────────────────────────

col_left, col_right = st.columns([4, 1])

with col_left:
    if last_updated:
        from datetime import timedelta
        last_mst = last_updated + timedelta(hours=-7)
        updated_str = (
            f"Rate as of {last_mst.strftime('%d %b %Y · %H:%M MST')}"
            f" / {last_updated.strftime('%H:%M UTC')}"
        )
    else:
        updated_str = "Rate as of unknown"
    st.markdown(
        f'<p style="font-size:0.75rem;color:#9CA3AF;font-weight:600;'
        f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.1rem">'
        f'USD / INR &nbsp;·&nbsp; {updated_str} &nbsp;·&nbsp; Updates every 5 minutes</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="rate-block">'
        f'<div class="rate-number">{ind.current_rate:.4f}</div>'
        f'<div class="rate-sub">'
        f'<span style="color:{delta_color};font-weight:600">'
        f'{delta_sign}{rate_vs_avg:.4f}</span>'
        f'&nbsp; vs 24h average &nbsp;·&nbsp; '
        f'Target: <strong>{ind.dynamic_target:.2f}</strong> <span style="color:#9CA3AF;font-size:0.75rem">(set daily · resets midnight MST)</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

with col_right:
    st.markdown("<div style='height:1.6rem'></div>", unsafe_allow_html=True)
    if st.button("↺ Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.markdown("<div style='height:0.35rem'></div>", unsafe_allow_html=True)
    if st.button("📲 Send Alert", use_container_width=True, type="primary",
                 disabled=not user_chat_id.strip()):
        cid  = user_chat_id.strip()
        sent = send_message(format_message(dec, ind), chat_id=cid)
        st.toast("Sent to your Telegram!" if sent else "Failed — did you message the bot first? (Step 1)",
                 icon="📲" if sent else "⚠️")

# ── Signal banner ─────────────────────────────────────────────────────────────

st.markdown(
    f'<div class="signal-box" style="'
    f'background:{ss["bg"]};'
    f'border-left:4px solid {ss["border"]}">'
    f'<div class="signal-title" style="color:{ss["color"]}">{ss["label"]}</div>'
    f'<div class="signal-body" style="color:#374151">{dec.summary}</div>'
    f'</div>',
    unsafe_allow_html=True,
)

# ── Metrics row ───────────────────────────────────────────────────────────────

m1, m2, m3, m4, m5 = st.columns(5)

m1.metric("Dynamic Target", f"{ind.dynamic_target:.2f}",
          "Above ✓" if ind.current_rate >= ind.dynamic_target else f"Gap: {ind.dynamic_target - ind.current_rate:.2f}")
m2.metric("RSI · 14",    f"{ind.rsi_14:.0f}",
          "Overbought" if ind.rsi_14 >= 70 else "Oversold" if ind.rsi_14 <= 30 else "Neutral")
m3.metric("Trend",       ind.trend_label.capitalize(),
          f"{ind.trend_slope:+.4f}/hr")
m4.metric("Forecast 24h", f"{ind.predicted_24h:.2f}",
          f"±{ind.forecast_uncertainty:.2f} uncertainty")
m5.metric("Signal Strength", f"{ind.signal_strength}/100",
          "High" if ind.signal_strength >= 67 else "Medium" if ind.signal_strength >= 34 else "Low")

st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

# ── Chart ─────────────────────────────────────────────────────────────────────

st.markdown('<div class="section-title">Last 72 Hours · Hourly · + 48h Forecast &nbsp;·&nbsp; All times in UTC</div>', unsafe_allow_html=True)

if not df.empty:
    last_ts    = df["timestamp"].iloc[-1]
    future_ts  = [last_ts + pd.Timedelta(hours=24), last_ts + pd.Timedelta(hours=48)]
    forecast_x = [last_ts] + future_ts
    forecast_y = [ind.current_rate, ind.predicted_24h, ind.predicted_48h]

    all_y  = list(df["rate"]) + forecast_y
    y_min  = round(df_10d["rate"].min() - 0.2, 2)   # 10-day low minus small padding
    y_max  = round(max(all_y) + 0.4, 2)

    fig = go.Figure()

    # ── Area fill: invisible baseline at y_min, then fill "tonexty" ──────────
    # This fills from 80 up to the rate line — correct area chart behaviour
    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=[y_min] * len(df),   # area fills from 10-day low upward
        mode="lines",
        line=dict(width=0, color="rgba(0,0,0,0)"),
        showlegend=False,
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=df["timestamp"], y=df["rate"],
        mode="lines",
        name="USD/INR",
        fill="tonexty",
        fillcolor="rgba(37,99,235,0.10)",
        line=dict(color="#1D4ED8", width=2.5, shape="spline", smoothing=1.3),
        hovertemplate=(
            "<span style='font-size:13px'><b>%{y:.4f}</b> INR/USD</span>"
            "<br><span style='color:#9CA3AF'>%{x|%b %d · %H:%M}</span>"
            "<extra></extra>"
        ),
    ))

    # ── Forecast line ─────────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=forecast_x, y=forecast_y,
        mode="lines+markers",
        name="Forecast",
        line=dict(color="#F97316", width=2, dash="dot", shape="spline"),
        marker=dict(
            size=10, color="#F97316",
            line=dict(color="white", width=2.5),
        ),
        hovertemplate=(
            "<span style='font-size:13px'><b>%{y:.4f}</b> (forecast)</span>"
            "<extra></extra>"
        ),
    ))

    # ── Dynamic target line ───────────────────────────────────────────────────
    fig.add_hline(
        y=ind.dynamic_target,
        line_color="#16A34A", line_width=1.5, line_dash="dash",
        annotation_text=f"Target {ind.dynamic_target:.2f}",
        annotation_font=dict(size=12, color="#16A34A", family="Inter, sans-serif"),
        annotation_position="top right",
        annotation_bgcolor="rgba(255,255,255,0.85)",
        annotation_borderpad=4,
    )

    # ── Current rate marker ───────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=[last_ts], y=[ind.current_rate],
        mode="markers",
        name="Now",
        marker=dict(size=10, color="#1D4ED8", line=dict(color="white", width=2.5)),
        hovertemplate=(
            "<b>Now: %{y:.4f}</b><extra></extra>"
        ),
    ))

    fig.update_layout(
        height=430,
        margin=dict(l=0, r=10, t=8, b=0),
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="white",
            font=dict(size=13, color="#111827", family="Inter, sans-serif"),
            bordercolor="#E5E7EB",
        ),
        legend=dict(
            orientation="h", y=1.06, x=0,
            font=dict(size=12, color="#374151"),
            bgcolor="rgba(0,0,0,0)",
            itemwidth=30,
        ),
        xaxis=dict(
            showgrid=False,
            showline=False,
            zeroline=False,
            tickfont=dict(size=11, color="#9CA3AF", family="Inter, sans-serif"),
            tickformat="%H:%M\n%b %d",
            dtick=6 * 3600000,          # tick every 6 hours
            title=dict(text="Time (UTC)", font=dict(size=11, color="#9CA3AF"), standoff=8),
            rangeslider=dict(visible=True, thickness=0.04, bgcolor="#F9FAFB"),
        ),
        yaxis=dict(
            range=[y_min, y_max],
            showgrid=True,
            gridcolor="#F3F4F6",
            gridwidth=1,
            showline=False,
            zeroline=False,
            tickfont=dict(size=11, color="#9CA3AF", family="Inter, sans-serif"),
            tickformat=".2f",
            side="right",               # y-axis on the right like Google Finance
        ),
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "displayModeBar": True,
            "displaylogo": False,
            "modeBarButtonsToRemove": [
                "zoom2d", "pan2d", "select2d", "lasso2d",
                "zoomIn2d", "zoomOut2d", "autoScale2d",
                "hoverClosestCartesian", "hoverCompareCartesian",
                "toggleSpikelines",
            ],
            "modeBarButtonsToAdd": ["resetScale2d"],
            "toImageButtonOptions": {
                "format": "png", "filename": "usdinr_chart",
                "height": 500, "width": 1200, "scale": 2,
            },
        },
    )

st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

# ── How to read this dashboard ─────────────────────────────────────────────────


with st.expander("How to read this dashboard", expanded=False):
    rsi_val  = ind.rsi_14
    rsi_status = (
        ("🔴", "Overbought — rate has risen fast and is likely to drop. Strong time to send.")
        if rsi_val >= 70 else
        ("🟢", "Oversold — rate has fallen and may bounce back up. Consider waiting.")
        if rsi_val <= 30 else
        ("🟡", "Neutral — rate is moving normally. Other signals take priority.")
    )

    st.markdown(f"""
**What is RSI?**
RSI (Relative Strength Index) is a number from 0–100 that measures how fast the rate is moving.
Think of it like a rubber band — if stretched too far in one direction, it snaps back.

| RSI Range | Status | What it means for you |
|---|---|---|
| **Above 70** | Overbought 🔴 | Rate rose too fast — likely to drop. **Good time to send.** |
| **30 – 70** | Neutral 🟡 | Normal movement. Check trend and forecast. |
| **Below 30** | Oversold 🟢 | Rate fell too fast — likely to recover. **Wait for better rate.** |

**Right now:** RSI is `{rsi_val:.0f}` — {rsi_status[0]} {rsi_status[1]}

---

**What is Signal Strength?**
Signal Strength (0–100) counts how many indicators agree that the rate is at a peak and likely to drop.
**SEND NOW only fires when Signal Strength ≥ 50** — meaning at least 2 indicators confirm.

| Score | Label | Meaning |
|---|---|---|
| **67–100** | High | RSI + Bollinger + Trend all agree. Strong signal. |
| **34–66** | Medium | 2 indicators agree. Decent confidence. |
| **0–33** | Low | Signals mixed. Rate may still rise. |

**Right now:** Signal Strength is `{ind.signal_strength}/100`

---

**What are Bollinger Bands?**
Bollinger Bands mark the "normal range" for the rate based on the last 20 hours.
If the rate goes above the upper band, it's statistically extended — more likely to pull back.
This catches rate peaks that RSI alone might miss.

---

**What is the Dynamic Target?**
Instead of a fixed number, the target updates daily as `48h average rate + 0.5`.
Current target: **{ind.dynamic_target:.2f}** (48h avg {ind.ma_48h:.2f} + 0.5)

---

**What does the signal mean?**

| Signal | Meaning |
|---|---|
| 🟢 **SEND NOW** | Rate above target AND ≥ 2 indicators agree it's at a peak. |
| 🟡 **MONITOR** | Rate near/above target but signals are mixed. May still rise. |
| ⚪ **WAIT** | Rate below target. Not the right time yet. |

---

**⚠️ Model limitation**
This model uses trend analysis (RSI, Bollinger Bands, linear regression).
It **cannot predict** news events, RBI/Fed policy changes, or financial year-end effects.
Always confirm on your transfer service before sending.

---

**Chart guide**
- **Blue line** — actual USD/INR rate, from Google Finance
- **Orange dashed** — trend-based forecast (±uncertainty shown)
- **Green dashed line** — your dynamic target. You want the blue line above this.
""")

st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

# ── Bottom: Reasoning + Levels ────────────────────────────────────────────────

col_a, col_gap, col_b = st.columns([5, 0.3, 4])

with col_a:
    st.markdown('<div class="section-title">Why This Signal</div>', unsafe_allow_html=True)
    for line in dec.reasons:
        key, sep, val = line.partition(":")
        if sep and val:
            st.markdown(
                f'<div class="kv-row">'
                f'<span class="kv-key">{key.strip()}</span>'
                f'<span class="kv-val">{val.strip()}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

with col_b:
    st.markdown('<div class="section-title">Key Levels</div>', unsafe_allow_html=True)

    bb_label = (
        "Above upper band" if ind.bb_pct >= 1.0 else
        f"{ind.bb_pct*100:.0f}% (near upper)" if ind.bb_pct >= 0.8 else
        f"{ind.bb_pct*100:.0f}% (mid range)" if ind.bb_pct >= 0.5 else
        f"{ind.bb_pct*100:.0f}% (near lower)"
    )
    strength_label = "High" if ind.signal_strength >= 67 else "Medium" if ind.signal_strength >= 34 else "Low"
    levels = [
        ("Dynamic Target",   f"{ind.dynamic_target:.2f}  (48h avg + 0.5)"),
        ("Current Rate",     f"{ind.current_rate:.4f}"),
        ("24h Average",      f"{ind.ma_24h:.4f}"),
        ("Bollinger Band",   bb_label),
        ("Forecast 24h",     f"{ind.predicted_24h:.4f}  ±{ind.forecast_uncertainty:.4f}"),
        ("Forecast 48h",     f"{ind.predicted_48h:.4f}"),
        ("Signal Strength",  f"{ind.signal_strength}/100  ({strength_label})"),
    ]
    for label, value in levels:
        st.markdown(
            f'<div class="kv-row">'
            f'<span class="kv-key">{label}</span>'
            f'<span class="kv-val">{value}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

# ── Ask a Question ────────────────────────────────────────────────────────────

st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
st.markdown('<div class="section-title">Ask a Question</div>', unsafe_allow_html=True)

QUESTIONS = {
    "q1": ("Shall I send in an hour?",    send_in_one_hour),
    "q2": ("Shall I send tomorrow?",       send_tomorrow),
    "q3": ("When is the best time?",       best_time_to_send),
}

# Initialise session state
for key in QUESTIONS:
    if f"answer_{key}" not in st.session_state:
        st.session_state[f"answer_{key}"] = None

btn_cols = st.columns(3)
for i, (key, (label, fn)) in enumerate(QUESTIONS.items()):
    with btn_cols[i]:
        if st.button(label, use_container_width=True, key=f"btn_{key}"):
            verdict, dash_ans, tg_ans = fn(ind)
            st.session_state[f"answer_{key}"] = (verdict, dash_ans, tg_ans)
            # Clear other answers so only one shows at a time
            for other in QUESTIONS:
                if other != key:
                    st.session_state[f"answer_{other}"] = None

# Show whichever answer is active
VERDICT_STYLE = {
    "yes" : ("#F0FDF4", "#16A34A", "#15803D"),
    "now" : ("#F0FDF4", "#16A34A", "#15803D"),
    "maybe": ("#FFFBEB", "#D97706", "#92400E"),
    "wait" : ("#FFFBEB", "#D97706", "#92400E"),
    "no"  : ("#FEF2F2", "#DC2626", "#991B1B"),
}

for key in QUESTIONS:
    result = st.session_state.get(f"answer_{key}")
    if result:
        verdict, dash_ans, tg_ans = result
        bg, border, color = VERDICT_STYLE.get(verdict, ("#F9FAFB", "#9CA3AF", "#374151"))

        st.markdown(
            f'<div style="background:{bg};border-left:4px solid {border};'
            f'border-radius:8px;padding:1.1rem 1.4rem;margin-top:1rem">'
            f'<div style="color:{color};font-size:0.9rem;line-height:1.7">{dash_ans}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
        if st.button("📲 Send this to Telegram", key=f"tg_{key}",
                     disabled=not user_chat_id.strip()):
            cid  = user_chat_id.strip()
            sent = send_message(tg_ans, chat_id=cid)
            st.toast("Sent to your Telegram!" if sent else "Failed — did you message the bot first? (Step 1)",
                     icon="📲" if sent else "⚠️")
        break  # only one answer visible at a time

# ── Historical Accuracy ───────────────────────────────────────────────────────

st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
st.markdown('<div class="section-title">Prediction Accuracy · How Good Is The Model?</div>',
            unsafe_allow_html=True)

acc = compute_accuracy()

if acc is None:
    st.info("Not enough history yet to score accuracy. Check back in 24–48 hours once predictions have been made and can be compared against actual rates.")
else:
    a1, a2, a3, a4 = st.columns(4)

    a1.metric("24h Forecast Error",  f"±{acc.mae_24h:.4f}",
              help="Average difference between predicted and actual rate (24h ahead)")
    a2.metric("48h Forecast Error",  f"±{acc.mae_48h:.4f}",
              help="Average difference between predicted and actual rate (48h ahead)")
    a3.metric("Within ±0.5  (24h)", f"{acc.within_half_24h:.0f}%",
              help="% of 24h predictions that landed within 0.5 of the actual rate")
    a4.metric("SEND NOW Accuracy",
              f"{acc.signal_accuracy:.0f}%" if acc.signal_correct + acc.signal_wrong > 0 else "—",
              f"{acc.signal_correct} correct · {acc.signal_wrong} wrong",
              help="When SEND NOW fired, was the rate actually at or near a peak?")

    if not acc.df_chart.empty:
        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)
        st.markdown('<div class="section-title">Predicted vs Actual — Last 50 Scored Predictions (24h)</div>',
                    unsafe_allow_html=True)

        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=acc.df_chart["Time"], y=acc.df_chart["Actual"],
            mode="lines", name="Actual",
            line=dict(color="#2563EB", width=2),
        ))
        fig2.add_trace(go.Scatter(
            x=acc.df_chart["Time"], y=acc.df_chart["Predicted"],
            mode="lines", name="Predicted",
            line=dict(color="#F97316", width=1.5, dash="dot"),
        ))
        fig2.update_layout(
            height=260,
            margin=dict(l=0, r=0, t=4, b=0),
            plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
            hovermode="x unified",
            legend=dict(orientation="h", y=1.08, x=0,
                        font=dict(size=12, color="#374151"),
                        bgcolor="rgba(0,0,0,0)"),
            xaxis=dict(showgrid=False, tickfont=dict(size=11, color="#9CA3AF"),
                       tickformat="%b %d", showline=False, zeroline=False),
            yaxis=dict(showgrid=True, gridcolor="#F3F4F6",
                       tickfont=dict(size=11, color="#9CA3AF"),
                       tickformat=".2f", showline=False, zeroline=False),
        )
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

# ── Footer ────────────────────────────────────────────────────────────────────

st.markdown("<div style='height:2rem'></div>", unsafe_allow_html=True)
st.markdown(
    f"<div style='font-size:0.72rem;color:#D1D5DB;text-align:center;"
    f"padding-top:1rem;border-top:1px solid #F3F4F6'>"
    f"Updated {datetime.now(timezone.utc).strftime('%d %b %Y · %H:%M UTC')}"
    f" &nbsp;·&nbsp; Target = 48h avg + 0.5 &nbsp;·&nbsp; Not financial advice"
    f"</div>",
    unsafe_allow_html=True,
)

st.markdown(
    "<div style='margin-top:0.75rem;padding:0.85rem 1.25rem;background:#FEF9C3;"
    "border:2px solid #EAB308;border-radius:8px;text-align:center'>"
    "<strong style='color:#92400E;font-size:0.85rem'>⚠️ DATA SOURCE &amp; MODEL DISCLAIMER</strong>"
    "<p style='color:#78350F;font-size:0.8rem;margin:0.4rem 0 0'>"
    "Rates are sourced from <strong>Google Finance</strong> via Google Sheets (=GOOGLEFINANCE). "
    "These are mid-market rates and may differ from your transfer service due to spread and fees. "
    "Forecasts are <strong>trend-based only</strong> and cannot predict macro events, news, or "
    "policy changes. <strong>Always verify the live rate on your transfer service before sending. "
    "Do your own research.</strong></p></div>",
    unsafe_allow_html=True,
)
