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
from .adapters.tts import make_tts
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

    # Fresh news items: each becomes a SOURCED fact (skeptic + number-guard
    # cover it) plus guidance to lead the hook with the strongest one — news is
    # a built-in curiosity gap ("X just happened" beats "X exists").
    for n, item in enumerate(extras.get("news", []), start=1):
        fact = item.get("fact", "").strip()
        if not fact:
            continue
        sheet.specs.append(Spec(
            name=f"news_{n}",
            value=fact[:80],
            source_url=item.get("source", source),
            source_sentence=f"{fact} (as reported {item.get('date', 'recently')}).",
        ))
        guidance.append(f"FRESH NEWS #{n} (fact, cite as news_{n}): {fact}.")
    if extras.get("news"):
        guidance.append("Lead the HOOK with the strongest news item — timeliness is the hype.")
    variant = extras.get("value_variant")
    features = extras.get("value_features")
    if variant:
        # Back the variant NAME too, so "the Creative variant" reads as sourced
        # (the recommendation itself stays opinion).
        sheet.specs.append(Spec(
            name="value_variant",
            value=variant,
            source_url=extras.get("value_source", source),
            source_sentence=(f"The {variant} variant is widely considered the "
                             f"value-for-money pick (source CarDekho)."),
        ))
        # Make the value variant's features a SOURCED spec so the fact-checker
        # passes them, then tell the writer to NAME them (concrete features sell).
        vp = extras.get("value_price", "")
        if features:
            # Include the variant price in the sourced sentence so the writer may
            # quote it (e.g. "ZXi around ₹7.53 lakh") without the number-guard
            # flagging it as fabricated.
            price_clause = f" ({vp})" if vp else ""
            sheet.specs.append(Spec(
                name="value_features",
                value=features,
                source_url=extras.get("value_source", source),
                source_sentence=(f"The {variant} variant{price_clause} includes {features} "
                                 f"(source CarDekho)."),
            ))
        guidance.append(
            f"VALUE PICK (your opinion): the {variant} variant {vp} is the sweet "
            f"spot. NAME these concrete features it gives you: {features or 'key features'}."
        )
    return " ".join(guidance)

VOICE_BY_LANG = {
    "english": "en-US-GuyNeural",
    "hinglish": "en-IN-PrabhatNeural",
    "hindi": "hi-IN-MadhurNeural",
}



def _llm_shot_match(segments, pool: list[str], provider: str | None) -> dict[int, list[str]]:
    """One LLM call: rank pool assets per script beat by semantic fit (asset
    filenames are descriptive). Returns {section_index: [asset paths ranked]}.
    Empty dict on any failure — callers fall back to keyword hints."""
    import os as _os
    if not pool or not (provider or _os.environ.get("GROQ_API_KEY")):
        return {}
    try:
        from .stages.pipeline import _rows  # tolerant JSON row coercion
        llm = make_llm(provider or "groq")
        names = [Path(a).name for a in pool]
        beats = "\n".join(f"{i}. [{seg.role}] {seg.text}" for i, seg in enumerate(segments))
        assets = "\n".join(f"- {n}" for n in names)
        system = (
            "You match visuals to a car-video script. For EACH beat, rank the 3 "
            "best-fitting asset filenames (they describe their content). Match "
            "meaning: engine lines -> engine shots, off-road claims -> "
            "mud/trail/river action, news/facelift -> press/roxx images, price/"
            "value -> interior/feature shots. Output ONLY a JSON array: "
            '[{"beat": <index>, "assets": ["<filename>", ...]}]'
        )
        rows = _rows(llm.complete_json(system, f"BEATS:\n{beats}\n\nASSETS:\n{assets}"))
        by_name = {Path(a).name: a for a in pool}
        ranked: dict[int, list[str]] = {}
        for row in rows:
            try:
                idx = int(row.get("beat"))
            except (TypeError, ValueError):
                continue
            ranked[idx] = [by_name[n] for n in row.get("assets", []) if n in by_name]
        return ranked
    except Exception:  # noqa: BLE001 — matcher is best-effort
        return {}


def _is_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "quota" in text or "resourceexhausted" in text


def produce(spec_path: str | None, out_path: str, language: str = "english",
            voice: str | None = None, script_file: str | None = None,
            skip_factcheck: bool = False, provider: str | None = None,
            footage: bool = True, music: str | None = "auto",
            captions: bool = False, stock: bool | None = None,
            voice_engine: str = "edge", persona: str = "",
            shots_file: str | None = None) -> str:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # --- Get a script: either load a saved one (free) or draft one (uses a model).
    if script_file:
        script = Script.model_validate_json(Path(script_file).read_text())
        sheet = SpecSheet.model_validate_json(Path(spec_path).read_text()) if spec_path else None
        if sheet is not None:
            _apply_extras(sheet)   # merge sourced price/variant so the guard knows them
        print(f"loaded script from {script_file} ({len(script.segments)} sections)")
    else:
        if not spec_path:
            raise SystemExit("Provide --spec (to write a script) or --script-file (to render one).")

        sheet = SpecSheet.model_validate_json(Path(spec_path).read_text())
        guidance = _apply_extras(sheet)   # merges sourced price + value-pick guidance
        from .learnings import load_learnings_guidance
        craft = load_learnings_guidance()
        if craft:
            guidance = f"{guidance}\n\n{craft}" if guidance else craft
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

    # --- Car photos: prefer the hand-VETTED local folder; fetch CC photos only
    # when it's empty (fetched images must then be vetted — old-gen/plates).
    images: list[str] = []
    if footage:
        img_dir = f"assets/cars/{_slug(script.subject)}/images"
        images = sorted(str(p) for p in Path(img_dir).glob("*.[jp][pn]g"))
        if images:
            print(f"3/5  using {len(images)} vetted local images from {img_dir}")
        else:
            print(f"3/5  fetching CC car photos -> {img_dir} ...")
            try:
                images = WikimediaImageSource().fetch(script.subject, img_dir, limit=6)
                print(f"     {len(images)} images (VET THESE — generation + plates)")
            except Exception as exc:  # noqa: BLE001 — no photos just means plain cards
                print(f"     footage fetch failed ({exc}); using plain caption cards.")

    # --- Stock b-roll: prefer the VETTED local folder (curated by hand); only
    # fetch fresh clips when the folder is empty and a Pexels key exists.
    stock_videos: list[str] = []
    use_stock = stock if stock is not None else True
    if use_stock:
        stock_videos = sorted(str(p) for p in Path("assets/stock").glob("*.mp4"))
        if stock_videos:
            print(f"     using {len(stock_videos)} vetted local stock clips")
        elif os.environ.get("PEXELS_API_KEY"):
            print("     fetching stock car b-roll (Pexels) for motion...")
            try:
                stock_videos = PexelsVideoSource().fetch("assets/stock", limit=4)
                print(f"     {len(stock_videos)} stock clips (VET THESE — check each)")
            except Exception as exc:  # noqa: BLE001 — fall back to stills
                print(f"     stock fetch failed ({exc}); stills only.")

    # --- Render (always local, always free). Voice each section separately so
    # visuals stay in sync. Interleave: exact-car stills for identity, stock
    # video for motion.
    # persona picks voice+energy for English; language picks the voice otherwise.
    voice = voice or (None if persona else VOICE_BY_LANG.get(language, "en-US-GuyNeural"))
    tts = make_tts(engine=voice_engine, persona=persona, voice=voice)
    print(f"4/5  voicing {len(script.segments)} sections "
          f"(engine={voice_engine}, persona={persona or 'default'})...")
    ai_dir = Path("assets/cars") / _slug(script.subject) / "own"

    # --- Voice all sections first so we know each duration, then distribute a
    # visual POOL across fast sub-scenes (~2.8s cuts). Every asset is used at
    # most once across the whole video (repeats read as cheap), interleaving
    # the user's real clips with stock motion and stills for variety.
    tmpdir = Path(tempfile.mkdtemp(prefix="carshorts_"))
    from moviepy import AudioFileClip as _Audio

    # TTS cache: keyed by engine+voice+text, so re-renders (music/visual tweaks)
    # never re-spend paid voice credits on unchanged lines.
    import hashlib
    cache_dir = Path("out/tts_cache") / voice_engine
    cache_dir.mkdir(parents=True, exist_ok=True)

    audio_paths, durations = [], []
    for i, seg in enumerate(script.segments):
        key = hashlib.md5(f"{voice_engine}|{voice}|{persona}|{seg.text}".encode()).hexdigest()[:16]
        cached = cache_dir / f"{key}.mp3"
        if not cached.exists():
            tts.synthesize(seg.text, str(cached))
        audio_paths.append(str(cached))
        durations.append(_Audio(str(cached)).duration)

    user_clips = sorted(str(p) for p in ai_dir.glob("*.mp4"))

    # Order the pool so visually-similar shots never sit adjacent: bucket by
    # look (pool_NN_<category> prefix for own clips, query name for stock),
    # then round-robin across buckets.
    # Alias visually-similar categories into one family so all steering/gauge
    # POVs (wheelpov / cluster / wheel2) count as the SAME look and get maximum
    # spacing — three different files that look alike still read as repetition.
    look_alias = {"wheelpov": "wheel", "wheel": "wheel", "cluster": "wheel",
                  "windshield": "glass", "switches": "door"}

    def _bucket(asset: str) -> str:
        name = Path(asset).stem
        if name.startswith("pool_"):
            category = re.sub(r"\d+$", "", name.split("_", 2)[-1])
            return look_alias.get(category, category)
        return name.split("_")[0]

    buckets: dict[str, list[str]] = {}
    for asset in user_clips + stock_videos + list(images):
        buckets.setdefault(_bucket(asset), []).append(asset)
    pool: list[str] = []
    bucket_lists = list(buckets.values())
    idxs = [0] * len(bucket_lists)
    while any(idxs[k] < len(bucket_lists[k]) for k in range(len(bucket_lists))):
        for k in range(len(bucket_lists)):
            if idxs[k] < len(bucket_lists[k]):
                pool.append(bucket_lists[k][idxs[k]])
                idxs[k] += 1
    print(f"     visual pool: {len(user_clips)} own clips + {len(stock_videos)} stock "
          f"+ {len(images)} stills = {len(pool)} (similar shots spaced apart)")

    # Adapt cut length to the pool so no asset repeats: aim ~2.8s cuts, but
    # stretch (up to 3.8s) when the pool is small.
    total = sum(durations)
    target = 2.3   # snappy default; stretch until the pool covers every cut so
    # nothing has to repeat (per-section rounding can overshoot, hence the loop)
    if pool:
        while target < 4.2 and sum(
                max(1, round(d / target)) for d in durations) > len(pool):
            target += 0.1

    # Topic hints: route an asset to the beat that talks about it (AC clip on
    # the AC line, petrol station on mileage, engine shot on the engine beat).
    topic_hints = [
        (re.compile(r"facelift|Roxx|2026", re.I), re.compile(r"roxx|press", re.I)),
        (re.compile(r"4x4|off-?road", re.I), re.compile(r"offroad|mud|trail|mountain", re.I)),
        (re.compile(r"vent|\bAC\b|climate", re.I), re.compile(r"vent|air_conditioning", re.I)),
        (re.compile(r"kmpl|mileage|fuel|wallet", re.I), re.compile(r"fuel|petrol", re.I)),
        (re.compile(r"engine|litre|\bPS\b|torque", re.I), re.compile(r"engine|cluster", re.I)),
        (re.compile(r"touchscreen|ZXi|alloys|projector", re.I), re.compile(r"console|side", re.I)),
    ]
    used: set = set()
    reuse_cursor = [len(pool) // 2]   # overflow reuse starts mid-pool, spreads out

    def _grab(matcher, want: int, section_buckets: set) -> list[str]:
        """Pick unused assets, at most ONE per look-family per section — two
        same-family shots inside one beat read as a repeat even if distinct."""
        picked = []
        for asset in pool:
            if len(picked) >= want:
                break
            if asset in used or not matcher(asset):
                continue
            if _bucket(asset) in section_buckets:
                continue
            picked.append(asset)
            used.add(asset)
            section_buckets.add(_bucket(asset))
        return picked

    llm_ranked = _llm_shot_match(script.segments, pool, provider)
    if llm_ranked:
        print(f"     shot-matcher aligned {len(llm_ranked)} beats to visuals")
    sections = []
    prev_last_bucket = ""
    for i, seg in enumerate(script.segments):
        chunks = max(1, round(durations[i] / target))
        visuals: list[str] = []
        section_buckets: set = set()
        for asset in llm_ranked.get(i, []):     # semantic matches first
            if len(visuals) >= chunks:
                break
            if asset in used or _bucket(asset) in section_buckets:
                continue
            visuals.append(asset)
            used.add(asset)
            section_buckets.add(_bucket(asset))
        for text_pat, file_pat in topic_hints:
            if text_pat.search(seg.text):
                visuals += _grab(lambda a, p=file_pat: bool(p.search(Path(a).name)),
                                 chunks - len(visuals), section_buckets)
                break
        visuals += _grab(lambda a: True, chunks - len(visuals), section_buckets)
        # Avoid a same-look seam across the section boundary: if this section
        # opens with the family the previous one closed on, swap in a later
        # visual from a different family.
        if visuals and sections and prev_last_bucket == _bucket(visuals[0]):
            for j in range(1, len(visuals)):
                if _bucket(visuals[j]) != prev_last_bucket:
                    visuals[0], visuals[j] = visuals[j], visuals[0]
                    break
        if visuals:
            prev_last_bucket = _bucket(visuals[-1])
        while len(visuals) < chunks and pool:                     # pool exhausted:
            # continue round-robin from a moving cursor so reuse is spread
            # across different assets, never hammering the same opening clip.
            visuals.append(pool[reuse_cursor[0] % len(pool)])
            reuse_cursor[0] += 1
        sections.append(Section(audio_path=audio_paths[i], caption=seg.text,
                                background_pool=visuals))

    # Background music: auto-generate a royalty-free beat unless disabled/overridden.
    music_path: str | None = None
    if music == "auto":
        library = sorted(Path("assets/music").glob("*.mp3")) + sorted(Path("assets/music").glob("*.wav"))
        if library:
            music_path = str(library[0])
            print(f"     music: {Path(music_path).name} (from assets/music)")
        else:
            music_path = str(out.with_suffix(".beat.wav"))
            print("     generating royalty-free beat...")
            generate_beat(music_path, duration=90)
    elif music and music != "none":
        music_path = music

    print(f"5/5  rendering synced video -> {out_path}  "
          f"(captions={'on' if captions else 'off'}, music={'yes' if music_path else 'no'})")
    MoviePyRenderer().render_sections(sections, str(out), music_path=music_path,
                                      draw_captions=captions)

    # Recipe card: log every creative choice so analytics can attribute results.
    try:
        import datetime as _dt
        hook = script.segments[0]
        recipe = {
            "out": str(out), "subject": script.subject,
            "rendered_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "script_file": script_file or str(out.with_suffix(".script.json")),
            "persona": persona or "default", "voice_engine": voice_engine,
            "language": language, "music": Path(music_path).name if music_path else "none",
            "captions": captions, "word_count": script.approx_word_count(),
            "sections": len(script.segments),
            "hook_text": hook.text,
            "hook_type": ("news" if any(c.startswith("news") for c in hook.cited_spec_names)
                          else "question" if "?" in hook.text else "statement"),
            "pool": {"own": len(user_clips), "stock": len(stock_videos), "stills": len(images)},
            "cut_target_s": round(target, 2),
            "video_id": None, "metrics": None
        }
        rp = Path("data/recipes") / (out.stem + ".json")
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps(recipe, indent=2))
        print(f"     recipe card -> {rp}")
    except Exception as exc:  # noqa: BLE001 — logging must never break a render
        print(f"     recipe card skipped ({exc})")

    credits = attribution_lines(f"assets/cars/{_slug(script.subject)}/images") if images else []
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
    parser.add_argument("--voice-engine", default="edge", choices=["edge", "elevenlabs"],
                        help="edge (free) or elevenlabs (expressive, needs ELEVENLABS_API_KEY).")
    parser.add_argument("--persona", default="", choices=["", "bhai", "deadpan", "hype"],
                        help="Voice energy profile (edge rate/pitch).")
    parser.add_argument("--shots", help="Shot-plan JSON (routes beats to AI clips vs car footage).")
    args = parser.parse_args()

    stock = True if args.stock else (False if args.no_stock else None)
    path = produce(args.spec, args.out, language=args.language, voice=args.voice,
                   script_file=args.script_file, skip_factcheck=args.skip_factcheck,
                   provider=args.provider, footage=not args.no_footage, music=args.music,
                   captions=args.captions, stock=stock,
                   voice_engine=args.voice_engine, persona=args.persona,
                   shots_file=args.shots)
    print(f"\nDone -> {path}")


if __name__ == "__main__":
    main()
