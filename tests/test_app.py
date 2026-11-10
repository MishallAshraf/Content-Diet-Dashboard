"""FR-07: the dashboard page, one test per row of the dashboard states table in
docs/requirements.md, and the sample's known figures."""
import sys
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

import demo_data
import stats
from store import db

END = date(2026, 11, 1)  # a Sunday, so the sample's four weeks are all full weeks


def run_app(monkeypatch, db_file, **query):
    monkeypatch.setattr(sys, "argv", ["app.py", "--db", str(db_file)])
    at = AppTest.from_file("../app.py", default_timeout=120)
    for k, v in query.items():
        at.query_params[k] = v
    at.run()
    assert not at.exception, at.exception
    return at


def own_db(path, labelled=True):
    """A small database of 'real' (non-sample) viewings."""
    conn = db.connect(path)
    for i, day in enumerate(["2026-10-12", "2026-10-13"]):
        db.save_viewing(conn, {
            "video_id": f"v{i}", "platform": "youtube", "url": f"https://example.com/v{i}", "title": f"V{i}",
            "channel": "A", "duration_sec": 600, "language": "en", "tags": [], "description": "",
            "watched_at": f"{day}T21:00:00", "start_offset_sec": 0, "watched_sec": 600})
    if labelled:
        db.save_labels(conn, "v0", {"category": "Learning", "format": "Lecture", "topic": "x"}, "phi4-mini")
    conn.close()
    return path


def texts(elements):
    return " ".join(e.value for e in elements)


# Sample data builder

def test_demo_data_builds_and_rebuilds(tmp_path):
    path = tmp_path / "demo.db"
    assert demo_data.build(path, end=END) == 433
    assert demo_data.build(path, end=END) == 433  # rebuilding replaces, doesn't append or fail


def test_demo_data_never_touches_the_real_database():
    with pytest.raises(SystemExit):
        demo_data.build(demo_data.db.DEFAULT_DB)


def test_sample_reproduces_known_figures(tmp_path):
    """State 'Known figures': a change to the numbers shows up here."""
    path = tmp_path / "demo.db"
    demo_data.build(path, end=END)
    df = stats.frame(db.viewings(db.connect(path)))
    t = stats.totals(df, days=28)
    assert round(t["minutes"], 1) == 2080.1
    assert (t["viewings"], t["videos"]) == (433, 28)
    assert round(t["learning_share"], 1) == 33.3
    assert stats.top_creators(df, 1)["channel"].item() == "Quiet Strings"
    weekly = stats.learning_share_by_week(df, date(2026, 10, 5), END)
    assert list(weekly["share"].round()) == [46, 22, 23, 37]


# Dashboard states

def test_sample_data_shows_banner_and_every_chart(tmp_path, monkeypatch):
    path = tmp_path / "demo.db"
    demo_data.build(path, end=END)
    at = run_app(monkeypatch, path)
    assert "Sample data" in at.warning[0].value
    assert [m.label for m in at.metric] == ["Time logged", "Per day", "Videos", "Learning share"]
    assert [s.value for s in at.subheader] == ["Time by category per day", "Learning share by week",
                                               "Platform split", "When you watch", "Top creators", "Videos"]
    # FR-14: with nothing clicked, the list holds every video in the dates
    assert len(at.dataframe[0].value) == 28
    assert "Click a bar" in texts(at.caption)


def test_no_database_explains_and_creates_nothing(tmp_path, monkeypatch):
    at = run_app(monkeypatch, tmp_path / "missing.db")
    assert "demo_data.py" in at.info[0].value
    assert not (tmp_path / "missing.db").exists()


def test_empty_database(tmp_path, monkeypatch):
    path = tmp_path / "empty.db"
    db.connect(path).close()
    at = run_app(monkeypatch, path)
    assert "No viewings logged yet" in at.info[0].value


def test_own_data_has_no_sample_banner(tmp_path, monkeypatch):
    at = run_app(monkeypatch, own_db(tmp_path / "own.db"))
    assert not at.warning


def test_nothing_in_picked_platforms(tmp_path, monkeypatch):
    at = run_app(monkeypatch, own_db(tmp_path / "own.db"))
    at.multiselect[0].set_value([]).run()
    assert "Nothing watched in this range" in at.info[0].value


def test_unlabelled_viewings_are_explained(tmp_path, monkeypatch):
    at = run_app(monkeypatch, own_db(tmp_path / "own.db"))
    assert "1 viewings aren't labelled yet" in texts(at.caption)
    assert at.metric[3].value == "100%"  # the unlabelled one is left out of the share


def test_nothing_labelled_shows_na(tmp_path, monkeypatch):
    at = run_app(monkeypatch, own_db(tmp_path / "own.db", labelled=False))
    assert at.metric[3].value == "n/a"


def test_partial_week_is_explained(tmp_path, monkeypatch):
    # own_db's viewings end on Tuesday 13 Oct, so the range ends mid-week.
    at = run_app(monkeypatch, own_db(tmp_path / "own.db"))
    assert "so far" in texts(at.caption)


# FR-14: filters in the URL

def test_url_sets_dates_and_platforms(tmp_path, monkeypatch):
    path = tmp_path / "demo.db"
    demo_data.build(path, end=END)
    at = run_app(monkeypatch, path, **{"from": "2026-10-26", "to": "2026-11-01", "platforms": "instagram"})
    assert at.date_input[0].value == (date(2026, 10, 26), date(2026, 11, 1))
    assert at.multiselect[0].value == ["instagram"]
    assert set(at.dataframe[0].value["channel"]) <= {"devmemes.daily", "pawsandclaws", "code.with.rhea",
                                                     "move.daily", "wanderplates", "quietstrings", "laughtrackclub"}


def test_changing_filters_updates_the_url(tmp_path, monkeypatch):
    at = run_app(monkeypatch, own_db(tmp_path / "own.db"))
    assert at.query_params["from"] == "2026-10-12"
    at.multiselect[0].set_value([]).run()
    assert at.query_params["platforms"] == ""


def test_bad_or_out_of_range_url_falls_back(tmp_path, monkeypatch):
    path = own_db(tmp_path / "own.db")
    at = run_app(monkeypatch, path, **{"from": "yesterday", "to": "2026-10-13"})
    assert at.date_input[0].value == (date(2026, 10, 12), date(2026, 10, 13))
    at = run_app(monkeypatch, path, **{"from": "2020-01-01", "to": "2030-01-01", "platforms": "tiktok,youtube"})
    assert at.date_input[0].value == (date(2026, 10, 12), date(2026, 10, 13))  # clamped to what's logged
    assert at.multiselect[0].value == ["youtube"]  # unknown platforms dropped
