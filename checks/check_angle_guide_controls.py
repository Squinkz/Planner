"""Angle Guide constraint rays, axis guides, numeric editing and stable property drags."""
import math
import os
import sys
from pathlib import Path
from unittest.mock import Mock

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtWidgets, QtTest
from planner import MainWindow
from planner_app.models import AngleGuide, ObjectControlPoints
from planner_app.graphics.fonts import LoadApplicationFonts


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    point = QtCore.QPointF
    ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
    guide = AngleGuide(point(1100, 0), point(0, 700), middleVertex = point())
    v.walls = [guide]
    v.snapEnabled = False
    for local in (False, True):
        v.localTransforms = local
        for index in (0, 1):
            v.SetSelection([(guide, index)])
            original = tuple(point(vertex) for vertex in ObjectControlPoints(guide))
            start = v.WorldToViewport(original[index]).toPoint()
            target = point(900 * math.cos(math.radians(38)), 900 * math.sin(math.radians(38)))
            QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, ctrl, start)
            v.UpdateInteraction(v.WorldToViewport(target), ctrl)
            direction = ObjectControlPoints(guide)[index] - guide.middleVertex
            angle = math.degrees(math.atan2(direction.y(), direction.x()))
            assert math.isclose(angle, 45, abs_tol = 1e-6), (local, index, angle)
            assert guide.middleVertex == original[2] and ObjectControlPoints(guide)[1 - index] == original[1 - index]
            assert v.axisConstraintOrigin == guide.middleVertex and v.axisConstraintDirection is not None
            painter = Mock()
            v.DrawSnapGuides(painter, v.DrawingRect())
            assert painter.drawLine.call_count >= 1
            assert any(call.args[0].style() == QtCore.Qt.PenStyle.DashLine for call in painter.setPen.call_args_list)
            v.CancelInteraction()
            assert ObjectControlPoints(guide) == original
        # Middle movement uses X/Y even with local transforms selected.
        v.SetSelection([(guide, 2)])
        original = tuple(point(vertex) for vertex in ObjectControlPoints(guide))
        QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, ctrl, v.WorldToViewport(guide.middleVertex).toPoint())
        v.UpdateInteraction(v.WorldToViewport(guide.middleVertex + point(500, 300)), ctrl)
        delta = guide.middleVertex - original[2]
        assert math.isclose(delta.x(), 500, abs_tol = 1e-6) and abs(delta.y()) < 1e-6
        assert all(vertex == before + delta for vertex, before in zip(ObjectControlPoints(guide), original))
        painter = Mock()
        v.DrawSnapGuides(painter, v.DrawingRect())
        lines = [call.args[0] for call in painter.drawLine.call_args_list]
        assert len(lines) == 2 and any(line.dx() == 0 for line in lines) and any(line.dy() == 0 for line in lines)
        assert any(call.args[0].style() == QtCore.Qt.PenStyle.DashLine for call in painter.setPen.call_args_list)
        v.CancelInteraction()
    v.localTransforms = False
    # Local angular steps use the arm direction, never the chord between ends.
    original = tuple(point(vertex) for vertex in ObjectControlPoints(guide))
    guide.firstVertex = point(900 * math.cos(math.radians(33)), 900 * math.sin(math.radians(33)))
    v.localTransforms = True
    v.SetSelection([(guide, 0)])
    QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, ctrl, v.WorldToViewport(guide.firstVertex).toPoint())
    target = point(900 * math.cos(math.radians(70)), 900 * math.sin(math.radians(70)))
    v.UpdateInteraction(v.WorldToViewport(target), ctrl)
    direction = guide.firstVertex - guide.middleVertex
    assert math.isclose(math.degrees(math.atan2(direction.y(), direction.x())), 63, abs_tol = 1e-6)
    v.CancelInteraction()
    guide.firstVertex = point(original[0])
    v.localTransforms = False
    v.SetSelection([(guide, None)])
    field = main.angleGuideAngleField
    assert field.isVisible() and field.value() == 90 and main.selectionLabel.text().startswith("Angle Guide (#")
    before = tuple(point(vertex) for vertex in ObjectControlPoints(guide))
    # East is farther from north than +Y, so the last arm retains its direction.
    field.setValue(60)
    assert math.isclose(guide.angle, 60, abs_tol = 1e-6)
    assert guide.secondVertex == point(0, 700)
    assert math.isclose(QtCore.QLineF(guide.firstVertex, guide.middleVertex).length(), 700)
    assert len(v.undoHistory) == 1
    v.Undo()
    assert ObjectControlPoints(guide) == before
    # With both arms south of the vertex, the farther arm can pass north.
    # A continuous edit must still retain the originally chosen fixed arm.
    originalState = v.CaptureState()
    fixedDirection = point(math.cos(math.radians(-10)), math.sin(math.radians(-10)))
    guide.firstVertex = fixedDirection * 900
    guide.secondVertex = point(math.cos(math.radians(-100)), math.sin(math.radians(-100))) * 700
    v.RecordEdit(originalState)
    main.BeginPropertyDrag()
    for degrees in (175, 80, 180, 20):
        main.EditAngleGuideAngle(degrees)
        assert math.isclose(guide.angle, degrees, abs_tol = 1e-6)
        assert QtCore.QLineF(guide.firstVertex, fixedDirection * 700).length() < 1e-6
    main.FinishPropertyDrag(True)
    v.Undo()
    assert ObjectControlPoints(guide) == before
    # Re-entering the displayed angle still equalizes unequal arm lengths.
    field.setFocus()
    field.lineEdit().selectAll()
    QtTest.QTest.keyClicks(field.lineEdit(), "90")
    QtTest.QTest.keyClick(field, QtCore.Qt.Key.Key_Return)
    assert math.isclose(QtCore.QLineF(guide.firstVertex, guide.middleVertex).length(), 700)
    v.Undo()
    assert ObjectControlPoints(guide) == before
    # Numeric drags retain their original arm/side through north and both limits.
    main.BeginPropertyDrag()
    for degrees in (0, 20, 180, 10, 130):
        main.EditAngleGuideAngle(degrees)
        assert math.isclose(guide.angle, degrees, abs_tol = 1e-6)
        assert guide.secondVertex == point(0, 700)
    main.FinishPropertyDrag(False)
    v.Undo()
    assert ObjectControlPoints(guide) == before
    # Choose either arm consistently by unsigned angular distance from north.
    for firstDegrees, lastDegrees in ((80, 10), (170, 100), (250, 310), (350, 160)):
        first = point(math.cos(math.radians(firstDegrees)), math.sin(math.radians(firstDegrees)))
        last = point(math.cos(math.radians(lastDegrees)), math.sin(math.radians(lastDegrees)))
        obj = AngleGuide(first * 900, last * 600, middleVertex = point())
        moving = 0 if first.y() < last.y() - 1e-10 else 1
        assert obj.SetAngle(55) and math.isclose(obj.angle, 55, abs_tol = 1e-6)
        fixed = ObjectControlPoints(obj)[1 - moving]
        assert QtCore.QLineF(fixed, (last if moving == 0 else first) * 600).length() < 1e-6
        assert all(math.isclose(QtCore.QLineF(vertex, obj.middleVertex).length(), 600) for vertex in ObjectControlPoints(obj)[:2])
    # Mixed fields apply one requested angle to every guide; collapsed arms are undefined.
    other = AngleGuide(point(1000, 0), point(1000, 1000), middleVertex = point(1000, 500))
    v.walls.append(other)
    v.SetSelection([(guide, None), (other, None)])
    assert field.mixedValue and main.selectionLabel.text() == "2 Angle Guides selected"
    main.EditAngleGuideAngle(75)
    assert math.isclose(guide.angle, 75, abs_tol = 1e-6) and math.isclose(other.angle, 75, abs_tol = 1e-6)
    v.Undo()
    v.SetSelection([(guide, None)])
    guide.firstVertex = point(guide.middleVertex)
    main.RefreshProperties()
    assert not field.isEnabled() and field.lineEdit().placeholderText() == "Undefined"
    app.clipboard().clear()
    main.MarkProjectClean()
    main.close()
    print("PASS: 15-degree arm constraints, X/Y middle movement, dashed guides, Angle Guide identity and reversible numeric angle edits")


if __name__ == "__main__":
    Main()
