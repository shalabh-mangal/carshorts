"""The system's own judgment layer — bounded decisions without a chat session.

  python -m carshorts.agents.brain triage        # classify unresolved QA/VQA failures
  python -m carshorts.agents.brain vet <file>    # second opinion on an asset
  python -m carshorts.agents.brain strategy      # weekly strategy note from all data

Constitution = claude.md + data/learnings.json (read before every decision).
Every decision is journaled to data/brain_log.jsonl — reviewable, learnable.
Bounded by design: the brain NEVER publishes, spends, or bypasses the human
gates; it decides, explains, and queues.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from carshorts.adapters.llm import make_llm
from carshorts.core import paths
from carshorts.writing.draft import _rows

LOG = paths.BRAIN_LOG


def _constitution() -> str:
    parts = []
    for f in (paths.ROOT / "CLAUDE.md", paths.LEARNINGS):
        if f.exists():
            parts.append(f.read_text()[:4000])
    return "\n\n".join(parts)


def _journal(kind: str, decision: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as fh:
        fh.write(json.dumps({"at": datetime.datetime.now().isoformat(timespec="seconds"),
                             "kind": kind, **decision}, ensure_ascii=False) + "\n")


def triage(provider: str | None = None) -> None:
    """Classify unresolved failures: auto-fixable pattern, needs-code, needs-human."""
    fj = paths.FAILURES
    if not fj.exists():
        print("no failures journaled")
        return
    unresolved = [json.loads(l) for l in fj.read_text().splitlines()
                  if l.strip() and not json.loads(l).get("resolved")]
    if not unresolved:
        print("no unresolved failures")
        return
    llm = make_llm(provider)
    rows = _rows(llm.complete_json(
        "You are the maintenance brain of a video pipeline. Constitution:\n"
        + _constitution()[:2500] +
        "\nFor each failure, classify: fix=known-pattern (describe the exact "
        "fix), code=needs a code change (describe where), human=needs the "
        "owner's judgment. Output ONLY JSON: "
        '[{"check": "...", "class": "fix|code|human", "action": "..."}]',
        json.dumps(unresolved[-15:], ensure_ascii=False)))
    for r in rows:
        print(f"  [{r.get('class','?'):5}] {r.get('check','?')}: {r.get('action','')[:90]}")
        _journal("triage", r)


def vet(asset: str, provider: str | None = None) -> None:
    """Second opinion on one asset via vision (advisory, journaled)."""
    import os
    import subprocess
    import tempfile

    import google.generativeai as genai
    from PIL import Image
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
    model = genai.GenerativeModel("gemini-2.5-flash")
    tdir = tempfile.mkdtemp()
    frames = []
    if asset.lower().endswith((".mp4", ".mov")):
        for t in (1, 3):
            fp = f"{tdir}/f{t}.jpg"
            subprocess.run(["ffmpeg", "-y", "-ss", str(t), "-i", asset, "-frames:v", "1",
                            "-vf", "scale=320:-1", fp], capture_output=True)
            if Path(fp).exists():
                frames.append(Image.open(fp))
    else:
        frames.append(Image.open(asset))
    raw = model.generate_content(
        ["Vet this asset for a car channel. Constitution rules: no readable "
         "plates, no third-party watermarks, correct vehicle for the subject, "
         "decent quality. Output ONLY JSON: "
         '{"usable": bool, "issues": [], "note": ""}', *frames],
        generation_config={"response_mime_type": "application/json"})
    verdict = json.loads(raw.text)
    print(json.dumps(verdict, indent=2))
    _journal("vet", {"asset": asset, **verdict})


def strategy(provider: str | None = None) -> None:
    """Weekly strategy note: reads ALL system data, writes one honest page."""
    blob = {}
    for name, p in (("learnings", paths.LEARNINGS),
                    ("calendar", paths.CALENDAR),
                    ("topic_ideas", paths.TOPIC_IDEAS)):
        if p.exists():
            blob[name] = json.loads(p.read_text())
    blob["recipes"] = [json.loads(p.read_text())
                       for p in sorted(paths.RECIPES.glob("*.json"))]
    llm = make_llm(provider)
    note = llm.complete(
        "You are the strategy brain of a car-Shorts channel. Constitution:\n"
        + _constitution()[:2500] +
        "\nGiven the system data, write a ONE-PAGE honest strategy note: what "
        "is working, what to change next week, which calendar slots to "
        "reorder and why, what the owner should film. Be concrete, humble "
        "about small samples, no fluff.",
        json.dumps(blob, ensure_ascii=False)[:20000])
    out = paths.REPORTS / f"strategy-{datetime.date.today()}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(note)
    _journal("strategy", {"report": str(out)})
    print(f"strategy note -> {out}")


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("task", choices=["triage", "vet", "strategy"])
    ap.add_argument("target", nargs="?")
    ap.add_argument("--provider")
    args = ap.parse_args()
    if args.task == "triage":
        triage(args.provider)
    elif args.task == "vet":
        if not args.target:
            raise SystemExit("brain vet <asset-path>")
        vet(args.target, args.provider)
    else:
        strategy(args.provider)


if __name__ == "__main__":
    main()
