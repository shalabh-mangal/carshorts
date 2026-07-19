"""Offline tests for complete_json robustness.

These reproduce the real-model failure that dropped a car from the harness: a
fact-check response is a JSON ARRAY, and the old first-{-to-last-} extraction
corrupted it. Also cover markdown fences, prose preamble, and trailing commas.
"""
from carshorts.adapters.llm import MockLLMClient

SYS = "sys"


def _client(raw: str) -> MockLLMClient:
    # Keyed on a substring present in the user prompt below.
    return MockLLMClient({"go": raw})


def test_array_with_prose_preamble_parses_as_list():
    raw = 'Here is the fact-check result:\n[{"a": 1}, {"b": 2}]'
    out = _client(raw).complete_json(SYS, "go")
    assert out == [{"a": 1}, {"b": 2}]


def test_array_in_markdown_fences():
    raw = "```json\n[1, 2, 3]\n```"
    assert _client(raw).complete_json(SYS, "go") == [1, 2, 3]


def test_object_with_preamble_parses_as_dict():
    raw = 'Sure!\n{"subject": "X", "segments": []}'
    out = _client(raw).complete_json(SYS, "go")
    assert out == {"subject": "X", "segments": []}


def test_trailing_comma_is_tolerated():
    raw = '[{"x": 1,}, {"y": 2},]'
    assert _client(raw).complete_json(SYS, "go") == [{"x": 1}, {"y": 2}]


def test_unparseable_raises_valueerror_with_snippet():
    import pytest

    raw = "totally not json at all"
    with pytest.raises(ValueError, match="unparseable JSON"):
        _client(raw).complete_json(SYS, "go")
