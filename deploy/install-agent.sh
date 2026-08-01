#!/usr/bin/env bash
#
# One-command agent install for a GPU node.
#
#   bash deploy/install-agent.sh --hub-url https://gpu.example.com --token <agent token>
#
# Creates a virtualenv, installs the single dependency, writes deploy/agent.env and
# starts the agent under a supervisor. Safe to re-run: it is the upgrade path too.
#
# Deliberately does NOT use systemd. The nodes this targets are containers where PID 1
# is a supervisor like s6, so `systemctl` exists but cannot talk to a bus.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/deploy/agent.env"
VENV="$ROOT/agent/.venv"

HUB_URL="${GPU_AGENT_HUB_URL:-}"
TOKEN="${GPU_AGENT_TOKEN:-}"
NODE_ID="${GPU_AGENT_NODE_ID:-$(hostname)}"
NODE_INDEX="${GPU_AGENT_NODE_INDEX:-0}"
INTERVAL="${GPU_AGENT_INTERVAL:-1.0}"
HEADROOM_MB="${GPU_AGENT_DUMMY_HEADROOM_MB:-2048}"
COOLDOWN="${GPU_AGENT_DUMMY_COOLDOWN:-30}"
BACKEND="${GPU_AGENT_DUMMY_BACKEND:-auto}"
INSECURE="${GPU_AGENT_INSECURE:-0}"
START=1

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m warn\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31merror\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  cat <<'EOF'

Options:
  --hub-url URL        hub base URL, e.g. https://gpu.example.com   (required)
  --token TOKEN        hub agent token                              (required)
  --node-id NAME       stable node identifier      (default: hostname)
  --node-index N       node number shown in the UI (default: 0)
  --interval SEC       poll interval               (default: 1.0)
  --headroom-mb MB     VRAM the dummy leaves free  (default: 2048)
  --cooldown SEC       quiet period before re-occupying a freed GPU (default: 30)
  --backend NAME       dummy backend: auto|cuda|torch (default: auto)
  --insecure           skip TLS verification when talking to the hub
  --no-start           install and configure only, do not start
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --hub-url) HUB_URL="$2"; shift 2 ;;
    --token) TOKEN="$2"; shift 2 ;;
    --node-id) NODE_ID="$2"; shift 2 ;;
    --node-index) NODE_INDEX="$2"; shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    --headroom-mb) HEADROOM_MB="$2"; shift 2 ;;
    --cooldown) COOLDOWN="$2"; shift 2 ;;
    --backend) BACKEND="$2"; shift 2 ;;
    --insecure) INSECURE=1; shift ;;
    --no-start) START=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1 (try --help)" ;;
  esac
done

[ -n "$HUB_URL" ] || { usage; die "--hub-url is required"; }
[ -n "$TOKEN" ] || { usage; die "--token is required"; }

say "installing the GPU agent for node '$NODE_ID' (#$NODE_INDEX)"

# --------------------------------------------------------------------- interpreter

PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    PY="$(command -v "$candidate")"
    break
  fi
done
[ -n "$PY" ] || die "no Python >= 3.9 found on this node"
say "using interpreter $PY ($("$PY" --version 2>&1))"

command -v nvidia-smi >/dev/null 2>&1 || warn "nvidia-smi not found; the agent will report no GPUs"

# ------------------------------------------------------------------------- venv

# Three ways to get an isolated interpreter, in order of how universally they work.
# If all of them fail the agent still runs: it falls back to parsing nvidia-smi.
AGENT_PY=""
if "$PY" -m venv "$VENV" >/dev/null 2>&1; then
  AGENT_PY="$VENV/bin/python"
  say "virtualenv ready at $VENV"
elif command -v uv >/dev/null 2>&1 && uv venv --python "$PY" "$VENV" >/dev/null 2>&1; then
  AGENT_PY="$VENV/bin/python"
  say "virtualenv ready at $VENV (via uv)"
else
  warn "could not create a virtualenv; using $PY directly"
  AGENT_PY="$PY"
fi

install_dep() {
  if [ "$AGENT_PY" = "$VENV/bin/python" ]; then
    if command -v uv >/dev/null 2>&1; then
      uv pip install --python "$AGENT_PY" --quiet nvidia-ml-py && return 0
    fi
    "$AGENT_PY" -m pip install --quiet --disable-pip-version-check nvidia-ml-py && return 0
  else
    "$AGENT_PY" -m pip install --quiet --disable-pip-version-check --user nvidia-ml-py && return 0
  fi
  return 1
}

if "$AGENT_PY" -c 'import pynvml' 2>/dev/null; then
  say "nvidia-ml-py already available"
elif install_dep && "$AGENT_PY" -c 'import pynvml' 2>/dev/null; then
  say "installed nvidia-ml-py"
else
  warn "could not install nvidia-ml-py; the agent will fall back to parsing nvidia-smi"
fi

# ------------------------------------------------------------------------ config

umask 077
cat > "$ENV_FILE" <<EOF
# Written by deploy/install-agent.sh -- re-run it to change these.
GPU_AGENT_PYTHON=$AGENT_PY
GPU_AGENT_HUB_URL=$HUB_URL
GPU_AGENT_TOKEN=$TOKEN
GPU_AGENT_NODE_ID=$NODE_ID
GPU_AGENT_NODE_INDEX=$NODE_INDEX
GPU_AGENT_INTERVAL=$INTERVAL
GPU_AGENT_DUMMY_HEADROOM_MB=$HEADROOM_MB
GPU_AGENT_DUMMY_COOLDOWN=$COOLDOWN
GPU_AGENT_DUMMY_BACKEND=$BACKEND
GPU_AGENT_INSECURE=$INSECURE
GPU_AGENT_LOG_LEVEL=INFO
EOF
umask 022
say "wrote $ENV_FILE"

chmod +x "$ROOT/deploy/agentctl.sh" "$ROOT/deploy/_supervise.sh" 2>/dev/null || true

# ------------------------------------------------------------------------- start

if [ "$START" = "1" ]; then
  "$ROOT/deploy/agentctl.sh" restart
  sleep 3
  "$ROOT/deploy/agentctl.sh" status
else
  say "skipping start (--no-start); run deploy/agentctl.sh start when ready"
fi
