# gpu-monitoring

Live GPU dashboard for a multi-node cluster, designed to be embedded in a Notion page.

Shows, for every node and every GPU: the processes running on it (pid, user, command),
used / total VRAM, and utilization. Any GPU that nothing is using can be filled with a
**dummy** process — full VRAM, ~100% utilization, named `dummy` — which steps aside
automatically the moment a real job appears.

```
[node agent] ─┐
[node agent] ─┼── POST /api/v1/ingest (1 Hz) ──▶ [hub] ──SSE──▶ [dashboard]
[node agent] ─┘   ◀── desired dummy state              ▲
                                                       │
                                          Cloudflare Tunnel (HTTPS)
                                                       ▲
                                              Notion /embed iframe
```

## Quick start

On the machine that will host the dashboard (it can also be a GPU node):

```bash
git clone https://github.com/YunseokHan/gpu-monitoring.git
cd gpu-monitoring

bash deploy/install-hub.sh      # builds the dashboard, starts the hub on :8000
bash deploy/tunnel.sh start     # public HTTPS URL via Cloudflare, no ports opened
bash deploy/install-agent.sh \
    --hub-url "$(cat .run/tunnel.url)" \
    --token   "$(cat .state/agent_token)" \
    --node-index 0              # monitor this machine's own GPUs
```

`deploy/hubctl.sh tokens` then prints the URL to paste into Notion.

To add every other node in one command (see [Adding nodes](#adding-nodes)):

```bash
bash deploy/deploy-remote.sh
```

## Putting it in Notion

`deploy/hubctl.sh tokens` prints two URLs:

| URL | Who to give it to |
|---|---|
| `https://…/` | anyone — read-only, the dummy switches are disabled |
| `https://…/?k=<control token>` | people allowed to turn dummies on and off |

In Notion: type `/embed`, choose **Create embed**, paste the URL, then drag the bottom
edge to size it. Details and the fixed-domain setup are in
[deploy/NOTION.md](deploy/NOTION.md).

Add `&theme=dark` or `&theme=light` to pin the theme — an iframe cannot see which theme
the surrounding Notion page is using, so by default it follows the viewer's OS setting.

> **A quick tunnel's hostname changes every time it restarts.** The remote agents have
> that hostname baked into `deploy/agent.env`, so after `deploy/tunnel.sh restart` you
> must re-paste the URL into Notion *and* re-run `deploy/deploy-remote.sh`. Set up a
> named tunnel with a domain you control ([deploy/NOTION.md](deploy/NOTION.md)) and
> neither is ever needed again.

## The dummy process

A dummy occupies a GPU so it *looks* busy — useful for holding a card, or for keeping a
node warm. It is a real process, so `nvidia-smi` shows it like any other:

```
|    7   N/A  N/A   1082486      C   dummy                          79096MiB |
```

**It only ever occupies an idle GPU.** Every tick the agent checks which processes are on
the card; if anything that is not a dummy appears, the dummy is stopped immediately and
the VRAM released. It comes back once the GPU has been quiet for `--cooldown` seconds
(30 by default), which keeps it from stealing the card back in between the restarts of a
crash-looping job.

Turning the switch on therefore means *"use this GPU when nobody else is"*, not *"reserve
this GPU"*. The dashboard distinguishes the two states: **dummy holding this GPU** vs
**dummy on · yielded to a real job**.

### The one risk worth knowing about

Detection is not instantaneous, so there is a window where an incoming job's allocation
can fail. What saves it in practice is that creating a CUDA context takes a second or
two on its own, and the process becomes visible to NVML at the *start* of that — which is
usually enough time for the agent to notice and get out of the way.

Measured on a B200 node (183 GB cards, dummy holding ~181 GB, 1 s tick):

| Incoming job | Result |
|---|---|
| context, ~5 s of setup, then 10 GB | allocated at t+6.8 s — fine |
| context then 10 GB immediately, ×3 | allocated at t+1.8 s — fine all three times |
| context then **150 GB** immediately | `OutOfMemoryError` at t+1.7 s |
| the same 150 GB job, retried at once | allocated at t+2.2 s — fine |

So a normal job is unaffected, and a job that asks for most of the card in the same
instant its context comes up can lose one attempt and then succeed. If that is still too
much for a shared node, raise `--headroom-mb` or lower `--interval` to 0.5.

### How it holds the GPU

The worker talks to the CUDA driver API directly through `ctypes`, so it needs nothing but
`libcuda.so.1` — no CUDA toolkit, no PyTorch, no pip packages on the node. Utilization
comes from a pre-compiled PTX kernel (`agent/gpu_agent/dummy_worker/kernel.ptx`) that the
driver JIT-compiles for whatever GPU it lands on. A `torch` backend is used as a fallback
if that path ever fails (`--backend torch` forces it).

The process is named `dummy` because the agent starts it with `argv[0] = "dummy"` and the
worker calls `prctl(PR_SET_NAME)`, so `nvidia-smi`, `ps` and the dashboard all agree.
`prctl(PR_SET_PDEATHSIG)` makes the kernel kill it if the agent ever dies unexpectedly, and
the agent reaps any orphan it finds at startup — a dummy can never be left holding a card
with nothing able to stop it.

## Adding nodes

`deploy/deploy-remote.sh` clones the repo onto each host and runs the installer:

```bash
HOSTS="gpu-a gpu-b gpu-c" \
REMOTE_DIR=/home/jovyan/gpu-monitoring \
bash deploy/deploy-remote.sh
```

Defaults come from the local checkout: `REPO` from `git remote origin`, `HUB_URL` from the
running tunnel, `TOKEN` from the hub's state directory. Node numbers are assigned in order
starting at `INDEX_BASE` (1 by default, leaving 0 for the hub machine).

Nothing has to be configured on the hub side — a new agent simply starts reporting and
appears on the dashboard. Nodes that stop reporting are shown greyed out as `stale`
(> 5 s) then `offline` (> 30 s) rather than silently vanishing.

The agent needs Python ≥ 3.9 and, ideally, `nvidia-ml-py` (the installer handles it). If
that cannot be installed it falls back to parsing `nvidia-smi`, and it does not use
systemd — the supervisor is a plain `setsid` loop, so it works in containers where PID 1 is
something like s6.

## Operating it

| | |
|---|---|
| `deploy/hubctl.sh {start\|stop\|restart\|status\|logs\|tokens}` | the hub |
| `deploy/agentctl.sh {start\|stop\|restart\|status\|logs}` | the agent, on a node |
| `deploy/tunnel.sh {start\|stop\|status\|url}` | the Cloudflare tunnel |
| `deploy/deploy-remote.sh` | install/upgrade every remote agent |

Logs and pidfiles live in `.run/`; the hub's tokens and the persisted dummy settings live
in `.state/`. Turning a dummy on survives a hub restart — the desired state is written to
`.state/desired_dummy.json`, and agents keep reconciling towards the last instruction they
received even while the hub is unreachable.

## Layout

```
hub/     FastAPI: ingest from agents, SSE to browsers, serves the dashboard
agent/   per-node collector (NVML) + dummy process manager
web/     React + Vite + Tailwind dashboard, built into hub/gpu_hub/static/
deploy/  install and control scripts
```

Development: `deploy/hubctl.sh start`, then `cd web && npm run dev` (Vite proxies `/api`
to the hub on port 8000).

## Configuration

Agent — `deploy/agent.env`, written by the installer:

| Variable | Default | |
|---|---|---|
| `GPU_AGENT_HUB_URL` | — | hub base URL |
| `GPU_AGENT_TOKEN` | — | agent token |
| `GPU_AGENT_NODE_ID` | hostname | stable node identifier |
| `GPU_AGENT_NODE_INDEX` | 0 | node number shown in the UI |
| `GPU_AGENT_INTERVAL` | 1.0 | seconds per tick |
| `GPU_AGENT_DUMMY_HEADROOM_MB` | 2048 | VRAM the dummy leaves free |
| `GPU_AGENT_DUMMY_COOLDOWN` | 30 | quiet seconds before re-occupying a freed GPU |
| `GPU_AGENT_DUMMY_BACKEND` | auto | `auto`, `cuda` or `torch` |

Hub — `deploy/hub.env`, optional:

| Variable | Default | |
|---|---|---|
| `GPU_HUB_HOST` / `GPU_HUB_PORT` | 127.0.0.1 / 8000 | bind address |
| `GPU_HUB_AGENT_TOKEN` | generated once | shared with the agents |
| `GPU_HUB_CONTROL_TOKEN` | generated once | the `?k=` value |
| `GPU_HUB_FRAME_ANCESTORS` | Notion domains | CSP for embedding elsewhere |
| `GPU_HUB_STALE_AFTER` / `GPU_HUB_OFFLINE_AFTER` | 5 / 30 | liveness thresholds |
