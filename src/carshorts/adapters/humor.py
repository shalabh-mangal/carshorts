"""Humor layer — a small library of reusable AI comedic cutaways, mapped to beats.

A visual joke vocabulary (rocket = turbo/speed, money-rain = value, shield =
safety, mind-blown = shock) generated ONCE via videogen and reused across every
video — cheap, fast, on-brand. These are EDITORIAL jokes intercut with the real
car footage; they NEVER depict the subject car (that stays real, per the wall in
produce). Every clip is provenance-tagged 'generated' by the videogen adapter.

The pipeline calls joke_for(beat_text) on reaction/peak beats; a match returns a
cached comedic clip to flash under the punchline. No match, or no video env ->
None, and the render just uses the normal car visuals.
"""
from __future__ import annotations

import re

from carshorts.adapters import videogen

# (concept, trigger regex, t2v prompt). First match wins — order strongest first.
JOKE_CONCEPTS: list[tuple[str, str, str]] = [
    ("rocket",
     r"\bturbo\b|horsepower|\bbhp\b|\bnm\b|torque|\bfast\b|\bpower|rocket|flies?|blazing|quick",
     "a cute cartoon rocket ship blasting off fast into a bright blue sky with a "
     "big whoosh of orange flames, comic-book style, bold saturated colors, "
     "dynamic fast motion, clean simple shapes"),
    ("money",
     r"value|paisa|worth|\bcheap\b|\blakh\b|price|budget|save|money|afford",
     "a happy cartoon shower of gold coins and banknotes raining down over a "
     "smiling wallet, comic-book style, bright celebratory colors, dynamic motion"),
    ("shield",
     r"\bsafe\b|safety|ncap|\bstar\b|protect|\bstrong\b|\btough\b|\bbuild\b|solid",
     "a glowing cartoon shield with a big checkmark and sparkles, comic-book "
     "style, bold blue and gold, protective, gentle pulse, clean shapes"),
    ("mindblown",
     r"\bwait\b|\bwhat\b|crazy|insane|unbelievable|\bhow\b|legal|shock|no way",
     "a cartoon head with the top exploding into a burst of colorful stars and a "
     "galaxy, classic mind-blown meme, comic-book style, dynamic, funny"),
    ("boot",
     r"\bboot\b|\bspace\b|\broom\b|storage|\blitre|luggage|spacious",
     "a cartoon car boot opening to reveal an impossibly huge pile of suitcases "
     "and bags, comic exaggeration, bright colors, playful bounce"),
]


def joke_for(text: str) -> str | None:
    """A cached comedic clip for the first concept `text` hits, or None (no match
    / no video env). Each concept is generated once and reused (joke_<concept>.mp4)."""
    if not text or not videogen.available():
        return None
    low = text.lower()
    for concept, trigger, prompt in JOKE_CONCEPTS:
        if re.search(trigger, low):
            return videogen.generate(
                prompt, mode="t2v",
                out_path=str(videogen.GEN_DIR / f"joke_{concept}.mp4"))
    return None


def prebuild(concepts: list[str] | None = None) -> dict[str, str | None]:
    """Generate (and cache) the joke library up front. Returns {concept: path|None}."""
    out: dict[str, str | None] = {}
    for concept, _trigger, prompt in JOKE_CONCEPTS:
        if concepts and concept not in concepts:
            continue
        out[concept] = videogen.generate(
            prompt, mode="t2v", out_path=str(videogen.GEN_DIR / f"joke_{concept}.mp4"))
    return out
