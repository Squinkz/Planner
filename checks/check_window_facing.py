"""Window facing changes the crossbar, survives edits, and follows Ctrl-drag."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Window, SilledWindow, DrawOpeningSymbol

app = QtWidgets.QApplication([])
main = MainWindow()
main.SetThemes(uiTheme = "Dark UI", canvasTheme = "Dark Canvas")
main.show()
app.processEvents()
viewport = main.viewport
point = QtCore.QPointF
wall = Wall(point(-2000, 0), point(2000, 0), 240)
viewport.walls = [wall]
viewport.snapEnabled = False
opening = viewport.PlaceWindow(viewport.WorldToViewport(point()), openingType = Window)
assert not opening.swingsOutwards
assert main.doorProperties.isVisible()
assert main.doorProperties.layout().labelForField(main.doorFields["swing"]).text() == "Facing"
assert main.doorFields["swing"].isVisible() and not main.doorFields["hinge"].isVisible()
main.EditDoorProperty("swing")
assert opening.swingsOutwards
viewport.Undo()
assert not opening.swingsOutwards
viewport.Redo()
assert opening.swingsOutwards
assert viewport.CloneOpening(opening, wall).swingsOutwards
assert viewport.InactiveOpening(point(), Window, opening).swingsOutwards

# Actual mouse events orient an existing standard window without moving it.
ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
left = QtCore.Qt.MouseButton.LeftButton
center = viewport.WorldToViewport(point())
QtTest.QTest.mousePress(viewport, left, ctrl, center.toPoint())
target = viewport.WorldToViewport(point(0, -500))
event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, target,
                         QtCore.QPointF(viewport.mapToGlobal(target.toPoint())), left, left, ctrl)
QtWidgets.QApplication.sendEvent(viewport, event)
assert not opening.swingsOutwards and opening.centerFraction == .5
QtTest.QTest.mouseRelease(viewport, left, ctrl, target.toPoint())
viewport.Undo()
assert opening.swingsOutwards

# Both window styles keep their double crossbar slightly toward the facing wall edge.
for openingType in (Window, SilledWindow):
    for reversedFacing in (False, True):
        image = QtGui.QImage(240, 150, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtGui.QColor("#0e0e0e"))
        painter = QtGui.QPainter(image)
        painter.setPen(QtGui.QPen(QtGui.QColor("#a5b0b8"), 1.5))
        painter.drawLine(QtCore.QLineF(point(20, 50), point(220, 50)))
        painter.drawLine(QtCore.QLineF(point(20, 90), point(220, 90)))
        DrawOpeningSymbol(painter, point(20, 70), point(220, 70), 40,
                          openingType, swingsOutwards = reversedFacing,
                          color = "#ffffff", pixelsPerMillimeter = .2,
                          wallColor = "#a5b0b8", wallLineWidth = 1.5)
        painter.end()
        crossbarY = 63 if reversedFacing else 77
        facingSign = -1 if reversedFacing else 1
        assert image.pixelColor(120, crossbarY - 4 * facingSign).name() == "#ffffff"
        assert image.pixelColor(120, crossbarY + 2 * facingSign).name() == "#ffffff"
        assert image.pixelColor(120, crossbarY).name() == "#0e0e0e"
        assert image.pixelColor(120, 70).name() == "#0e0e0e"
        if openingType is SilledWindow:
            sillY = 42 if reversedFacing else 98
            assert image.pixelColor(120, sillY).name() == "#ffffff"
            assert image.pixelColor(120, 50 if reversedFacing else 90).name() == "#0e0e0e"
            # Wall-colored end crossbars must cover the sill/frame junction.
            assert image.pixelColor(20, 50 if reversedFacing else 90).name() == "#a5b0b8"

# Held-S placement uses the same facing rule and commits the preview's side.
viewport.windows = []
viewport.SetSelection([])
viewport.BeginOpeningMode("Window")
viewport.UpdateOpeningMode(center, QtCore.Qt.KeyboardModifier.NoModifier)
viewport.UpdateOpeningMode(viewport.WorldToViewport(point(0, 500)), ctrl)
assert viewport.windowDropPreview.swingsOutwards
QtTest.QTest.mouseClick(viewport, left, ctrl, viewport.WorldToViewport(point(0, 500)).toPoint())
assert len(viewport.windows) == 1 and viewport.windows[0].swingsOutwards
viewport.EndOpeningMode()
main.close()
print("PASS: standard facing UI, native Ctrl-drag, placement, history, clones and both crossbar sides")
