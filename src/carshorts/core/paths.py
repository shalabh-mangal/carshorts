"""Canonical filesystem layout — one ROOT, every data dir hangs off it.

Historically the tool hardcoded cwd-relative strings (``Path("scripts/…")``,
``Path("agents")``, ``Path("out/…")``) and so only ran from the repo root. This
module makes the layout explicit and absolute: ROOT is derived from this file's
location (``<root>/src/carshorts/core/paths.py``), overridable with the
``CARSHORTS_ROOT`` env var for unusual deployments. The CLI chdirs to ROOT at
startup (see ``carshorts.cli``), so legacy relative literals still resolve while
they are migrated onto these constants.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("CARSHORTS_ROOT") or Path(__file__).resolve().parents[3])

# --- Knowledge / inputs (committed) --------------------------------------
CHARTERS = ROOT / "charters"        # role charters + TASTE.md (was ./agents)
CONTEXT = ROOT / "context"
MANIFESTS = CONTEXT / "manifests"   # curated render-record mirror
SPECS = ROOT / "specs"
SPECS_EXTRAS = ROOT / "specs_extras"
ASSETS = ROOT / "assets"

# --- Operational state (machine-written) ---------------------------------
DATA = ROOT / "data"
SCRIPTS = DATA / "scripts"          # locked .script.json per video (was ./scripts)
QUEUE = DATA / "queue"
RECIPES = DATA / "recipes"
REPORTS = DATA / "reports"
LOGS = DATA / "logs"

# --- Outputs (regenerable, gitignored) -----------------------------------
OUT = ROOT / "out"


def resolve(p: str | os.PathLike) -> Path:
    """Resolve a stored, possibly-relative path robustly. Absolute paths pass
    through; a relative path that exists under the caller's cwd is honoured (so
    tests and ad-hoc invocations keep working); otherwise it is anchored to
    ROOT. Windows backslashes are normalised so cards written on Windows still
    load on POSIX."""
    q = Path(str(p).replace("\\", "/"))
    if q.is_absolute() or q.exists():
        return q
    return ROOT / q
