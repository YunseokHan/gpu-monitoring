#!/usr/bin/env bash
#
#   deploy/hubctl.sh {start|stop|restart|status|logs|tokens}
#
# Process control for the hub. Configuration comes from deploy/hub.env if present.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${GPU_HUB_RUN_DIR:-$ROOT/.run}"
PID_FILE="$RUN_DIR/hub.pid"
LOG_FILE="$RUN_DIR/hub.log"
ENV_FILE="$ROOT/deploy/hub.env"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

export GPU_HUB_HOST="${GPU_HUB_HOST:-127.0.0.1}"
export GPU_HUB_PORT="${GPU_HUB_PORT:-8000}"
export GPU_HUB_STATE_DIR="${GPU_HUB_STATE_DIR:-$ROOT/.state}"

running_pid() {
  [ -f "$PID_FILE" ] || return 1
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null)"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  echo "$pid"
}

cmd_start() {
  if pid="$(running_pid)"; then echo "already running (pid $pid)"; return 0; fi
  mkdir -p "$RUN_DIR" "$GPU_HUB_STATE_DIR"
  setsid "$ROOT/hub/.venv/bin/python" -m gpu_hub >> "$LOG_FILE" 2>&1 < /dev/null &
  echo $! > "$PID_FILE"
  sleep 1.5
  if pid="$(running_pid)"; then
    echo "hub started (pid $pid) on http://$GPU_HUB_HOST:$GPU_HUB_PORT"
  else
    echo "failed to start -- last lines of $LOG_FILE:" >&2
    tail -20 "$LOG_FILE" >&2
    exit 1
  fi
}

cmd_stop() {
  pid="$(running_pid)" || { echo "not running"; rm -f "$PID_FILE"; return 0; }
  kill -TERM "$pid" 2>/dev/null
  for _ in $(seq 1 20); do
    kill -0 "$pid" 2>/dev/null || { echo "stopped"; rm -f "$PID_FILE"; return 0; }
    sleep 0.5
  done
  kill -KILL "$pid" 2>/dev/null
  rm -f "$PID_FILE"
  echo "killed"
}

cmd_tokens() {
  local dir="$GPU_HUB_STATE_DIR"
  local agent control url
  agent="$(cat "$dir/agent_token" 2>/dev/null || echo '<hub has not started yet>')"
  control="$(cat "$dir/control_token" 2>/dev/null || echo '<hub has not started yet>')"
  url="$(cat "$RUN_DIR/tunnel.url" 2>/dev/null || echo "http://$GPU_HUB_HOST:$GPU_HUB_PORT")"
  cat <<EOF

  agent token   : $agent
      (deploy/deploy-remote.sh picks this up automatically)

  dashboard     : $url
  Notion embed  : $url/?k=$control
      (the ?k= token is what enables the dummy switches; share the bare URL for read-only)

EOF
}

case "${1:-status}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_stop; cmd_start ;;
  status)
    if pid="$(running_pid)"; then echo "hub: running (pid $pid) on port $GPU_HUB_PORT"; else echo "hub: stopped"; fi
    curl -s --max-time 3 "http://127.0.0.1:$GPU_HUB_PORT/api/v1/state" \
      | head -c 120 | sed 's/^/  state: /' 2>/dev/null || true
    echo
    ;;
  logs) tail -f "$LOG_FILE" ;;
  tokens) cmd_tokens ;;
  *) echo "usage: $0 {start|stop|restart|status|logs|tokens}" >&2; exit 2 ;;
esac
