#!/usr/bin/env bash
#
# One-command hub install: builds the dashboard, creates the venv, starts the hub.
#
#   bash deploy/install-hub.sh
#
# Prints the agent token and the dashboard control URL at the end -- those are what you
# feed to deploy/deploy-remote.sh and paste into Notion.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/hub/.venv"
SKIP_WEB=0
START=1

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m warn\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31merror\033[0m %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --skip-web) SKIP_WEB=1; shift ;;
    --no-start) START=0; shift ;;
    -h|--help) sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$(command -v "$candidate")"
    break
  fi
done
[ -n "$PY" ] || die "no Python >= 3.10 found (the hub needs it for FastAPI)"
say "using interpreter $PY"

# ---------------------------------------------------------------------- dashboard

if [ "$SKIP_WEB" = "0" ]; then
  if command -v npm >/dev/null 2>&1; then
    say "building the dashboard"
    (cd "$ROOT/web" && npm install --silent && npm run build)
  else
    warn "npm not found; skipping the dashboard build (the hub will serve a placeholder)"
  fi
fi

# --------------------------------------------------------------------------- venv

if command -v uv >/dev/null 2>&1; then
  uv venv --python "$PY" "$VENV" >/dev/null
  uv pip install --python "$VENV/bin/python" --quiet -e "$ROOT/hub"
else
  "$PY" -m venv "$VENV"
  "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check -e "$ROOT/hub"
fi
say "hub environment ready at $VENV"

chmod +x "$ROOT/deploy/hubctl.sh" "$ROOT/deploy/tunnel.sh" "$ROOT/deploy/deploy-remote.sh" 2>/dev/null || true

if [ "$START" = "1" ]; then
  "$ROOT/deploy/hubctl.sh" restart
  sleep 2
  "$ROOT/deploy/hubctl.sh" tokens
fi
