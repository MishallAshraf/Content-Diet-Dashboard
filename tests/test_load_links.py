"""Offline tests for load_links.py. yt-dlp is stubbed, so no network is used (NFR-04)."""
import pytest

import load_links
from store import db

FAKE_META = {"video_id": "DCYaJb8Bzdk", "platform": "youtube", "title": "EP-1 System Design Explained",
             "channel": "Ankit Jain", "duration_sec": 2597, "language": "hi",
             "tags": ["system design"], "description": ""}


@pytest.fixture
def fake_extract(monkeypatch):
    monkeypatch.setattr(load_links, "extract_metadata", lambda url: dict(FAKE_META, url=url))


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


def test_watched_at_with_csv_is_rejected(tmp_path):
    with pytest.raises(SystemExit):
        load_links.main(["--csv", "x.csv", "--watched-at", "2026-10-14", "--db", str(tmp_path / "t.db")])
