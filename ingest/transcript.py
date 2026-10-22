"""Fetch a YouTube video's captions with timestamps (FR-05)."""
import time

from youtube_transcript_api import (NoTranscriptFound, TranscriptsDisabled,
                                    VideoUnavailable, YouTubeTranscriptApi)

NO_CAPTIONS = (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable)


def pick(transcripts, language=None):
    """Prefer manual captions over auto-generated, and the video's own language over others."""
    return min(transcripts, key=lambda t: (t.is_generated, t.language_code != language))


def fetch_transcript(video_id, language=None, attempts=4):
    """Return {language, is_generated, segments: [{start, duration, text}]}, or None if the
    video has no captions. Network errors are retried, then raised."""
    api = YouTubeTranscriptApi()
    for attempt in range(1, attempts + 1):
        try:
            available = list(api.list(video_id))
            if not available:
                return None
            chosen = pick(available, language)
            fetched = chosen.fetch()
            break
        except NO_CAPTIONS:
            return None
        except Exception:
            # The connection to YouTube drops mid-request on this network (SSL EOF).
            if attempt == attempts:
                raise
            time.sleep(2 * attempt)
    return {
        "language": chosen.language_code,
        "is_generated": chosen.is_generated,
        "segments": [{"start": round(s.start, 2), "duration": round(s.duration, 2), "text": s.text}
                     for s in fetched.snippets],
    }
