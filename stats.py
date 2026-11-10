"""FR-07: the numbers behind the dashboard, as plain pandas functions.

Kept apart from app.py so they can be tested without Streamlit, and reused by
the agent's query_stats tool later (FR-10). Time is counted in watched minutes.
"""
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd

import demo_data
from ingest.classify import CATEGORIES

CATEGORY_ORDER = [*CATEGORIES, "Unlabelled"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
COLUMNS = ["watched_at", "watched_sec", "start_offset_sec", "video_id", "platform", "url",
           "title", "channel", "category", "format", "topic", "model"]
# FR-14: the fields a chart click can pick, and the column each one matches.
PICK_FIELDS = {"date": "date", "category": "category", "weekday": "weekday_name",
               "hour": "hour", "channel": "channel"}


def frame(rows):
    """A DataFrame from store.db.viewings(), with minutes, day, week, weekday and hour added."""
    df = pd.DataFrame(rows, columns=COLUMNS)
    at = pd.to_datetime(df["watched_at"])
    df["watched_at"] = at
    df["minutes"] = df["watched_sec"] / 60
    df["day"] = at.dt.normalize()
    df["week"] = at.dt.to_period("W-SUN").dt.start_time  # weeks start on Monday
    df["date"] = at.dt.strftime("%Y-%m-%d")  # a plain string, so a chart click returns it unchanged
    df["weekday"] = at.dt.day_of_week
    df["weekday_name"] = df["weekday"].map(dict(enumerate(WEEKDAYS)))
    df["hour"] = at.dt.hour
    return df


def between(df, start, end, platforms=None):
    """Viewings from start to end (dates, inclusive), optionally on some platforms only."""
    keep = (df["day"] >= pd.Timestamp(start)) & (df["day"] <= pd.Timestamp(end))
    if platforms is not None:
        keep &= df["platform"].isin(platforms)
    return df[keep]


def is_sample(df):
    """True when any label came from demo_data.py rather than a model."""
    return bool((df["model"] == demo_data.MODEL).any())


def learning_share(df):
    """Percent of labelled minutes spent on Learning, or None if nothing is labelled."""
    labelled = df[df["category"] != "Unlabelled"]
    total = labelled["minutes"].sum()
    return None if total == 0 else 100 * labelled.loc[labelled["category"] == "Learning", "minutes"].sum() / total


def totals(df, days):
    return {
        "minutes": df["minutes"].sum(),
        "viewings": len(df),
        "videos": df["video_id"].nunique(),
        "minutes_per_day": df["minutes"].sum() / days if days else 0,
        "learning_share": learning_share(df),
        "unlabelled": int((df["category"] == "Unlabelled").sum()),
    }


def by_category_per_day(df):
    """One row per (day, category) with the minutes watched."""
    return df.groupby(["day", "date", "category"], as_index=False)["minutes"].sum()


def learning_share_by_week(df, start, end):
    """One row per week with the Learning share of labelled minutes. `partial` marks a week
    that runs past either end of the start..end range, so its share is only "so far"."""
    weeks = [{"week": week, "share": learning_share(g),
              "partial": week.date() < start or (week + timedelta(days=6)).date() > end}
             for week, g in df.groupby("week")]
    return pd.DataFrame(weeks, columns=["week", "share", "partial"]).dropna()


def hour_by_weekday(df):
    """Minutes for every weekday x hour cell, zeros included, so the heatmap has no holes."""
    grid = (df.groupby(["weekday", "hour"])["minutes"].sum()
              .reindex(pd.MultiIndex.from_product([range(7), range(24)], names=["weekday", "hour"]),
                       fill_value=0)
              .reset_index())
    grid["weekday"] = grid["weekday"].map(dict(enumerate(WEEKDAYS)))
    return grid


def top_creators(df, n=10):
    """The n channels with the most minutes, with how many distinct videos of theirs were watched."""
    return (df.groupby(["channel", "platform"], as_index=False)
              .agg(minutes=("minutes", "sum"), videos=("video_id", "nunique"))
              .sort_values("minutes", ascending=False)
              .head(n))


def platform_split(df):
    return df.groupby("platform", as_index=False).agg(minutes=("minutes", "sum"), viewings=("video_id", "size"))


# FR-14: drill-downs from a chart click to the videos behind it

def matching(df, picks):
    """Viewings matching any of a chart's picks, e.g. [{"date": "2026-10-23", "category": "Music"}].
    No picks means no filter."""
    if not picks:
        return df
    keep = pd.Series(False, index=df.index)
    for pick in picks:
        hit = pd.Series(True, index=df.index)
        for field, value in pick.items():
            if field in PICK_FIELDS:
                hit &= df[PICK_FIELDS[field]] == value
        keep |= hit
    return df[keep]


def describe(pick):
    """A chart pick in words: {"date": "2026-10-23", "category": "Music"} -> "Music on Fri 23 Oct"."""
    if "date" in pick:
        return f"{pick.get('category', 'everything')} on {pd.Timestamp(pick['date']):%a %d %b}"
    if "hour" in pick:
        return f"{pick.get('weekday', 'any day')} {int(pick['hour']):02d}:00–{int(pick['hour']) + 1:02d}:00"
    return pick.get("channel", "")


def watch_link(url, platform, start_sec):
    """The video's link, starting where you started watching (YouTube only; reels play from 0)."""
    if platform != "youtube" or not start_sec:
        return url
    scheme, netloc, path, query, _ = urlsplit(url)
    params = [(k, v) for k, v in parse_qsl(query) if k != "t"] + [("t", f"{int(start_sec)}s")]
    return urlunsplit((scheme, netloc, path, urlencode(params), ""))


def videos(df):
    """One row per video, most watched first, linking to where its latest viewing started."""
    if df.empty:
        return pd.DataFrame(columns=["title", "channel", "category", "format", "minutes", "viewings",
                                     "last_watched", "link"])
    latest = df.sort_values("watched_at").groupby("video_id").tail(1).set_index("video_id")
    out = (df.groupby("video_id")
             .agg(minutes=("minutes", "sum"), viewings=("watched_at", "size"), last_watched=("watched_at", "max"))
             .join(latest[["title", "channel", "category", "format", "url", "platform", "start_offset_sec"]]))
    out["link"] = [watch_link(u, p, s) for u, p, s in zip(out["url"], out["platform"], out["start_offset_sec"])]
    return (out.sort_values("minutes", ascending=False).reset_index()
               [["title", "channel", "category", "format", "minutes", "viewings", "last_watched", "link"]])
