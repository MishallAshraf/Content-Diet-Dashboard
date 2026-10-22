# Content Diet Dashboard: requirements

Track the YouTube videos and Instagram reels I watch, then chart where my time goes and ask questions about what I watched.

Status values: `todo` · `built` (code exists, no automated test) · `passing` (a test verifies it) · `deferred`.
Change a status in the same commit as the code. Never delete a requirement; mark it `deferred` with a reason.

## Phase 1: Capture

| ID | Requirement | Status |
|---|---|---|
| FR-01 | Log a single YouTube or Instagram link, with an optional watched-at time (default: now). | passing |
| FR-02 | Import a CSV of links with a `url` column and an optional `watched_at` column. | passing |
| FR-03 | Subtract a `t=` start time (`40` or `40s`) from the duration to get watched seconds. | passing |
| FR-04 | Store videos and watch events in SQLite (`videos`, `watch_events`), so rewatches count as new events and re-importing the same viewing adds nothing. | passing |

## Phase 2: Understand

| ID | Requirement | Status |
|---|---|---|
| FR-05 | Fetch each YouTube video's captions once, with timestamps: manual over auto-generated, the video's own language first. Videos without captions are remembered, not re-fetched. | passing |
| FR-13 | Transcribe Instagram reels and captionless videos with Whisper (split from FR-05). | deferred: needs PyTorch and audio downloads; revisit once reels are logged regularly |
| FR-06 | Classify each video with an LLM into category, format, topic and intent, returned as JSON. | todo |

## Phase 3: Dashboard

| ID | Requirement | Status |
|---|---|---|
| FR-07 | Streamlit dashboard: time by category per day, learning share by week, hour-by-day heatmap, top creators, platform split. | todo |

## Phase 4: Ask your history

| ID | Requirement | Status |
|---|---|---|
| FR-08 | Split transcripts into ~500-token chunks that keep their start time, embed them with a multilingual model and store them in Chroma. | todo |
| FR-09 | Answer questions from the top-k chunks, citing video and timestamp. | todo |

## Phase 5: Agent and digest

| ID | Requirement | Status |
|---|---|---|
| FR-10 | Agent with tools `query_stats`, `search_videos`, `fetch_transcript` that answers mixed questions. | todo |
| FR-11 | Weekly digest: an LLM summary of the week's stats with one suggestion. | todo |

## Phase 6: Bulk import

| ID | Requirement | Status |
|---|---|---|
| FR-12 | Import Google Takeout `watch-history.json`. | todo |

## Non-functional

| ID | Requirement | Status |
|---|---|---|
| NFR-01 | Personal data (`data/`) and secrets (`.env`) are never committed. | passing (`.gitignore`) |
| NFR-02 | One bad link never stops a bulk import; failures are reported and skipped. | passing |
| NFR-03 | Runs locally on one machine: no server, no hosted database. | passing |
| NFR-04 | Tests run offline: network calls (yt-dlp, LLMs) are stubbed. | passing |
