"""Hub configuration, all via ``GPU_HUB_*`` environment variables."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return default if raw is None or raw == "" else float(raw)


def _default_state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return Path(base) / "gpu-monitoring"


@dataclass
class Config:
    host: str = field(default_factory=lambda: os.environ.get("GPU_HUB_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.environ.get("GPU_HUB_PORT", "8000")))
    state_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("GPU_HUB_STATE_DIR") or _default_state_dir())
    )

    # How often the SSE ticker pushes a fresh cluster snapshot to connected browsers.
    stream_interval: float = field(default_factory=lambda: _env_float("GPU_HUB_STREAM_INTERVAL", 1.0))
    # Liveness thresholds, measured from the last ingest for a node.
    stale_after: float = field(default_factory=lambda: _env_float("GPU_HUB_STALE_AFTER", 5.0))
    offline_after: float = field(default_factory=lambda: _env_float("GPU_HUB_OFFLINE_AFTER", 30.0))
    # Nodes that have not reported for this long are dropped from the dashboard entirely.
    forget_after: float = field(default_factory=lambda: _env_float("GPU_HUB_FORGET_AFTER", 86400.0))

    # Notion serves pages from notion.so and published sites from notion.site.
    frame_ancestors: str = field(
        default_factory=lambda: os.environ.get(
            "GPU_HUB_FRAME_ANCESTORS",
            "'self' https://*.notion.so https://*.notion.site https://notion.so",
        )
    )

    agent_token: str = ""
    control_token: str = ""

    def __post_init__(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.agent_token = self._resolve_token("GPU_HUB_AGENT_TOKEN", "agent_token")
        self.control_token = self._resolve_token("GPU_HUB_CONTROL_TOKEN", "control_token")

    def _resolve_token(self, env_name: str, filename: str) -> str:
        """Use the env var if set, otherwise mint a token once and reuse it forever.

        Persisting the generated token matters: the agents and the Notion embed URL both
        bake it in, so it must survive a hub restart.
        """
        from_env = os.environ.get(env_name)
        if from_env:
            return from_env

        path = self.state_dir / filename
        if path.exists():
            token = path.read_text().strip()
            if token:
                return token

        token = secrets.token_urlsafe(24)
        path.write_text(token + "\n")
        path.chmod(0o600)
        return token

    @property
    def desired_state_file(self) -> Path:
        return self.state_dir / "desired_dummy.json"


config = Config()
