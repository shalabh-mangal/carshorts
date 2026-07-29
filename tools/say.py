"""Generate ONE voiceover clip with the cloned Chatterbox voice — no video.

A tiny wrapper around carshorts.adapters.tts so you can audition the voice, a
language, and an energy level from the command line, fast.

Examples (run from the repo root, with the venv python):
  .\.venv\Scripts\python.exe tools\say.py "This SUV packs 172 bhp of pure punch!"
  .\.venv\Scripts\python.exe tools\say.py "यह गाड़ी कमाल की है!" --language hindi
  .\.venv\Scripts\python.exe tools\say.py "line" --exaggeration 1.35 --cfg 0.30 --out out\test.mp3
  .\.venv\Scripts\python.exe tools\say.py "line" --ref data\voice\my_new_reference.wav

Energy dials:
  --exaggeration  emotional intensity (0.5 calm .. 1.6 very hot; >1.6 can strain)
  --cfg           pacing/adherence  (lower = faster, looser, more expressive)
The named --persona presets set sensible defaults for these two dials.
"""
from __future__ import annotations

import argparse
import os

from carshorts.adapters.tts import ChatterboxTTSProvider, make_tts


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate one cloned-voice clip.")
    ap.add_argument("text", help="What to say (wrap in quotes).")
    ap.add_argument("--language", default="english",
                    choices=["english", "hindi", "hinglish"])
    ap.add_argument("--persona", default="hype",
                    choices=["deadpan", "hype", "bhai", "default"],
                    help="Energy preset (sets exaggeration + cfg).")
    ap.add_argument("--exaggeration", type=float, default=None,
                    help="Override the preset's emotional intensity.")
    ap.add_argument("--cfg", type=float, default=None,
                    help="Override the preset's pacing (cfg_weight).")
    ap.add_argument("--ref", default=None,
                    help="Reference voice clip. Defaults to CARSHORTS_VOICE_REF "
                         "or data/voice/owner_reference.mp3.")
    ap.add_argument("--out", default="out/say.mp3", help="Output MP3 path.")
    args = ap.parse_args()

    if args.ref:
        os.environ["CARSHORTS_VOICE_REF"] = args.ref

    tts = make_tts(engine="chatterbox", persona=args.persona, language=args.language)
    if isinstance(tts, ChatterboxTTSProvider):
        if args.exaggeration is not None:
            tts.exaggeration = args.exaggeration
        if args.cfg is not None:
            tts.cfg_weight = args.cfg
        print(f"voice=clone  lang={args.language}  exag={tts.exaggeration}  "
              f"cfg={tts.cfg_weight}  ref={tts.ref_path}")
    else:
        print("NOTE: chatterbox unavailable — fell back to the free edge voice")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    tts.synthesize(args.text, args.out)
    print("wrote", args.out)


if __name__ == "__main__":
    main()
