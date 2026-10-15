"""Log watched videos from one link or a CSV of links.

Usage:
    python load_links.py --url "https://www.youtube.com/watch?v=DCYaJb8Bzdk&t=40s"
    python load_links.py --csv my_links.csv

The CSV needs a `url` column and may have a `watched_at` column (e.g. 2026-10-14 21:40).
Each viewing is appended to data/watch_log.jsonl as one JSON line.
"""
import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yt_dlp

SUPPORTED_HOSTS = ("youtube.com", "youtu.be", "instagram.com")
DEFAULT_OUT = Path(__file__).resolve().parent / "data" / "watch_log.jsonl"


def is_supported(url):
    host = urlparse(url).netloc.lower()
    return any(host == h or host.endswith("." + h) for h in SUPPORTED_HOSTS)


def start_offset(url):
    """Seconds from a t=40 or t=40s parameter, 0 if absent."""
    t = parse_qs(urlparse(url).query).get("t", ["0"])[0].removesuffix("s")
    return int(t) if t.isdigit() else 0


def extract_metadata(url):
    # Metadata only: don't fail when YouTube hides the video formats.
    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "noplaylist": True, "ignore_no_formats_error": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "video_id": info.get("id"),
        "platform": (info.get("extractor_key") or "").lower(),
        "url": info.get("webpage_url") or url,
        "title": info.get("title"),
        "channel": info.get("channel") or info.get("uploader"),
        "duration_sec": info.get("duration") or 0,
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


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="a YouTube or Instagram link")
    src.add_argument("--csv", type=Path, help="CSV with a url column and optional watched_at")
    p.add_argument("--watched-at", help="when you watched it, e.g. 2026-10-14 21:40 (with --url)")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = p.parse_args(argv)
    if args.csv and args.watched_at:
        p.error("--watched-at only works with --url; put times in the CSV's watched_at column")

    rows = read_csv(args.csv) if args.csv else [(args.url.strip(), args.watched_at)]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    failed = 0
    with open(args.out, "a", encoding="utf-8") as out:
        for url, when in rows:
            try:  # one bad link shouldn't stop a bulk import
                rec = log_viewing(url, when)
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                print(f"  + {rec['title'] or url}  ({rec['watched_sec'] // 60} min)")
            except Exception as e:
                failed += 1
                print(f"  x {url}\n      {str(e).splitlines()[0]}")

    print(f"\nLogged {len(rows) - failed} of {len(rows)} link(s) to {args.out}")
    return 1 if failed == len(rows) else 0


if __name__ == "__main__":
    sys.exit(main())
