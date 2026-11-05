"""FR-07: the dashboard page renders, on the sample data and with no database."""
import sys

import pytest
from streamlit.testing.v1 import AppTest

import demo_data


def run_app(monkeypatch, db_file):
    monkeypatch.setattr(sys, "argv", ["app.py", "--db", str(db_file)])
    at = AppTest.from_file("../app.py", default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    return at


def test_demo_data_builds(tmp_path):
    path = tmp_path / "demo.db"
    assert demo_data.build(path) > 100
    assert demo_data.build(path) > 100  # rebuilding replaces, doesn't append or fail


def test_demo_data_never_touches_the_real_database():
    with pytest.raises(SystemExit):
        demo_data.build(demo_data.db.DEFAULT_DB)


def test_dashboard_renders_sample(tmp_path, monkeypatch):
    path = tmp_path / "demo.db"
    demo_data.build(path)
    at = run_app(monkeypatch, path)
    assert [m.label for m in at.metric] == ["Time watched", "Per day", "Videos", "Learning share"]
    assert [s.value for s in at.subheader] == ["Time by category per day", "Learning share by week",
                                               "Platform split", "When you watch", "Top creators"]


def test_dashboard_explains_missing_database(tmp_path, monkeypatch):
    at = run_app(monkeypatch, tmp_path / "missing.db")
    assert "demo_data.py" in at.info[0].value
    assert not (tmp_path / "missing.db").exists()
