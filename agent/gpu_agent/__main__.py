"""Node agent main loop: collect -> push -> reconcile dummies, once per tick."""

from __future__ import annotations

import logging
import signal
import sys
import time

from . import __version__
from .collector import Collector
from .config import load_config
from .dummy import DummyManager
from .hubclient import HubClient

log = logging.getLogger("gpu_agent")

_running = True


def _stop(signum, frame):  # noqa: ARG001
    global _running
    _running = False


def main(argv: list[str] | None = None) -> int:
    config = load_config(argv)
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if not config.token:
        log.error("no hub token configured (set GPU_AGENT_TOKEN or pass --token)")
        return 2

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    collector = Collector()
    dummies = DummyManager(config)
    client = HubClient(config.ingest_url, config.token, config.timeout, config.insecure)

    log.info(
        "agent %s starting: node_id=%s node_index=%d hub=%s interval=%.1fs",
        __version__, config.node_id, config.node_index, config.ingest_url, config.interval,
    )

    # Held across ticks so a hub outage does not silently tear down every dummy: we keep
    # reconciling towards the last instruction we actually received.
    desired: dict[int, bool] = {}

    try:
        while _running:
            tick_started = time.monotonic()

            gpus, error = collector.collect()
            dummies.annotate(gpus)

            payload = {
                "node_id": config.node_id,
                "node_index": config.node_index,
                "cluster": config.cluster,
                "hostname": config.hostname,
                "ts": time.time(),
                "agent_version": __version__,
                "driver_version": collector.driver_version,
                "cuda_version": collector.cuda_version,
                "gpus": gpus,
                "error": error,
            }

            response = client.post_snapshot(payload)
            if response is not None:
                desired = {
                    int(index): bool(enabled)
                    for index, enabled in (response.get("desired_dummy") or {}).items()
                }

            try:
                dummies.reconcile(gpus, desired)
            except Exception:
                log.exception("dummy reconcile failed")

            sleep_for = config.interval - (time.monotonic() - tick_started)
            if sleep_for > 0:
                time.sleep(sleep_for)
    finally:
        log.info("shutting down")
        dummies.stop_all()
        collector.shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
