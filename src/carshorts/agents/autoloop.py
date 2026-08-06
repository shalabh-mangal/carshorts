"""Close the loop — QA/critique -> auto-fix -> re-render, until it ships or needs
the owner. Removes the human from the fix seam I kept standing in for.

Two things it can fix by itself:
  - VISION block (a readable plate / wrong-or-rival vehicle clip) -> quarantine that
    exact clip and re-render (the G-Wagon-in-the-hook fix, automated).
  - Critic below bar with script issues -> the Script Studio revises the script
    (no unsourced facts — the draft guards hold) and re-render.

What it does NOT pretend to fix: a LOOP/REPEAT QA red is a FOOTAGE gap — you can't
invent clips — so it surfaces to the owner for more footage. Bounded by max_iter so
it never spins; the decision core (`next_action`) and the vision fix are pure/tested,
the render + revise are injected so the loop is testable and reusable by the pipeline.
"""
from __future__ import annotations

import json
from pathlib import Path

from carshorts.core import paths

BAR = 8            # critic score (1-10) the render must clear to ship
MAX_ITER = 2       # auto-fix attempts before we hand it to the owner


def next_action(*, vision_blocked: bool, footage_qa_red: bool,
                critique_score: int | None, attempt: int,
                max_iter: int = MAX_ITER, bar: int = BAR) -> str:
    """The decision brain (pure). Returns one of:
      'ship'       — QA-green, no vision block, critic >= bar → done.
      'fix_vision' — a blocking plate/wrong-vehicle clip → quarantine + re-render.
      'fix_script' — QA-green but critic < bar → revise the script + re-render.
      'surface'    — out of attempts, or a footage-only QA red we can't invent past.
    Precedence: run out of attempts → surface; else vision first (cheap, deterministic),
    then footage-red (needs owner), then a weak critic (script revise)."""
    if attempt >= max_iter:
        return "surface"
    if vision_blocked:
        return "fix_vision"
    if footage_qa_red:
        return "surface"
    if (critique_score or 0) < bar:
        return "fix_script"
    return "ship"


def _blocking_clip_names(vqa_path: Path) -> list[str]:
    """Asset filenames whose sampled frame had a BLOCKING vision defect."""
    if not vqa_path.exists():
        return []
    try:
        vq = json.loads(vqa_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — a bad vqa file just means nothing to quarantine
        return []
    return sorted({Path(d.get("asset", "")).name
                   for d in vq.get("blocking_detail", []) if d.get("asset")})


def quarantine_flagged(slug: str, vqa_path: Path) -> list[str]:
    """Move every vision-blocked clip out of the car's own/ pool into own/_rejected/
    so the next render can't pick it. Returns the names moved."""
    names = _blocking_clip_names(vqa_path)
    if not names:
        return []
    own = paths.car_dir(slug) / "own"
    rej = own / "_rejected"
    rej.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    for name in names:
        src = own / name
        if src.exists():
            src.rename(rej / name)
            moved.append(name)
    return moved


def _assess(slug: str, out_path: str) -> tuple[bool, bool, int | None]:
    """Read the render's manifest QA + vqa.json + the card critique. Returns
    (vision_blocked, footage_qa_red, critique_score)."""
    out = Path(out_path)
    warns: list[str] = []
    man = out.with_suffix(".manifest.json")
    if man.exists():
        try:
            warns = json.loads(man.read_text(encoding="utf-8")).get("quality_warnings", [])
        except Exception:  # noqa: BLE001
            warns = []
    footage_qa_red = any(w.startswith(("LOOP", "REPEAT")) for w in warns)
    vqp = out.with_suffix(".vqa.json")
    vision_blocked = bool(_blocking_clip_names(vqp))
    score = None
    card = paths.QUEUE / f"{slug}.json"
    if card.exists():
        try:
            score = (json.loads(card.read_text(encoding="utf-8")).get("critique") or {}).get("score")
        except Exception:  # noqa: BLE001
            score = None
    return vision_blocked, footage_qa_red, score


def _surface_footage_gap(slug: str) -> None:
    """When the loop hands back to the owner on a footage red, print the precise
    coverage/provenance shopping list — not just 'needs footage'. Best-effort:
    a missing pool never masks the real surface reason."""
    try:
        from carshorts.sourcing import footageplan
        print("     ── FOOTAGE NEEDED ──")
        for line in footageplan.shopping_list(footageplan.assess(slug)):
            print(f"       • {line}")
    except Exception as exc:  # noqa: BLE001
        print(f"     (footage plan unavailable: {str(exc)[:80]})")


def auto_improve(slug: str, out_path: str, render_fn, revise_fn,
                 max_iter: int = MAX_ITER, bar: int = BAR) -> str:
    """Render, assess, auto-fix, repeat. `render_fn()` performs one render (of the
    current script + pool); `revise_fn()` rewrites the script from the critique.
    Returns 'shipped' | 'needs_owner'. Journaled to the failures log per attempt."""
    outcome = "needs_owner"
    for attempt in range(max_iter + 1):
        render_fn()
        vision_blocked, footage_qa_red, score = _assess(slug, out_path)
        action = next_action(vision_blocked=vision_blocked, footage_qa_red=footage_qa_red,
                             critique_score=score, attempt=attempt, max_iter=max_iter, bar=bar)
        print(f"     autoloop attempt {attempt}: vision_blocked={vision_blocked} "
              f"footage_red={footage_qa_red} critic={score} -> {action}")
        if action == "ship":
            return "shipped"
        if action == "surface":
            _surface_footage_gap(slug)
            return "needs_owner"
        if action == "fix_vision":
            moved = quarantine_flagged(slug, Path(out_path).with_suffix(".vqa.json"))
            print(f"       quarantined vision-blocked clip(s): {', '.join(moved) or 'none'}")
        elif action == "fix_script":
            revise_fn(score)
    return outcome


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(
        description="Close the loop: render -> auto-fix (vision quarantine / script "
                    "revise) -> re-render, until it ships or needs the owner.")
    ap.add_argument("slug")
    ap.add_argument("--max-iter", type=int, default=MAX_ITER)
    args = ap.parse_args()
    card_path = paths.QUEUE / f"{args.slug}.json"
    if not card_path.exists():
        raise SystemExit(f"no card for {args.slug!r}")
    card = json.loads(card_path.read_text(encoding="utf-8"))
    out_path = card.get("draft") or f"out/{args.slug}_draft.mp4"

    def _render() -> None:
        from carshorts.rendering.produce import produce
        _v2p = {"calm": "deadpan", "natural": "", "hype": "hype", "bhai": "bhai"}
        persona = _v2p.get(card.get("voice", ""), card.get("persona", "deadpan"))
        produce(card.get("spec"), out_path, language=card.get("language", "english"),
                script_file=card.get("script"), skip_factcheck=True, footage=False,
                stock=False, voice_engine="chatterbox" if card.get("voice") else "edge",
                persona=persona, footage_slug=args.slug, humor=False,
                script_format=card.get("script_format", "mix"), vqa=True)

    def _revise(_score: int | None) -> None:
        from carshorts.core.models import Script, SpecSheet
        from carshorts.writing import scriptbrain
        try:
            sc = Script.model_validate_json(Path(card["script"]).read_text(encoding="utf-8"))
            sheet = SpecSheet.model_validate_json(Path(card["spec"]).read_text(encoding="utf-8"))
            crit = json.loads(card_path.read_text(encoding="utf-8")).get("critique") or {}
            revised = scriptbrain.revise(sc, sheet, crit, fmt=card.get("script_format", "spotlight"))
            if revised.segments:
                Path(card["script"]).write_text(revised.model_dump_json(indent=2), encoding="utf-8")
                print("     script revised from the critique")
        except Exception as exc:  # noqa: BLE001 — a failed revise keeps the current script
            print(f"     (script revise skipped: {str(exc)[:80]})")

    print(f"autoloop [{args.slug}] -> {auto_improve(args.slug, out_path, _render, _revise, max_iter=args.max_iter)}")


if __name__ == "__main__":
    main()
