"""FastAPI application: ingest from agents, stream to browsers, serve the dashboard."""

from __future__ import annotations

import contextlib
import logging
import secrets
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import config
from .models import ClusterState, DummyControl, IngestResponse, NodeSnapshot
from .state import Store
from .stream import Broadcaster

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

store = Store(config)
broadcaster = Broadcaster(store, config.stream_interval)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    await broadcaster.start()
    log.info("hub %s listening; state dir %s", __version__, config.state_dir)
    log.info("agent token:   %s", config.agent_token)
    log.info("control token: %s  (embed URL: <base>/?k=%s)", config.control_token, config.control_token)
    try:
        yield
    finally:
        await broadcaster.stop()


app = FastAPI(title="GPU Monitoring Hub", version=__version__, lifespan=lifespan)


@app.middleware("http")
async def embed_headers(request: Request, call_next):
    response = await call_next(request)
    # Notion renders the dashboard inside an iframe, so we must opt in explicitly.
    # frame-ancestors is the modern replacement for X-Frame-Options; we never set the
    # latter, since a stray DENY would break the embed.
    response.headers["Content-Security-Policy"] = f"frame-ancestors {config.frame_ancestors}"
    if "x-frame-options" in response.headers:
        del response.headers["X-Frame-Options"]
    return response


# --------------------------------------------------------------------------- auth


def require_agent(authorization: str = Header(default="")) -> None:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(token, config.agent_token):
        raise HTTPException(status_code=401, detail="invalid agent token")


def require_control(x_control_token: str = Header(default="")) -> None:
    if not secrets.compare_digest(x_control_token, config.control_token):
        raise HTTPException(status_code=401, detail="invalid control token")


# ---------------------------------------------------------------------- api: agent


@app.post("/api/v1/ingest", response_model=IngestResponse, dependencies=[Depends(require_agent)])
async def ingest(snapshot: NodeSnapshot) -> IngestResponse:
    desired = store.ingest(snapshot)
    return IngestResponse(desired_dummy=desired, server_ts=time.time())


# -------------------------------------------------------------------- api: viewers


@app.get("/api/v1/state", response_model=ClusterState)
async def get_state() -> ClusterState:
    return store.cluster_state()


@app.get("/api/v1/stream")
async def stream() -> StreamingResponse:
    return StreamingResponse(
        broadcaster.events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            # Tells nginx (and other buffering proxies) to pass chunks straight through.
            # Note: Cloudflare's edge ignores this and buffers ~128 KiB of any streamed
            # response, which is why the dashboard falls back to polling automatically
            # when frames stop arriving -- see web/src/useStream.ts.
            "X-Accel-Buffering": "no",
        },
    )


# -------------------------------------------------------------------- api: control


@app.post("/api/v1/nodes/{node_id}/dummy", dependencies=[Depends(require_control)])
async def set_dummy(node_id: str, body: DummyControl) -> dict:
    try:
        desired = store.set_dummy(node_id, body.gpu_index, body.enabled)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown node {node_id!r}")
    except IndexError:
        raise HTTPException(status_code=404, detail=f"node {node_id!r} has no GPU {body.gpu_index}")
    log.info("dummy %s: node=%s gpu=%s", "on" if body.enabled else "off", node_id, body.gpu_index)
    return {"node_id": node_id, "desired_dummy": desired}


@app.get("/api/v1/whoami")
async def whoami(x_control_token: str = Header(default="")) -> dict:
    """Lets the dashboard tell the user up front whether its ?k= token can control anything."""
    can_control = bool(x_control_token) and secrets.compare_digest(x_control_token, config.control_token)
    return {"can_control": can_control, "version": __version__}


# ------------------------------------------------------------------------- static

_PLACEHOLDER = """<!doctype html>
<meta charset="utf-8"><title>GPU Monitoring Hub</title>
<body style="font:14px/1.6 ui-monospace,monospace;background:#0b0f16;color:#e6edf3;padding:40px">
<h1>Dashboard not built yet</h1>
<p>The hub is running, but <code>gpu_hub/static/index.html</code> does not exist.</p>
<pre>cd web &amp;&amp; npm install &amp;&amp; npm run build</pre>
<p>The API is live in the meantime:
<a style="color:#7aa2f7" href="/api/v1/state">/api/v1/state</a></p>
</body>"""

if (STATIC_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
else:

    @app.get("/", response_class=HTMLResponse)
    async def placeholder() -> str:
        return _PLACEHOLDER
