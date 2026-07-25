"""The orchestrator — one command per car, human gates preserved.

  python -m carshorts.orchestration.pipeline "Mahindra Thar" --persona deadpan   # draft stage
  python -m carshorts.orchestration.pipeline --approve thar                      # final + upload
  python -m carshorts.orchestration.pipeline --queue                             # what awaits you

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

from carshorts.rendering.produce import _slug

QUEUE = Path("data/queue")


def _run(cmd: list[str]) -> int:
    print(f"\n▶ {' '.join(cmd)}")
    return subprocess.call(cmd)


def draft(car: str, persona: str = "deadpan", language: str = "english",
          video_format: str = "spotlight", no_agent: bool = False) -> None:
    slug = _slug(car)
    spec = Path(f"specs/{slug}.json")
    extras = Path(f"specs_extras/{slug}.json")
    if not spec.exists():
        sys.exit(f"missing {spec} — crawl it first:  python -m carshorts.sourcing.crawl \"{car}\" --out specs\n"
                 f"then VERIFY the specs against CarDekho (generation mixing!).")

    script = Path(f"scripts/{slug}_{persona}.script.json")
    agent_wrote = False
    if not no_agent:
        # SCRIPTWRIGHT: researches fresh news + prices from real outlets,
        # writes extras AND the script itself, proves both guards clean.
        from carshorts.agents.agent import run_agent
        print("scriptwright agent researching + writing (this takes a few minutes)…")
        outcome = run_agent("scriptwright", (
            f"Car: {car}\nSlug: {slug}\nPersona: {persona}\n"
            f"Format: {video_format}\nLanguage: {language}\n"
            f"Spec sheet: specs/{slug}.json\n"
            f"Extras to write: specs_extras/{slug}.json\n"
            f"Script to write: {script}"))
        agent_wrote = outcome["ok"] and script.exists() and extras.exists()
        print(("scriptwright: " + str(outcome["result"])[:600]) if agent_wrote
              else f"scriptwright unavailable ({str(outcome['result'])[:120]}) — "
                   f"falling back to the template writer")
    # CURATOR: thin visual pool -> the asset hunter fills it (license-clean)
    if not no_agent:
        pool_count = (len(list(Path(f"assets/cars/{slug}/images").glob("*")))
                      + len(list(Path(f"assets/cars/{slug}/stock").glob("*.mp4"))))
        if pool_count < 12:
            from carshorts.agents.agent import run_agent
            print(f"visual pool thin ({pool_count}) — curator agent hunting assets…")
            run_agent("curator", f"Car: {car}\nSlug: {slug}\n"
                                 f"Pool root: assets/cars/{slug}/")
    # COMPOSER: one-time per-car sound profile (cached forever after)
    if not no_agent and not Path(f"data/sound_profiles/{slug}.json").exists():
        from carshorts.agents.agent import run_agent
        print("composer agent profiling the car's sound…")
        run_agent("composer", f"Car: {car}\nSlug: {slug}\n"
                              f"Spec: specs/{slug}.json\nScript: {script}\n"
                              f"Profile out: data/sound_profiles/{slug}.json")

    if not agent_wrote:
        if not extras.exists():
            sys.exit(f"missing {extras} — add price/value/news "
                     f"(see specs_extras/mahindra-thar.json as template).")
        if _run([sys.executable, "-m", "carshorts.writing.writescript", "--spec", str(spec),
                 "--persona", persona, "--language", language, "--format", video_format,
                 "--variants", "3", "--provider", "groq", "--out", str(script)]) != 0:
            sys.exit("script stage failed")

    draft_out = Path(f"out/{slug}_draft.mp4")
    if _run([sys.executable, "-m", "carshorts.rendering.produce", "--script-file", str(script),
             "--spec", str(spec), "--skip-factcheck", "--persona", persona,
             "--provider", "groq", "--out", str(draft_out)]) != 0:
        sys.exit("draft render failed")
    _run([sys.executable, "-m", "carshorts.quality.vqa", str(draft_out)])

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
          f"3. Approve: python -m carshorts.orchestration.pipeline --approve {slug}\n"
          f"   (re-run draft after edits: python -m carshorts.orchestration.pipeline \"{car}\")")


def _progress(slug: str, step: str, done: bool = False) -> None:
    pf = QUEUE / f"{slug}.progress.json"
    if done:
        pf.unlink(missing_ok=True)
        return
    pf.write_text(json.dumps({"step": step,
                              "at": datetime.datetime.now().isoformat(timespec="seconds")}))


def approve(slug: str, privacy: str = "public") -> None:
    """Draft approved -> render the PREMIUM final and put it back in the
    portal for a second approval. Nothing is uploaded from here — the owner
    reviews the actual file that would ship (owner rule: the final version
    must also be shown and approved)."""
    card_path = QUEUE / f"{slug}.json"
    if not card_path.exists():
        sys.exit(f"nothing queued for {slug!r} — run the draft stage first.")
    card = json.loads(card_path.read_text())

    final_out = Path(f"out/{slug}_final.mp4")
    _progress(slug, "rendering premium final (ElevenLabs voice)…")
    # finals use the same owner-chosen edge voice as drafts (free, consistent —
    # what the owner approved is exactly what ships). ElevenLabs upgrade is a
    # one-line change here when revenue justifies it.
    if _run([sys.executable, "-m", "carshorts.rendering.produce", "--script-file", card["script"],
             "--spec", card["spec"], "--skip-factcheck",
             "--persona", card.get("persona", "deadpan"),
             "--provider", "groq", "--out", str(final_out)]) != 0:
        card["status"] = "final_failed"
        card_path.write_text(json.dumps(card, indent=2))
        _progress(slug, "", done=True)
        sys.exit("final render failed — queue card kept")
    _progress(slug, "visual QA on the final…")
    _run([sys.executable, "-m", "carshorts.quality.vqa", str(final_out)])

    card["status"] = "final_review"
    card["final"] = str(final_out)
    card["note"] = ("PREMIUM FINAL ready (channel voice) — review THIS file; "
                    "Publish ships it to YouTube untouched.")
    card_path.write_text(json.dumps(card, indent=2))
    _progress(slug, "", done=True)
    print(f"final ready for second approval -> {final_out}")


def publish(slug: str, privacy: str = "public") -> None:
    """Second approval given on the FINAL -> publish kit + YouTube upload."""
    card_path = QUEUE / f"{slug}.json"
    card = json.loads(card_path.read_text())
    final_out = Path(card.get("final") or f"out/{slug}_final.mp4")
    if not final_out.exists():
        sys.exit("no final file — approve the draft first")
    _progress(slug, "writing title/description kit…")
    _run([sys.executable, "-m", "carshorts.publishing.publishkit", "--script", card["script"],
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

    _progress(slug, "uploading to YouTube…")
    # pass a thumbnail when one exists (out/<slug>_thumb.jpg|png). Shorts
    # ignore custom thumbs in the feed (frame 1 is the thumb there — QA
    # already forces a car shot), but the channel grid/search can use it.
    publish_cmd = [sys.executable, "-m", "carshorts.publishing.publish", str(final_out),
                   "--title", title, "--description-file", str(desc_file),
                   "--privacy", privacy]
    for ext in ("jpg", "png"):
        thumb = Path(f"out/{slug.split('-')[-1]}_thumb.{ext}")
        thumb2 = Path(f"out/{slug}_thumb.{ext}")
        pick = thumb2 if thumb2.exists() else thumb if thumb.exists() else None
        if pick:
            publish_cmd += ["--thumbnail", str(pick)]
            break
    if _run(publish_cmd) != 0:
        card["status"] = "final_review"
        card["note"] = "⚠ upload failed — final kept on disk, publish again to retry"
        card_path.write_text(json.dumps(card, indent=2))
        _progress(slug, "", done=True)
        sys.exit("upload failed — final kept on disk")

    card["status"] = "published"
    card["published_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    card_path.write_text(json.dumps(card, indent=2))
    _progress(slug, "", done=True)
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
    ap.add_argument("--approve", metavar="SLUG",
                    help="Approve a queued draft -> premium final -> back to portal for 2nd approval.")
    ap.add_argument("--publish", metavar="SLUG",
                    help="Second approval on the final -> publish kit + YouTube upload.")
    ap.add_argument("--privacy", default="public", choices=["public", "unlisted", "private"])
    ap.add_argument("--no-agent", action="store_true",
                    help="Skip the scriptwright agent (template writer only).")
    ap.add_argument("--queue", action="store_true", help="Show the approval queue.")
    ap.add_argument("--next", action="store_true",
                    help="Draft the next pending slot from the experiment calendar.")
    args = ap.parse_args()

    if args.next:
        from carshorts.orchestration.calendar_plan import mark, next_pending
        entry = next_pending()
        if not entry:
            sys.exit("calendar empty — python -m carshorts.orchestration.calendar_plan --build")
        print(f"calendar slot {entry['slot']}: {entry['car']} "
              f"[{entry['persona']}/{entry['format']}/{entry['length_bucket']}]")
        draft(entry["car"], persona=entry["persona"], video_format=entry["format"],
              no_agent=args.no_agent)
        mark(entry["slot"], "drafted")
        return
    if args.queue:
        show_queue()
    elif args.approve:
        approve(args.approve, privacy=args.privacy)
    elif args.publish:
        publish(args.publish, privacy=args.privacy)
    elif args.car:
        draft(args.car, persona=args.persona, language=args.language,
              video_format=args.format, no_agent=args.no_agent)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
