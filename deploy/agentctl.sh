#!/usr/bin/env bash
#
#   deploy/agentctl.sh {start|stop|restart|status|logs}
#
# Process control for the node agent, without systemd.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${GPU_AGENT_RUN_DIR:-$ROOT/.run}"
PID_FILE="$RUN_DIR/agent.pid"
LOG_FILE="$RUN_DIR/agent.log"
STOP_FLAG="$RUN_DIR/stopping"
ENV_FILE="$ROOT/deploy/agent.env"
MAX_LOG_BYTES=$((20 * 1024 * 1024))

running_pid() {
  [ -f "$PID_FILE" ] || return 1
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null)"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  echo "$pid"
}

rotate_log() {
  if [ -f "$LOG_FILE" ]; then
    local size
    size="$(wc -c < "$LOG_FILE" 2>/dev/null || echo 0)"
    [ "$size" -gt "$MAX_LOG_BYTES" ] && mv -f "$LOG_FILE" "$LOG_FILE.1"
  fi
}

cmd_start() {
  [ -f "$ENV_FILE" ] || { echo "no $ENV_FILE -- run deploy/install-agent.sh first" >&2; exit 1; }
  if pid="$(running_pid)"; then
    echo "already running (pid $pid)"
    return 0
  fi
  mkdir -p "$RUN_DIR"
  rm -f "$STOP_FLAG"
  rotate_log
  setsid "$ROOT/deploy/_supervise.sh" >> "$LOG_FILE" 2>&1 < /dev/null &
  # The supervisor writes its own pid; give it a moment to do so.
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    sleep 0.3
    pid="$(running_pid)" && { echo "started (pid $pid), logging to $LOG_FILE"; return 0; }
  done
  echo "failed to start -- last lines of $LOG_FILE:" >&2
  tail -20 "$LOG_FILE" >&2 2>/dev/null
  exit 1
}

cmd_stop() {
  pid="$(running_pid)" || { echo "not running"; rm -f "$PID_FILE"; return 0; }
  mkdir -p "$RUN_DIR"
  touch "$STOP_FLAG"
  # Negative pid == the whole process group: supervisor plus the agent it is running.
  # The agent's SIGTERM handler is what shuts the dummy workers down cleanly.
  kill -TERM -"$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
  for _ in $(seq 1 40); do
    kill -0 "$pid" 2>/dev/null || { echo "stopped"; rm -f "$PID_FILE" "$STOP_FLAG"; return 0; }
    sleep 0.5
  done
  echo "did not exit in 20s, killing" >&2
  kill -KILL -"$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null
  rm -f "$PID_FILE" "$STOP_FLAG"
  echo "killed"
}

cmd_status() {
  if pid="$(running_pid)"; then
    echo "agent: running (pid $pid)"
  else
    echo "agent: stopped"
  fi
  if [ -f "$ENV_FILE" ]; then
    echo "config:"
    grep -E '^GPU_AGENT_(NODE_ID|NODE_INDEX|HUB_URL|INTERVAL|DUMMY_)' "$ENV_FILE" | sed 's/^/  /'
  fi
  echo "dummy workers: $(pgrep -x dummy 2>/dev/null | wc -l)"
  if [ -f "$LOG_FILE" ]; then
    echo "log tail:"
    tail -8 "$LOG_FILE" | sed 's/^/  /'
  fi
}

case "${1:-status}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_stop; cmd_start ;;
  status) cmd_status ;;
  logs) tail -f "$LOG_FILE" ;;
  *) echo "usage: $0 {start|stop|restart|status|logs}" >&2; exit 2 ;;
esac
