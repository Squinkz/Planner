"""Only end-joined counters/stairs merge; stair treads stay between inset edges."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Counter, Stair
from planner_app.graphics.symbols import DrawStairSymbol
from check_stair_arrowheads import LineRecorder


def HasEdge(path, point):
    first = None
    for index in range(path.elementCount()):
        element = path.elementAt(index)
        second = QtCore.QPointF(element.x, element.y)
        if element.isLineTo() and first is not None:
            line = second - first
            length = QtCore.QLineF(first, second).length()
            offset = point - first
            if length > .0001 and abs(line.x() * offset.y() - line.y() * offset.x()) / length < .001:
                along = QtCore.QPointF.dotProduct(line, offset) / length
                if .001 < along < length - .001:
                    return True
        first = second
    return False


def Outline(viewport, objects):
    InstallScene(viewport.window(), objects)
    if type(objects[0]) is Stair:
        viewport.ConnectedStairPath(objects)
        return QtGui.QTransform().scale(1 / viewport.basePixelsPerMillimeter, -1 / viewport.basePixelsPerMillimeter).map(viewport.stairOutlinePath)
    path = viewport.ConnectedCounterPath(objects, False)[0] if type(objects[0]) is Counter else viewport.ConnectedWallPath(objects)
    origin = viewport.WorldToViewport(QtCore.QPointF())
    scale = viewport.basePixelsPerMillimeter * viewport.zoom
    return QtGui.QTransform(1 / scale, 0, 0, -1 / scale, -origin.x() / scale, origin.y() / scale).map(path)


def Main():
    p = QtCore.QPointF
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.showMeasurements = v.showTips = False
        for cls in (Counter, Stair):
            for angle in (0, 37):
                transform = QtGui.QTransform().translate(-1500, -300).rotate(angle)
                runs = [cls(transform.map(p(0, 0)), transform.map(p(3000, 0)), 600),
                        cls(transform.map(p(0, 600)), transform.map(p(3000, 600)), 600)]
                assert HasEdge(Outline(v, runs), transform.map(p(1500, 300))), (cls, angle, "side contact")
                runs = [cls(transform.map(p(0, 0)), transform.map(p(3000, 0)), 600),
                        cls(transform.map(p(3000, 0)), transform.map(p(6000, 0)), 600)]
                assert not HasEdge(Outline(v, runs), transform.map(p(3000, 0))), (cls, angle, "end join")
                runs = [cls(transform.map(p(0, 0)), transform.map(p(3000, 0)), 600),
                        cls(transform.map(p(1500, 0)), transform.map(p(1500, 2000)), 600)]
                assert HasEdge(Outline(v, runs), transform.map(p(1500, 300))), (cls, angle, "end-to-side")
                runs = [cls(transform.map(p(0, 0)), transform.map(p(3000, 0)), 600),
                        cls(transform.map(p(3000, 0)), transform.map(p(3000, 600)), 600),
                        cls(transform.map(p(3000, 600)), transform.map(p(0, 600)), 600)]
                assert HasEdge(Outline(v, runs), transform.map(p(1500, 300))), (cls, angle, "U-shaped chain")
                if angle == 0:
                    v.zoom = .8
                    v.grab().save(str(Path(__file__).resolve().parents[1] / f"diagnostics/{cls.__name__.lower()}-end-merging.png"))
        walls = [Wall(p(0, 0), p(3000, 0), 600), Wall(p(0, 600), p(3000, 600), 600)]
        assert not HasEdge(Outline(v, walls), p(1500, 300)), "Ordinary wall union changed"
    recorder = LineRecorder()
    DrawStairSymbol(recorder, p(), p(0, 1000), 200, stepCount = 10, outline = False, edgeInset = 5)
    rails, treads = recorder.lines[:2], recorder.lines[2:11]
    assert len(treads) == 9
    assert all(abs(abs(line.x1()) - 95) < 1e-6 and line.x1() == line.x2() for line in rails)
    assert all(abs(line.x1()) == 95 and abs(line.x2()) == 95 for line in treads)
    assert all(line.y1() == line.y2() for line in treads)
    print("PASS: counter/stair end-only joins, side seams including U-chains, rotation and inset tread bounds")


if __name__ == "__main__":
    Main()
