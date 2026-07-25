"""The heartbeat — one command that runs the day.

  python -m carshorts.orchestration.heartbeat              # run the day
  python -m carshorts.orchestration.heartbeat --dry-run    # decide + report, change nothing
  python -m carshorts.orchestration.heartbeat --status     # just the state of the channel

Cadence is not a growth tactic here, it is the DATA-GENERATION ENGINE: without a
steady stream of published videos there is no signal to learn from, and every
downstream organ (experiments, analytics, competitor comparison) starves. Yet
`pipeline --next` has never had anything driving it, so the run stopped the
moment a human forgot.

This is that driver, and it is deliberately conservative:

  1. refresh analytics first (retention_watch) — decide on fresh data
  2. GUARDS, in order:
       - a render already in flight        -> skip (never two at once)
       - drafts already waiting on the owner (>= --max-pending) -> skip
         (the owner is the bottleneck; piling up drafts wastes budget and
          buries the queue)
       - already produced today            -> skip (idempotent: safe to run
         hourly, safe to retry after a crash)
       - calendar has no pending slot      -> skip and say so
  3. otherwise draft the next calendar slot via pipeline --next
  4. journal + write an owner-facing report

IT NEVER PUBLISHES. Gate 1 (draft approval) and Gate 2 (final watch) belong to
the owner — see agents/TASTE.md. The heartbeat's whole job is to make sure a
draft is always WAITING for those gates, never to walk through them.
"""
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

QUEUE = Path("data/queue")
JOURNAL = Path("data/heartbeat_log.jsonl")
REPORTS = Path("data/reports")

# statuses that mean the owner must act before more work is useful
AWAITING_OWNER = {"awaiting_approval", "final_review"}
# statuses that mean the machine is mid-flight; never start a second render
IN_FLIGHT = {"rendering", "reworking", "approved", "publishing"}


def queue_state() -> dict:
    """Count queue cards by what they're blocked on."""
    awaiting, in_flight, other = [], [], []
    for path in sorted(QUEUE.glob("*.json")) if QUEUE.exists() else []:
        if path.name.endswith(".progress.json"):
            continue
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a corrupt card must not stop the day
            continue
        status = card.get("status", "")
        bucket = (awaiting if status in AWAITING_OWNER
                  else in_flight if status in IN_FLIGHT else other)
        bucket.append({"slug": card.get("slug"), "status": status,
                       "car": card.get("car")})
    return {"awaiting_owner": awaiting, "in_flight": in_flight, "other": other}


def produced_today(today: str | None = None) -> bool:
    """Did a produce action already succeed today? Keeps the run idempotent."""
    today = today or datetime.date.today().isoformat()
    if not JOURNAL.exists():
        return False
    for line in JOURNAL.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("action") == "produce" and entry.get("ok") \
                and str(entry.get("at", "")).startswith(today):
            return True
    return False


def agents_available() -> bool:
    """Can the agentic minds run? They shell out to the `claude` CLI."""
    import shutil
    return shutil.which("claude") is not None


def preflight(slug: str, agents_ok: bool) -> list[str]:
    """What would stop the pipeline drafting this car? Returns blockers.

    Cheap to check and worth checking: without this the heartbeat starts a run,
    spends agent budget and ~15 minutes of render, and only then discovers a
    missing extras file. A system that fails at 3am should be able to say why.
    """
    blockers: list[str] = []
    if not Path(f"specs/{slug}.json").exists():
        blockers.append(f"specs/{slug}.json missing — crawl it first")
    if not Path(f"specs_extras/{slug}.json").exists() and not agents_ok:
        blockers.append(
            f"specs_extras/{slug}.json missing AND the scriptwright agent is "
            f"unavailable (no `claude` CLI) — nothing can supply price/news")
    return blockers


def decide(awaiting: int, in_flight: int, ran_today: bool,
           has_slot: bool, max_pending: int) -> tuple[str, str]:
    """Pure decision function: (action, reason). Ordered most-blocking first.

    Kept free of I/O so the day's logic is testable offline — this is the one
    piece that must never misfire, because a wrong 'produce' burns agent budget
    and a wrong 'skip' silently stops the channel.
    """
    if in_flight:
        return "skip", f"{in_flight} render(s) already in flight"
    if ran_today:
        return "skip", "already produced today (idempotent)"
    if awaiting >= max_pending:
        return "skip", (f"{awaiting} draft(s) waiting on you (limit {max_pending}) — "
                        f"review the queue and the next one will flow")
    if not has_slot:
        return "skip", "experiment calendar has no pending slot — build one"
    return "produce", "clear to draft the next calendar slot"


def _journal(entry: dict) -> None:
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run(dry_run: bool = False, no_agent: bool = False, max_pending: int = 2,
        status_only: bool = False) -> dict:
    now = datetime.datetime.now().isoformat(timespec="seconds")
    today = datetime.date.today().isoformat()

    # 1. fresh data first — decide on today's numbers, not yesterday's
    if not status_only:
        try:
            from carshorts.intel.retention_watch import run as watch
            watch(quiet=True)
        except Exception as exc:  # noqa: BLE001 — analytics must never block the day
            print(f"  (analytics refresh skipped: {str(exc)[:100]})")

    state = queue_state()
    try:
        from carshorts.orchestration.calendar_plan import next_pending
        slot = next_pending()
    except Exception:  # noqa: BLE001
        slot = None

    ran_today = produced_today(today)
    action, reason = decide(len(state["awaiting_owner"]), len(state["in_flight"]),
                            ran_today, slot is not None, max_pending)

    # pre-flight: never start a run that cannot finish. Checked only when we
    # would otherwise produce, so a healthy skip stays cheap.
    blockers: list[str] = []
    if action == "produce" and slot:
        from carshorts.rendering.produce import _slug
        blockers = preflight(_slug(slot["car"]), agents_available())
        if blockers:
            action, reason = "blocked", "; ".join(blockers)

    print(f"\n═══ HEARTBEAT {now} ═══")
    print(f"  awaiting you : {len(state['awaiting_owner'])}"
          + (f"  ({', '.join(c['slug'] or '?' for c in state['awaiting_owner'])})"
             if state["awaiting_owner"] else ""))
    print(f"  in flight    : {len(state['in_flight'])}")
    print("  next slot    : " + (f"{slot['car']} [{slot['persona']}/{slot['format']}]"
                                  if slot else "none"))
    print(f"  decision     : {action.upper()} — {reason}")

    result = {"at": now, "action": action, "reason": reason,
              "awaiting_owner": len(state["awaiting_owner"]),
              "in_flight": len(state["in_flight"]),
              "slot": (slot or {}).get("car"), "blockers": blockers, "ok": None}

    if status_only or action in ("skip", "blocked"):
        result["ok"] = True
        if not status_only:
            _journal(result)
        _write_report(result, state, slot)
        return result

    if dry_run:
        print("  dry-run      : would run pipeline --next"
              + (" --no-agent" if no_agent else ""))
        result["ok"] = True
        result["dry_run"] = True
        return result

    cmd = [sys.executable, "-m", "carshorts.orchestration.pipeline", "--next"]
    if no_agent:
        cmd.append("--no-agent")
    print(f"  running      : {' '.join(cmd[2:])}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    result["ok"] = proc.returncode == 0
    result["qa_flagged"] = "QA FAILED" in (proc.stdout or "")
    tail = (proc.stdout or "")[-1500:]
    result["tail"] = tail[-400:]
    print(tail)
    if not result["ok"]:
        print(f"  ⚠ produce failed (exit {proc.returncode})")
        result["stderr"] = (proc.stderr or "")[-400:]

    _journal(result)
    _write_report(result, queue_state(), slot)
    return result


def _write_report(result: dict, state: dict, slot: dict | None) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    lines = [f"# Heartbeat — {today}", "",
             f"- decision: **{result['action']}** — {result['reason']}",
             f"- awaiting your review: {len(state['awaiting_owner'])}",
             f"- in flight: {len(state['in_flight'])}",
             f"- next calendar slot: {(slot or {}).get('car', 'none')}", ""]
    if state["awaiting_owner"]:
        lines += ["## Waiting on you (portal → localhost:8787)", ""]
        lines += [f"- **{c['car']}** ({c['slug']}) — {c['status']}"
                  for c in state["awaiting_owner"]]
        lines.append("")
    if result.get("blockers"):
        lines += ["## 🚧 Blocked — the run cannot start until these are fixed", ""]
        lines += [f"- {b}" for b in result["blockers"]]
        lines.append("")
    if result.get("ok") is False:
        lines += ["## ⚠ Produce failed", "", "```", result.get("stderr", "")[:600], "```"]
    elif result.get("qa_flagged"):
        lines += ["", "⚠ QA flagged the new draft — inspect before approving."]
    (REPORTS / f"heartbeat-{today}.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the day: draft the next slot, report state.")
    ap.add_argument("--dry-run", action="store_true", help="Decide and report, change nothing.")
    ap.add_argument("--status", action="store_true", help="Show state only; take no action.")
    ap.add_argument("--no-agent", action="store_true", help="Skip agents (template writer).")
    ap.add_argument("--max-pending", type=int, default=2,
                    help="Skip producing when this many drafts already await you.")
    args = ap.parse_args()
    run(dry_run=args.dry_run, no_agent=args.no_agent,
        max_pending=args.max_pending, status_only=args.status)


if __name__ == "__main__":
    main()
