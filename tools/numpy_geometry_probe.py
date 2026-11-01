"""Compare frozen containment and pixel diagnostics with the array paths."""
import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import tempfile
from time import perf_counter
import tracemalloc

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.numpy_runtime import LoadNumPy
from planner_app.viewport.widget import DrawingViewport
from check_numpy_containment import MakeWalls, ReferenceGeometry
from image_comparison import ChangedPixels


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--output", type = Path, default = root / "diagnostics/numpy-geometry-probe.json")
    args = parser.parse_args()
    app = QtWidgets.QApplication([])
    view = DrawingViewport()
    view.performanceTimer.stop()
    started = perf_counter()
    np = LoadNumPy()
    results = dict(python = platform.python_version(), qt = QtCore.qVersion(), numpy = np.__version__,
                   numpyImportMs = (perf_counter() - started) * 1000, containment = [], pixels = [])
    for count in (16, 32, 64, 128, 404, 1024, 4096):
        walls = MakeWalls(count)
        samples = [[], []]
        expected = None
        for repeat in range(9):
            for methodIndex in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                view.containedWallKey = None
                method = (ReferenceGeometry.ContainedWalls, DrawingViewport.ContainedWalls)[methodIndex]
                started = perf_counter()
                result = method(view, walls)
                elapsed = (perf_counter() - started) * 1000
                if expected is None:
                    expected = result
                assert result == expected, (count, methodIndex)
                if repeat:
                    samples[methodIndex].append(elapsed)
        cached = view.ContainedWalls(walls)
        started = perf_counter()
        for repeat in range(100):
            assert view.ContainedWalls(walls) is cached
        warmMs = (perf_counter() - started) * 10
        view.containedWallKey = None
        tracemalloc.start()
        view.ContainedWalls(walls)
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        record = dict(walls = count, contained = len(expected), scalarMedianMs = statistics.median(samples[0]),
                      arrayMedianMs = statistics.median(samples[1]), warmCacheMs = warmMs,
                      tracedPeakBytes = peak, samplesMs = samples)
        results["containment"].append(record)
        print(f"{count} walls: {record['scalarMedianMs']:.3f} -> {record['arrayMedianMs']:.3f} ms; "
              f"cache {warmMs:.3f} ms; peak tracked {peak / 1024:.1f} KiB", flush = True)

    for width, height, spacing in ((1600, 1000, 2000), (400, 300, 1)):
        first = bytearray([120, 130, 140, 255]) * (width * height)
        second = first.copy()
        for index in range(0, width * height, spacing):
            second[index * 4] = 0
        left = QtGui.QImage(first, width, height, width * 4, QtGui.QImage.Format.Format_RGBA8888)
        right = QtGui.QImage(second, width, height, width * 4, QtGui.QImage.Format.Format_RGBA8888)
        samples = [[], []]
        expected = None
        for repeat in range(5):
            for methodIndex in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                started = perf_counter()
                if methodIndex == 0:
                    a, b = memoryview(left.constBits()), memoryview(right.constBits())
                    changed = [index for index, (x, y) in enumerate(zip(a.cast("I"), b.cast("I"))) if x != y]
                    maximum = max((abs(a[index * 4 + channel] - b[index * 4 + channel])
                                   for index in changed for channel in range(4)), default = 0)
                    result = len(changed), maximum
                else:
                    changed, differences = ChangedPixels(left, right)
                    result = len(changed), int(differences.max(initial = 0))
                elapsed = (perf_counter() - started) * 1000
                if expected is None:
                    expected = result
                assert result == expected
                samples[methodIndex].append(elapsed)
        record = dict(width = width, height = height, changedPixels = expected[0], maximumError = expected[1],
                      pythonMedianMs = statistics.median(samples[0]), arrayMedianMs = statistics.median(samples[1]),
                      samplesMs = samples)
        results["pixels"].append(record)
        print(f"{width} x {height}, {expected[0]} changed: {record['pythonMedianMs']:.3f} -> "
              f"{record['arrayMedianMs']:.3f} ms", flush = True)
    view.close()
    assert QtWidgets.QApplication.instance() is app
    args.output.parent.mkdir(parents = True, exist_ok = True)
    args.output.write_text(json.dumps(results, indent = 2), encoding = "utf-8")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        for key, name in (("PLANNER_SESSION_PATH", "session.json"), ("PLANNER_STARTUP_PATH", "startup.plan"),
                          ("PLANNER_PREFERENCES_PATH", "preferences.json")):
            os.environ[key] = str(Path(directory) / name)
        Main()
