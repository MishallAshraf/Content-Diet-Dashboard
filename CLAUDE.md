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
```

## Current state

Phase 1 (capture) is done. `load_links.py` saves each viewing to SQLite at `data/content_diet.db` through `store/db.py`:

- `videos`: one row per video, keyed by `video_id`; metadata is refreshed on every fetch. `tags` is a JSON list.
- `watch_events`: one row per viewing, unique on `(video_id, watched_at)`, so rewatches add rows and re-imports don't.

Next is Phase 2: FR-05 (transcripts), then FR-06 (LLM classification), which will add columns to `videos`.

Planned layout as phases land (create folders only when a phase needs them):

```
load_links.py        capture (Phase 1)
store/db.py          SQLite schema and writes (FR-04); Chroma later (FR-08)
ingest/              transcript, classify, embed (FR-05, FR-06, FR-08)
features/            rag, agent, digest (FR-09..11)
app.py, pages/       Streamlit dashboard and chat (FR-07, FR-09)
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
