"""FR-07: the Streamlit dashboard.

    streamlit run app.py                         # your real history
    streamlit run app.py -- --db data/demo.db    # the sample from demo_data.py
"""
import argparse
import sys
from datetime import timedelta
from pathlib import Path

import altair as alt
import streamlit as st

import stats
from store import db

CATEGORY_COLORS = {
    "Learning": "#2a9d8f", "Entertainment": "#e76f51", "Fitness": "#8ab17d", "News": "#457b9d",
    "Music": "#b5838d", "Other": "#9aa5b1", "Unlabelled": "#d3d9df",
}
PLATFORM_COLORS = {"youtube": "#c44536", "instagram": "#7b5ea7"}


def db_path():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=db.DEFAULT_DB)
    return Path(parser.parse_known_args(sys.argv[1:])[0].db)


@st.cache_data
def load(path, modified):
    """Viewings as a DataFrame; `modified` is the file's mtime, so new links show up on refresh."""
    conn = db.connect(path)
    try:
        return stats.frame(db.viewings(conn))
    finally:
        conn.close()


def duration(minutes):
    h, m = divmod(round(minutes), 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def color(field, palette, present):
    """Fixed colours per value, with only the values in the data in the legend."""
    domain = [k for k in palette if k in set(present)]
    return alt.Color(f"{field}:N", scale=alt.Scale(domain=domain, range=[palette[k] for k in domain]),
                     legend=alt.Legend(orient="bottom", title=None))


st.set_page_config(page_title="Content Diet", layout="wide")
st.title("Content Diet")

path = db_path()
if not path.exists():
    st.info(f"No database at `{path}` yet. Log something with `python load_links.py --url <link>`, "
            "or try the sample: `python demo_data.py`, then `streamlit run app.py -- --db data/demo.db`.")
    st.stop()

df = load(path, path.stat().st_mtime)
if df.empty:
    st.info("No viewings logged yet. Add some with `python load_links.py`.")
    st.stop()

with st.sidebar:
    st.caption(f"Database: `{path.name}`")
    first, last = df["day"].min().date(), df["day"].max().date()
    default_start = max(first, last - timedelta(days=27))
    picked = st.date_input("Dates", (default_start, last), min_value=first, max_value=last)
    start, end = (picked if len(picked) == 2 else (picked[0], picked[0]))
    platforms = st.multiselect("Platforms", sorted(df["platform"].unique()), default=sorted(df["platform"].unique()))

view = stats.between(df, start, end, platforms)
if view.empty:
    st.info("Nothing watched in this range.")
    st.stop()

days = (end - start).days + 1
t = stats.totals(view, days)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Time watched", duration(t["minutes"]))
c2.metric("Per day", duration(t["minutes_per_day"]))
c3.metric("Videos", t["videos"], help=f"{t['viewings']} viewings, rewatches included")
c4.metric("Learning share", "n/a" if t["learning_share"] is None else f"{t['learning_share']:.0f}%")
if t["unlabelled"]:
    st.caption(f"{t['unlabelled']} viewings aren't labelled yet; run `python -m ingest.classify`. "
               "They show as Unlabelled and don't count toward the learning share.")

st.subheader("Time by category per day")
daily = stats.by_category_per_day(view)
st.altair_chart(
    alt.Chart(daily).mark_bar().encode(
        x=alt.X("day:T", title=None, axis=alt.Axis(format="%d %b")),
        y=alt.Y("minutes:Q", title="Minutes", stack=True),
        color=color("category", CATEGORY_COLORS, daily["category"]),
        order=alt.Order("category:N"),
        tooltip=[alt.Tooltip("day:T", format="%a %d %b"), "category",
                 alt.Tooltip("minutes:Q", format=".0f")],
    ).properties(height=280),
    width="stretch",
)

left, right = st.columns(2)
with left:
    st.subheader("Learning share by week")
    weekly = stats.learning_share_by_week(view)
    st.altair_chart(
        alt.Chart(weekly).mark_line(point=True, color=CATEGORY_COLORS["Learning"]).encode(
            x=alt.X("week:T", title="Week of", axis=alt.Axis(format="%d %b")),
            y=alt.Y("share:Q", title="% of labelled time", scale=alt.Scale(domain=[0, 100])),
            tooltip=[alt.Tooltip("week:T", title="Week of", format="%d %b"),
                     alt.Tooltip("share:Q", title="Learning %", format=".0f")],
        ).properties(height=260),
        width="stretch",
    )
with right:
    st.subheader("Platform split")
    split = stats.platform_split(view)
    st.altair_chart(
        alt.Chart(split).mark_arc(innerRadius=60).encode(
            theta="minutes:Q",
            color=color("platform", PLATFORM_COLORS, split["platform"]),
            tooltip=["platform", alt.Tooltip("minutes:Q", format=".0f"), "viewings"],
        ).properties(height=260),
        width="stretch",
    )

left, right = st.columns(2)
with left:
    st.subheader("When you watch")
    grid = stats.hour_by_weekday(view)
    st.altair_chart(
        alt.Chart(grid).mark_rect().encode(
            x=alt.X("hour:O", title="Hour of day"),
            y=alt.Y("weekday:O", title=None, sort=stats.WEEKDAYS),
            color=alt.Color("minutes:Q", title="Minutes", scale=alt.Scale(range=["#f3f6fa", "#1d4e89"])),
            tooltip=["weekday", "hour", alt.Tooltip("minutes:Q", format=".0f")],
        ).properties(height=260),
        width="stretch",
    )
with right:
    st.subheader("Top creators")
    creators = stats.top_creators(view)
    st.altair_chart(
        alt.Chart(creators).mark_bar().encode(
            x=alt.X("minutes:Q", title="Minutes"),
            y=alt.Y("channel:N", title=None, sort="-x", axis=alt.Axis(labelLimit=160, labelOverlap=False)),
            color=color("platform", PLATFORM_COLORS, creators["platform"]),
            tooltip=["channel", "platform", alt.Tooltip("minutes:Q", format=".0f"), "videos"],
        ).properties(height=max(260, 28 * len(creators))),
        width="stretch",
    )
