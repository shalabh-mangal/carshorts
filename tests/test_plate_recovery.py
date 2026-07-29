"""Offline tests for auto plate-blur recovery (no network / API key).

A plated-but-good shot should be RECOVERED (plate blurred, confirmed clean by a
re-vet) instead of quarantined — the exact case that cost us two good Tata Punch
beauty shots. But a plate that stays readable after blurring must NEVER be kept.
"""
from PIL import Image

from carshorts.quality import assetvet


def _make_img(path):
    Image.new("RGB", (200, 120), (100, 100, 100)).save(path)


def test_recovers_plated_shot(tmp_path):
    img = tmp_path / "car.jpg"
    _make_img(img)
    calls = {"n": 0}

    def vet(_paths, _subject, _generation=""):
        calls["n"] += 1
        if calls["n"] == 1:  # first look: plate readable, with a box
            return '[{"image":0,"defects":["readable_plate"],"plate_box":[0.3,0.6,0.7,0.75]}]'
        return '[{"image":0,"defects":[]}]'  # re-vet after blur: clean

    rep = assetvet.vet_folder(str(tmp_path), "Test Car", apply=True, vet_fn=vet)
    assert rep["recovered"] == 1
    assert rep["quarantined"] == 0
    assert img.exists()  # kept in the pool, not quarantined


def test_quarantines_when_plate_survives_blur(tmp_path):
    img = tmp_path / "car.jpg"
    _make_img(img)

    def vet(_paths, _subject, _generation=""):
        # always readable -> recovery can't confirm clean -> must quarantine
        return '[{"image":0,"defects":["readable_plate"],"plate_box":[0.3,0.6,0.7,0.75]}]'

    rep = assetvet.vet_folder(str(tmp_path), "Test Car", apply=True, vet_fn=vet)
    assert rep["recovered"] == 0
    assert rep["quarantined"] == 1
    assert not img.exists()
    assert (tmp_path / "_quarantine" / "car.jpg").exists()
