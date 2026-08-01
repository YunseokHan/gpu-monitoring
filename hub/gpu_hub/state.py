"""In-memory cluster state plus the persisted desired dummy configuration.

Everything here is touched only from the asyncio event loop (all routes are ``async``),
so no locking is needed. The only thing that outlives the process is the desired dummy
state, which is written to disk on every change so a hub restart does not silently turn
everyone's dummy processes off.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from .config import Config
from .models import ClusterState, NodeSnapshot, NodeView

log = logging.getLogger(__name__)


class Store:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._snapshots: dict[str, NodeSnapshot] = {}
        self._last_seen: dict[str, float] = {}
        # node_id -> {gpu_index: enabled}
        self._desired: dict[str, dict[int, bool]] = {}
        self._load_desired()

    # ------------------------------------------------------------------ ingest

    def ingest(self, snapshot: NodeSnapshot) -> dict[str, bool]:
        """Record an agent report and return the desired dummy state for that node."""
        self._snapshots[snapshot.node_id] = snapshot
        self._last_seen[snapshot.node_id] = time.time()

        # Register any GPU we have not seen before as "dummy off".
        node_desired = self._desired.setdefault(snapshot.node_id, {})
        for gpu in snapshot.gpus:
            node_desired.setdefault(gpu.index, False)

        return self.desired_for(snapshot.node_id)

    def desired_for(self, node_id: str) -> dict[str, bool]:
        return {str(idx): enabled for idx, enabled in self._desired.get(node_id, {}).items()}

    # ----------------------------------------------------------------- control

    def set_dummy(self, node_id: str, gpu_index: int | None, enabled: bool) -> dict[str, bool]:
        """Turn the dummy on/off for one GPU, or for every GPU on the node."""
        snapshot = self._snapshots.get(node_id)
        if snapshot is None:
            raise KeyError(node_id)

        node_desired = self._desired.setdefault(node_id, {})
        if gpu_index is None:
            for gpu in snapshot.gpus:
                node_desired[gpu.index] = enabled
        else:
            if not any(gpu.index == gpu_index for gpu in snapshot.gpus):
                raise IndexError(gpu_index)
            node_desired[gpu_index] = enabled

        self._save_desired()
        return self.desired_for(node_id)

    def known_nodes(self) -> list[str]:
        return sorted(self._snapshots)

    # ------------------------------------------------------------------- views

    def cluster_state(self) -> ClusterState:
        now = time.time()
        nodes: list[NodeView] = []

        for node_id, snapshot in self._snapshots.items():
            age = now - self._last_seen.get(node_id, 0.0)
            if age > self.config.forget_after:
                continue

            if age > self.config.offline_after:
                status = "offline"
            elif age > self.config.stale_after:
                status = "stale"
            else:
                status = "online"

            view = NodeView(**snapshot.model_dump(), status=status, age_s=round(age, 1))
            node_desired = self._desired.get(node_id, {})
            for gpu in view.gpus:
                gpu.dummy_enabled = node_desired.get(gpu.index, False)
                if status == "offline":
                    # We have no idea what is really running; do not claim it is live.
                    gpu.dummy_active = False
            nodes.append(view)

        # Stable, human-friendly ordering: node number first, then name.
        nodes.sort(key=lambda n: (n.node_index, n.node_id))
        return ClusterState(ts=now, nodes=nodes)

    # ------------------------------------------------------------- persistence

    def _load_desired(self) -> None:
        path = self.config.desired_state_file
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text())
            self._desired = {
                node_id: {int(idx): bool(val) for idx, val in gpus.items()}
                for node_id, gpus in raw.items()
            }
            log.info("loaded desired dummy state for %d node(s) from %s", len(self._desired), path)
        except Exception:
            log.exception("could not read %s, starting with an empty desired state", path)

    def _save_desired(self) -> None:
        path: Path = self.config.desired_state_file
        payload = {
            node_id: {str(idx): val for idx, val in gpus.items()}
            for node_id, gpus in self._desired.items()
        }
        tmp = path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
            os.replace(tmp, path)
        except Exception:
            log.exception("could not persist desired dummy state to %s", path)
