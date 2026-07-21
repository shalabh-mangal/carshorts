"""The orchestrator — one command per car, human gates preserved.

  python -m carshorts.pipeline "Mahindra Thar" --persona deadpan   # draft stage
  python -m carshorts.pipeline --approve thar                      # final + upload
  python -m carshorts.pipeline --queue                             # what awaits you

DRAFT stage (fully automatic):
  1. checks spec sheet + extras exist (tells you exactly what's missing if not)
  2. writes the script (variants → judge → editor, learnings injected)
  3. renders the FREE draft (edge voice) with full QA + Visual QA
  4. parks an approval card in data/queue/ and stops — Gate 1 is YOURS

APPROVE stage (after you review draft + optionally edit the script):
  5. renders the final (ElevenLabs, cached where possible)
  6. generates the publish kit, uploads public, links the recipe
"""
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

from .produce import _slug

QUEUE = Path("data/queue")


def _run(cmd: list[str]) -> int:
    print(f"\n▶ {' '.join(cmd)}")
    return subprocess.call(cmd)


def draft(car: str, persona: str = "deadpan", language: str = "english",
          video_format: str = "spotlight") -> None:
    slug = _slug(car)
    spec = Path(f"specs/{slug}.json")
    extras = Path(f"specs_extras/{slug}.json")
    if not spec.exists():
        sys.exit(f"missing {spec} — crawl it first:  python -m carshorts.crawl \"{car}\" --out specs\n"
                 f"then VERIFY the specs against CarDekho (generation mixing!).")
    if not extras.exists():
        sys.exit(f"missing {extras} — add price/value/news (see specs_extras/mahindra-thar.json as template).")

    script = Path(f"scripts/{slug}_{persona}.script.json")
    if _run([sys.executable, "-m", "carshorts.writescript", "--spec", str(spec),
             "--persona", persona, "--language", language, "--format", video_format,
             "--variants", "3", "--provider", "groq", "--out", str(script)]) != 0:
        sys.exit("script stage failed")

    draft_out = Path(f"out/{slug}_draft.mp4")
    if _run([sys.executable, "-m", "carshorts.produce", "--script-file", str(script),
             "--spec", str(spec), "--skip-factcheck", "--persona", persona,
             "--provider", "groq", "--out", str(draft_out)]) != 0:
        sys.exit("draft render failed")
    _run([sys.executable, "-m", "carshorts.vqa", str(draft_out)])

    QUEUE.mkdir(parents=True, exist_ok=True)
    card = {
        "car": car, "slug": slug, "persona": persona, "language": language,
        "script": str(script), "spec": str(spec), "draft": str(draft_out),
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "status": "awaiting_approval",
    }
    (QUEUE / f"{slug}.json").write_text(json.dumps(card, indent=2))
    print(f"\n════ GATE 1 — YOUR MOVE ════\n"
          f"1. Watch the draft: {draft_out}\n"
          f"2. Edit the script if needed: {script}\n"
          f"3. Approve: python -m carshorts.pipeline --approve {slug}\n"
          f"   (re-run draft after edits: python -m carshorts.pipeline \"{car}\")")


def approve(slug: str, privacy: str = "public") -> None:
    card_path = QUEUE / f"{slug}.json"
    if not card_path.exists():
        sys.exit(f"nothing queued for {slug!r} — run the draft stage first.")
    card = json.loads(card_path.read_text())

    final_out = Path(f"out/{slug}_final.mp4")
    if _run([sys.executable, "-m", "carshorts.produce", "--script-file", card["script"],
             "--spec", card["spec"], "--skip-factcheck", "--voice-engine", "elevenlabs",
             "--provider", "groq", "--out", str(final_out)]) != 0:
        sys.exit("final render failed — queue card kept")
    _run([sys.executable, "-m", "carshorts.vqa", str(final_out)])

    _run([sys.executable, "-m", "carshorts.publishkit", "--script", card["script"],
          "--spec", card["spec"], "--provider", "groq"])
    kit = Path("out") / (Path(card["script"]).stem.replace(".script", "") + ".publish.md")
    title, desc_lines, in_desc = "", [], False
    for line in kit.read_text().splitlines():
        if line.startswith("1. "):
            title = title or line[3:]
        if line.startswith("## Description"):
            in_desc = True; continue
        if line.startswith("## Hashtags"):
            in_desc = False
        if in_desc and not line.startswith("## "):
            desc_lines.append(line)
    hashtags = [l for l in kit.read_text().splitlines() if l.startswith("#")]
    desc_file = Path(f"out/{slug}_upload_desc.txt")
    desc_file.write_text("\n".join(desc_lines).strip() + "\n\n" + (hashtags[-1] if hashtags else ""))

    if _run([sys.executable, "-m", "carshorts.publish", str(final_out),
             "--title", title, "--description-file", str(desc_file),
             "--privacy", privacy]) != 0:
        sys.exit("upload failed — final kept on disk")

    card["status"] = "published"
    card["published_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    card_path.write_text(json.dumps(card, indent=2))
    print(f"\n🚗 shipped {card['car']} — set the thumbnail via mobile app if needed.")


def show_queue() -> None:
    cards = sorted(QUEUE.glob("*.json")) if QUEUE.exists() else []
    if not cards:
        print("queue empty")
    for c in cards:
        d = json.loads(c.read_text())
        print(f"- {d['slug']:24} {d['status']:20} draft={d.get('draft')}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Car -> draft -> (you) -> final -> YouTube.")
    ap.add_argument("car", nargs="?", help="Car name to draft (e.g. 'Hyundai Creta').")
    ap.add_argument("--persona", default="deadpan", choices=["deadpan", "hype", "bhai"])
    ap.add_argument("--language", default="english", choices=["english", "hinglish", "hindi"])
    ap.add_argument("--format", default="spotlight",
                    choices=["spotlight", "vs", "five_things", "mythbust", "base_vs_top"])
    ap.add_argument("--approve", metavar="SLUG", help="Approve a queued draft -> final + upload.")
    ap.add_argument("--privacy", default="public", choices=["public", "unlisted", "private"])
    ap.add_argument("--queue", action="store_true", help="Show the approval queue.")
    ap.add_argument("--next", action="store_true",
                    help="Draft the next pending slot from the experiment calendar.")
    args = ap.parse_args()

    if args.next:
        from .calendar_plan import mark, next_pending
        entry = next_pending()
        if not entry:
            sys.exit("calendar empty — python -m carshorts.calendar_plan --build")
        print(f"calendar slot {entry['slot']}: {entry['car']} "
              f"[{entry['persona']}/{entry['format']}/{entry['length_bucket']}]")
        draft(entry["car"], persona=entry["persona"], video_format=entry["format"])
        mark(entry["slot"], "drafted")
        return
    if args.queue:
        show_queue()
    elif args.approve:
        approve(args.approve, privacy=args.privacy)
    elif args.car:
        draft(args.car, persona=args.persona, language=args.language, video_format=args.format)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
