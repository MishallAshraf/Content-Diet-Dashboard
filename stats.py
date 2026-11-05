"""FR-07: the numbers behind the dashboard, as plain pandas functions.

Kept apart from app.py so they can be tested without Streamlit, and reused by
the agent's query_stats tool later (FR-10). Time is counted in watched minutes.
"""
import pandas as pd

from ingest.classify import CATEGORIES

CATEGORY_ORDER = [*CATEGORIES, "Unlabelled"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
COLUMNS = ["watched_at", "watched_sec", "video_id", "platform", "title", "channel",
           "category", "format", "topic"]


def frame(rows):
    """A DataFrame from store.db.viewings(), with minutes, day, week, weekday and hour added."""
    df = pd.DataFrame(rows, columns=COLUMNS)
    at = pd.to_datetime(df["watched_at"])
    df["watched_at"] = at
    df["minutes"] = df["watched_sec"] / 60
    df["day"] = at.dt.normalize()
    df["week"] = at.dt.to_period("W-SUN").dt.start_time  # weeks start on Monday
    df["weekday"] = at.dt.day_of_week
    df["hour"] = at.dt.hour
    return df


def between(df, start, end, platforms=None):
    """Viewings from start to end (dates, inclusive), optionally on some platforms only."""
    keep = (df["day"] >= pd.Timestamp(start)) & (df["day"] <= pd.Timestamp(end))
    if platforms is not None:
        keep &= df["platform"].isin(platforms)
    return df[keep]


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
    return df.groupby(["day", "category"], as_index=False)["minutes"].sum()


def learning_share_by_week(df):
    """One row per week with the Learning share of labelled minutes."""
    weeks = [{"week": week, "share": learning_share(g)} for week, g in df.groupby("week")]
    return pd.DataFrame(weeks, columns=["week", "share"]).dropna()


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
