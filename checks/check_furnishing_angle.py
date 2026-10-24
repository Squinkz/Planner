"""Midpoint rotation, oriented bounds, collision rollback, history and bulk angles."""
import math
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall
from furnishings import Furnishing
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    window = MainWindow()
    window.show()
    app.processEvents()
    v = window.viewport
    desk = Furnishing(v.furnishingDefinitions["desk"], QtCore.QPointF(250, -100))
    v.furnishings = [desk]
    v.SetSelection([(desk, None)])
    center = (desk.firstVertex + desk.secondVertex) / 2
    assert desk.angle == 0 and window.propertyFields["angle"].isVisible()
    assert "angle" not in desk.definition
    window.propertyFields["angle"].setValue(90)
    assert math.isclose(desk.angle, 90) and math.isclose(desk.length, 600)
    assert (desk.firstVertex + desk.secondVertex) / 2 == center
    corners = v.ObjectCorners(desk)
    assert math.isclose(max(p.x() for p in corners) - min(p.x() for p in corners), 600)
    assert math.isclose(max(p.y() for p in corners) - min(p.y() for p in corners), 1200)
    assert desk.Clone().angle == desk.angle
    v.Undo()
    assert desk.angle == 0
    v.Redo()
    assert math.isclose(desk.angle, 90)
    other = Furnishing(desk.definition, QtCore.QPointF(-1500, 0))
    v.furnishings.append(other)
    v.SetSelection([(desk, None), (other, None)])
    assert window.propertyFields["angle"].lineEdit().placeholderText() == "(different)"
    otherCenter = (other.firstVertex + other.secondVertex) / 2
    window.EditProperty("angle", 45)
    assert math.isclose(desk.angle, 45) and math.isclose(other.angle, 45)
    assert (desk.firstVertex + desk.secondVertex) / 2 == center
    assert (other.firstVertex + other.secondVertex) / 2 == otherCenter
    v.Undo()
    assert math.isclose(desk.angle, 90) and other.angle == 0
    v.SetSelection([(desk, None)])
    window.EditProperty("angle", 0)
    wall = Wall(QtCore.QPointF(-1000, 400), QtCore.QPointF(1500, 400), 100)
    v.walls = [wall]
    assert v.FurnishingFits(desk)
    window.EditProperty("angle", 90)
    assert desk.angle == 0 and v.FurnishingFits(desk)
    assert (desk.firstVertex + desk.secondVertex) / 2 == center
    v.walls = []
    window.EditProperty("angle", 30)
    v.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "furnishing-angle.png"))
    window.close()
    print("PASS: angle UI/editor-only state, midpoint rotation, oriented footprint, cloning, undo/redo, bulk edits and collision rollback.")


if __name__ == "__main__":
    Main()
