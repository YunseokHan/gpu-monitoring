#!/usr/bin/env bash
#
# Deploy the agent to every remote node in one command, from the hub machine.
#
#   bash deploy/deploy-remote.sh
#
# For each host it clones (or fast-forwards) the repo into REMOTE_DIR and runs
# deploy/install-agent.sh there. Re-running it is the upgrade path.
#
# Configuration, all overridable by environment variable:
#
#   HOSTS       ssh targets, space separated
#   REMOTE_DIR  where to clone on each node        (default /home/jovyan/gpu-monitoring)
#   REPO        git URL to clone                   (default this repo's origin)
#   BRANCH      branch to deploy                   (default main)
#   HUB_URL     hub base URL the agents report to  (default: the live tunnel URL)
#   TOKEN       hub agent token                    (default: read from the hub state dir)
#   INDEX_BASE  node number of the first host      (default 1; the hub node is 0)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${GPU_HUB_RUN_DIR:-$ROOT/.run}"
STATE_DIR="${GPU_HUB_STATE_DIR:-$ROOT/.state}"

HOSTS="${HOSTS:-kakao-b200-gpu-0 kakao-b200-gpu-1 kakao-b200-gpu-2 kakao-b200-gpu-3}"
REMOTE_DIR="${REMOTE_DIR:-/home/jovyan/gpu-monitoring}"
REPO="${REPO:-$(git -C "$ROOT" remote get-url origin 2>/dev/null || echo '')}"
BRANCH="${BRANCH:-main}"
HUB_URL="${HUB_URL:-$(cat "$RUN_DIR/tunnel.url" 2>/dev/null || echo '')}"
TOKEN="${TOKEN:-$(cat "$STATE_DIR/agent_token" 2>/dev/null || echo '')}"
INDEX_BASE="${INDEX_BASE:-1}"
EXTRA_ARGS="${EXTRA_ARGS:-}"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror\033[0m %s\n' "$*" >&2; exit 1; }

[ -n "$REPO" ] || die "no REPO configured and this checkout has no origin remote"
[ -n "$HUB_URL" ] || die "no HUB_URL; start the tunnel first (deploy/tunnel.sh start) or set HUB_URL"
[ -n "$TOKEN" ] || die "no TOKEN; start the hub first (deploy/hubctl.sh start) or set TOKEN"

say "repo      $REPO ($BRANCH)"
say "hub       $HUB_URL"
say "hosts     $HOSTS"
echo

index=$INDEX_BASE
failed=""
for host in $HOSTS; do
  say "[$host] deploying as node #$index"
  # shellcheck disable=SC2029  # deliberate: the variables must expand locally
  if ssh -o BatchMode=yes -o ConnectTimeout=20 "$host" "
      set -e
      if [ -d '$REMOTE_DIR/.git' ]; then
        cd '$REMOTE_DIR'
        git remote set-url origin '$REPO'
        git fetch --quiet origin '$BRANCH'
        git checkout --quiet -B '$BRANCH' 'origin/$BRANCH'
      else
        git clone --quiet --branch '$BRANCH' '$REPO' '$REMOTE_DIR'
      fi
      bash '$REMOTE_DIR/deploy/install-agent.sh' \
        --hub-url '$HUB_URL' \
        --token '$TOKEN' \
        --node-index $index \
        $EXTRA_ARGS
    "; then
    echo
  else
    failed="$failed $host"
    printf '\033[1;31m[%s] FAILED\033[0m\n\n' "$host"
  fi
  index=$((index + 1))
done

if [ -n "$failed" ]; then
  die "these hosts failed:$failed"
fi
say "all hosts deployed -- check the dashboard at $HUB_URL"
