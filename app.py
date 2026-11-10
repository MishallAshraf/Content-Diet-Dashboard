"""FR-07: the Streamlit dashboard.

    streamlit run app.py                         # your real history
    streamlit run app.py -- --db data/demo.db    # the sample from demo_data.py
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import altair as alt
import pandas as pd
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


def week_lines(weekly, x, y, colour):
    """One segment per pair of neighbouring weeks, dashed when either week is partial."""
    rows = []
    for i in range(len(weekly) - 1):
        a, b = weekly.iloc[i], weekly.iloc[i + 1]
        dashed = bool(a["partial"] or b["partial"])
        rows += [{"week": w["week"], "share": w["share"], "segment": i, "dashed": dashed} for w in (a, b)]
    segments = pd.DataFrame(rows, columns=["week", "share", "segment", "dashed"])
    return alt.Chart(segments).mark_line(color=colour).encode(
        x=x, y=y, detail="segment:N",
        strokeDash=alt.condition("datum.dashed", alt.value([5, 4]), alt.value([1, 0])))


def from_url(first, last, default_start, all_platforms):
    """FR-14: the dates and platforms in the URL, clamped to what's logged, else the defaults."""
    qp = st.query_params
    try:
        start, end = date.fromisoformat(qp["from"]), date.fromisoformat(qp["to"])
        start = min(max(start, first), last)
        end = min(max(end, start), last)
    except (KeyError, ValueError):
        start, end = default_start, last
    platforms = all_platforms if "platforms" not in qp else [
        p for p in qp["platforms"].split(",") if p in all_platforms]
    return (start, end), platforms


def clicks(event, name):
    """The picks of a chart's named point selection, e.g. [{"channel": "A"}]."""
    return list(event.selection.get(name, [])) if event else []


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
if stats.is_sample(df):
    st.warning("**Sample data.** These viewings are made up by `demo_data.py`; none of this is your "
               "history. Run `streamlit run app.py` without `--db` to see your own.")

with st.sidebar:
    st.caption(f"Database: `{path.name}`")
    first, last = df["day"].min().date(), df["day"].max().date()
    all_platforms = sorted(df["platform"].unique())
    if "dates" not in st.session_state:  # first run: start from the URL, so a bookmark or refresh keeps the view
        st.session_state["dates"], st.session_state["platforms"] = from_url(
            first, last, max(first, last - timedelta(days=27)), all_platforms)
    picked = st.date_input("Dates", key="dates", min_value=first, max_value=last)
    start, end = (picked if len(picked) == 2 else (picked[0], picked[0]))
    platforms = st.multiselect("Platforms", all_platforms, key="platforms")
    st.query_params.from_dict({"from": start.isoformat(), "to": end.isoformat(), "platforms": ",".join(platforms)})

view = stats.between(df, start, end, platforms)
if view.empty:
    st.info("Nothing watched in this range.")
    st.stop()

days = (end - start).days + 1
t = stats.totals(view, days)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Time logged", duration(t["minutes"]),
          help="From each link's start time to the end of the video. "
               "It assumes you watched to the end, so real viewing may be shorter.")
c2.metric("Per day", duration(t["minutes_per_day"]))
c3.metric("Videos", t["videos"], help=f"{t['viewings']} viewings, rewatches included")
c4.metric("Learning share", "n/a" if t["learning_share"] is None else f"{t['learning_share']:.0f}%")
if t["unlabelled"]:
    st.caption(f"{t['unlabelled']} viewings aren't labelled yet; run `python -m ingest.classify`. "
               "They show as Unlabelled and don't count toward the learning share.")

st.subheader("Time by category per day")
# Chart picks can't be reset through session state, so Clear bumps this number, which is
# part of each chart's key: the charts come back as new widgets with nothing picked.
round_ = st.session_state.setdefault("pick_round", 0)

daily = stats.by_category_per_day(view)
pick_day = alt.selection_point(name="day_category", fields=["date", "category"])
by_day = st.altair_chart(
    alt.Chart(daily).mark_bar().encode(
        x=alt.X("day:T", title=None, axis=alt.Axis(format="%d %b")),
        y=alt.Y("minutes:Q", title="Minutes", stack=True),
        color=color("category", CATEGORY_COLORS, daily["category"]),
        order=alt.Order("category:N"),
        opacity=alt.condition(pick_day, alt.value(1), alt.value(0.3)),
        tooltip=[alt.Tooltip("day:T", format="%a %d %b"), "category",
                 alt.Tooltip("minutes:Q", format=".0f")],
    ).add_params(pick_day).properties(height=280),
    width="stretch", on_select="rerun", key=f"by_day_{round_}",
)

left, right = st.columns(2)
with left:
    st.subheader("Learning share by week")
    weekly = stats.learning_share_by_week(view, start, end)
    weekly["label"] = weekly["partial"].map({True: "so far", False: "full week"})
    x = alt.X("week:T", title="Week of", axis=alt.Axis(format="%d %b"))
    y = alt.Y("share:Q", title="% of labelled time", scale=alt.Scale(domain=[0, 100]))
    learning = CATEGORY_COLORS["Learning"]
    points = alt.Chart(weekly).mark_point(filled=True, size=60, color=learning).encode(
        x=x, y=y, opacity=alt.condition("datum.partial", alt.value(0.45), alt.value(1)),
        tooltip=[alt.Tooltip("week:T", title="Week of", format="%d %b"),
                 alt.Tooltip("share:Q", title="Learning %", format=".0f"), alt.Tooltip("label", title="")])
    st.altair_chart((week_lines(weekly, x, y, learning) + points).properties(height=260), width="stretch")
    if weekly["partial"].any():
        st.caption("Dashed: a week only partly inside the dates, so its share is so far, not final.")
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
    pick_hour = alt.selection_point(name="weekday_hour", fields=["weekday", "hour"])
    by_hour = st.altair_chart(
        alt.Chart(grid).mark_rect().encode(
            x=alt.X("hour:O", title="Hour of day"),
            y=alt.Y("weekday:O", title=None, sort=stats.WEEKDAYS),
            color=alt.Color("minutes:Q", title="Minutes", scale=alt.Scale(range=["#f3f6fa", "#1d4e89"])),
            stroke=alt.condition(pick_hour, alt.value("#e76f51"), alt.value(None), empty=False),
            strokeWidth=alt.condition(pick_hour, alt.value(2), alt.value(0), empty=False),
            tooltip=["weekday", "hour", alt.Tooltip("minutes:Q", format=".0f")],
        ).add_params(pick_hour).properties(height=260),
        width="stretch", on_select="rerun", key=f"by_hour_{round_}",
    )
with right:
    st.subheader("Top creators")
    creators = stats.top_creators(view)
    pick_creator = alt.selection_point(name="creator", fields=["channel"])
    by_creator = st.altair_chart(
        alt.Chart(creators).mark_bar().encode(
            x=alt.X("minutes:Q", title="Minutes"),
            y=alt.Y("channel:N", title=None, sort="-x", axis=alt.Axis(labelLimit=160, labelOverlap=False)),
            color=color("platform", PLATFORM_COLORS, creators["platform"]),
            opacity=alt.condition(pick_creator, alt.value(1), alt.value(0.3)),
            tooltip=["channel", "platform", alt.Tooltip("minutes:Q", format=".0f"), "videos"],
        ).add_params(pick_creator).properties(height=max(260, 28 * len(creators))),
        width="stretch", on_select="rerun", key=f"by_creator_{round_}",
    )

st.subheader("Videos")
chosen, said = view, []
for picks in (clicks(by_day, "day_category"), clicks(by_hour, "weekday_hour"), clicks(by_creator, "creator")):
    chosen = stats.matching(chosen, picks)
    said += [stats.describe(p) for p in picks]
if said:
    text, button = st.columns([5, 1], vertical_alignment="center")
    text.caption(f"Showing {' and '.join(said)}.")
    button.button("Clear", on_click=lambda: st.session_state.update(pick_round=round_ + 1),
                  help="Clear the picks in every chart")
else:
    st.caption("Everything in the dates above. Click a bar, a heatmap cell or a creator to narrow the list.")
if said and chosen.empty:
    st.info("No video matches all of these picks together. Clear them and pick one at a time.")
else:
    st.dataframe(
        stats.videos(chosen), hide_index=True, width="stretch",
        column_config={
            "title": "Title", "channel": "Channel", "category": "Category", "format": "Format",
            "minutes": st.column_config.NumberColumn("Minutes", format="%.0f"),
            "viewings": st.column_config.NumberColumn("Times", help="Viewings in the dates, rewatches included"),
            "last_watched": st.column_config.DatetimeColumn("Last watched", format="D MMM, HH:mm"),
            "link": st.column_config.LinkColumn("Watch", display_text="Open",
                                                help="Opens where you started watching"),
        },
    )
