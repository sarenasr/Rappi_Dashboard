import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta
import os
from google import genai
from google.genai import types

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG & BRANDING
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Rappi · Store Availability Monitor",
    page_icon="🟠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Rappi brand palette */
    :root {
        --rappi-orange: #FF441F;
        --rappi-dark: #1A1A2E;
        --rappi-light: #F8F9FA;
        --rappi-green: #00C853;
        --rappi-red: #FF1744;
        --rappi-yellow: #FFD600;
    }

    /* Header bar */
    .rappi-header {
        background: linear-gradient(135deg, #FF441F 0%, #FF6B3D 100%);
        padding: 1.2rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .rappi-header h1 {
        color: white;
        margin: 0;
        font-size: 1.8rem;
        font-weight: 700;
        letter-spacing: -0.5px;
    }
    .rappi-header p {
        color: rgba(255,255,255,0.85);
        margin: 0;
        font-size: 0.95rem;
    }

    /* KPI cards */
    .kpi-card {
        background: white;
        border-radius: 12px;
        padding: 1.2rem 1.4rem;
        box-shadow: 0 1px 6px rgba(0,0,0,0.07);
        border-left: 4px solid var(--rappi-orange);
        height: 100%;
    }
    .kpi-card .kpi-label {
        font-size: 0.78rem;
        color: #6B7280;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        font-weight: 600;
        margin-bottom: 0.3rem;
    }
    .kpi-card .kpi-value {
        font-size: 1.75rem;
        font-weight: 700;
        color: #1A1A2E;
        line-height: 1.2;
    }
    .kpi-card .kpi-delta {
        font-size: 0.82rem;
        margin-top: 0.2rem;
    }
    .kpi-delta.positive { color: #00C853; }
    .kpi-delta.negative { color: #FF1744; }

    /* Section titles */
    .section-title {
        font-size: 1.1rem;
        font-weight: 700;
        color: #1A1A2E;
        margin: 1.5rem 0 0.8rem 0;
        padding-bottom: 0.4rem;
        border-bottom: 2px solid #FF441F;
        display: inline-block;
    }

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: #1A1A2E;
    }
    [data-testid="stSidebar"] * {
        color: white !important;
    }
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stMultiSelect label,
    [data-testid="stSidebar"] .stSlider label,
    [data-testid="stSidebar"] .stDateInput label,
    [data-testid="stSidebar"] .stRadio label {
        color: rgba(255,255,255,0.9) !important;
        font-weight: 600;
    }

    /* Chat placeholder */
    .chat-container {
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 1px 6px rgba(0,0,0,0.07);
        border: 2px dashed #FF441F;
    }
    .chat-container h4 {
        color: #FF441F;
        margin-top: 0;
    }

    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Plotly chart container */
    .stPlotlyChart {
        border-radius: 12px;
        overflow: hidden;
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=600)
def load_data(path: str) -> pd.DataFrame:
    """Load and enrich the base availability dataset."""
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], utc=True).dt.tz_convert("America/Bogota")
    df.sort_values("time", inplace=True)
    df.reset_index(drop=True, inplace=True)

    # Derived columns
    df["date"] = df["time"].dt.date
    df["hour"] = df["time"].dt.hour
    df["minute"] = df["time"].dt.minute
    df["day_of_week"] = df["time"].dt.day_name()
    df["day_num"] = df["time"].dt.dayofweek  # 0=Mon ... 6=Sun
    df["is_weekend"] = df["day_num"].isin([5, 6])

    # Rate of change (per‑minute delta smoothed)
    df["stores_delta"] = df["available_stores"].diff()
    df["stores_pct_change"] = df["available_stores"].pct_change() * 100

    return df


DATA_PATH = os.path.join(os.path.dirname(__file__), "Base_Unificada.csv")
df_raw = load_data(DATA_PATH)

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — USER CONTROLS
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🟠 Rappi Controls")
    st.markdown("---")

    # Date range
    min_date = df_raw["date"].min()
    max_date = df_raw["date"].max()
    st.markdown("#### 📅 Date Range")
    date_range = st.date_input(
        "Select period",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        key="date_range",
    )

    st.markdown("---")

    # Hour range
    st.markdown("#### 🕐 Hour Window")
    hour_range = st.slider(
        "Operating hours",
        min_value=0,
        max_value=23,
        value=(6, 23),
        key="hour_range",
    )

    st.markdown("---")

    # Resampling frequency
    st.markdown("#### 📊 Granularity")
    resample_map = {
        "10 seconds (raw)": None,
        "1 minute": "1min",
        "5 minutes": "5min",
        "15 minutes": "15min",
        "30 minutes": "30min",
        "1 hour": "1h",
    }
    resample_label = st.selectbox(
        "Resampling frequency",
        list(resample_map.keys()),
        index=2,
        key="resample_freq",
    )
    resample_freq = resample_map[resample_label]

    st.markdown("---")

    # Day of week filter
    st.markdown("#### 📆 Day of Week")
    all_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    selected_days = st.multiselect(
        "Filter days",
        all_days,
        default=all_days,
        key="dow_filter",
    )

    st.markdown("---")

    # Weekend / Weekday toggle
    st.markdown("#### 🔀 Comparison Mode")
    comparison_mode = st.radio(
        "Compare by",
        ["None", "Weekday vs Weekend", "Day‑over‑Day"],
        index=0,
        key="comparison_mode",
    )

    st.markdown("---")

    # Anomaly sensitivity
    st.markdown("#### ⚠️ Anomaly Detection")
    anomaly_sigma = st.slider(
        "Sensitivity (σ threshold)",
        min_value=1.0,
        max_value=4.0,
        value=2.5,
        step=0.1,
        key="anomaly_sigma",
        help="Lower = more sensitive (flags more anomalies)",
    )

    st.markdown("---")
    st.caption("Data: Feb 1 – Feb 11, 2026")
    st.caption("Source: Rappi Availability Monitor")


# ─────────────────────────────────────────────────────────────────────────────
# FILTER DATA
# ─────────────────────────────────────────────────────────────────────────────
def filter_data(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all sidebar filters."""
    if isinstance(date_range, tuple) and len(date_range) == 2:
        mask = (df["date"] >= date_range[0]) & (df["date"] <= date_range[1])
    else:
        mask = df["date"] == date_range
    mask &= (df["hour"] >= hour_range[0]) & (df["hour"] <= hour_range[1])
    mask &= df["day_of_week"].isin(selected_days)
    return df[mask].copy()


df = filter_data(df_raw)

if df.empty:
    st.warning("No data matches the selected filters. Adjust the sidebar controls.")
    st.stop()


def resample_data(df: pd.DataFrame, freq: str | None) -> pd.DataFrame:
    """Resample to the chosen granularity."""
    if freq is None:
        return df
    rs = (
        df.set_index("time")["available_stores"]
        .resample(freq)
        .agg(["mean", "min", "max", "std", "count"])
        .dropna(subset=["mean"])
        .reset_index()
    )
    rs.rename(columns={"mean": "available_stores"}, inplace=True)
    rs["available_stores"] = rs["available_stores"].round(0).astype(int)
    rs["date"] = rs["time"].dt.date
    rs["hour"] = rs["time"].dt.hour
    rs["day_of_week"] = rs["time"].dt.day_name()
    rs["day_num"] = rs["time"].dt.dayofweek
    rs["is_weekend"] = rs["day_num"].isin([5, 6])
    return rs


df_plot = resample_data(df, resample_freq)

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="rappi-header">
    <div>
        <h1>🟠 Rappi Store Availability Monitor</h1>
        <p>Real‑time visibility into store availability across the platform</p>
    </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# KPI ROW
# ─────────────────────────────────────────────────────────────────────────────
def fmt(n: float) -> str:
    """Human‑friendly large number formatting."""
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:,.2f}M"
    elif abs(n) >= 1_000:
        return f"{n / 1_000:,.1f}K"
    return f"{n:,.0f}"


latest = df["available_stores"].iloc[-1]
peak = df["available_stores"].max()
avg = df["available_stores"].mean()
minimum = df["available_stores"].min()

# Compare to previous period of same length
period_length = (df["time"].iloc[-1] - df["time"].iloc[0])
prev_mask = (
    (df_raw["time"] >= df["time"].iloc[0] - period_length)
    & (df_raw["time"] < df["time"].iloc[0])
)
df_prev = df_raw[prev_mask]
if not df_prev.empty:
    prev_avg = df_prev["available_stores"].mean()
    delta_pct = ((avg - prev_avg) / prev_avg) * 100 if prev_avg != 0 else 0
else:
    delta_pct = 0

# Stability = coefficient of variation (lower is more stable)
stability = (df["available_stores"].std() / avg * 100) if avg > 0 else 0

col1, col2, col3, col4, col5, col6 = st.columns(6)

with col1:
    delta_class = "positive" if delta_pct >= 0 else "negative"
    delta_arrow = "▲" if delta_pct >= 0 else "▼"
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">Latest Reading</div>
        <div class="kpi-value">{fmt(latest)}</div>
        <div class="kpi-delta {delta_class}">{delta_arrow} {abs(delta_pct):.1f}% vs prev period</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">Peak Stores</div>
        <div class="kpi-value">{fmt(peak)}</div>
        <div class="kpi-delta" style="color:#6B7280;">All‑time high in range</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">Average</div>
        <div class="kpi-value">{fmt(avg)}</div>
        <div class="kpi-delta" style="color:#6B7280;">Mean availability</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">Minimum</div>
        <div class="kpi-value">{fmt(minimum)}</div>
        <div class="kpi-delta" style="color:#FF1744;">Lowest in range</div>
    </div>
    """, unsafe_allow_html=True)

with col5:
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">Stability Index</div>
        <div class="kpi-value">{stability:.1f}%</div>
        <div class="kpi-delta" style="color:#6B7280;">CV (lower = stable)</div>
    </div>
    """, unsafe_allow_html=True)

with col6:
    total_points = len(df)
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-label">Data Points</div>
        <div class="kpi-value">{fmt(total_points)}</div>
        <div class="kpi-delta" style="color:#6B7280;">{resample_label} intervals</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# MAIN TIME SERIES CHART
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">📈 Store Availability Over Time</div>', unsafe_allow_html=True)

fig_ts = go.Figure()

if comparison_mode == "Weekday vs Weekend":
    df_wd = df_plot[~df_plot["is_weekend"]]
    df_we = df_plot[df_plot["is_weekend"]]
    fig_ts.add_trace(go.Scatter(
        x=df_wd["time"], y=df_wd["available_stores"],
        name="Weekday", mode="lines",
        line=dict(color="#FF441F", width=1.5),
        fill="tozeroy", fillcolor="rgba(255,68,31,0.08)",
    ))
    fig_ts.add_trace(go.Scatter(
        x=df_we["time"], y=df_we["available_stores"],
        name="Weekend", mode="lines",
        line=dict(color="#3B82F6", width=1.5),
        fill="tozeroy", fillcolor="rgba(59,130,246,0.08)",
    ))
elif comparison_mode == "Day‑over‑Day":
    colors = px.colors.qualitative.Set2
    for i, (date, grp) in enumerate(df_plot.groupby("date")):
        day_name = grp["day_of_week"].iloc[0] if not grp.empty else ""
        fig_ts.add_trace(go.Scatter(
            x=grp["hour"] + grp["time"].dt.minute / 60,
            y=grp["available_stores"],
            name=f"{date} ({day_name[:3]})",
            mode="lines",
            line=dict(color=colors[i % len(colors)], width=1.5),
        ))
    fig_ts.update_xaxes(title_text="Hour of Day")
else:
    fig_ts.add_trace(go.Scatter(
        x=df_plot["time"], y=df_plot["available_stores"],
        name="Available Stores", mode="lines",
        line=dict(color="#FF441F", width=1.5),
        fill="tozeroy", fillcolor="rgba(255,68,31,0.06)",
    ))
    # Add a rolling average overlay
    if len(df_plot) > 20:
        window = max(6, len(df_plot) // 50)
        df_plot["rolling_avg"] = df_plot["available_stores"].rolling(window, center=True).mean()
        fig_ts.add_trace(go.Scatter(
            x=df_plot["time"], y=df_plot["rolling_avg"],
            name=f"Trend (rolling {window})",
            mode="lines",
            line=dict(color="#1A1A2E", width=2, dash="dot"),
        ))

fig_ts.update_layout(
    template="plotly_white",
    height=420,
    margin=dict(l=0, r=0, t=30, b=0),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    yaxis_title="Available Stores",
    xaxis_title="Time" if comparison_mode != "Day‑over‑Day" else "Hour of Day",
    hovermode="x unified",
)
st.plotly_chart(fig_ts, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# ROW 2 — HEATMAP + DAILY DISTRIBUTION
# ─────────────────────────────────────────────────────────────────────────────
col_left, col_right = st.columns([3, 2])

with col_left:
    st.markdown('<div class="section-title">🌡️ Hourly Availability Heatmap</div>', unsafe_allow_html=True)

    heatmap_data = (
        df.groupby(["date", "hour"])["available_stores"]
        .mean()
        .reset_index()
    )
    pivot = heatmap_data.pivot(index="hour", columns="date", values="available_stores")
    pivot = pivot.sort_index()

    fig_heat = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=[str(d) for d in pivot.columns],
        y=[f"{h:02d}:00" for h in pivot.index],
        colorscale=[
            [0, "#FFF3E0"],
            [0.25, "#FFB74D"],
            [0.5, "#FF8A65"],
            [0.75, "#FF441F"],
            [1, "#B71C1C"],
        ],
        colorbar=dict(title="Stores"),
        hovertemplate="Date: %{x}<br>Hour: %{y}<br>Avg Stores: %{z:,.0f}<extra></extra>",
    ))
    fig_heat.update_layout(
        template="plotly_white",
        height=400,
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis_title="Date",
        yaxis_title="Hour",
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig_heat, use_container_width=True)

with col_right:
    st.markdown('<div class="section-title">📊 Daily Peak vs Average</div>', unsafe_allow_html=True)

    daily_stats = (
        df.groupby("date")["available_stores"]
        .agg(["mean", "max", "min"])
        .reset_index()
    )
    daily_stats["date_str"] = daily_stats["date"].astype(str)

    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        x=daily_stats["date_str"], y=daily_stats["max"],
        name="Peak", marker_color="#FF441F", opacity=0.7,
    ))
    fig_bar.add_trace(go.Bar(
        x=daily_stats["date_str"], y=daily_stats["mean"].round(0),
        name="Average", marker_color="#FFB74D", opacity=0.85,
    ))
    fig_bar.add_trace(go.Bar(
        x=daily_stats["date_str"], y=daily_stats["min"],
        name="Minimum", marker_color="#1A1A2E", opacity=0.5,
    ))
    fig_bar.update_layout(
        template="plotly_white",
        height=400,
        margin=dict(l=0, r=0, t=10, b=0),
        barmode="group",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis_title="Stores",
        xaxis_title="Date",
    )
    st.plotly_chart(fig_bar, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# ROW 3 — HOURLY PATTERN + DAY OF WEEK
# ─────────────────────────────────────────────────────────────────────────────
col_a, col_b = st.columns(2)

with col_a:
    st.markdown('<div class="section-title">⏰ Average Hourly Pattern</div>', unsafe_allow_html=True)

    hourly_pattern = (
        df.groupby("hour")["available_stores"]
        .agg(["mean", "std"])
        .reset_index()
    )
    hourly_pattern["upper"] = hourly_pattern["mean"] + hourly_pattern["std"]
    hourly_pattern["lower"] = (hourly_pattern["mean"] - hourly_pattern["std"]).clip(lower=0)

    fig_hourly = go.Figure()
    fig_hourly.add_trace(go.Scatter(
        x=hourly_pattern["hour"],
        y=hourly_pattern["upper"],
        mode="lines",
        line=dict(width=0),
        showlegend=False,
        hoverinfo="skip",
    ))
    fig_hourly.add_trace(go.Scatter(
        x=hourly_pattern["hour"],
        y=hourly_pattern["lower"],
        mode="lines",
        line=dict(width=0),
        fillcolor="rgba(255,68,31,0.15)",
        fill="tonexty",
        name="±1 Std Dev",
    ))
    fig_hourly.add_trace(go.Scatter(
        x=hourly_pattern["hour"],
        y=hourly_pattern["mean"],
        mode="lines+markers",
        line=dict(color="#FF441F", width=3),
        marker=dict(size=6),
        name="Avg Stores",
    ))
    fig_hourly.update_layout(
        template="plotly_white",
        height=350,
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis=dict(
            title="Hour of Day",
            tickmode="linear",
            dtick=1,
        ),
        yaxis_title="Available Stores",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig_hourly, use_container_width=True)

with col_b:
    st.markdown('<div class="section-title">📅 Day of Week Performance</div>', unsafe_allow_html=True)

    dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    dow_data = (
        df.groupby("day_of_week")["available_stores"]
        .agg(["mean", "max", "min", "std"])
        .reindex(dow_order)
        .reset_index()
    )
    dow_data["short"] = dow_data["day_of_week"].str[:3]

    fig_dow = go.Figure()
    fig_dow.add_trace(go.Bar(
        x=dow_data["short"],
        y=dow_data["mean"].round(0),
        name="Average",
        marker_color=["#FF441F" if d not in ["Saturday", "Sunday"] else "#3B82F6" for d in dow_data["day_of_week"]],
        text=[fmt(v) for v in dow_data["mean"]],
        textposition="outside",
    ))
    fig_dow.update_layout(
        template="plotly_white",
        height=350,
        margin=dict(l=0, r=0, t=10, b=0),
        yaxis_title="Avg Available Stores",
        xaxis_title="Day of Week",
    )
    st.plotly_chart(fig_dow, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# ROW 4 — ANOMALY DETECTION + VELOCITY
# ─────────────────────────────────────────────────────────────────────────────
col_c, col_d = st.columns(2)

with col_c:
    st.markdown('<div class="section-title">⚠️ Anomaly Detection</div>', unsafe_allow_html=True)

    # Use resampled at 5min for anomaly detection
    df_anomaly = resample_data(df, "5min") if resample_freq is None or resample_freq in ["1min"] else df_plot.copy()
    if len(df_anomaly) > 10:
        roll_mean = df_anomaly["available_stores"].rolling(12, center=True).mean()
        roll_std = df_anomaly["available_stores"].rolling(12, center=True).std()
        df_anomaly["z_score"] = (df_anomaly["available_stores"] - roll_mean) / roll_std
        df_anomaly["is_anomaly"] = df_anomaly["z_score"].abs() > anomaly_sigma
        anomalies = df_anomaly[df_anomaly["is_anomaly"]]

        fig_anom = go.Figure()
        fig_anom.add_trace(go.Scatter(
            x=df_anomaly["time"], y=df_anomaly["available_stores"],
            mode="lines", name="Stores",
            line=dict(color="#D1D5DB", width=1),
        ))
        if not anomalies.empty:
            fig_anom.add_trace(go.Scatter(
                x=anomalies["time"], y=anomalies["available_stores"],
                mode="markers", name=f"Anomaly (>{anomaly_sigma}σ)",
                marker=dict(color="#FF1744", size=7, symbol="x"),
            ))
        fig_anom.update_layout(
            template="plotly_white",
            height=350,
            margin=dict(l=0, r=0, t=10, b=0),
            yaxis_title="Available Stores",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_anom, use_container_width=True)
        st.caption(f"🔴 **{len(anomalies)}** anomalous points detected at {anomaly_sigma}σ threshold")
    else:
        st.info("Not enough data for anomaly detection with current filters.")

with col_d:
    st.markdown('<div class="section-title">🚀 Store Ramp‑Up / Ramp‑Down Velocity</div>', unsafe_allow_html=True)

    # Compute velocity = change per minute
    df_vel = resample_data(df, "5min")
    if len(df_vel) > 2:
        df_vel["velocity"] = df_vel["available_stores"].diff()
        df_vel = df_vel.dropna(subset=["velocity"])

        fig_vel = go.Figure()
        colors = ["#00C853" if v >= 0 else "#FF1744" for v in df_vel["velocity"]]
        fig_vel.add_trace(go.Bar(
            x=df_vel["time"], y=df_vel["velocity"],
            marker_color=colors,
            name="Δ Stores / 5min",
        ))
        fig_vel.update_layout(
            template="plotly_white",
            height=350,
            margin=dict(l=0, r=0, t=10, b=0),
            yaxis_title="Change in Stores",
            xaxis_title="Time",
            showlegend=False,
        )
        st.plotly_chart(fig_vel, use_container_width=True)

        max_ramp = df_vel["velocity"].max()
        max_drop = df_vel["velocity"].min()
        st.caption(f"🟢 Max ramp‑up: **+{fmt(max_ramp)}** stores/5min  ·  🔴 Max drop: **{fmt(max_drop)}** stores/5min")
    else:
        st.info("Not enough data for velocity analysis.")

# ─────────────────────────────────────────────────────────────────────────────
# ROW 5 — DISTRIBUTION + STATS TABLE
# ─────────────────────────────────────────────────────────────────────────────
col_e, col_f = st.columns(2)

with col_e:
    st.markdown('<div class="section-title">📉 Distribution of Availability</div>', unsafe_allow_html=True)

    fig_hist = go.Figure()
    fig_hist.add_trace(go.Histogram(
        x=df["available_stores"],
        nbinsx=60,
        marker_color="#FF441F",
        opacity=0.75,
        name="Distribution",
    ))
    fig_hist.add_vline(x=avg, line_dash="dash", line_color="#1A1A2E",
                       annotation_text=f"Mean: {fmt(avg)}", annotation_position="top right")
    fig_hist.update_layout(
        template="plotly_white",
        height=350,
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis_title="Available Stores",
        yaxis_title="Frequency",
        showlegend=False,
    )
    st.plotly_chart(fig_hist, use_container_width=True)

with col_f:
    st.markdown('<div class="section-title">📋 Daily Summary Statistics</div>', unsafe_allow_html=True)

    summary = (
        df.groupby("date")["available_stores"]
        .agg(["mean", "std", "min", "max", "count"])
        .reset_index()
    )
    summary.columns = ["Date", "Avg Stores", "Std Dev", "Min", "Max", "Data Points"]
    summary["Avg Stores"] = summary["Avg Stores"].apply(lambda x: f"{x:,.0f}")
    summary["Std Dev"] = summary["Std Dev"].apply(lambda x: f"{x:,.0f}")
    summary["Min"] = summary["Min"].apply(lambda x: f"{x:,.0f}")
    summary["Max"] = summary["Max"].apply(lambda x: f"{x:,.0f}")
    summary["Data Points"] = summary["Data Points"].apply(lambda x: f"{x:,}")

    st.dataframe(
        summary,
        use_container_width=True,
        height=350,
        hide_index=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# ROW 6 — WEEKDAY vs WEEKEND BOXPLOT
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">📦 Availability Distribution: Weekday vs Weekend (by Hour)</div>', unsafe_allow_html=True)

df["period"] = df["is_weekend"].map({True: "Weekend", False: "Weekday"})
fig_box = px.box(
    df,
    x="hour",
    y="available_stores",
    color="period",
    color_discrete_map={"Weekday": "#FF441F", "Weekend": "#3B82F6"},
    labels={"available_stores": "Available Stores", "hour": "Hour of Day", "period": ""},
)
fig_box.update_layout(
    template="plotly_white",
    height=380,
    margin=dict(l=0, r=0, t=10, b=0),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    boxmode="group",
)
st.plotly_chart(fig_box, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# DATA EXPLORER (EXPANDABLE)
# ─────────────────────────────────────────────────────────────────────────────
with st.expander("🔍 Raw Data Explorer", expanded=False):
    st.dataframe(
        df_plot[["time", "available_stores"]].rename(columns={
            "time": "Timestamp",
            "available_stores": "Available Stores",
        }),
        use_container_width=True,
        height=300,
    )
    csv = df_plot[["time", "available_stores"]].to_csv(index=False)
    st.download_button(
        label="📥 Download filtered data as CSV",
        data=csv,
        file_name="rappi_filtered_availability.csv",
        mime="text/csv",
    )

# ─────────────────────────────────────────────────────────────────────────────
# AI CHATBOT — Gemini 2.5 Flash (Rappi CityOps Monitor)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
st.markdown('<div class="section-title">🤖 Rappi CityOps Monitor — AI Assistant</div>', unsafe_allow_html=True)

# ── Gemini configuration ────────────────────────────────────────────────────
GEMINI_API_KEY = "AIzaSyBd109ClZlRLV0KoctS7nDmSNGCo3rFUiw"
client = genai.Client(api_key=GEMINI_API_KEY)


@st.cache_data(ttl=3600)
def build_data_summary(_df: pd.DataFrame) -> str:
    """Build a compact statistical summary the LLM can use as context."""
    _df = _df.copy()
    _df["date"] = pd.to_datetime(_df["time"]).dt.date
    _df["hour"] = pd.to_datetime(_df["time"]).dt.hour
    _df["day_of_week"] = pd.to_datetime(_df["time"]).dt.day_name()

    lines = ["=== RAPPI STORE AVAILABILITY DATA SUMMARY ==="]
    lines.append(f"Period: {_df['date'].min()} to {_df['date'].max()}")
    lines.append(f"Total data points: {len(_df):,}")
    lines.append(f"Sampling: ~10 seconds")
    lines.append(f"Global min: {_df['available_stores'].min():,}")
    lines.append(f"Global max: {_df['available_stores'].max():,}")
    lines.append(f"Global mean: {_df['available_stores'].mean():,.0f}")
    lines.append("")

    # Daily stats
    lines.append("=== DAILY STATS ===")
    daily = _df.groupby(["date", "day_of_week"])["available_stores"].agg(["mean", "min", "max", "std"]).reset_index()
    for _, row in daily.iterrows():
        lines.append(
            f"{row['date']} ({row['day_of_week']}): "
            f"avg={row['mean']:,.0f}, min={row['min']:,}, max={row['max']:,}, std={row['std']:,.0f}"
        )
    lines.append("")

    # Hourly pattern per day
    lines.append("=== HOURLY AVERAGES PER DAY ===")
    hourly = _df.groupby(["date", "hour"])["available_stores"].mean().reset_index()
    for date, grp in hourly.groupby("date"):
        vals = ", ".join([f"{int(r['hour'])}h:{r['available_stores']:,.0f}" for _, r in grp.iterrows()])
        lines.append(f"{date}: {vals}")
    lines.append("")

    # Biggest drops (>10% in <10 min)
    lines.append("=== NOTABLE DROPS (>10% in <10min windows) ===")
    _df_sorted = _df.sort_values("time").reset_index(drop=True)
    window = 60  # ~10 min at 10s intervals
    if len(_df_sorted) > window:
        rolled_max = _df_sorted["available_stores"].rolling(window).max().shift(1)
        drop_pct = (_df_sorted["available_stores"] - rolled_max) / rolled_max * 100
        big_drops = _df_sorted[drop_pct < -10].head(20)
        if len(big_drops) > 0:
            for _, r in big_drops.iterrows():
                lines.append(f"  {r['time']}: {r['available_stores']:,} stores")
        else:
            lines.append("  No drops >10% detected in a 10-minute window.")
    lines.append("")

    # Peak hours per day ("Golden Hour")
    lines.append("=== GOLDEN HOUR (peak hour per day) ===")
    peak_hours = hourly.loc[hourly.groupby("date")["available_stores"].idxmax()]
    for _, r in peak_hours.iterrows():
        lines.append(f"  {r['date']}: {int(r['hour'])}:00 with avg {r['available_stores']:,.0f} stores")

    return "\n".join(lines)


SYSTEM_PROMPT = """
Rol:
Eres el **Rappi CityOps Monitor**, el analista central encargado de vigilar la salud de la oferta en la ciudad. Tu trabajo es asegurar que la plataforma tenga suficientes tiendas activas para satisfacer la demanda.

Datos Disponibles:
Tienes acceso a un registro minuto a minuto de `available_stores` (oferta total).
- Datos: Del 1 de febrero al 11 de febrero de 2026.
- Granularidad: Muestras cada 10 segundos aprox.

Misión:
Identificar patrones de oferta (cuándo se conectan las tiendas) y detectar anomalías (caídas súbitas que indiquen problemas técnicos masivos).

Capacidades (Instrucciones):

1. **Análisis de Picos**: Identificar siempre la "Hora Dorada" (momento de máxima disponibilidad) del día.

2. **Detección de Caídas**: Si el usuario pregunta por "problemas", busca momentos donde la curva de `available_stores` caiga más de un 10% en menos de 10 minutos.

3. **Comparativas**: Agrega datos por hora. No compares punto a punto (ruido), compara promedios horarios.

4. **Formato de Respuesta**: Responde siempre con:
   - Datos concretos (números, horas, porcentajes)
   - Contexto operativo (qué significa para la plataforma)
   - Recomendaciones si aplica
   - Usa emojis para hacer la respuesta visual: 📈 para subidas, 📉 para bajadas, ⏰ para horas, 🏆 para picos, ⚠️ para problemas

5. **Idioma**: Responde en el mismo idioma que use el usuario (español o inglés).

Ejemplo de Interacción:

Usuario: "¿Cómo estuvo la operación el lunes?"

Agente (CityOps): "El lunes 2 de febrero la operación fue estable.
🏆 Pico Máximo: Alcanzamos 2,450 tiendas conectadas a las 13:00 (almuerzo).
📉 Valle: El momento con menos oferta fue a las 04:00 AM con 35 tiendas.
📈 Tendencia: Vimos una curva de conexión más lenta que el domingo; las tiendas tardaron 30 minutos más en llegar al 80% de capacidad."

IMPORTANTE: Basa TODAS tus respuestas en los datos reales que se te proporcionan a continuación. No inventes datos.
"""

# Build data context for the LLM
data_context = build_data_summary(df_raw)

st.markdown("""
<div class="chat-container">
    <h4>💬 Rappi CityOps Monitor</h4>
    <p style="color:#6B7280; font-size:0.92rem;">
        Analista IA de disponibilidad de tiendas — Powered by Gemini 2.5 Flash
    </p>
    <ul style="color:#6B7280; font-size:0.88rem;">
        <li>"¿Cómo estuvo la operación el lunes?"</li>
        <li>"¿Hubo problemas el viernes?"</li>
        <li>"Compara entre semana vs fin de semana"</li>
        <li>"¿Cuál fue la Hora Dorada de cada día?"</li>
        <li>"¿Cuándo es el mejor momento para onboarding de tiendas?"</li>
    </ul>
</div>
""", unsafe_allow_html=True)

# ── Chat state ──────────────────────────────────────────────────────────────
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "gemini_messages" not in st.session_state:
    st.session_state.gemini_messages = []

# Display previous messages
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"], avatar="🟠" if msg["role"] == "assistant" else None):
        st.markdown(msg["content"])

# Chat input
user_input = st.chat_input("Pregunta sobre disponibilidad de tiendas...")

if user_input:
    # Show user message
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Build Gemini request
    with st.chat_message("assistant", avatar="🟠"):
        with st.spinner("🔍 Analizando datos..."):
            try:
                # Build conversation history for Gemini
                contents = []
                for m in st.session_state.gemini_messages:
                    contents.append(types.Content(
                        role=m["role"],
                        parts=[types.Part.from_text(text=m["content"])],
                    ))
                # Add current user message
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=user_input)],
                ))

                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT + "\n\n" + data_context,
                        temperature=0.3,
                        max_output_tokens=4096,
                    ),
                )
                assistant_text = response.text

                st.markdown(assistant_text)

                # Save to both histories
                st.session_state.gemini_messages.append({"role": "user", "content": user_input})
                st.session_state.gemini_messages.append({"role": "model", "content": assistant_text})
                st.session_state.chat_history.append({"role": "assistant", "content": assistant_text})

            except Exception as e:
                error_msg = f"⚠️ Error al conectar con Gemini: `{str(e)}`"
                st.error(error_msg)
                st.session_state.chat_history.append({"role": "assistant", "content": error_msg})

# Clear chat button
if st.session_state.chat_history:
    if st.button("🗑️ Limpiar conversación", key="clear_chat"):
        st.session_state.chat_history = []
        st.session_state.gemini_messages = []
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    '<p style="text-align:center; color:#9CA3AF; font-size:0.8rem;">'
    'Rappi Store Availability Dashboard · Data from Feb 1–11, 2026 · Built with Streamlit & Plotly'
    '</p>',
    unsafe_allow_html=True,
)
