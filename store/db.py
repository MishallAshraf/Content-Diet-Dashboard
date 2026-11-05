"""SQLite storage for videos and watch events (FR-04).

videos holds one row per video. watch_events holds one row per viewing, so a
rewatch is a new event. Re-importing the same CSV adds nothing: an event is
unique by (video_id, watched_at).
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "content_diet.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id     TEXT PRIMARY KEY,
    platform     TEXT NOT NULL,
    url          TEXT NOT NULL,
    title        TEXT,
    channel      TEXT,
    duration_sec INTEGER NOT NULL,
    language     TEXT,
    tags         TEXT NOT NULL DEFAULT '[]',   -- JSON list
    description  TEXT NOT NULL DEFAULT '',
    fetched_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watch_events (
    id               INTEGER PRIMARY KEY,
    video_id         TEXT NOT NULL REFERENCES videos(video_id),
    watched_at       TEXT NOT NULL,             -- ISO 8601, local time
    start_offset_sec INTEGER NOT NULL DEFAULT 0,
    watched_sec      INTEGER NOT NULL,
    UNIQUE (video_id, watched_at)
);

CREATE INDEX IF NOT EXISTS idx_watch_events_watched_at ON watch_events(watched_at);

-- FR-05: one row per video. A video without captions gets a row with language NULL and
-- segments '[]', so it isn't re-fetched on every run.
CREATE TABLE IF NOT EXISTS transcripts (
    video_id     TEXT PRIMARY KEY REFERENCES videos(video_id),
    language     TEXT,
    is_generated INTEGER,
    segments     TEXT NOT NULL DEFAULT '[]',   -- JSON list of {start, duration, text}
    fetched_at   TEXT NOT NULL
);

-- FR-06: LLM labels, one row per video. Kept apart from videos so a metadata refresh
-- never touches them and existing databases need no migration.
CREATE TABLE IF NOT EXISTS labels (
    video_id      TEXT PRIMARY KEY REFERENCES videos(video_id),
    category      TEXT NOT NULL,
    format        TEXT NOT NULL,
    topic         TEXT,
    model         TEXT NOT NULL,
    classified_at TEXT NOT NULL
);
"""


def connect(path=DEFAULT_DB):
    """Open the database, creating the file and tables if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def save_viewing(conn, rec):
    """Upsert the video and add the watch event. Returns False if the event was already logged."""
    with conn:
        conn.execute(
            """INSERT INTO videos (video_id, platform, url, title, channel, duration_sec,
                                   language, tags, description, fetched_at)
               VALUES (:video_id, :platform, :url, :title, :channel, :duration_sec,
                       :language, :tags, :description, :fetched_at)
               ON CONFLICT (video_id) DO UPDATE SET
                   platform = excluded.platform, url = excluded.url, title = excluded.title,
                   channel = excluded.channel, duration_sec = excluded.duration_sec,
                   language = excluded.language, tags = excluded.tags,
                   description = excluded.description, fetched_at = excluded.fetched_at""",
            {**rec, "tags": json.dumps(rec.get("tags") or [], ensure_ascii=False),
             "fetched_at": datetime.now().isoformat(timespec="seconds")},
        )
        cur = conn.execute(
            """INSERT OR IGNORE INTO watch_events (video_id, watched_at, start_offset_sec, watched_sec)
               VALUES (:video_id, :watched_at, :start_offset_sec, :watched_sec)""",
            rec,
        )
    return cur.rowcount == 1


def has_transcript(conn, video_id):
    """True once a transcript was fetched, or the video was found to have no captions."""
    return conn.execute("SELECT 1 FROM transcripts WHERE video_id = ?", (video_id,)).fetchone() is not None


def transcript_text(conn, video_id, max_chars):
    """The first max_chars characters of a video's transcript, or '' if there is none."""
    row = conn.execute("SELECT segments FROM transcripts WHERE video_id = ?", (video_id,)).fetchone()
    text = " ".join(s["text"] for s in json.loads(row["segments"])) if row else ""
    return text[:max_chars]


def unlabelled_videos(conn):
    """Videos without labels, oldest first, with tags decoded to a list."""
    rows = conn.execute(
        """SELECT v.* FROM videos v LEFT JOIN labels l USING (video_id)
           WHERE l.video_id IS NULL ORDER BY v.fetched_at""").fetchall()
    return [{**dict(r), "tags": json.loads(r["tags"])} for r in rows]


def save_labels(conn, video_id, labels, model):
    with conn:
        conn.execute(
            """INSERT OR REPLACE INTO labels (video_id, category, format, topic, model, classified_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (video_id, labels["category"], labels["format"], labels["topic"], model,
             datetime.now().isoformat(timespec="seconds")),
        )


def viewings(conn):
    """FR-07: every watch event with its video and labels, oldest first.
    Videos not classified yet get category 'Unlabelled'."""
    rows = conn.execute(
        """SELECT e.watched_at, e.watched_sec, v.video_id, v.platform, v.title, v.channel,
                  COALESCE(l.category, 'Unlabelled') AS category, l.format, l.topic
           FROM watch_events e
           JOIN videos v USING (video_id)
           LEFT JOIN labels l USING (video_id)
           ORDER BY e.watched_at""").fetchall()
    return [dict(r) for r in rows]


def save_transcript(conn, video_id, transcript):
    """Store a transcript from ingest.transcript, or None for a video without captions."""
    t = transcript or {"language": None, "is_generated": None, "segments": []}
    with conn:
        conn.execute(
            """INSERT OR REPLACE INTO transcripts (video_id, language, is_generated, segments, fetched_at)
               VALUES (?, ?, ?, ?, ?)""",
            (video_id, t["language"], t["is_generated"],
             json.dumps(t["segments"], ensure_ascii=False), datetime.now().isoformat(timespec="seconds")),
        )
