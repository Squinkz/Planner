"""Profile real scene interaction and painting with isolated recovery writes.

Arguments: optional fixture JSON (session format), optional output JSON.
Without a fixture, reads the current saved session without modifying it.
"""
import cProfile
import io
import json
import os
from pathlib import Path
import pstats
import statistics
import sys
import tempfile
from time import perf_counter

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner_app.ui.main_window import MainWindow
from planner_app.project_codec import DecodeProject
from planner_app.models import Wall
from planner_app.viewport.widget import DrawingViewport


def Main():
    arguments = [value for value in sys.argv[1:] if value != "--baseline"]
    if "--baseline" in sys.argv:
        root = Path(__file__).resolve().parent.parent
        for module, mixin in (("geometry", "GeometryMixin"), ("snapping", "SnappingMixin"),
                             ("rendering", "RenderingMixin"), ("placement", "PlacementMixin")):
            namespace = {"__name__": f"planner_app.viewport.{module}"}
            exec((root / "scratch" / f"{module}-before-current-perf.py").read_text(encoding = "utf-8"), namespace)
            for name, method in vars(namespace[mixin]).items():
                if callable(method):
                    setattr(DrawingViewport, name, method)
    source = Path(arguments[0]) if arguments else Path(os.environ["LOCALAPPDATA"]) / "Planner/session.json"
    data = json.loads(source.read_text(encoding = "utf-8"))
    data["project"].pop("history", None)
    app = QtWidgets.QApplication([])
    results = {}
    with tempfile.TemporaryDirectory() as sessionFolder:
        os.environ["PLANNER_SESSION_PATH"] = str(Path(sessionFolder) / "session.json")
        os.environ["PLANNER_STARTUP_PATH"] = str(Path(sessionFolder) / "startup.plan")
        window = MainWindow()
        viewport = window.viewport
        window.ApplyProject(DecodeProject(data["project"], viewport.furnishingDefinitions), None)
        window.showNormal()
        window.resize(*data.get("ui", {}).get("size", [2560, 1336]))
        window.mainSplitter.setSizes(data.get("ui", {}).get("mainSplitter", [2132, 396]))
        app.processEvents()
        viewport.performanceTimer.stop()
        window.sessionPollTimer.stop()
        window.sessionTimer.stop()
        window.projectTimer.stop()
        point = QtCore.QPointF
        originalPan = point(viewport.panOffset)
        results["viewport"] = [viewport.width(), viewport.height(), viewport.devicePixelRatioF()]
        for mode in ("hover", "pan", "pan-fractional", "move-walls", "move-furnishings", "move-all"):
            viewport.CancelInteraction()
            viewport.panOffset = point(originalPan)
            viewport.SetSelection([], notify = True)
            viewport.hoverPosition = point(300, 250)
            viewport.isPanning = mode.startswith("pan")
            if mode.startswith("move-"):
                objects = ([obj for obj in viewport.walls if type(obj) is Wall] if mode == "move-walls" else
                           viewport.furnishings if mode == "move-furnishings" else
                           viewport.walls + viewport.windows + viewport.furnishings + viewport.labels)
                viewport.SetSelection([(obj, None) for obj in objects])
                viewport.interactionBefore = viewport.CaptureState()
                viewport.dragStart = point(300, 250)
                viewport.StartGroupDrag()
                viewport.isDragging = True
            samples = []
            for frame in range(17):
                start = perf_counter()
                if mode.startswith("pan"):
                    viewport.panOffset = originalPan + (point(frame * 3, frame) if mode == "pan" else point(frame * .7, frame * .3))
                    viewport.update()
                elif mode == "hover":
                    viewport.hoverPosition = point(300 + frame, 250)
                    viewport.update()
                else:
                    viewport.UpdateInteraction(point(330 + frame * .73, 273 + frame * .31), QtCore.Qt.KeyboardModifier.NoModifier)
                app.processEvents()
                if frame >= 5:
                    samples.append((perf_counter() - start) * 1000)
            profiler = cProfile.Profile()
            profiler.enable()
            for frame in range(4):
                if mode.startswith("pan"):
                    viewport.panOffset = originalPan + (point(frame * 3, frame) if mode == "pan" else point(frame * .7, frame * .3))
                    viewport.update()
                elif mode == "hover":
                    viewport.hoverPosition = point(300 + frame, 250)
                    viewport.update()
                else:
                    viewport.UpdateInteraction(point(330 + frame * .73, 273 + frame * .31), QtCore.Qt.KeyboardModifier.NoModifier)
                app.processEvents()
            profiler.disable()
            stream = io.StringIO()
            pstats.Stats(profiler, stream = stream).strip_dirs().sort_stats("cumulative").print_stats(28)
            results[mode] = {"medianMs": statistics.median(samples), "maxMs": max(samples), "profile": stream.getvalue()}
            print(f"{mode}: {results[mode]['medianMs']:.2f} ms", flush = True)
            print(stream.getvalue(), flush = True)
            viewport.isPanning = False
        viewport.CancelInteraction()
        window.close()
    if len(arguments) > 1:
        Path(arguments[1]).write_text(json.dumps(results, indent = 2), encoding = "utf-8")


if __name__ == "__main__":
    Main()
