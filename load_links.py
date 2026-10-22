"""Log watched videos from one link or a CSV of links.

Usage:
    python load_links.py --url "https://www.youtube.com/watch?v=DCYaJb8Bzdk&t=40s"
    python load_links.py --csv my_links.csv

The CSV needs a `url` column and may have a `watched_at` column (e.g. 2026-10-14 21:40).
Each viewing is saved to the SQLite database in data/content_diet.db.
"""
import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yt_dlp

from ingest.transcript import fetch_transcript
from store import db

SUPPORTED_HOSTS = ("youtube.com", "youtu.be", "instagram.com")


def is_supported(url):
    host = urlparse(url).netloc.lower()
    return any(host == h or host.endswith("." + h) for h in SUPPORTED_HOSTS)


def start_offset(url):
    """Seconds from a t=40 or t=40s parameter, 0 if absent."""
    t = parse_qs(urlparse(url).query).get("t", ["0"])[0].removesuffix("s")
    return int(t) if t.isdigit() else 0


def extract_metadata(url):
    # Metadata only: don't fail when YouTube hides the video formats.
    # The connection to YouTube drops mid-request on this network (SSL EOF), so retry more
    # than yt-dlp's default 3 times before giving up.
    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "noplaylist": True, "ignore_no_formats_error": True,
            "retries": 10, "extractor_retries": 10}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info.get("duration"):  # YouTube sometimes returns partial info; don't log 0 minutes
        raise ValueError("no duration returned; run again (already-logged links are skipped)")
    return {
        "video_id": info.get("id"),
        "platform": (info.get("extractor_key") or "").lower(),
        "url": info.get("webpage_url") or url,
        "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "duration_sec": int(info["duration"]),
        "language": info.get("language"),
        "tags": info.get("tags") or [],
        "description": info.get("description") or "",
    }


def log_viewing(url, watched_at=None):
    if not is_supported(url):
        raise ValueError("only YouTube and Instagram links are supported")
    meta = extract_metadata(url)
    offset = start_offset(url)
    when = datetime.fromisoformat(watched_at) if watched_at else datetime.now()
    return {
        **meta,
        "watched_at": when.isoformat(timespec="seconds"),
        "start_offset_sec": offset,
        "watched_sec": max(meta["duration_sec"] - offset, 0),
    }


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel CSVs
        reader = csv.DictReader(f)
        if "url" not in (reader.fieldnames or []):
            sys.exit(f"{path} needs a 'url' column. Found: {reader.fieldnames}")
        return [(row["url"].strip(), (row.get("watched_at") or "").strip() or None)
                for row in reader if (row["url"] or "").strip()]


def add_transcript(conn, rec):
    """FR-05: fetch captions once per YouTube video. Failing here never fails the viewing."""
    if rec["platform"] != "youtube" or db.has_transcript(conn, rec["video_id"]):
        return
    try:
        t = fetch_transcript(rec["video_id"], rec.get("language"))
    except Exception as e:
        print(f"      transcript failed, will retry next run: {str(e).splitlines()[0][:100]}")
        return
    db.save_transcript(conn, rec["video_id"], t)
    if t:
        kind = "auto" if t["is_generated"] else "manual"
        print(f"      transcript: {t['language']} ({kind}), {len(t['segments'])} lines")
    else:
        print("      transcript: none (no captions)")


def main(argv=None):
    # Titles and transcripts can be in Devanagari, which the Windows console can't encode.
    sys.stdout.reconfigure(errors="replace")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="a YouTube or Instagram link")
    src.add_argument("--csv", type=Path, help="CSV with a url column and optional watched_at")
    p.add_argument("--watched-at", help="when you watched it, e.g. 2026-10-14 21:40 (with --url)")
    p.add_argument("--db", type=Path, default=db.DEFAULT_DB, help="SQLite file (default data/content_diet.db)")
    args = p.parse_args(argv)
    if args.csv and args.watched_at:
        p.error("--watched-at only works with --url; put times in the CSV's watched_at column")

    rows = read_csv(args.csv) if args.csv else [(args.url.strip(), args.watched_at)]

    conn = db.connect(args.db)
    added = skipped = failed = 0
    for url, when in rows:
        try:  # one bad link shouldn't stop a bulk import
            rec = log_viewing(url, when)
            if db.save_viewing(conn, rec):
                added += 1
                print(f"  + {rec['title'] or url}  ({rec['watched_sec'] // 60} min)")
            else:
                skipped += 1
                print(f"  = {rec['title'] or url}  (already logged at {rec['watched_at']})")
            add_transcript(conn, rec)  # also backfills videos logged before FR-05
        except Exception as e:
            failed += 1
            print(f"  x {url}\n      {str(e).splitlines()[0]}")
    conn.close()

    print(f"\nAdded {added}, already logged {skipped}, failed {failed}. Database: {args.db}")
    return 1 if failed == len(rows) else 0


if __name__ == "__main__":
    sys.exit(main())
