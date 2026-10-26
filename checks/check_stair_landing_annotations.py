"""Inset landing outlines and unambiguous directed stair chains."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Stair
from check_run_end_merging import HasEdge
from check_scene_render_cache import CompareDirect
from planner_app.export_plan import RenderPlan


def Main():
    p = QtCore.QPointF
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.showMeasurements = v.showTips = False
        for angle in (0, 37):
            transform = QtGui.QTransform().translate(-1500, -300).rotate(angle)
            stairs = [Stair(transform.map(p(0, 0)), transform.map(p(3000, 0)), 600),
                      Stair(transform.map(p(3000, 0)), transform.map(p(3000, 600)), 600),
                      Stair(transform.map(p(3000, 600)), transform.map(p(0, 600)), 600)]
            InstallScene(main, stairs)
            v.grab()
            arrows = v.stairArrowRuns
            assert len(arrows) == 3 and sum(showTip for stair, start, tip, showTip in arrows) == 1
            assert QtCore.QLineF(arrows[0][2], arrows[1][1]).length() < .001
            assert QtCore.QLineF(arrows[1][2], arrows[2][1]).length() < .001
            path = QtGui.QPainterPath()
            toWorld = QtGui.QTransform().scale(1 / v.basePixelsPerMillimeter, -1 / v.basePixelsPerMillimeter)
            for stair, line in v.stairInsetLines:
                line = toWorld.map(line)
                path.moveTo(line.p1())
                path.lineTo(line.p2())
            assert HasEdge(path, transform.map(p(3275, 300))), "Outer landing inset is missing"
            assert HasEdge(path, transform.map(p(2725, 300))), "Inset must wrap the side-seam tip"
            assert not HasEdge(path, transform.map(p(25, 0))), "No extra terminal-end inset cap"
            CompareDirect(v)
            key = v.stairGeometryKey
            inset = v.stairInsetLines
            stairs[2].directionReversed = True
            v.grab()
            assert v.stairGeometryKey == key and v.stairInsetLines is inset
            assert sum(showTip for stair, start, tip, showTip in v.stairArrowRuns) == 2
            stairs[2].directionReversed = False
            v.grab()
            if angle == 0:
                v.grab().save(str(Path(__file__).resolve().parents[1] / "diagnostics/stair-landing-annotations.png"))
                data = main.BuildProjectData(includeHistory = False)
                for format in ("png", "svg"):
                    output = RenderPlan(folder / "stairs.plan", 100, bounds = [-2500, -1500, 5000, 3000],
                                        projectData = data, outputFormat = format, applyTheme = False)
                    assert output if format == "png" else QtSvg.QSvgRenderer(output).isValid()
        # Three-way branches do not choose an arbitrary continuation.
        stairs = [Stair(p(-2000, 0), p(), 600), Stair(p(), p(2000, 0), 600), Stair(p(), p(0, 2000), 600)]
        InstallScene(main, stairs)
        v.grab()
        assert len(v.stairArrowRuns) == 3 and all(showTip for stair, start, tip, showTip in v.stairArrowRuns)
        # Independent directed cycles each retain a visible direction head.
        points = [p(0, 0), p(2000, 0), p(2000, 2000), p(0, 2000)]
        cycles = [Stair(first + offset, second + offset, 600) for offset in (p(), p(5000, 0))
                  for first, second in zip(points, points[1:] + points[:1])]
        InstallScene(main, cycles)
        v.grab()
        assert len(v.stairArrowRuns) == 8 and sum(showTip for stair, start, tip, showTip in v.stairArrowRuns) == 2
    print("PASS: continuous U-landing insets/arrows, rotated geometry, reversal, branches and PNG/SVG")


if __name__ == "__main__":
    Main()
