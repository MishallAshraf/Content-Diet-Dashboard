# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A personal tracker for YouTube videos and Instagram reels: capture links, fetch metadata and transcripts, classify them with an LLM, then show a dashboard, answer questions over transcripts (RAG) and run an agent over the stats. Solo project, runs locally.

Requirements live in [docs/requirements.md](docs/requirements.md) with IDs (`FR-01`…, `NFR-01`…) and a status each. That file is the source of truth for scope and progress.

## Commands

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -e ".[dev]"
pytest                                    # offline, must pass before every commit
python load_links.py --url "<link>"       # log one link
python load_links.py --csv <file.csv>     # log a CSV of links
python -m ingest.classify                 # label unlabelled videos (Ollama must be running)
python demo_data.py                       # sample data in data/demo.db
streamlit run app.py [-- --db data/demo.db]  # dashboard
```

## Current state

Phase 1 (capture) is done. `load_links.py` saves each viewing to SQLite at `data/content_diet.db` through `store/db.py`:

- `videos`: one row per video, keyed by `video_id`; metadata is refreshed on every fetch. `tags` is a JSON list.
- `watch_events`: one row per viewing, unique on `(video_id, watched_at)`, so rewatches add rows and re-imports don't.
- `transcripts` (FR-05): one row per YouTube video, fetched by `ingest/transcript.py` right after the viewing is saved. `segments` is a JSON list of `{start, duration, text}`. A captionless video gets `language NULL, segments '[]'` so it isn't re-fetched. A failed fetch saves nothing and is retried on the next run. Instagram is skipped (FR-13, deferred).

Captions for Hindi videos are auto-generated Hinglish in Devanagari script; the console is reconfigured with `errors="replace"` so printing them can't crash a run.

- `labels` (FR-06): one row per video with `category`, `format`, `topic` and the `model` that produced them, written by `python -m ingest.classify` (a separate command because a local model takes ~10–30 s per video). Labels live in their own table, not in `videos`, so metadata refreshes never touch them and old databases need no migration. Category and format are fixed lists in `ingest/classify.py`; anything else the model returns becomes `Other`.

All LLM calls go through `llm.complete_json(prompt, schema)`. It raises `LLMError` for a bad answer about one item (skip it, carry on) and `LLMUnavailable` when the provider is down or not set up (stop the run).

- Dashboard (FR-07): `app.py` draws Altair charts from `stats.py`, plain pandas functions over `db.viewings()` so they test without Streamlit and the FR-10 agent can reuse them. `tests/test_app.py` renders the page with Streamlit's `AppTest`. `demo_data.py` fills `data/demo.db` with invented, pre-labelled viewings and refuses to touch the real database. Its labels carry `model = 'demo'`, which turns on the sample-data banner. The page's states (no database, empty, sample, unlabelled, partial week…) are listed in `docs/requirements.md` under FR-07, one test each; keep them in step. Label numbers only with what they measure: time is "time logged" (FR-03 assumes watching to the end).

- Drill-downs (FR-14): charts use named Altair point selections with `on_select="rerun"`; `stats.matching()` applies the picks (OR within a chart, AND across charts) and `stats.videos()` builds the list. Selection state can't be reset through session state, so the Clear button bumps a number that is part of each chart's `key`. Dates and platforms are mirrored to `st.query_params`.

Next is FR-08: transcript chunks embedded into Chroma.

Planned layout as phases land (create folders only when a phase needs them):

```
load_links.py        capture (Phase 1)
store/db.py          SQLite schema and writes (FR-04); Chroma later (FR-08)
llm.py               the single LLM entry point and provider switch (FR-06 onwards)
ingest/transcript.py YouTube captions (FR-05)
ingest/classify.py   category / format / topic labels (FR-06); embed later (FR-08)
features/            rag, agent, digest (FR-09..11)
app.py, stats.py     Streamlit dashboard and its numbers (FR-07); pages/ for chat (FR-09)
```

## Rules

- **Work by requirement.** Every change implements or fixes a requirement ID. Update its status in `docs/requirements.md` in the same commit. A requirement is `passing` only when a test covers it; otherwise `built`.
- **Commit messages start with the ID**, e.g. `FR-04: store watch events in SQLite`. Scaffolding and docs use `chore:` or `docs:`.
- **Personal data never leaves the machine.** `data/` and `.env` are git-ignored. Never commit watch history, transcripts, databases or keys, and never print an API key.
- **Tests run offline.** Stub yt-dlp, transcript APIs and LLM calls (see `tests/test_load_links.py` for the monkeypatch pattern).
- **Add dependencies when a phase needs them**, in `pyproject.toml`, with a comment naming the requirement.
- **Keep it small.** No speculative abstractions, no new folders before they hold code. Prefer plain functions and the standard library.
- **yt-dlp:** extraction is metadata only (`skip_download`, `ignore_no_formats_error`). YouTube changes break it periodically; the first fix to try is `pip install -U yt-dlp`.

## Stack (decided)

Python 3.11 · yt-dlp · SQLite · Streamlit · Chroma · multilingual sentence-transformers (videos include Hindi/Hinglish).

**LLMs: local first, with a switch** (decided 2026-10-22).
- Every LLM call goes through one function that reads `LLM_PROVIDER` from `.env`: `ollama` (default) or `anthropic`. Never call a provider directly from feature code.
- Default local model: `phi4-mini` (3.8B) via Ollama. The dev machine is a 2015 dual-core laptop with 8 GB RAM and no GPU, so stay at 1–4B models and expect ~20–60 s per classification.
- `anthropic` (Claude Haiku 5.5 / Sonnet 5.5) is the fallback if RAG answers or the agent are too slow or weak locally. Send only video content (title, tags, transcript), never watch times.
- Ollama lives on `D:\Ollama` (`app\ollama.exe`, models in `D:\Ollama\models`). Start it with `OLLAMA_MODELS=D:\Ollama\models` set, then `D:\Ollama\app\ollama.exe serve`; it listens on `http://127.0.0.1:11434`.
