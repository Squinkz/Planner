"""Held D/S tools share previews, cycle types and place on valid releases."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Window, Door, SlidingDoor, PocketDoor, OpenDoorway, SilledWindow
from theme import BuildStyle


def Move(viewport, position, modifiers = QtCore.Qt.KeyboardModifier.NoModifier):
    screen = viewport.WorldToViewport(position)
    event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, screen,
                             QtCore.QPointF(viewport.mapToGlobal(screen.toPoint())),
                             QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.NoButton, modifiers)
    QtWidgets.QApplication.sendEvent(viewport, event)
    return screen.toPoint()


def Wheel(viewport, position, delta):
    screen = viewport.WorldToViewport(position)
    event = QtGui.QWheelEvent(screen, QtCore.QPointF(viewport.mapToGlobal(screen.toPoint())),
                             QtCore.QPoint(), QtCore.QPoint(0, delta), QtCore.Qt.MouseButton.NoButton,
                             QtCore.Qt.KeyboardModifier.NoModifier, QtCore.Qt.ScrollPhase.NoScrollPhase, False)
    QtWidgets.QApplication.sendEvent(viewport, event)


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    window = MainWindow()
    window.SetThemes(uiTheme = "Dark UI", canvasTheme = "Dark Canvas")  # Fixed palette for pixel assertions.
    window.show()
    app.processEvents()
    viewport = window.viewport
    viewport.snapEnabled = False
    viewport.zoom = .25
    point = QtCore.QPointF
    wall = Wall(point(-8000, 0), point(8000, 0), 240)
    viewport.walls = [wall]
    viewport.setFocus()
    left = QtCore.Qt.MouseButton.LeftButton
    QtTest.QTest.keyPress(viewport, QtCore.Qt.Key.Key_D)
    assert viewport.mode == "Door" and viewport.cursor().shape() == QtCore.Qt.CursorShape.BlankCursor
    assert window.doorButton.property("placementActive")
    assert window.doorButton.grab().toImage().pixelColor(0, 24).name() == "#72b8ff"
    thickness = window.wallWidthSelector.slider.value()
    sliderPosition = QtCore.QPointF(window.wallWidthSelector.slider.rect().center())
    for delta, objectType in ((-120, SlidingDoor), (120, Door)):
        wheel = QtGui.QWheelEvent(sliderPosition,
                                 QtCore.QPointF(window.wallWidthSelector.slider.mapToGlobal(sliderPosition.toPoint())),
                                 QtCore.QPoint(), QtCore.QPoint(0, delta), QtCore.Qt.MouseButton.NoButton,
                                 QtCore.Qt.KeyboardModifier.NoModifier, QtCore.Qt.ScrollPhase.NoScrollPhase, False)
        QtWidgets.QApplication.sendEvent(window.wallWidthSelector.slider, wheel)
        assert window.wallWidthSelector.slider.value() == thickness
        assert window.openingToolButtons[objectType].property("placementActive")
    invalid = Move(viewport, point(-6000, 1200))
    assert type(viewport.inactiveOpeningPreview) is Door and viewport.windowDropPreview is None
    QtTest.QTest.mouseClick(viewport, left, pos = invalid)
    assert not viewport.windows and not viewport.undoHistory
    position = Move(viewport, point(-6000, 0))
    assert type(viewport.windowDropPreview) is Door
    QtTest.QTest.mousePress(viewport, left, pos = position)
    assert not viewport.windows
    QtTest.QTest.mouseRelease(viewport, left, pos = position)
    assert len(viewport.windows) == 1 and type(viewport.windows[-1]) is Door
    firstDoor = viewport.windows[-1]
    # A second click stays in mode; clicking an occupied point adds nothing.
    QtTest.QTest.mouseClick(viewport, left, pos = position)
    assert len(viewport.windows) == 1
    QtTest.QTest.mouseClick(viewport, left, pos = Move(viewport, point(-4000, 0)))
    assert len(viewport.windows) == 2 and len(viewport.undoHistory) == 2
    zoom = viewport.zoom
    Wheel(viewport, point(-1500, 0), -120)
    assert viewport.zoom == zoom and type(viewport.windowDropPreview) is SlidingDoor
    assert window.slidingDoorButton.property("placementActive") and not window.doorButton.property("placementActive")
    QtTest.QTest.mouseClick(viewport, left, pos = Move(viewport, point(-1500, 0)))
    assert type(viewport.windows[-1]) is SlidingDoor
    Wheel(viewport, point(1000, 0), -120)
    assert type(viewport.windowDropPreview) is PocketDoor and window.pocketDoorButton.property("placementActive")
    QtTest.QTest.mouseClick(viewport, left, pos = Move(viewport, point(1000, 0)))
    assert type(viewport.windows[-1]) is PocketDoor
    Wheel(viewport, point(4000, 0), -120)
    assert type(viewport.windowDropPreview).__name__ == "BarnDoor"
    assert window.barnDoorButton.property("placementActive")
    Wheel(viewport, point(4000, 0), -120)
    assert type(viewport.windowDropPreview).__name__ == "BifoldDoor"
    assert window.bifoldDoorButton.property("placementActive")
    Wheel(viewport, point(4000, 0), -120)
    assert type(viewport.windowDropPreview) is OpenDoorway
    assert window.openDoorwayButton.property("placementActive")
    QtTest.QTest.mouseClick(viewport, left, pos = Move(viewport, point(2500, 0)))
    assert type(viewport.windows[-1]) is OpenDoorway and abs(viewport.windows[-1].length - 900) < .01
    Wheel(viewport, point(4000, 0), -120)
    assert type(viewport.windowDropPreview) is Door
    # Ctrl locks the preview to the wall and chooses orientation before release.
    Move(viewport, point(4000, 0))
    centerFraction = viewport.windowDropPreview.centerFraction
    ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
    oriented = Move(viewport, point(4400, 600), ctrl)
    assert viewport.doorOrientationLocked and viewport.windowDropPreview.centerFraction == centerFraction
    QtTest.QTest.mouseClick(viewport, left, ctrl, oriented)
    assert type(viewport.windows[-1]) is Door and viewport.windows[-1].hingeAtSecond
    assert not firstDoor.hingeAtSecond
    QtTest.QTest.keyRelease(viewport, QtCore.Qt.Key.Key_D)
    assert viewport.mode == "Select" and viewport.windowDropPreview is None and viewport.inactiveOpeningPreview is None
    assert not any(button.property("placementActive") for button in window.openingToolButtons.values())
    # Releasing the tool key before a pending mouse release cancels that click.
    count = len(viewport.windows)
    QtTest.QTest.keyPress(viewport, QtCore.Qt.Key.Key_D)
    click = Move(viewport, point(7000, 0))
    QtTest.QTest.mousePress(viewport, left, pos = click)
    QtTest.QTest.keyRelease(viewport, QtCore.Qt.Key.Key_D)
    QtTest.QTest.mouseRelease(viewport, left, pos = click)
    assert len(viewport.windows) == count
    # Windows also support repeated placement and cycling to Silled Window.
    QtTest.QTest.keyPress(viewport, QtCore.Qt.Key.Key_S)
    assert viewport.mode == "Window" and window.windowButton.property("placementActive")
    QtTest.QTest.mouseClick(viewport, left, pos = Move(viewport, point(6000, 0)))
    assert type(viewport.windows[-1]) is Window
    Wheel(viewport, point(-6000, 0), -120)
    assert window.silledWindowButton.property("placementActive")
    # A separate wall gives the silled window room to be placed.
    secondWall = Wall(point(-8000, 1500), point(8000, 1500), 240)
    viewport.walls.append(secondWall)
    QtTest.QTest.mouseClick(viewport, left, pos = Move(viewport, point(-6000, 1500)))
    assert type(viewport.windows[-1]) is SilledWindow
    QtTest.QTest.keyRelease(viewport, QtCore.Qt.Key.Key_S)
    viewport.Undo()
    assert type(viewport.windows[-1]) is Window
    viewport.Redo()
    assert type(viewport.windows[-1]) is SilledWindow
    QtTest.QTest.keyPress(viewport, QtCore.Qt.Key.Key_S)
    Wheel(viewport, point(0, 1500), -120)
    assert window.casementWindowButton.property("placementActive")
    QtTest.QTest.mouseClick(viewport, left, pos = Move(viewport, point(0, 1500)))
    assert type(viewport.windows[-1]).__name__ == "CasementWindow"
    QtTest.QTest.keyRelease(viewport, QtCore.Qt.Key.Key_S)
    # Typing in an editor and Ctrl+S do not activate placement tools.
    editor = window.propertyFields["length"].lineEdit()
    editor.setFocus()
    QtTest.QTest.keyClick(editor, QtCore.Qt.Key.Key_D)
    assert viewport.openingPlacementMode is None
    viewport.setFocus()
    with patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value = ("", "")):
        QtTest.QTest.keyClick(viewport, QtCore.Qt.Key.Key_S, ctrl)
    assert viewport.openingPlacementMode is None
    QtTest.QTest.keyPress(viewport, QtCore.Qt.Key.Key_D)
    QtTest.QTest.keyClick(viewport, QtCore.Qt.Key.Key_Escape)
    assert viewport.openingPlacementMode is None
    QtTest.QTest.keyRelease(viewport, QtCore.Qt.Key.Key_D)
    QtTest.QTest.keyPress(viewport, QtCore.Qt.Key.Key_S)
    QtWidgets.QApplication.sendEvent(window, QtCore.QEvent(QtCore.QEvent.Type.ApplicationDeactivate))
    assert viewport.openingPlacementMode is None
    window.close()
    print("PASS: D/S held tools, previews, releases, repeated inserts, wheel cycling, UI highlight, Ctrl orientation, undo and cancellation.")


if __name__ == "__main__":
    Main()
