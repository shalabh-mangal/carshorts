"""The LLMClient adapter — the only model dependency the pipeline knows about.

The pipeline never imports Gemini or Ollama directly. It depends on this
interface. Swapping providers (or upgrading from a free tier to a paid model)
is a one-line change in the composition root, never a change in a stage.

Two implementations ship in Milestone 1:
  - MockLLMClient: deterministic, used in tests, no network, no cost.
  - GeminiLLMClient: real, free-tier. (Ollama would be a third, same shape.)

`complete_json` exists because every structured stage (ranking, fact-check)
needs validated JSON back. We ask the model for raw JSON, strip any markdown
fences, and parse. Stages then validate into Pydantic models.
"""
from __future__ import annotations

import json
import os
import re
import ssl
import urllib.request
from abc import ABC, abstractmethod

# Shared TLS context (macOS python.org builds don't find the system CA store).
try:
    import certifi

    _SSL_CONTEXT: ssl.SSLContext | None = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = None


class LLMClient(ABC):
    @abstractmethod
    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        """Return the model's text response.

        json_mode asks the provider to guarantee syntactically valid JSON where
        it supports that (Gemini's response_mime_type). It is the reliable fix
        for models emitting JSON with unescaped quotes inside strings, which no
        amount of post-hoc regex cleanup can safely repair.
        """

    def complete_json(self, system: str, user: str) -> dict | list:
        """Return parsed JSON. Strips ```json fences and preamble defensively.

        Real models return either an object or an array, sometimes wrapped in
        prose or markdown fences. We locate whichever bracket opens first ({ or
        [), slice to its matching last close, and strip trailing commas — the
        two failure modes that crash json.loads on otherwise-fine model output.
        A naive "first { to last }" regex silently corrupts array responses by
        dropping the enclosing brackets, so bracket TYPE is chosen by position.
        """
        raw = self.complete(system, user, json_mode=True)
        cleaned = re.sub(r"```(?:json)?", "", raw).strip()

        obj_at = cleaned.find("{")
        arr_at = cleaned.find("[")
        if arr_at != -1 and (obj_at == -1 or arr_at < obj_at):
            start, end = arr_at, cleaned.rfind("]")
        elif obj_at != -1:
            start, end = obj_at, cleaned.rfind("}")
        else:
            start, end = -1, -1
        if start != -1 and end > start:
            cleaned = cleaned[start:end + 1]

        # Trailing commas before a closing bracket are invalid JSON but common
        # in model output: {"a":1,} / [1,2,].
        cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Model returned unparseable JSON ({exc}). First 200 chars: "
                f"{cleaned[:200]!r}"
            ) from exc


class MockLLMClient(LLMClient):
    """Deterministic client for tests. Returns canned responses keyed by a
    substring of the user prompt, so tests never hit the network or spend
    tokens."""

    def __init__(self, responses: dict[str, str]):
        # responses maps a substring -> the response to return when that
        # substring appears in the user prompt.
        self._responses = responses

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        for needle, response in self._responses.items():
            if needle in user:
                return response
        raise KeyError(
            f"MockLLMClient had no canned response matching prompt: {user[:120]!r}"
        )


class GeminiLLMClient(LLMClient):
    """Real free-tier client. Imported lazily so tests don't need the SDK."""

    def __init__(self, model: str = "gemini-2.5-flash", api_key: str | None = None):
        self._model_name = model
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self._model = None  # lazy init

    def _ensure(self):
        if self._model is None:
            import google.generativeai as genai  # type: ignore

            genai.configure(api_key=self._api_key)
            self._model = genai.GenerativeModel(self._model_name)

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        self._ensure()
        generation_config = {"response_mime_type": "application/json"} if json_mode else None
        resp = self._model.generate_content(
            f"{system}\n\n{user}",
            generation_config=generation_config,
        )
        return resp.text


class OpenAICompatLLMClient(LLMClient):
    """One client for every OpenAI-compatible endpoint — which is most of the
    free world: Groq, Cerebras, OpenRouter, and a LOCAL Ollama server all speak
    this same /chat/completions format. Swap provider = change base_url + model
    + key. No SDK needed; we POST JSON with urllib.

    Examples:
      Ollama (local, free, unlimited): base_url=http://localhost:11434/v1
      Groq (free, ~1000/day, Llama 70B): base_url=https://api.groq.com/openai/v1
    """

    def __init__(self, base_url: str, model: str, api_key: str | None = None, timeout: int = 180):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.7,
        }
        if json_mode:
            # Honored by Groq/OpenRouter/Ollama; ignored elsewhere (our parser copes).
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json",
            # Cloudflare (in front of Groq etc.) 403s the default Python-urllib
            # user-agent as a bot, so send a real one.
            "User-Agent": "carshorts/0.1",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=self.timeout, context=_SSL_CONTEXT) as resp:
            body = json.load(resp)
        return body["choices"][0]["message"]["content"]


class FallbackLLMClient(LLMClient):
    """Tries providers in order; a provider outage never blocks a render."""

    def __init__(self, clients: list[tuple[str, LLMClient]]):
        self.clients = clients

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        last_error: Exception | None = None
        for name, client in self.clients:
            try:
                return client.complete(system, user, json_mode=json_mode)
            except Exception as exc:  # noqa: BLE001 — fall through the chain
                print(f"     LLM fallback: {name} failed ({str(exc)[:80]}); trying next")
                last_error = exc
        raise last_error or RuntimeError("no LLM providers available")


def make_llm(provider: str | None = None, model: str | None = None) -> LLMClient:
    """Pick an LLM backend by name (or the CARSHORTS_LLM env var).

    gemini   — Google, free tier (this project's key is capped at 20/day)
    groq     — free, ~1000 req/day, Llama 3.3 70B, fast (needs GROQ_API_KEY)
    cerebras — free, ~1M tokens/day (needs CEREBRAS_API_KEY)
    openrouter — free models, one key many models (needs OPENROUTER_API_KEY)
    ollama   — local, free, unlimited, offline (needs a pulled model)
    """
    if provider is None and not os.environ.get("CARSHORTS_LLM"):
        # no explicit choice -> resilient chain from whatever keys exist
        chain: list[tuple[str, LLMClient]] = []
        if os.environ.get("GROQ_API_KEY"):
            chain.append(("groq", make_llm("groq", model)))
        if os.environ.get("GEMINI_API_KEY"):
            chain.append(("gemini", make_llm("gemini", model)))
        chain.append(("ollama", make_llm("ollama", model)))
        if len(chain) > 1:
            return FallbackLLMClient(chain)
    provider = (provider or os.environ.get("CARSHORTS_LLM", "gemini")).lower()
    if provider == "gemini":
        return GeminiLLMClient(model=model or "gemini-2.5-flash")
    if provider == "ollama":
        return OpenAICompatLLMClient(
            "http://localhost:11434/v1",
            model or os.environ.get("OLLAMA_MODEL", "qwen2.5:7b"),
        )
    if provider == "groq":
        return OpenAICompatLLMClient(
            "https://api.groq.com/openai/v1",
            model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
            api_key=os.environ.get("GROQ_API_KEY"),
        )
    if provider == "cerebras":
        return OpenAICompatLLMClient(
            "https://api.cerebras.ai/v1",
            model or os.environ.get("CEREBRAS_MODEL", "llama-3.3-70b"),
            api_key=os.environ.get("CEREBRAS_API_KEY"),
        )
    if provider == "openrouter":
        return OpenAICompatLLMClient(
            "https://openrouter.ai/api/v1",
            model or os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
            api_key=os.environ.get("OPENROUTER_API_KEY"),
        )
    raise ValueError(f"Unknown LLM provider: {provider!r}")
