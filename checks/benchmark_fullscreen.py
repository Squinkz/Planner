"""Read-only comparison of scene redraw costs in normal and viewport-only layouts."""
import cProfile
import io
import json
import os
import pstats
import statistics
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from planner_app.project_codec import DecodeProject
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    recovery = Path(os.environ["LOCALAPPDATA"]) / "Planner/session.json"
    if recovery.exists():
        data = json.loads(recovery.read_text(encoding = "utf-8"))
        main.ApplyProject(DecodeProject(data["project"], main.viewport.furnishingDefinitions), None)
    main.showNormal()
    main.resize(1440, 900)
    app.processEvents()
    v = main.viewport
    v.performanceTimer.stop()
    main.sessionPollTimer.stop()
    results = {}
    for enabled in (False, True, False):
        main.SetViewportOnlyMode(enabled)
        app.processEvents()
        for index in range(3):
            v.repaint()
        v.renderSamples.clear()
        profiler = cProfile.Profile()
        profiler.enable()
        for index in range(30):
            v.hoverPosition = QtCore.QPointF(100 + index, 150)
            v.repaint()
        profiler.disable()
        stream = io.StringIO()
        pstats.Stats(profiler, stream = stream).strip_dirs().sort_stats("tottime").print_stats(18)
        results["fullscreen" if enabled else "normal"] = {
            "viewport": [v.width(), v.height()],
            "medianRenderMs": statistics.median(duration for timestamp, duration in v.renderSamples),
            "profile": stream.getvalue(), "walls": len(v.walls), "furnishings": len(v.furnishings)}
    output = Path(__file__).resolve().parent.parent / "diagnostics/fullscreen-performance.json"
    output.write_text(json.dumps(results, indent = 2), encoding = "utf-8")
    main.close()


if __name__ == "__main__":
    Main()
