#!/usr/bin/env bash
#
# Update this node's agent to the latest code, in one command:
#
#   bash deploy/update-agent.sh
#
# For nodes the hub cannot reach over SSH -- behind a VPN, in another network -- and so
# cannot be reached by deploy/deploy-remote.sh. Run it on the node itself.
#
# Settings are reused from deploy/agent.env, so no arguments are needed. Pass any
# install-agent.sh option to change one, e.g. --hub-url after the tunnel hostname moved.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="${BRANCH:-main}"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

[ -f "$ROOT/deploy/agent.env" ] || {
  printf '\033[1;31merror\033[0m no deploy/agent.env -- run deploy/install-agent.sh first\n' >&2
  exit 1
}

say "updating $ROOT to origin/$BRANCH"
git -C "$ROOT" fetch --quiet origin "$BRANCH"
before="$(git -C "$ROOT" rev-parse --short HEAD)"
git -C "$ROOT" checkout --quiet -B "$BRANCH" "origin/$BRANCH"
after="$(git -C "$ROOT" rev-parse --short HEAD)"

if [ "$before" = "$after" ]; then
  say "already at $after"
else
  say "$before -> $after"
fi

bash "$ROOT/deploy/install-agent.sh" "$@"
