"""FR-06: classifying videos. The LLM is stubbed (NFR-04)."""
import pytest

import llm
from ingest import classify
from store import db

VIDEO = {"video_id": "DCYaJb8Bzdk", "platform": "youtube", "url": "https://youtu.be/DCYaJb8Bzdk",
         "title": "EP-1 System Design Explained", "channel": "Ankit Jain", "duration_sec": 2597,
         "language": "hi", "tags": ["system design", "hld", "lld"],
         "description": "Master System Design from zero. " * 5}


def add_video(conn, **changes):
    video = dict(VIDEO, **changes)
    db.save_viewing(conn, dict(video, watched_at="2026-10-14T21:40:00", start_offset_sec=0, watched_sec=2597))
    return video


@pytest.fixture
def answers(monkeypatch):
    """Stub the LLM: returns queued answers and records each prompt."""
    state = {"queue": [], "prompts": []}

    def fake(prompt, schema):
        state["prompts"].append(prompt)
        answer = state["queue"].pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(llm, "complete_json", fake)
    return state


def test_prompt_has_metadata_and_categories():
    prompt = classify.build_prompt(VIDEO)
    assert "EP-1 System Design Explained" in prompt
    assert "system design, hld, lld" in prompt
    assert "Learning: teaches a skill" in prompt
    assert "Transcript start" not in prompt


def test_classify_keeps_valid_labels(answers):
    answers["queue"].append({"category": "Learning", "format": "Lecture", "topic": "System design"})
    assert classify.classify(VIDEO) == {"category": "Learning", "format": "Lecture", "topic": "System design"}


def test_classify_maps_invalid_values_to_other(answers):
    answers["queue"].append({"category": "Education", "format": "Course",
                             "topic": "distributed systems design for interviews"})
    assert classify.classify(VIDEO) == {"category": "Other", "format": "Other",
                                        "topic": "distributed systems design for"}


def test_fr06_main_labels_only_unlabelled_videos(answers, tmp_path):
    db_path = tmp_path / "t.db"
    conn = db.connect(db_path)
    add_video(conn)
    answers["queue"].append({"category": "Learning", "format": "Lecture", "topic": "System design"})

    assert classify.main(["--db", str(db_path)]) == 0
    assert classify.main(["--db", str(db_path)]) == 0          # second run: nothing left to do
    row = conn.execute("SELECT category, format, topic, model FROM labels").fetchone()
    assert tuple(row) == ("Learning", "Lecture", "System design", "phi4-mini")
    assert len(answers["prompts"]) == 1


def test_fr06_transcript_used_only_when_description_is_short(answers, tmp_path):
    db_path = tmp_path / "t.db"
    conn = db.connect(db_path)
    add_video(conn, description="")
    db.save_transcript(conn, "DCYaJb8Bzdk", {"language": "hi", "is_generated": True,
                                             "segments": [{"start": 0, "duration": 2, "text": "सिस्टम डिजाइन"}]})
    answers["queue"].append({"category": "Learning", "format": "Lecture", "topic": "System design"})
    classify.main(["--db", str(db_path)])
    assert "Transcript start: सिस्टम डिजाइन" in answers["prompts"][0]


def test_fr06_bad_answer_skips_video_and_continues(answers, tmp_path):
    db_path = tmp_path / "t.db"
    conn = db.connect(db_path)
    add_video(conn)
    add_video(conn, video_id="NAPO123", title="NAPO")
    answers["queue"] += [llm.LLMError("invalid JSON"),
                         {"category": "Entertainment", "format": "Other", "topic": "Animated film"}]
    assert classify.main(["--db", str(db_path)]) == 0
    assert [r[0] for r in conn.execute("SELECT video_id FROM labels")] == ["NAPO123"]


def test_fr06_unavailable_provider_stops_the_run(answers, tmp_path):
    db_path = tmp_path / "t.db"
    conn = db.connect(db_path)
    add_video(conn)
    add_video(conn, video_id="NAPO123", title="NAPO")
    answers["queue"] += [llm.LLMUnavailable("Ollama isn't running")]
    assert classify.main(["--db", str(db_path)]) == 1
    assert len(answers["prompts"]) == 1                          # didn't hammer a dead server
    assert conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0] == 0
