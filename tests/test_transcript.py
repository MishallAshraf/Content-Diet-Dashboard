"""FR-05: choosing and fetching captions. The transcript API is stubbed (NFR-04)."""
from types import SimpleNamespace as NS

import pytest
from youtube_transcript_api import TranscriptsDisabled

from ingest import transcript


def caption(code, generated, lines=(("नमस्ते", 0.4),)):
    snippets = [NS(text=t, start=s, duration=2.0) for t, s in lines]
    return NS(language_code=code, is_generated=generated, fetch=lambda: NS(snippets=snippets))


class FakeApi:
    """Stands in for YouTubeTranscriptApi: list() fails `failures` times, then returns `available`."""
    def __init__(self, available, failures=0, error=ConnectionError("SSL EOF")):
        self.available, self.failures, self.error, self.calls = available, failures, error, 0

    def __call__(self):
        return self

    def list(self, video_id):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        return self.available


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(transcript.time, "sleep", lambda s: None)


def test_pick_prefers_manual_then_video_language():
    en_auto, hi_auto, en_manual = caption("en", True), caption("hi", True), caption("en", False)
    assert transcript.pick([en_auto, hi_auto], language="hi") is hi_auto
    assert transcript.pick([hi_auto, en_manual], language="hi") is en_manual


def test_fetch_returns_segments_with_timestamps(monkeypatch):
    monkeypatch.setattr(transcript, "YouTubeTranscriptApi",
                        FakeApi([caption("hi", True, (("नमस्ते", 0.4), ("CAP theorem", 61.0)))]))
    t = transcript.fetch_transcript("DCYaJb8Bzdk", language="hi")
    assert t["language"] == "hi" and t["is_generated"] is True
    assert t["segments"] == [{"start": 0.4, "duration": 2.0, "text": "नमस्ते"},
                             {"start": 61.0, "duration": 2.0, "text": "CAP theorem"}]


def test_fetch_retries_dropped_connections(monkeypatch):
    api = FakeApi([caption("hi", True)], failures=2)
    monkeypatch.setattr(transcript, "YouTubeTranscriptApi", api)
    assert transcript.fetch_transcript("DCYaJb8Bzdk") is not None
    assert api.calls == 3


def test_fetch_gives_up_after_attempts(monkeypatch):
    monkeypatch.setattr(transcript, "YouTubeTranscriptApi", FakeApi([], failures=10))
    with pytest.raises(ConnectionError):
        transcript.fetch_transcript("DCYaJb8Bzdk", attempts=3)


def test_no_captions_returns_none_without_retrying(monkeypatch):
    api = FakeApi([], failures=10, error=TranscriptsDisabled("DCYaJb8Bzdk"))
    monkeypatch.setattr(transcript, "YouTubeTranscriptApi", api)
    assert transcript.fetch_transcript("DCYaJb8Bzdk") is None
    assert api.calls == 1
