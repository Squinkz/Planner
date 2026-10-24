"""Verify window body snapping chooses the closest endpoint or midpoint without breaking bounds."""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtGui, QtWidgets

from check_history import Drag
from planner import MainWindow, Wall, Window, Door


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    alt = QtCore.Qt.KeyboardModifier.AltModifier
    window.snapOptions["vertices"].setChecked(False)
    window.snapOptions["alignment"].setChecked(False)
    parent = Wall(point(), point(5000, 0))
    opening = Window(parent, 123 / 5000, 1180 / 5000)
    viewport.walls = [parent]
    viewport.windows = [opening]
    for rootIndex, expectedFirst in ((0, 471.5), (1, 471.5)):
        opening.firstFraction = 123 / 5000
        opening.secondFraction = 1180 / 5000
        viewport.selectedWall = opening
        grab = point(273 if rootIndex == 0 else 1030, 0)
        start = viewport.WorldToViewport(grab).toPoint()
        Drag(viewport, start, start + QtCore.QPoint(70, 0))
        assert abs(opening.firstVertex.x() - expectedFirst) < 0.001
        assert abs(QtCore.QLineF(opening.firstVertex, opening.secondVertex).length() - 1057) < 0.001
        viewport.Undo()
        Drag(viewport, start, start + QtCore.QPoint(70, 0), alt)
        assert abs(opening.firstVertex.x() - 473) < 0.001
        viewport.Undo()

    # The midpoint snaps to nearby wall vertices independently of the grab location.
    window.snapOptions["vertices"].setChecked(True)
    window.snapOptions["grid"].setChecked(False)
    targetWall = Wall(point(1037, 0), point(1037, 800))
    viewport.walls.append(targetWall)
    viewport.selectedWall = opening
    start = viewport.WorldToViewport(point(273, 0)).toPoint()
    Drag(viewport, start, start + QtCore.QPoint(70, 0))
    assert abs(opening.firstVertex.x() - 123) < .001  # Other wall obstructs the requested snap.

    # Endpoint resizing keeps the dragged endpoint as its snapping root.
    targetWall.firstVertex = point(1537, 0)
    endpoint = viewport.WorldToViewport(opening.secondVertex).toPoint()
    Drag(viewport, endpoint, endpoint + QtCore.QPoint(70, 0))
    assert abs(opening.secondVertex.x() - 1180) < .001
    assert abs(opening.firstVertex.x() - 123) < 0.001

    # Alignment also works along the parent, even for a distant target vertex.
    window.snapOptions["grid"].setChecked(False)
    window.snapOptions["vertices"].setChecked(False)
    window.snapOptions["alignment"].setChecked(True)
    window.snapButton.setChecked(True)
    targetWall.firstVertex = point(1037, 800)
    Drag(viewport, start, start + QtCore.QPoint(70, 0))
    assert abs((opening.firstVertex.x() + opening.secondVertex.x()) / 2 - 1037) < 0.001
    viewport.Undo()

    # Angled parents retain exact collinearity while grid crossings set lengthwise position.
    viewport.walls = [parent]
    parent.secondVertex = point(4000, 3000)
    window.snapOptions["grid"].setChecked(True)
    window.snapOptions["alignment"].setChecked(False)
    viewport.selectedWall = opening
    grab = opening.firstVertex + (opening.secondVertex - opening.firstVertex) * 0.15
    start = viewport.WorldToViewport(grab).toPoint()
    Drag(viewport, start, start + QtCore.QPoint(60, -45))
    anchors = (opening.firstVertex, (opening.firstVertex + opening.secondVertex) / 2, opening.secondVertex)
    assert all(abs(anchor.x() * 3000 - anchor.y() * 4000) < 0.001 for anchor in anchors)
    assert any(min(abs(anchor.x() - round(anchor.x() / 100) * 100),
                   abs(anchor.y() - round(anchor.y() / 100) * 100)) < 0.001 for anchor in anchors)
    assert 0 <= opening.firstFraction < opening.secondFraction <= 1
    parent.firstVertex = point()
    parent.secondVertex = point(5000, 0)
    opening.firstFraction = 0.001
    opening.secondFraction = 0.2
    window.snapOptions["vertices"].setChecked(True)
    window.snapOptions["grid"].setChecked(False)
    viewport.selectedWall = parent
    start = viewport.WorldToViewport(point(1500, 0)).toPoint()
    Drag(viewport, start, start + QtCore.QPoint(6, -6))
    assert parent.firstVertex == point(30, 30)  # Carried windows cannot snap their own parent back.
    viewport.windows = []
    viewport.walls = [parent]
    window.snapOptions["grid"].setChecked(True)
    window.snapOptions["vertices"].setChecked(False)
    for openingType in (Window, Door):
        mime = QtCore.QMimeData()
        kind = "door" if openingType is Door else "window"
        mime.setData(f"application/x-planner-{kind}", kind.encode())
        for modifiers, expectedCenter in ((QtCore.Qt.KeyboardModifier.NoModifier, 1000), (alt, 1035)):
            expectedCenter = 1050 if openingType is Door and modifiers == QtCore.Qt.KeyboardModifier.NoModifier else expectedCenter
            position = viewport.WorldToViewport(point(1035, 0))
            enter = QtGui.QDragEnterEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                          QtCore.Qt.MouseButton.LeftButton, modifiers)
            QtWidgets.QApplication.sendEvent(viewport, enter)
            move = QtGui.QDragMoveEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                        QtCore.Qt.MouseButton.LeftButton, modifiers)
            QtWidgets.QApplication.sendEvent(viewport, move)
            preview = viewport.windowDropPreview
            assert move.isAccepted() and isinstance(preview, openingType)
            assert abs((preview.firstVertex.x() + preview.secondVertex.x()) / 2 - expectedCenter) < 0.001
            drop = QtGui.QDropEvent(position, QtCore.Qt.DropAction.CopyAction, mime,
                                    QtCore.Qt.MouseButton.LeftButton, modifiers)
            QtWidgets.QApplication.sendEvent(viewport, drop)
            placed = viewport.windows[-1]
            assert drop.isAccepted()
            assert abs((placed.firstVertex.x() + placed.secondVertex.x()) / 2 - expectedCenter) < 0.001
            viewport.Undo()

    # Each of the three roots can win, independent of opening type and grab location.
    window.snapOptions["grid"].setChecked(False)
    window.snapOptions["vertices"].setChecked(True)
    window.snapOptions["alignment"].setChecked(False)
    window.snapButton.setChecked(True)
    for openingType in (Window, Door):
        for firstTarget, middleTarget, secondTarget, expectedFirst in (
                (479, 1037, 1533, 476), (474, 1004, 1537, 474), (480, 1002, 1540, 473.5)):
            parent.firstVertex = point()
            parent.secondVertex = point(5000, 0)
            candidate = openingType(parent, 123 / 5000, 1180 / 5000)
            viewport.windows = [candidate]
            viewport.walls = [parent] + [Wall(point(x, 0), point(x, 1000))
                                        for x in (firstTarget, middleTarget, secondTarget)]
            viewport.selectedWall = candidate
            grab = viewport.WorldToViewport(point(273, 0)).toPoint()
            Drag(viewport, grab, grab + QtCore.QPoint(70, 0))
            assert abs(candidate.firstVertex.x() - 123) < .001  # All three targets obstruct the opening.
            assert abs(candidate.length - 1057) < .001

    window.close()
    print("PASS: closest endpoint/midpoint window and door snapping, endpoint resizing, grid/vertices/alignment, Alt, bounds and angled parents.")


if __name__ == "__main__":
    Main()
