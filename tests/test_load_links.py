"""Offline tests for load_links.py. yt-dlp and the transcript API are stubbed (NFR-04)."""
import json

import pytest

import load_links
from store import db

FAKE_META = {"video_id": "DCYaJb8Bzdk", "platform": "youtube", "title": "EP-1 System Design Explained",
             "channel": "Ankit Jain", "duration_sec": 2597, "language": "hi",
             "tags": ["system design"], "description": ""}


TRANSCRIPT = {"language": "hi", "is_generated": True,
              "segments": [{"start": 0.4, "duration": 4.6, "text": "नमस्ते"}]}


@pytest.fixture(autouse=True)
def transcript_calls(monkeypatch):
    """Stub the transcript API for every test (NFR-04) and record which videos were fetched."""
    calls = []

    def fake(video_id, language=None):
        calls.append(video_id)
        return TRANSCRIPT

    monkeypatch.setattr(load_links, "fetch_transcript", fake)
    return calls


@pytest.fixture
def fake_extract(monkeypatch):
    monkeypatch.setattr(load_links, "extract_metadata", lambda url: dict(FAKE_META, url=url))


def transcripts(db_path):
    conn = db.connect(db_path)
    rows = [dict(r) for r in conn.execute("SELECT * FROM transcripts")]
    conn.close()
    return rows


def events(db_path):
    conn = db.connect(db_path)
    rows = [dict(r) for r in conn.execute("SELECT * FROM watch_events ORDER BY id")]
    conn.close()
    return rows


@pytest.mark.parametrize("url, expected", [
    ("https://youtu.be/x?t=40", 40),
    ("https://youtu.be/x?t=40s", 40),
    ("https://www.youtube.com/watch?v=x&t=90s", 90),
    ("https://youtu.be/x", 0),
    ("https://youtu.be/x?t=abc", 0),
])
def test_fr03_start_offset(url, expected):
    assert load_links.start_offset(url) == expected


@pytest.mark.parametrize("url, ok", [
    ("https://www.youtube.com/watch?v=x", True),
    ("https://youtu.be/x", True),
    ("https://www.instagram.com/reel/abc/", True),
    ("https://example.com/video", False),
    ("https://notyoutube.com/watch", False),
])
def test_supported_hosts(url, ok):
    assert load_links.is_supported(url) is ok


def test_fr01_single_link_logs_watched_seconds(fake_extract, tmp_path):
    db_path = tmp_path / "t.db"
    code = load_links.main(["--url", "https://www.youtube.com/watch?v=DCYaJb8Bzdk&t=40s",
                            "--watched-at", "2026-10-14 21:40", "--db", str(db_path)])
    [ev] = events(db_path)
    assert code == 0
    assert ev["watched_sec"] == 2557
    assert ev["start_offset_sec"] == 40
    assert ev["watched_at"] == "2026-10-14T21:40:00"


def test_fr02_nfr02_csv_import_skips_bad_rows(fake_extract, tmp_path):
    csv_file = tmp_path / "links.csv"
    csv_file.write_text(
        "url,watched_at\n"
        "https://www.youtube.com/watch?v=DCYaJb8Bzdk,2026-10-14\n"
        "https://example.com/not-a-video,\n"
        "https://youtu.be/DCYaJb8Bzdk,2026-10-15 08:00\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "t.db"
    code = load_links.main(["--csv", str(csv_file), "--db", str(db_path)])
    rows = events(db_path)
    assert code == 0
    assert len(rows) == 2                      # bad row skipped, import continued
    assert rows[0]["watched_at"] == "2026-10-14T00:00:00"


def test_fr04_reimporting_csv_adds_nothing(fake_extract, tmp_path):
    csv_file = tmp_path / "links.csv"
    csv_file.write_text("url,watched_at\nhttps://youtu.be/DCYaJb8Bzdk,2026-10-14 21:40\n",
                        encoding="utf-8")
    db_path = tmp_path / "t.db"
    for _ in range(2):
        assert load_links.main(["--csv", str(csv_file), "--db", str(db_path)]) == 0
    assert len(events(db_path)) == 1


def test_fr02_csv_without_url_column_exits(tmp_path):
    csv_file = tmp_path / "links.csv"
    csv_file.write_text("link\nhttps://youtu.be/x\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        load_links.main(["--csv", str(csv_file), "--db", str(tmp_path / "t.db")])


def test_missing_title_does_not_crash(monkeypatch, tmp_path):
    monkeypatch.setattr(load_links, "extract_metadata",
                        lambda url: dict(FAKE_META, title=None, url=url))
    db_path = tmp_path / "t.db"
    assert load_links.main(["--url", "https://www.instagram.com/reel/abc/", "--db", str(db_path)]) == 0
    assert len(events(db_path)) == 1


def test_fr03_missing_duration_fails_instead_of_logging_zero(monkeypatch, tmp_path):
    class PartialInfo:  # yt-dlp sometimes returns metadata without a duration
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def extract_info(self, url, download): return {"id": "DCYaJb8Bzdk", "title": "EP-1"}

    monkeypatch.setattr(load_links.yt_dlp, "YoutubeDL", PartialInfo)
    db_path = tmp_path / "t.db"
    assert load_links.main(["--url", "https://youtu.be/DCYaJb8Bzdk?t=40", "--db", str(db_path)]) == 1
    assert events(db_path) == []


def test_fr05_transcript_fetched_once_per_video(fake_extract, transcript_calls, tmp_path):
    db_path = tmp_path / "t.db"
    for when in ("2026-10-14 21:40", "2026-10-15 08:00"):   # a rewatch
        load_links.main(["--url", "https://youtu.be/DCYaJb8Bzdk", "--watched-at", when, "--db", str(db_path)])
    [t] = transcripts(db_path)
    assert transcript_calls == ["DCYaJb8Bzdk"]
    assert t["language"] == "hi"
    assert json.loads(t["segments"])[0]["text"] == "नमस्ते"


def test_fr05_no_transcript_for_instagram(monkeypatch, transcript_calls, tmp_path):
    monkeypatch.setattr(load_links, "extract_metadata",
                        lambda url: dict(FAKE_META, platform="instagram", url=url))
    load_links.main(["--url", "https://www.instagram.com/reel/abc/", "--db", str(tmp_path / "t.db")])
    assert transcript_calls == []


def test_fr05_transcript_failure_keeps_viewing_and_retries_next_run(fake_extract, monkeypatch, tmp_path):
    def broken(video_id, language=None):
        raise ConnectionError("SSL EOF")

    monkeypatch.setattr(load_links, "fetch_transcript", broken)
    db_path = tmp_path / "t.db"
    args = ["--url", "https://youtu.be/DCYaJb8Bzdk", "--watched-at", "2026-10-14", "--db", str(db_path)]
    assert load_links.main(args) == 0
    assert len(events(db_path)) == 1 and transcripts(db_path) == []

    monkeypatch.setattr(load_links, "fetch_transcript", lambda video_id, language=None: TRANSCRIPT)
    load_links.main(args)                      # viewing already logged, transcript backfilled
    assert len(events(db_path)) == 1 and len(transcripts(db_path)) == 1


def test_fr05_video_without_captions_is_not_refetched(fake_extract, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(load_links, "fetch_transcript",
                        lambda video_id, language=None: calls.append(video_id))   # returns None
    db_path = tmp_path / "t.db"
    for when in ("2026-10-14", "2026-10-15"):
        load_links.main(["--url", "https://youtu.be/DCYaJb8Bzdk", "--watched-at", when, "--db", str(db_path)])
    assert calls == ["DCYaJb8Bzdk"]
    assert transcripts(db_path)[0]["language"] is None


def test_watched_at_with_csv_is_rejected(tmp_path):
    with pytest.raises(SystemExit):
        load_links.main(["--csv", "x.csv", "--watched-at", "2026-10-14", "--db", str(tmp_path / "t.db")])
