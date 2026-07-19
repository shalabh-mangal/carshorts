"""Produce a full video from a spec sheet: specs -> script -> fact-check -> video.

  python -m carshorts.produce --spec specs_top5/tata-nexon.json --language hinglish
  python -m carshorts.produce --script-file out/nexon.script.json --out out/nexon.mp4
  python -m carshorts.produce --spec ... --skip-factcheck        # render without the skeptic

Two halves, deliberately decoupled:
  - GENERATION (draft + fact-check) needs GEMINI_API_KEY and spends daily quota.
  - RENDERING (voice + assemble) is all local and free.

So the drafted script is SAVED the moment it is written, fact-check failure is
non-fatal (the video is marked UNVERIFIED, never silently "passed"), and you can
re-render any saved script with zero model calls via --script-file. This means a
quota limit can never waste a script you already paid for, and you can iterate on
the video freely without spending quota.

The printed Gate 1 report is your human checkpoint — read it before publishing.
Sections are voiced independently so each caption stays in sync with the audio.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path

from .adapters.footage import WikimediaImageSource, attribution_lines
from .adapters.llm import make_llm
from .adapters.music import generate_beat
from .adapters.renderer import MoviePyRenderer, Section
from .adapters.stock import PexelsVideoSource
from .adapters.tts import EdgeTTSProvider
from .gate1 import render_gate1_report
from .models import Script, Spec, SpecSheet
from .stages.pipeline import (
    draft_script,
    fact_check,
    structural_citation_check,
    unsourced_numbers_check,
)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _apply_extras(sheet: SpecSheet) -> str:
    """Merge a human-curated extras file (price estimate + best-value variant)
    into the sheet as a SOURCED spec, and return writer guidance text.

    Price/variant data isn't on Wikipedia and has no free API, so a human looks
    it up (CarDekho/CarWale/official) and drops it in specs_extras/<slug>.json.
    It becomes a real sourced spec (so the number-guard allows the figure); the
    value-variant pick is passed as guidance and phrased as opinion in the video.
    """
    path = Path("specs_extras") / f"{_slug(sheet.subject)}.json"
    if not path.exists():
        return ""
    extras = json.loads(path.read_text())
    price = extras.get("price_estimate")
    if not price:
        return ""
    note = extras.get("price_note", "estimate; varies by city")
    source = extras.get("price_source", "https://www.cardekho.com")
    sheet.specs.append(Spec(
        name="price_estimate",
        value=price,
        source_url=source,
        source_sentence=f"Estimated price {price} ({note}; source CarDekho/CarWale).",
    ))
    guidance = [f"PRICE (estimate, say so): {price} — {note}."]
    if extras.get("value_variant"):
        guidance.append(f"VALUE PICK (state as YOUR opinion): {extras['value_variant']}.")
    return " ".join(guidance)

VOICE_BY_LANG = {
    "english": "en-US-GuyNeural",
    "hinglish": "en-IN-PrabhatNeural",
    "hindi": "hi-IN-MadhurNeural",
}


def _is_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "quota" in text or "resourceexhausted" in text


def produce(spec_path: str | None, out_path: str, language: str = "english",
            voice: str | None = None, script_file: str | None = None,
            skip_factcheck: bool = False, provider: str | None = None,
            footage: bool = True, music: str | None = "auto",
            captions: bool = False, stock: bool | None = None) -> str:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # --- Get a script: either load a saved one (free) or draft one (uses a model).
    if script_file:
        script = Script.model_validate_json(Path(script_file).read_text())
        sheet = SpecSheet.model_validate_json(Path(spec_path).read_text()) if spec_path else None
        print(f"loaded script from {script_file} ({len(script.segments)} sections)")
    else:
        if not spec_path:
            raise SystemExit("Provide --spec (to write a script) or --script-file (to render one).")

        sheet = SpecSheet.model_validate_json(Path(spec_path).read_text())
        guidance = _apply_extras(sheet)   # merges sourced price + value-pick guidance
        llm = make_llm(provider)
        print(f"1/4  writing {language} script ({len(sheet.specs)} specs"
              + (", +price/variant" if guidance else "") + ")...")
        script = draft_script(sheet, llm, language=language, guidance=guidance)
        script_out = out.with_suffix(".script.json")
        script_out.write_text(script.model_dump_json(indent=2))
        print(f"     saved script -> {script_out}  (re-render free with --script-file)")

    # --- Safety gates. The number-guard is deterministic and always runs when we
    # have a sheet (free, model-independent). The LLM fact-check is best-effort
    # and non-fatal on quota — a failure marks the video UNVERIFIED.
    if sheet is not None:
        structural = structural_citation_check(script, sheet)
        number_problems = unsourced_numbers_check(script, sheet)
        if number_problems:
            print("\n🔴 NUMBER-GUARD — figures NOT found in the spec sheet (do NOT publish):")
            for problem in number_problems:
                print(f"     - {problem}")
            print()

        if not skip_factcheck:
            try:
                llm = make_llm(provider)
                print("2/4  fact-checking (separate skeptic pass)...")
                report = fact_check(script, sheet, llm)
                print("\n" + render_gate1_report(
                    script, sheet, report, structural + number_problems) + "\n")
            except Exception as exc:  # noqa: BLE001
                if _is_quota_error(exc):
                    print("\n⚠️  LLM FACT-CHECK SKIPPED — model quota exhausted. Video renders "
                          "UNVERIFIED (number-guard above still applied). Re-run the "
                          "fact-check before publishing.\n")
                else:
                    raise
        else:
            print("2/4  LLM fact-check skipped (--skip-factcheck) — number-guard above still applied.")
    else:
        print("2/4  no spec sheet given — both gates skipped, video is UNVERIFIED.")

    # --- Fetch legal CC car photos (exact-car identity), attributed.
    images: list[str] = []
    if footage:
        img_dir = f"assets/images/{_slug(script.subject)}"
        print(f"3/5  fetching CC car photos -> {img_dir} ...")
        try:
            images = WikimediaImageSource().fetch(script.subject, img_dir, limit=6)
            print(f"     {len(images)} images (credits in {img_dir}/attributions.json)")
        except Exception as exc:  # noqa: BLE001 — no photos just means plain cards
            print(f"     footage fetch failed ({exc}); using plain caption cards.")

    # --- Fetch generic stock video b-roll (real motion) if a Pexels key exists.
    stock_videos: list[str] = []
    use_stock = stock if stock is not None else bool(os.environ.get("PEXELS_API_KEY"))
    if use_stock:
        print("     fetching stock car b-roll (Pexels) for motion...")
        try:
            stock_videos = PexelsVideoSource().fetch("assets/stock", limit=4)
            print(f"     {len(stock_videos)} stock clips")
        except Exception as exc:  # noqa: BLE001 — fall back to stills
            print(f"     stock fetch failed ({exc}); stills only.")

    # --- Render (always local, always free). Voice each section separately so
    # visuals stay in sync. Interleave: exact-car stills for identity, stock
    # video for motion.
    voice = voice or VOICE_BY_LANG.get(language, "en-US-GuyNeural")
    print(f"4/5  voicing {len(script.segments)} sections (voice={voice})...")
    tts = EdgeTTSProvider(voice=voice)
    tmpdir = Path(tempfile.mkdtemp(prefix="carshorts_"))
    sections = []
    for i, seg in enumerate(script.segments):
        audio_path = str(tmpdir / f"seg_{i}.mp3")
        tts.synthesize(seg.text, audio_path)
        bg_image = bg_video = None
        if stock_videos and i % 2 == 1:
            bg_video = stock_videos[(i // 2) % len(stock_videos)]   # odd scenes: motion
        elif images:
            bg_image = images[i % len(images)]                       # even scenes: the car
        sections.append(Section(audio_path=audio_path, caption=seg.text,
                                background_image=bg_image, background_video=bg_video))

    # Background music: auto-generate a royalty-free beat unless disabled/overridden.
    music_path: str | None = None
    if music == "auto":
        music_path = str(out.with_suffix(".beat.wav"))
        print("     generating royalty-free beat...")
        generate_beat(music_path, duration=90)
    elif music and music != "none":
        music_path = music

    print(f"5/5  rendering synced video -> {out_path}  "
          f"(captions={'on' if captions else 'off'}, music={'yes' if music_path else 'no'})")
    MoviePyRenderer().render_sections(sections, str(out), music_path=music_path,
                                      draw_captions=captions)

    credits = attribution_lines(f"assets/images/{_slug(script.subject)}") if images else []
    if credits:
        print("\nImage credits (put these in the YouTube description):")
        for line in credits:
            print(f"  {line}")
    return str(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Spec sheet -> fact-checked, synced video.")
    parser.add_argument("--spec", help="Path to a spec-sheet JSON (to write + fact-check).")
    parser.add_argument("--script-file", help="Render a previously saved script JSON (no model calls).")
    parser.add_argument("--out", default="out/produced.mp4", help="Output MP4 path.")
    parser.add_argument("--language", default="english",
                        choices=["english", "hinglish", "hindi"], help="Script + voice language.")
    parser.add_argument("--voice", help="Override the edge-tts voice.")
    parser.add_argument("--skip-factcheck", action="store_true",
                        help="Skip the skeptic pass (renders UNVERIFIED).")
    parser.add_argument("--provider", choices=["gemini", "groq", "cerebras", "openrouter", "ollama"],
                        help="LLM backend (or set CARSHORTS_LLM). Default gemini.")
    parser.add_argument("--no-footage", action="store_true", help="Skip CC photo fetch (plain cards).")
    parser.add_argument("--captions", action="store_true", help="Burn captions on screen (default off).")
    parser.add_argument("--music", default="auto",
                        help="'auto' (generate a beat, default), 'none', or a path to a track.")
    parser.add_argument("--stock", action="store_true", help="Force stock-video b-roll (needs PEXELS_API_KEY).")
    parser.add_argument("--no-stock", action="store_true", help="Disable stock video (stills only).")
    args = parser.parse_args()

    stock = True if args.stock else (False if args.no_stock else None)
    path = produce(args.spec, args.out, language=args.language, voice=args.voice,
                   script_file=args.script_file, skip_factcheck=args.skip_factcheck,
                   provider=args.provider, footage=not args.no_footage, music=args.music,
                   captions=args.captions, stock=stock)
    print(f"\nDone -> {path}")


if __name__ == "__main__":
    main()
