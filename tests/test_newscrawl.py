"""Offline tests for the news crawler (no network).

The load-bearing guarantee is the LAST test: this tool must never write or alter
a price. CLAUDE.md: "prices are estimates from a one-off CarDekho/CarWale lookup
— never automated scraping of them." A crawler that quietly invented a price
would defeat the number-guard's entire premise.
"""
import json

from carshorts.newscrawl import (
    _car_tokens,
    matches_car,
    merge_into_extras,
    parse_feed,
    to_news_entries,
)

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>2026 Mahindra Thar facelift spied testing</title>
    <link>https://example.com/thar-spied</link>
    <description>Roxx-style headlamps seen on test mule</description>
    <pubDate>Wed, 22 Jul 2026 10:00:00 +0530</pubDate>
  </item>
  <item>
    <title>Kia Sonet gets new variant</title>
    <link>https://example.com/sonet</link>
    <description>unrelated</description>
    <pubDate>Wed, 22 Jul 2026 11:00:00 +0530</pubDate>
  </item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Tata Punch facelift launched</title>
    <link href="https://example.com/punch"/>
    <summary>New Punch arrives</summary>
    <updated>2026-07-20T09:00:00Z</updated>
  </entry>
</feed>"""


def test_parses_rss():
    items = parse_feed(RSS, "Test")
    assert len(items) == 2
    assert items[0]["title"].startswith("2026 Mahindra Thar")
    assert items[0]["link"] == "https://example.com/thar-spied"
    assert items[0]["published"].year == 2026


def test_parses_atom_link_href():
    items = parse_feed(ATOM, "Test")
    assert len(items) == 1
    assert items[0]["link"] == "https://example.com/punch"


def test_malformed_feed_is_survivable():
    assert parse_feed(b"not xml at all", "Test") == []


def test_brand_only_tokens_do_not_match_everything():
    # "maruti" alone must not pull in every Maruti story onto the Swift
    tokens = _car_tokens("Maruti Suzuki Swift", "maruti-suzuki-swift")
    assert "swift" in tokens
    assert "maruti" not in tokens and "suzuki" not in tokens


def test_matching_selects_only_the_subject_car():
    items = parse_feed(RSS, "Test")
    tokens = _car_tokens("Mahindra Thar", "mahindra-thar")
    matched = [i for i in items if matches_car(i, tokens, set())]
    assert len(matched) == 1 and "Thar" in matched[0]["title"]


def test_aliases_widen_matching():
    items = parse_feed(RSS, "Test")
    # "roxx" only appears in the description; alias matching must still catch it
    matched = [i for i in items if matches_car(i, {"nonexistent"}, {"roxx"})]
    assert len(matched) == 1


def test_news_entries_keep_outlet_wording_and_source():
    items = parse_feed(RSS, "Test")
    news = to_news_entries(items[:1])
    assert news[0]["fact"] == "2026 Mahindra Thar facelift spied testing"  # hedge preserved
    assert news[0]["source"] == "https://example.com/thar-spied"
    assert news[0]["date"] == "July 2026"


def test_merge_never_touches_price_fields(tmp_path, monkeypatch):
    import carshorts.newscrawl as nc
    monkeypatch.setattr(nc, "EXTRAS_DIR", tmp_path)
    (tmp_path / "mahindra-thar.json").write_text(json.dumps({
        "price_estimate": "₹10.32 lakh to ₹17.80 lakh",
        "price_source": "https://www.cardekho.com/mahindra/thar",
        "value_variant": "LXT RWD Diesel",
        "news": [],
    }), encoding="utf-8")

    nc.merge_into_extras("mahindra-thar", [
        {"fact": "New story", "source": "https://example.com/a", "date": "July 2026"}
    ], write=True)

    after = json.loads((tmp_path / "mahindra-thar.json").read_text(encoding="utf-8"))
    assert after["price_estimate"] == "₹10.32 lakh to ₹17.80 lakh"   # untouched
    assert after["price_source"] == "https://www.cardekho.com/mahindra/thar"
    assert after["value_variant"] == "LXT RWD Diesel"
    assert len(after["news"]) == 1


def test_merge_is_idempotent_on_the_same_source(tmp_path, monkeypatch):
    import carshorts.newscrawl as nc
    monkeypatch.setattr(nc, "EXTRAS_DIR", tmp_path)
    story = [{"fact": "S", "source": "https://example.com/a", "date": "July 2026"}]
    nc.merge_into_extras("x", story, write=True)
    result = nc.merge_into_extras("x", story, write=True)
    assert result["added"] == 0 and result["total_news"] == 1


def test_merge_reports_missing_price(tmp_path, monkeypatch):
    import carshorts.newscrawl as nc
    monkeypatch.setattr(nc, "EXTRAS_DIR", tmp_path)
    result = nc.merge_into_extras("brand-new-car", [
        {"fact": "S", "source": "https://example.com/z", "date": "July 2026"}
    ], write=True)
    assert result["has_price"] is False   # the owner must still supply it
