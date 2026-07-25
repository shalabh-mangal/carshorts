"""Extras merging: news must survive a car that has no price yet.

Price is human-supplied (never scraped — CLAUDE.md), so a freshly crawled car
legitimately has fresh news long before it has a price. _apply_extras used to
`return ""` the moment price was missing, silently throwing away every news
item — which would have made the whole news crawler a no-op on exactly the new
cars it exists to unblock.
"""
import json

from carshorts.core.models import Spec, SpecSheet
from carshorts.rendering.produce import _apply_extras


def _sheet():
    return SpecSheet(subject="Maruti Suzuki Brezza", specs=[
        Spec(name="power", value="102 PS", source_url="https://en.wikipedia.org/wiki/x",
             source_sentence="The Brezza makes 102 PS."),
    ])


def _write_extras(tmp_path, payload):
    d = tmp_path / "specs_extras"
    d.mkdir(exist_ok=True)
    (d / "maruti-suzuki-brezza.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_news_applies_when_there_is_no_price(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_extras(tmp_path, {"news": [
        {"fact": "Brezza scores 5-star Bharat NCAP rating",
         "source": "https://example.com/ncap", "date": "July 2026"},
    ]})
    sheet = _sheet()
    guidance = _apply_extras(sheet)

    names = [s.name for s in sheet.specs]
    assert "news_1" in names                      # became a SOURCED spec
    assert "price_estimate" not in names          # and no price was invented
    assert "FRESH NEWS #1" in guidance
    assert "Lead the HOOK" in guidance


def test_price_still_applies_when_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_extras(tmp_path, {
        "price_estimate": "₹8.34 lakh to ₹14.14 lakh",
        "news": [{"fact": "F", "source": "https://example.com/a", "date": "July 2026"}],
    })
    sheet = _sheet()
    guidance = _apply_extras(sheet)

    names = [s.name for s in sheet.specs]
    assert "price_estimate" in names and "news_1" in names
    assert "PRICE (estimate, say so)" in guidance


def test_news_source_url_is_the_articles_own(tmp_path, monkeypatch):
    """A news spec must cite the ARTICLE, not the price source — otherwise the
    Gate 1 report would point the owner at the wrong page to verify a claim."""
    monkeypatch.chdir(tmp_path)
    _write_extras(tmp_path, {
        "price_source": "https://www.cardekho.com/maruti/brezza",
        "news": [{"fact": "F", "source": "https://autocarindia.com/story",
                  "date": "July 2026"}],
    })
    sheet = _sheet()
    _apply_extras(sheet)
    news_spec = next(s for s in sheet.specs if s.name == "news_1")
    assert str(news_spec.source_url) == "https://autocarindia.com/story"


def test_empty_extras_yields_no_guidance(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_extras(tmp_path, {})
    sheet = _sheet()
    assert _apply_extras(sheet) == ""
    assert [s.name for s in sheet.specs] == ["power"]
