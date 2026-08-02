"""Wire format shared between the node agents, the hub and the dashboard.

The agent has no pydantic dependency, so it builds these as plain dicts. Keep the
field names here in sync with agent/gpu_agent/collector.py.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ProcInfo(BaseModel):
    pid: int
    name: str
    cmdline: str = ""
    user: str = ""
    used_mem_mb: Optional[int] = None
    kind: Literal["C", "G"] = "C"
    is_dummy: bool = False


class GpuSnapshot(BaseModel):
    index: int
    uuid: str = ""
    name: str = ""
    mem_used_mb: int = 0
    mem_total_mb: int = 0
    util_gpu: Optional[int] = None
    util_mem: Optional[int] = None
    temp_c: Optional[int] = None
    power_w: Optional[float] = None
    power_limit_w: Optional[float] = None
    processes: list[ProcInfo] = Field(default_factory=list)

    # Reported by the agent: is our dummy process actually running on this GPU right now?
    dummy_active: bool = False
    dummy_pid: Optional[int] = None
    # Which backend the worker settled on ("cuda" or "torch"), and the reason none worked.
    dummy_backend: Optional[str] = None
    dummy_error: Optional[str] = None
    # Filled in by the hub from its desired state, not by the agent.
    dummy_enabled: bool = False


class NodeSnapshot(BaseModel):
    """One agent's report for one tick."""

    node_id: str
    node_index: int = 0
    # Nodes reporting the same cluster name are drawn inside one card on the dashboard.
    cluster: str = ""
    hostname: str = ""
    ts: float = 0.0
    agent_version: str = ""
    driver_version: Optional[str] = None
    cuda_version: Optional[str] = None
    gpus: list[GpuSnapshot] = Field(default_factory=list)
    # Non-fatal collector problem (e.g. NVML unavailable, fell back to nvidia-smi).
    error: Optional[str] = None


class NodeView(NodeSnapshot):
    """A node snapshot decorated with liveness, as sent to the dashboard."""

    status: Literal["online", "stale", "offline"] = "online"
    age_s: float = 0.0


class ClusterState(BaseModel):
    ts: float
    nodes: list[NodeView] = Field(default_factory=list)


class IngestResponse(BaseModel):
    """Desired dummy state echoed back to the agent on every ingest.

    Keys are GPU indices as strings (JSON object keys). The agent reconciles towards
    this on each tick, so a lost response simply means a one-tick delay.
    """

    desired_dummy: dict[str, bool] = Field(default_factory=dict)
    server_ts: float = 0.0


class DummyControl(BaseModel):
    """Dashboard -> hub. gpu_index=None means "every GPU on this node"."""

    gpu_index: Optional[int] = None
    enabled: bool
