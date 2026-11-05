"""FR-06: label each video with a category, format and topic using the LLM.

Usage:
    python -m ingest.classify          # classify every video that has no labels yet

Runs separately from load_links.py because a local model takes ~10 s per video
(about a minute for the first one while the model loads).
"""
import argparse
import sys
import time
from pathlib import Path

import llm
from store import db

CATEGORIES = {
    "Learning": "teaches a skill or explains a subject: tutorials, lectures, explainers",
    "Entertainment": "comedy, films, gaming, vlogs, memes, reaction videos",
    "Fitness": "workouts, sports training, health and diet routines",
    "News": "current events, politics, business and market updates",
    "Music": "songs, music videos, live performances",
    "Other": "none of the above",
}
FORMATS = ["Lecture", "Tutorial", "Podcast", "Vlog", "Review", "Comedy",
           "Performance", "News report", "Other"]

SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": list(CATEGORIES)},
        "format": {"type": "string", "enum": FORMATS},
        "topic": {"type": "string"},
    },
    "required": ["category", "format", "topic"],
    "additionalProperties": False,
}


def build_prompt(video, transcript_start=""):
    categories = "\n".join(f"  {name}: {meaning}" for name, meaning in CATEGORIES.items())
    lines = [
        "Classify one video someone watched. Answer with JSON only.",
        f"category, what the video is for the viewer:\n{categories}",
        f"format: one of {', '.join(FORMATS)}",
        'topic: 1 to 4 English words naming the main subject, e.g. "System design".',
        "",
        f"Title: {video['title'] or ''}",
        f"Channel: {video['channel'] or ''}",
        f"Tags: {', '.join(video['tags'][:15])}",
        f"Description: {video['description'][:600]}",
    ]
    if transcript_start:
        lines.append(f"Transcript start: {transcript_start}")
    return "\n".join(lines)


def classify(video, transcript_start=""):
    """Return {category, format, topic}. Values outside the allowed lists become Other."""
    answer = llm.complete_json(build_prompt(video, transcript_start), SCHEMA)
    category = answer.get("category") if answer.get("category") in CATEGORIES else "Other"
    fmt = answer.get("format") if answer.get("format") in FORMATS else "Other"
    topic = " ".join(str(answer.get("topic") or "").split()[:4]) or None
    return {"category": category, "format": fmt, "topic": topic}


def main(argv=None):
    sys.stdout.reconfigure(errors="replace")
    p = argparse.ArgumentParser(description="Label videos with a category, format and topic.")
    p.add_argument("--db", type=Path, default=db.DEFAULT_DB, help="SQLite file (default data/content_diet.db)")
    args = p.parse_args(argv)

    conn = db.connect(args.db)
    videos = db.unlabelled_videos(conn)
    if not videos:
        print("Every video already has labels.")
        return 0
    print(f"Classifying {len(videos)} video(s) with {llm.setting('LLM_PROVIDER')} / {llm.model_name()}")

    done = failed = 0
    for video in videos:
        # Hindi captions are Devanagari Hinglish; only use them when there's little else to go on.
        transcript_start = "" if len(video["description"]) >= 100 else db.transcript_text(conn, video["video_id"], 400)
        started = time.time()
        try:
            labels = classify(video, transcript_start)
        except llm.LLMUnavailable as e:
            print(f"\nStopped: {e}")
            return 1
        except llm.LLMError as e:
            failed += 1
            print(f"  x {video['title'] or video['video_id']}\n      {e}")
            continue
        db.save_labels(conn, video["video_id"], labels, llm.model_name())
        done += 1
        print(f"  + {video['title'] or video['video_id']}\n      {labels['category']} | "
              f"{labels['format']} | {labels['topic']}  ({time.time() - started:.0f} s)")

    print(f"\nLabelled {done}, failed {failed}. Database: {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
