"""Shot planner — decide each beat's visual and write AI prompts for the jokes.

  python -m carshorts.shotplan --script-file scripts/swift_deadpan.script.json --provider groq

For every script segment it decides:
  - type "car"     -> show the ACTUAL car (real still/stock footage). Used for
                      spec/price/looks beats. The car's identity must be real.
  - type "concept" -> a conceptual/comedic scene that visualizes the JOKE, not
                      the car. Gets a brand-neutral text-to-video prompt you can
                      paste into a free AI-video tool (Pika, or local LTX).

Writes shots/<name>.shots.json and prints the AI prompts to generate. Car beats
never go to AI (AI can't render a brand-accurate car); jokes never show a real
badge (brand-neutral). That split is deliberate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .adapters.llm import make_llm
from .models import Script
from .stages.pipeline import _rows

SHOTPLAN_SYSTEM = """You are the shot planner for a car YouTube Short. For EACH
segment you receive (in order), choose the strongest visual:

- "car": show the ACTUAL car. Use for spec, price, value and looks beats — any
  line about the car itself. No AI prompt needed.
- "concept": a conceptual / comedic / lifestyle scene that visualizes the JOKE
  or feeling, NOT the car. Use for hooks, punchlines, metaphors and reactions.

For every "concept" segment, write a vivid TEXT-TO-VIDEO prompt:
- brand-neutral: NEVER name a car brand or show a badge/logo.
- ONE 5-second cinematic scene: subject + action + mood + shot type + lighting.
- concrete and shootable (e.g. "an older couple on a sofa glaring skeptically
  at the camera, arms crossed, warm living-room light, slow push-in, cinematic").

Output ONLY a JSON array, one object per segment IN ORDER:
{"type": "car" | "concept", "prompt": "<text-to-video prompt, or empty for car>"}"""


def plan_shots(script: Script, llm) -> list[dict]:
    seglist = "\n".join(f"{i}. [{s.role}] {s.text}" for i, s in enumerate(script.segments))
    rows = _rows(llm.complete_json(SHOTPLAN_SYSTEM, f"SEGMENTS:\n{seglist}\n\nPlan the shots now."))
    plan = []
    for i, seg in enumerate(script.segments):
        row = rows[i] if i < len(rows) else {}
        kind = row.get("type", "car")
        plan.append({
            "index": i,
            "role": seg.role,
            "text": seg.text,
            "type": kind,
            "prompt": (row.get("prompt", "") if kind == "concept" else ""),
        })
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan per-beat visuals + AI prompts.")
    parser.add_argument("--script-file", required=True)
    parser.add_argument("--provider", default="groq",
                        choices=["gemini", "groq", "cerebras", "openrouter", "ollama"])
    parser.add_argument("--out", help="Where to save the shots JSON (default: shots/<name>.shots.json).")
    args = parser.parse_args()

    script = Script.model_validate_json(Path(args.script_file).read_text())
    plan = plan_shots(script, make_llm(args.provider))

    out = Path(args.out) if args.out else Path("shots") / (Path(args.script_file).stem.replace(".script", "") + ".shots.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=2))

    print(f"\nSHOT PLAN — {script.subject}  (saved {out})\n" + "=" * 60)
    for shot in plan:
        if shot["type"] == "car":
            print(f"[{shot['index']}] {shot['role']:6} CAR footage — \"{shot['text'][:60]}...\"")
        else:
            print(f"[{shot['index']}] {shot['role']:6} AI CONCEPT clip:")
            print(f"      line : {shot['text'][:70]}")
            print(f"      PROMPT: {shot['prompt']}")
    concept = [s for s in plan if s["type"] == "concept"]
    print("=" * 60)
    print(f"{len(concept)} AI clip(s) to generate. Save them as "
          f"assets/ai/<car>/seg_<index>.mp4")


if __name__ == "__main__":
    main()
