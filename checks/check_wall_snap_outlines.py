"""Native snapped wall dragging must preserve exterior outlines at float precision."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall


def Main():
    app = QtWidgets.QApplication([])
    if os.path.exists("C:/Windows/Fonts/segoeui.ttf"):
        QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    main = MainWindow()
    main.show()
    app.processEvents()
    viewport = main.viewport
    point = QtCore.QPointF
    viewport.ResetView()
    viewport.snapEnabled = viewport.gridSnapEnabled = viewport.alignmentSnapEnabled = True
    viewport.vertexSnapEnabled = viewport.midpointSnapEnabled = True
    viewport.connectedEnabled = True
    viewport.connectedObjectsEnabled = False
    # Preserve the sub-picometer slopes produced by previous snapping operations.
    walls = [Wall(point(5100, -500), point(5100, -4300), 240),
             Wall(point(5100, -500), point(1800, -499.9999999999989), 240),
             Wall(point(7080, -440), point(7079.999999999999, -4000.0000000000005), 240),
             Wall(point(7080, -440), point(7960, -439.99999999999943), 240)]
    viewport.walls = walls
    viewport.SetSelection([])
    viewport.zoom = 1.7368512667967493
    viewport.panOffset += viewport.DrawingRect().center() - viewport.WorldToViewport(point(7520, -440))
    start = viewport.WorldToViewport(point(7520, -440)).toPoint()
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos = start)
    assert viewport.selectedWall is walls[-1] and viewport.dragAttachments
    guideCoordinates = set()
    for offsetX in (-24, 0, 19):
        for offsetY in range(-70, 71, 3):
            position = point(start) + point(offsetX, offsetY + .5)
            event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, position,
                                     point(viewport.mapToGlobal(position.toPoint())),
                                     QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.LeftButton,
                                     QtCore.Qt.KeyboardModifier.NoModifier)
            app.sendEvent(viewport, event)
            guideCoordinates.update(round(coordinate) for axis, coordinate in viewport.alignmentGuides if axis == 1)
            path = viewport.ConnectedWallPath(walls)
            previous = None
            for index in range(path.elementCount()):
                element = path.elementAt(index)
                current = viewport.ViewportToWorld(point(element.x, element.y))
                if not element.isMoveTo():
                    delta = current - previous
                    length = QtCore.QLineF(previous, current).length()
                    if length > .01:
                        parallel = False
                        for wall in walls:
                            axis = wall.secondVertex - wall.firstVertex
                            axis /= QtCore.QLineF(wall.firstVertex, wall.secondVertex).length()
                            cross = abs(delta.x() * axis.y() - delta.y() * axis.x()) / length
                            dot = abs(QtCore.QPointF.dotProduct(delta, axis)) / length
                            parallel |= min(cross, dot) < 1e-6
                        assert parallel, (position, previous, current, viewport.alignmentGuides)
                previous = current
            viewport.grab()  # Includes selected fills, guides and dimensions.
    assert -500 in guideCoordinates and (-380 in guideCoordinates or -620 in guideCoordinates), guideCoordinates
    viewport.UpdateInteraction(point(start) + point(-24, -40.5), QtCore.Qt.KeyboardModifier.NoModifier)
    viewport.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "wall-snap-outline.png"))
    viewport.CancelInteraction()
    main.close()


if __name__ == "__main__":
    Main()
