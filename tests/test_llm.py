"""The LLM switch (FR-06). Ollama and Anthropic are both stubbed (NFR-04)."""
import io
import json
import sys
import urllib.error
from types import SimpleNamespace as NS

import pytest

import llm

SCHEMA = {"type": "object", "properties": {"category": {"type": "string"}},
          "required": ["category"], "additionalProperties": False}


def test_setting_order_env_then_dotenv_then_default(monkeypatch):
    assert llm.setting("OLLAMA_MODEL") == "phi4-mini"
    llm.ENV_FILE.write_text("# comment\nOLLAMA_MODEL=qwen2.5:3b\nANTHROPIC_API_KEY=\n", encoding="utf-8")
    assert llm.setting("OLLAMA_MODEL") == "qwen2.5:3b"
    assert llm.setting("ANTHROPIC_API_KEY") is None          # empty value counts as unset
    monkeypatch.setenv("OLLAMA_MODEL", "gemma3:4b")
    assert llm.setting("OLLAMA_MODEL") == "gemma3:4b"


def test_ollama_sends_schema_and_returns_dict(monkeypatch):
    sent = {}

    def fake_urlopen(request, timeout):
        sent["url"], sent["body"] = request.full_url, json.loads(request.data)
        return io.BytesIO(json.dumps({"message": {"content": '{"category": "Learning"}'}}).encode())

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    assert llm.complete_json("Classify", SCHEMA) == {"category": "Learning"}
    assert sent["url"] == "http://127.0.0.1:11434/api/chat"
    assert sent["body"]["model"] == "phi4-mini"
    assert sent["body"]["format"] == SCHEMA
    assert sent["body"]["options"]["temperature"] == 0


def test_ollama_not_running_is_unavailable(monkeypatch):
    def refused(request, timeout):
        raise urllib.error.URLError(ConnectionRefusedError("refused"))

    monkeypatch.setattr(llm.urllib.request, "urlopen", refused)
    with pytest.raises(llm.LLMUnavailable, match="isn't running"):
        llm.complete_json("Classify", SCHEMA)


def test_ollama_missing_model_says_how_to_pull(monkeypatch):
    def not_found(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "not found", {}, io.BytesIO(b""))

    monkeypatch.setattr(llm.urllib.request, "urlopen", not_found)
    with pytest.raises(llm.LLMUnavailable, match="ollama pull phi4-mini"):
        llm.complete_json("Classify", SCHEMA)


def test_invalid_json_is_an_item_error(monkeypatch):
    monkeypatch.setattr(llm.urllib.request, "urlopen", lambda request, timeout: io.BytesIO(
        json.dumps({"message": {"content": "Learning, I think"}}).encode()))
    with pytest.raises(llm.LLMError) as err:
        llm.complete_json("Classify", SCHEMA)
    assert not isinstance(err.value, llm.LLMUnavailable)


def test_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    with pytest.raises(llm.LLMUnavailable, match="ollama' or 'anthropic"):
        llm.complete_json("Classify", SCHEMA)


class FakeAnthropic:
    """Stands in for the anthropic package; records the request and returns a canned reply."""
    class APIError(Exception):
        message = "error"
    AuthenticationError = PermissionDeniedError = NotFoundError = APIConnectionError = APIStatusError = APIError

    def __init__(self, reply="{\"category\": \"Learning\"}", stop_reason="end_turn"):
        self.reply, self.stop_reason, self.calls = reply, stop_reason, []

    def Anthropic(self, api_key=None):
        return NS(messages=NS(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return NS(stop_reason=self.stop_reason, content=[NS(type="text", text=self.reply)])


def test_anthropic_uses_structured_output(monkeypatch):
    fake = FakeAnthropic()
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert llm.complete_json("Classify", SCHEMA) == {"category": "Learning"}
    [call] = fake.calls
    assert call["model"] == "claude-haiku-5-5"
    assert call["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA}
    assert llm.model_name() == "claude-haiku-5-5"


def test_anthropic_refusal_is_an_item_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", FakeAnthropic(reply="", stop_reason="refusal"))
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    with pytest.raises(llm.LLMError, match="declined"):
        llm.complete_json("Classify", SCHEMA)
