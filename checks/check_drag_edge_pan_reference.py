"""Reference/filter, calibration and native catalogue drag edge-pan routes."""
import os
from pathlib import Path
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from check_drag_edge_pan import Mouse, Tick


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.sessionTimer.stop()
    main.sessionPollTimer.stop()
    main.show()
    app.processEvents()
    v, reference = main.viewport, main.referenceImage
    v.performanceTimer.stop()
    v.snapEnabled = False
    point, types = QtCore.QPointF, QtCore.QEvent.Type
    main.sidebarTabs.setCurrentWidget(main.visibilityPage)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "edge-pan.png"
        image = QtGui.QImage(100, 80, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtCore.Qt.GlobalColor.white)
        assert image.save(str(path)) and reference.Load(path)
        reference.Show()
        start = v.WorldToViewport(point(*reference.state["center"]))
        edge = point(v.width() + 20, start.y())
        Mouse(v, types.MouseButtonPress, start)
        Mouse(v, types.MouseMove, edge)
        assert v.dragPanTimer.isActive()
        Tick(v)
        assert QtCore.QLineF(v.WorldToViewport(point(*reference.state["center"])), edge).length() < 1e-6
        Mouse(v, types.MouseButtonRelease, edge)
        assert not v.dragPanTimer.isActive()
        calibration = reference.calibration
        calibration.Start()
        start = v.DrawingRect().center()
        Mouse(v, types.MouseButtonPress, start)
        fixed = point(calibration.points[0])
        Mouse(v, types.MouseMove, edge)
        assert calibration.draggedPoint == 1 and v.dragPanTimer.isActive()
        Tick(v)
        assert calibration.points[0] == fixed
        assert QtCore.QLineF(v.WorldToViewport(calibration.points[1]), edge).length() < 1e-6
        Mouse(v, types.MouseButtonRelease, edge)
        assert not v.dragPanTimer.isActive()
        calibration.Stop()
        start = v.WorldToViewport(point(*reference.state["center"]))
        if not v.DrawingRect().contains(start):
            reference.state["center"] = list(v.ViewportToWorld(v.DrawingRect().center()).toTuple())
            start = v.DrawingRect().center()
        Mouse(v, types.MouseButtonPress, start)
        Mouse(v, types.MouseMove, edge)
        assert v.dragPanTimer.isActive()
        QtWidgets.QApplication.sendEvent(app, QtCore.QEvent(types.ApplicationDeactivate))
        assert not v.dragPanTimer.isActive()
        reference.Hide()
    v.walls, v.windows, v.furnishings = [], [], []
    v.guiDragActive = True
    v.guiDragCancelled = False
    mime = QtCore.QMimeData()
    mime.setData("application/x-planner-furnishing", b"desk")
    left = QtCore.Qt.MouseButton.LeftButton
    modifiers = QtCore.Qt.KeyboardModifier.NoModifier
    actions = QtCore.Qt.DropAction.CopyAction
    position = QtCore.QPoint(v.width() - 3, v.height() // 2)
    enter = QtGui.QDragEnterEvent(position, actions, mime, left, modifiers)
    QtWidgets.QApplication.sendEvent(v, enter)
    assert enter.isAccepted()
    move = QtGui.QDragMoveEvent(position, actions, mime, left, modifiers)
    QtWidgets.QApplication.sendEvent(v, move)
    assert move.isAccepted() and v.dragPanTimer.isActive()
    previous = point(v.panOffset)
    Tick(v)
    assert v.panOffset.x() < previous.x()
    center = v.WorldToViewport((v.furnishingPreview.firstVertex + v.furnishingPreview.secondVertex) / 2)
    assert QtCore.QLineF(center, point(position)).length() < 1e-6
    QtWidgets.QApplication.sendEvent(v, QtGui.QDragLeaveEvent())
    assert not v.dragPanTimer.isActive() and v.dragPanMimeData is None
    QtWidgets.QApplication.sendEvent(v, QtGui.QDragEnterEvent(position, actions, mime, left, modifiers))
    QtWidgets.QApplication.sendEvent(v, QtGui.QDragMoveEvent(position, actions, mime, left, modifiers))
    assert v.dragPanTimer.isActive()
    historyLength = len(v.undoHistory)
    drop = QtGui.QDropEvent(point(position), actions, mime, left, modifiers)
    QtWidgets.QApplication.sendEvent(v, drop)
    assert drop.isAccepted() and len(v.furnishings) == 1
    assert len(v.undoHistory) == historyLength + 1
    assert not v.dragPanTimer.isActive() and v.dragPanMimeData is None
    v.guiDragActive = False
    main.close()
    print("PASS: reference image, calibration, deactivation, catalogue preview following and native drag exit")


if __name__ == "__main__":
    Main()
