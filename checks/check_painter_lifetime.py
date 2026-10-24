"""Painter scopes end even when a Qt paint callback raises and keeps its traceback."""
import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.ui.color_picker import ColorPlane
from planner_app.project_codec import DecodeProject


def Main():
    with tempfile.TemporaryDirectory(dir = Path(__file__).parent) as folder:
        os.environ["PLANNER_SESSION_PATH"] = str(Path(folder) / "session.json")
        os.environ["PLANNER_STARTUP_PATH"] = str(Path(folder) / "startup.plan")
        app = QtWidgets.QApplication([])
        ApplyApplicationTheme(app)
        main = MainWindow()
        main.show()
        app.processEvents()
        v = main.viewport
        v.walls = [Wall(QtCore.QPointF(-1000, 0), QtCore.QPointF(1000, 0), 240)]
        painters, errors, messages = [], [], []
        failTarget = None
        failMeasurements = False
        recordedLabels = []
        class TrackedPainter(QtGui.QPainter):
            def __init__(self, device):
                super().__init__(device)
                painters.append(self)

            def fillRect(self, *args):
                if self.device() is failTarget:
                    raise RuntimeError("Injected color-plane paint failure")
                return super().fillRect(*args)

            def fontMetrics(self):
                if failMeasurements and isinstance(self.device(), QtGui.QPicture):
                    raise RuntimeError("Injected measurement recording failure")
                return super().fontMetrics()

            def drawText(self, *args):
                assert self.isActive(), "Text was drawn after ending its painter"
                if isinstance(self.device(), QtGui.QPicture):
                    recordedLabels.append(args[-1])
                return super().drawText(*args)

        previousHandler = QtCore.qInstallMessageHandler(lambda kind, context, message: messages.append(message))
        previousHook = sys.excepthook
        sys.excepthook = lambda kind, error, traceback: errors.append(error)
        try:
            with patch.object(QtGui, "QPainter", TrackedPainter), contextlib.redirect_stderr(io.StringIO()):
                v.showMeasurements = True
                v.measurementVisibility = dict.fromkeys(v.measurementVisibility, True)
                saved = main.BuildProjectData(includeHistory = False)
                # Repeated project loads must rebuild measurement commands with an active painter.
                for iteration in range(2):
                    main.ApplyProject(DecodeProject(saved, v.furnishingDefinitions), None)
                    before = len(recordedLabels)
                    v.grab()
                    assert len(recordedLabels) > before and v.measurementPictures
                    assert all(not painter.isActive() for painter in painters)
                main.ApplyProject(DecodeProject(saved, v.furnishingDefinitions), None)
                failMeasurements = True
                try:
                    v.grab()
                except RuntimeError as error:
                    errors.append(error)
                assert all(not painter.isActive() for painter in painters)
                failMeasurements = False
                for drawingMethod in ("DrawGridBackground", "DrawScene"):
                    for name in ("background", "scene", "pan"):
                        v.rasterCacheBudget.Clear(name)
                    before = len(painters)
                    with patch.object(v, drawingMethod, side_effect = RuntimeError("Injected viewport paint failure")):
                        try:
                            v.grab()
                        except RuntimeError as error:
                            errors.append(error)
                    assert len(painters) >= before + 2, "Nested cache painter failure was not exercised"
                    assert all(not painter.isActive() for painter in painters)
                main.sidebarTabs.setCurrentWidget(main.exportPanel)
                with patch.object(v.exportOverlay, "DrawPreview", side_effect = RuntimeError("Injected export paint failure")):
                    try:
                        v.grab()
                    except RuntimeError as error:
                        errors.append(error)
                assert all(not painter.isActive() for painter in painters)
                plane = ColorPlane()
                failTarget = plane
                try:
                    plane.grab()
                except RuntimeError as error:
                    errors.append(error)
                assert all(not painter.isActive() for painter in painters)
                failTarget = None
                plane.close()
                v.grab()
            assert errors, "Injected drawing failures were not observed"
            assert not any("active painter" in message or "being painted" in message for message in messages), messages
            assert not any("Painter not active" in message or "Unbalanced save/restore" in message for message in messages), messages
        finally:
            sys.excepthook = previousHook
            QtCore.qInstallMessageHandler(previousHandler)
            main.close()
        print("PASS: measurement recording after reload and exception cleanup for viewport, cache, export and color-plane painters")


if __name__ == "__main__":
    Main()
