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
from streamlit_autorefresh import st_autorefresh

_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
sys.path.insert(0, _root)
sys.path.insert(0, _here)

import config
try:
    from src.fetcher   import bootstrap, load_rates, fetch_current_rate, save_current_rate, get_manual_target, set_manual_target, get_minimum_target, set_minimum_target
    from src.predictor import analyse
    from src.decision  import decide, format_message, Signal
    from src.alerter   import send_message
    from src.advisor   import send_in_one_hour, send_tomorrow, best_time_to_send
    from src.accuracy  import compute_accuracy
    from src.db        import get_conn
except ImportError:
    from fetcher   import bootstrap, load_rates, fetch_current_rate, save_current_rate, get_manual_target, set_manual_target, get_minimum_target, set_minimum_target
    from predictor import analyse
    from decision  import decide, format_message, Signal
    from alerter   import send_message
    from advisor   import send_in_one_hour, send_tomorrow, best_time_to_send
    from accuracy  import compute_accuracy
    from db        import get_conn

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="USD/INR · Should I Send?",
    page_icon="💹",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Auto-refresh every 60 seconds ─────────────────────────────────────────────

_refresh_count = st_autorefresh(interval=60_000, key="rate_auto_refresh")
if _refresh_count > 0:
    with st.spinner("Refreshing rate…"):
        _rate = fetch_current_rate()
        if _rate:
            save_current_rate(_rate)
    st.cache_data.clear()

# ── CSS ───────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding: 1.5rem 2rem 3rem; max-width: 1200px; }

    .hero-signal {
        padding: 1.2rem 1.5rem; border-radius: 12px; margin-bottom: 0.75rem;
    }
    .hero-signal-label {
        font-size: 1.55rem; font-weight: 800; letter-spacing: -0.01em; line-height: 1.1;
    }
    .hero-signal-sub  { font-size: 0.875rem; margin-top: 0.4rem; line-height: 1.55; }
    .hero-signal-hint { font-size: 0.77rem; color: #6B7280; margin-top: 0.35rem; }

    .rate-hero {
        font-size: 2.8rem; font-weight: 800; color: #111827;
        letter-spacing: -0.03em; line-height: 1;
    }
    .rate-sub { font-size: 0.8rem; color: #6B7280; margin-top: 0.3rem; }

    .kv-row {
        display: flex; justify-content: space-between;
        padding: 0.5rem 0; border-bottom: 1px solid #F3F4F6; font-size: 0.85rem;
    }
    .kv-key { color: #6B7280; }
    .kv-val { color: #111827; font-weight: 600; }

    .section-title {
        font-size: 0.67rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.09em; color: #9CA3AF;
        margin-bottom: 0.5rem; padding-bottom: 0.3rem;
        border-bottom: 1px solid #E5E7EB;
    }
    .impact-box {
        background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px;
        padding: 0.9rem 1.1rem; margin-bottom: 0.4rem;
    }
    .impact-number { font-size: 1.35rem; font-weight: 700; color: #111827; }
    .impact-label  { font-size: 0.77rem; color: #6B7280; margin-top: 0.1rem; }

    .contrib-bar-wrap { background: #F3F4F6; border-radius: 4px; height: 5px; margin-top: 3px; width: 100%; }
    .contrib-bar      { border-radius: 4px; height: 5px; }

    /* ── Tab bar ── */
    [data-testid="stTabs"] > div:first-child {
        border-bottom: 2px solid #E5E7EB;
        gap: 0;
    }
    [data-testid="stTabs"] button[data-baseweb="tab"] {
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        padding: 0.5rem 1.1rem !important;
        color: #6B7280 !important;
        border-bottom: 2px solid transparent !important;
        margin-bottom: -2px !important;
        background: transparent !important;
    }
    [data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
        color: #1D4ED8 !important;
        border-bottom: 2px solid #1D4ED8 !important;
    }
    [data-testid="stTabs"] button[data-baseweb="tab"]:hover {
        color: #374151 !important;
        background: #F9FAFB !important;
    }

    /* ── Settings cards ── */
    .settings-card {
        background: #FAFAFA; border: 1px solid #E5E7EB;
        border-radius: 10px; padding: 1.1rem 1.3rem; margin-bottom: 1rem;
    }
    .settings-card-title {
        font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
        letter-spacing: 0.09em; color: #6B7280; margin-bottom: 0.75rem;
    }

    @media (max-width: 768px) {
        .block-container { padding: 0.75rem 0.75rem 2rem !important; }
        .rate-hero        { font-size: 2.2rem !important; }
        .hero-signal-label { font-size: 1.25rem !important; }
        [data-testid="column"] {
            width: 100% !important; flex: 1 1 100% !important;
            min-width: 100% !important; margin-bottom: 0.4rem;
        }
        [data-testid="baseButton-secondary"],
        [data-testid="baseButton-primary"] { min-height: 48px !important; }
        [data-testid="stMetricValue"]       { font-size: 1.2rem !important; }
    }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────

if "user_chat_id" not in st.session_state:
    st.session_state["user_chat_id"] = ""
if "chart_window" not in st.session_state:
    st.session_state["chart_window"] = "72h"
for _k in ["answer_q1", "answer_q2", "answer_q3"]:
    if _k not in st.session_state:
        st.session_state[_k] = None

# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def get_data():
    bootstrap()
    df_7d  = load_rates(days=7)
    df_10d = load_rates(days=10)
    ind    = analyse(df_10d)
    if ind:
        manual = get_manual_target()
        if manual is not None:
            ind.dynamic_target = manual
        ind.minimum_target = get_minimum_target()
    dec    = decide(ind) if ind else None
    acc    = compute_accuracy()
    last_ts = df_10d["timestamp"].iloc[-1] if not df_10d.empty else None
    return df_7d, df_10d, ind, dec, acc, last_ts


@st.cache_data(ttl=300)
def get_send_now_markers(days: int = 7):
    """Timestamps where SEND NOW signal fired in last N days (deduplicated by hour)."""
    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT DISTINCT ON (DATE_TRUNC('hour', created_at))
                created_at
            FROM predictions
            WHERE signal = 'SEND NOW'
              AND created_at >= NOW() - (%s || ' days')::INTERVAL
            ORDER BY DATE_TRUNC('hour', created_at), created_at DESC
        """, (str(days),))
        rows = cur.fetchall()
        conn.close()
        return pd.DataFrame({"timestamp": [r[0] for r in rows]}) if rows else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


with st.spinner("Fetching latest rate…"):
    df_7d, df_10d, ind, dec, acc, last_updated = get_data()

if ind is None or dec is None:
    st.error("Not enough data. Run `python scheduler.py --now` first, then refresh.")
    st.stop()

# ── Constants + helpers ───────────────────────────────────────────────────────

SIGNAL_STYLE = {
    Signal.SEND_NOW: {"bg": "#F0FDF4", "border": "#16A34A", "color": "#15803D", "label": "SEND NOW"},
    Signal.MONITOR:  {"bg": "#FFFBEB", "border": "#D97706", "color": "#92400E", "label": "MONITOR"},
    Signal.WAIT:     {"bg": "#F9FAFB", "border": "#6B7280", "color": "#374151", "label": "WAIT"},
}
ss = SIGNAL_STYLE[dec.signal]


def compute_confidence(ind, acc) -> int:
    model_conf = max(0, min(100, int((1 - acc.mae_24h / 0.5) * 100))) if (acc and acc.mae_24h > 0) else 50
    return int(0.5 * model_conf + 0.5 * ind.signal_strength)


def forecast_at_hours(hours: int) -> float:
    if hours <= 0:
        return ind.current_rate
    if hours <= 24:
        return ind.current_rate + (ind.predicted_24h - ind.current_rate) * (hours / 24)
    if hours <= 48:
        return ind.predicted_24h + (ind.predicted_48h - ind.predicted_24h) * ((hours - 24) / 24)
    slope = ind.predicted_48h - ind.predicted_24h
    return ind.predicted_48h + slope * ((hours - 48) / 24)


def one_liner() -> str:
    parts = []
    if ind.current_rate >= ind.dynamic_target:
        parts.append(f"rate above target ({ind.dynamic_target:.2f})")
    else:
        parts.append(f"rate {ind.dynamic_target - ind.current_rate:.2f} below target ({ind.dynamic_target:.2f})")
    if ind.rsi_14 >= 70:   parts.append("RSI overbought")
    elif ind.rsi_14 >= 60: parts.append("RSI elevated")
    if ind.bb_pct >= 1.0:  parts.append("above Bollinger band")
    elif ind.bb_pct >= 0.8: parts.append("Bollinger near upper")
    if ind.trend_label == "falling": parts.append("trend falling")
    elif ind.trend_label == "rising": parts.append("trend rising")
    return " · ".join(parts)


confidence   = compute_confidence(ind, acc)
rate_vs_avg  = ind.current_rate - ind.ma_24h
delta_sign   = "+" if rate_vs_avg >= 0 else ""
delta_color  = "#16A34A" if rate_vs_avg >= 0 else "#DC2626"

VERDICT_STYLE = {
    "yes":   ("#F0FDF4", "#16A34A", "#15803D"),
    "now":   ("#F0FDF4", "#16A34A", "#15803D"),
    "maybe": ("#FFFBEB", "#D97706", "#92400E"),
    "wait":  ("#FFFBEB", "#D97706", "#92400E"),
    "no":    ("#FEF2F2", "#DC2626", "#991B1B"),
}

# ── HERO ──────────────────────────────────────────────────────────────────────

col_rate, col_signal = st.columns([2, 3])

with col_rate:
    if last_updated:
        from zoneinfo import ZoneInfo
        mountain = ZoneInfo("America/Denver")
        last_mt  = last_updated.replace(tzinfo=timezone.utc).astimezone(mountain)
        ts_str   = f"{last_mt.strftime('%d %b · %H:%M')} {last_mt.strftime('%Z')}"
    else:
        ts_str = "—"
    st.markdown(
        f'<p style="font-size:0.72rem;color:#9CA3AF;font-weight:600;'
        f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.15rem">'
        f'USD / INR · {ts_str} · refreshes every 60s</p>',
        unsafe_allow_html=True,
    )
    _min_tgt = get_minimum_target()
    _at_floor = _min_tgt is not None and ind.current_rate <= _min_tgt
    _floor_html = ""
    if _min_tgt is not None:
        _floor_color = "#DC2626" if _at_floor else "#6B7280"
        _floor_html = (
            f' &nbsp;·&nbsp; Floor: <strong style="color:{_floor_color}">{_min_tgt:.2f}</strong>'
            + (f' <span style="color:#DC2626;font-weight:700">⚠ HIT</span>' if _at_floor else "")
        )
    st.markdown(
        f'<div class="rate-hero">{ind.current_rate:.4f}</div>'
        f'<div class="rate-sub">'
        f'<span style="color:{delta_color};font-weight:600">{delta_sign}{rate_vs_avg:.4f}</span>'
        f' vs 24h avg &nbsp;·&nbsp; Target: <strong>{ind.dynamic_target:.2f}</strong>'
        f' <span style="color:#9CA3AF">('
        f'{"manual" if get_manual_target() else "auto"})</span>'
        f'{_floor_html}'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
    _c1, _c2 = st.columns(2)
    with _c1:
        if st.button("↺ Refresh", use_container_width=True):
            with st.spinner("Fetching..."):
                _r = fetch_current_rate()
                if _r:
                    save_current_rate(_r)
            st.cache_data.clear()
            st.rerun()
    with _c2:
        if st.button("📲 Send Alert", use_container_width=True, type="primary",
                     disabled=not st.session_state["user_chat_id"].strip()):
            _sent = send_message(format_message(dec, ind),
                                 chat_id=st.session_state["user_chat_id"].strip())
            st.toast("Sent!" if _sent else "Failed", icon="📲" if _sent else "⚠️")

with col_signal:
    st.markdown(
        f'<div class="hero-signal" style="background:{ss["bg"]};border-left:5px solid {ss["border"]}">'
        f'<div class="hero-signal-label" style="color:{ss["color"]}">{ss["label"]}</div>'
        f'<div class="hero-signal-sub" style="color:#374151">{dec.summary}</div>'
        f'<div class="hero-signal-hint">{one_liner()}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── 6 Metric cards ────────────────────────────────────────────────────────────

m1, m2, m3, m4, m5, m6 = st.columns(6)
gap = ind.dynamic_target - ind.current_rate

m1.metric("Current Rate",    f"{ind.current_rate:.4f}",
          f"{delta_sign}{rate_vs_avg:.4f} vs 24h avg", delta_color="normal")
m2.metric("Target Rate",     f"{ind.dynamic_target:.2f}",
          "Above ✓" if ind.current_rate >= ind.dynamic_target else f"{gap:.2f} away",
          delta_color="normal",
          help="Set your own target in ⚙️ Settings. Auto = 85th pct of last 72h.")
m3.metric("Signal Strength", f"{ind.signal_strength}/100",
          "High" if ind.signal_strength >= 67 else "Medium" if ind.signal_strength >= 34 else "Low",
          help="How many indicators agree rate is at a peak. 35+ needed to fire SEND NOW.")
m4.metric("Confidence",      f"{confidence}%",
          "Model accuracy + signal",
          help="Blends recent forecast MAE with signal strength.")
m5.metric("Forecast 24h",    f"{ind.predicted_24h:.2f}",
          f"±{ind.forecast_uncertainty:.2f}",
          help=f"Active model: {ind.model_used}")
m6.metric("Forecast 48h",    f"{ind.predicted_48h:.2f}",
          f"±{ind.forecast_uncertainty * 1.3:.2f}")

st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

# ── Money Impact Calculator ───────────────────────────────────────────────────

st.markdown('<div class="section-title">Money Impact Calculator</div>', unsafe_allow_html=True)
_mic1, _mic2 = st.columns([1, 3])
with _mic1:
    usd_amount = st.number_input("USD", min_value=1.0, max_value=500000.0,
                                 value=1000.0, step=100.0, format="%.0f",
                                 label_visibility="collapsed")
    st.caption("Enter USD amount")

with _mic2:
    inr_now  = usd_amount * ind.current_rate
    inr_24h  = usd_amount * ind.predicted_24h
    inr_48h  = usd_amount * ind.predicted_48h
    g24      = inr_24h - inr_now
    g48      = inr_48h - inr_now
    gc24     = "#16A34A" if g24 >= 0 else "#DC2626"
    gc48     = "#16A34A" if g48 >= 0 else "#DC2626"

    _ic1, _ic2, _ic3 = st.columns(3)
    _ic1.markdown(
        f'<div class="impact-box">'
        f'<div class="impact-number">₹{inr_now:,.0f}</div>'
        f'<div class="impact-label">Send <b>now</b></div>'
        f'</div>', unsafe_allow_html=True)
    _ic2.markdown(
        f'<div class="impact-box">'
        f'<div class="impact-number">₹{inr_24h:,.0f}</div>'
        f'<div class="impact-label">In <b>24h</b> &nbsp;'
        f'<span style="color:{gc24};font-weight:700">{"+" if g24 >= 0 else ""}₹{abs(g24):,.0f}</span>'
        f'</div></div>', unsafe_allow_html=True)
    _ic3.markdown(
        f'<div class="impact-box">'
        f'<div class="impact-number">₹{inr_48h:,.0f}</div>'
        f'<div class="impact-label">In <b>48h</b> &nbsp;'
        f'<span style="color:{gc48};font-weight:700">{"+" if g48 >= 0 else ""}₹{abs(g48):,.0f}</span>'
        f'</div></div>', unsafe_allow_html=True)

st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

# ── Chart ─────────────────────────────────────────────────────────────────────

_chart_header, _chart_toggle = st.columns([5, 1])
with _chart_toggle:
    _win = st.radio("Window", ["24h", "72h", "7d"], index=1,
                    key="chart_window_radio", label_visibility="collapsed")
    st.session_state["chart_window"] = _win

window = st.session_state.get("chart_window", "72h")
_cutoff_days = {"24h": 1, "72h": 3, "7d": 7}[window]
df_chart = (df_7d[df_7d["timestamp"] >= df_7d["timestamp"].iloc[-1]
            - pd.Timedelta(days=_cutoff_days)]
            if not df_7d.empty else df_7d)

# Convert timestamps to Mountain Time for display
from zoneinfo import ZoneInfo as _ZI
_MT = _ZI("America/Denver")
if not df_chart.empty:
    _ts = df_chart["timestamp"]
    if _ts.dt.tz is None:
        _ts = _ts.dt.tz_localize("UTC")
    df_chart = df_chart.copy()
    df_chart["timestamp"] = _ts.dt.tz_convert(_MT)

with _chart_header:
    st.markdown(f'<div class="section-title">USD/INR · Last {window} + 48h Forecast · MT</div>',
                unsafe_allow_html=True)

if not df_chart.empty:
    _last_ts = df_chart["timestamp"].iloc[-1]
    _fx = [_last_ts,
           _last_ts + pd.Timedelta(hours=24),
           _last_ts + pd.Timedelta(hours=48)]
    _fy  = [ind.current_rate, ind.predicted_24h, ind.predicted_48h]
    _unc = ind.forecast_uncertainty
    _fhi = [ind.current_rate + _unc * 0.3,
            ind.predicted_24h + _unc,
            ind.predicted_48h + _unc * 1.4]
    _flo = [ind.current_rate - _unc * 0.3,
            ind.predicted_24h - _unc,
            ind.predicted_48h - _unc * 1.4]

    _key_vals = list(df_chart["rate"]) + [ind.predicted_24h, ind.predicted_48h, ind.dynamic_target]
    if ind.minimum_target is not None:
        _key_vals.append(ind.minimum_target)
    _y_min = round(min(_key_vals) - 0.15, 2)
    _y_max = round(max(_key_vals) + 0.15, 2)

    fig = go.Figure()

    # Area baseline
    fig.add_trace(go.Scatter(x=df_chart["timestamp"], y=[_y_min] * len(df_chart),
                             mode="lines", line=dict(width=0),
                             showlegend=False, hoverinfo="skip"))
    # Rate line + fill
    fig.add_trace(go.Scatter(
        x=df_chart["timestamp"], y=df_chart["rate"],
        mode="lines", name="USD/INR", fill="tonexty",
        fillcolor="rgba(37,99,235,0.09)",
        line=dict(color="#1D4ED8", width=2.5, shape="spline", smoothing=1.2),
        hovertemplate=(
            "<b>%{y:.4f}</b> INR/USD"
            "<br><span style='color:#9CA3AF'>%{x|%b %d · %H:%M MT}</span>"
            "<extra></extra>"
        ),
    ))

    # Uncertainty band
    fig.add_trace(go.Scatter(x=_fx, y=_fhi, mode="lines",
                             line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=_fx, y=_flo, mode="lines", name="Uncertainty",
        fill="tonexty", fillcolor="rgba(249,115,22,0.11)",
        line=dict(width=0), hoverinfo="skip",
    ))

    # Forecast line
    fig.add_trace(go.Scatter(
        x=_fx, y=_fy, mode="lines+markers",
        name=f"Forecast ({ind.model_used})",
        line=dict(color="#F97316", width=2, dash="dot"),
        marker=dict(size=9, color="#F97316", line=dict(color="white", width=2)),
        hovertemplate=(
            "<b>%{y:.4f}</b> (forecast)"
            "<br>Model: " + ind.model_used +
            "<extra></extra>"
        ),
    ))

    # SEND NOW markers from history
    _markers = get_send_now_markers(days=_cutoff_days)
    if not _markers.empty:
        _markers["timestamp"] = pd.to_datetime(_markers["timestamp"], utc=True)
        _df_c_tz = df_chart.copy()
        if _df_c_tz["timestamp"].dt.tz is None:
            _df_c_tz["timestamp"] = _df_c_tz["timestamp"].dt.tz_localize("UTC")
        _merged = pd.merge_asof(
            _markers.sort_values("timestamp"),
            _df_c_tz[["timestamp", "rate"]].sort_values("timestamp"),
            on="timestamp", direction="nearest",
        )
        if not _merged.empty and "rate" in _merged.columns:
            fig.add_trace(go.Scatter(
                x=_merged["timestamp"], y=_merged["rate"],
                mode="markers", name="SEND NOW fired",
                marker=dict(size=13, color="#16A34A", symbol="star",
                            line=dict(color="white", width=1.5)),
                hovertemplate="<b>SEND NOW</b> @ %{y:.4f}<extra></extra>",
            ))

    # Target line
    fig.add_hline(
        y=ind.dynamic_target, line_color="#16A34A",
        line_width=1.5, line_dash="dash",
        annotation_text=f"Target {ind.dynamic_target:.2f}",
        annotation_font=dict(size=11, color="#16A34A"),
        annotation_position="top right",
        annotation_bgcolor="rgba(255,255,255,0.85)",
        annotation_borderpad=3,
    )
    # Minimum floor line (red dashed)
    if ind.minimum_target is not None:
        fig.add_hline(
            y=ind.minimum_target, line_color="#DC2626",
            line_width=1.5, line_dash="dash",
            annotation_text=f"Floor {ind.minimum_target:.2f}",
            annotation_font=dict(size=11, color="#DC2626"),
            annotation_position="bottom right",
            annotation_bgcolor="rgba(255,255,255,0.85)",
            annotation_borderpad=3,
        )

    # Now dot
    fig.add_trace(go.Scatter(
        x=[_last_ts], y=[ind.current_rate],
        mode="markers", name="Now",
        marker=dict(size=10, color="#1D4ED8", line=dict(color="white", width=2.5)),
        hovertemplate="<b>Now: %{y:.4f}</b><extra></extra>",
    ))

    _dtick = 3600000 * (6 if window == "24h" else 12 if window == "72h" else 24)
    fig.update_layout(
        height=400, margin=dict(l=0, r=10, t=4, b=0),
        plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        hovermode="x unified",
        hoverlabel=dict(bgcolor="white", bordercolor="#E5E7EB",
                        font=dict(size=12, color="#111827")),
        legend=dict(orientation="h", y=1.06, x=0, bgcolor="rgba(0,0,0,0)",
                    font=dict(size=11, color="#374151"), itemwidth=30),
        xaxis=dict(
            showgrid=False, showline=False, zeroline=False,
            tickfont=dict(size=10, color="#9CA3AF"),
            tickformat="%H:%M\n%b %d" if window != "7d" else "%b %d",
            dtick=_dtick,
            rangeslider=dict(visible=False),
        ),
        yaxis=dict(
            range=[_y_min, _y_max], showgrid=True, gridcolor="#F3F4F6",
            tickfont=dict(size=10, color="#9CA3AF"), tickformat=".2f",
            showline=False, zeroline=False, side="right",
        ),
    )
    st.plotly_chart(fig, use_container_width=True, config={
        "displayModeBar": True, "displaylogo": False,
        "modeBarButtonsToRemove": [
            "zoom2d", "pan2d", "select2d", "lasso2d", "zoomIn2d", "zoomOut2d",
            "autoScale2d", "hoverClosestCartesian", "hoverCompareCartesian", "toggleSpikelines",
        ],
        "modeBarButtonsToAdd": ["resetScale2d"],
        "toImageButtonOptions": {"format": "png", "filename": "usdinr_chart",
                                 "height": 500, "width": 1200, "scale": 2},
    })

st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📊 Signal", "🔮 Forecast", "🤖 Models", "📈 Accuracy", "⚙️ Settings"]
)

# ═══════════════════════════════
# TAB 1 — Dashboard
# ═══════════════════════════════
with tab1:

    with st.expander("🔍 Why this signal?", expanded=True):
        _rsi_c   = 35 if ind.rsi_14 >= 70 else (15 if ind.rsi_14 >= 60 else 0)
        _bb_c    = 35 if ind.bb_pct >= 1.0 else (15 if ind.bb_pct >= 0.8 else 0)
        _trend_c = 30 if ind.trend_label == "falling" else (15 if ind.trend_label == "sideways" else 0)

        for _lbl, _val, _contrib, _max, _desc in [
            ("RSI (Momentum)",
             f"{ind.rsi_14:.0f} / 100", _rsi_c, 35,
             "≥70 overbought → +35 pts · 60–70 elevated → +15 pts · <60 neutral"),
            ("Bollinger Band",
             f"{ind.bb_pct*100:.0f}%", _bb_c, 35,
             "≥100% above upper band → +35 pts · 80–100% near upper → +15 pts"),
            ("Trend",
             ind.trend_label.capitalize(), _trend_c, 30,
             "Falling → +30 pts · Sideways → +15 pts · Rising → 0 pts"),
        ]:
            _bar_w  = int(_contrib / _max * 100) if _max else 0
            _color  = "#16A34A" if _contrib > 0 else "#E5E7EB"
            _pts_c  = "#16A34A" if _contrib > 0 else "#9CA3AF"
            st.markdown(
                f'<div class="kv-row" style="flex-direction:column;gap:3px;padding:0.6rem 0">'
                f'<div style="display:flex;justify-content:space-between;width:100%">'
                f'<span class="kv-key">{_lbl}</span>'
                f'<span class="kv-val">{_val} &nbsp;'
                f'<span style="color:{_pts_c};font-size:0.77rem;font-weight:500">+{_contrib} pts</span>'
                f'</span></div>'
                f'<div class="contrib-bar-wrap">'
                f'<div class="contrib-bar" style="width:{_bar_w}%;background:{_color}"></div></div>'
                f'<div style="font-size:0.71rem;color:#9CA3AF">{_desc}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        _gate = getattr(config, "SIGNAL_STRENGTH_GATE", 35)
        _at_target = ind.current_rate >= ind.dynamic_target
        _strong    = ind.signal_strength >= _gate
        _status_c  = "#15803D" if (_at_target and _strong) else "#92400E"
        _status_t  = (f"🟢 SEND NOW conditions met (rate ≥ target + signal ≥ {_gate})"
                      if _at_target and _strong else
                      f"🟡 Need: {'✓ rate ≥ target' if _at_target else '✗ rate below target'}"
                      f"  +  {'✓ signal ≥ ' + str(_gate) if _strong else '✗ signal < ' + str(_gate)}")
        st.markdown(
            f'<div style="margin-top:0.4rem;padding:0.5rem 0.75rem;background:#F8FAFC;'
            f'border-radius:6px;font-size:0.82rem;color:{_status_c}">'
            f'<strong>Total: {ind.signal_strength}/100</strong> — {_status_t}'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.divider()
    _t1a, _t1b = st.columns(2)

    with _t1a:
        st.markdown('<div class="section-title">Key Levels</div>', unsafe_allow_html=True)
        _bb_lbl = ("Above upper band" if ind.bb_pct >= 1.0 else
                   f"{ind.bb_pct*100:.0f}% near upper" if ind.bb_pct >= 0.8 else
                   f"{ind.bb_pct*100:.0f}% mid range" if ind.bb_pct >= 0.5 else
                   f"{ind.bb_pct*100:.0f}% near lower")
        for _l, _v in [
            ("Current Rate",    f"{ind.current_rate:.4f}"),
            ("Target",          f"{ind.dynamic_target:.2f}  ({'manual' if get_manual_target() else 'auto · 85th pct 72h'})"),
            ("24h Average",     f"{ind.ma_24h:.4f}"),
            ("48h Average",     f"{ind.ma_48h:.4f}"),
            ("Bollinger Upper", f"{ind.bb_upper:.4f}"),
            ("Bollinger Lower", f"{ind.bb_lower:.4f}"),
            ("Bollinger Pos",   _bb_lbl),
            ("Forecast 24h",    f"{ind.predicted_24h:.4f}  ±{ind.forecast_uncertainty:.4f}"),
            ("Forecast 48h",    f"{ind.predicted_48h:.4f}"),
        ]:
            st.markdown(
                f'<div class="kv-row"><span class="kv-key">{_l}</span>'
                f'<span class="kv-val">{_v}</span></div>',
                unsafe_allow_html=True,
            )

    with _t1b:
        st.markdown('<div class="section-title">Missed Opportunities · Last 7 Days</div>',
                    unsafe_allow_html=True)
        if not df_7d.empty:
            _bi = df_7d["rate"].idxmax()
            _wi = df_7d["rate"].idxmin()
            _br = df_7d.loc[_bi, "rate"]
            _wr = df_7d.loc[_wi, "rate"]
            _bt = pd.to_datetime(df_7d.loc[_bi, "timestamp"]).strftime("%b %d · %H:%M")
            _wt = pd.to_datetime(df_7d.loc[_wi, "timestamp"]).strftime("%b %d · %H:%M")
            _dk = (_br - _wr) * 1000
            for _l, _v in [
                ("Best rate (7d)",       f"{_br:.4f}  @ {_bt}"),
                ("Worst rate (7d)",      f"{_wr:.4f}  @ {_wt}"),
                ("7-day range",          f"{_br - _wr:.4f}"),
                ("Per $1,000 swing",     f"₹{_dk:,.0f} best vs worst"),
                ("Current vs best",      f"{ind.current_rate - _br:+.4f}"),
                ("Current vs worst",     f"{ind.current_rate - _wr:+.4f} above floor"),
            ]:
                st.markdown(
                    f'<div class="kv-row"><span class="kv-key">{_l}</span>'
                    f'<span class="kv-val">{_v}</span></div>',
                    unsafe_allow_html=True,
                )

        st.divider()
        st.markdown('<div class="section-title">Ask the Advisor</div>', unsafe_allow_html=True)
        QUESTIONS = {
            "q1": ("Send in an hour?", send_in_one_hour),
            "q2": ("Send tomorrow?",   send_tomorrow),
            "q3": ("Best time?",       best_time_to_send),
        }
        _bcols = st.columns(3)
        for _i, (_key, (_lbl, _fn)) in enumerate(QUESTIONS.items()):
            with _bcols[_i]:
                if st.button(_lbl, use_container_width=True, key=f"t1btn_{_key}"):
                    _v, _da, _ta = _fn(ind)
                    st.session_state[f"answer_{_key}"] = (_v, _da, _ta)
                    for _o in QUESTIONS:
                        if _o != _key:
                            st.session_state[f"answer_{_o}"] = None
        for _key in QUESTIONS:
            _res = st.session_state.get(f"answer_{_key}")
            if _res:
                _v, _da, _ta = _res
                _bg, _bd, _tc = VERDICT_STYLE.get(_v, ("#F9FAFB", "#9CA3AF", "#374151"))
                st.markdown(
                    f'<div style="background:{_bg};border-left:4px solid {_bd};'
                    f'border-radius:8px;padding:0.85rem 1.1rem;margin-top:0.6rem">'
                    f'<div style="color:{_tc};font-size:0.875rem;line-height:1.65">{_da}</div>'
                    f'</div>', unsafe_allow_html=True,
                )
                if st.button("📲 Send to Telegram", key=f"t1tg_{_key}",
                             disabled=not st.session_state["user_chat_id"].strip()):
                    _s = send_message(_ta, chat_id=st.session_state["user_chat_id"].strip())
                    st.toast("Sent!" if _s else "Failed", icon="📲" if _s else "⚠️")
                break

# ═══════════════════════════════
# TAB 2 — Forecast
# ═══════════════════════════════
with tab2:
    st.markdown('<div class="section-title">Time-Horizon Selector</div>', unsafe_allow_html=True)
    _hl = st.select_slider(
        "Horizon",
        options=["1h", "6h", "12h", "24h", "2 days", "3 days", "5 days", "7 days"],
        value="24h", label_visibility="collapsed",
    )
    _hh  = {"1h": 1, "6h": 6, "12h": 12, "24h": 24,
             "2 days": 48, "3 days": 72, "5 days": 120, "7 days": 168}[_hl]
    _rh  = forecast_at_hours(_hh)
    _dh  = _rh - ind.current_rate
    _uh  = ind.forecast_uncertainty * (1 + _hh / 48 * 0.3)
    _act = ("SEND NOW"  if _rh >= ind.dynamic_target and ind.signal_strength >= getattr(config, "SIGNAL_STRENGTH_GATE", 35)
            else "MONITOR" if _rh >= ind.dynamic_target - 0.5
            else "WAIT")
    _ac  = {"SEND NOW": "#16A34A", "MONITOR": "#D97706", "WAIT": "#6B7280"}[_act]

    _hc1, _hc2, _hc3 = st.columns(3)
    _hc1.metric(f"Rate in {_hl}", f"{_rh:.4f}", f"{_dh:+.4f} vs now", delta_color="normal")
    _hc2.metric("Uncertainty", f"±{_uh:.4f}", "Grows with horizon")
    _hc3.metric("Projected Signal", _act, f"vs target {ind.dynamic_target:.2f}")

    _dir = "higher" if _dh > 0 else "lower"
    st.markdown(
        f'<div style="padding:0.7rem 1rem;background:#F8FAFC;border-radius:8px;'
        f'font-size:0.875rem;color:#374151;margin:0.6rem 0">'
        f'In <strong>{_hl}</strong>, rate forecast at <strong>{_rh:.4f}</strong> — '
        f'{abs(_dh):.4f} {_dir} than now (±{_uh:.4f}). '
        f'Projected: <strong style="color:{_ac}">{_act}</strong>.'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.divider()
    st.markdown('<div class="section-title">Scenario Simulator</div>', unsafe_allow_html=True)
    _sa1, _sa2 = st.columns([1, 2])
    with _sa1:
        _sim = st.number_input("USD to send", min_value=1.0, max_value=500000.0,
                               value=1000.0, step=100.0, format="%.0f")
    with _sa2:
        _inr_n = _sim * ind.current_rate
        _inr_h = _sim * _rh
        _inr_t = _sim * ind.dynamic_target
        _wg    = _inr_h - _inr_n
        _tg    = _inr_t - _inr_n
        _wc    = "#16A34A" if _wg >= 0 else "#DC2626"
        _tc    = "#16A34A" if _tg >= 0 else "#DC2626"
        _sc1, _sc2, _sc3 = st.columns(3)
        _sc1.markdown(
            f'<div class="impact-box"><div class="impact-number">₹{_inr_n:,.0f}</div>'
            f'<div class="impact-label">Send <b>now</b> @ {ind.current_rate:.4f}</div></div>',
            unsafe_allow_html=True)
        _sc2.markdown(
            f'<div class="impact-box"><div class="impact-number">₹{_inr_h:,.0f}</div>'
            f'<div class="impact-label">In <b>{_hl}</b> &nbsp;'
            f'<span style="color:{_wc};font-weight:700">{"+" if _wg >= 0 else ""}₹{abs(_wg):,.0f}</span>'
            f'</div></div>', unsafe_allow_html=True)
        _sc3.markdown(
            f'<div class="impact-box"><div class="impact-number">₹{_inr_t:,.0f}</div>'
            f'<div class="impact-label">At <b>target</b> {ind.dynamic_target:.2f} &nbsp;'
            f'<span style="color:{_tc};font-weight:700">{"+" if _tg >= 0 else ""}₹{abs(_tg):,.0f}</span>'
            f'</div></div>', unsafe_allow_html=True)

    # Horizon forecast curve
    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
    _hrs  = list(range(0, max(_hh + 1, 49)))
    _rats = [forecast_at_hours(h) for h in _hrs]
    _uncs = [ind.forecast_uncertainty * (1 + h / 48 * 0.3) for h in _hrs]

    _figh = go.Figure()
    _figh.add_trace(go.Scatter(x=_hrs, y=[r + u for r, u in zip(_rats, _uncs)],
                               mode="lines", line=dict(width=0),
                               showlegend=False, hoverinfo="skip"))
    _figh.add_trace(go.Scatter(x=_hrs, y=[r - u for r, u in zip(_rats, _uncs)],
                               fill="tonexty", fillcolor="rgba(249,115,22,0.1)",
                               mode="lines", line=dict(width=0),
                               name="±uncertainty", hoverinfo="skip"))
    _figh.add_trace(go.Scatter(x=_hrs, y=_rats, mode="lines",
                               name="Forecast", line=dict(color="#F97316", width=2),
                               hovertemplate="<b>%{y:.4f}</b> @ %{x}h<extra></extra>"))
    _figh.add_hline(y=ind.dynamic_target, line_color="#16A34A", line_dash="dash", line_width=1.5,
                    annotation_text=f"Target {ind.dynamic_target:.2f}",
                    annotation_font=dict(size=11, color="#16A34A"),
                    annotation_position="top right")
    _figh.add_vline(x=_hh, line_color="#6B7280", line_dash="dot", line_width=1.5)
    _figh.update_layout(
        height=250, margin=dict(l=0, r=0, t=4, b=0),
        plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        hovermode="x unified",
        xaxis=dict(title="Hours from now", showgrid=False,
                   tickfont=dict(size=10, color="#9CA3AF")),
        yaxis=dict(showgrid=True, gridcolor="#F3F4F6", tickformat=".2f",
                   tickfont=dict(size=10, color="#9CA3AF"), side="right"),
        legend=dict(orientation="h", y=1.08, x=0, font=dict(size=11)),
    )
    st.plotly_chart(_figh, use_container_width=True, config={"displayModeBar": False})

# ═══════════════════════════════
# TAB 3 — Models
# ═══════════════════════════════
with tab3:
    st.markdown('<div class="section-title">6-Model Competition · 24h Holdout Error (lower = better)</div>',
                unsafe_allow_html=True)
    MODEL_LABELS = {
        "Linear":      "Linear Regression",
        "GBM":         "Gradient Boosting",
        "ExpSmooth":   "Exp Smoothing",
        "PPP":         "Purchasing Power Parity",
        "RelStrength": "Relative Econ Strength",
        "ARIMA":       "ARIMA (Econometric)",
    }
    if ind.model_scores:
        _valid  = {k: v for k, v in ind.model_scores.items() if v < 999}
        _colors = ["#16A34A" if k == ind.model_used else "#93C5FD" for k in _valid]

        _figm = go.Figure(go.Bar(
            x=list(_valid.values()),
            y=[MODEL_LABELS.get(k, k) for k in _valid],
            orientation="h",
            marker_color=_colors,
            text=[f"{v:.4f}" for v in _valid.values()],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Error: %{x:.4f}<extra></extra>",
        ))
        _figm.update_layout(
            height=270, margin=dict(l=0, r=70, t=4, b=0),
            plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
            xaxis=dict(title="Absolute Error (24h holdout)", showgrid=True,
                       gridcolor="#F3F4F6", tickformat=".3f",
                       tickfont=dict(size=10, color="#9CA3AF")),
            yaxis=dict(showgrid=False, tickfont=dict(size=11, color="#374151"),
                       autorange="reversed"),
            showlegend=False,
        )
        st.plotly_chart(_figm, use_container_width=True, config={"displayModeBar": False})

        st.markdown(
            f'<div style="padding:0.6rem 1rem;background:#F0FDF4;border-radius:6px;'
            f'font-size:0.85rem;color:#15803D;margin-bottom:0.75rem">'
            f'✓ Active: <strong>{MODEL_LABELS.get(ind.model_used, ind.model_used)}</strong>'
            f' — 24h: <strong>{ind.predicted_24h:.4f}</strong>'
            f' · 48h: <strong>{ind.predicted_48h:.4f}</strong>'
            f' · uncertainty: ±{ind.forecast_uncertainty:.4f}'
            f'</div>', unsafe_allow_html=True,
        )
        for _mk, _ml in MODEL_LABELS.items():
            _err = ind.model_scores.get(_mk)
            if _err is None or _err >= 999:
                continue
            _iw    = _mk == ind.model_used
            _worst = max(_valid.values())
            _bp    = max(5, min(100, int((1 - _err / _worst) * 100)))
            _bc    = "#16A34A" if _iw else "#93C5FD"
            _bar   = f"<div style='background:{_bc};height:5px;border-radius:3px;width:{_bp}%;margin-top:2px'></div>"
            st.markdown(
                f'<div class="kv-row" style="flex-direction:column;gap:2px">'
                f'<div style="display:flex;justify-content:space-between;width:100%">'
                f'<span class="kv-key">{_ml}</span>'
                f'<span class="kv-val" style="color:{"#15803D" if _iw else "#374151"}">'
                f'{_err:.4f}{"  ✓ Active" if _iw else ""}</span></div>{_bar}</div>',
                unsafe_allow_html=True,
            )
    else:
        st.caption("Model comparison available after 100+ data points.")

    st.divider()
    with st.expander("What does each model do?", expanded=False):
        st.markdown("""
| Model | Approach |
|---|---|
| **Linear Regression** | Straight-line trend through last 7 days of rates |
| **Gradient Boosting** | Lag features (1h–168h) + rolling momentum, ML-trained |
| **Exp Smoothing** | Holt-Winters with trend dampening — weighs recent data more |
| **ARIMA(1,1,1)** | Differenced autoregressive + moving-average econometric model |
| **Purchasing Power Parity** | Drift from India vs US inflation differential |
| **Relative Econ Strength** | Drift from RBI repo vs Fed funds rate differential |

The model with the lowest 24h holdout error **wins automatically** each run.
Economic parameters (interest rates, inflation) can be updated in `config.py`.
""")

# ═══════════════════════════════
# TAB 4 — Accuracy
# ═══════════════════════════════
with tab4:
    if acc is None:
        st.info("Not enough scored predictions yet. Check back in 24–48 hours.")
    else:
        _, _a1, _a2, _a3, _ = st.columns([0.5, 2, 2, 2, 0.5])
        _a1.metric("24h Forecast Error", f"±{acc.mae_24h:.4f}",
                   help="Mean absolute error for 24h forecasts vs actual rates")
        _a2.metric("48h Forecast Error", f"±{acc.mae_48h:.4f}",
                   help="Mean absolute error for 48h forecasts vs actual rates")
        _a3.metric("Within ±0.5  (24h)", f"{acc.within_half_24h:.0f}%",
                   help="% of 24h predictions within ±0.5 of actual rate")

        _mc  = max(0, min(100, int((1 - acc.mae_24h / 0.5) * 100))) if acc.mae_24h > 0 else 50
        st.markdown(
            f'<div style="padding:0.6rem 1rem;background:#F8FAFC;border-radius:6px;'
            f'font-size:0.84rem;color:#374151;margin:0.6rem 0">'
            f'Model accuracy score: <strong>{_mc}%</strong>'
            f' · Signal strength: <strong>{ind.signal_strength}/100</strong>'
            f' · Combined confidence: <strong>{confidence}%</strong>'
            f'</div>', unsafe_allow_html=True,
        )

        if not acc.df_chart.empty:
            st.markdown("<div style='height:0.25rem'></div>", unsafe_allow_html=True)
            st.markdown('<div class="section-title">Predicted vs Actual — Last 50 Scored Predictions (24h)</div>',
                        unsafe_allow_html=True)
            _figa = go.Figure()
            # ±0.5 band
            _figa.add_trace(go.Scatter(
                x=pd.concat([acc.df_chart["Time"], acc.df_chart["Time"][::-1]]).tolist(),
                y=(acc.df_chart["Predicted"] + 0.5).tolist() +
                  (acc.df_chart["Predicted"] - 0.5).iloc[::-1].tolist(),
                fill="toself", fillcolor="rgba(249,115,22,0.08)",
                line=dict(width=0), showlegend=True, name="±0.5 band", hoverinfo="skip",
            ))
            _figa.add_trace(go.Scatter(
                x=acc.df_chart["Time"], y=acc.df_chart["Actual"],
                mode="lines", name="Actual", line=dict(color="#2563EB", width=2)))
            _figa.add_trace(go.Scatter(
                x=acc.df_chart["Time"], y=acc.df_chart["Predicted"],
                mode="lines", name="Predicted", line=dict(color="#F97316", width=1.5, dash="dot")))
            _figa.update_layout(
                height=290, margin=dict(l=0, r=0, t=4, b=0),
                plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
                hovermode="x unified",
                legend=dict(orientation="h", y=1.08, x=0, bgcolor="rgba(0,0,0,0)",
                            font=dict(size=11, color="#374151")),
                xaxis=dict(showgrid=False, tickformat="%b %d",
                           tickfont=dict(size=10, color="#9CA3AF"), showline=False),
                yaxis=dict(showgrid=True, gridcolor="#F3F4F6", tickformat=".2f",
                           tickfont=dict(size=10, color="#9CA3AF"), showline=False),
            )
            st.plotly_chart(_figa, use_container_width=True, config={"displayModeBar": False})

            # Recent trend assessment
            _rec = acc.df_chart.tail(10).copy()
            _rec["error"] = (_rec["Predicted"] - _rec["Actual"]).abs()
            _tr_mae = _rec["error"].mean()
            _trend_str = ("improving" if _tr_mae < acc.mae_24h * 0.9 else
                          "stable"    if _tr_mae < acc.mae_24h * 1.1 else "degrading")
            _trend_c = {"improving": "#16A34A", "stable": "#D97706", "degrading": "#DC2626"}[_trend_str]
            st.markdown(
                f'<div style="padding:0.6rem 1rem;background:#F8FAFC;border-radius:6px;'
                f'font-size:0.84rem;color:#374151">'
                f'Recent 10-prediction MAE: <strong>{_tr_mae:.4f}</strong>'
                f' · Overall MAE: <strong>{acc.mae_24h:.4f}</strong>'
                f' · Trend: <strong style="color:{_trend_c}">{_trend_str}</strong>'
                f'</div>', unsafe_allow_html=True,
            )

# ═══════════════════════════════
# TAB 5 — Settings
# ═══════════════════════════════
with tab5:
    _stored     = get_manual_target()
    _stored_min = get_minimum_target()

    # ── Target Rate card ──────────────────────────────────────────────────────
    st.markdown(
        '<div class="settings-card">'
        '<div class="settings-card-title">🎯 Target Rate</div>',
        unsafe_allow_html=True,
    )
    _mode_badge = (
        f'<span style="background:#DBEAFE;color:#1D4ED8;font-size:0.72rem;'
        f'font-weight:700;padding:2px 8px;border-radius:20px">MANUAL · {_stored:.2f}</span>'
        if _stored else
        f'<span style="background:#F3F4F6;color:#6B7280;font-size:0.72rem;'
        f'font-weight:700;padding:2px 8px;border-radius:20px">AUTO · {config.TARGET_PERCENTILE}th pct 72h</span>'
    )
    st.markdown(
        f'<div style="margin-bottom:0.75rem">Currently active: {_mode_badge}</div>',
        unsafe_allow_html=True,
    )
    st.markdown('</div>', unsafe_allow_html=True)

    _ts1, _ts2, _ts3 = st.columns([3, 1, 1])
    with _ts1:
        _new_t = st.number_input("Set target rate (INR/USD)", min_value=70.0, max_value=120.0,
                                 value=float(_stored) if _stored else 93.0,
                                 step=0.05, format="%.2f", label_visibility="visible")
    with _ts2:
        st.markdown("<div style='height:1.85rem'></div>", unsafe_allow_html=True)
        if st.button("💾 Save", use_container_width=True, type="primary"):
            set_manual_target(_new_t)
            st.toast(f"Target set to {_new_t:.2f}", icon="🎯")
            st.rerun()
    with _ts3:
        st.markdown("<div style='height:1.85rem'></div>", unsafe_allow_html=True)
        if _stored:
            if st.button("↩ Auto", use_container_width=True):
                set_manual_target(None)
                st.toast(f"Reverted to auto ({config.TARGET_PERCENTILE}th pct 72h)", icon="↩️")
                st.rerun()

    st.divider()

    # ── Minimum Floor card ────────────────────────────────────────────────────
    st.markdown(
        '<div class="settings-card">'
        '<div class="settings-card-title">🛡️ Minimum Floor Rate</div>',
        unsafe_allow_html=True,
    )
    _floor_badge = (
        f'<span style="background:#FEE2E2;color:#DC2626;font-size:0.72rem;'
        f'font-weight:700;padding:2px 8px;border-radius:20px">FLOOR · {_stored_min:.2f}</span>'
        if _stored_min else
        '<span style="background:#F3F4F6;color:#6B7280;font-size:0.72rem;'
        'font-weight:700;padding:2px 8px;border-radius:20px">NOT SET</span>'
    )
    st.markdown(
        f'<div style="margin-bottom:0.75rem">Status: {_floor_badge}</div>'
        f'<div style="font-size:0.83rem;color:#374151;margin-bottom:0.75rem">'
        f'Set a floor rate you\'re willing to accept. If the rate falls <strong>to or below</strong> '
        f'this level, you\'ll get an immediate <strong>SEND NOW</strong> alert — '
        f'lock it in before it falls further.'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown('</div>', unsafe_allow_html=True)

    _fs1, _fs2, _fs3 = st.columns([3, 1, 1])
    with _fs1:
        _new_floor = st.number_input("Set minimum floor rate (INR/USD)", min_value=70.0, max_value=120.0,
                                     value=float(_stored_min) if _stored_min else round(ind.current_rate - 0.5, 2),
                                     step=0.05, format="%.2f", label_visibility="visible")
    with _fs2:
        st.markdown("<div style='height:1.85rem'></div>", unsafe_allow_html=True)
        if st.button("💾 Save Floor", use_container_width=True, type="primary", key="save_floor"):
            set_minimum_target(_new_floor)
            st.toast(f"Floor set to {_new_floor:.2f}", icon="🛡️")
            st.rerun()
    with _fs3:
        st.markdown("<div style='height:1.85rem'></div>", unsafe_allow_html=True)
        if _stored_min:
            if st.button("✕ Clear", use_container_width=True, key="clear_floor"):
                set_minimum_target(None)
                st.toast("Minimum floor cleared", icon="✕")
                st.rerun()

    st.divider()

    # ── Telegram Alerts card ──────────────────────────────────────────────────
    st.markdown(
        '<div class="settings-card">'
        '<div class="settings-card-title">📲 Telegram Alerts</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        "**Step 1:** Search **@Rajam009bot** on Telegram → send it `hi` (activates the bot)\n\n"
        "**Step 2:** Message [@userinfobot](https://t.me/userinfobot) → it replies with your Chat ID\n\n"
        "**Step 3:** Paste your Chat ID below — Send buttons across the dashboard become active"
    )
    st.markdown('</div>', unsafe_allow_html=True)

    _cid = st.text_input("Your Telegram Chat ID", value=st.session_state["user_chat_id"],
                          placeholder="e.g. 123456789")
    if _cid != st.session_state["user_chat_id"]:
        st.session_state["user_chat_id"] = _cid
    if _cid.strip():
        st.success("✅ Ready — all Send buttons across the dashboard are now active.")
        if st.button("📲 Send a test alert now", use_container_width=False):
            _s = send_message(format_message(dec, ind), chat_id=_cid.strip())
            st.toast("Sent!" if _s else "Failed — did you message the bot first?",
                     icon="📲" if _s else "⚠️")
    else:
        st.caption("Chat ID is stored only in your browser session — never saved to the database.")

    st.divider()

    # ── About cards ───────────────────────────────────────────────────────────
    _ab1, _ab2 = st.columns(2)
    with _ab1:
        with st.expander("🍴 Want your own alerts?", expanded=False):
            st.markdown(
                "This app is open source. "
                "[Fork the repo on GitHub](https://github.com/rajamadabattula/exchange-rate-predictor) "
                "→ set up your own Telegram bot (~5 min) → host free on "
                "[Streamlit Cloud](https://streamlit.io/cloud). "
                "You'll get SEND NOW alerts directly to your phone."
            )
    with _ab2:
        with st.expander("💡 Why this was built", expanded=False):
            st.markdown(
                "I came from India to the US for my Master's degree. Every month I faced the same "
                "question: *when do I send money?*\n\n"
                "A week before building this, I sent at a rate **₹3/dollar lower** than it became "
                "days later — thousands of rupees lost. So I built this instead of guessing."
            )

# ── Footer ─────────────────────────────────────────────────────────────────────

st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
st.markdown(
    f"<div style='font-size:0.72rem;color:#D1D5DB;text-align:center;"
    f"padding-top:0.75rem;border-top:1px solid #F3F4F6'>"
    f"Updated {datetime.now(timezone.utc).strftime('%d %b %Y · %H:%M UTC')}"
    f" &nbsp;·&nbsp; Not financial advice &nbsp;·&nbsp; "
    f"<a href='https://github.com/rajamadabattula/exchange-rate-predictor' "
    f"style='color:#9CA3AF;text-decoration:none'>GitHub</a>"
    f"</div>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div style='margin-top:0.5rem;padding:0.7rem 1rem;background:#FEF9C3;"
    "border:1px solid #EAB308;border-radius:8px;font-size:0.77rem;color:#78350F;text-align:center'>"
    "⚠️ Mid-market rates from Google Finance. Forecasts are trend-based only — cannot predict "
    "macro events, news, or policy changes. Always verify on your transfer service before sending."
    "</div>",
    unsafe_allow_html=True,
)
