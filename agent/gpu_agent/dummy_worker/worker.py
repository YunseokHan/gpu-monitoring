"""The dummy process: holds a GPU's VRAM and (optionally) pins it at ~100% utilization.

Started by the agent as::

    Popen(["dummy", worker.py, ...], executable=sys.executable,
          env={"CUDA_VISIBLE_DEVICES": "<gpu uuid>", ...})

Setting argv[0] to "dummy" is what makes nvidia-smi's Process name column -- which shows
argv[0] as invoked -- read "dummy". prctl(PR_SET_NAME) additionally fixes /proc/<pid>/comm,
which is what `ps` and `top` display.

Two backends:

* ``cuda``  -- the CUDA driver API through ctypes. Needs nothing but libcuda.so.1, which
  ships with the driver, so it works on a bare node with no CUDA toolkit and no pip
  packages. The compute kernel is the pre-compiled kernel.ptx sitting next to this file;
  the driver JIT-compiles it for whatever GPU it lands on.
* ``torch`` -- fallback for nodes where the driver API path fails for any reason.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import signal
import sys
import time
from pathlib import Path

PTX_PATH = Path(__file__).with_name("kernel.ptx")

MIB = 1024 * 1024
MIN_CHUNK = 64 * MIB
# Each kernel launch is calibrated to roughly this duration: long enough that launch
# overhead is negligible, short enough to react to SIGTERM promptly.
TARGET_KERNEL_MS = 20.0

_running = True


def _handle_signal(signum, frame):  # noqa: ARG001
    global _running
    _running = False


def set_process_name(name: str = "dummy") -> None:
    """Set /proc/<pid>/comm (what ps/top show). argv[0] is set by the parent."""
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        PR_SET_NAME = 15
        libc.prctl(PR_SET_NAME, ctypes.c_char_p(name.encode()), 0, 0, 0)
    except Exception:
        pass


def die_with_parent() -> None:
    """Ask the kernel to SIGTERM us if the agent dies.

    Without this, an agent that is SIGKILLed (or a container that restarts its
    supervisor) would leave a process holding every byte of VRAM on the card with
    nothing left to turn it off.
    """
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        PR_SET_PDEATHSIG = 1
        libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0)
        # Guard the race where the parent died between fork and this call.
        if os.getppid() == 1:
            raise SystemExit(0)
    except SystemExit:
        raise
    except Exception:
        pass


def log(msg: str) -> None:
    print(f"[dummy] {msg}", flush=True)


# --------------------------------------------------------------- CUDA driver API


class CudaError(RuntimeError):
    pass


CUdeviceptr = ctypes.c_ulonglong
CU_DEVICE_ATTRIBUTE_MULTIPROCESSOR_COUNT = 16


class CudaDriver:
    """Just enough of libcuda.so.1 to allocate memory and launch one kernel."""

    def __init__(self) -> None:
        self.lib = ctypes.CDLL("libcuda.so.1")
        self.ctx = None
        self.blocks: list[int] = []

    def check(self, code: int, what: str) -> None:
        if code != 0:
            name = ctypes.c_char_p()
            try:
                self.lib.cuGetErrorName(code, ctypes.byref(name))
                detail = name.value.decode() if name.value else str(code)
            except Exception:
                detail = str(code)
            raise CudaError(f"{what} -> {detail} ({code})")

    # -- lifecycle ---------------------------------------------------------

    def init(self) -> None:
        self.check(self.lib.cuInit(0), "cuInit")
        count = ctypes.c_int()
        self.check(self.lib.cuDeviceGetCount(ctypes.byref(count)), "cuDeviceGetCount")
        if count.value < 1:
            raise CudaError("no CUDA device visible (check CUDA_VISIBLE_DEVICES)")

        device = ctypes.c_int()
        self.check(self.lib.cuDeviceGet(ctypes.byref(device), 0), "cuDeviceGet")
        self.device = device

        ctx = ctypes.c_void_p()
        self.check(self.lib.cuCtxCreate_v2(ctypes.byref(ctx), 0, device), "cuCtxCreate")
        self.ctx = ctx

    def destroy(self) -> None:
        for ptr in self.blocks:
            try:
                self.lib.cuMemFree_v2(CUdeviceptr(ptr))
            except Exception:
                pass
        self.blocks.clear()
        if self.ctx is not None:
            try:
                self.lib.cuCtxDestroy_v2(self.ctx)
            except Exception:
                pass
            self.ctx = None

    # -- memory ------------------------------------------------------------

    def mem_info(self) -> tuple[int, int]:
        free, total = ctypes.c_size_t(), ctypes.c_size_t()
        self.check(
            self.lib.cuMemGetInfo_v2(ctypes.byref(free), ctypes.byref(total)), "cuMemGetInfo"
        )
        return free.value, total.value

    def alloc(self, size: int) -> int | None:
        ptr = CUdeviceptr()
        if self.lib.cuMemAlloc_v2(ctypes.byref(ptr), ctypes.c_size_t(size)) != 0:
            return None
        self.blocks.append(ptr.value)
        return ptr.value

    def fill(self, headroom: int, chunk: int) -> int:
        """Allocate up to (free - headroom), shrinking the chunk size on failure."""
        held = 0
        while _running:
            free, _ = self.mem_info()
            budget = free - headroom
            if budget < MIN_CHUNK:
                break
            size = min(chunk, budget)
            if self.alloc(size) is None:
                chunk //= 2
                if chunk < MIN_CHUNK:
                    break
                continue
            held += size
        return held

    # -- compute -----------------------------------------------------------

    def load_kernel(self) -> tuple[ctypes.c_void_p, int]:
        ptx = PTX_PATH.read_bytes()
        module = ctypes.c_void_p()
        self.check(
            self.lib.cuModuleLoadData(ctypes.byref(module), ctypes.c_char_p(ptx)),
            "cuModuleLoadData (driver could not JIT kernel.ptx)",
        )
        func = ctypes.c_void_p()
        self.check(
            self.lib.cuModuleGetFunction(ctypes.byref(func), module, b"spin"),
            "cuModuleGetFunction",
        )
        sm_count = ctypes.c_int()
        self.check(
            self.lib.cuDeviceGetAttribute(
                ctypes.byref(sm_count), CU_DEVICE_ATTRIBUTE_MULTIPROCESSOR_COUNT, self.device
            ),
            "cuDeviceGetAttribute",
        )
        return func, sm_count.value

    def launch(self, func, buf_ptr: int, grid: int, block: int, iters: int) -> None:
        buf = CUdeviceptr(buf_ptr)
        n = ctypes.c_ulonglong(iters)
        params = (ctypes.c_void_p * 2)(
            ctypes.cast(ctypes.byref(buf), ctypes.c_void_p),
            ctypes.cast(ctypes.byref(n), ctypes.c_void_p),
        )
        self.check(
            self.lib.cuLaunchKernel(
                func, grid, 1, 1, block, 1, 1, 0, None, params, None
            ),
            "cuLaunchKernel",
        )

    def sync(self) -> None:
        self.check(self.lib.cuCtxSynchronize(), "cuCtxSynchronize")


def run_cuda(headroom: int, chunk: int, want_util: bool) -> None:
    drv = CudaDriver()
    drv.init()
    try:
        func = grid = block = None
        buf_ptr = None
        iters = 1 << 14

        if want_util:
            func, sm_count = drv.load_kernel()
            block = 256
            grid = max(sm_count, 1) * 4
            # Reserve the kernel's scratch buffer before hogging the rest of the card.
            buf_ptr = drv.alloc(grid * block * 4)
            if buf_ptr is None:
                raise CudaError("could not allocate the kernel scratch buffer")

        held = drv.fill(headroom, chunk)
        free, total = drv.mem_info()
        log(
            f"backend=cuda held={held / MIB:.0f}MiB "
            f"free={free / MIB:.0f}MiB total={total / MIB:.0f}MiB util={'on' if want_util else 'off'}"
        )

        if not want_util:
            while _running:
                time.sleep(0.5)
            return

        # Calibrate so one launch lands near TARGET_KERNEL_MS on this particular GPU.
        start = time.perf_counter()
        drv.launch(func, buf_ptr, grid, block, iters)
        drv.sync()
        elapsed_ms = (time.perf_counter() - start) * 1000
        if elapsed_ms > 0:
            iters = max(1 << 10, int(iters * TARGET_KERNEL_MS / elapsed_ms))
        log(f"kernel calibrated: grid={grid} block={block} iters={iters} (~{TARGET_KERNEL_MS:.0f}ms)")

        # Keep several launches queued so the GPU never drains between syncs.
        while _running:
            for _ in range(4):
                drv.launch(func, buf_ptr, grid, block, iters)
            drv.sync()
    finally:
        drv.destroy()


# ---------------------------------------------------------------- torch backend


def run_torch(headroom: int, chunk: int, want_util: bool) -> None:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("torch reports no CUDA device")
    device = torch.device("cuda:0")
    torch.cuda.init()

    a = b = c = None
    if want_util:
        # Allocated before the fill loop, including the output buffer: once we have taken
        # every free byte there is nothing left for matmul to allocate implicitly.
        n = 8192
        a = torch.randn(n, n, device=device, dtype=torch.float32)
        b = torch.randn(n, n, device=device, dtype=torch.float32)
        c = torch.empty(n, n, device=device, dtype=torch.float32)

    blocks = []
    held = 0
    while _running:
        free, _ = torch.cuda.mem_get_info()
        budget = free - headroom
        if budget < MIN_CHUNK:
            break
        size = min(chunk, budget)
        try:
            blocks.append(torch.empty(size, dtype=torch.uint8, device=device))
            held += size
        except RuntimeError:
            chunk //= 2
            if chunk < MIN_CHUNK:
                break

    free, total = torch.cuda.mem_get_info()
    log(
        f"backend=torch held={held / MIB:.0f}MiB "
        f"free={free / MIB:.0f}MiB total={total / MIB:.0f}MiB util={'on' if want_util else 'off'}"
    )

    while _running:
        if want_util:
            torch.matmul(a, b, out=c)
            torch.cuda.synchronize()
        else:
            time.sleep(0.5)


# ------------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dummy")
    parser.add_argument("--headroom-mb", type=int, default=2048)
    parser.add_argument("--chunk-mb", type=int, default=1024)
    parser.add_argument("--backend", default="auto", choices=["auto", "cuda", "torch"])
    parser.add_argument("--no-util", action="store_true")
    parser.add_argument("--label", default="", help="informational only; shows up in ps output")
    args = parser.parse_args(argv)

    set_process_name("dummy")
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    die_with_parent()

    headroom = args.headroom_mb * MIB
    chunk = max(args.chunk_mb * MIB, MIN_CHUNK)
    want_util = not args.no_util

    backends = ["cuda", "torch"] if args.backend == "auto" else [args.backend]
    last_error: Exception | None = None
    for backend in backends:
        try:
            (run_cuda if backend == "cuda" else run_torch)(headroom, chunk, want_util)
            return 0
        except Exception as exc:
            last_error = exc
            log(f"backend {backend} failed: {exc}")

    log(f"all backends failed: {last_error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
