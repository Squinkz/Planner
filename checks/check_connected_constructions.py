"""Rigid connected constructions and direct, same-class vertex following."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow
from planner_app.models import Wall, Pillar, Stair, Counter, Railing, Arrow, MeasurementGuide, Window
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    v.ResetView()
    v.snapEnabled = False
    v.connectedEnabled = v.connectedObjectsEnabled = True
    v.connectedVerticesEnabled = False
    point = QtCore.QPointF
    delta = point(200, 100)
    root = Wall(point(-1000, 0), point(1000, 0), 120)
    # Crossing rectangles connect even though neither endpoint lies in the other.
    crossing = Wall(point(0, -1000), point(0, 1000), 120)
    child = Wall(point(0, 1000), point(1000, 1000), 120)
    touching = Wall(point(1000, 1120), point(2000, 1120), 120)
    pillar = Pillar(point(1800, 1120), point(1800, 1520), 400)
    throughPillar = Wall(point(1800, 1520), point(2800, 1520), 120)
    separate = Wall(point(-1000, -2000), point(1000, -2000), 120)
    otherClass = Railing(point(-1000, 0), point(1000, 0))
    members = [root, crossing, child, touching, pillar, throughPillar]
    v.walls = members + [separate, otherClass]
    opening = Window(throughPillar, .4, .8)
    v.windows = [opening]
    v.SetSelection([(root, None)])
    before = v.CaptureState()
    originals = [(obj, point(obj.firstVertex), point(obj.secondVertex)) for obj in v.walls]
    openingFirst = point(opening.firstVertex)
    start = v.WorldToViewport(point(-500, 0)).toPoint()
    Drag(v, start, start + QtCore.QPoint(40, -20))
    for obj, first, second in originals:
        expected = delta if obj in members else point()
        assert obj.firstVertex == first + expected and obj.secondVertex == second + expected
    assert opening.firstVertex == openingFirst + delta
    v.Undo()
    assert v.CaptureState()[0] == before[0] and v.CaptureState()[3] == before[3]
    v.Redo()
    v.Undo()
    # Pillars can carry their touching wall construction as well.
    v.SetSelection([(pillar, None)])
    assert v.MoveSpecial(200, 100, 0) is None
    assert root.firstVertex == originals[0][1] + delta
    v.Undo()
    # Constructions follow body contact within their class; annotations retain
    # endpoint-only connections. Neither crosses into another object class.
    for cls in (Stair, Counter, Railing, Arrow, MeasurementGuide):
        root = cls(point(-1000, 0), point(0, 0))
        child = cls(point(0, 0), point(0, 1000))
        last = cls(point(0, 1000), point(1000, 1000))
        overlap = cls(point(-500, -500), point(-500, 500))
        wall = Wall(point(0, 1000), point(1000, 1000))
        foreign = [other(point(-1000, 0), point(0, 0)) for other in (Stair, Counter, Railing) if other is not cls]
        v.walls, v.windows = [root, child, last, overlap, wall] + foreign, []
        v.SetSelection([(root, None)])
        attached = v.AttachedVertices(root)
        connected = (child, last, overlap) if cls in (Stair, Counter, Railing) else (child, last)
        assert {(id(obj), index) for obj, index, vertex in attached} == {
            (id(obj), index) for obj in connected for index in (0, 1)}
        v.walls = [root, child, last, overlap]
        assert v.MoveSpecial(200, 100, 0) is None, cls.__name__
        assert child.firstVertex == delta and child.secondVertex == point(0, 1000) + delta
        assert last.secondVertex == point(1000, 1000) + delta
        assert overlap.firstVertex == point(-500, -500) + (delta if overlap in connected else point())
        assert wall.firstVertex == point(0, 1000)
        v.Undo()
    # Collision-based object following and shared-vertex following stay separate.
    root = Arrow(point(-1000, 0), point(0, 0))
    child = Arrow(point(0, 0), point(0, 1000))
    interior = Arrow(point(-500, 0), point(-500, -1000))
    v.walls = [root, child, interior]
    v.SetSelection([(root, None)])
    start = v.WorldToViewport(point(-800, 0)).toPoint()
    Drag(v, start, start + QtCore.QPoint(40, -20))
    assert child.firstVertex == delta and child.secondVertex == point(0, 1000) + delta
    assert interior.firstVertex == point(-500, 0) and interior.secondVertex == point(-500, -1000)
    v.Undo()
    v.connectedObjectsEnabled = False
    v.connectedVerticesEnabled = True
    for cls in (Wall, Stair, Counter, Railing):
        root = cls(point(-1000, 0), point(1000, 0), 200)
        inside = cls(point(0, 100), point(0, 1000), 200)
        descendant = cls(point(0, 1000), point(1000, 1000), 200)
        shared = cls(point(1000, 0), point(2000, 0), 200)
        other = Counter(point(0, 100), point(0, 1000)) if cls is not Counter else Stair(point(0, 100), point(0, 1000))
        v.walls = [root, inside, descendant, shared, other]
        v.SetSelection([(root, None)])
        assert all(obj is not other for obj, index, vertex in v.AttachedVertices(root))
        v.walls.remove(other)
        assert v.MoveSpecial(200, 100, 0) is None, cls.__name__
        assert inside.firstVertex == point(0, 100) + delta and inside.secondVertex == point(0, 1000)
        assert descendant.firstVertex == point(0, 1000) and other.firstVertex == point(0, 100)
        assert shared.firstVertex == point(1000, 0) + delta and shared.secondVertex == point(2000, 0)
        v.Undo()
        v.SetSelection([(root, 1)])
        attached = v.AttachedVertices(root)
        assert [(obj, index) for obj, index, vertex in attached] == [(shared, 0)]
    # Multiple selected roots carry endpoints within their footprints directly.
    a = Wall(point(-1000, 0), point(1000, 0), 200)
    b = Wall(point(-1000, 2000), point(1000, 2000), 200)
    innerA = Wall(point(0, 50), point(0, 1000), 120)
    innerB = Wall(point(0, 1950), point(0, 1000), 120)
    sharedA = Wall(point(1000, 0), point(1500, 500), 120)
    sharedB = Wall(point(1000, 2000), point(1500, 1500), 120)
    v.walls = [a, b, innerA, innerB, sharedA, sharedB]
    v.SetSelection([(a, None), (b, None)])
    start = v.WorldToViewport(point(-500, 0)).toPoint()
    Drag(v, start, start + QtCore.QPoint(40, -20))
    assert innerA.firstVertex == point(0, 50) + delta and innerA.secondVertex == point(0, 1000)
    assert innerB.firstVertex == point(0, 1950) + delta and innerB.secondVertex == point(0, 1000)
    assert sharedA.firstVertex == point(1000, 0) + delta and sharedA.secondVertex == point(1500, 500)
    assert sharedB.firstVertex == point(1000, 2000) + delta and sharedB.secondVertex == point(1500, 1500)
    main.close()


if __name__ == "__main__":
    Main()
