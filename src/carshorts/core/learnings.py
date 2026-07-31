"""Self-improving guidance: craft playbook + data-driven learnings.

data/learnings.json holds two lists:
  - craft_playbook: distilled retention craft from studying top short-form
    creators (techniques, never their content).
  - data_learnings: findings written by the weekly analytics pass — what OUR
    numbers say worked or failed.

load_learnings_guidance() folds both into every writer prompt, so each new
script is written with everything the channel has learned so far.
"""
from __future__ import annotations

import json

from carshorts.core import paths

LEARNINGS = paths.LEARNINGS


def load_learnings_guidance(max_items: int = 14) -> str:
    if not LEARNINGS.exists():
        return ""
    try:
        data = json.loads(LEARNINGS.read_text())
    except Exception:  # noqa: BLE001 — bad file must never block writing
        return ""
    rules = (data.get("craft_playbook", []) + data.get("data_learnings", []))[:max_items]
    if not rules:
        return ""
    lines = "\n".join(f"- {r}" for r in rules)
    return f"PROVEN CRAFT RULES (follow all; learned from data + top creators):\n{lines}"
