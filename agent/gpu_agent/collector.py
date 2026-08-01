"""Read GPU state.

Primary path is NVML (``nvidia-ml-py``), which is a pure-ctypes wrapper with no
sub-dependencies. If it is missing or fails to initialise we shell out to
``nvidia-smi`` instead, so the agent still works on a node where nothing could be
installed. The two paths produce the same dict shape, which is exactly the JSON the hub
expects (see hub/gpu_hub/models.py).
"""

from __future__ import annotations

import logging
import subprocess
from typing import Any

from . import procinfo

log = logging.getLogger(__name__)

try:  # nvidia-ml-py exposes itself as `pynvml`
    import pynvml  # type: ignore
except ImportError:  # pragma: no cover - depends on the node
    pynvml = None  # type: ignore


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return "" if value is None else str(value)


def _mib(value: Any) -> int:
    return int(value) // (1024 * 1024) if value else 0


class Collector:
    """Stateless-ish GPU reader. Holds the NVML handle set once initialised."""

    def __init__(self) -> None:
        self.backend = "none"
        self.driver_version: str | None = None
        self.cuda_version: str | None = None
        self._handles: list[Any] = []
        self._init()

    # ------------------------------------------------------------------ startup

    def _init(self) -> None:
        if pynvml is not None:
            try:
                pynvml.nvmlInit()
                self._handles = [
                    pynvml.nvmlDeviceGetHandleByIndex(i)
                    for i in range(pynvml.nvmlDeviceGetCount())
                ]
                self.driver_version = _text(pynvml.nvmlSystemGetDriverVersion())
                try:
                    raw = pynvml.nvmlSystemGetCudaDriverVersion()
                    self.cuda_version = f"{raw // 1000}.{(raw % 1000) // 10}"
                except Exception:
                    pass
                self.backend = "nvml"
                log.info("NVML ready: %d GPU(s), driver %s", len(self._handles), self.driver_version)
                return
            except Exception as exc:
                log.warning("NVML unavailable (%s), falling back to nvidia-smi", exc)

        if _nvidia_smi(["--query-gpu=index", "--format=csv,noheader"]) is not None:
            self.backend = "nvidia-smi"
            log.info("using nvidia-smi fallback collector")
        else:
            log.error("neither NVML nor nvidia-smi is usable; no GPU data will be reported")

    # ------------------------------------------------------------------ reading

    def collect(self) -> tuple[list[dict], str | None]:
        """Return ``(gpus, error)`` where error is a non-fatal note for the dashboard."""
        if self.backend == "nvml":
            try:
                return self._collect_nvml(), None
            except Exception as exc:
                log.exception("NVML read failed")
                return [], f"NVML read failed: {exc}"
        if self.backend == "nvidia-smi":
            try:
                return self._collect_smi(), "NVML unavailable, using nvidia-smi"
            except Exception as exc:
                log.exception("nvidia-smi read failed")
                return [], f"nvidia-smi read failed: {exc}"
        return [], "no GPU backend available"

    def _collect_nvml(self) -> list[dict]:
        gpus = []
        for index, handle in enumerate(self._handles):
            gpu: dict[str, Any] = {
                "index": index,
                "uuid": _text(_try(pynvml.nvmlDeviceGetUUID, handle)),
                "name": _text(_try(pynvml.nvmlDeviceGetName, handle)),
                "processes": [],
            }

            mem = _try(pynvml.nvmlDeviceGetMemoryInfo, handle)
            if mem is not None:
                gpu["mem_used_mb"] = _mib(mem.used)
                gpu["mem_total_mb"] = _mib(mem.total)

            util = _try(pynvml.nvmlDeviceGetUtilizationRates, handle)
            if util is not None:
                gpu["util_gpu"] = int(util.gpu)
                gpu["util_mem"] = int(util.memory)

            temp = _try(pynvml.nvmlDeviceGetTemperature, handle, pynvml.NVML_TEMPERATURE_GPU)
            if temp is not None:
                gpu["temp_c"] = int(temp)

            power = _try(pynvml.nvmlDeviceGetPowerUsage, handle)
            if power is not None:
                gpu["power_w"] = round(power / 1000.0, 1)

            limit = _try(pynvml.nvmlDeviceGetEnforcedPowerLimit, handle)
            if limit is None:
                limit = _try(pynvml.nvmlDeviceGetPowerManagementLimit, handle)
            if limit is not None:
                gpu["power_limit_w"] = round(limit / 1000.0, 1)

            for kind, getter in (("C", _compute_procs), ("G", _graphics_procs)):
                for proc in getter(handle):
                    gpu["processes"].append(_describe_proc(proc.pid, proc, kind))

            gpus.append(gpu)
        return gpus

    def _collect_smi(self) -> list[dict]:
        fields = (
            "index,uuid,name,memory.used,memory.total,utilization.gpu,"
            "utilization.memory,temperature.gpu,power.draw,power.limit"
        )
        out = _nvidia_smi([f"--query-gpu={fields}", "--format=csv,noheader,nounits"]) or ""
        by_uuid: dict[str, dict] = {}
        gpus: list[dict] = []
        for line in out.strip().splitlines():
            cells = [c.strip() for c in line.split(",")]
            if len(cells) < 10:
                continue
            gpu = {
                "index": int(cells[0]),
                "uuid": cells[1],
                "name": cells[2],
                "mem_used_mb": _num(cells[3], int) or 0,
                "mem_total_mb": _num(cells[4], int) or 0,
                "util_gpu": _num(cells[5], int),
                "util_mem": _num(cells[6], int),
                "temp_c": _num(cells[7], int),
                "power_w": _num(cells[8], float),
                "power_limit_w": _num(cells[9], float),
                "processes": [],
            }
            by_uuid[gpu["uuid"]] = gpu
            gpus.append(gpu)

        apps = _nvidia_smi(
            ["--query-compute-apps=gpu_uuid,pid,process_name,used_memory",
             "--format=csv,noheader,nounits"]
        ) or ""
        for line in apps.strip().splitlines():
            cells = [c.strip() for c in line.split(",")]
            if len(cells) < 4:
                continue
            gpu = by_uuid.get(cells[0])
            if gpu is None:
                continue
            pid = _num(cells[1], int)
            if pid is None:
                continue
            gpu["processes"].append(
                _describe_proc(pid, None, "C", nvml_name=cells[2], used_mem_mb=_num(cells[3], int))
            )
        return gpus

    def shutdown(self) -> None:
        if self.backend == "nvml" and pynvml is not None:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass


# ------------------------------------------------------------------------ helpers


def _try(fn, *args):
    try:
        return fn(*args)
    except Exception:
        return None


def _num(text: str, cast):
    try:
        return cast(text)
    except (TypeError, ValueError):
        return None


def _nvidia_smi(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", *args], capture_output=True, text=True, timeout=10, check=True
        )
        return result.stdout
    except Exception:
        return None


def _compute_procs(handle):
    for name in ("nvmlDeviceGetComputeRunningProcesses_v3", "nvmlDeviceGetComputeRunningProcesses"):
        fn = getattr(pynvml, name, None)
        if fn is not None:
            result = _try(fn, handle)
            if result is not None:
                return result
    return []


def _graphics_procs(handle):
    for name in ("nvmlDeviceGetGraphicsRunningProcesses_v3", "nvmlDeviceGetGraphicsRunningProcesses"):
        fn = getattr(pynvml, name, None)
        if fn is not None:
            result = _try(fn, handle)
            if result is not None:
                return result
    return []


def _describe_proc(pid, raw, kind, nvml_name: str = "", used_mem_mb=None) -> dict:
    if raw is not None:
        used = getattr(raw, "usedGpuMemory", None)
        used_mem_mb = _mib(used) if used else None
        if pynvml is not None:
            nvml_name = _text(_try(pynvml.nvmlSystemGetProcessName, pid))

    name, cmdline, user = procinfo.describe(pid, nvml_name)
    return {
        "pid": pid,
        "name": name,
        "cmdline": cmdline,
        "user": user,
        "used_mem_mb": used_mem_mb,
        "kind": kind,
        "is_dummy": procinfo.is_dummy_process(name, cmdline, nvml_name),
    }
