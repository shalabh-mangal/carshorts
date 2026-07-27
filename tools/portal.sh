#!/usr/bin/env bash
# Review portal - the Gate 1 / Gate 2 review station at http://localhost:8787.
# It's a LOCAL server (no hosting), so it's only "up" while this stays running.
# Run it and leave it open; it opens your browser. Ctrl-C to stop.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONUTF8=1

URL="http://localhost:8787"
echo "Review station -> $URL   (leave this running; Ctrl-C to stop)"
# best-effort browser open (macOS: open, Linux: xdg-open)
(command -v open >/dev/null 2>&1 && open "$URL") \
  || (command -v xdg-open >/dev/null 2>&1 && xdg-open "$URL") \
  || true
exec .venv/bin/python -m carshorts portal
