"""Offline test for the portal's cross-process render lock.

Two portal instances (or a double-clicked Lock) once spawned two identical
renders racing the same draft + voice cache. _claim_render is the atomic guard
that makes a duplicate impossible: the first claim wins, the rest are refused
until the render finishes (or the lock goes stale)."""
import time

from carshorts.portal import server


def test_claim_render_is_exclusive(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "QUEUE", tmp_path)

    # first caller wins the lock; a concurrent second caller is refused
    assert server._claim_render("sierra-vs-creta") is True
    assert server._claim_render("sierra-vs-creta") is False
    assert (tmp_path / "sierra-vs-creta.progress.json").exists()

    # a DIFFERENT card is independent
    assert server._claim_render("tata-punch") is True

    # once the render worker clears the progress file, the lock is free again
    (tmp_path / "sierra-vs-creta.progress.json").unlink()
    assert server._claim_render("sierra-vs-creta") is True


def test_claim_render_reclaims_a_stale_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "QUEUE", tmp_path)
    pf = tmp_path / "nexon.progress.json"
    pf.write_text("{}")
    # backdate it beyond the 30-min staleness window (a died render)
    old = time.time() - 3600
    import os
    os.utime(pf, (old, old))
    assert server._claim_render("nexon") is True   # stale lock reclaimed
