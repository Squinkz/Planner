"""Isolated Windows native-history retention and real warm geometry rebuilds."""
import argparse
import ctypes
from ctypes import wintypes
import gc
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
from time import perf_counter
import tracemalloc

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
os.environ["QT_QPA_PLATFORM"] = "offscreen"


class MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in (
        "peakWorkingSet", "workingSet", "peakPagedPool", "pagedPool", "peakNonPagedPool", "nonPagedPool",
        "pagefile", "peakPagefile", "privateBytes")]


def ProcessMemory():
    kernel = ctypes.WinDLL("kernel32", use_last_error = True)
    psapi = ctypes.WinDLL("psapi", use_last_error = True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD]
    values = MemoryCounters()
    values.cb = ctypes.sizeof(values)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(values), values.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return dict(workingSet = values.workingSet, privateBytes = values.privateBytes)


def Probe(variant):
    from PySide6 import QtCore, QtGui, QtWidgets
    from planner_app.models import Wall
    from planner_app.viewport.geometry import FootprintGeometry
    from planner_app.viewport.geometry_cache import NativeGeometryBudget, NativeGeometryCache, GeometryCacheCost
    app = QtWidgets.QApplication([])
    gc.disable()
    point = QtCore.QPointF
    owners = [Wall(point(index * 1000, 0), point(index * 1000, 500), 200) for index in range(64)]
    polygon = QtGui.QPolygonF([point(0, 0), point(100, 0), point(100, 50), point(0, 50), point(0, 0)])
    template = QtGui.QPainterPath()
    template.addPolygon(QtGui.QPolygonF([point(index * .1, math.sin(index * .013) * 100) for index in range(16384)]))
    template.closeSubpath()
    budget = NativeGeometryBudget()
    cache = {} if variant == "before" else NativeGeometryCache(budget)
    gc.collect()
    before = ProcessMemory()
    tracemalloc.start()
    for frame in range(128):
        transform = QtGui.QTransform().translate((frame + 1) * .17, frame * .03)
        key = (.1, True, tuple((id(owner), frame * .17, index * 500.0, 160.0) for index, owner in enumerate(owners)))
        value = transform.map(template), [(owner, transform.map(polygon)) for owner in owners]
        cache[key] = value
        while len(cache) > 128:
            cache.pop(next(iter(cache)))
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    after = ProcessMemory()
    costs = [GeometryCacheCost(key, value) for key, value in cache.items()]
    retention = dict(entries = len(cache), estimatedBytes = sum(cost[0] for cost in costs), points = sum(cost[1] for cost in costs),
        processBefore = before, processAfter = after, pythonRetained = current, pythonPeak = peak,
        workingSetGrowth = after["workingSet"] - before["workingSet"], privateGrowth = after["privateBytes"] - before["privateBytes"])
    cache.clear()
    del value, key
    gc.collect()
    retention["processAfterClear"] = ProcessMemory()
    return dict(variant = variant, retention = retention)


def ProbeCpu():
    from PySide6 import QtCore, QtWidgets
    from planner_app.models import Wall
    from planner_app.viewport.geometry import FootprintGeometry
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    gc.disable()
    source = root / "diagnostics/performance-memory-gc-20261031/before/geometry.py"
    spec = importlib.util.spec_from_file_location("planner_app.viewport.geometry_memory_before", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    views = [module.FootprintGeometry(.1), FootprintGeometry(.1)]
    sources = [[Wall(QtCore.QPointF(index * 2000, 0), QtCore.QPointF(index * 2000, 600), 200) for index in range(1024)] for view in views]
    for view, walls in zip(views, sources):
        view.ConnectedWallPath(walls)
    gc.collect()
    samples = [[], []]
    for frame in range(20):
        for variant in ((0, 1) if frame % 2 == 0 else (1, 0)):
            start = perf_counter()
            for step in range(8):
                sources[variant][-1].secondVertex += QtCore.QPointF(.7, .3)
                views[variant].ConnectedWallPath(sources[variant])
            elapsed = (perf_counter() - start) * 1000 / 8
            if frame >= 5:
                samples[variant].append(elapsed)
    return dict(beforeMs = statistics.median(samples[0]), afterMs = statistics.median(samples[1]), samplesMs = samples)


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--variant", choices = ("before", "after"))
    parser.add_argument("--output", type = Path, default = root / "diagnostics/performance-memory-gc-20261031/geometry-memory-final.json")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("The process-memory counters in this probe require Windows")
    if args.variant:
        result = Probe(args.variant)
    else:
        measurements = []
        for variant in ("before", "after"):
            path = args.output.with_name("geometry-memory-" + variant + ".json")
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "--variant", variant, "--output", str(path)], check = True)
            measurements.append(json.loads(path.read_text(encoding = "utf-8")))
        result = dict(methodology = "Fresh process per variant. Retain 128 synthetic complex component histories with 16,385-element native paths, "
            "64 owned polygons and model keys; compare original entry-count policy with the aggregate budget. "
            "Record process working-set/private growth alongside tracemalloc retained/peak Python bytes. "
            "This isolates cache retention, not full-scene memory or rendering. A separate untraced, alternating frozen/current 1,024-wall rebuild changes one "
            "isolated endpoint, discards five warmup batches and reports 15 samples averaging eight updates each, "
            "with automatic Python GC disabled like the editor. "
            "Original source snapshot required for baseline.", measurements = measurements, warmGeometry = ProbeCpu())
    args.output.parent.mkdir(parents = True, exist_ok = True)
    args.output.write_text(json.dumps(result, indent = 2) + "\n", encoding = "utf-8")
    print(json.dumps(result), flush = True)


if __name__ == "__main__":
    Main()
