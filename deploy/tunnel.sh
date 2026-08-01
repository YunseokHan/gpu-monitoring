#!/usr/bin/env bash
#
#   deploy/tunnel.sh {start|stop|status|url}
#
# Exposes the hub over HTTPS with a Cloudflare quick tunnel, downloading cloudflared to
# .run/ if it is not installed. Only outbound connections are made -- no port needs to be
# opened and no inbound firewall rule is required.
#
# The generated https://<random>.trycloudflare.com URL is what both Notion's iframe and
# the remote agents talk to. It changes every restart; for a stable address create a
# named tunnel (see deploy/NOTION.md).

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${GPU_HUB_RUN_DIR:-$ROOT/.run}"
BIN="$RUN_DIR/cloudflared"
PID_FILE="$RUN_DIR/tunnel.pid"
LOG_FILE="$RUN_DIR/tunnel.log"
URL_FILE="$RUN_DIR/tunnel.url"
PORT="${GPU_HUB_PORT:-8000}"

mkdir -p "$RUN_DIR"

running_pid() {
  [ -f "$PID_FILE" ] || return 1
  local pid; pid="$(cat "$PID_FILE" 2>/dev/null)"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && echo "$pid"
}

ensure_binary() {
  if command -v cloudflared >/dev/null 2>&1; then
    BIN="$(command -v cloudflared)"
    return
  fi
  if [ -x "$BIN" ]; then return; fi
  local arch
  case "$(uname -m)" in
    x86_64) arch=amd64 ;;
    aarch64|arm64) arch=arm64 ;;
    *) echo "unsupported architecture $(uname -m)" >&2; exit 1 ;;
  esac
  echo "downloading cloudflared ($arch)..."
  curl -fsSL -o "$BIN" \
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$arch"
  chmod +x "$BIN"
}

cmd_start() {
  if pid="$(running_pid)"; then echo "already running (pid $pid)"; cmd_url; return 0; fi
  ensure_binary
  rm -f "$URL_FILE" "$LOG_FILE"
  setsid "$BIN" tunnel --no-autoupdate --url "http://127.0.0.1:$PORT" \
    >> "$LOG_FILE" 2>&1 < /dev/null &
  echo $! > "$PID_FILE"

  echo -n "waiting for the tunnel URL"
  for _ in $(seq 1 60); do
    sleep 1
    url="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG_FILE" 2>/dev/null | head -1)"
    if [ -n "$url" ]; then
      echo "$url" > "$URL_FILE"
      echo
      echo "tunnel up: $url"
      return 0
    fi
    echo -n "."
  done
  echo
  echo "no URL after 60s -- see $LOG_FILE" >&2
  exit 1
}

cmd_stop() {
  pid="$(running_pid)" || { echo "not running"; rm -f "$PID_FILE"; return 0; }
  kill -TERM "$pid" 2>/dev/null
  sleep 1
  kill -KILL "$pid" 2>/dev/null
  rm -f "$PID_FILE" "$URL_FILE"
  echo "stopped"
}

cmd_url() { cat "$URL_FILE" 2>/dev/null || { echo "no tunnel URL yet" >&2; exit 1; }; }

case "${1:-status}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_stop; cmd_start ;;
  url) cmd_url ;;
  status)
    if pid="$(running_pid)"; then echo "tunnel: running (pid $pid) -> $(cat "$URL_FILE" 2>/dev/null)"; else echo "tunnel: stopped"; fi ;;
  *) echo "usage: $0 {start|stop|restart|status|url}" >&2; exit 2 ;;
esac
