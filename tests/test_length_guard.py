"""Offline tests for write-time length enforcement.

Overlong scripts run past 60s and fail the render's length QA (a Punch draft
came out ~196 words / ~75s). enforce_length trims at write-time without touching
sourced facts; when already short it must be a no-op (no LLM call)."""
from carshorts.core.models import Script, ScriptSegment, SpecSheet
from carshorts.writing.draft import enforce_length

SHEET = SpecSheet(subject="X", specs=[])


class _BoomLLM:
    """An LLM that fails loudly if used — proves the short-script path skips it."""

    def complete_json(self, *_args, **_kwargs):
        raise AssertionError("enforce_length must not call the LLM when under the cap")


def test_short_script_is_a_noop():
    script = Script(subject="X", segments=[
        ScriptSegment(role="hook", text="Short, punchy, and well under the cap."),
        ScriptSegment(role="cta", text="Like, share, subscribe."),
    ])
    assert enforce_length(script, SHEET, _BoomLLM(), max_words=120) is script


def test_trim_falls_back_on_llm_error():
    # A long script + an LLM that errors -> returns the original, never crashes.
    long_text = " ".join(["word"] * 200)
    script = Script(subject="X", segments=[ScriptSegment(role="spec", text=long_text)])

    class _ErrLLM:
        def complete_json(self, *_a, **_k):
            raise RuntimeError("model down")

    out = enforce_length(script, SHEET, _ErrLLM(), max_words=120)
    assert out is script
