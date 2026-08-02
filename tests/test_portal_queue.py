"""Portal queue robustness — a single malformed/fresh card must never crash the
whole queue. Regression for the bug where a script_review card with no `draft`
field made Path("").with_suffix(".lock") raise, blanking the entire portal."""
import json

from carshorts.portal import server as portal


def test_draftless_card_does_not_crash_queue(tmp_path, monkeypatch):
    q = tmp_path / "queue"
    q.mkdir()
    # a fresh Gate-1 card: NO draft, NO final (this is what broke the portal)
    (q / "car-x.json").write_text(json.dumps({
        "car": "Car X", "slug": "car-x", "status": "script_review",
    }))
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    monkeypatch.setattr(portal, "QUEUE", q)
    monkeypatch.setattr(portal.paths, "SCRIPTS", scripts)
    monkeypatch.setattr(portal.paths, "VOICE_OPTIONS", tmp_path / "voice_options")

    cards = portal._queue_cards()   # must not raise
    assert len(cards) == 1
    c = cards[0]
    assert c["slug"] == "car-x"
    assert c["status"] == "script_review"
    assert c["play"] == ""          # no video yet — empty, not a crash
    assert c["draft_v"] == 0
    assert c["beats"] == []          # no manifest yet
