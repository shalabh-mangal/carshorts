"""Owner-pick voice samples — the cloned channel voice in a few energies.

The portal's VOICE picker offers the owner a calm / natural / hype take of the
channel's cloned voice so they choose the delivery before we render. Those samples
have to exist as out/voice_options/<slug>_<label>.mp3; nothing generated them
automatically, so the portal's "generating…" line was a placeholder with no job
behind it. This module IS that job: the portal auto-triggers it (once) when a
script_review card has no samples, and it's runnable by hand as `carshorts voices
<slug>`.

Free by design: local Chatterbox (the cloned voice), never a paid engine.
"""
from __future__ import annotations

import json
import os

from carshorts.adapters.tts import make_tts
from carshorts.core import paths

# portal label -> persona (matches the set the Sierra card used)
SAMPLE_VOICES = [("calm", "deadpan"), ("natural", ""), ("hype", "hype")]


def _sample_line(slug: str) -> str:
    """A representative line to voice — the first script option's hook, so the
    sample sounds like the actual video; falls back to a generic line."""
    for sp in sorted(paths.SCRIPTS.glob(f"{slug}_opt*.script.json")):
        try:
            segs = json.loads(sp.read_text(encoding="utf-8")).get("segments", [])
        except Exception:  # noqa: BLE001 — skip an unreadable option
            continue
        hook = next((s.get("text", "") for s in segs if s.get("role") == "hook"), "")
        if hook:
            return hook
    return "This is the channel voice — a quick sample so you can pick the energy."


def generate(slug: str, engine: str = "chatterbox", language: str = "english") -> list[str]:
    """Synthesize the sample set for `slug` into out/voice_options/, atomically
    (write a hidden temp, then rename) so the portal never lists a half-written mp3."""
    paths.VOICE_OPTIONS.mkdir(parents=True, exist_ok=True)
    line = _sample_line(slug)
    written: list[str] = []
    for label, persona in SAMPLE_VOICES:
        out = paths.VOICE_OPTIONS / f"{slug}_{label}.mp3"
        tmp = paths.VOICE_OPTIONS / f".{slug}_{label}.tmp.mp3"   # dot-prefixed: not globbed
        make_tts(engine=engine, persona=persona, language=language).synthesize(line, str(tmp))
        os.replace(tmp, out)
        written.append(str(out))
        print(f"wrote {out}", flush=True)
    return written


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Generate owner-pick voice samples for a card.")
    ap.add_argument("slug")
    ap.add_argument("--engine", default="chatterbox")
    ap.add_argument("--language", default="english")
    args = ap.parse_args()
    generate(args.slug, engine=args.engine, language=args.language)


if __name__ == "__main__":
    main()
