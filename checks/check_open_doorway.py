"""Open doorway placement, exposed jambs, dimensions and editing."""
import os
import sys
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall, OpenDoorway, DrawOpeningSymbol


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    main = MainWindow()
    main.show()
    app.processEvents()
    viewport = main.viewport
    viewport.unitsMode = "Adaptive Metric"
    point = QtCore.QPointF
    wall = Wall(point(-2500, 0), point(2500, 0), 240)
    viewport.walls = [wall]
    center = viewport.WorldToViewport(point())
    mime = QtCore.QMimeData()
    mime.setData("application/x-planner-open-doorway", b"open-doorway")
    left = QtCore.Qt.MouseButton.LeftButton
    none = QtCore.Qt.KeyboardModifier.NoModifier
    enter = QtGui.QDragEnterEvent(center.toPoint(), QtCore.Qt.DropAction.CopyAction, mime, left, none)
    QtWidgets.QApplication.sendEvent(viewport, enter)
    move = QtGui.QDragMoveEvent(center.toPoint(), QtCore.Qt.DropAction.CopyAction, mime, left, none)
    QtWidgets.QApplication.sendEvent(viewport, move)
    assert enter.isAccepted() and type(viewport.windowDropPreview) is OpenDoorway
    drop = QtGui.QDropEvent(center, QtCore.Qt.DropAction.CopyAction, mime, left, none)
    QtWidgets.QApplication.sendEvent(viewport, drop)
    assert drop.isAccepted()
    doorway = viewport.windows[0]
    assert type(doorway) is OpenDoorway and abs(doorway.length - 900) < .01
    assert main.selectionLabel.text().startswith("Open Doorway")
    assert not main.doorProperties.isVisible()
    assert main.openDoorwayButton.toolTip() == "Open doorway"
    assert not main.openDoorwayButton.icon().isNull()
    assert viewport.PlaceWindow(center, OpenDoorway) is None
    main.propertyFields["length"].setValue(1.2)
    assert abs(doorway.length - 1200) < .01
    viewport.Undo()
    assert abs(doorway.length - 900) < .01
    viewport.Redo()
    assert abs(doorway.length - 1200) < .01
    assert type(viewport.CloneOpening(doorway, wall)) is OpenDoorway
    assert not hasattr(doorway, "swingsOutwards")
    # Both exposed wall faces split at the two jambs, even on angled walls.
    for endpoint in (point(5000, 0), point(0, 5000), point(3000, 4000)):
        parent = Wall(point(), endpoint)
        viewport.windows = [OpenDoorway(parent, .2, .4)]
        spans = viewport.WallDimensions([parent], viewport.ConnectedWallPath([parent]))
        lengths = sorted(QtCore.QLineF(first, second).length() for first, second, owners in spans)
        assert len(lengths) == 6
        assert all(abs(a - b) < .01 for a, b in zip(lengths, [1000, 1000, 1000, 1000, 3000, 3000]))
    # The wall faces and jambs outline the doorway; its interior stays transparent.
    image = QtGui.QImage(240, 100, QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(image)
    DrawOpeningSymbol(painter, point(20, 50), point(220, 50), 40, OpenDoorway)
    painter.end()
    assert image.pixelColor(20, 50).alpha() > 0
    assert image.pixelColor(220, 50).alpha() > 0
    assert image.pixelColor(120, 30).alpha() > 0
    assert image.pixelColor(120, 70).alpha() > 0
    assert all(image.pixelColor(x, y).alpha() == 0 for x in range(30, 210) for y in range(32, 68))
    # The actual wall cut reveals precisely the same grid as an empty viewport.
    viewport.walls = []
    viewport.windows = []
    viewport.SetSelection([])
    empty = viewport.grab().toImage()
    viewport.walls = [wall]
    viewport.windows = [doorway]
    cut = viewport.grab().toImage()
    for offset in (point(0, 0), point(100, 70), point(-100, -70)):
        pixel = viewport.WorldToViewport(offset).toPoint()
        assert cut.pixelColor(pixel) == empty.pixelColor(pixel)
    for offset in (point(100, 120), point(100, -120)):
        pixel = viewport.WorldToViewport(offset).toPoint()
        assert cut.pixelColor(pixel) != empty.pixelColor(pixel)
    main.close()
    print("PASS: Open Doorway native drop, size edits, undo, cloning, both-side dimensions and clear opening rendering.")


if __name__ == "__main__":
    Main()
