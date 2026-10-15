# Content Diet Dashboard

Track the YouTube videos and Instagram reels you watch, then chart where your time goes and ask questions about what you watched.

> **Status: Phase 1 (capture) done.** `load_links.py` saves links with their metadata and watched time to a local SQLite database. Transcripts, classification, the dashboard, RAG and the agent are not built yet. See [docs/requirements.md](docs/requirements.md).

## Prerequisites

- Python 3.11 or newer

## Quickstart

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Log what you watched

One link (watched-at defaults to now):

```bash
python load_links.py --url "https://www.youtube.com/watch?v=DCYaJb8Bzdk&t=40s"
```

A CSV of links:

```bash
python load_links.py --csv my_links.csv
```

The CSV needs a `url` column. An optional `watched_at` column takes `2026-10-14` or `2026-10-14 21:40`.
A `t=` start time in the link is subtracted from the duration, so `&t=40s` on a 43m 17s video logs 42m 37s.
Links that fail are reported and skipped.

Viewings are saved to `data/content_diet.db`: a `videos` table with one row per video, and a `watch_events` table with one row per viewing. Watching a video again adds a new event; importing the same CSV twice adds nothing. Open the file with any SQLite viewer, such as [DB Browser for SQLite](https://sqlitebrowser.org/).

Everything under `data/` stays on your machine; it is git-ignored.

## Layout

| Path | Purpose |
|---|---|
| `load_links.py` | Capture links or a CSV, fetch metadata with yt-dlp, save to SQLite. |
| `store/db.py` | SQLite schema (`videos`, `watch_events`) and writes. |
| `tests/` | Offline tests; yt-dlp is stubbed. |
| `docs/requirements.md` | Numbered requirements and their status. |
| `.env.example` | Settings template; copy to `.env` when a phase needs keys. |
