"""Keeps the dummy workers in sync with the hub's desired state.

The rule the whole feature rests on: a dummy may only occupy a GPU that nothing else is
using. The moment any other compute process shows up we stop, and we do not come back
until the GPU has been quiet for ``dummy_cooldown`` seconds. That cooldown is what stops
us from stealing the card back in between the restarts of a crash-looping job.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from .config import Config
from .procinfo import DUMMY_ARGV0

log = logging.getLogger(__name__)

WORKER = Path(__file__).parent / "dummy_worker" / "worker.py"

_TERM_GRACE = 5.0
# Exponential backoff after a worker exits on its own (bad driver, no PTX support, ...)
# so a permanently broken GPU does not turn into a spawn loop.
_BACKOFF_START = 5.0
_BACKOFF_MAX = 300.0


class DummyManager:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._procs: dict[int, subprocess.Popen] = {}
        self._started_at: dict[int, float] = {}
        self._last_busy: dict[int, float] = {}
        self._backoff_until: dict[int, float] = {}
        self._backoff: dict[int, float] = {}
        # Every pid we have ever spawned in this run, so orphan cleanup can never
        # mistake a live child of ours for a leftover.
        self._our_pids: set[int] = set()
        self._orphan_warned: set[int] = set()

    # ------------------------------------------------------------------- status

    def active(self, gpu_index: int) -> subprocess.Popen | None:
        proc = self._procs.get(gpu_index)
        return proc if proc is not None and proc.poll() is None else None

    def annotate(self, gpus: list[dict]) -> None:
        """Stamp each GPU dict with whether our dummy is live on it."""
        for gpu in gpus:
            proc = self.active(gpu["index"])
            gpu["dummy_active"] = proc is not None
            gpu["dummy_pid"] = proc.pid if proc is not None else None

    # ---------------------------------------------------------------- reconcile

    def reconcile(self, gpus: list[dict], desired: dict[int, bool]) -> None:
        now = time.time()
        self._reap(now)

        for gpu in gpus:
            index = gpu["index"]
            want = desired.get(index, False)
            proc = self.active(index)

            self._kill_orphans(gpu, now)

            others = [p for p in gpu.get("processes", []) if not p.get("is_dummy")]
            if others:
                self._last_busy[index] = now
                if proc is not None:
                    names = ", ".join(sorted({p["name"] for p in others})) or "?"
                    log.info("GPU %d: yielding to %s (pid %s)", index, names, others[0]["pid"])
                    self._stop(index)
                continue

            if not want:
                if proc is not None:
                    log.info("GPU %d: dummy turned off", index)
                    self._stop(index)
                continue

            if proc is not None:
                continue
            if now - self._last_busy.get(index, 0.0) < self.config.dummy_cooldown:
                continue
            if now < self._backoff_until.get(index, 0.0):
                continue
            self._spawn(gpu)

    def _kill_orphans(self, gpu: dict, now: float) -> None:
        """Reap dummy processes left behind by a previous agent run.

        Without this, a restarted agent would see "no other process is using this GPU"
        (orphans are dummies, so they never count as a real job), start a second dummy,
        and the first one's VRAM would be held forever.
        """
        index = gpu["index"]
        # A worker takes a moment to appear in NVML; do not judge a fresh spawn.
        if now - self._started_at.get(index, 0.0) < 15.0:
            return

        for proc_info in gpu.get("processes", []):
            pid = proc_info.get("pid")
            if not proc_info.get("is_dummy") or pid in self._our_pids:
                continue
            try:
                os.kill(pid, signal.SIGTERM)
                log.warning("GPU %d: killed orphaned dummy pid %d from an earlier run", index, pid)
            except ProcessLookupError:
                pass
            except PermissionError:
                if pid not in self._orphan_warned:
                    self._orphan_warned.add(pid)
                    log.warning(
                        "GPU %d: dummy pid %d belongs to another user and cannot be stopped",
                        index, pid,
                    )

    # -------------------------------------------------------------- child procs

    def _spawn(self, gpu: dict) -> None:
        index = gpu["index"]
        uuid = gpu.get("uuid") or str(index)
        env = dict(os.environ)
        # Pin by UUID rather than ordinal: immune to enumeration order changing.
        env["CUDA_VISIBLE_DEVICES"] = uuid
        env["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"

        args = [
            DUMMY_ARGV0,  # argv[0] -- this is the name nvidia-smi will display
            str(WORKER),
            "--headroom-mb", str(self.config.dummy_headroom_mb),
            "--chunk-mb", str(self.config.dummy_chunk_mb),
            "--backend", "auto" if self.config.dummy_backend == "auto" else self.config.dummy_backend,
            "--label", f"gpu{index}",
        ]
        if not self.config.dummy_target_util:
            args.append("--no-util")

        try:
            proc = subprocess.Popen(args, executable=sys.executable, env=env, start_new_session=True)
        except Exception:
            log.exception("GPU %d: could not start dummy worker", index)
            self._penalise(index)
            return

        self._procs[index] = proc
        self._our_pids.add(proc.pid)
        self._started_at[index] = time.time()
        log.info("GPU %d: dummy started (pid %d, uuid %s)", index, proc.pid, uuid)

    def _stop(self, index: int) -> None:
        proc = self._procs.pop(index, None)
        if proc is None:
            return
        if proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=_TERM_GRACE)
        except subprocess.TimeoutExpired:
            log.warning("GPU %d: dummy pid %d ignored SIGTERM, killing", index, proc.pid)
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()
            try:
                proc.wait(timeout=_TERM_GRACE)
            except subprocess.TimeoutExpired:
                log.error("GPU %d: dummy pid %d will not die", index, proc.pid)
        except Exception:
            log.exception("GPU %d: error stopping dummy", index)

    def _reap(self, now: float) -> None:
        """Notice workers that exited by themselves and back off before retrying."""
        for index, proc in list(self._procs.items()):
            rc = proc.poll()
            if rc is None:
                continue
            self._procs.pop(index, None)
            lifetime = now - self._started_at.pop(index, now)
            log.warning(
                "GPU %d: dummy pid %d exited on its own (rc=%s, after %.0fs)",
                index, proc.pid, rc, lifetime,
            )
            # A worker that ran fine for a while and then died is not a broken GPU;
            # forget any accumulated penalty so we retry promptly.
            if lifetime > 60.0:
                self._backoff.pop(index, None)
            self._penalise(index, now)

    def _penalise(self, index: int, now: float | None = None) -> None:
        now = time.time() if now is None else now
        delay = min(self._backoff.get(index, 0.0) * 2 or _BACKOFF_START, _BACKOFF_MAX)
        self._backoff[index] = delay
        self._backoff_until[index] = now + delay
        log.info("GPU %d: not retrying the dummy for %.0fs", index, delay)

    def stop_all(self) -> None:
        for index in list(self._procs):
            log.info("GPU %d: stopping dummy (agent shutting down)", index)
            self._stop(index)
