"""Skills — codified, invokable workflows the whole system shares.

Step 5 of the autonomy roadmap. A CHARTER says WHO an agent is (role, judgment,
hard rules — charters/*.md). A SKILL says HOW to run one workflow: the exact
ordered steps, the real `carshorts ...` commands, and the gates that must stay
green. Charters give competence; skills give CONSISTENCY — the headless agent
(agents/agent.py) and the owner run a task the same way every time instead of
the agent re-deriving the procedure (and drifting) each run.

A skill is a markdown file in charters/skills/<name>.md with frontmatter:

    ---
    name: source-footage
    description: <one line — what the skill accomplishes>
    triggers: footage, coverage, ingest, provenance   # keywords for auto-routing
    ---
    1. ...ordered steps, with the exact commands and gates...

This module loads them, lists them, routes a free-text task to the best-matching
skill by trigger keywords, and composes the skill body into an agent prompt. The
routing/parse core is pure so it is unit-tested without the filesystem.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from carshorts.core import paths

SKILLS_DIR = paths.CHARTERS / "skills"


@dataclass
class Skill:
    name: str
    description: str
    triggers: list[str] = field(default_factory=list)
    body: str = ""


def parse_skill(text: str, fallback_name: str = "") -> Skill:
    """Parse a skill markdown doc (frontmatter + body). Minimal, dependency-free:
    the frontmatter is simple `key: value` lines between `---` fences; `triggers`
    is a comma-separated list. Missing frontmatter → the whole text is the body."""
    name, description, triggers, body = fallback_name, "", [], text.strip()
    if text.lstrip().startswith("---"):
        after = text.lstrip()[3:]
        end = after.find("\n---")
        if end != -1:
            front = after[:end]
            body = after[end + 4:].lstrip("\n")
            for line in front.splitlines():
                if ":" not in line:
                    continue
                key, _, val = line.partition(":")
                key, val = key.strip().lower(), val.strip()
                if key == "name":
                    name = val
                elif key == "description":
                    description = val
                elif key == "triggers":
                    triggers = [t.strip().lower() for t in val.split(",") if t.strip()]
    return Skill(name=name or fallback_name, description=description,
                 triggers=triggers, body=body)


def load_skill(name: str, skills_dir: Path = SKILLS_DIR) -> Skill | None:
    path = skills_dir / f"{name}.md"
    if not path.exists():
        return None
    return parse_skill(path.read_text(encoding="utf-8"), fallback_name=name)


def list_skills(skills_dir: Path = SKILLS_DIR) -> list[Skill]:
    if not skills_dir.exists():
        return []
    out = [parse_skill(p.read_text(encoding="utf-8"), fallback_name=p.stem)
           for p in sorted(skills_dir.glob("*.md"))]
    return out


def route(task: str, skills: list[Skill]) -> Skill | None:
    """Pick the skill whose trigger keywords best match the task text. Returns the
    highest-scoring skill, or None if nothing matches (the agent then just runs on
    its charter). Ties break toward the skill defined first (stable order)."""
    low = (task or "").lower()
    best, best_score = None, 0
    for sk in skills:
        score = sum(1 for t in sk.triggers if t and t in low)
        if score > best_score:
            best, best_score = sk, score
    return best


def compose_prompt(skill: Skill, task: str) -> str:
    """Inject a skill's canonical steps ahead of the task, so the agent follows
    the procedure verbatim rather than improvising it."""
    return (f"# Skill: {skill.name}\n{skill.description}\n\n"
            f"Follow these steps IN ORDER; do not skip a gate:\n\n{skill.body}\n\n"
            f"# Task\n{task}")


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="List or show the system's codified skills.")
    ap.add_argument("name", nargs="?", help="skill to show; omit to list all")
    ap.add_argument("--route", metavar="TASK",
                    help="print which skill a free-text task would route to")
    args = ap.parse_args()

    skills = list_skills()
    if args.route:
        picked = route(args.route, skills)
        print(f"routes to: {picked.name if picked else '(none — charter only)'}")
        return
    if args.name:
        sk = load_skill(args.name)
        if not sk:
            raise SystemExit(f"no skill {args.name!r} in {SKILLS_DIR}")
        print(f"# {sk.name}\n{sk.description}\ntriggers: {', '.join(sk.triggers)}\n")
        print(sk.body)
        return
    if not skills:
        print("no skills yet — add charters/skills/<name>.md")
        return
    print(f"{len(skills)} skill(s):")
    for sk in skills:
        print(f"  {sk.name:<18} {sk.description}")


if __name__ == "__main__":
    main()
