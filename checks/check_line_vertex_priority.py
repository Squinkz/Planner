"""Annotation bodies inside walls must not intercept visible control points."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtTest
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Stair, Railing, Counter, Arrow, MeasurementGuide, BoundaryLine, DashedLine, SolidLine, Window
from check_history import Drag


def Main():
    p = QtCore.QPointF
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.snapEnabled = v.connectedVerticesEnabled = v.connectedObjectsEnabled = False
        v.showTips = v.showMeasurements = False
        for lineType in (BoundaryLine, DashedLine, SolidLine):
            for targetType in (Wall, Stair, Railing, Counter, Arrow, MeasurementGuide, Window):
                for endpoint in (0, 1):
                    cover = Wall(p(-2000, 0), p(2000, 0), 600)
                    line = lineType(p(-1800, 0), p(1800, 0))
                    if targetType is Window:
                        target = Window(cover, .5, .8) if endpoint == 0 else Window(cover, .2, .5)
                    else:
                        first, second = (p(), p(0, 1200)) if endpoint == 0 else (p(0, 1200), p())
                        target = targetType(first, second)
                    InstallScene(main, [cover, target, line])
                    v.SetSelection([(target, None)] if targetType is Counter else [])
                    position = v.WorldToViewport(p())
                    QtTest.QTest.mouseMove(v, position.toPoint())
                    assert v.HitTest(position) == (target, endpoint), (lineType, targetType, endpoint, v.HitTest(position))
                    v.SetSelection([(target, endpoint)])
                    assert v.HitTest(position) == (target, endpoint)
                    # Away from control points the line remains selectable,
                    # including when its covering wall is selected.
                    v.SetSelection([(cover, None)])
                    assert v.HitTest(v.WorldToViewport(p(-1000, 0))) == (line, None)
                    v.hiddenObjectIds = {id(target)}
                    assert v.HitTest(position) == (line, None)
                    v.hiddenObjectIds = set()
            cover = Wall(p(-2000, 0), p(2000, 0), 600)
            target = Wall(p(), p(0, 1200), 120)
            line = lineType(p(-1800, 0), p(1800, 0))
            InstallScene(main, [cover, target, line])
            first, second = p(target.firstVertex), p(target.secondVertex)
            lineEnds = p(line.firstVertex), p(line.secondVertex)
            Drag(v, v.WorldToViewport(first).toPoint(), v.WorldToViewport(p(200, 100)).toPoint())
            assert target.firstVertex != first and target.secondVertex == second
            assert (line.firstVertex, line.secondVertex) == lineEnds
            v.Undo()
            assert target.firstVertex == first and target.secondVertex == second
    print("PASS: wall/architectural/annotation/opening endpoints beat line bodies, with drag and undo")


if __name__ == "__main__":
    Main()
