#!/usr/bin/env bash
# One-command stand-up of the carshorts stack on macOS or Linux (incl. a fresh
# machine). Idempotent: safe to re-run; skips whatever is already present.
#
#   ./tools/setup.sh                 # full setup
#   ./tools/setup.sh --skip-install  # tools already present
#   ./tools/setup.sh --skip-cron     # don't add the daily cron jobs
#   HEARTBEAT_TIME=08:00 ./tools/setup.sh
#
# It NEVER touches your secrets or uploads anything. At the end it prints exactly
# what only you can do (drop in .env / OAuth files / assets, authenticate agents).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
SKIP_INSTALL=0; SKIP_CRON=0
for a in "$@"; do case "$a" in
  --skip-install) SKIP_INSTALL=1 ;; --skip-cron) SKIP_CRON=1 ;;
esac; done
HEARTBEAT_TIME="${HEARTBEAT_TIME:-08:00}"

OK=(); WARN=(); TODO=()
say()  { printf '\n==> %s\n' "$1"; }
good() { printf '  [ok]   %s\n' "$1"; OK+=("$1"); }
warn() { printf '  [warn] %s\n' "$1"; WARN+=("$1"); }
have() { command -v "$1" >/dev/null 2>&1; }

OS="$(uname -s)"
say "carshorts setup - repo: $REPO ($OS)"

# --- 1. system tools -------------------------------------------------------
install_pkg() {  # install_pkg <brew-name> <apt-name>
  if [ "$OS" = "Darwin" ]; then brew install "$1"
  elif have apt-get; then sudo apt-get update -qq && sudo apt-get install -y "$2"
  elif have dnf; then sudo dnf install -y "$2"
  elif have pacman; then sudo pacman -S --noconfirm "$2"
  else return 1; fi
}

if [ "$SKIP_INSTALL" = "0" ]; then
  say "System tools (Python, ffmpeg, Node, claude CLI)"
  if [ "$OS" = "Darwin" ] && ! have brew; then
    warn "Homebrew not found - install it from https://brew.sh then re-run"
  fi
  if have python3 && python3 -c 'import sys; sys.exit(0 if sys.version_info[:2]>=(3,10) else 1)'; then
    good "Python present: $(python3 --version)"
  else
    printf '  installing Python...\n'; install_pkg python@3.12 python3 || warn "install Python 3.12 manually"; good "Python step done"
  fi
  if have ffmpeg; then good "ffmpeg present"; else printf '  installing ffmpeg...\n'; install_pkg ffmpeg ffmpeg || warn "install ffmpeg manually"; good "ffmpeg step done"; fi
  if have node; then good "Node present: $(node --version)"; else printf '  installing Node...\n'; install_pkg node nodejs || warn "install Node manually"; good "Node step done"; fi
  if have claude; then good "claude CLI present"
  elif have npm; then printf '  installing claude CLI...\n'; npm install -g @anthropic-ai/claude-code >/dev/null 2>&1 && good "claude CLI installed" || warn "claude CLI install failed - run: npm install -g @anthropic-ai/claude-code"
  else warn "npm not found - install Node/npm, then: npm install -g @anthropic-ai/claude-code"; fi
else
  say "Skipping installs (--skip-install)"
fi

# --- 2. venv + package -----------------------------------------------------
say "Python virtual environment + dependencies"
PY="$(command -v python3 || command -v python)"
if [ ! -x ".venv/bin/python" ]; then "$PY" -m venv .venv && good "created .venv"; else good ".venv already present"; fi
./.venv/bin/python -m pip install --upgrade pip -q
./.venv/bin/python -m pip install -e ".[dev,video,crawl,publish,real]" -q
good "installed carshorts with all extras"

# --- 3. daily cron (the heartbeat) -----------------------------------------
# On Unix, cron is the portable scheduler. macOS launchd is an alternative but
# cron works on both. The heartbeat NEVER publishes.
if [ "$SKIP_CRON" = "0" ]; then
  say "Daily cron jobs"
  HH="${HEARTBEAT_TIME%%:*}"; MM="${HEARTBEAT_TIME##*:}"; HH2=$(( (10#$HH + 1) % 24 ))
  VENV="$REPO/.venv/bin/python"; LOGDIR="$REPO/data/logs"; mkdir -p "$LOGDIR"
  HB="cd '$REPO' && PYTHONUTF8=1 $VENV -m carshorts.heartbeat >> '$LOGDIR/heartbeat.log' 2>&1"
  RW="cd '$REPO' && PYTHONUTF8=1 $VENV -m carshorts.retention_watch >> '$LOGDIR/retention_watch.log' 2>&1"
  CRON="$(crontab -l 2>/dev/null | grep -v 'carshorts.heartbeat' | grep -v 'carshorts.retention_watch' || true)"
  { printf '%s\n' "$CRON"; \
    printf '%s %s * * * %s # carshorts.heartbeat\n' "$MM" "$HH" "$HB"; \
    printf '%s %s * * * %s # carshorts.retention_watch\n' "$MM" "$HH2" "$RW"; } | crontab - \
    && good "cron: heartbeat $HEARTBEAT_TIME, retention_watch ${HH2}:${MM}" \
    || warn "could not write crontab - add the two jobs above by hand (crontab -e)"
else
  say "Skipping cron (--skip-cron)"
fi

# --- 4. smoke test ---------------------------------------------------------
say "Smoke test (ruff + pytest, offline)"
if ./.venv/bin/python -m ruff check . >/dev/null 2>&1; then good "ruff clean"; else warn "ruff reported issues (run: ./.venv/bin/ruff check .)"; fi
if ./.venv/bin/python -m pytest -q >/tmp/carshorts_pytest.txt 2>&1; then good "pytest green ($(tail -1 /tmp/carshorts_pytest.txt))"; else warn "pytest failed - see /tmp/carshorts_pytest.txt (ensure ffmpeg on PATH)"; fi

# --- 5. what only you can do -----------------------------------------------
[ -f .env ]               || TODO+=("Create .env (copy .env.example): GROQ_API_KEY, GEMINI_API_KEY, PEXELS_API_KEY. Add ANTHROPIC_API_KEY to enable agents.")
[ -f client_secret.json ] || TODO+=("Add client_secret.json + youtube_token.json for uploads/analytics (Google OAuth - see publish.py).")
[ -d assets/cars ]        || TODO+=("Populate assets/ (curated car pools, fonts, music) - the render pool is otherwise empty.")
if have claude && claude -p "PONG" --output-format json --max-turns 1 2>&1 | grep -q "Not logged in"; then
  TODO+=("Authenticate claude ('claude' then /login) OR set ANTHROPIC_API_KEY, to enable the scriptwright/curator agents.")
fi

say "SUMMARY"
printf '  %s step(s) ok, %s warning(s)\n' "${#OK[@]}" "${#WARN[@]}"
for w in "${WARN[@]:-}"; do [ -n "$w" ] && printf '  ! %s\n' "$w"; done
if [ "${#TODO[@]}" -gt 0 ]; then
  printf '\n  YOUR TO-DO (only you can do these):\n'
  for t in "${TODO[@]}"; do printf '   - %s\n' "$t"; done
fi
printf '\n  Verify state:  ./.venv/bin/python -m carshorts.heartbeat --status\n'
printf '  Review portal: ./.venv/bin/python -m carshorts.portal   (http://localhost:8787)\n\n'
exit 0
