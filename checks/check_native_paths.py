"""Exact native backend output, reusable strokes and Qt-free coverage orchestration."""
import math
import os
from pathlib import Path
import random
import subprocess
import sys
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))


def CheckWithoutQt():
    from check_geometry_core import CheckWithoutQt as CheckExisting
    CheckExisting()
    from planner_app.geometry.path_operations import PathOperations, ClipPathCoverage
    class Backend:
        def __init__(self): self.calls = []
        def Empty(self): self.calls.append("empty"); return set()
        def Union(self, a, b): self.calls.append("union"); return a | b
        def Difference(self, a, b): self.calls.append("difference"); return a - b
        def Intersection(self, a, b): self.calls.append("intersection"); return a & b
    for case in range(300):
        backend = Backend()
        masks = [{i % 11, (i + case) % 17} for i in range(case % 20)]
        clip = set(range(12)) if case % 2 else None
        expected = set(range(20)) - set().union(*masks)
        if clip is not None: expected &= clip
        assert ClipPathCoverage(backend, set(range(20)), iter(masks), clip) == expected
        assert backend.calls == ["empty"] + ["union"] * len(masks) + ["difference"] + (["intersection"] if clip is not None else [])
    assert not any(name.startswith(("PySide", "PyQt")) for name in sys.modules)
    print("PASS: backend contract and ordered coverage without Qt/site packages")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"], capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import QtCore, QtGui, QtWidgets
    from planner_app.graphics.path_operations import Paths
    from planner_app.geometry.path_operations import ClipPathCoverage
    from fixtures.native_paths_reference_20261017 import Configure, Load
    app = QtWidgets.QApplication([])
    p = QtCore.QPointF
    rng = random.Random(11950)
    def Values(path):
        return path.fillRule(), [(path.elementAt(i).x, path.elementAt(i).y, path.elementAt(i).type) for i in range(path.elementCount())]
    caps = {"flat": QtCore.Qt.PenCapStyle.FlatCap, "round": QtCore.Qt.PenCapStyle.RoundCap, "square": QtCore.Qt.PenCapStyle.SquareCap}
    joins = {"miter": QtCore.Qt.PenJoinStyle.MiterJoin, "bevel": QtCore.Qt.PenJoinStyle.BevelJoin, "round": QtCore.Qt.PenJoinStyle.RoundJoin, "svg-miter": QtCore.Qt.PenJoinStyle.SvgMiterJoin}
    for case in range(24):
        first, second = QtGui.QPainterPath(), QtGui.QPainterPath()
        first.setFillRule((QtCore.Qt.FillRule.WindingFill, QtCore.Qt.FillRule.OddEvenFill)[case % 2])
        first.addRect(-40, -30, 80, 60)
        first.addEllipse(-25, -25, 50, 50)
        if case % 3:
            first.moveTo(-50, -20)
            first.cubicTo(-100, 120, 110, -110, 55, 30)
        if case % 7:
            second.addEllipse(-30 + case % 9, -40, 70, 80)
        if case % 5:
            second.moveTo(-80, -60);second.lineTo(80, 60);second.lineTo(-80, 60);second.closeSubpath()
        offset = 1e8 if case % 4 == 0 else .37
        transform = QtGui.QTransform().translate(offset, -offset).rotate(case * 7.3).scale((.001, 1, 10)[case % 3], 1.3)
        first, second = transform.map(first), transform.map(second)
        before = Values(first), Values(second)
        for method, native in [(Paths.Union, first.united), (Paths.Intersection, first.intersected), (Paths.Difference, first.subtracted)]:
            assert Values(method(first, second)) == Values(native(second)), (case, method)
        assert Paths.Intersects(first, second) == first.intersects(second)
        assert Paths.Contours(first) == first.toSubpathPolygons()
        assert Paths.FillPolygons(first) == first.toFillPolygons()
        for position in (transform.map(p()), transform.map(p(30, 30)), transform.map(p(-40, -30))):
            assert Paths.Contains(first, position) == first.contains(position)
        cap, join = list(caps)[case % 3], list(joins)[case % 4]
        native = QtGui.QPainterPathStroker()
        width = (0, .02, 1, 10)[case % 4]
        native.setWidth(width);native.setCapStyle(caps[cap]);native.setJoinStyle(joins[join])
        native.setMiterLimit(2.5);native.setCurveThreshold(.13)
        native.setDashPattern([2.0, 1.0]);native.setDashOffset(.3)
        stroke = Paths.PrepareStroke(width = width, cap = cap, join = join, miterLimit = 2.5,
            curveThreshold = .13, dashPattern = [2.0, 1.0], dashOffset = .3)
        assert Values(stroke(first)) == Values(native.createStroke(first)), (case, "stroke")
        assert Values(stroke(second)) == Values(native.createStroke(second)), (case, "reuse")
        pen = QtGui.QPen(QtCore.Qt.GlobalColor.black)
        pen.setWidthF(width);pen.setCosmetic(bool(case % 2));pen.setStyle(QtCore.Qt.PenStyle.DashDotLine)
        native = QtGui.QPainterPathStroker(pen)
        native.setWidth(width or 1)
        assert Values(Paths.PreparePenStroke(pen, width = width or 1)(first)) == Values(native.createStroke(first))
        covered = QtGui.QPainterPath().united(first).united(second)
        expected = first.subtracted(covered).intersected(second)
        assert Values(ClipPathCoverage(Paths, first, [first, second], second)) == Values(expected)
        assert before == (Values(first), Values(second)), "input mutation"
    Configure()
    from planner_app.graphics.arrows import ArrowPaths
    original = Load("graphics/arrows.py").ArrowPaths
    for case in range(120):
        args = (p(case * .3, -case * .2), p(case * .7 + 100, case * .4 + 40),
                .02 + case % 20, bool(case % 2), 30 + case % 10, (.001, .2, 1.5)[case % 3], bool(case % 3))
        assert [Values(path) for path in ArrowPaths(*args)] == [Values(path) for path in original(*args)]
    print("PASS: 24 exact boolean/contour/containment/stroke cases, input immutability, pen strokes and 120 frozen arrows")


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
