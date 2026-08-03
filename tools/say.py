r"""Generate ONE voiceover clip with the cloned Chatterbox voice — no video.

A tiny wrapper around carshorts.adapters.tts so you can audition the voice, a
language, and an energy level from the command line, fast.

Examples (run from the repo root, with the venv python):
  .\.venv\Scripts\python.exe tools\say.py "This SUV packs 172 bhp of pure punch!"
  .\.venv\Scripts\python.exe tools\say.py "यह गाड़ी कमाल की है!" --language hindi
  .\.venv\Scripts\python.exe tools\say.py "line" --exaggeration 1.35 --cfg 0.30 --out out\test.mp3
  .\.venv\Scripts\python.exe tools\say.py "line" --ref data\voice\my_new_reference.wav
  .\.venv\Scripts\python.exe tools\say.py "a steal at this price" --expressions   # 6-style battery

Energy dials:
  --exaggeration  emotional intensity (0.5 calm .. 1.6 very hot; >1.6 can strain)
  --cfg           pacing/adherence  (lower = faster, looser, more expressive)
The named --persona presets set sensible defaults for these two dials.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from carshorts.adapters.tts import ChatterboxTTSProvider, make_tts

EXPRESSION_VARIANTS = {
    "a_plain": lambda t: t if t.rstrip().endswith((".", "!", "?")) else t + ".",
    "b_triple_bang": lambda t: t.rstrip(".!?") + "!!!.",
    "c_bang_question": lambda t: t.rstrip(".!?") + "?!.",
    "d_allcaps_bang": lambda t: t.rstrip(".!?").upper() + "!!!.",
    "e_haha": lambda t: t.rstrip(".!?") + "! Ha ha ha!",
    "f_triple_question": lambda t: t.rstrip(".!?") + "???",
}


def _gen_battery(text: str, tts: ChatterboxTTSProvider, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for label, fmt in EXPRESSION_VARIANTS.items():
        p = out_dir / f"{label}.mp3"
        tts.synthesize(fmt(text), str(p))
        print(f"  {label:<20} {p.stat().st_size:>7} bytes")
    print("wrote", len(EXPRESSION_VARIANTS), "samples to", out_dir)


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
    ap.add_argument("--expressions", action="store_true",
                    help="Generate all 6 expression variants into "
                         "out/voice_options/tests/ and open the folder.")
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

    if args.expressions:
        out_dir = Path("out/voice_options/tests")
        if not isinstance(tts, ChatterboxTTSProvider):
            print("--expressions needs the chatterbox engine (no chatterbox here)")
            return
        _gen_battery(args.text, tts, out_dir)
        if os.name == "nt":
            os.startfile(out_dir)  # open the folder for quick audition
        return

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    tts.synthesize(args.text, args.out)
    print("wrote", args.out)


if __name__ == "__main__":
    main()
