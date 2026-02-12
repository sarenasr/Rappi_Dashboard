# 🟠 Rappi Store Availability Dashboard — Project Documentation

## Overview

This document explains every decision made during the design and development of the **Rappi Store Availability Monitor** dashboard, a Streamlit-based operational intelligence tool built on real production data.

---

## 1. Data Exploration & Understanding

### What was done

Before writing any code, the raw data (`Base_Unificada.csv`) was thoroughly analyzed:

- **Shape**: 67,141 rows × 2 columns (`time`, `available_stores`)
- **Time range**: Feb 1, 2026 06:11 → Feb 11, 2026 15:00 (≈11 days)
- **Sampling**: Every ~10 seconds (high-frequency time series)
- **Value range**: 0 → 6,198,472 stores
- **Zero-store events**: 6 occurrences, all at system restart times (06:11 AM, 00:06 AM)

### Why it matters

Understanding the data dictated **every design choice**. The enormous value range (0 to 6.2M) meant we needed human-friendly formatting (K/M suffixes). The 10-second granularity across 11 days meant 67K points — too many to plot raw without a resampling control. The daily sunrise/sunset pattern in store counts revealed this is **availability monitoring data**, not transaction data — which shaped the entire analytical framing.

---

## 2. Dashboard Architecture Decisions

### 2.1 Technology Stack

| Component | Choice                 | Why                                                                                                |
| --------- | ---------------------- | -------------------------------------------------------------------------------------------------- |
| Framework | **Streamlit**          | User requirement; rapid prototyping, Python-native, built-in state management for the chatbot      |
| Charting  | **Plotly**             | Interactive hover/zoom crucial for 67K+ datapoints; declarative API; Rappi-brandable color schemes |
| AI Model  | **Gemini 2.5 Flash**   | User-provided API key; fast responses for chat UX; cost-efficient for frequent queries             |
| SDK       | **google-genai** (new) | Migrated from deprecated `google-generativeai` to the current supported SDK                        |

### 2.2 Layout Philosophy

The dashboard follows an **inverted pyramid** information architecture:

1. **KPIs first** — instant situational awareness (6 cards)
2. **Main time series** — the primary monitoring view
3. **Deep-dive charts** — heatmap, patterns, anomalies
4. **Raw data** — expandable explorer for power users
5. **AI chatbot** — conversational analysis at the bottom

This mirrors how operations teams actually consume dashboards: glance → investigate → deep-dive → ask questions.

---

## 3. Feature-by-Feature Breakdown

### 3.1 KPI Cards (6 metrics)

| Metric              | Formula                              | Why it matters                                            |
| ------------------- | ------------------------------------ | --------------------------------------------------------- |
| **Latest Reading**  | Last row in filtered data            | Is the platform healthy _right now_?                      |
| **Peak Stores**     | `max(available_stores)` in range     | Capacity ceiling — are we growing?                        |
| **Average**         | `mean(available_stores)` in range    | Baseline for anomaly detection                            |
| **Minimum**         | `min(available_stores)` in range     | Worst-case — did we have outages?                         |
| **Stability Index** | Coefficient of Variation (σ/μ × 100) | A single number: is availability predictable or volatile? |
| **Data Points**     | `count` at current granularity       | Context for statistical significance                      |

**Delta comparison**: The "Latest Reading" card computes % change vs the _previous period of equal length_, so if you're viewing 3 days, it compares to the prior 3 days. This gives temporal context without requiring a separate baseline dataset.

### 3.2 Sidebar Controls (6 filters)

| Control                 | Type                                             | Why                                                                                 |
| ----------------------- | ------------------------------------------------ | ----------------------------------------------------------------------------------- |
| **Date Range**          | Date picker (tuple)                              | Focus on specific incidents or periods                                              |
| **Hour Window**         | Slider (0–23)                                    | Filter out overnight low-activity hours; focus on peak operations                   |
| **Granularity**         | Selectbox (10s → 1h)                             | Raw data is too noisy for trend analysis; 5min default balances signal vs noise     |
| **Day of Week**         | Multi-select                                     | Compare Tuesdays only, exclude weekends, etc.                                       |
| **Comparison Mode**     | Radio (None / Weekday vs Weekend / Day-over-Day) | Three distinct analytical views from the same chart                                 |
| **Anomaly Sensitivity** | Slider (1.0σ – 4.0σ)                             | Let users tune false-positive rate; operations teams have different risk tolerances |

**Why these specific controls?** They represent the dimensions a Rappi ops manager would naturally think in: "Show me last Friday, lunch hours only, at 15-minute granularity." Every filter applies globally to all charts, maintaining analytical consistency.

### 3.3 Main Time Series Chart

- **Default mode**: Line chart with area fill + rolling average trend overlay
- **Weekday vs Weekend mode**: Two overlaid series with distinct colors — reveals the systematic ~25% weekend drop
- **Day-over-Day mode**: All days overlaid on a 0–24h x-axis — instant visual comparison of daily shapes

**Why rolling average?** The raw 5-min data has micro-fluctuations. The rolling window (auto-sized to data length) reveals the underlying trend, making it easy to spot macro patterns vs noise.

### 3.4 Hourly Heatmap (Date × Hour)

A matrix where:

- X-axis = dates (Feb 1–11)
- Y-axis = hours (0–23)
- Color = average `available_stores`

**Why it matters**: This is the single most information-dense view. In one glance you can see:

- The daily ramp-up pattern (light → dark from 6AM → 4PM)
- Weekend vs weekday differences (Sat/Sun columns are lighter)
- Anomalous hours (any unexpected light/dark cell)

The custom orange-to-red colorscale matches Rappi branding while maintaining perceptual uniformity.

### 3.5 Daily Peak vs Average Bars

Grouped bar chart showing max, mean, and min per day.

**Why it matters**: The gap between peak and average indicates supply volatility. A large gap means stores connect late or disconnect early. This chart immediately flags days with poor ramp-up behavior.

### 3.6 Average Hourly Pattern (±1σ band)

The "typical day" profile: mean stores per hour with a ±1 standard deviation shaded band.

**Why it matters**:

- The band width shows predictability — narrow bands = reliable operations
- The curve shape reveals the business rhythm: ramp-up starts ~7AM, plateau ~14:00–17:00, decline ~18:00+
- Deviations from this template are operational incidents

### 3.7 Day of Week Performance

Bar chart of average availability per day, colored by weekday (orange) vs weekend (blue).

**Why it matters**: Discovered that **Friday is the best day** (3.72M avg) and **Monday is the worst weekday** (2.84M avg). This has direct implications for staffing, marketing campaigns, and partner incentive programs.

### 3.8 Anomaly Detection

Statistical anomaly detection using z-scores on a rolling window:

```
z_score = (value - rolling_mean) / rolling_std
anomaly = |z_score| > threshold
```

**Why this approach?**

- Adapts to the natural daily cycle (rolling window = local context)
- User-configurable sensitivity via the σ slider
- No training required — works immediately on any time range
- At 2.5σ (default), flags roughly the top/bottom 0.6% of deviations

### 3.9 Ramp-Up / Ramp-Down Velocity

Bar chart showing `Δ stores / 5 minutes` — the rate of change.

**Why it matters**: This is the **early warning indicator**. A normal morning ramp-up might be +50K stores/5min. If you see +5K, something is blocking store connections. Conversely, a sudden -100K stores/5min in the afternoon signals a platform incident. The chart makes these events visually unmissable (tall red bars).

### 3.10 Distribution Histogram

Shows how often each availability level occurs across the entire filtered period.

**Why it matters**: Reveals the bimodal nature of the data — there are two peaks (low nighttime values and high daytime values), with relatively few observations in between. This confirms the sharp daily on/off cycle of store availability.

### 3.11 Weekday vs Weekend Boxplot (by Hour)

Side-by-side box plots per hour, split by weekday/weekend.

**Why it matters**: Shows not just the average difference, but the **variance**. Weekends have wider boxes (more unpredictable) and lower medians. This visualization answers: "At 2PM on a Saturday, what's the realistic range of store availability I should expect?"

### 3.12 Raw Data Explorer

Expandable section with:

- Sortable/searchable data table
- CSV download button for filtered data

**Why it matters**: Power users and data analysts need to verify numbers, export for their own analysis, or cross-reference with other data sources. This respects the "trust but verify" principle.

---

## 4. AI Chatbot — Rappi CityOps Monitor

### 4.1 Architecture

```
User Question
    ↓
Streamlit chat_input
    ↓
Pre-computed Data Summary (injected as context)
    ↓
Gemini 2.5 Flash API (system prompt + conversation history)
    ↓
Streamed response → displayed in chat bubble
```

### 4.2 System Prompt Design

The prompt establishes the **Rappi CityOps Monitor** persona with:

1. **Role definition**: Central analyst monitoring city-level supply health
2. **Data awareness**: Explicit mention of what data is available and its granularity
3. **Analytical capabilities**:
   - "Golden Hour" identification (peak availability time per day)
   - Drop detection (>10% in <10 minutes = potential incident)
   - Hourly aggregation for comparisons (avoids noisy point-to-point comparisons)
4. **Response format**: Numbers, context, recommendations, emojis
5. **Bilingual**: Responds in the user's language

### 4.3 Data Context Injection

The `build_data_summary()` function pre-computes and caches:

- Global statistics (min, max, mean, total points)
- Daily stats (avg, min, max, std per day with day-of-week labels)
- Hourly averages per day (full hour-by-hour breakdown)
- Notable drops (>10% in <10 minute windows)
- Golden Hour per day (peak hour with average value)

This summary is ~3KB of text — small enough to fit in every API call, comprehensive enough for the model to answer most operational questions **without hallucinating**.

### 4.4 Why Gemini 2.5 Flash?

- Initially configured for Gemini 2.5 Pro — switched to Flash for faster response times and better API key compatibility
- Temperature set to `0.3` — low enough for factual, data-grounded responses; not zero to allow natural phrasing
- `max_output_tokens=4096` — sufficient for detailed analysis without runaway generation
- Full conversation history maintained via `st.session_state` for multi-turn context

### 4.5 SDK Migration

Originally implemented with `google-generativeai` (deprecated). Migrated to `google-genai` (current supported SDK) which uses:

- `genai.Client(api_key=...)` instead of `genai.configure(...)`
- `client.models.generate_content(...)` instead of `GenerativeModel.start_chat().send_message(...)`
- `types.Content` / `types.Part` for structured message formatting

---

## 5. Performance Considerations

| Concern                          | Solution                                                |
| -------------------------------- | ------------------------------------------------------- |
| 67K rows loading time            | `@st.cache_data(ttl=600)` — cached for 10 min           |
| Chart rendering with many points | Default 5-min resampling reduces to ~2K points          |
| LLM data context                 | Pre-computed summary cached for 1 hour                  |
| Repeated Streamlit reruns        | All expensive computations are cached or session-stated |

---

## 6. Files Created

| File                       | Purpose                                  |
| -------------------------- | ---------------------------------------- |
| `dashboard.py`             | Main Streamlit application (~1000 lines) |
| `requirements.txt`         | Python dependencies                      |
| `PROJECT_DOCUMENTATION.md` | This file                                |

---

## 7. Key Insights Discovered from the Data

1. **Friday is king**: Highest peak (6.2M) and highest average (3.7M) — likely the strongest demand day
2. **Weekend penalty**: ~25% lower average availability on Sundays vs Fridays
3. **Golden window**: 14:00–17:00 COT is consistently the peak availability period
4. **Morning ramp takes ~2 hours**: From first store at ~6AM to plateau at ~8AM
5. **Zero-store resets**: 6 occurrences, all at system restart boundaries — indicates scheduled maintenance
6. **Monday slow start**: Consistently the weakest weekday — possible partner engagement opportunity
7. **High stability during plateau**: CV drops significantly during 12:00–18:00, indicating predictable operations

---

_Built with Streamlit, Plotly, and Gemini 2.5 Flash · February 2026_
