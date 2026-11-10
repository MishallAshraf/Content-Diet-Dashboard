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
| FR-06 | Classify each video with an LLM into category, format and topic, returned as JSON, through the `LLM_PROVIDER` switch (local Ollama by default). Intent was dropped: the local model answered it inconsistently and the Learning category already gives the learning share. | passing |

## Phase 3: Dashboard

| ID | Requirement | Status |
|---|---|---|
| FR-07 | Streamlit dashboard: time by category per day, learning share by week, hour-by-day heatmap, top creators, platform split. `demo_data.py` builds a sample database to try it on. | passing |
| FR-14 | Drill-downs: clicking a category, heatmap cell or creator lists the videos behind it, each linking back to the video at its start time. Date range and platforms live in the URL, so a view survives a refresh and can be bookmarked. | todo |

Dashboard states (FR-07). Each row has a test; numbers carry only labels they support.

| State | What the page shows |
|---|---|
| No database file | How to log a link or build the sample; the file is not created. |
| Database with no viewings | How to log a link. |
| Nothing in the picked dates or platforms | "Nothing watched in this range." |
| Sample data (labels from `demo_data.py`) | A banner saying it is made-up data, above everything else. |
| Some viewings unlabelled | They chart as Unlabelled, are left out of the learning share, and a caption says how to label them. |
| Nothing labelled | Learning share shows n/a. |
| Week only partly inside the range | Drawn dashed, labelled "so far", so a short week doesn't read as a drop. |
| Time | Labelled "time logged": from the link's start time to the end of the video (FR-03), not measured viewing. |
| Known figures | The sample built with a fixed seed and end date reproduces exact totals, so a change to the numbers is caught. |

## Phase 4: Ask your history

| ID | Requirement | Status |
|---|---|---|
| FR-08 | Split transcripts into ~500-token chunks that keep their start time, embed them with a multilingual model and store them in Chroma. | todo |
| FR-09 | Answer questions from the top-k chunks, citing video and timestamp. Each citation quotes the transcript, and a quote not found in the retrieved chunk is marked unverified. The answer shape (text plus citations) is defined in one place. A short design note and mockup of the chat page are agreed before code. | todo |

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
| NFR-05 | Every LLM feature has a small fixed test set and a pass bar before a model becomes its default: ~30 hand-labelled videos for FR-06, ~15 questions with known answer videos for FR-09. Each model tried gets a results row. | todo |
