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


def joke_for(text: str, avoid: set[str] | None = None) -> tuple[str, str] | None:
    """(clip_path, concept) for the first UNUSED concept `text` hits, else None.

    `avoid` = concepts already used in this video, so each humor beat lands a
    DIFFERENT joke (varied, not repeated). Cached-only ON PURPOSE: never generate
    during a render — the GPU worker would contend with the loaded voice model
    and can OOM the 8GB card. The library is built once offline (`carshorts
    jokes`); renders only look it up."""
    if not text:
        return None
    avoid = avoid or set()
    low = text.lower()
    for concept, trigger, _prompt in JOKE_CONCEPTS:
        if concept in avoid:
            continue
        if re.search(trigger, low):
            path = videogen.GEN_DIR / f"joke_{concept}.mp4"
            return (str(path), concept) if path.exists() else None
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


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Pre-build the reusable AI joke-clip library (one-time).")
    ap.add_argument("--concepts", nargs="*", help="Subset of concepts (default: all).")
    args = ap.parse_args()
    if not videogen.available():
        print("video env not found (.venv-video) — run tools/setup for the LTX stack first.")
        return
    result = prebuild(args.concepts)
    for concept, path in result.items():
        print(f"  {concept:12} {'-> ' + path if path else 'FAILED'}")


if __name__ == "__main__":
    main()
