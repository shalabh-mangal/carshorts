"""Canonical filesystem layout — one ROOT, every path hangs off it.

Historically the tool hardcoded cwd-relative strings (``Path("data/…")``,
``Path("out/…")``) and so only ran from the repo root, with the layout implicit
and scattered across ~15 modules. This module makes the layout explicit and
absolute: ROOT is derived from this file's location
(``<root>/src/carshorts/core/paths.py``), overridable with ``CARSHORTS_ROOT``.
The CLI chdirs to ROOT at startup (see ``carshorts.cli``) so any not-yet-migrated
relative literal still resolves.

The constants are grouped by RESPONSIBILITY, which is the seam the AI-Media-OS
Sprint 0 reorg cuts along:

  * KNOWLEDGE  — human-curated inputs, committed (specs, charters, assets, the
                 curated data/* knowledge files). These stay in the source tree.
  * RUNTIME    — machine-written operational state (queue, ledgers, reports,
                 caches). Regenerable-ish; destined for ``workspace/``.
  * OUTPUT     — generated media (renders, generated clips). Gitignored; destined
                 for ``workspace/``.

Because every module reads its paths from HERE, relocating a directory to
``workspace/`` later is a one-line edit in this file — no module changes.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("CARSHORTS_ROOT") or Path(__file__).resolve().parents[3])
WORKSPACE = ROOT / "workspace"        # all generated/regenerable artifacts (gitignored)

# ======================================================================
# KNOWLEDGE — human-curated inputs, committed, stay in the source tree
# ======================================================================
CHARTERS = ROOT / "charters"          # role charters + TASTE.md (the LAW)
CONTEXT = ROOT / "context"
MANIFESTS = CONTEXT / "manifests"     # curated render-record mirror
SPECS = ROOT / "specs"                # sourced fact sheets
SPECS_EXTRAS = ROOT / "specs_extras"  # price/news extras
ASSETS = ROOT / "assets"              # curated licensed media pool (committed)

# Curated asset sub-pools (real, licensed footage/stills/fonts/music) — SOURCE.
CARS = ASSETS / "cars"                # per-car vetted pools (images/press/own/stock)
STOCK = ASSETS / "stock"              # generic vetted stock
FONTS = ASSETS / "fonts"
MUSIC = ASSETS / "music"
BROLL = ASSETS / "broll"              # reusable real b-roll pool

# Curated KNOWLEDGE — human-tuned inputs, split OUT of data/ into knowledge/
# (committed; the "knowledge" half of the data/ split).
KNOWLEDGE = ROOT / "knowledge"
LEARNINGS = KNOWLEDGE / "learnings.json"      # the craft/data playbook
CALENDAR = KNOWLEDGE / "calendar.json"        # experiment calendar
TOPIC_IDEAS = KNOWLEDGE / "topic_ideas.json"
COMPETITORS = KNOWLEDGE / "competitors.json"  # watchlist (handles/IDs)
NEWS_SOURCES = KNOWLEDGE / "news_sources.json"
MUSIC_TAGS = KNOWLEDGE / "music_tags.json"
FIRSTFRAME_BASELINE = KNOWLEDGE / "firstframe_baseline.json"  # learned feed norm
SOUND_PROFILES = KNOWLEDGE / "sound_profiles"  # per-car mix profiles
VOICE = KNOWLEDGE / "voice"                   # owner reference clip(s) — curated
VOICE_REF = VOICE / "owner_reference.mp3"

# ======================================================================
# RUNTIME — machine-written operational state (the "runtime" half of data/)
# ======================================================================
DATA = ROOT / "data"
SCRIPTS = DATA / "scripts"            # locked .script.json per video
QUEUE = DATA / "queue"                # review/approval cards
RECIPES = DATA / "recipes"            # render-record cards
REPORTS = DATA / "reports"            # generated markdown reports
FEEDBACK = DATA / "feedback"          # owner Gate-1/2 feedback
COMMENTS = DATA / "comments"          # harvested comment reports
LOGS = WORKSPACE / "logs"             # scheduled-task stdout (regenerable)

# Runtime ledgers / caches (single files).
AGENT_BUDGET = DATA / "agent_budget.json"
AGENT_LOG = DATA / "agent_log.jsonl"
BRAIN_LOG = DATA / "brain_log.jsonl"
BRAIN_INBOX = DATA / "brain_inbox.jsonl"
FAILURES = DATA / "failures.jsonl"
HEARTBEAT_LOG = DATA / "heartbeat_log.jsonl"
RETENTION_LOG = DATA / "retention_log.jsonl"
EXPERIMENTS = DATA / "experiments.json"
ENGAGEMENT = DATA / "engagement.json"
COMPETITOR_INTEL = DATA / "competitor_intel.json"
VET_CACHE = DATA / "vet_cache.json"
GEN_PROVENANCE = DATA / "gen_provenance.json"   # AI-clip provenance ledger

# Transient ingest drop zone (gitignored working area, not a curated pool).
INBOX = ASSETS / "inbox"

# ======================================================================
# WORKSPACE — generated/regenerable artifacts, gitignored, OUT of the source tree
# ======================================================================
GEN = WORKSPACE / "generated"         # AI-generated clips (jokes / living stills)
CACHE = WORKSPACE / "cache"
TTS_CACHE = CACHE / "tts"             # synthesized voice cache

# OUTPUT — final deliverables (renders + publish kits). Kept at out/ because live
# queue cards store "out/<slug>..." paths; relocating to workspace/renders is a
# ranked future step (needs a card-path migration). Already dedicated + gitignored.
OUT = ROOT / "out"
VOICE_OPTIONS = OUT / "voice_options" # per-video voice samples for owner pick


def car_dir(slug: str) -> Path:
    """The curated asset pool for one car: <ASSETS>/cars/<slug>."""
    return CARS / slug


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
