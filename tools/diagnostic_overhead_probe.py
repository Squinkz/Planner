"""Disabled wrapper dispatch cost; this does not measure whole-frame overhead."""
import json
import platform
import sys
from pathlib import Path
from statistics import median
from timeit import repeat
from types import SimpleNamespace

root = Path(__file__).resolve().parent.parent
(root / "diagnostics").mkdir(exist_ok = True)
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore
from planner_app.viewport.diagnostics import MeasurePaint, MeasureRecoveryCheckpoint, MeasureRecoveryWrite


def Main():
    viewport = SimpleNamespace(renderDiagnostics = None)
    window = SimpleNamespace(viewport = viewport)

    def Callback(owner):
        return None

    iterations = 300000
    results = {}
    for name, decorator, owner in (("paint", MeasurePaint, viewport),
                                   ("checkpoint", MeasureRecoveryCheckpoint, window),
                                   ("writer", MeasureRecoveryWrite, window)):
        wrapped = decorator(Callback)
        direct = median(repeat(lambda: Callback(owner), number = iterations, repeat = 5))
        disabled = median(repeat(lambda: wrapped(owner), number = iterations, repeat = 5))
        results[name] = {"directNs": direct / iterations * 1e9,
                         "disabledNs": disabled / iterations * 1e9,
                         "addedNs": (disabled - direct) / iterations * 1e9}
    report = {"python": platform.python_version(), "qt": QtCore.qVersion(),
              "iterationsPerSample": iterations, "medianSamples": 5, "wrappers": results,
              "note": "No-op dispatch only; not whole-frame or native presentation overhead."}
    (root / "diagnostics/diagnostic-overhead-20261008.json").write_text(json.dumps(report, indent = 2) + "\n",
                                                                     encoding = "utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    Main()
