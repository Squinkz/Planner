"""Collect Python cycles on the GUI thread, where Qt objects may be destroyed."""
import gc
import time
from PySide6 import QtCore, QtWidgets


class GuiGarbageCollector(QtCore.QObject):
    def __init__(self, app):
        super().__init__(app)
        # Automatic collection runs in whichever thread allocates Python objects.
        # Recovery JSON decoding can otherwise destroy GUI wrappers on its worker.
        gc.disable()
        self.lastFullCollection = time.monotonic()
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.Collect)
        self.timer.start()
        app.aboutToQuit.connect(self.timer.stop)

    def Collect(self):
        from .viewport.widget import DrawingViewport
        app = QtWidgets.QApplication.instance()
        if app.mouseButtons() != QtCore.Qt.MouseButton.NoButton:
            return
        for window in app.topLevelWidgets():
            viewport = getattr(window, "viewport", None)
            if isinstance(viewport, DrawingViewport) and (viewport.dragStart is not None or viewport.pendingWall is not None or
                                                         viewport.furnishingHandleDrag is not None or viewport.guiDragActive or
                                                         getattr(window, "propertyDragBefore", None) is not None):
                return
        now = time.monotonic()
        if now - self.lastFullCollection >= 30:
            gc.collect()
            self.lastFullCollection = now
        elif gc.get_count()[0] >= gc.get_threshold()[0]:
            gc.collect(0)


def ConfigureGarbageCollection():
    app = QtWidgets.QApplication.instance()
    if not hasattr(app, "plannerGarbageCollector"):
        app.plannerGarbageCollector = GuiGarbageCollector(app)
