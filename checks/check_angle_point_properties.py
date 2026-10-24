"""Angle anchors use object position; arm endpoints add normal Point panels."""
import math
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow
from planner_app.models import AngleGuide, ObjectControlPoints
from planner_app.units import MetricUnit


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    point = QtCore.QPointF
    guide = AngleGuide(point(1100, 200), point(100, 900), middleVertex = point(100, 200))
    v.walls = [guide]
    original = tuple(point(vertex) for vertex in ObjectControlPoints(guide))
    for mode in ("Millimeters", "Meters", "Feet and Inches", "Inches"):
        v.unitsMode = mode
        divisor, unit = MetricUnit(mode)
        for index in range(3):
            v.SetSelection([(guide, index)])
            assert main.vertexProperties.isVisible() == (index < 2)
            if index < 2:
                assert main.vertexProperties.title() == f"Point {index + 1}"
            assert main.angleGuideProperties.isVisible()
            for axis in ("x", "y"):
                field = main.propertyFields[axis] if index < 2 else main.angleGuidePositionFields[axis]
                expected = getattr(original[index], axis)() / divisor
                assert abs(field.value() - expected) <= .001 and field.commonSuffix == " " + unit, (mode, index, axis, field.value(), expected, field.commonSuffix)
                field.setValue(field.value() + 2)
                target = field.value() * divisor
                actual = ObjectControlPoints(guide)
                assert math.isclose(getattr(actual[index], axis)(), target, abs_tol = 1e-6)
                if index == 2:
                    delta = actual[2] - original[2]
                    assert all(QtCore.QLineF(actual[i], original[i] + delta).length() < 1e-6 for i in range(2))
                else:
                    assert all(actual[i] == original[i] for i in range(3) if i != index)
                v.Undo()
                assert ObjectControlPoints(guide) == original
    v.unitsMode = "Millimeters"
    v.SetSelection([(guide, 2)])
    main.BeginPropertyDrag()
    for value in (300, 500, 700):
        main.angleGuidePositionFields["x"].setValue(value)
    main.FinishPropertyDrag(False)
    assert guide.middleVertex.x() == 700
    v.Undo()
    assert ObjectControlPoints(guide) == original
    other = AngleGuide(point(2000, 100), point(1300, 800), middleVertex = point(1300, 100))
    v.walls.append(other)
    v.SetSelection([(guide, 0), (other, 1)])
    assert main.propertyFields["x"].mixedValue
    main.propertyFields["x"].setValue(-400)
    assert guide.firstVertex.x() == other.secondVertex.x() == -400
    assert other.firstVertex == point(2000, 100) and other.middleVertex == point(1300, 100)
    v.Undo()
    assert ObjectControlPoints(guide) == original and other.middleVertex == point(1300, 100)
    # Object position is available for body, anchor, label and endpoint selections.
    for index in (None, 2, 3, 0):
        v.SetSelection([(guide, index)])
        assert main.vertexProperties.isVisible() == (index == 0)
        assert main.angleGuidePositionRow.isVisible()
        main.angleGuidePositionFields["y"].setValue(-500)
        assert guide.middleVertex == point(100, -500)
        assert guide.firstVertex == point(1100, -500) and guide.secondVertex == point(100, 200)
        v.Undo()
        assert ObjectControlPoints(guide) == original
    v.SetSelection([(guide, None), (other, 2)])
    assert main.angleGuidePositionFields["x"].mixedValue
    main.angleGuidePositionFields["x"].setValue(300)
    assert guide.middleVertex.x() == other.middleVertex.x() == 300
    assert guide.firstVertex == point(1300, 200) and other.firstVertex == point(1000, 100)
    v.Undo()
    assert ObjectControlPoints(guide) == original and other.middleVertex == point(1300, 100)
    main.MarkProjectClean()
    main.close()
    print("PASS: anchor object position, endpoint Point panels, coordinate edits, units, mixed selections and undo")


if __name__ == "__main__":
    Main()
