"""Verify independent grid, vertex and independent X/Y alignment snapping controls."""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtTest, QtGui, QtWidgets

from planner import MainWindow, Wall
from theme import BuildStyle


def SetOptions(window, grid, vertices, alignment, corners = None):
    window.snapOptions["midpoints"].setChecked(False)
    window.snapOptions["grid"].setChecked(grid)
    window.snapOptions["vertices"].setChecked(vertices)
    window.snapOptions["corners"].setChecked(vertices if corners is None else corners)
    window.snapOptions["alignment"].setChecked(alignment)
    window.snapButton.setChecked(True)


def Main():
    app = QtWidgets.QApplication([])
    if os.path.exists("C:/Windows/Fonts/segoeui.ttf"):
        QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    window = MainWindow()
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    none = QtCore.Qt.KeyboardModifier.NoModifier
    alt = QtCore.Qt.KeyboardModifier.AltModifier
    wall = Wall(point(37, 23), point(837, 523))
    viewport.walls = [wall]
    assert window.snapOptions["grid"].isChecked()
    assert window.snapOptions["vertices"].isChecked()
    assert window.snapOptions["corners"].isChecked() and viewport.cornerSnapEnabled
    assert window.snapOptions["alignment"].isChecked() and viewport.alignmentSnapEnabled
    assert window.snapOptions["midpoints"].isChecked() and viewport.midpointSnapEnabled

    SetOptions(window, True, False, False)
    assert viewport.SnapPosition(point(47, 33), none) == point(0, 0)
    SetOptions(window, False, True, False)
    assert viewport.SnapPosition(point(47, 33), none) == point(37, 23)
    assert viewport.SnapPosition(point(400, 400), none) == point(400, 400)

    SetOptions(window, False, False, True)
    assert viewport.SnapPosition(point(47, 311), none) == point(47, 311)
    assert not viewport.alignmentGuides
    SetOptions(window, False, True, True)
    assert viewport.SnapPosition(point(47, 311), none) == point(37, 311)
    assert viewport.SnapPosition(point(112, 311), none) == point(37, 311)  # 15 screen pixels.
    assert viewport.SnapPosition(point(142, 311), none) == point(142, 311)  # 21 screen pixels.
    assert viewport.SnapPosition(point(211, 33), none) == point(211, 23)
    assert viewport.SnapPosition(point(47, 33), none) == point(37, 23)  # Both components can align together.
    assert viewport.SnapPosition(point(400, 400), none) == point(400, 400)
    # Alignment coordinates remain available at every grid/zoom scale.
    viewport.walls = [Wall(point(37, 23), point(37, 523))]
    for zoom in (0.02, 1, 10, 100):
        viewport.zoom = zoom
        nearX = 37 + 3 / (viewport.basePixelsPerMillimeter * zoom)
        assert viewport.SnapPosition(point(nearX, 1e6), none) == point(37, 1e6)
    viewport.ResetView()
    viewport.walls = [wall]

    SetOptions(window, True, False, True)
    assert viewport.SnapPosition(point(47, 311), none) == point(0, 300)
    SetOptions(window, False, True, True)
    assert viewport.SnapPosition(point(47, 33), none) == point(37, 23)
    SetOptions(window, True, True, True)
    assert viewport.SnapPosition(point(47, 33), none) == point(37, 23)
    assert viewport.SnapPosition(point(47, 311), none) == point(37, 300)

    # Main toggle controls all options without forgetting the choices. Alt
    # continues to invert the effective toggle until released.
    raw = point(47, 311)
    assert viewport.SnapPosition(raw, alt) == raw
    window.snapButton.setChecked(False)
    assert all(window.snapOptions[option].isChecked() for option in ("grid", "vertices", "alignment"))
    assert not window.snapOptions["midpoints"].isChecked()
    assert viewport.SnapPosition(raw, none) == raw
    assert viewport.SnapPosition(raw, alt) == point(37, 300)
    window.snapButton.setChecked(True)

    for checkBox in window.snapOptions.values():
        checkBox.setChecked(False)
    assert not window.snapButton.isChecked() and not viewport.snapEnabled
    assert viewport.SnapPosition(raw, alt) == raw
    window.snapButton.setChecked(True)
    assert window.snapOptions["grid"].isChecked()
    assert not window.snapOptions["vertices"].isChecked()
    assert not window.snapOptions["alignment"].isChecked()
    assert viewport.SnapPosition(raw, none) == point(0, 300)

    # The moving vertex must not align to its own old position.
    SetOptions(window, False, True, True)
    viewport.selectedWall = wall
    viewport.selectedVertex = 0
    viewport.dragStart = viewport.WorldToViewport(wall.firstVertex)
    assert viewport.SnapPosition(point(47, 311), none) == point(47, 311)
    viewport.dragStart = None
    SetOptions(window, True, True, True)
    viewport.selectedWall = None
    app.processEvents()
    window.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "snap-options-preview.png"))
    for baseState in (True, False):
        window.snapButton.setChecked(baseState)
        focusWidget = window.snapOptions["grid"]
        focusWidget.setFocus()
        QtTest.QTest.keyPress(focusWidget, QtCore.Qt.Key.Key_Alt)
        assert viewport.snapEnabled == baseState
        assert window.snapButton.isChecked() != baseState
        QtTest.QTest.keyRelease(focusWidget, QtCore.Qt.Key.Key_Alt)
        assert viewport.snapEnabled == baseState
        assert window.snapButton.isChecked() == baseState
    QtTest.QTest.keyPress(focusWidget, QtCore.Qt.Key.Key_Alt)
    QtWidgets.QApplication.sendEvent(app, QtCore.QEvent(QtCore.QEvent.Type.ApplicationDeactivate))
    assert not window.altHeld and window.snapButton.isChecked() == viewport.snapEnabled
    QtTest.QTest.keyRelease(focusWidget, QtCore.Qt.Key.Key_Alt)

    window.close()
    print("PASS: independent snap types, combined priorities, independent X/Y alignment, zoom invariance, Alt inversion and checkbox/main-toggle rules.")


if __name__ == "__main__":
    Main()
