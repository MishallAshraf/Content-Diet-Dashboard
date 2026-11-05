"""FR-07: the dashboard's numbers."""
from datetime import date

import pytest

import stats
from store import db


def rec(video_id, watched_at, minutes, platform="youtube", channel="A"):
    return {"video_id": video_id, "platform": platform, "url": f"https://example.com/{video_id}",
            "title": video_id, "channel": channel, "duration_sec": minutes * 60, "language": "en",
            "tags": [], "description": "", "watched_at": watched_at, "start_offset_sec": 0,
            "watched_sec": minutes * 60}


@pytest.fixture
def df(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.save_viewing(conn, rec("learn", "2026-10-12T21:00:00", 30))                    # Mon, week 1
    db.save_viewing(conn, rec("learn", "2026-10-13T21:00:00", 30))                    # rewatch
    db.save_viewing(conn, rec("fun", "2026-10-13T23:30:00", 20, "instagram", "B"))   # Tue
    db.save_viewing(conn, rec("fun", "2026-10-19T23:10:00", 10, "instagram", "B"))   # Mon, week 2
    db.save_viewing(conn, rec("new", "2026-10-19T08:00:00", 5))                       # not labelled
    db.save_labels(conn, "learn", {"category": "Learning", "format": "Lecture", "topic": "x"}, "m")
    db.save_labels(conn, "fun", {"category": "Entertainment", "format": "Comedy", "topic": "y"}, "m")
    return stats.frame(db.viewings(conn))


def test_viewings_mark_unlabelled_videos(df):
    assert len(df) == 5
    assert df.set_index("video_id").loc["new", "category"] == "Unlabelled"


def test_totals(df):
    t = stats.totals(df, days=8)
    assert t["minutes"] == 95
    assert t["viewings"] == 5
    assert t["videos"] == 3
    assert t["unlabelled"] == 1
    # 60 Learning out of 90 labelled minutes; the unlabelled 5 don't count
    assert t["learning_share"] == pytest.approx(100 * 60 / 90)


def test_learning_share_is_none_without_labels(df):
    assert stats.learning_share(df[df["category"] == "Unlabelled"]) is None


def test_by_category_per_day(df):
    daily = stats.by_category_per_day(df).set_index(["day", "category"])["minutes"]
    assert daily[("2026-10-13", "Learning")] == 30
    assert daily[("2026-10-13", "Entertainment")] == 20


def test_learning_share_by_week_starts_monday(df):
    weekly = stats.learning_share_by_week(df)
    assert [w.date() for w in weekly["week"]] == [date(2026, 10, 12), date(2026, 10, 19)]
    assert list(weekly["share"].round()) == [75, 0]


def test_hour_by_weekday_fills_every_cell(df):
    grid = stats.hour_by_weekday(df)
    assert len(grid) == 7 * 24
    cell = grid[(grid["weekday"] == "Mon") & (grid["hour"] == 23)]["minutes"]
    assert cell.item() == 10
    assert grid["minutes"].sum() == 95


def test_top_creators_and_platform_split(df):
    top = stats.top_creators(df)
    assert list(top["channel"]) == ["A", "B"]
    assert top.iloc[0]["minutes"] == 65
    assert top.iloc[0]["videos"] == 2
    split = stats.platform_split(df).set_index("platform")
    assert split.loc["instagram", "minutes"] == 30
    assert split.loc["youtube", "viewings"] == 3


def test_between_filters_dates_and_platforms(df):
    assert len(stats.between(df, date(2026, 10, 13), date(2026, 10, 13))) == 2
    assert len(stats.between(df, date(2026, 10, 1), date(2026, 10, 31), ["instagram"])) == 2
