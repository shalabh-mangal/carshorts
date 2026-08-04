"""Offline tests for the LLM robustness layer (adapters/llm.py).

Every provider is a small free/cheap tier, so a throttle must degrade cleanly:
transient 429/5xx are retried; a hard per-day cap raises LLMQuotaExhausted and
the fallback chain disables that provider for the run. No network, no sleeping."""
import pytest

from carshorts.adapters import llm
from carshorts.adapters.llm import (
    FallbackLLMClient,
    LLMClient,
    LLMQuotaExhausted,
    LLMRateLimit,
    _classify_llm_error,
    _paced_retry,
)


# --- error classification -------------------------------------------------
def test_classify_daily_cap_is_hard():
    exc = Exception("429 ...GenerateRequestsPerDayPerProjectPerModel... quota")
    assert isinstance(_classify_llm_error(exc), LLMQuotaExhausted)


def test_classify_billing_message_is_hard():
    # Google's daily-exhaustion wording, no short retry delay -> hard cap.
    exc = Exception("429 You exceeded your current quota, please check your plan "
                    "and billing details.")
    assert isinstance(_classify_llm_error(exc), LLMQuotaExhausted)


def test_classify_per_minute_is_retriable_with_delay():
    exc = Exception("429 rate limit: requests per minute. retry_delay { seconds: 7 }")
    mapped = _classify_llm_error(exc)
    assert isinstance(mapped, LLMRateLimit) and mapped.retry_after == 7.0


def test_classify_5xx_is_retriable():
    assert isinstance(_classify_llm_error(Exception("503 Service Unavailable")),
                      LLMRateLimit)


def test_classify_unknown_passes_through():
    boom = ValueError("totally unrelated bug")
    assert _classify_llm_error(boom) is boom


# --- paced retry ----------------------------------------------------------
def test_paced_retry_recovers_after_transient(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda *_a: None)   # no real waiting
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise LLMRateLimit("slow down", retry_after=1)
        return "ok"

    assert _paced_retry(flaky, key="t", min_interval=0) == "ok"
    assert calls["n"] == 3


def test_paced_retry_does_not_retry_hard_cap(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda *_a: None)
    calls = {"n": 0}

    def dead():
        calls["n"] += 1
        raise LLMQuotaExhausted("20/day gone")

    with pytest.raises(LLMQuotaExhausted):
        _paced_retry(dead, key="t", min_interval=0)
    assert calls["n"] == 1          # hard caps are never retried


# --- fallback circuit breaker ---------------------------------------------
class _Client(LLMClient):
    def __init__(self, behaviour):
        self._b = behaviour
        self.calls = 0

    def complete(self, system, user, json_mode=False):
        self.calls += 1
        if isinstance(self._b, Exception):
            raise self._b
        return self._b


def test_fallback_disables_daily_exhausted_provider():
    dead = _Client(LLMQuotaExhausted("gemini 20/day gone"))
    live = _Client("from-groq")
    chain = FallbackLLMClient([("gemini", dead), ("groq", live)])

    assert chain.complete("s", "u") == "from-groq"
    # second call must SKIP the dead provider entirely (no re-probe thrash)
    assert chain.complete("s", "u") == "from-groq"
    assert dead.calls == 1 and live.calls == 2


def test_fallback_raises_when_all_exhausted():
    a = _Client(LLMQuotaExhausted("a gone"))
    b = _Client(LLMQuotaExhausted("b gone"))
    chain = FallbackLLMClient([("a", a), ("b", b)])
    with pytest.raises(Exception):
        chain.complete("s", "u")
    # both now dead -> a further call finds nothing to try and still raises
    with pytest.raises(RuntimeError):
        chain.complete("s", "u")
