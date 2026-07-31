"""Produce a full video from a spec sheet: specs -> script -> fact-check -> video.

  python -m carshorts.rendering.produce --spec specs/tata-nexon.json --language hinglish
  python -m carshorts.rendering.produce --script-file out/nexon.script.json --out out/nexon.mp4
  python -m carshorts.rendering.produce --spec ... --skip-factcheck        # render without the skeptic

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
from pathlib import Path

from carshorts.adapters.footage import WikimediaImageSource, attribution_lines
from carshorts.adapters.llm import make_llm
from carshorts.adapters.music import generate_beat
from carshorts.adapters.renderer import MoviePyRenderer, Section
from carshorts.adapters.stock import PexelsVideoSource
from carshorts.adapters.tts import make_tts
from carshorts.core import paths
from carshorts.core.models import Script, Spec, SpecSheet
from carshorts.writing.draft import (
    draft_script,
    fact_check,
    structural_citation_check,
    unsourced_features_check,
    unsourced_numbers_check,
)
from carshorts.writing.gate1 import render_gate1_report


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
    source = extras.get("price_source", "https://www.cardekho.com")
    guidance: list[str] = []

    # PRICE is optional. It is human-supplied (never scraped — see CLAUDE.md), so
    # a freshly crawled car legitimately has news long before it has a price.
    # This used to `return ""` when price was missing, which silently discarded
    # every news item on such a car — the newscrawl output went nowhere.
    price = extras.get("price_estimate")
    if price:
        note = extras.get("price_note", "estimate; varies by city")
        sheet.specs.append(Spec(
            name="price_estimate",
            value=price,
            source_url=source,
            source_sentence=f"Estimated price {price} ({note}; source CarDekho/CarWale).",
        ))
        guidance.append(f"PRICE (estimate, say so): {price} — {note}.")

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




_KW_NUM = re.compile(
    r"(?:₹|Rs\.?\s?)?\d[\d,.]*\s?(?:to|–|-)?\s?(?:₹|Rs\.?\s?)?[\d,.]*\s?"
    r"(?:lakh|crore|PS|bhp|kW|Nm|N⋅m|kmpl|km/h|seconds?|litre|liter|-litre)", re.I)


def _keyword_for(seg) -> str:
    """Short punch text shown on screen while the beat is spoken. Muted viewers
    (the majority on Shorts) must still get the payoff."""
    m = _KW_NUM.search(seg.text)
    if m:
        return m.group(0).strip().rstrip(".,")[:22]
    frag = ""
    for w in (w.strip(",.!—-") for w in seg.text.split()):
        if not w:
            continue
        if len(frag) + len(w) + 1 > 24:   # whole words only, never chop mid-word
            break
        frag = f"{frag} {w}".strip()
    return frag + ("?" if "?" in seg.text and not frag.endswith("?") else "")


def _news_callouts() -> list[str]:
    return []   # replaced per-car below by _news_callouts_for


def _news_callouts_for(sheet) -> list[str]:
    """What's-new card lines from the extras news_callouts list."""
    if sheet is None:
        return []
    path = Path("specs_extras") / f"{_slug(sheet.subject)}.json"
    if not path.exists():
        return []
    try:
        return list(json.loads(path.read_text()).get("news_callouts", []))[:5]
    except Exception:  # noqa: BLE001
        return []


def _callout_lines_for(sheet) -> list[str]:
    """Feature lines for the value-beat card, from the sourced value spec."""
    idx = sheet.fact_index() if sheet else {}
    feat = idx.get("value_features")
    variant = idx.get("value_variant")
    if not feat:
        return []
    raw = re.split(r",| and ", feat.value)
    lines = [f.strip().rstrip(".").capitalize() for f in raw if f.strip()][:4]
    if variant:
        lines.insert(0, f"{variant.value} = value pick")
    return lines



def _phrases_with_times(text: str, marks_file: str | None) -> list[tuple[float, str]]:
    """Split narration into phrases and anchor each to its spoken start time
    (word-boundary marks from TTS). Falls back to a single phrase when marks
    are unavailable (e.g. cached ElevenLabs audio)."""
    from carshorts.adapters.tts import normalize_for_speech

    norm = normalize_for_speech(text)
    raw = [p.strip() for p in re.split(r"(?<=[,.;:!?])\s+|\s+—\s+", norm) if p.strip()]
    phrases: list[str] = []
    for ph in raw:   # merge fragments so no cut is shorter than ~3 words
        if phrases and (len(ph.split()) < 3 or len(phrases[-1].split()) < 3):
            phrases[-1] += " " + ph
        else:
            phrases.append(ph)
    if not marks_file or not Path(marks_file).exists() or len(phrases) <= 1:
        return [(0.0, norm)]
    try:
        marks = json.loads(Path(marks_file).read_text())
    except Exception:  # noqa: BLE001
        return [(0.0, norm)]
    if not marks:
        return [(0.0, norm)]
    out: list[tuple[float, str]] = []
    word_i = 0
    for ph in phrases:
        t = marks[min(word_i, len(marks) - 1)]["t"]
        # start the visual a beat BEFORE the word lands (pro b-roll lead)
        out.append((max(0.0, t - 0.15), ph))
        word_i += len(ph.split())
    out[0] = (0.0, out[0][1])
    return out




def _exact_span(frag: str, marks_file: str | None, fallback: tuple) -> tuple | None:
    """Time on-screen text to the EXACT moment its words are SPOKEN. Finds the
    fragment's word sequence in the TTS word marks; text appears with the first
    word, leaves shortly after the last. Owner feedback: 'magic happens if text
    appears with beats only when perfectly timed with voice'."""
    if not marks_file or not Path(marks_file).exists():
        return None          # no word timeline -> no on-screen text at all
    try:
        marks = json.loads(Path(marks_file).read_text())
    except Exception:  # noqa: BLE001
        return None

    def norm(word: str) -> str:
        # keep interior dots (decimals like 10.25) but drop sentence-final ones
        return re.sub(r"\.+$", "", re.sub(r"[^a-z0-9.]", "", word.lower()))

    want = [norm(w) for w in frag.split() if norm(w)]
    # a single TTS mark can carry MULTIPLE words ("Level 2" arrives as one
    # boundary) — flatten to word granularity, remembering each word's mark
    have: list[str] = []
    mark_of: list[int] = []
    for mi, m in enumerate(marks):
        for piece in m["w"].split():
            n = norm(piece)
            if n:
                have.append(n)
                mark_of.append(mi)
    if not want or not have:
        return None
    for i in range(len(have) - len(want) + 1):
        if have[i:i + len(want)] == want:
            first_mark = mark_of[i]
            last_mark = mark_of[i + len(want) - 1]
            start = max(0.0, marks[first_mark]["t"] - 0.05)
            end = (marks[last_mark + 1]["t"] if last_mark + 1 < len(marks)
                   else marks[last_mark]["t"] + 0.8)
            return (start, max(1.2, end - start + 0.35))
    return None              # words not found -> perfectly timed or absent


_POP_MAX_PER_SECTION = 6
_POP_GAP = 0.15
# CTA narrations that speak "like, share, subscribe" (any punctuation between)
# auto-generate an LSS graphic pop — the renderer draws three icons in place
# of text (thumbs-up / share arrow / bell). Detects any word order-preserving
# spacing so "like, share, subscribe" and "like share subscribe" both trigger.
_LSS_RE = re.compile(r"\blike\W+share\W+subscribe\b", re.I)


def _clip_brightness(path: str) -> float:
    """Score a clip's ACTUAL first frame by brightness × contrast — used to pick
    the opener from motion clips. Sampling frame 0 (what the feed-norm QA sees)
    and weighting contrast rejects BOTH a dark interior AND a blown-out/blank
    transition frame (bright but flat), either of which fails the QA and makes a
    poor thumbnail. Best-effort: 0.0 if it can't be read."""
    import os as _os
    import subprocess as _sp
    import tempfile

    from PIL import Image
    tmp = tempfile.mktemp(suffix=".jpg")
    try:
        _sp.run(["ffmpeg", "-y", "-i", path, "-frames:v", "1",
                 "-vf", "scale=64:-1", tmp], capture_output=True)
        if not _os.path.exists(tmp):
            return 0.0
        with Image.open(tmp) as im:
            data = list(im.convert("L").getdata())
        if not data:
            return 0.0
        mean = sum(data) / len(data)
        std = (sum((d - mean) ** 2 for d in data) / len(data)) ** 0.5
        return mean * std            # bright AND contrasty (not blank, not dark)
    except Exception:  # noqa: BLE001 — brightness is a hint, never a hard dependency
        return 0.0
    finally:
        try:
            _os.unlink(tmp)
        except OSError:
            pass


def _subject_families(subject: str) -> set[str]:
    """Name tokens that identify THIS car in asset filenames (plus curated
    aliases from specs_extras, e.g. Thar -> roxx). Used by the edge-beat
    car rule and written into the manifest for QA."""
    slug = _slug(subject)
    families = {t for t in slug.split("-") if len(t) >= 3} | {"pool"}
    extras_path = Path("specs_extras") / f"{slug}.json"
    if extras_path.exists():
        try:
            families |= {a.lower() for a in
                         json.loads(extras_path.read_text()).get("aliases", [])}
        except Exception:  # noqa: BLE001
            pass
    return families


def _pop_candidates(seg, sheet) -> list[dict]:
    """Pop candidates, strongest first: curated script pops, then every spec
    figure in the line, then cited spec VALUES spoken verbatim — the spec
    sheet is the well of extra on-screen information. Kinds:
      word     — white transcript fragment
      number   — cyan figure + white unit, marker-wipe underline
      reaction — written editorial reaction, fires AFTER the anchor (punchlines)
      card     — big count-up number card, THE payoff stat, max one per short
    """
    def kind_of(show: str) -> str:
        return "number" if any(ch.isdigit() for ch in show) else "word"

    out: list[dict] = []
    for c in (getattr(seg, "pops", None) or []):
        if isinstance(c, dict):
            anchor = c.get("anchor", "")
            show = c.get("show", "") or anchor
            kind = ("card" if c.get("card")
                    else "reaction" if show.strip().lower() != anchor.strip().lower()
                    else kind_of(show))
            label = c.get("label", "")
        else:
            anchor, show, kind, label = c, c, kind_of(c), ""
        if anchor and len(show) <= 26:
            out.append({"anchor": anchor, "show": show, "kind": kind, "label": label})
    for match in _KW_NUM.finditer(seg.text):
        cand = match.group(0).strip().rstrip(".,")
        if cand and len(cand) <= 26 and all(cand != o["anchor"] for o in out):
            out.append({"anchor": cand, "show": cand, "kind": "number", "label": ""})
    if sheet is not None:
        for spec in sheet.specs:
            value = spec.value.strip().rstrip(".,")
            if (2 < len(value) <= 26 and value.lower() in seg.text.lower()
                    and all(value != o["anchor"] for o in out)):
                out.append({"anchor": value, "show": value,
                            "kind": kind_of(value), "label": ""})
    return out


def _word_pops(seg, marks_file: str | None, dur: float,
               sheet=None) -> list[tuple]:
    """WORD-SYNCED HIGHLIGHT POPS — the single on-screen text engine.

    Every candidate's ANCHOR words are matched word-exactly against the TTS
    word timeline; no word-exact match, no text — ever. Transcript pops render
    from the first anchor word to just after the last. Reaction pops fire in
    the SILENCE BEAT ~0.25s after the anchor ends (comedy-editing standard:
    the reaction lands after the line, never on it). Returns
    [(start, dur, show_text, kind, label)].
    """
    # SELECT-ALL-THEN-TRIM: match every candidate first; the karaoke pass
    # below resolves overlaps by trimming, not by silently dropping owner-
    # requested pops (the old crowding gate ate rapid spec lists).
    rail: list[tuple] = []          # word/number pops share the y=0.64 rail
    floaters: list[tuple] = []      # reaction (y=0.30) and card have own slots
    for cand in _pop_candidates(seg, sheet):
        span = _exact_span(cand["anchor"], marks_file, (0.0, 0.0))
        if span is None:
            continue
        start, span_dur = span
        if cand["kind"] == "reaction":
            # fire in the silence beat after the anchor. Punchlines usually END
            # a beat, so the reaction may straddle the section cut — allowed:
            # it renders on the global timeline, and the cut IS the silence.
            if dur < 1.2:
                continue
            start = min(start + span_dur - 0.35 + 0.25, dur - 0.4)
            floaters.append((start, 1.1, cand["show"], "reaction", ""))
            continue
        if cand["kind"] == "card":
            # Card holds until the section beat ends (owner: keep the value
            # card up while the voice keeps talking about it). ~2.2s is the
            # animated count-up; the rest is a static hold on the final figure.
            span_dur = max(2.2, dur - start - 0.3)
            if start < dur - 0.5:
                floaters.append((start, span_dur, cand["show"], "card",
                                 cand["label"]))
            continue
        span_dur = min(span_dur, 3.5, max(0.9, dur - start - 0.1))
        if start < dur - 0.5:
            rail.append((start, span_dur, cand["show"], cand["kind"],
                         cand["label"]))
    # Auto-LSS: if the narration speaks "like, share, subscribe", generate a
    # graphic pop timed word-exactly to those three words. Renderer draws the
    # icon strip; the show text is a manifest tag so QA/tests can see it.
    if _LSS_RE.search(seg.text):
        lss_span = _exact_span("like share subscribe", marks_file, (0.0, 0.0))
        if lss_span is not None:
            lss_start, _ = lss_span
            lss_dur = max(0.9, dur - lss_start - 0.2)
            if lss_start < dur - 0.5:
                floaters.append((lss_start, lss_dur, "LSS", "lss", ""))
    # the card owns the screen while it counts up (first 2.2s). AFTER the
    # count-up settles, rail pops may run again — the static hold on the
    # final figure isn't a focal-point conflict, so let feature pops fire
    # over it (owner: rail must render AFTER the count-up settles).
    cards = [f for f in floaters if f[3] == "card"]
    rail = [r for r in rail
            if not any(r[2] == c[2]
                       or (c[0] <= r[0] < c[0] + 2.2)
                       for c in cards)]
    # karaoke pass: rail pops replace each other — trim each to the next
    # pop's start; drop only what lands under the 0.5s legibility floor
    rail.sort()
    trimmed: list[tuple] = []
    for j, pop in enumerate(rail):
        if len(trimmed) >= _POP_MAX_PER_SECTION:
            break
        span_dur = pop[1]
        if j + 1 < len(rail):
            span_dur = min(span_dur, rail[j + 1][0] - pop[0] - 0.05)
        if span_dur >= 0.5:
            trimmed.append((pop[0], span_dur, pop[2], pop[3], pop[4]))
    return sorted(trimmed + floaters)


def _time_callouts(lines: list[str], sec_phrases: list[tuple[float, str]],
                   dur: float) -> list[tuple[float, float, str]]:
    """Anchor each callout line to the phrase that SPEAKS it (token overlap),
    so text appears with its words and leaves when the section's context ends."""
    timed: list[tuple[float, float, str]] = []
    last = 0.4
    for line in lines:
        tokens = {w.lower().strip('.,"“”()') for w in line.split() if len(w) > 3}
        best_t, best_score = None, 0
        for (t, txt) in sec_phrases:
            ph = {w.lower().strip('.,"“”()') for w in txt.split() if len(w) > 3}
            score = len(tokens & ph)
            if score > best_score:
                best_score, best_t = score, t
        # end when the NEXT line's words begin (no stale text), else short hold
        if best_t is None or best_score == 0:
            # first line (card title) may lead the section; anything else that
            # can't anchor to spoken words is dropped — no guessed timings
            if timed:
                continue
            best_t = 0.35
        start = max(best_t - 0.1, last, 0.2)     # keep list order monotonic
        end = min(dur - 0.05, start + 6.0)       # hold while context lasts, no longer
        if start < dur - 0.6:
            timed.append((start, end, line))
            last = start + 0.5
    return timed


def _llm_phrase_match(entries: list[tuple[int, int, str]], pool: list[str],
                      provider: str | None) -> dict[tuple[int, int], str]:
    """One call: best asset per PHRASE (or NONE). entries = (sec, ph, text)."""
    import os as _os
    if not pool or not (provider or _os.environ.get("GROQ_API_KEY")):
        return {}
    try:
        from carshorts.writing.draft import _rows
        llm = make_llm(provider or "groq")
        names = [Path(a).name for a in pool]
        listing = "\n".join(f"{si}.{pi}: {txt}" for si, pi, txt in entries)
        assets = "\n".join(f"- {n}" for n in names)
        system = (
            "You match b-roll to narration PHRASES for a car short. For each "
            "phrase pick the single best-fitting asset filename, or the string "
            "NONE if nothing genuinely matches (do NOT force a bad match — a "
            "wrong visual is worse than a neutral one). Match meaning: screen/"
            "dash phrases -> console/press interior shots, off-road claims -> "
            "mud/trail/river, facelift/new-model/caught-testing phrases -> the "
            "OFFICIAL press/roxx images (best match for the newer model), "
            "price/value phrases -> clean beauty shots of the subject car "
            "(front/detail), NEVER action/event/crowd shots on price talk. "
            "Output ONLY a JSON array: "
            '[{"id": "<sec>.<ph>", "asset": "<filename or NONE>"}]'
        )
        rows = _rows(llm.complete_json(system, f"PHRASES:\n{listing}\n\nASSETS:\n{assets}"))
        by_name = {Path(a).name: a for a in pool}
        out: dict[tuple[int, int], str] = {}
        for row in rows:
            rid = str(row.get("id", ""))
            if "." not in rid:
                continue
            asset = row.get("asset", "NONE")
            if asset in by_name:
                si, pi = rid.split(".", 1)
                try:
                    out[(int(si), int(pi))] = by_name[asset]
                except ValueError:
                    continue
        return out
    except Exception:  # noqa: BLE001
        return {}


def _llm_shot_match(segments, pool: list[str], provider: str | None) -> dict[int, list[str]]:
    """One LLM call: rank pool assets per script beat by semantic fit (asset
    filenames are descriptive). Returns {section_index: [asset paths ranked]}.
    Empty dict on any failure — callers fall back to keyword hints."""
    import os as _os
    if not pool or not (provider or _os.environ.get("GROQ_API_KEY")):
        return {}
    try:
        from carshorts.writing.draft import _rows  # tolerant JSON row coercion
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
            shots_file: str | None = None, kwcaps: bool = True,
            polish_audio: bool = True, plan_only: bool = False,
            humor: bool | None = None) -> str:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Humor layer: flash an AI comedy cutaway on the punchline. Defaults ON when
    # the video-gen env is present. NEVER touches the car — see the peak-beat
    # insertion below (mid-video only; the opener/closer stay the real car).
    if humor is None:
        try:
            from carshorts.adapters import videogen
            humor = videogen.available() and not plan_only
        except Exception:  # noqa: BLE001
            humor = False

    # --- Get a script: either load a saved one (free) or draft one (uses a model).
    if script_file:
        script = Script.model_validate_json(paths.resolve(script_file).read_text())
        sheet = SpecSheet.model_validate_json(paths.resolve(spec_path).read_text()) if spec_path else None
        if sheet is not None:
            _apply_extras(sheet)   # merge sourced price/variant so the guard knows them
        print(f"loaded script from {script_file} ({len(script.segments)} sections)")
    else:
        if not spec_path:
            raise SystemExit("Provide --spec (to write a script) or --script-file (to render one).")

        sheet = SpecSheet.model_validate_json(Path(spec_path).read_text())
        guidance = _apply_extras(sheet)   # merges sourced price + value-pick guidance
        from carshorts.core.learnings import load_learnings_guidance
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
        feature_problems = unsourced_features_check(script, sheet)
        if number_problems or feature_problems:
            print("\n🔴 FACT-GUARD — claims NOT found in the spec sheet (do NOT publish):")
            for problem in number_problems + feature_problems:
                print(f"     - {problem}")
            print()

        if not skip_factcheck:
            try:
                llm = make_llm(provider)
                print("2/4  fact-checking (separate skeptic pass)...")
                report = fact_check(script, sheet, llm)
                print("\n" + render_gate1_report(
                    script, sheet, report,
                    structural + number_problems + feature_problems) + "\n")
            except Exception as exc:
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
        car_root = paths.car_dir(_slug(script.subject))
        img_dir = str(car_root / "images")
        # OFFICIAL PRESS outranks everything among stills (highest quality,
        # correct generation, no plates) — then the vetted image folder.
        # oldgen_-prefixed files sort last within their tier.
        def _still_rank(path: Path) -> tuple:
            return (path.name.startswith("oldgen_"), path.name)
        press = [str(x) for x in sorted((car_root / "press").glob("*.[jp][pn]g"),
                                        key=_still_rank)]
        vetted = [str(x) for x in sorted(Path(img_dir).glob("*.[jp][pn]g"),
                                         key=_still_rank)]
        images = press + [v for v in vetted if v not in press]
        if images:
            print(f"3/5  using {len(press)} press + {len(vetted)} vetted local "
                  f"images from {car_root}")
        else:
            print(f"3/5  fetching CC car photos -> {img_dir} ...")
            try:
                # Wikimedia is the reliable free backbone (angle-broad search);
                # Openverse is a best-effort bonus for non-Wikimedia sources when
                # its anonymous rate-limit allows — never required for a render.
                images = WikimediaImageSource().fetch(script.subject, img_dir, limit=14)
                try:
                    from carshorts.adapters.openverse import OpenverseImageSource
                    images += [e for e in
                               OpenverseImageSource().fetch(script.subject, img_dir, limit=6)
                               if e not in images]
                except Exception:  # noqa: BLE001 — Openverse is a bonus, not a dependency
                    pass
                print(f"     {len(images)} images fetched — vetting before use…")
                # Wikimedia checks the LICENCE, nothing else. Real fetches have
                # returned readable number plates and third-party watermarks, so
                # nothing auto-fetched may enter the pool unlooked-at. Failures
                # are quarantined (recoverable), never deleted.
                from carshorts.quality.assetvet import vet_folder
                report = vet_folder(img_dir, script.subject, apply=True)
                if report.get("checked"):
                    print(f"     asset vet: {report['clean']}/{report['checked']} clean, "
                          f"{report['quarantined']} quarantined")
                    for r in report["results"]:
                        if not r["ok"]:
                            print(f"       ✂ {r['file'][:44]}: {','.join(r['blocking'])}")
                # re-derive the pool from what actually survived the vet
                images = [str(x) for x in sorted(Path(img_dir).glob("*.[jp][pn]g"),
                                                 key=_still_rank)]
                print(f"     {len(images)} usable image(s) after vetting")
            except Exception as exc:  # noqa: BLE001 — no photos just means plain cards
                print(f"     footage fetch failed ({exc}); using plain caption cards.")

    # --- Stock b-roll: prefer the VETTED local folder (curated by hand); only
    # fetch fresh clips when the folder is empty and a Pexels key exists.
    # Two tiers: assets/cars/<slug>/stock/ (subject-appropriate — e.g. offroad
    # clips live with Thar, not Creta) and assets/stock/ (brand-neutral generic
    # motion — dashboards, road POV — safe for any car). Subject-scoped comes
    # first so the pool leans into car-appropriate motion.
    stock_videos: list[str] = []
    use_stock = stock if stock is not None else True
    if use_stock:
        car_stock_dir = paths.car_dir(_slug(script.subject)) / "stock"
        car_stock = sorted(str(p) for p in car_stock_dir.glob("*.mp4"))
        generic_stock = sorted(str(p) for p in paths.STOCK.glob("*.mp4"))
        stock_videos = car_stock + generic_stock
        if stock_videos:
            print(f"     using {len(car_stock)} car-scoped + {len(generic_stock)} "
                  f"generic vetted stock clips")
        elif os.environ.get("PEXELS_API_KEY"):
            print("     fetching stock car b-roll (Pexels) for motion...")
            try:
                stock_videos = PexelsVideoSource().fetch(str(paths.STOCK), limit=4)
                print(f"     {len(stock_videos)} stock clips (VET THESE — check each)")
            except Exception as exc:  # noqa: BLE001 — fall back to stills
                print(f"     stock fetch failed ({exc}); stills only.")

    # --- Render (always local, always free). Voice each section separately so
    # visuals stay in sync. Interleave: exact-car stills for identity, stock
    # video for motion.
    # persona picks voice+energy for English; language picks the voice otherwise.
    voice = voice or (None if persona else VOICE_BY_LANG.get(language, "en-US-GuyNeural"))
    tts = make_tts(engine=voice_engine, persona=persona, voice=voice, language=language)
    print(f"4/5  voicing {len(script.segments)} sections "
          f"(engine={voice_engine}, persona={persona or 'default'})...")
    ai_dir = paths.car_dir(_slug(script.subject)) / "own"

    # --- Voice all sections first so we know each duration, then distribute a
    # visual POOL across fast sub-scenes (~2.8s cuts). Every asset is used at
    # most once across the whole video (repeats read as cheap), interleaving
    # the user's real clips with stock motion and stills for variety.
    # TTS cache: keyed by engine+voice+SPOKEN-text, so re-renders (music/visual
    # tweaks) never re-spend paid voice credits on unchanged lines — but a change
    # to the speech normalization (number enunciation, acronym spelling) DOES bust
    # the key, because we hash the exact string the model will speak, not the raw
    # script. (A stale cache once silently reused old audio after a number fix.)
    import hashlib

    from moviepy import AudioFileClip as _Audio

    from carshorts.adapters.tts import _speak_numbers as _spk
    from carshorts.adapters.tts import normalize_for_speech as _norm
    cache_dir = paths.TTS_CACHE / voice_engine
    cache_dir.mkdir(parents=True, exist_ok=True)

    audio_paths, durations, marks_paths = [], [], []
    for i, seg in enumerate(script.segments):
        # the VOICE is part of the cache identity for every engine — 11labs
        # stores it as .voice_id, edge as .voice. Missing the edge attr made
        # every edge render share one key: a voice change silently reused the
        # old voice's cached audio.
        effective_voice = (getattr(tts, "voice_id", None)
                           or getattr(tts, "voice", None) or voice)
        effective_voice = (f"{effective_voice}"
                           f"|{getattr(tts, 'rate', '')}|{getattr(tts, 'pitch', '')}")
        speech_sig = _spk(_norm(seg.text))   # what the model ACTUALLY speaks
        key = hashlib.md5(f"{voice_engine}|{effective_voice}|{persona}|{speech_sig}".encode()).hexdigest()[:16]
        cached = cache_dir / f"{key}.mp3"
        marks_file = cache_dir / f"{key}.marks.json"
        # re-synthesize when word marks are missing (old cache entries) — free
        # for edge, and marks are what phrase-synced cutting runs on
        needs = not cached.exists()
        if voice_engine in ("edge", "chatterbox") and not marks_file.exists():
            needs = True   # free engines: regenerate for word marks; NEVER auto-respend paid ones
        if needs:
            try:
                tts.synthesize(seg.text, str(cached), marks_path=str(marks_file))
            except TypeError:   # provider without word-boundary support
                tts.synthesize(seg.text, str(cached))
        trimmed = cache_dir / f"{key}.trim.mp3"
        if not trimmed.exists():
            import subprocess as _sp
            _sp.run(["ffmpeg", "-y", "-i", str(cached),
                     "-af", "areverse,silenceremove=start_periods=1:start_silence=0.18:start_threshold=-42dB,areverse",
                     "-codec:a", "libmp3lame", "-q:a", "2", str(trimmed)],
                    capture_output=True)
            # validate: the trim must yield a real, probe-able audio stream
            probe = _sp.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                             "-of", "default=noprint_wrappers=1:nokey=1", str(trimmed)],
                            capture_output=True, text=True)
            try:
                ok = float(probe.stdout.strip()) > 0.3
            except ValueError:
                ok = False
            if not ok:
                trimmed.unlink(missing_ok=True)
                trimmed = cached   # trim failed/empty -> use original
        audio_paths.append(str(trimmed))
        marks_paths.append(str(marks_file) if marks_file.exists() else None)
        durations.append(_Audio(str(audio_paths[-1])).duration)

    user_clips = sorted(str(p) for p in ai_dir.glob("*.mp4"))
    # Living Stills: a "living_<stem>.mp4" in own/ is the i2v-animated version of
    # a still (see rendering/liven.py) — prefer the motion clip and drop the
    # matching static still, so animated REAL footage replaces the slideshow.
    livened_stems = {Path(c).stem[len("living_"):] for c in user_clips
                     if Path(c).stem.startswith("living_")}
    if livened_stems:
        images = [im for im in images if Path(im).stem not in livened_stems]

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

    # --- Phrase-level sync (the retention core): visuals change exactly when
    # the narration changes subject. Needs word marks (edge TTS); cached
    # ElevenLabs audio without marks falls back to beat-level matching.
    phrase_map = {i: _phrases_with_times(seg.text, marks_paths[i])
                  for i, seg in enumerate(script.segments)}
    phrase_sync = any(len(v) > 1 for v in phrase_map.values())
    entries = [(i, j, txt) for i, phs in phrase_map.items()
               for j, (_, txt) in enumerate(phs)]
    phrase_ranked = _llm_phrase_match(entries, pool, provider) if phrase_sync else {}
    if phrase_ranked:
        print(f"     phrase-sync: {len(phrase_ranked)}/{len(entries)} phrases matched to visuals")
        gaps = [txt for (i, j, txt) in entries if (i, j) not in phrase_ranked]
        if gaps:
            print("     B-ROLL GAPS (no matching asset — worth shooting/fetching):")
            for g in gaps[:8]:
                print(f"       - {g[:70]}")

    llm_ranked = _llm_shot_match(script.segments, pool, provider) if not phrase_ranked else {}
    if llm_ranked:
        print(f"     shot-matcher aligned {len(llm_ranked)} beats to visuals")
    subject_families = _subject_families(script.subject)

    def _is_subject_asset(asset: str) -> bool:
        return any(f in Path(asset).name.lower() for f in subject_families)

    # --- DETERMINISTIC OPENER. On a Short frame 1 IS the thumbnail, yet it was
    # whatever the LLM phrase-matcher happened to return that run (two renders
    # of the same script opened on different photos). Rank the subject stills
    # by measured stop-power against the rival baseline instead.
    opening_pick = None
    try:
        from carshorts.quality.firstframe import load_baseline, rank_opening_stills
        _baseline = load_baseline()
        if _baseline:
            still_candidates = [
                a for a in pool
                if _is_subject_asset(a)
                and not a.lower().endswith((".mp4", ".mov", ".m4v", ".webm"))
                and not Path(a).name.lower().startswith("oldgen_")]
            ranked = rank_opening_stills(still_candidates, _baseline)  # scored once
            # VET-ON-USE: the scorer is blind to plates/watermarks/promo text, so
            # a defective image can win on exposure alone (a Thai-promo showroom
            # shot once did). Vet the top candidates from the top down, cache-first
            # and capped, and drop blocking-failed ones before one becomes the
            # thumbnail. Cached verdicts (incl. this pool's seed) cost nothing;
            # quota-dead just means "unvetted", never "blocked".
            blocked: set = set()
            try:
                from carshorts.quality.assetvet import vet_paths
                top = [p for _, p, _ in ranked[:12]]
                verdicts = vet_paths(top, script.subject, max_calls=3)
                blocked = {p for p, v in verdicts.items() if not v["ok"]}
                if blocked:
                    print(f"     vet-on-use: dropped {len(blocked)} opener "
                          f"candidate(s): "
                          + ", ".join(Path(p).name[:26] for p in blocked))
                    pool = [a for a in pool if a not in blocked]
            except Exception as exc:  # noqa: BLE001 — vetting is best-effort
                print(f"     vet-on-use skipped ({str(exc)[:70]})")

            for score, path, _ in ranked:
                if path not in blocked:
                    opening_pick = path
                    print(f"     opener (deterministic, score {score:.2f}): "
                          f"{Path(path).name}")
                    break
    except Exception as exc:  # noqa: BLE001 — never block a render on this
        print(f"     opener scoring skipped ({str(exc)[:80]})")

    if opening_pick is None:
        # No static subject still (e.g. every still was livened into a clip) —
        # open on a subject MOTION clip (a Living Still of the car) so the
        # opens-on-subject-car QA holds and frame 1 is the real car, not stock.
        subj = [a for a in pool if _is_subject_asset(a)
                and not Path(a).name.lower().startswith("oldgen_")]
        if subj:
            # Pick the BRIGHTEST subject clip, not just the first — a dark interior
            # opener fails the first-frame feed-norm QA (and makes a weak thumbnail);
            # the well-lit exterior/showroom clips win.
            opening_pick = max(subj, key=_clip_brightness)
            print(f"     opener (brightest subject clip): {Path(opening_pick).name}")

    sections = []
    manifest_sections: list[dict] = []
    prev_last_bucket = ""
    humor_concepts_used: set[str] = set()   # AI comedy concepts used so far
    _HUMOR_MAX = 3                          # a lively few, not a meme every beat
    for i, seg in enumerate(script.segments):
        chunks = max(1, round(durations[i] / target))
        visuals: list[str] = []
        section_buckets: set = set()
        if phrase_sync:
            # phrase-synced cuts are the render path — beat-level assignment
            # must not run, or it silently consumes pool assets that never
            # appear on screen (forcing repeats in the real cuts)
            chunks = 0
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
        timed_cuts: list = []
        if phrase_ranked or phrase_sync:
            cuts_src = phrase_map[i]
            prev_asset = sections[-1].timed_cuts[-1][1] if (sections and sections[-1].timed_cuts) else None
            for j, (t_off, _txt) in enumerate(cuts_src):
                # merge decision FIRST: a cut closer than 1.1s to the previous
                # one never happens, so it must not consume an asset either
                if timed_cuts and t_off - timed_cuts[-1][0] < 1.1:
                    continue
                pick = phrase_ranked.get((i, j))
                # the very first cut is the thumbnail — it is chosen by measured
                # stop-power, not by whatever the matcher returned this run
                if i == 0 and not timed_cuts and opening_pick:
                    pick = opening_pick
                if pick is not None and pick in used:
                    pick = None          # once-only: a used asset can't repeat
                if pick is None:
                    # neutral fill: first unused asset not clashing with the
                    # previous cut's look family. On the HOOK and the CTA the
                    # subject car itself must be on screen — edges of the video
                    # are where irrelevant b-roll hurts most.
                    # SUBJECT-FIRST everywhere (owner rule): real content of
                    # THIS car claims every cut it can; generic b-roll only
                    # fills what's left. Edge beats additionally hard-require
                    # the subject (see below).
                    edge_beat = (i == 0 or i == len(script.segments) - 1)
                    ordering = sorted(pool, key=lambda a: not _is_subject_asset(a))
                    for cand in ordering:
                        if cand in used:
                            continue
                        if prev_asset and _bucket(cand) == _bucket(prev_asset):
                            continue
                        if edge_beat and not _is_subject_asset(cand) and any(
                                _is_subject_asset(x) and x not in used for x in pool):
                            continue
                        pick = cand
                        break
                if pick is None:         # relax the family constraint first
                    for cand in ordering:
                        if cand not in used:
                            pick = cand
                            break
                if pick is None:         # pool truly exhausted: spread reuse
                    pick = pool[reuse_cursor[0] % len(pool)]
                    reuse_cursor[0] += 1
                used.add(pick)
                timed_cuts.append((t_off, pick))
                prev_asset = pick
        sec_phrases = phrase_map[i]
        word_pops = _word_pops(seg, marks_paths[i], durations[i], sheet) if kwcaps else []
        # the very last thing on screen must be the subject car
        if i == len(script.segments) - 1 and timed_cuts:
            if not _is_subject_asset(timed_cuts[-1][1]):
                swapped = False
                for j in range(len(timed_cuts) - 2, -1, -1):   # within this section
                    if _is_subject_asset(timed_cuts[j][1]):
                        timed_cuts[-1], timed_cuts[j] = (
                            (timed_cuts[-1][0], timed_cuts[j][1]),
                            (timed_cuts[j][0], timed_cuts[-1][1]))
                        swapped = True
                        break
                if not swapped:
                    # no car cut in the CTA — swap with one from an EARLIER
                    # section (never the opener); asset counts stay identical
                    for prev in reversed(sections):
                        for k in range(len(prev.timed_cuts) - 1, -1, -1):
                            if prev is sections[0] and k == 0:
                                continue
                            if _is_subject_asset(prev.timed_cuts[k][1]):
                                a, b = prev.timed_cuts[k], timed_cuts[-1]
                                prev.timed_cuts[k] = (a[0], b[1])
                                timed_cuts[-1] = (b[0], a[1])
                                swapped = True
                                break
                        if swapped:
                            break
        # HUMOR LAYER — flash AI comedy cutaways under the punchlines. Each is a
        # non-car editorial joke (provenance-tagged); the wall holds because we
        # only touch NON-EDGE beats (never the video's first/last cut), so the
        # opener/closer stay the real subject car (QA still enforces that). We
        # REPLACE a beat's last cut (keeps timing -> no sub-1s cut, QA-safe), cap
        # the total and never repeat a concept, so it stays lively, not spammy.
        if (humor and timed_cuts and 0 < i < len(script.segments) - 1
                and len(humor_concepts_used) < _HUMOR_MAX):
            try:
                from carshorts.adapters.humor import joke_for
                result = joke_for(seg.text, avoid=humor_concepts_used)
                if result:
                    clip, concept = result
                    timed_cuts[-1] = (timed_cuts[-1][0], clip)
                    humor_concepts_used.add(concept)
                    print(f"     humor: AI comedy flash [{seg.role}] {concept} -> {Path(clip).name}")
            except Exception as exc:  # noqa: BLE001 — humor is best-effort
                print(f"     humor skipped ({str(exc)[:70]})")
        sections.append(Section(
            audio_path=audio_paths[i], caption=seg.text, background_pool=visuals,
            timed_cuts=timed_cuts, word_pops=word_pops))
        manifest_sections.append({
            "index": i, "role": seg.role, "duration": round(durations[i], 3),
            "text": seg.text,
            "phrases": [{"t": round(t, 3), "text": txt} for t, txt in sec_phrases],
            "cuts": [{"t": round(t, 3), "asset": Path(a).name} for t, a in timed_cuts],
            "pops": [{"start": round(p[0], 3), "dur": round(p[1], 3),
                      "text": p[2], "kind": p[3]} for p in word_pops],
        })

    manifest_path = out.with_suffix(".manifest.json")
    # subject families: QA's opens/closes-on-car checks must know THIS car's
    # names (plus curated aliases like Thar->roxx), not a hardcoded list
    families = _subject_families(script.subject)
    manifest_path.write_text(json.dumps({
        "out": str(out), "sections": manifest_sections,
        "pool_size": len(pool),
        "subject": script.subject,
        "subject_families": sorted(families),
    }, indent=2, ensure_ascii=False))
    if plan_only:
        print(f"     plan-only: manifest -> {manifest_path}")
        return str(manifest_path)

    lock = out.with_suffix(".lock")
    lock.write_text(json.dumps({"started": __import__("datetime").datetime.now()
                                .isoformat(timespec="seconds")}))

    # Background music: auto-generate a royalty-free beat unless disabled/overridden.
    # The composer agent's per-car sound profile (data/sound_profiles/<slug>.json)
    # outranks the persona default: the CAR's personality picks the sound.
    music_path: str | None = None
    sound_profile: dict = {}
    profile_file = paths.SOUND_PROFILES / f"{_slug(script.subject)}.json"
    if profile_file.exists():
        try:
            sound_profile = json.loads(profile_file.read_text())
        except Exception:  # noqa: BLE001
            pass
    if music == "auto":
        library = sorted(paths.MUSIC.glob("*.mp3")) + sorted(paths.MUSIC.glob("*.wav"))
        if library:
            # mood-match: composer mood first, then persona (data/music_tags.json)
            choice = library[0]
            tags_file = paths.MUSIC_TAGS
            if tags_file.exists():
                try:
                    tags = json.loads(tags_file.read_text())
                    wanted = sound_profile.get("mood") or (persona or "default")
                    fitting = [t for t in library
                               if wanted in tags.get(t.name, {}).get("fits", [])]
                    if not fitting:
                        fitting = [t for t in library
                                   if (persona or "default") in tags.get(t.name, {}).get("fits", [])]
                    if fitting:
                        choice = fitting[0]
                except Exception:  # noqa: BLE001
                    pass
            music_path = str(choice)
            print(f"     music: {Path(music_path).name} (mood-matched)")
        else:
            music_path = str(out.with_suffix(".beat.wav"))
            bpm = int(sound_profile.get("bpm") or 84)
            print(f"     generating royalty-free beat ({bpm} bpm"
                  + (f", {sound_profile['mood']}" if sound_profile.get("mood") else "")
                  + ")...")
            generate_beat(music_path, duration=90, bpm=bpm)
    elif music and music != "none":
        music_path = music

    print(f"5/5  rendering synced video -> {out_path}  "
          f"(kwcaps={'on' if kwcaps else 'off'}, music={'yes' if music_path else 'no'}, "
          f"polish={'on' if polish_audio else 'off'})")
    renderer = MoviePyRenderer()
    if polish_audio:
        voice_only = str(out.with_suffix(".voice.mp4"))
        renderer.render_sections(sections, voice_only, music_path=None,
                                 draw_captions=captions)
        boundaries = getattr(renderer, "last_boundaries", [])
        value_start = None
        cursor = 0.0
        from moviepy import AudioFileClip as _A
        for i, seg in enumerate(script.segments):
            if seg.role == "value":
                value_start = cursor
                break
            cursor += _A(audio_paths[i]).duration
        from carshorts.rendering.audiopolish import polish as _polish
        try:
            _polish(voice_only, str(out), music_path=music_path,
                    whoosh_times=boundaries[:6], riser_time=value_start)
        except Exception as exc:  # noqa: BLE001 — fall back to unpolished
            print(f"     polish failed ({exc}); delivering unpolished mix.")
            renderer.render_sections(sections, str(out), music_path=music_path,
                                     draw_captions=captions)
    else:
        renderer.render_sections(sections, str(out), music_path=music_path,
                                 draw_captions=captions)

    # Render manifest: the machine-checkable plan of what SHOULD be on screen
    # when — the QA gate validates the rendered file against it.
    # --- Self-correcting QA loop: known failure classes map to fixes that are
    # applied automatically and re-verified; every failure is journaled and
    # becomes a learning the writer/pipeline sees next time.
    try:
        from carshorts.quality.qa import run_qa
        journal = paths.FAILURES
        journal.parent.mkdir(parents=True, exist_ok=True)
        qa_ok, fails = run_qa(str(out), str(manifest_path), details=True)
        attempts = 0
        auto_fixed: list[str] = []
        while not qa_ok and attempts < 2:
            audio_only = all(("loudness" in f["check"] or "peak" in f["check"]) for f in fails)
            if not (audio_only and polish_audio and 'voice_only' in dir()):
                break
            attempts += 1
            print(f"     🔧 auto-fix attempt {attempts}: re-polishing audio with more headroom")
            from carshorts.rendering.audiopolish import polish as _polish2
            _polish2(voice_only, str(out), music_path=music_path,
                     whoosh_times=boundaries[:6], riser_time=value_start,
                     music_gain=0.45, sfx_gain=0.4)
            auto_fixed = [f["check"] for f in fails]
            qa_ok, fails = run_qa(str(out), str(manifest_path), details=True)
        import datetime as _dtm
        for f in fails:
            with journal.open("a") as fh:
                fh.write(json.dumps({"at": _dtm.datetime.now().isoformat(timespec="seconds"),
                                     "video": str(out), "check": f["check"],
                                     "detail": f["detail"], "resolved": False}) + "\n")
        if auto_fixed and qa_ok:
            with journal.open("a") as fh:
                for name in auto_fixed:
                    fh.write(json.dumps({"at": _dtm.datetime.now().isoformat(timespec="seconds"),
                                         "video": str(out), "check": name,
                                         "detail": "auto-repolish", "resolved": True}) + "\n")
            try:   # a resolved failure becomes a standing lesson (deduped)
                ldata = json.loads(paths.LEARNINGS.read_text())
                lesson = f"QA auto-fix works for {'/'.join(sorted(set(auto_fixed)))} via re-polish with extra headroom; keep gains conservative on punchy voices."
                if lesson not in ldata.get("data_learnings", []):
                    ldata.setdefault("data_learnings", []).append(lesson)
                    ldata["data_learnings"] = ldata["data_learnings"][-10:]
                    paths.LEARNINGS.write_text(json.dumps(ldata, indent=2, ensure_ascii=False))
            except Exception:  # noqa: BLE001
                pass
        if not qa_ok:
            print("     🔴 QA FAILED — inspect before publishing.")
        elif attempts:
            print("     ✅ QA green after auto-fix.")
    except Exception as exc:  # noqa: BLE001
        print(f"     QA skipped ({exc})")

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
        rp = paths.RECIPES / (out.stem + ".json")
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps(recipe, indent=2))
        print(f"     recipe card -> {rp}")
    except Exception as exc:  # noqa: BLE001 — logging must never break a render
        print(f"     recipe card skipped ({exc})")

    lock.unlink(missing_ok=True)

    credits = attribution_lines(f"assets/cars/{_slug(script.subject)}/images") if images else []
    if credits:
        print("\nImage credits (put these in the YouTube description):")
        for line in credits:
            print(f"  {line}")
    return str(out)


def main() -> None:
    # Load .env BEFORE building the parser so env-backed defaults (e.g.
    # --voice-engine = CARSHORTS_VOICE_ENGINE) actually see the .env value.
    # Without this the finalized clone voice is silently ignored (defaults to edge).
    from carshorts.core.config import load_env
    load_env()
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
    parser.add_argument("--voice-engine", default=os.environ.get("CARSHORTS_VOICE_ENGINE", "edge"),
                        choices=["edge", "chatterbox", "elevenlabs"],
                        help="edge (free) or elevenlabs (expressive, needs ELEVENLABS_API_KEY).")
    parser.add_argument("--persona", default="", choices=["", "bhai", "deadpan", "hype"],
                        help="Voice energy profile (edge rate/pitch).")
    parser.add_argument("--shots", help="Shot-plan JSON (routes beats to AI clips vs car footage).")
    parser.add_argument("--no-kwcaps", action="store_true", help="Disable keyword pop captions.")
    parser.add_argument("--no-polish", action="store_true", help="Skip audio duck/SFX/loudnorm pass.")
    parser.add_argument("--plan-only", action="store_true",
                        help="Stop after writing the manifest (no render) — for tests/planning.")
    parser.add_argument("--humor", dest="humor", action="store_true", default=None,
                        help="Flash an AI comedy cutaway on the peak beat (default: on if .venv-video exists).")
    parser.add_argument("--no-humor", dest="humor", action="store_false",
                        help="Disable the AI humor layer.")
    args = parser.parse_args()

    stock = True if args.stock else (False if args.no_stock else None)
    path = produce(args.spec, args.out, language=args.language, voice=args.voice,
                   script_file=args.script_file, skip_factcheck=args.skip_factcheck,
                   provider=args.provider, footage=not args.no_footage, music=args.music,
                   captions=args.captions, stock=stock,
                   voice_engine=args.voice_engine, persona=args.persona,
                   shots_file=args.shots, kwcaps=not args.no_kwcaps,
                   polish_audio=not args.no_polish, plan_only=args.plan_only,
                   humor=args.humor)
    print(f"\nDone -> {path}")


if __name__ == "__main__":
    main()
