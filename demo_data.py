"""Fill data/demo.db with four weeks of made-up, already-labelled viewings.

For building and trying the dashboard (FR-07) without real history, Ollama or
the network. Every channel and title is invented. Your real database
(data/content_diet.db) is never touched.

Usage:
    python demo_data.py                       # rebuild data/demo.db
    streamlit run app.py -- --db data/demo.db
"""
import argparse
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

from store import db

DEMO_DB = db.DEFAULT_DB.with_name("demo.db")
MODEL = "demo"  # the labels' model column; the dashboard shows a sample-data banner when it sees it

# (platform, title, channel, minutes, category, format, topic)
CATALOG = [
    ("youtube", "System Design Basics: Load Balancers", "Byte Sized Systems", 42, "Learning", "Lecture", "System Design"),
    ("youtube", "Database Sharding in 20 Minutes", "Byte Sized Systems", 21, "Learning", "Lecture", "Database Sharding"),
    ("youtube", "Caching Strategies Explained", "Byte Sized Systems", 35, "Learning", "Lecture", "Caching"),
    ("youtube", "Python Decorators From Scratch", "Code With Rhea", 18, "Learning", "Tutorial", "Python Decorators"),
    ("youtube", "Build a REST API With FastAPI", "Code With Rhea", 54, "Learning", "Tutorial", "FastAPI"),
    ("youtube", "SQL Window Functions, Hands-On", "Code With Rhea", 27, "Learning", "Tutorial", "SQL"),
    ("youtube", "How Transformers Actually Work", "Neural Notes", 38, "Learning", "Lecture", "Transformers"),
    ("youtube", "RAG in Plain Language", "Neural Notes", 24, "Learning", "Lecture", "RAG"),
    ("youtube", "Founders on Burnout | Ep. 41", "The Long Table", 72, "Learning", "Podcast", "Startups"),
    ("youtube", "Money Habits in Your 20s | Ep. 42", "The Long Table", 65, "Learning", "Podcast", "Personal Finance"),
    ("youtube", "20-Min Full Body Workout, No Equipment", "Move Daily", 20, "Fitness", "Tutorial", "Home Workout"),
    ("youtube", "Morning Mobility Routine", "Move Daily", 12, "Fitness", "Tutorial", "Mobility"),
    ("youtube", "Weekly Market Wrap", "Ledger Live News", 16, "News", "News report", "Markets"),
    ("youtube", "Tech Headlines This Week", "Ledger Live News", 14, "News", "News report", "Tech News"),
    ("youtube", "Street Food Tour, Old City", "Wander Plates", 23, "Entertainment", "Vlog", "Street Food"),
    ("youtube", "I Tried Every Instant Noodle", "Wander Plates", 19, "Entertainment", "Review", "Food Review"),
    ("youtube", "Stand-Up Special: Office Life", "Laugh Track Club", 31, "Entertainment", "Comedy", "Stand-Up"),
    ("youtube", "Speedrun Fails Compilation", "Pixel Panic", 17, "Entertainment", "Comedy", "Gaming"),
    ("youtube", "Acoustic Evening Live Session", "Quiet Strings", 26, "Music", "Performance", "Acoustic"),
    ("youtube", "Lo-fi Beats to Study To", "Quiet Strings", 60, "Music", "Performance", "Lo-fi"),
    ("instagram", "POV: debugging at 2am", "devmemes.daily", 0.4, "Entertainment", "Comedy", "Dev Memes"),
    ("instagram", "When the code works first try", "devmemes.daily", 0.3, "Entertainment", "Comedy", "Dev Memes"),
    ("instagram", "Cat vs cucumber, round 3", "pawsandclaws", 0.3, "Entertainment", "Comedy", "Pets"),
    ("instagram", "Dog learns to open the fridge", "pawsandclaws", 0.5, "Entertainment", "Comedy", "Pets"),
    ("instagram", "3 Python tricks in 30 seconds", "code.with.rhea", 0.5, "Learning", "Tutorial", "Python Tips"),
    ("instagram", "Git commands you forget", "code.with.rhea", 0.6, "Learning", "Tutorial", "Git"),
    ("instagram", "60-second ab burner", "move.daily", 1.0, "Fitness", "Tutorial", "Core Workout"),
    ("instagram", "Biryani in one pot", "wanderplates", 0.8, "Entertainment", "Vlog", "Cooking"),
    ("instagram", "Guitar riff of the day", "quietstrings", 0.4, "Music", "Performance", "Guitar"),
    ("instagram", "Prank on my roommate", "laughtrackclub", 0.5, "Entertainment", "Comedy", "Pranks"),
]


def videos():
    out = []
    for i, (platform, title, channel, minutes, category, fmt, topic) in enumerate(CATALOG, 1):
        video_id = f"demo-{'yt' if platform == 'youtube' else 'ig'}-{i:02d}"
        out.append({
            "video_id": video_id, "platform": platform,
            "url": f"https://example.com/{video_id}", "title": title, "channel": channel,
            "duration_sec": round(minutes * 60), "language": "en", "tags": [], "description": "",
            "labels": {"category": category, "format": fmt, "topic": topic},
        })
    return out


def sessions(day, rng):
    """(start time, pool of categories, platform, how many videos) for one day."""
    weekend = day.weekday() >= 5
    out = []
    if rng.random() < 0.5:
        out.append((time(7, rng.randint(0, 40)), {"Fitness", "News"}, "youtube", 1))
    if not weekend and rng.random() < 0.6:
        out.append((time(13, rng.randint(0, 30)), {"News", "Music"}, "youtube", 1))
    if rng.random() < (0.5 if weekend else 0.75):
        out.append((time(rng.choice([19, 20, 21]), rng.randint(0, 50)), {"Learning"}, "youtube", rng.randint(1, 2)))
    if weekend or rng.random() < 0.3:
        out.append((time(rng.choice([15, 16, 22]), rng.randint(0, 50)), {"Entertainment", "Music"}, "youtube", rng.randint(1, 3)))
    if rng.random() < (0.9 if weekend else 0.7):
        out.append((time(23, rng.randint(0, 45)), None, "instagram", rng.randint(8, 25)))
    return out


def viewings(days=28, end=None, seed=7):
    """Viewing records for load into store.db, in the shape load_links.py produces."""
    rng = random.Random(seed)
    catalog = videos()
    end = end or date.today()
    out = []
    for offset in range(days, 0, -1):
        day = end - timedelta(days=offset - 1)
        for start, categories, platform, count in sessions(day, rng):
            pool = [v for v in catalog if v["platform"] == platform
                    and (categories is None or v["labels"]["category"] in categories)]
            at = datetime.combine(day, start)
            for _ in range(count):
                v = rng.choice(pool)
                # Long videos are often abandoned part-way; reels are watched to the end.
                share = 1.0 if platform == "instagram" else rng.choice([1.0, 1.0, 0.8, 0.5, 0.3])
                watched = max(10, round(v["duration_sec"] * share))
                out.append({**v, "watched_at": at.isoformat(timespec="seconds"),
                            "start_offset_sec": 0, "watched_sec": watched})
                at += timedelta(seconds=watched + rng.randint(5, 120))
    return out


def build(path=DEMO_DB, days=28, seed=7, end=None):
    path = Path(path)
    if path.resolve() == db.DEFAULT_DB.resolve():
        raise SystemExit("Refusing to overwrite your real database; pick another --db.")
    path.unlink(missing_ok=True)
    conn = db.connect(path)
    recs = viewings(days, end=end, seed=seed)
    for rec in recs:
        db.save_viewing(conn, rec)
    watched = {rec["video_id"] for rec in recs}
    for v in videos():
        if v["video_id"] in watched:  # a video never picked has no row to label
            db.save_labels(conn, v["video_id"], v["labels"], model=MODEL)
    conn.close()
    return len(recs)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build a demo database of made-up viewings.")
    parser.add_argument("--db", default=DEMO_DB, help=f"output file (default: {DEMO_DB})")
    parser.add_argument("--days", type=int, default=28, help="days of history ending today")
    args = parser.parse_args(argv)
    n = build(args.db, args.days)
    print(f"Wrote {n} viewings of {len(CATALOG)} videos to {args.db}")
    print(f"View it: streamlit run app.py -- --db {args.db}")


if __name__ == "__main__":
    main()
