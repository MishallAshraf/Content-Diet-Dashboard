# Content Diet Dashboard

Track the YouTube videos and Instagram reels you watch, then chart where your time goes and ask questions about what you watched.

> **Status: Phase 3 done.** `load_links.py` saves links with their metadata, watched time and YouTube captions to a local SQLite database, `python -m ingest.classify` labels each video with a local LLM, and `streamlit run app.py` charts it. RAG and the agent are not built yet. See [docs/requirements.md](docs/requirements.md).

## Prerequisites

- Python 3.11 or newer
- From Phase 2 (classification) onwards: [Ollama](https://ollama.com) with a small model, e.g. `ollama pull phi4-mini`. LLM calls run locally by default; set `LLM_PROVIDER=anthropic` in `.env` to use Claude instead.

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

Viewings are saved to `data/content_diet.db`: a `videos` table with one row per video, and a `watch_events` table with one row per viewing. Watching a video again adds a new event; importing the same CSV twice adds nothing.
Each YouTube video's captions are saved once, with timestamps, in a `transcripts` table. If a transcript fetch fails, the viewing is still saved and the transcript is fetched on the next run. Instagram reels have no transcripts yet. Open the file with any SQLite viewer, such as [DB Browser for SQLite](https://sqlitebrowser.org/).

Everything under `data/` stays on your machine; it is git-ignored.

## Label your videos

Start Ollama, then:

```bash
python -m ingest.classify
```

Each video without labels gets a category (Learning, Entertainment, Fitness, News, Music, Other), a format (Lecture, Tutorial, Podcast…) and a short topic, saved in a `labels` table. With a small local model on a laptop CPU, expect about a minute for the first video while the model loads, then 10–30 seconds each. To use Claude instead, `pip install -e ".[anthropic]"`, then set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` in `.env`.

## See the dashboard

```bash
streamlit run app.py
```

It opens in your browser at `http://localhost:8501` and shows time by category per day, your learning share by week, when you watch (hour by weekday), top creators and the YouTube/Instagram split, for the dates and platforms you pick in the sidebar. New links show up when you refresh the page.

No history yet? Try it on four weeks of made-up viewings:

```bash
python demo_data.py
streamlit run app.py -- --db data/demo.db
```

## Layout

| Path | Purpose |
|---|---|
| `load_links.py` | Capture links or a CSV, fetch metadata with yt-dlp, save to SQLite. |
| `store/db.py` | SQLite schema (`videos`, `watch_events`, `transcripts`, `labels`) and writes. |
| `ingest/transcript.py` | Fetch YouTube captions with timestamps, retrying dropped connections. |
| `ingest/classify.py` | Label videos with category, format and topic. |
| `app.py` | Streamlit dashboard. |
| `stats.py` | The numbers behind the charts (pandas). |
| `demo_data.py` | Builds `data/demo.db` with made-up, labelled viewings. |
| `llm.py` | The single LLM entry point; `LLM_PROVIDER` switches between Ollama and Anthropic. |
| `tests/` | Offline tests; yt-dlp is stubbed. |
| `docs/requirements.md` | Numbered requirements and their status. |
| `.env.example` | Settings template; copy to `.env` when a phase needs keys. |
