import pytest

import llm


@pytest.fixture(autouse=True)
def isolated_llm_settings(monkeypatch, tmp_path):
    """Tests never read the real .env or LLM environment variables."""
    monkeypatch.setattr(llm, "ENV_FILE", tmp_path / "no.env")
    for name in ("LLM_PROVIDER", "OLLAMA_URL", "OLLAMA_MODEL", "ANTHROPIC_MODEL", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
