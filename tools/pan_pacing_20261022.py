"""Queued pan input versus paint timing; does not measure monitor presentation."""
import json
import os
from pathlib import Path
import sys
import threading
from time import perf_counter, sleep

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
root = Path(__file__).resolve().parent.parent
(root / "diagnostics").mkdir(exist_ok = True)
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner_app.models import Furnishing, Wall
from planner_app.viewport.widget import DrawingViewport
from planner_app.graphics.theme import ApplyApplicationTheme


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    v = DrawingViewport()
    v.resize(1440, 900)
    v.performanceTimer.stop()
    v.showTips = False
    v.zoom = .4
    point = QtCore.QPointF
    v.walls, v.furnishings = [], []
    for index in range(160):
        center = point((index % 16 - 8) * 1400, (index // 16 - 5) * 1600)
        v.walls.append(Wall(center, center + point(1100, 0)))
        v.furnishings.append(Furnishing(v.furnishingDefinitions["desk"], center + point(500, 650)))
    v.show()
    app.processEvents()
    v.SetRenderDiagnosticsEnabled(True)
    press = QtCore.QPoint(250, 250)
    QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.MiddleButton, pos = press)
    initialPan = point(v.panOffset)
    globalOrigin = point(v.mapToGlobal(QtCore.QPoint()))
    finished = threading.Event()
    posted = []
    rate = 250
    duration = 2.4
    started = perf_counter()

    def Produce():
        for index in range(round(rate * duration)):
            due = started + (index + 1) / rate
            sleep(max(0, due - perf_counter()))
            elapsed = perf_counter() - started
            position = point(press) + point(elapsed * 80, elapsed * 20)
            event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, position, globalOrigin + position,
                                     QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.MiddleButton,
                                     QtCore.Qt.KeyboardModifier.NoModifier)
            event.setTimestamp(round(elapsed * 1000) + 1)
            posted.append((elapsed, position.x(), position.y()))
            QtCore.QCoreApplication.postEvent(v, event)
        finished.set()

    producer = threading.Thread(target = Produce)
    producer.start()
    loop = QtCore.QEventLoop()
    stopTimer = QtCore.QTimer()
    stopTimer.setInterval(20)

    def Finish():
        if finished.is_set() and v.renderDiagnostics.inputSequence >= len(posted) + 1:
            loop.quit()

    stopTimer.timeout.connect(Finish)
    stopTimer.start()
    QtCore.QTimer.singleShot(10000, loop.quit)
    loop.exec()
    producer.join()
    stopTimer.stop()
    app.processEvents()
    report = v.renderDiagnostics.Report()
    report["probe"] = {"rateHz": rate, "durationSeconds": duration, "posted": len(posted),
                       "finalPan": [v.panOffset.x(), v.panOffset.y()],
                       "expectedPan": [initialPan.x() + posted[-1][1] - press.x(), initialPan.y() + posted[-1][2] - press.y()]}
    QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.MiddleButton, pos = QtCore.QPoint(round(posted[-1][1]), round(posted[-1][2])))
    suffix = sys.argv[1] if len(sys.argv) > 1 else "latest"
    path = root / "diagnostics" / ("pan-pacing-20261022-" + suffix + ".json")
    path.write_text(json.dumps(report, indent = 2), encoding = "utf-8")
    print(json.dumps({"summary": report["summary"], "probe": report["probe"]}, indent = 2))
    v.close()


if __name__ == "__main__":
    Main()
