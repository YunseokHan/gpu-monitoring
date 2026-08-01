#!/usr/bin/env bash
#
# Restart-on-exit wrapper for the agent. Started by agentctl.sh under `setsid`, so it
# leads its own process group and agentctl can signal the whole group at once.
#
# This exists because the target nodes are containers without a usable systemd; it is
# the smallest thing that gives "keep it running, and stop cleanly when told to".

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${GPU_AGENT_RUN_DIR:-$ROOT/.run}"
STOP_FLAG="$RUN_DIR/stopping"

mkdir -p "$RUN_DIR"
echo $$ > "$RUN_DIR/agent.pid"

set -a
# shellcheck disable=SC1090
. "$ROOT/deploy/agent.env"
set +a

PY="${GPU_AGENT_PYTHON:-python3}"
export PYTHONPATH="$ROOT/agent${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

trap 'touch "$STOP_FLAG"' TERM INT

while true; do
  echo "--- $(date '+%Y-%m-%d %H:%M:%S') starting agent ---"
  "$PY" -m gpu_agent
  rc=$?
  if [ -e "$STOP_FLAG" ]; then
    echo "--- $(date '+%Y-%m-%d %H:%M:%S') agent stopped (rc=$rc), not restarting ---"
    break
  fi
  echo "--- $(date '+%Y-%m-%d %H:%M:%S') agent exited rc=$rc, restarting in 5s ---"
  sleep 5
done

rm -f "$RUN_DIR/agent.pid"
