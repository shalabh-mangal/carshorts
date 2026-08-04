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
import threading
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

# Shared TLS context (macOS python.org builds don't find the system CA store).
try:
    import certifi

    _SSL_CONTEXT: ssl.SSLContext | None = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = None


# ---------------------------------------------------------------------------
# Robustness layer — every provider is a free/cheap tier with hard throttles,
# so a rate limit must NEVER silently corrupt output (a rate-limited critique
# once shipped a thin script scored on a pre-trim draft). We distinguish two
# failure modes, pace calls to stay under RPM, retry the transient ones, and
# circuit-break the dead ones so a burst degrades cleanly instead of thrashing.
# ---------------------------------------------------------------------------
class LLMRateLimit(Exception):
    """A TRANSIENT throttle — per-minute RPM/TPM or a 5xx. Safe to retry after
    `retry_after` seconds (honored from the server when it tells us)."""

    def __init__(self, msg: str = "rate limited", retry_after: float | None = None):
        super().__init__(msg)
        self.retry_after = retry_after


class LLMQuotaExhausted(Exception):
    """A HARD cap for this run — a per-DAY request/quota ceiling (e.g. Gemini
    free tier's 20 req/day). Retrying can't recover it, so the fallback chain
    disables this provider for the rest of the process instead of hammering it."""


# Metric fragments that mark a HARD per-day cap (vs a recoverable per-minute one).
_DAILY_MARKERS = ("perday", "requestsperday", "dailylimit", "perdayperproject")


def _parse_retry_after(text: str) -> float | None:
    """Pull a retry delay out of a provider error — either an HTTP-style
    'retry-after: N' or Google's 'retry_delay { seconds: N }'."""
    m = (re.search(r"retry.?after[\"']?\s*[:=]?\s*(\d+(?:\.\d+)?)", text, re.I)
         or re.search(r"retry_delay\s*\{?\s*seconds:?\s*(\d+)", text, re.I)
         or re.search(r"try again in\s+(\d+(?:\.\d+)?)\s*s", text, re.I))
    return float(m.group(1)) if m else None


def _classify_llm_error(exc: Exception, code: int | None = None, body: str = "") -> Exception:
    """Map a raw provider error to LLMRateLimit / LLMQuotaExhausted, or return it
    unchanged when it's not a throttle we recognise (caller re-raises as-is)."""
    s = (body or str(exc)).lower()
    is_429 = (code == 429 or "429" in s or "resource_exhausted" in s
              or "resourceexhausted" in s or "too many requests" in s or "quota" in s)
    is_5xx = (code is not None and 500 <= code < 600) or any(
        t in s for t in ("503", "500", "unavailable", "overloaded", "internal error"))
    if is_429:
        delay = _parse_retry_after(s)
        flat = s.replace("_", "").replace("-", "").replace(" ", "")
        # HARD when the metric names a per-day cap, or the message points at
        # billing with no short retry delay (Google's "check your plan and
        # billing details" is the daily-exhaustion wording).
        hard = any(m in flat for m in _DAILY_MARKERS) or ("billing" in s and not delay)
        if hard:
            return LLMQuotaExhausted(str(exc)[:200])
        return LLMRateLimit(str(exc)[:200], retry_after=delay)
    if is_5xx:
        return LLMRateLimit(str(exc)[:200])
    return exc


class _RateGate:
    """Process-wide minimum interval between calls per provider key — self-pacing
    so a burst (the Script Studio fires ~25 calls) stays under the RPM ceiling
    instead of tripping it. Thread-safe; a no-op when min_interval <= 0."""

    def __init__(self) -> None:
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, key: str, min_interval: float) -> None:
        if not min_interval or min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            delay = min_interval - (now - self._last.get(key, 0.0))
            if delay > 0:
                time.sleep(delay)
                now = time.monotonic()
            self._last[key] = now


_GATE = _RateGate()


def _paced_retry(call, key: str, min_interval: float, attempts: int = 4):
    """Pace to `min_interval`, run `call`, retry LLMRateLimit with backoff (honor
    the server's retry_after), and propagate LLMQuotaExhausted immediately so the
    fallback chain can disable a dead provider."""
    last: Exception | None = None
    for attempt in range(attempts):
        _GATE.wait(key, min_interval)
        try:
            return call()
        except LLMQuotaExhausted:
            raise
        except LLMRateLimit as exc:
            last = exc
            if attempt == attempts - 1:
                raise
            time.sleep(min(exc.retry_after or 3 * 2 ** attempt, 30))
    raise last or RuntimeError("unreachable")


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

    def __init__(self, model: str = "gemini-2.5-flash", api_key: str | None = None,
                 min_interval: float = 0.0):
        self._model_name = model
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self._model = None  # lazy init
        self._min_interval = min_interval

    def _ensure(self):
        if self._model is None:
            import google.generativeai as genai  # type: ignore

            genai.configure(api_key=self._api_key)
            self._model = genai.GenerativeModel(self._model_name)

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        self._ensure()
        generation_config = {"response_mime_type": "application/json"} if json_mode else None

        def _call() -> str:
            try:
                resp = self._model.generate_content(
                    f"{system}\n\n{user}", generation_config=generation_config)
                return resp.text
            except (LLMRateLimit, LLMQuotaExhausted):
                raise
            except Exception as exc:
                mapped = _classify_llm_error(exc)
                if mapped is exc:
                    raise
                raise mapped from exc

        return _paced_retry(_call, key=f"gemini:{self._model_name}",
                            min_interval=self._min_interval)


def gemini_vision(parts: list, json_mode: bool = True, model: str = "gemini-2.5-flash",
                  api_key: str | None = None, min_interval: float | None = None) -> str:
    """Multimodal Gemini call for the VQA/asset-vet/first-frame paths that pass
    FRAMES (PIL images) — which the text LLMClient can't take. Wrapped in the SAME
    pacing + retry + quota classification as the text path, and sharing the rate-gate
    key `gemini:<model>` so vision and text calls jointly respect the (tiny, 20/day)
    free quota instead of each racing it blind. `parts` is the SDK's list of
    str / PIL.Image parts. Returns the raw response text (caller parses)."""
    import google.generativeai as genai  # type: ignore

    genai.configure(api_key=api_key or os.environ.get("GEMINI_API_KEY"))
    m = genai.GenerativeModel(model)
    gen_cfg = {"response_mime_type": "application/json"} if json_mode else None
    interval = _min_interval("gemini", 13.0) if min_interval is None else min_interval

    def _call() -> str:
        try:
            return m.generate_content(parts, generation_config=gen_cfg).text
        except (LLMRateLimit, LLMQuotaExhausted):
            raise
        except Exception as exc:
            mapped = _classify_llm_error(exc)
            if mapped is exc:
                raise
            raise mapped from exc

    return _paced_retry(_call, key=f"gemini:{model}", min_interval=interval)


class OpenAICompatLLMClient(LLMClient):
    """One client for every OpenAI-compatible endpoint — which is most of the
    free world: Groq, Cerebras, OpenRouter, and a LOCAL Ollama server all speak
    this same /chat/completions format. Swap provider = change base_url + model
    + key. No SDK needed; we POST JSON with urllib.

    Examples:
      Ollama (local, free, unlimited): base_url=http://localhost:11434/v1
      Groq (free, ~1000/day, Llama 70B): base_url=https://api.groq.com/openai/v1
    """

    def __init__(self, base_url: str, model: str, api_key: str | None = None,
                 timeout: int = 180, min_interval: float = 0.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.min_interval = min_interval

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

        # Classify 429/5xx (transient vs hard daily cap) so the shared retry can
        # back off the recoverable ones and let the fallback chain disable the
        # dead ones — a burst degrades cleanly instead of thrashing every call.
        def _call() -> str:
            try:
                with urllib.request.urlopen(req, timeout=self.timeout, context=_SSL_CONTEXT) as resp:
                    body = json.load(resp)
                return body["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as exc:
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", "ignore")
                except Exception:  # noqa: BLE001 — body is best-effort context
                    pass
                mapped = _classify_llm_error(exc, code=exc.code, body=detail)
                if mapped is exc:
                    raise
                if isinstance(mapped, LLMRateLimit) and mapped.retry_after is None:
                    try:
                        mapped.retry_after = float(exc.headers.get("Retry-After", "") or 0) or None
                    except (TypeError, ValueError):
                        pass
                raise mapped from exc

        return _paced_retry(_call, key=f"{self.base_url}:{self.model}",
                            min_interval=self.min_interval)


class FallbackLLMClient(LLMClient):
    """Tries providers in order; a provider outage never blocks a render. A
    provider that hits a HARD daily cap (LLMQuotaExhausted) is disabled for the
    rest of the process — so a 25-call burst doesn't re-probe a dead free tier on
    every single call (that turned one generation into minutes of 429 thrash)."""

    def __init__(self, clients: list[tuple[str, LLMClient]]):
        self.clients = clients
        self._dead: set[str] = set()   # providers that exhausted their daily quota

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        last_error: Exception | None = None
        tried = 0
        for name, client in self.clients:
            if name in self._dead:
                continue
            tried += 1
            try:
                return client.complete(system, user, json_mode=json_mode)
            except LLMQuotaExhausted as exc:
                print(f"     LLM: {name} daily quota exhausted — disabling for this run")
                self._dead.add(name)
                last_error = exc
            except Exception as exc:  # noqa: BLE001 — fall through the chain
                print(f"     LLM fallback: {name} failed ({str(exc)[:80]}); trying next")
                last_error = exc
        if tried == 0:
            raise RuntimeError("all LLM providers exhausted their quota this run")
        raise last_error or RuntimeError("no LLM providers available")


def _min_interval(provider: str, default: float) -> float:
    """Per-provider min seconds between calls (RPM self-pacing). Override per
    provider via <PROVIDER>_MIN_INTERVAL — set to 0 once on a paid/Tier-1 plan
    with high RPM. Defaults are tuned for the measured FREE tiers."""
    try:
        return float(os.environ.get(f"{provider.upper()}_MIN_INTERVAL", default))
    except (TypeError, ValueError):
        return default


def make_llm(provider: str | None = None, model: str | None = None) -> LLMClient:
    """Pick an LLM backend by name (or the CARSHORTS_LLM env var).

    Free-tier ceilings are SMALL and are the real constraint (measured 2026-08):
    gemini   — 2.5 Flash FREE: 5 RPM / 250K TPM / **20 req/DAY** (billing -> Tier 1
               lifts this ~100x). Strong instructions/JSON. Needs GEMINI_API_KEY.
    groq     — FREE: 30 RPM but only **6k tokens/MINUTE** / 14.4k req/day, fast
               Llama 3.3 70B (needs GROQ_API_KEY). Low TPM -> our big prompts throttle.
    cerebras — FREE: ~1M tokens/day but an 8k context cap (needs CEREBRAS_API_KEY).
    openrouter — free models, one key many models (needs OPENROUTER_API_KEY).
    ollama   — local, free, UNLIMITED, offline (needs a pulled model + server up).

    Every client paces to stay under RPM, retries transient 429/5xx, and raises
    LLMQuotaExhausted on a hard daily cap so the fallback chain disables it.
    """
    if provider is None and not os.environ.get("CARSHORTS_LLM"):
        # no explicit choice -> resilient chain from whatever keys exist.
        # Order = quality-first with graceful degradation: Gemini (best
        # instructions, tiny daily quota) -> Groq (fast, TPM-throttled) ->
        # local Ollama (unlimited, weaker). The circuit breaker means once a
        # cloud tier is daily-exhausted we fall through to Ollama for free.
        chain: list[tuple[str, LLMClient]] = []
        if os.environ.get("GEMINI_API_KEY"):
            chain.append(("gemini", make_llm("gemini", model)))
        if os.environ.get("GROQ_API_KEY"):
            chain.append(("groq", make_llm("groq", model)))
        chain.append(("ollama", make_llm("ollama", model)))
        if len(chain) > 1:
            return FallbackLLMClient(chain)
    provider = (provider or os.environ.get("CARSHORTS_LLM", "gemini")).lower()
    if provider == "gemini":
        # 5 RPM free -> ~13s between calls keeps us under the per-minute ceiling.
        return GeminiLLMClient(model=model or "gemini-2.5-flash",
                               min_interval=_min_interval("gemini", 13.0))
    if provider == "ollama":
        return OpenAICompatLLMClient(
            "http://localhost:11434/v1",
            model or os.environ.get("OLLAMA_MODEL", "qwen2.5:7b"),
            min_interval=_min_interval("ollama", 0.0),   # local, no throttle
        )
    if provider == "groq":
        # 6k TPM with ~3-4k-token prompts -> ~2 calls/min; ~20s spacing avoids
        # most TPM 429s (the retry still covers the rest).
        return OpenAICompatLLMClient(
            "https://api.groq.com/openai/v1",
            model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
            api_key=os.environ.get("GROQ_API_KEY"),
            min_interval=_min_interval("groq", 20.0),
        )
    if provider == "cerebras":
        return OpenAICompatLLMClient(
            "https://api.cerebras.ai/v1",
            model or os.environ.get("CEREBRAS_MODEL", "llama-3.3-70b"),
            api_key=os.environ.get("CEREBRAS_API_KEY"),
            min_interval=_min_interval("cerebras", 2.0),
        )
    if provider == "openrouter":
        return OpenAICompatLLMClient(
            "https://openrouter.ai/api/v1",
            model or os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
            api_key=os.environ.get("OPENROUTER_API_KEY"),
            min_interval=_min_interval("openrouter", 2.0),
        )
    raise ValueError(f"Unknown LLM provider: {provider!r}")
