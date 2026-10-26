"""Hidden exterior dimensions preserve continuous chains and compact stacks."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_room_detection import Rectangle
from check_scene_render_cache import CompareDirect
from planner_app.models import Wall, Window, Door
from planner_app.export_plan import RenderPlan
from planner_app.viewport.rendering import RenderingMixin


def Signature(viewport):
    return sorted((*(round(value, 5) for value in (first.x(), first.y(), second.x(), second.y())), tier)
                  for rows, stacked in ((viewport.sceneMeasurements[1], False), (viewport.sceneMeasurements[2], True))
                  for first, second, owners, *extra in rows for tier in ([extra[0]] if stacked else [0]))


def Capture(viewport):
    # A replayed measurement picture need not refresh the diagnostic span
    # container. Force this probe to inspect the current computed spans.
    viewport.measurementPictures = []
    viewport.grab()
    return Signature(viewport)


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.showMeasurements, v.showTips = True, False
        v.measurementVisibility = {key: key == "walls" for key in v.measurementVisibility}
        v.measurementSettings.update(doors = 0, windows = 0, stairs = 2, counters = 2)
        p = QtCore.QPointF
        for mode in ("All", "Exterior", "Exterior stacked"):
            v.wallMeasurementMode = mode
            for reference in ("Centerline", "Wall faces"):
                v.wallMeasurementReference = reference
                for openingType in (Window, Door):
                    walls = Rectangle(-2000, -2000, 4000, 4000)
                    opening = openingType(walls[0], .25, .5)
                    InstallScene(main, walls)
                    baseline = Capture(v)
                    roomAreas = [region["area"] for region in v.roomDetection.regions]
                    assert len(baseline) == (8 if mode == "All" else 4)
                    v.windows = [opening]
                    shown = Capture(v)
                    assert shown != baseline
                    before = v.CaptureState()
                    opening.measurementHidden = True
                    v.RecordEdit(before)
                    assert Capture(v) == baseline, (mode, reference, openingType, Signature(v), baseline)
                    assert [region["area"] for region in v.roomDetection.regions] == roomAreas
                    assert not v.sceneMeasurements[2], "Hidden openings retained an unnecessary outer tier"
                    v.Undo()
                    assert Capture(v) == shown
                    v.Redo()
                    assert Capture(v) == baseline
                    v.SetSelection([(opening, None)])
                    assert Capture(v) == baseline
                    assert any(opening in owners for first, second, owners in v.selectionMeasurements)
                    v.SetSelection([])
                    assert Capture(v) == baseline
                    CompareDirect(v)
                    # Hiding a parent wall also suppresses its opening's chain.
                    opening.measurementHidden = False
                    walls[0].measurementHidden = True
                    Capture(v)
                    assert all(opening not in owners and walls[0] not in owners
                               for rows in v.sceneMeasurements[1:] for first, second, owners, *extra in rows)
                    walls[0].measurementHidden = False
                    opening.measurementHidden = True
                    expected = Capture(v)
                    data = main.BuildProjectData(includeHistory = False, includeActivity = False)
                    observed = []
                    draw = RenderingMixin.DrawSceneMeasurements

                    def Draw(viewport, *args, **kwargs):
                        result = draw(viewport, *args, **kwargs)
                        observed.append(Signature(viewport))
                        return result

                    with patch.object(RenderingMixin, "DrawSceneMeasurements", Draw):
                        for kind in ("png", "svg"):
                            output = RenderPlan(folder / "hidden.plan", 100, (-3000, -3000, 6000, 6000),
                                outputFormat = kind, projectData = data, applyTheme = False)
                            assert not output.isNull() if kind == "png" else QtSvg.QSvgRenderer(output).isValid()
                    assert observed and all(value == expected for value in observed)
            # A hidden segment cannot borrow a collinear neighbor's ownership
            # to keep drawing its dimensions, on any stacked tier.
            for reference in ("Centerline", "Wall faces"):
                v.wallMeasurementReference = reference
                for angle in (0, 37):
                    transform = QtGui.QTransform().rotate(angle)
                    toLocal = transform.inverted()[0]
                    walls = Rectangle(-2000, -2000, 4000, 4000)
                    left = Wall(p(-2000, -2000), p(0, -2000), 200)
                    right = Wall(p(0, -2000), p(2000, -2000), 200)
                    for wall in [left, right] + walls[1:]:
                        wall.firstVertex = transform.map(wall.firstVertex)
                        wall.secondVertex = transform.map(wall.secondVertex)
                    InstallScene(main, [left, right] + walls[1:])
                    right.measurementHidden = True
                    Capture(v)
                    bottom = [(toLocal.map(first), toLocal.map(second)) for rows in v.sceneMeasurements[1:]
                              for first, second, owners, *extra in rows
                              if toLocal.map(first).y() < -2000 and toLocal.map(second).y() < -2000]
                    assert bottom and all(max(first.x(), second.x()) <= .01 for first, second in bottom), (mode, bottom)
                    left.measurementHidden = True
                    Capture(v)
                    assert not [(first, second) for rows in v.sceneMeasurements[1:]
                                for first, second, owners, *extra in rows
                                if toLocal.map(first).y() < -2000 and toLocal.map(second).y() < -2000]
                    v.SetSelection([(left, None)])
                    Capture(v)
                    assert any(left in owners for first, second, owners in v.selectionMeasurements)
                    v.SetSelection([])
    print("PASS: hidden openings/parents, contiguous collinear walls, stack compaction, selection, undo and PNG/SVG")


if __name__ == "__main__":
    Main()
