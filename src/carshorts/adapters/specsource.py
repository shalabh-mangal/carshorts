"""The SpecSource adapter — where verified facts come from.

The pipeline's accuracy design rests on one thing (see models.Spec): every
figure carries the *exact source sentence* it was extracted from. A spec source
is therefore NOT "a thing that returns numbers" — it is "a thing that returns
numbers each bound to a real sentence on a real page." This module enforces
that: extraction lifts the literal sentence, then re-checks that the value is a
substring of the sentence and the sentence is a substring of the fetched page.
Anything that fails is dropped, never guessed.

Why Wikipedia first: it is CC-licensed and explicitly allows programmatic
access (unlike most manufacturer/news sites, whose ToS forbid scraping), its
car articles carry real prose sentences we can quote verbatim, and its
structure is stable across many cars. It is the right source for *measuring*
the model's hallucination rate. Production discovery from licensed, time-
sensitive sources is a separate, later problem.

No LLM is involved here on purpose. If a model extracted the "source sentence"
it could invent one, which would poison the very ground truth the harness
measures against. Extraction is deterministic; the model is only ever the thing
under test, never the thing that builds the answer key.
"""
from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod

from carshorts.core.models import Spec, SpecSheet

# macOS python.org builds don't wire the system CA store into Python's default
# SSL context, so HTTPS verification fails with CERTIFICATE_VERIFY_FAILED. Point
# at certifi's bundle when available. Verification stays ON — we never fall back
# to an unverified context, that would defeat TLS.
try:
    import certifi

    _SSL_CONTEXT: ssl.SSLContext = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # certifi absent -> use the platform default, still verified
    _SSL_CONTEXT = ssl.create_default_context()


class SpecSource(ABC):
    """Swappable fact source. Wikipedia now; manufacturer/news adapters later,
    same signature, once their licensing is sorted."""

    @abstractmethod
    def fetch(self, subject: str) -> SpecSheet:
        """Return a SpecSheet of verifiable, source-bound facts for `subject`."""


# ---------------------------------------------------------------------------
# Deterministic extraction
# ---------------------------------------------------------------------------
# Each entry: (spec_name, value-capturing regex). The regex must capture the
# literal value (with unit) in group "val". First valid match per name wins —
# we want a handful of solid, source-bound facts per car, not exhaustive stats.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("power", re.compile(r"(?P<val>\d[\d,]*(?:\.\d+)?\s?(?:bhp|PS|hp|kW))", re.I)),
    ("torque", re.compile(r"(?P<val>\d[\d,]*(?:\.\d+)?\s?(?:N⋅m|N·m|N-m|Nm))", re.I)),
    ("engine_cc", re.compile(r"(?P<val>\d[\d,]*\s?cc)", re.I)),
    # (?<!\d) stops "308-litre" (a boot volume) being read as an "8-litre"
    # engine. Engine displacement is a single leading digit (<10 litres).
    ("engine_litre", re.compile(r"(?P<val>(?<!\d)\d(?:\.\d+)?[\s-]?(?:litre|liter))\b")),
    ("mileage", re.compile(r"(?P<val>\d[\d,]*(?:\.\d+)?\s?(?:kmpl|km/l|mpg))", re.I)),
    ("top_speed", re.compile(r"top speed[^.\d]{0,25}(?P<val>\d[\d,]*(?:\.\d+)?\s?(?:km/h|mph))", re.I)),
    # Require a real magnitude (lakh/crore/...) OR a comma-grouped amount, so a
    # model code like "RS413" is NOT read as a price.
    ("price", re.compile(
        r"(?P<val>(?:₹|Rs\.?|US\$|\$|€|£)\s?"
        r"(?:\d[\d,]*(?:\.\d+)?\s?(?:lakh|crore|million|billion)|\d{1,3}(?:,\d{2,3})+(?:\.\d+)?))",
        re.I)),
    # Acceleration is captured only when the sentence is genuinely a 0-to-X
    # sprint claim (guarded in extract_specs), to avoid grabbing stray seconds.
    ("acceleration", re.compile(r"(?P<val>\d+(?:\.\d+)?\s?seconds?)", re.I)),
]

# A boundary is sentence-ending punctuation FOLLOWED BY whitespace, or a
# newline. The lookahead is what keeps decimals intact: the '.' in "12.99",
# "8.2" or "2.0-litre" is followed by a digit, not whitespace, so it is not a
# boundary. Without this, sentences get chopped mid-number and the value stops
# being a substring of its own sentence — silently dropping real specs.
_SENTENCE_BOUNDARY = re.compile(r"[.!?](?=\s)|\n")


def _sentence_at(text: str, idx: int) -> str:
    """Return the sentence in `text` containing character position `idx`.

    Bounds are the nearest sentence terminator on each side. Kept intentionally
    simple — Wikipedia plain-text extracts use '. ' between sentences and
    newlines between sections, which this handles without an NLP dependency.
    """
    start = 0
    for m in _SENTENCE_BOUNDARY.finditer(text, 0, idx):
        start = m.end()
    end_match = _SENTENCE_BOUNDARY.search(text, idx)
    end = end_match.end() if end_match else len(text)
    return text[start:end].strip()


def _is_acceleration_sentence(sentence: str) -> bool:
    s = sentence.lower()
    return "0" in s and ("km/h" in s or "mph" in s or "60" in s or "100" in s)


def extract_specs(text: str, source_url: str) -> list[Spec]:
    """Pure, offline, deterministic. Extract source-bound Specs from page text.

    For every match we lift the enclosing sentence verbatim and enforce the
    honesty gate: value ⊂ sentence ⊂ text. This is what makes each Spec a
    2-minute Gate 1 check instead of a claim to be re-researched.
    """
    specs: list[Spec] = []
    seen: set[str] = set()
    for name, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            if name in seen:
                break
            value = match.group("val").strip()
            sentence = _sentence_at(text, match.start("val"))
            if name == "acceleration" and not _is_acceleration_sentence(sentence):
                continue
            # Honesty gate: never emit a Spec whose sentence we can't stand behind.
            if value not in sentence or sentence not in text:
                continue
            if len(sentence) < 10 or len(sentence) > 400:
                continue
            if "==" in sentence:   # a Wikipedia section header, not a real sentence
                continue
            specs.append(
                Spec(
                    name=name,
                    value=value,
                    source_url=source_url,
                    source_sentence=sentence,
                )
            )
            seen.add(name)
            break
    return specs


# ---------------------------------------------------------------------------
# Generation scoping — don't blend specs across model years
# ---------------------------------------------------------------------------
# Matches "== Heading ==", "=== Sub ===" etc. (exsectionformat=wiki gives these).
_SECTION_HEADER = re.compile(r"^(={2,})\s*(.+?)\s*\1\s*$", re.M)


def scope_to_current_generation(text: str) -> str:
    """Return the lead + ONLY the current generation's section (with its
    sub-sections), so extraction doesn't mix a 2003 model with a 2024 one.

    A section spans until the next header of the same-or-higher level, so a
    "== Fourth generation ==" keeps its "=== Engine ===" sub-section. The current
    generation is the section whose title says 'present' (else the latest year).
    Falls back to the whole text when there are no generation sections (a single-
    generation article, where there's nothing to disambiguate).
    """
    headers = [(m.start(), m.end(), len(m.group(1)), m.group(2))
               for m in _SECTION_HEADER.finditer(text)]
    if not headers:
        return text
    lead = text[:headers[0][0]]

    def body_of(idx: int) -> str:
        start, level = headers[idx][1], headers[idx][2]
        end = len(text)
        for j in range(idx + 1, len(headers)):
            if headers[j][2] <= level:   # next same-or-higher header ends this section
                end = headers[j][0]
                break
        return text[start:end]

    gens = []
    for idx, (_s, _e, _level, title) in enumerate(headers):
        low = title.lower()
        years = [int(y) for y in re.findall(r"(?:19|20)\d{2}", title)]
        if "generation" in low or "present" in low or years:
            gens.append(("present" in low, max(years) if years else 0, idx))
    if not gens:
        return text
    gens.sort(key=lambda g: (g[0], g[1]), reverse=True)   # 'present' first, then newest
    return lead + "\n" + body_of(gens[0][2])


# ---------------------------------------------------------------------------
# Wikipedia implementation
# ---------------------------------------------------------------------------
class WikipediaSpecSource(SpecSource):
    """Fetches a car's plain-text article from Wikipedia and extracts
    source-bound specs. Network fetch and extraction are separated so the
    extractor can be unit-tested offline."""

    API = "https://en.wikipedia.org/w/api.php"
    _USER_AGENT = "carshorts/0.1 (spec-accuracy-harness; contact via project owner)"

    def __init__(self, lang: str = "en"):
        self.API = f"https://{lang}.wikipedia.org/w/api.php"
        self._wiki_base = f"https://{lang}.wikipedia.org/wiki/"

    def _fetch_extract(self, subject: str) -> tuple[str, str]:
        """Return (plain_text, canonical_article_url) for `subject`.

        Uses redirects=1 so "Tata Nexon" resolves to the real article title.
        Raises LookupError if the article is missing.
        """
        params = {
            "action": "query",
            "prop": "extracts",
            "explaintext": "1",
            "exsectionformat": "wiki",   # keep "== Heading ==" so we can find sections
            "redirects": "1",
            "format": "json",
            "titles": subject,
        }
        url = f"{self.API}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": self._USER_AGENT})
        data = None
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=20, context=_SSL_CONTEXT) as resp:
                    data = json.load(resp)
                break
            except urllib.error.HTTPError as exc:
                # Be a polite API citizen: on 429 honour Retry-After and back off.
                if exc.code == 429 and attempt < 3:
                    retry_after = exc.headers.get("Retry-After", "3")
                    wait = min(max(int(retry_after) if retry_after.isdigit() else 3, 2), 30)
                    time.sleep(wait)
                    continue
                raise
        if data is None:
            raise LookupError(f"Rate-limited fetching {subject!r} after retries")
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            if "missing" in page:
                raise LookupError(f"No Wikipedia article for {subject!r}")
            title = page.get("title", subject)
            text = page.get("extract", "")
            article_url = self._wiki_base + urllib.parse.quote(title.replace(" ", "_"))
            return text, article_url
        raise LookupError(f"No Wikipedia page returned for {subject!r}")

    def fetch(self, subject: str) -> SpecSheet:
        text, article_url = self._fetch_extract(subject)
        scoped = scope_to_current_generation(text)
        specs = extract_specs(scoped, article_url)
        if len(specs) < 2:   # scoped section too thin — fall back to the full article
            specs = extract_specs(text, article_url)
        return SpecSheet(subject=subject, specs=specs)
