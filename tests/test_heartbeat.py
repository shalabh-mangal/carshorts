"""Offline tests for the heartbeat's decision logic.

This is the logic that decides whether the channel produces today. A wrong
"produce" starts a second render and burns agent budget; a wrong "skip" stops
the channel silently — which is exactly how the cadence died after 2026-07-22.
Both failure modes are quiet, so they get tests.
"""
import json

from carshorts.heartbeat import decide

CLEAR = {"awaiting": 0, "in_flight": 0, "ran_today": False, "has_slot": True, "max_pending": 2}


def test_clear_day_produces():
    action, _ = decide(**CLEAR)
    assert action == "produce"


def test_in_flight_blocks_everything():
    # even with an otherwise perfect day, never start a second render
    action, reason = decide(**{**CLEAR, "in_flight": 1})
    assert action == "skip" and "in flight" in reason


def test_in_flight_outranks_other_blockers():
    action, reason = decide(awaiting=9, in_flight=1, ran_today=True,
                            has_slot=False, max_pending=2)
    assert action == "skip" and "in flight" in reason


def test_already_produced_today_is_idempotent():
    action, reason = decide(**{**CLEAR, "ran_today": True})
    assert action == "skip" and "already produced" in reason


def test_backpressure_when_owner_has_a_backlog():
    action, reason = decide(**{**CLEAR, "awaiting": 2})
    assert action == "skip" and "waiting on you" in reason


def test_one_pending_draft_still_produces():
    # back-pressure must not be so eager that it stalls a healthy channel
    action, _ = decide(**{**CLEAR, "awaiting": 1})
    assert action == "produce"


def test_empty_calendar_is_reported_not_crashed():
    action, reason = decide(**{**CLEAR, "has_slot": False})
    assert action == "skip" and "calendar" in reason


def test_produced_today_reads_the_journal(tmp_path, monkeypatch):
    import carshorts.heartbeat as hb
    journal = tmp_path / "hb.jsonl"
    journal.write_text(
        json.dumps({"at": "2026-07-23T09:00:00", "action": "produce", "ok": True}) + "\n",
        encoding="utf-8")
    monkeypatch.setattr(hb, "JOURNAL", journal)
    assert hb.produced_today("2026-07-23") is True
    assert hb.produced_today("2026-07-24") is False


def test_failed_produce_does_not_count_as_done(tmp_path, monkeypatch):
    # a crashed run must not block a retry later the same day
    import carshorts.heartbeat as hb
    journal = tmp_path / "hb.jsonl"
    journal.write_text(
        json.dumps({"at": "2026-07-23T09:00:00", "action": "produce", "ok": False}) + "\n",
        encoding="utf-8")
    monkeypatch.setattr(hb, "JOURNAL", journal)
    assert hb.produced_today("2026-07-23") is False


def test_preflight_clean_when_specs_and_extras_exist(tmp_path, monkeypatch):
    from carshorts.heartbeat import preflight
    monkeypatch.chdir(tmp_path)
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs_extras").mkdir()
    (tmp_path / "specs" / "tata-punch.json").write_text("{}", encoding="utf-8")
    (tmp_path / "specs_extras" / "tata-punch.json").write_text("{}", encoding="utf-8")
    assert preflight("tata-punch", agents_ok=False) == []


def test_preflight_flags_missing_specs(tmp_path, monkeypatch):
    from carshorts.heartbeat import preflight
    monkeypatch.chdir(tmp_path)
    blockers = preflight("kia-sonet", agents_ok=True)
    assert any("specs/kia-sonet.json" in b for b in blockers)


def test_preflight_flags_missing_extras_only_without_agents(tmp_path, monkeypatch):
    """The scriptwright agent can WRITE extras — so missing extras only blocks
    when the agent layer is unavailable. This is the exact condition that would
    have failed the first real heartbeat run on Windows (no `claude` CLI)."""
    from carshorts.heartbeat import preflight
    monkeypatch.chdir(tmp_path)
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "tata-punch.json").write_text("{}", encoding="utf-8")

    assert preflight("tata-punch", agents_ok=True) == []          # agent can supply it
    blockers = preflight("tata-punch", agents_ok=False)
    assert any("specs_extras" in b for b in blockers)             # nothing can


def test_corrupt_journal_line_is_survivable(tmp_path, monkeypatch):
    import carshorts.heartbeat as hb
    journal = tmp_path / "hb.jsonl"
    journal.write_text("not json\n" + json.dumps(
        {"at": "2026-07-23T09:00:00", "action": "produce", "ok": True}) + "\n",
        encoding="utf-8")
    monkeypatch.setattr(hb, "JOURNAL", journal)
    assert hb.produced_today("2026-07-23") is True
