"""Agent configuration: environment variables, overridable by CLI flags.

Deliberately dependency-free -- the agent is copied onto arbitrary GPU nodes, some of
which are containers with an old Python and no build toolchain.
"""

from __future__ import annotations

import argparse
import os
import socket
from dataclasses import dataclass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return default if raw is None or raw == "" else float(raw)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return default if raw is None or raw == "" else int(raw)


@dataclass
class Config:
    hub_url: str
    token: str
    node_id: str
    node_index: int
    hostname: str
    interval: float
    timeout: float
    dummy_headroom_mb: int
    dummy_chunk_mb: int
    dummy_cooldown: float
    dummy_backend: str
    dummy_target_util: bool
    log_level: str
    insecure: bool

    @property
    def ingest_url(self) -> str:
        return self.hub_url.rstrip("/") + "/api/v1/ingest"


def load_config(argv: list[str] | None = None) -> Config:
    hostname = socket.gethostname()

    parser = argparse.ArgumentParser(prog="gpu-agent", description="GPU monitoring node agent")
    parser.add_argument("--hub-url", default=_env("GPU_AGENT_HUB_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--token", default=_env("GPU_AGENT_TOKEN"))
    parser.add_argument("--node-id", default=_env("GPU_AGENT_NODE_ID") or hostname)
    parser.add_argument("--node-index", type=int, default=_env_int("GPU_AGENT_NODE_INDEX", 0))
    parser.add_argument("--interval", type=float, default=_env_float("GPU_AGENT_INTERVAL", 1.0))
    parser.add_argument("--timeout", type=float, default=_env_float("GPU_AGENT_TIMEOUT", 10.0))
    parser.add_argument(
        "--dummy-headroom-mb",
        type=int,
        default=_env_int("GPU_AGENT_DUMMY_HEADROOM_MB", 2048),
        help="VRAM the dummy leaves free so an incoming real job can create its context "
             "before we have noticed it and stepped aside",
    )
    parser.add_argument("--dummy-chunk-mb", type=int, default=_env_int("GPU_AGENT_DUMMY_CHUNK_MB", 256))
    parser.add_argument(
        "--dummy-cooldown",
        type=float,
        default=_env_float("GPU_AGENT_DUMMY_COOLDOWN", 30.0),
        help="after yielding a GPU to a real process, wait this long before re-occupying it",
    )
    parser.add_argument(
        "--dummy-backend",
        default=_env("GPU_AGENT_DUMMY_BACKEND", "auto"),
        choices=["auto", "cuda", "torch"],
        help="auto: raw CUDA driver API via ctypes, falling back to torch",
    )
    parser.add_argument(
        "--dummy-no-util",
        action="store_true",
        default=os.environ.get("GPU_AGENT_DUMMY_NO_UTIL", "") not in ("", "0", "false"),
        help="hold VRAM only, do not burn compute",
    )
    parser.add_argument("--log-level", default=_env("GPU_AGENT_LOG_LEVEL", "INFO"))
    parser.add_argument(
        "--insecure",
        action="store_true",
        default=_env("GPU_AGENT_INSECURE", "") not in ("", "0", "false"),
        help="skip TLS certificate verification when talking to the hub",
    )
    args = parser.parse_args(argv)

    return Config(
        hub_url=args.hub_url,
        token=args.token,
        node_id=args.node_id,
        node_index=args.node_index,
        hostname=hostname,
        interval=args.interval,
        timeout=args.timeout,
        dummy_headroom_mb=args.dummy_headroom_mb,
        dummy_chunk_mb=args.dummy_chunk_mb,
        dummy_cooldown=args.dummy_cooldown,
        dummy_backend=args.dummy_backend,
        dummy_target_util=not args.dummy_no_util,
        log_level=args.log_level.upper(),
        insecure=args.insecure,
    )
