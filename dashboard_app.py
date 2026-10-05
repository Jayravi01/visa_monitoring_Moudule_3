"""Visa & Regulatory Change Monitor dashboard (Streamlit + Plotly prototype).

    streamlit run dashboard_app.py

Data: local JSON Lines store by default (live if it has data, otherwise the demo sample).
Set DATA_SOURCE=athena in .env to read the v_visa_changes view from Athena instead.
"""
import os
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import alerts
import config
import storage

st.set_page_config(page_title="Visa & Regulatory Change Monitor", layout="wide")

# ---------------------------------------------------------------- theme tokens (validated palette)
TOKENS = {
    "light": dict(surface="#fcfcfb", text1="#0b0b0b", text2="#52514e", muted="#898781",
                  grid="#e1e0d9", axis="#c3c2b7", series1="#2a78d6",
                  # ordinal ramp for impact: Low -> Medium -> High, darker = higher
                  low="#86b6ef", medium="#3987e5", high="#184f95"),
    "dark": dict(surface="#1a1a19", text1="#ffffff", text2="#c3c2b7", muted="#898781",
                 grid="#2c2c2a", axis="#383835", series1="#3987e5",
                 # on a dark surface the most prominent step is the lightest
                 low="#184f95", medium="#3987e5", high="#86b6ef"),
}
FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif"
IMPACT_ORDER = ["High", "Medium", "Low"]


def is_dark() -> bool:
    try:
        return st.context.theme.type == "dark"
    except Exception:  # older Streamlit or no theme info
        return False


C = TOKENS["dark" if is_dark() else "light"]


def style(fig: go.Figure, height: int = 340) -> go.Figure:
    fig.update_layout(
        height=height, paper_bgcolor=C["surface"], plot_bgcolor=C["surface"],
        font=dict(family=FONT, color=C["text2"], size=12),
        margin=dict(l=8, r=16, t=28, b=8), bargap=0.4,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=C["text2"])),
        hoverlabel=dict(bgcolor=C["surface"], font=dict(color=C["text1"], family=FONT), bordercolor=C["axis"]),
    )
    fig.update_xaxes(showgrid=False, linecolor=C["axis"], tickfont=dict(color=C["muted"]), zeroline=False)
    fig.update_yaxes(gridcolor=C["grid"], gridwidth=1, zeroline=False, linecolor=C["surface"],
                     tickfont=dict(color=C["muted"]))
    return fig


# ---------------------------------------------------------------- data
@st.cache_data(ttl=300, show_spinner="Loading data...")
def load_athena() -> pd.DataFrame:
    from athena_setup import run_query

    df = run_query(f"SELECT * FROM {config.ATHENA_DATABASE}.v_visa_changes")
    if df.empty:
        return df
    for col in ["published_date", "effective_date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    df["impact_score"] = pd.to_numeric(df["impact_score"])
    for col in storage.LIST_COLS:
        df[col] = df[col].fillna("").apply(lambda s: [x for x in s.split("; ") if x])
    return df.sort_values("published_date", ascending=False).reset_index(drop=True)


@st.cache_data(ttl=60, show_spinner="Loading data...")
def load_local(sample: bool) -> pd.DataFrame:
    return storage.load_df(storage.store_root(sample))


use_athena = os.getenv("DATA_SOURCE", "local").lower() == "athena"
if use_athena:
    df, alert_root, label = load_athena(), None, "Athena"
else:
    live_has_data = not load_local(False).empty
    choice = st.sidebar.radio("Data", ["Live", "Sample (demo)"], index=0 if live_has_data else 1)
    sample = choice != "Live"
    df, alert_root, label = load_local(sample), storage.store_root(sample), choice
    if sample:
        st.sidebar.caption("Synthetic demo items. Not real announcements.")

st.title("Visa & Regulatory Change Monitor")
st.caption(f"Changes that may shift demand for OSHC, OVHC and OWHC  ·  source: {label}")

if df.empty:
    st.info("No data yet. Run `python run_pipeline.py` (add `--offline` for demo data) and refresh.")
    st.stop()

# ---------------------------------------------------------------- filters (one row, above everything)
all_cats = sorted({c for row in df["visa_categories"] for c in row})
all_prods = sorted({p for row in df["products_affected"] for p in row})
dmin, dmax = df["published_date"].min().date(), max(df["published_date"].max().date(), date.today())

f1, f2, f3, f4, f5 = st.columns([1.3, 1, 1.4, 1, 1.3])
rng = f1.date_input("Published", value=(dmin, dmax), min_value=dmin, max_value=dmax)
impacts = f2.multiselect("Impact", IMPACT_ORDER, default=IMPACT_ORDER)
cats = f3.multiselect("Visa category", all_cats)
prods = f4.multiselect("Product", all_prods)
srcs = f5.multiselect("Source", sorted(df["source_name"].unique()))

start, end = (rng[0], rng[1]) if isinstance(rng, (list, tuple)) and len(rng) == 2 else (dmin, dmax)
f = df[(df["published_date"].dt.date >= start) & (df["published_date"].dt.date <= end) & df["impact"].isin(impacts)]
if cats:
    f = f[f["visa_categories"].apply(lambda v: bool(set(v) & set(cats)))]
if prods:
    f = f[f["products_affected"].apply(lambda v: bool(set(v) & set(prods)))]
if srcs:
    f = f[f["source_name"].isin(srcs)]
if f.empty:
    st.warning("No changes match these filters.")
    st.stop()

# ---------------------------------------------------------------- KPI row
today = pd.Timestamp(date.today())
soon = f[(f["effective_date"] >= today) & (f["effective_date"] <= today + timedelta(days=90))]
k1, k2, k3, k4 = st.columns(4)
k1.metric("Changes in range", len(f))
k2.metric("High impact", int((f["impact"] == "High").sum()))
k3.metric("Effective in next 90 days", len(soon))
k4.metric("Visa categories touched", len({c for row in f["visa_categories"] for c in row}))

# ---------------------------------------------------------------- alerts
if alert_root is not None:
    recent = [a for a in alerts.load_alerts(alert_root) if a["severity"] == "High"][:5]
    if recent:
        st.subheader("Latest High-impact alerts")
        st.dataframe(
            pd.DataFrame(recent)[["created_at", "severity", "title", "effective_date", "url"]],
            hide_index=True, width="stretch",
            column_config={
                "created_at": "Raised", "severity": "Impact", "title": "Change",
                "effective_date": "Effective", "url": st.column_config.LinkColumn("Source link", display_text="Open"),
            },
        )

# ---------------------------------------------------------------- change feed
st.subheader("Change feed")
feed = f.assign(
    visa=f["visa_categories"].apply(", ".join), products=f["products_affected"].apply(", ".join),
    types=f["change_types"].apply(", ".join),
)[["published_date", "effective_date", "impact", "title", "summary", "visa", "products", "types",
   "impact_rationale", "source_name", "url"]]
st.dataframe(
    feed, hide_index=True, width="stretch", height=380,
    column_config={
        "published_date": st.column_config.DateColumn("Published", format="DD MMM YYYY"),
        "effective_date": st.column_config.DateColumn("Effective", format="DD MMM YYYY"),
        "impact": "Impact", "title": "Change", "summary": "Change summary",
        "visa": "Visa categories affected", "products": "Products", "types": "Change type",
        "impact_rationale": "Impact assessment", "source_name": "Source",
        "url": st.column_config.LinkColumn("Source link", display_text="Open"),
    },
)

# ---------------------------------------------------------------- trends
st.subheader("Trends")
t1, t2 = st.columns(2)

monthly = (
    f.assign(month=f["published_date"].dt.to_period("M").dt.to_timestamp())
    .groupby(["month", "impact"]).size().unstack(fill_value=0)
    .reindex(columns=IMPACT_ORDER, fill_value=0)
)
months = pd.date_range(monthly.index.min(), monthly.index.max(), freq="MS")
monthly = monthly.reindex(months, fill_value=0)

fig1 = go.Figure()
for level, colour in [("Low", C["low"]), ("Medium", C["medium"]), ("High", C["high"])]:
    fig1.add_bar(
        x=monthly.index, y=monthly[level], name=level, marker_color=colour,
        marker_line_color=C["surface"], marker_line_width=2,  # 2px surface gap between segments
        hovertemplate=f"%{{x|%b %Y}}<br>{level}: %{{y}}<extra></extra>",
    )
fig1.update_layout(barmode="stack")
fig1.update_xaxes(tickformat="%b %y")
t1.markdown("**Change frequency by month, by impact**")
t1.plotly_chart(style(fig1), width="stretch", config={"displayModeBar": False})

by_cat = (
    f.explode("visa_categories")["visa_categories"].dropna().value_counts()
    .rename_axis("visa_category").reset_index(name="changes").sort_values("changes")
)
fig2 = go.Figure(go.Bar(
    x=by_cat["changes"], y=by_cat["visa_category"], orientation="h", marker_color=C["series1"],
    text=by_cat["changes"], textposition="outside", cliponaxis=False, textfont=dict(color=C["text2"]),
    hovertemplate="%{y}: %{x} change(s)<extra></extra>",
))
fig2.update_xaxes(showgrid=True, gridcolor=C["grid"], visible=True)
fig2.update_yaxes(showgrid=False, tickfont=dict(color=C["text2"]))
fig2.update_layout(height=max(260, 34 * len(by_cat) + 60), showlegend=False)
t2.markdown("**Visa categories affected**")
t2.plotly_chart(style(fig2, height=max(260, 34 * len(by_cat) + 60)), width="stretch",
                config={"displayModeBar": False})

# ---------------------------------------------------------------- coming into effect + table view
st.subheader("Coming into effect (next 90 days)")
if soon.empty:
    st.caption("Nothing in the filtered set takes effect in the next 90 days.")
else:
    st.dataframe(
        soon.sort_values("effective_date").assign(visa=lambda d: d["visa_categories"].apply(", ".join))
        [["effective_date", "impact", "title", "visa", "url"]],
        hide_index=True, width="stretch",
        column_config={
            "effective_date": st.column_config.DateColumn("Effective", format="DD MMM YYYY"),
            "impact": "Impact", "title": "Change", "visa": "Visa categories",
            "url": st.column_config.LinkColumn("Source link", display_text="Open"),
        },
    )

with st.expander("Chart data (table view)"):
    st.write("Changes per month by impact")
    st.dataframe(monthly.rename_axis("month").reset_index().assign(month=lambda d: d["month"].dt.strftime("%b %Y")),
                 hide_index=True, width="stretch")
    st.write("Changes per visa category")
    st.dataframe(by_cat.sort_values("changes", ascending=False), hide_index=True, width="stretch")
