"""Unified command-line entry point: `carshorts <command> [args...]`.

A single console script (installed via [project.scripts]) that dispatches to the
per-domain module CLIs. Each target module keeps its own argparse `main()`, so
`carshorts produce --spec ...` behaves exactly like the module did — we just run
its `__main__` block with the remaining args, the same as `python -m`.

  carshorts heartbeat --status
  carshorts produce --script-file data/scripts/x.json --spec specs/x.json ...
  carshorts portal
  carshorts competitors --limit 30
"""
from __future__ import annotations

import os
import runpy
import sys

from carshorts.core import paths

# command -> module. Grouped by domain to mirror the package layout.
COMMANDS: dict[str, str] = {
    # orchestration
    "heartbeat": "carshorts.orchestration.heartbeat",
    "pipeline": "carshorts.orchestration.pipeline",
    "calendar": "carshorts.orchestration.calendar_plan",
    # rendering / writing
    "produce": "carshorts.rendering.produce",
    "thumbnail": "carshorts.rendering.thumbnail",
    "jokes": "carshorts.adapters.humor",
    "liven": "carshorts.rendering.liven",
    "writescript": "carshorts.writing.writescript",
    "voices": "carshorts.rendering.voicesamples",
    # quality
    "qa": "carshorts.quality.qa",
    "vqa": "carshorts.quality.vqa",
    "assetvet": "carshorts.quality.assetvet",
    "firstframe": "carshorts.quality.firstframe",
    # sourcing
    "crawl": "carshorts.sourcing.crawl",
    "research": "carshorts.sourcing.webresearch",
    "newscrawl": "carshorts.sourcing.newscrawl",
    "ingest": "carshorts.sourcing.ingest",
    # intel
    "analytics": "carshorts.intel.analytics",
    "analyze": "carshorts.intel.analyze",
    "competitors": "carshorts.intel.competitors",
    "engagement": "carshorts.intel.engagement",
    "experiments": "carshorts.intel.experiments",
    "comments": "carshorts.intel.comments",
    "retention-watch": "carshorts.intel.retention_watch",
    "anglelab": "carshorts.intel.anglelab",
    # agents / publishing / portal
    "agent": "carshorts.agents.agent",
    "brain": "carshorts.agents.brain",
    "critic": "carshorts.agents.critic",
    "autoloop": "carshorts.agents.autoloop",
    "publish": "carshorts.publishing.publish",
    "publishkit": "carshorts.publishing.publishkit",
    "portal": "carshorts.portal.server",
    # demo
    "run": "carshorts.run",
}


def _usage() -> str:
    lines = ["carshorts <command> [args...]", "", "commands:"]
    lines += [f"  {c}" for c in sorted(COMMANDS)]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Run from the project root so every path resolves identically regardless of
    # where `carshorts` was launched from (see carshorts.core.paths).
    try:
        os.chdir(paths.ROOT)
    except OSError:
        pass
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_usage())
        return
    cmd, rest = argv[0], argv[1:]
    module = COMMANDS.get(cmd)
    if not module:
        print(f"unknown command {cmd!r}\n\n{_usage()}", file=sys.stderr)
        sys.exit(2)
    # run the target module's __main__ with the remaining args, like `python -m`
    sys.argv = [f"carshorts {cmd}", *rest]
    runpy.run_module(module, run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
