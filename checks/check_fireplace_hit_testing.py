"""Fireplace picking follows its rendered body, including over a selected parent."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets, QtTest
from planner import MainWindow
from planner_app.models import Wall, Fireplace
from planner_app.graphics.fireplace import FireplacePath
from planner_app.units import unitModes


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.resize(1300, 900)
    main.show()
    app.processEvents()
    v = main.viewport
    point = QtCore.QPointF
    # Same geometry as fireplace 16 in the reported session.
    wall = Wall(point(-1622.8701298237213, 1494.6010102717705), point(2318.4, 1494.6010102717705), 240)
    wallLength = QtCore.QLineF(wall.firstVertex, wall.secondVertex).length()
    fireplace = Fireplace(wall, .7235407579453212 - 600 / wallLength, .7235407579453212 + 600 / wallLength)
    fireplace.depth = 602.1076680110198
    v.walls, v.windows, v.furnishings, v.labels = [wall], [fireplace], [], []
    v.EnsureObjectIds()
    for mode in unitModes:
        v.unitsMode = mode
        v.SetSelection([(fireplace, None)])
        before = v.CaptureState()
        historyCount = len(v.undoHistory)
        for unused in range(3):
            main.RefreshProperties()
            center = (fireplace.firstVertex + fireplace.secondVertex) / 2
            body = center + fireplace.Axes()[1] * (.2 * fireplace.depth)
            QtTest.QTest.mouseClick(v, QtCore.Qt.MouseButton.LeftButton, pos = v.WorldToViewport(body).toPoint())
        assert v.CaptureState() == before, mode
        assert len(v.undoHistory) == historyCount, "Property refresh created an edit"
    v.unitsMode = "Adaptive Metric"
    for first, second, offset, reversedFacing in ((point(-2000, 0), point(2000, 0), 0, False),
                                                (point(0, -2000), point(0, 2000), -150, True),
                                                (point(-1600, -1200), point(1600, 1200), 150, False)):
        wall.firstVertex, wall.secondVertex = first, second
        fireplace.depthOffset = offset
        fireplace.swingsOutwards = reversedFacing
        direction, normal = fireplace.Axes()
        center = (fireplace.firstVertex + fireplace.secondVertex) / 2 + normal * fireplace.depthOffset
        normal *= -1 if reversedFacing else 1
        body = center + normal * (.2 * fireplace.depth)
        arm = center + direction * (.4 * fireplace.width) - normal * (.25 * fireplace.depth)
        cavity = center - normal * (.4 * fireplace.depth)
        assert FireplacePath(fireplace).contains(body) and FireplacePath(fireplace).contains(arm)
        assert not FireplacePath(fireplace).contains(cavity)
        for zoom in (.75, 1.5, 4):
            v.zoom = zoom
            v.panOffset = -point(center.x(), -center.y()) * (v.basePixelsPerMillimeter * zoom)
            for selected in ([], [(wall, None)], [(fireplace, None)]):
                v.SetSelection(selected)
                for position in (body, arm):
                    assert v.HitTest(v.WorldToViewport(position)) == (fireplace, None), (zoom, offset, selected, position)
                if not selected or selected[0][0] is not fireplace:
                    assert v.HitTest(v.WorldToViewport(cavity))[0] is not fireplace
            v.SetSelection([(wall, None)])
            QtTest.QTest.mouseClick(v, QtCore.Qt.MouseButton.LeftButton, pos = v.WorldToViewport(body).toPoint())
            assert v.selectedWall is fireplace
        v.SetSelection([])
        v.visibility["Fireplaces"] = False
        assert v.HitTest(v.WorldToViewport(body))[0] is not fireplace
        v.visibility["Fireplaces"] = True
    main.close()
    app.processEvents()
    print("PASS: fireplace body/cavity picking, selected parents, offsets, rotations, zoom and clicks.")


if __name__ == "__main__":
    Main()
