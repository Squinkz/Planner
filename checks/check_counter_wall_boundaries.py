"""Separate counter contours, isolated attachments and collision rollback."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Counter
from theme import BuildStyle
from planner_app.graphics.palette import themeColors
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    point = QtCore.QPointF
    v.snapEnabled = False
    wall = Wall(point(-1500, 0), point(1500, 0), 240)
    counter = Counter(point(-1000, -420), point(1000, -420))
    v.walls = [wall, counter]
    v.SetSelection([])
    assert v.CounterFits(counter) and v.OpeningsValid()
    image = v.grab().toImage()
    pixel = v.WorldToViewport(point(0, -120)).toPoint()
    assert image.pixelColor(pixel).name() != QtGui.QColor(themeColors["canvas"]).name()
    image.save(str(Path(__file__).resolve().parent.parent / "screenshots" / "counter-wall-boundary.png"))
    # Coincident centerline vertices still cannot create cross-class attachments.
    counter.firstVertex = point(wall.firstVertex)
    counter.secondVertex = point(-1500, -1500)
    for source, other in ((counter, wall), (wall, counter)):
        v.selectedWall = source
        for index in (None, 0):
            v.selectedVertex = index
            assert all(obj is not other for obj, vertexIndex, position in v.AttachedVertices(source))
        source.firstMiter = .7
        other.firstMiter = .3
        v.PropagateMiter(source, 0)
        assert other.firstMiter == .3
    counter.firstVertex, counter.secondVertex = point(-1000, -600), point(1000, -600)
    v.SetSelection([(counter, None)])
    before = v.CaptureState()
    start = v.WorldToViewport(point(0, -600)).toPoint()
    end = v.WorldToViewport(point()).toPoint()
    QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, pos = start)
    event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, point(end), point(v.mapToGlobal(end)),
                             QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.LeftButton,
                             QtCore.Qt.KeyboardModifier.NoModifier)
    app.sendEvent(v, event)
    assert not v.CounterFits(counter)
    assert counter.firstVertex.y() == 0  # Invalid previews keep moving through walls.
    invalidImage = v.grab().toImage()
    invalidPixel = v.WorldToViewport(point(0, 300)).toPoint()
    assert invalidImage.pixelColor(invalidPixel).name() == QtGui.QColor(themeColors["invalidOutline"]).name()
    QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, pos = end)
    assert v.CaptureState()[0] == before[0] and not v.undoHistory
    # A wall moved into a counter is invalid too, and never carries it along.
    v.SetSelection([(wall, None)])
    originalCounter = point(counter.firstVertex)
    Drag(v, v.WorldToViewport(point()).toPoint(), v.WorldToViewport(point(0, -600)).toPoint())
    assert wall.firstVertex == point(-1500, 0) and counter.firstVertex == originalCounter
    assert not v.undoHistory
    # Actual wall faces win over their centerline control endpoints.
    target = Wall(point(1000, -1000), point(1000, 1000), 240)
    for cls in (Wall, Counter):
        source = cls(point(-500, 0), point(500, 0), 120 if cls is Wall else 600)
        v.walls = [source, target]
        v.connectedEnabled = False
        v.snapEnabled = True
        v.gridSnapEnabled = v.midpointSnapEnabled = False
        v.SetSelection([(source, None)])
        Drag(v, v.WorldToViewport(point()).toPoint(), v.WorldToViewport(point(350, 0)).toPoint())
        assert abs(source.secondVertex.x() - 880) < .01, source.secondVertex
        assert source.firstVertex.y() == 0
        if cls is Counter:
            assert v.CounterFits(source)
        v.Undo()
        v.SetSelection([(source, 1)])
        Drag(v, v.WorldToViewport(point(500, 0)).toPoint(), v.WorldToViewport(point(850, 0)).toPoint())
        assert abs(source.secondVertex.x() - 880) < .01, source.secondVertex
        v.Undo()
    # Repainting moving geometry must not rebuild unchanged snap contours;
    # changing a target's width must update its actual face coordinates.
    source = Wall(point(-500, 0), point(500, 0), 120)
    v.walls = [source, target]
    v.SetSelection([(source, None)])
    firstTargets = v.StairSnapTargets(source)
    assert point(880, -1000) in firstTargets
    v.grab()
    with patch.object(v, "ConnectedWallPath", wraps = v.ConnectedWallPath) as contours:
        assert v.StairSnapTargets(source) is firstTargets
        assert contours.call_count == 0
    target.width = 300
    assert point(850, -1000) in v.StairSnapTargets(source)
    assert point(880, -1000) not in v.StairSnapTargets(source)
    main.close()
    app.processEvents()


if __name__ == "__main__":
    Main()
