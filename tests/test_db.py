"""FR-04: videos and watch events in SQLite."""
import json

from store import db

REC = {"video_id": "DCYaJb8Bzdk", "platform": "youtube", "url": "https://www.youtube.com/watch?v=DCYaJb8Bzdk",
       "title": "EP-1 System Design Explained", "channel": "Ankit Jain", "duration_sec": 2597,
       "language": "hi", "tags": ["system design", "hld"], "description": "Master System Design",
       "watched_at": "2026-10-14T21:40:00", "start_offset_sec": 40, "watched_sec": 2557}


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_connect_creates_file_and_tables(tmp_path):
    path = tmp_path / "sub" / "t.db"
    conn = db.connect(path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert path.exists()
    assert {"videos", "watch_events"} <= tables


def test_save_stores_video_and_event(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    assert db.save_viewing(conn, REC) is True
    video = conn.execute("SELECT * FROM videos").fetchone()
    event = conn.execute("SELECT * FROM watch_events").fetchone()
    assert video["title"] == REC["title"]
    assert json.loads(video["tags"]) == ["system design", "hld"]
    assert event["video_id"] == "DCYaJb8Bzdk"
    assert event["watched_sec"] == 2557


def test_rewatch_adds_event_not_video(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.save_viewing(conn, REC)
    db.save_viewing(conn, dict(REC, watched_at="2026-10-15T08:00:00"))
    assert count(conn, "videos") == 1
    assert count(conn, "watch_events") == 2


def test_same_viewing_twice_is_ignored(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    assert db.save_viewing(conn, REC) is True
    assert db.save_viewing(conn, REC) is False
    assert count(conn, "watch_events") == 1


def test_metadata_refreshes_on_new_fetch(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.save_viewing(conn, REC)
    db.save_viewing(conn, dict(REC, title="EP-1 (renamed)", watched_at="2026-10-15T08:00:00"))
    assert conn.execute("SELECT title FROM videos").fetchone()[0] == "EP-1 (renamed)"


def test_fr05_save_and_check_transcript(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.save_viewing(conn, REC)
    assert db.has_transcript(conn, "DCYaJb8Bzdk") is False
    db.save_transcript(conn, "DCYaJb8Bzdk", {"language": "hi", "is_generated": True,
                                             "segments": [{"start": 0.4, "duration": 4.6, "text": "नमस्ते"}]})
    row = conn.execute("SELECT * FROM transcripts").fetchone()
    assert db.has_transcript(conn, "DCYaJb8Bzdk") is True
    assert row["language"] == "hi"
    assert json.loads(row["segments"])[0]["text"] == "नमस्ते"


def test_fr05_no_captions_is_remembered(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.save_viewing(conn, REC)
    db.save_transcript(conn, "DCYaJb8Bzdk", None)
    row = conn.execute("SELECT language, segments FROM transcripts").fetchone()
    assert db.has_transcript(conn, "DCYaJb8Bzdk") is True
    assert (row["language"], row["segments"]) == (None, "[]")


def test_data_survives_reconnect(tmp_path):
    path = tmp_path / "t.db"
    conn = db.connect(path)
    db.save_viewing(conn, REC)
    conn.close()
    assert count(db.connect(path), "watch_events") == 1
