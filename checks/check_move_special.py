"""Exact transforms, shared/local origins, modal inputs, cancellation and atomic validation."""
import math
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow
from planner_app.models import Furnishing, Label, Pillar, Wall, Stair, Counter, Railing, Arrow, MeasurementGuide, Window
from planner_app.graphics.theme import BuildStyle


def Center(obj):
    return (obj.firstVertex + obj.secondVertex) / 2


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    # Exercise centimetre input independently of the application's unit default.
    v.unitsMode = "Adaptive Metric"
    v.connectedEnabled = False
    v.snapEnabled = True
    point = QtCore.QPointF
    v.setFocus()
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_T)
    assert getattr(main, "moveSpecialWindow", None) is None
    desk = Furnishing(v.furnishingDefinitions["desk"])
    v.furnishings = [desk]
    v.SetSelection([(desk, None)])
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_M)
    assert getattr(main, "moveSpecialWindow", None) is None
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_T)
    dialog = main.moveSpecialWindow
    assert dialog.isVisible() and dialog.windowTitle() == "Transform"
    app.processEvents()
    fields = (dialog.xField, dialog.yField, dialog.angleField, dialog.localOriginsField)
    assert len({field.height() for field in fields}) == 1
    gaps = [second.y() - first.y() - first.height() for first, second in zip(fields, fields[1:])]
    assert gaps[0] == gaps[2] == 6 and gaps[1] > gaps[0] + 8
    assert dialog.xField.value() == dialog.yField.value() == dialog.angleField.value() == 0
    assert dialog.divisor == 10 and dialog.xField.suffix() == dialog.yField.suffix() == " cm"
    assert not dialog.localOriginsField.isChecked()
    original = v.CaptureState()
    dialog.xField.setValue(1)
    dialog.angleField.setValue(90)
    dialog.reject()
    assert v.CaptureState() == original and not v.undoHistory
    main.ShowMoveSpecial()
    dialog = main.moveSpecialWindow
    dialog.xField.lineEdit().selectAll()
    QtTest.QTest.keyClicks(dialog.xField.lineEdit(), "112.5")
    dialog.yField.setValue(-25)
    dialog.angleField.setValue(90)
    dialog.buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).click()
    assert not dialog.isVisible()
    assert QtCore.QLineF(Center(desk), point(1125, -250)).length() < 1e-6
    assert math.isclose(desk.angle, 90) and len(v.undoHistory) == 1
    v.Undo()
    assert v.CaptureState() == original
    v.Redo()
    assert QtCore.QLineF(Center(desk), point(1125, -250)).length() < 1e-6
    v.Undo()

    for unitMode, divisor in (("Adaptive Metric", 10), ("Meters", 1000), ("Centimeters", 10), ("Millimeters", 1)):
        v.unitsMode = unitMode
        main.ShowMoveSpecial()
        dialog = main.moveSpecialWindow
        dialog.xField.setValue(25.125)
        dialog.accept()
        assert QtCore.QLineF(Center(desk), point(25.125 * divisor, 0)).length() < 1e-6
        v.Undo()
    v.unitsMode = "Adaptive Metric"
    second = Furnishing(desk.definition, point(2000, 0))
    v.furnishings = [desk, second]
    v.SetSelection([(desk, None), (second, None)])
    for local in (False, True):
        before = v.CaptureState()
        v.rotationPivot = None
        assert v.MoveSpecial(125, -75, 90, local) is None
        for obj, originalX in ((desk, 0), (second, 2000)):
            expected = point(originalX + 125, -75) if local else point(1125, originalX - 1075)
            assert QtCore.QLineF(Center(obj), expected).length() < 1e-6
            assert math.isclose(obj.angle, 90)
        v.Undo()
        assert v.CaptureState() == before
    # A chosen handle pivot is also the shared origin for exact Transform angles.
    v.rotationPivot = point(9000, 7000)
    before = v.CaptureState()
    assert v.MoveSpecial(125, -75, 90) is None
    for obj, originalX in ((desk, 0), (second, 2000)):
        expected = point(16125, originalX - 2075)
        assert QtCore.QLineF(Center(obj), expected).length() < 1e-6
        assert math.isclose(obj.angle, 90)
    assert v.rotationPivot == point(9000, 7000)
    v.Undo()
    assert v.CaptureState() == before
    v.rotationPivot = point(9000, 7000)
    main.ShowMoveSpecial()
    dialog = main.moveSpecialWindow
    dialog.xField.setValue(12.5)
    dialog.yField.setValue(-7.5)
    dialog.angleField.setValue(90)
    dialog.accept()
    assert not dialog.isVisible()
    assert QtCore.QLineF(Center(desk), point(16125, -2075)).length() < 1e-6
    assert v.rotationPivot == point(9000, 7000)
    v.Undo()
    assert v.CaptureState() == before
    v.rotationPivot = None
    # Every independently sized/vertex object accepts the same exact operation.
    label = Label(point(), "Special")
    label.firstVertex, label.secondVertex, label.width = point(0, -300), point(0, 300), 600
    for cls in (Wall, Stair, Counter, Railing, Arrow, MeasurementGuide, Pillar, Label):
        obj = label if cls is Label else cls(point(0, -300), point(0, 300))
        v.furnishings = []
        v.labels = [obj] if cls is Label else []
        v.walls = [] if cls is Label else [obj]
        v.windows = []
        v.SetSelection([(obj, None)])
        length = QtCore.QLineF(obj.firstVertex, obj.secondVertex).length()
        assert v.MoveSpecial(123, 456, -90) is None, cls.__name__
        assert QtCore.QLineF(Center(obj), point(123, 456)).length() < 1e-6
        assert math.isclose(QtCore.QLineF(obj.firstVertex, obj.secondVertex).length(), length)
    # Both connection modes retain the shared endpoint when the selected wall rotates.
    for wholeObjects in (False, True):
        wall = Wall(point(0, -300), point(0, 300), 120)
        neighbor = Wall(point(0, 300), point(1000, 300), 120)
        v.walls, v.labels, v.windows = [wall, neighbor], [], []
        v.connectedEnabled = v.connectedVerticesEnabled = True
        v.connectedObjectsEnabled = wholeObjects
        v.SetSelection([(wall, None)])
        assert v.MoveSpecial(125, 250, 90) is None
        assert QtCore.QLineF(wall.secondVertex, neighbor.firstVertex).length() < 1e-6
        expected = point(-175, 1250) if wholeObjects else point(1000, 300)
        assert QtCore.QLineF(neighbor.secondVertex, expected).length() < 1e-6
    v.connectedEnabled = False
    # Wall-mounted objects translate on their host, and rotate with a selected host.
    wall = Wall(point(-2000, 0), point(2000, 0), 240)
    opening = Window(wall, .4, .6)
    v.walls, v.windows, v.labels = [wall], [opening], []
    v.SetSelection([(opening, None)])
    assert v.MoveSpecial(125, 0, 0) is None
    assert Center(opening) == point(125, 0)
    before = v.CaptureState()
    assert v.MoveSpecial(0, 100, 0)
    assert v.CaptureState() == before
    assert v.MoveSpecial(0, 0, 45)
    assert v.CaptureState() == before
    v.SetSelection([(wall, None), (opening, None)])
    assert v.MoveSpecial(100, 200, 90) is None
    assert QtCore.QLineF(Center(opening), point(100, 325)).length() < 1e-6
    assert v.OpeningFits(opening)

    # Failed confirmation leaves the dialog open and restores all geometry.
    v.SetSelection([(opening, None)])
    main.ShowMoveSpecial()
    dialog = main.moveSpecialWindow
    before = v.CaptureState()
    dialog.xField.setValue(100)
    dialog.accept()
    assert dialog.isVisible() and v.clipboardError and v.clipboardErrorTimer.isActive() and v.CaptureState() == before
    assert all(label.text() != v.clipboardError for label in dialog.findChildren(QtWidgets.QLabel))
    QtTest.QTest.keyClick(dialog, QtCore.Qt.Key.Key_Escape)
    assert not dialog.isVisible()
    main.ShowMoveSpecial()
    dialog = main.moveSpecialWindow
    Path("screenshots").mkdir(exist_ok = True)
    assert dialog.grab().save("screenshots/move-special.png")
    dialog.reject()
    # Typing T in an editor must stay in the editor.
    v.labels, v.walls, v.windows = [label], [], []
    v.SetSelection([(label, None)])
    main.labelTextField.setFocus()
    QtTest.QTest.keyClicks(main.labelTextField, "t")
    assert not main.moveSpecialWindow.isVisible()
    v.SetSelection([(label, None)])
    assert v.MoveSpecial(0, 0, 360) is None
    assert v.MoveSpecial(math.inf, 0, 0) == "Enter valid movement and angle values."
    assert v.MoveSpecial(0, math.nan, 0) == "Enter valid movement and angle values."
    v.SetSelection([])
    assert v.MoveSpecial(1, 0, 0) == "Select an object to transform."
    main.close()


if __name__ == "__main__":
    Main()
