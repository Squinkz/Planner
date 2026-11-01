"""Texture-array initialization must not start a large unused BLAS thread pool."""
import ctypes
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from planner_app.graphics import compositing
from planner_app import numpy_runtime


def Main():
    assert "numpy" not in sys.modules, "NumPy loaded before its thread budget could be configured"
    before = None
    if sys.platform == "win32":
        from ctypes import wintypes

        class MemoryCounters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ("peakWorkingSet", "workingSet", "peakPagedPool", "pagedPool",
                    "peakNonPagedPool", "nonPagedPool", "pagefile", "peakPagefile", "privateBytes")]

        kernel = ctypes.WinDLL("kernel32")
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi")
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD]
        counters = MemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        assert psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
        before = counters.privateBytes
    # A high inherited setting must be overridden, not retained by setdefault.
    # Planner uses elementwise operations, so BLAS parallelism brings no benefit.
    os.environ["OPENBLAS_NUM_THREADS"] = "64"
    arrays = compositing.LoadNumPy()
    assert os.environ["OPENBLAS_NUM_THREADS"] == "1"
    assert arrays is compositing.LoadNumPy(), "Every lighting adjustment initialized the runtime again"
    assert compositing.LoadNumPy is numpy_runtime.LoadNumPy, "Geometry and lighting must share one lazy runtime"
    assert (arrays.arange(256, dtype = arrays.uint16) << 8)[255] == 65280
    if before is not None:
        assert psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
        increase = counters.privateBytes - before
        # Generous allowance for binaries/imports, but reject the observed
        # ~620 MiB default pool inside the 768 MiB preview-worker limit.
        assert increase < 128 * 1024 * 1024, f"NumPy initialization committed {increase / 1024 ** 2:.1f} MiB"
        print(f"NumPy initialized with one BLAS thread; private memory increased {increase / 1024 ** 2:.1f} MiB")


if __name__ == "__main__":
    Main()
