"""Wall drags preview furnishing collisions and commit only valid releases."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Window
from furnishings import Furnishing
from check_stair_drag_preview import Move


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    window = MainWindow()
    window.SetThemes(uiTheme = "Dark UI", canvasTheme = "Dark Canvas")  # Fixed palette for pixel assertions.
    window.show()
    app.processEvents()
    viewport = window.viewport
    viewport.snapEnabled = False
    point = QtCore.QPointF
    wall = Wall(point(-1500, 1000), point(1500, 1000), 240)
    opening = Window(wall, .3, .5)
    viewport.walls = [wall]
    viewport.windows = [opening]
    viewport.furnishings = [Furnishing(viewport.furnishingDefinitions["desk"])]
    viewport.SetSelection([(wall, None)])
    before = viewport.CaptureState()
    furnishingSample = viewport.WorldToViewport(point(-400, 300)).toPoint()
    furnishingColor = viewport.grab().toImage().pixelColor(furnishingSample)
    left = QtCore.Qt.MouseButton.LeftButton
    start = viewport.WorldToViewport(point(900, 1000)).toPoint()
    QtTest.QTest.mousePress(viewport, left, pos = start)
    end = Move(viewport, point(900, 0))
    assert wall.firstVertex.y() == 0 and not viewport.OpeningsValid()
    image = viewport.grab().toImage()
    assert image.pixelColor(furnishingSample) == furnishingColor
    sample = viewport.WorldToViewport(point(900, 0)).toPoint()
    color = image.pixelColor(sample)
    assert color.blue() - color.red() < 50, color.name()
    QtTest.QTest.mouseRelease(viewport, left, pos = end)
    assert viewport.CaptureState()[0] == before[0] and viewport.CaptureState()[3] == before[3]
    assert not viewport.undoHistory
    # The wall can cross an invalid position and commit a valid one beyond it.
    QtTest.QTest.mousePress(viewport, left, pos = start)
    Move(viewport, point(900, 0))
    end = Move(viewport, point(900, -1000))
    assert wall.firstVertex.y() == -1000 and viewport.OpeningsValid()
    QtTest.QTest.mouseRelease(viewport, left, pos = end)
    assert len(viewport.undoHistory) == 1
    viewport.Undo()
    assert viewport.CaptureState()[0] == before[0]
    # Vertex rotation must also preview collisions and roll back on release.
    viewport.SetSelection([(wall, 0)])
    QtTest.QTest.mousePress(viewport, left, pos = viewport.WorldToViewport(wall.firstVertex).toPoint())
    end = Move(viewport, point(-1500, -1000))
    assert wall.firstVertex == point(-1500, -1000) and not viewport.OpeningsValid()
    image = viewport.grab().toImage()
    assert image.pixelColor(end).name() == "#697680"
    QtTest.QTest.mouseRelease(viewport, left, pos = end)
    assert viewport.CaptureState()[0] == before[0] and not viewport.undoHistory
    # An invalid duplicate is removed, along with its duplicated child.
    viewport.SetSelection([(wall, None)])
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    QtTest.QTest.mousePress(viewport, left, shift, start)
    end = Move(viewport, point(900, 0), shift)
    assert len(viewport.walls) == 2 and viewport.selectedWall.firstVertex.y() == 0
    QtTest.QTest.mouseRelease(viewport, left, shift, end)
    assert viewport.walls == [wall] and viewport.windows == [opening] and not viewport.undoHistory
    # Group release cancels the whole gesture if one wall touches furniture.
    other = Wall(point(-1500, 2000), point(1500, 2000))
    viewport.walls.append(other)
    viewport.SetSelection([(wall, None), (other, None)])
    groupBefore = viewport.CaptureState()
    QtTest.QTest.mousePress(viewport, left, pos = start)
    end = Move(viewport, point(900, 0))
    assert wall.firstVertex.y() == 0 and other.firstVertex.y() == 1000
    QtTest.QTest.mouseRelease(viewport, left, pos = end)
    assert viewport.CaptureState()[0] == groupBefore[0] and not viewport.undoHistory
    window.close()
    print("PASS: wall/vertex/group/duplicate furnishing collision previews, grey feedback, valid crossing, rollback and undo.")


if __name__ == "__main__":
    Main()
