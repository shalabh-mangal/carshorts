"""Build a video from a script: text -> voice -> MP4.

  python -m carshorts.build                          # renders a built-in demo
  python -m carshorts.build --text-file script.txt --title "Tata Nexon" --out out/nexon.mp4
  python -m carshorts.build --text "..." --bg car.jpg --voice en-IN-PrabhatNeural

This is the "second half" of the factory (voice + assemble). It intentionally
does NOT call the LLM — it takes an already-written (and, in the real flow,
already fact-checked and human-approved) script. Keeping generation and
rendering separate means we can iterate on video output without spending model
quota, and we never render a script that hasn't passed Gate 1.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .adapters.renderer import MoviePyRenderer
from .adapters.tts import EdgeTTSProvider

DEMO_SCRIPT = (
    "Think small SUVs have to be boring? The Tata Nexon didn't get that memo. "
    "Under the hood, a peppy turbo engine that actually wants to play. "
    "It's the pocket rocket that pretends it's sensible. Would you daily drive one? "
    "Tell us below, and hit follow for more."
)


def build_video(script_text: str, title: str, out_path: str,
                background_image: str | None = None,
                voice: str = "en-US-GuyNeural") -> str:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    audio_path = str(out.with_suffix(".mp3"))

    print(f"1/2  voice  -> {audio_path}")
    EdgeTTSProvider(voice=voice).synthesize(script_text, audio_path)

    print(f"2/2  render -> {out_path}")
    MoviePyRenderer().render(audio_path, str(out),
                             background_image=background_image, title=title)
    return str(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a script into a Shorts MP4.")
    parser.add_argument("--text", help="Script text. Overrides --text-file.")
    parser.add_argument("--text-file", help="Path to a file containing the script.")
    parser.add_argument("--title", default="Tata Nexon", help="Title drawn on the card.")
    parser.add_argument("--out", default="out/demo.mp4", help="Output MP4 path.")
    parser.add_argument("--bg", help="Optional background image (else a dark title card).")
    parser.add_argument("--voice", default="en-US-GuyNeural", help="edge-tts voice.")
    args = parser.parse_args()

    if args.text:
        script = args.text
    elif args.text_file:
        script = Path(args.text_file).read_text().strip()
    else:
        script = DEMO_SCRIPT

    path = build_video(script, args.title, args.out, background_image=args.bg, voice=args.voice)
    print(f"\nDone -> {path}")


if __name__ == "__main__":
    main()
