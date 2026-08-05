"""Offline tests for the publish-safety guards.

Two real incidents motivated these: a Short went PUBLIC on the wrong channel
(wrong-channel token), and the publish kit tagged #Kia on a Tata-vs-Hyundai
video. The channel guard aborts a wrong-channel upload; the hashtag cleaner
drops brand tags for brands not in the video."""
import pytest

from carshorts.publishing import ytauth
from carshorts.publishing.publishkit import _clean_hashtags


class _FakeYT:
    def __init__(self, cid, title):
        self._cid, self._title = cid, title

    def channels(self):
        outer = self

        class _C:
            def list(self, **_k):
                class _R:
                    def execute(self_inner):
                        return {"items": [{"id": outer._cid,
                                           "snippet": {"title": outer._title}}]}
                return _R()
        return _C()


def test_channel_guard_passes_for_carshorts(monkeypatch):
    monkeypatch.delenv("CARSHORTS_CHANNEL", raising=False)
    cid, title = ytauth.assert_channel(_FakeYT("UC_car_123", "CarShorts"))
    assert cid == "UC_car_123" and title == "CarShorts"   # 'carshort' substring matches


def test_channel_guard_blocks_wrong_channel(monkeypatch):
    monkeypatch.delenv("CARSHORTS_CHANNEL", raising=False)
    with pytest.raises(RuntimeError, match="CHANNEL GUARD"):
        ytauth.assert_channel(_FakeYT("UCwrong", "Secret Lives Studio"))


def test_channel_guard_honours_env_channel_id(monkeypatch):
    monkeypatch.setenv("CARSHORTS_CHANNEL", "UCexact")
    # exact id match wins even if the title wouldn't
    assert ytauth.assert_channel(_FakeYT("UCexact", "Anything"))[0] == "UCexact"
    with pytest.raises(RuntimeError):
        ytauth.assert_channel(_FakeYT("UCother", "Anything"))


def test_hashtags_drop_wrong_brand():
    tags = ["#Sierra", "#Creta", "#Hyundai", "#Kia", "#Shorts", "#CarShorts"]
    out = _clean_hashtags(tags, "Tata Sierra vs Hyundai Creta", "sierra creta turbo")
    assert "#Kia" not in out               # Kia isn't in the video — dropped
    assert "#Hyundai" in out and "#Shorts" in out
    assert "#Tata" in out                  # subject brand injected even if the model missed it


def test_hashtags_keep_only_present_brands():
    out = _clean_hashtags(["#Maruti", "#Toyota"], "Maruti Swift", "swift petrol")
    assert "#Maruti" in out and "#Toyota" not in out
