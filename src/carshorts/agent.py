"""Agent harness — the system's own Claude brain.

  from carshorts.agent import run_agent
  result = run_agent("mechanic", "Owner feedback maps to no action: ...")

Invokes Claude Code headless (`claude -p`) inside this repo with a role
charter from agents/<role>.md. This is what makes the system smart instead
of scripted: the agent can read code, edit it, run tests, re-render — the
same competency as the interactive supervisor, on demand.

Safety envelope:
  - daily run budget (data/agent_budget.json) — the owner's Claude
    subscription is shared with interactive work; escalations must be
    rare-by-design, not a background drain
  - per-run turn cap and timeout
  - every run journaled to data/agent_log.jsonl (role, task, result, cost)
  - roles carry their own hard rules (no .env, no paid APIs, no uploads)
"""
from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path

AGENTS_DIR = Path("agents")
BUDGET_FILE = Path("data/agent_budget.json")
LOG_FILE = Path("data/agent_log.jsonl")

DAILY_RUN_CAP = 12          # escalations per day, shared across roles
MAX_TURNS = 60              # per-run agentic turn cap (40 proved tight for edit+render+verify)
TIMEOUT_S = 2400            # 40 min hard wall per run


class BudgetExhausted(RuntimeError):
    pass


def _budget_check_and_increment() -> int:
    today = datetime.date.today().isoformat()
    state = {"date": today, "runs": 0}
    if BUDGET_FILE.exists():
        state = json.loads(BUDGET_FILE.read_text())
        if state.get("date") != today:
            state = {"date": today, "runs": 0}
    if state["runs"] >= DAILY_RUN_CAP:
        raise BudgetExhausted(
            f"agent budget spent ({DAILY_RUN_CAP}/day) — escalation queued for "
            f"the supervisor instead")
    state["runs"] += 1
    BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
    BUDGET_FILE.write_text(json.dumps(state))
    return state["runs"]


def _journal(entry: dict) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run_agent(role: str, task: str, max_turns: int = MAX_TURNS) -> dict:
    """Run one headless agent session. Returns {ok, result, ...}; never raises
    on agent failure (journals and reports instead) — callers stay resilient.
    """
    role_file = AGENTS_DIR / f"{role}.md"
    if not role_file.exists():
        return {"ok": False, "result": f"unknown role {role!r}"}
    started = datetime.datetime.now().isoformat(timespec="seconds")
    try:
        run_no = _budget_check_and_increment()
    except BudgetExhausted as exc:
        _journal({"at": started, "role": role, "ok": False,
                  "result": str(exc), "task": task[:400]})
        return {"ok": False, "result": str(exc)}

    prompt = (role_file.read_text()
              + "\n\n# Task (from the system, automated escalation)\n" + task)
    # Load .env so a headless ANTHROPIC_API_KEY reaches the claude CLI (the only
    # auth option in a non-interactive/sandbox host — an interactive /login can't
    # run here). The subprocess inherits os.environ. If the CLI is instead logged
    # in interactively, no key is needed and this is a no-op.
    from .config import load_env
    load_env()
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt,
             "--output-format", "json",
             "--max-turns", str(max_turns),
             "--permission-mode", "acceptEdits",
             "--allowedTools",
             "Read,Edit,Write,Grep,Glob,WebSearch,WebFetch,"
             "Bash(python*),Bash(pytest*),Bash(ffmpeg*),Bash(ffprobe*),Bash(ls*)"],
            capture_output=True, text=True, timeout=TIMEOUT_S,
            cwd=str(Path.cwd()))
        payload = {}
        try:
            payload = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:
            pass
        result_text = payload.get("result") or (proc.stdout or proc.stderr)[-2000:]
        ok = proc.returncode == 0 and not payload.get("is_error", False)
        entry = {"at": started, "role": role, "run_no": run_no, "ok": ok,
                 "turns": payload.get("num_turns"),
                 "cost_usd": payload.get("total_cost_usd"),
                 "duration_ms": payload.get("duration_ms"),
                 "task": task[:400], "result": (result_text or "")[:1500]}
    except subprocess.TimeoutExpired:
        ok = False
        entry = {"at": started, "role": role, "run_no": run_no, "ok": False,
                 "task": task[:400], "result": f"timed out after {TIMEOUT_S}s"}
        result_text = entry["result"]
    except (FileNotFoundError, OSError) as exc:
        # `claude` not installed/on PATH — the whole agent layer is unavailable.
        # The harness promises never to raise on agent failure, so callers (the
        # pipeline, rework escalation) stay resilient and fall back to their
        # non-agent paths.
        ok = False
        result_text = ("claude CLI not available (install: npm i -g "
                       "@anthropic-ai/claude-code, then authenticate) — "
                       f"{str(exc)[:120]}")
        entry = {"at": started, "role": role, "run_no": run_no, "ok": False,
                 "task": task[:400], "result": result_text}
    _journal(entry)
    return {"ok": ok, "result": result_text, "run_no": run_no}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Run a system agent by role.")
    ap.add_argument("role", help="agents/<role>.md charter to use")
    ap.add_argument("task", help="Task text for the agent.")
    args = ap.parse_args()
    out = run_agent(args.role, args.task)
    print(("OK " if out["ok"] else "FAIL ") + str(out["result"])[:800])


if __name__ == "__main__":
    main()
