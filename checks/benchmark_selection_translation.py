"""Measure native multi-selection movement and repaint with snapping disabled."""
import os
import sys
import tempfile
import time
from pathlib import Path
from statistics import median

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, DrawingViewport
from planner_app.models import Furnishing


def Main():
    # Optional local snapshots allow the same workload to compare implementations.
    if "--baseline" in sys.argv:
        for module, mixin in (("geometry", "GeometryMixin"), ("snapping", "SnappingMixin"), ("scene", "SceneEditingMixin")):
            namespace = {"__name__": f"planner_app.viewport.{module}"}
            exec((root / "scratch" / f"{module}-before-translation.py").read_text(), namespace)
            for name, method in vars(namespace[mixin]).items():
                if callable(method):
                    setattr(DrawingViewport, name, method)
    app = QtWidgets.QApplication([])
    point = QtCore.QPointF
    left = QtCore.Qt.MouseButton.LeftButton
    with tempfile.TemporaryDirectory() as sessionFolder:
        os.environ["PLANNER_SESSION_PATH"] = str(Path(sessionFolder) / "session.json")
        window = MainWindow()
        window.show()
        app.processEvents()
        viewport = window.viewport
        viewport.snapEnabled = False
        viewport.connectedEnabled = False
        for kind in ("walls", "furnishings"):
            viewport.walls = [Wall(point((i % 10) * 1600, (i // 10) * 1200),
                                   point((i % 10) * 1600 + 1000, (i // 10) * 1200), 120)
                              for i in range(100)]
            viewport.furnishings = ([Furnishing(viewport.furnishingDefinitions["desk"],
                                               point((i % 5) * 1400, -1200 - (i // 5) * 1000))
                                    for i in range(20)] if kind == "furnishings" else [])
            objects = viewport.furnishings if kind == "furnishings" else viewport.walls[:20]
            viewport.SetSelection([(obj, None) for obj in objects])
            app.processEvents()
            start = viewport.WorldToViewport((objects[0].firstVertex + objects[0].secondVertex) / 2).toPoint()
            QtTest.QTest.mousePress(viewport, left, pos = start)
            assert viewport.groupDrag
            samples = []
            for frame in range(60):
                position = point(start) + point(20 + frame * .73, 23 + frame * .31)
                event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, position,
                                         point(viewport.mapToGlobal(position.toPoint())),
                                         QtCore.Qt.MouseButton.NoButton, left,
                                         QtCore.Qt.KeyboardModifier.NoModifier)
                started = time.perf_counter()
                app.sendEvent(viewport, event)
                app.processEvents()
                samples.append((time.perf_counter() - started) * 1000)
            samples = samples[5:]
            print(f"20 {kind}, 100 walls, snapping off: median {median(samples):.2f} ms, "
                  f"p95 {sorted(samples)[int(len(samples) * .95)]:.2f} ms", flush = True)
            viewport.CancelInteraction()
        window.close()
        app.processEvents()


if __name__ == "__main__":
    Main()

