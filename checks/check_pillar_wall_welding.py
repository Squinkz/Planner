"""Near-touching pillar faces weld without interior seams or diagonal closures."""
import itertools
import math
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))


def CheckWithoutQt():
    from planner_app.geometry.boundaries import TraceBoundaryContours
    def Rectangle(left, top, right, bottom):
        return (left, top, right, bottom, ((left, top, right, top), (right, top, right, bottom),
                                         (right, bottom, left, bottom), (left, bottom, left, top)))
    first, second = Rectangle(0, 0, 10, 10), Rectangle(10.005, 3, 20, 7)
    cache = {}
    strict, state = TraceBoundaryContours([first, second], (20, 10), edgeCache = cache)
    assert len(strict) == 2
    welded, state = TraceBoundaryContours([first, second], (20, 10), state = state, edgeCache = cache, weldTolerance = .01)
    assert len(welded) == 1 and math.dist(welded[0][0], welded[0][-1]) <= .01
    # The seam covers only part of the first face. Retain both uncovered ends.
    area = abs(sum(ring[index][0] * ring[(index + 1) % len(ring)][1] - ring[(index + 1) % len(ring)][0] * ring[index][1]
                   for ring in welded for index in range(len(ring)))) / 2
    assert math.isclose(area, 140, abs_tol = .03), area
    strictAgain, state = TraceBoundaryContours([first, second], (20, 10), state = state, edgeCache = cache)
    assert strictAgain == strict
    distant = Rectangle(10.02, 3, 20, 7)
    separated, state = TraceBoundaryContours([first, distant], (20, 10), state = state, edgeCache = cache, weldTolerance = .01)
    assert len(separated) == 2
    assert not any(name.startswith("PySide6") for name in sys.modules)


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"], capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    from PySide6 import QtCore, QtGui
    from planner_app.models import Wall, Pillar
    from planner_app.viewport.geometry import FootprintGeometry
    point = QtCore.QPointF
    # Exact affected sources from dorm room.plan, including its slanted face.
    sources = [(Wall, (4540, -6150), (4539.999484536082, -3049.9899999999975), 120),
               (Wall, (5299.999999999999, -4850), (4599.999999999998, -4850), 200),
               (Wall, (5299.999999999999, -4349.999999999998), (4599.999999999998, -4349.999999999997), 200),
               (Pillar, (4949.999999999998, -4449.999999999998), (4949.999999999998, -4750), 700)]
    cases = 0
    for angle, distance, scale, reverse in itertools.product((0, 37, 90), (0, 1e6), (.001, .2, 1.5), (False, True)):
        transform = QtGui.QTransform().translate(distance, -distance).rotate(angle)
        walls = [kind(transform.map(point(*first)), transform.map(point(*second)), width) for kind, first, second, width in sources]
        if reverse: walls.reverse()
        geometry = FootprintGeometry(scale)
        path = geometry.ConnectedWallPath(walls)
        assert len(path.toSubpathPolygons()) == 1, (angle, distance, scale, reverse)
        def View(x, y):
            return geometry.WorldToViewport(transform.map(point(x, y)))
        stroke = QtGui.QPainterPathStroker()
        stroke.setWidth(scale * 2)
        outline = stroke.createStroke(path)
        assert not outline.contains(View(4600, -4600)), ("interior pillar seam", angle, distance, scale, reverse)
        # Catch missing wall pieces and accidental closeSubpath diagonals.
        for x, y in ((4540, -3500), (4540, -5500), (4800, -4600), (5250, -4900), (4700, -4300)):
            assert path.contains(View(x, y)), ("missing fill", x, y, angle, distance, scale, reverse)
        for x, y in ((4700, -4000), (5200, -5200), (4400, -4600)):
            assert not path.contains(View(x, y)), ("outside fill", x, y, angle, distance, scale, reverse)
        assert geometry.ConnectedWallPath(walls) == path
        cases += 1
    for gap, expected in ((.005, 1), (.0099, 1), (.0101, 2), (.1, 2)):
        wall = Wall(point(0, -1000), point(0, 1000), 120)
        pillar = Pillar(point(410 + gap, -150), point(410 + gap, 150), 700)
        geometry = FootprintGeometry(.2)
        assert len(geometry.ConnectedWallPath([wall, pillar]).toSubpathPolygons()) == expected, gap
    wall = Wall(point(0, -1000), point(0, 1000), 120)
    pillar = Pillar(point(410.005, -150), point(410.005, 150), 700)
    geometry = FootprintGeometry(.2)
    members = [wall, pillar]
    assert len(geometry.ConnectedWallPath(members).toSubpathPolygons()) == 1
    for delta, expected in ((.02, 2), (-.02, 1)):
        pillar.firstVertex += point(delta, 0)
        pillar.secondVertex += point(delta, 0)
        assert len(geometry.ConnectedWallPath(members).toSubpathPolygons()) == expected
    print("PASS:", cases, "rotated/translated/scaled dorm joins, strict gap boundaries, partial seams and warm cache invalidation")


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
