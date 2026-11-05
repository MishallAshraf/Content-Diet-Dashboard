"""The one place LLM calls go through: local Ollama by default, Anthropic as a switch.

Set LLM_PROVIDER in .env (or the environment) to `ollama` or `anthropic`; see .env.example.
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent / ".env"

DEFAULTS = {
    "LLM_PROVIDER": "ollama",
    "OLLAMA_URL": "http://127.0.0.1:11434",
    "OLLAMA_MODEL": "phi4-mini",
    "ANTHROPIC_MODEL": "claude-haiku-5-5",
}


class LLMError(Exception):
    """The model answered badly or refused; skip this item and carry on."""


class LLMUnavailable(LLMError):
    """The provider can't be reached or isn't set up; stop the whole run."""


def setting(name):
    """Environment variable, else the value in .env, else the default."""
    if os.environ.get(name):
        return os.environ[name]
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == name and value.strip():
                return value.strip()
    return DEFAULTS.get(name)


def model_name():
    provider = setting("LLM_PROVIDER")
    return setting("ANTHROPIC_MODEL" if provider == "anthropic" else "OLLAMA_MODEL")


def complete_json(prompt, schema):
    """Send one prompt and return the model's answer as a dict matching `schema`."""
    provider = setting("LLM_PROVIDER")
    if provider == "ollama":
        text = _ollama(prompt, schema)
    elif provider == "anthropic":
        text = _anthropic(prompt, schema)
    else:
        raise LLMUnavailable(f"LLM_PROVIDER must be 'ollama' or 'anthropic', not {provider!r}")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise LLMError(f"model returned invalid JSON: {text[:120]!r}") from None


def _ollama(prompt, schema):
    url, model = setting("OLLAMA_URL"), setting("OLLAMA_MODEL")
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "format": schema,
        "stream": False,
        "keep_alive": "10m",  # loading the model takes ~60 s on the dev laptop; keep it warm
        "options": {"temperature": 0, "seed": 42, "num_ctx": 2048},
    }
    request = urllib.request.Request(f"{url}/api/chat", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.load(response)["message"]["content"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise LLMUnavailable(f"Ollama has no model {model!r}. Run: ollama pull {model}") from None
        raise LLMError(f"Ollama error {e.code}: {e.read()[:200]!r}") from None
    except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
        raise LLMUnavailable(
            f"Ollama isn't running at {url}. Start it (see CLAUDE.md, Stack). ({e})") from None


def _anthropic(prompt, schema):
    try:
        import anthropic
    except ImportError:
        raise LLMUnavailable('LLM_PROVIDER=anthropic needs: pip install -e ".[anthropic]"') from None
    client = anthropic.Anthropic(api_key=setting("ANTHROPIC_API_KEY"))
    try:
        response = client.messages.create(
            model=setting("ANTHROPIC_MODEL"),
            max_tokens=2048,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": prompt}],
        )
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError) as e:
        raise LLMUnavailable(f"Anthropic API: {e.message}") from None
    except anthropic.APIConnectionError:
        raise LLMUnavailable("can't reach the Anthropic API; check the network") from None
    except anthropic.APIStatusError as e:
        raise LLMError(f"Anthropic API error {e.status_code}: {e.message}") from None
    if response.stop_reason == "refusal":
        raise LLMError("the model declined to classify this video")
    return next((b.text for b in response.content if b.type == "text"), "")
