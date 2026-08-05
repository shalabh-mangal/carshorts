"""Pre-Gate critic — the 'think like the owner's partner' layer.

Deterministic QA (quality/qa.py) catches MECHANICAL defects (loops, dropped
overlays, stock-over-own, edge voice). It cannot judge TASTE: is the hook
gripping, do the clips match the narration, is it tight, does it earn a like?

This runs an LLM over the finished render (manifest + script facts + TASTE.md +
proven learnings) and writes a structured critique onto the queue card, so the
owner (and the pipeline) sees a demanding second opinion BEFORE Gate 2 — and can
send it straight to rework if the verdict is 'block'.

    carshorts critic tata-sierra          # review the latest render for a slug
"""
from __future__ import annotations

import datetime
import json

from carshorts.adapters.llm import make_llm
from carshorts.core import paths
from carshorts.core.learnings import load_learnings_guidance


def _taste() -> str:
    for p in (paths.ROOT / "charters" / "TASTE.md", paths.ROOT / "TASTE.md"):
        if p.exists():
            return p.read_text(encoding="utf-8")[:4000]
    return ""


def _latest_manifest(slug: str) -> dict:
    for name in (f"{slug}_final", f"{slug}_draft"):
        mp = paths.OUT / f"{name}.manifest.json"
        if mp.exists():
            try:
                return json.loads(mp.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 — a bad manifest never blocks the critic
                pass
    return {}


# Feature cues we expect an on-screen overlay for when NAMED in the narration.
# Used to compute overlay coverage DETERMINISTICALLY — the LLM miscounts when it
# has to cross-reference the narration against the overlay list itself (it once
# called three covered features "naked mentions"), so we hand it the answer.
_FEATURE_CUES = (
    "sunroof", "ventilated seats", "cooled seats", "wireless charging", "touchscreen",
    "adas", "driver assist", "airbags", "camera", "360", "speakers", "jbl", "dolby",
    "boot", "cruise control", "connected", "ncap", "sunroof", "led", "digital cluster",
)


def _uncovered_features(text: str, pop_texts: list[str]) -> list[str]:
    """Feature cues NAMED in the narration that have NO matching on-screen overlay.
    Deterministic ground truth for the critic's overlay-coverage check: a cue is
    COVERED if a distinctive word of it appears in any of the beat's pops."""
    t = (text or "").lower()
    pops = " ".join(pop_texts).lower()
    out: list[str] = []
    for cue in _FEATURE_CUES:
        if cue in t:
            key = cue.split()[-1]           # 'seats', 'charging', 'touchscreen', ...
            if key not in pops and cue not in pops and cue not in out:
                out.append(cue)
    return out


def _summary(card: dict, manifest: dict) -> dict:
    """Compact, LLM-readable picture of the actual render."""
    secs = manifest.get("sections", [])
    beats = []
    for s in secs:
        overlays = [p.get("text") for p in s.get("pops", [])]
        beats.append({
            "role": s.get("role"),
            "narration": s.get("text"),
            "clips": [c.get("asset") for c in s.get("cuts", [])],
            "overlays_on_screen": overlays,                 # GROUND TRUTH — these DO render
            "uncovered_features": _uncovered_features(s.get("text", ""), overlays),
            "seconds": round(s.get("duration", 0), 1),
        })
    return {
        "car": card.get("car"),
        "voice": card.get("voice"),
        "voice_engine": manifest.get("render", {}).get("voice_engine"),
        "total_seconds": round(sum(s.get("duration", 0) for s in secs), 1),
        "word_count": sum(len((s.get("text") or "").split()) for s in secs),
        "qa_warnings": manifest.get("quality_warnings", []),
        "beats": beats,
    }


def run(slug: str, provider: str | None = None) -> dict:
    card_path = paths.QUEUE / f"{slug}.json"
    if not card_path.exists():
        print(f"critic: no card for {slug!r}")
        return {}
    card = json.loads(card_path.read_text(encoding="utf-8"))
    manifest = _latest_manifest(slug)
    if not manifest.get("sections"):
        print(f"critic: no render manifest for {slug!r} yet")
        return {}

    system = (
        _taste() + "\n\n"
        "You are the PRE-GATE CRITIC for a free YouTube Shorts car channel (India). "
        "Review the finished render below like a demanding creative director AND the "
        "owner's partner — the last honest look before the owner's taste gate. Judge, "
        "and score HARSHLY on the retention shape (this is what the Shorts feed rewards):\n"
        "1. HOOK stopping-power in the first 2 seconds — the #1 lever. A hero number / "
        "curiosity gap wins. FRAME 1 must be MOTION or a bold hero shot: if the first "
        "beat's opening clip looks static/interior/badge, flag it (a boring frame 1 costs "
        "the swipe before a word is heard).\n"
        "2. Does each beat's CLIPS actually MATCH its narration? Filenames only HINT at "
        "content — flag a mismatch only when the filename clearly contradicts the line "
        "(e.g. an 'exterior'/'sand'/'grass' clip on an interior-feature line). Do NOT "
        "speculate about a clip you cannot infer from its name.\n"
        "3. THE SPEC-BEAT CLIFF — our #1 drop-off (retention data across 7 videos: 55-81% "
        "of ALL departures happen DURING the spec beat, right after the hook). Check the "
        "HOOK->SPEC seam: does the spec beat BRIDGE and ESCALATE the hook's tension ('here's "
        "the crazy part…') and land as a PAYOFF, or does it deflate into a flat number recital / "
        "fact-dump? Flag a spec beat that doesn't sustain the hook, or that runs longer than ~2 "
        "tight lines (long spec beats bleed hardest). Also flag any later hard topic-switch into "
        "value/peak with no bridge.\n"
        "4. TIGHTNESS — proven winner is ~90 words / ~30s. Flag a long OUTRO especially: the "
        "CTA beat should be <=4s / <=12 words; a polite 5-6s tail is dead air that drags "
        "average-view-% and delays the loop.\n"
        "5. OVERLAY COVERAGE: each beat gives `overlays_on_screen` (GROUND TRUTH — exactly "
        "what renders) and `uncovered_features` (features named in narration with NO overlay, "
        "computed for you). Flag ONLY the items in `uncovered_features`; if it is empty, "
        "coverage is COMPLETE — never claim an overlay is missing when it is in "
        "`overlays_on_screen`.\n"
        "6. Engagement levers (like-at-peak, a binary rivalry poll), loop-friendliness, and "
        "any TASTE or accuracy risk.\n"
        "Be specific and honest, but also name what genuinely works. Ground every point in the "
        "proven learnings below.\n\nPROVEN LEARNINGS:\n" + load_learnings_guidance(16)
    )
    user = (
        "RENDER TO REVIEW:\n" + json.dumps(_summary(card, manifest), ensure_ascii=False, indent=1)
        + "\n\nReturn ONLY JSON:\n"
        '{"verdict":"ship|revise|block","score":<1-10>,"summary":"one honest sentence",'
        '"strengths":["..."],'
        '"issues":[{"beat":"<role>","problem":"...","fix":"...","severity":"low|med|high"}]}'
    )

    try:
        crit = make_llm(provider).complete_json(system, user)
        if isinstance(crit, list):
            crit = crit[0] if crit else {}
    except Exception as exc:  # noqa: BLE001 — critic is advisory, never blocks a render
        crit = {"verdict": "revise", "score": None,
                "summary": f"critic unavailable ({str(exc)[:80]})",
                "strengths": [], "issues": []}
    crit["reviewed_at"] = datetime.datetime.now().isoformat(timespec="seconds")

    with open(card_path, encoding="utf-8") as fh:
        c = json.load(fh)
    c["critique"] = crit
    tmp = card_path.with_name(card_path.name + ".tmp")
    tmp.write_text(json.dumps(c, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(card_path)

    print(f"critic [{slug}] verdict={crit.get('verdict')} score={crit.get('score')} "
          f"— {str(crit.get('summary',''))[:120]}")
    for iss in (crit.get("issues") or [])[:6]:
        print(f"  [{iss.get('severity','?')}] {iss.get('beat','')}: "
              f"{iss.get('problem','')} → {iss.get('fix','')}")
    return crit


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--provider")
    args = ap.parse_args()
    run(args.slug, args.provider)


if __name__ == "__main__":
    main()
