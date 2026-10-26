"""Selection overlays cannot change ambient splits, hidden spans or stacked tiers."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_room_detection import Rectangle
from check_exterior_hidden_dimensions import Capture, Signature
from check_scene_render_cache import CompareDirect
from planner_app.models import Wall, Door, Window, Stair, Counter, Railing, Furnishing
from planner_app.export_plan import RenderPlan
from planner_app.viewport.rendering import RenderingMixin


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.showMeasurements, v.showTips = True, False
        v.measurementVisibility = dict.fromkeys(v.measurementVisibility, True)
        v.measurementSettings.update(doors = 0, windows = 0, stairs = 2, counters = 2)
        p = QtCore.QPointF
        for angle in (0, 37):
            walls = Rectangle(-2000, -2000, 4000, 4000)
            partition = Wall(p(0, -2000), p(0, 2000), 200)
            door, window = Door(walls[0], .15, .3), Window(walls[2], .15, .35)
            stair = Stair(p(-1200, -1000), p(-1200, 500), 400)
            counter = Counter(p(500, -1000), p(1300, -1000), 400)
            railing = Railing(p(500, 1000), p(1300, 1000), 80)
            desk = Furnishing(v.furnishingDefinitions["desk"], p(-4000, 0))
            transform = QtGui.QTransform().rotate(angle)
            for obj in walls + [partition, stair, counter, railing, desk]:
                obj.firstVertex = transform.map(obj.firstVertex)
                obj.secondVertex = transform.map(obj.secondVertex)
            InstallScene(main, walls + [partition, door, window, stair, counter, railing, desk])
            for mode in ("All", "Exterior", "Exterior stacked"):
                v.wallMeasurementMode = mode
                for reference in ("Centerline", "Wall faces"):
                    v.wallMeasurementReference = reference
                    for hidden in (False, True):
                        window.measurementHidden = hidden
                        walls[0].measurementHidden = hidden
                        v.SetSelection([])
                        baseline = Capture(v)
                        for entries in ([(window, None)], [(window, 0)], [(walls[0], None)], [(walls[0], 0)],
                                        [(partition, None)], [(stair, None)], [(counter, None)], [(railing, None)],
                                        [(desk, None)], [(door, None), (window, None)]):
                            v.SetSelection(entries)
                            assert Capture(v) == baseline, (angle, mode, reference, hidden, entries)
                            assert v.selectionMeasurements
                        # Group bounds supplement world dimensions; they cannot
                        # replace the members' ambient measurements.
                        v.objectGroups = [(walls[0], walls[1])]
                        v.SetSelection([(walls[0], None), (walls[1], None)])
                        assert Capture(v) == baseline
                        assert len(v.selectionMeasurements) == 4
                        v.objectGroups = []
                        v.SetSelection([(window, None)])
                        Capture(v)
                        CompareDirect(v)
                    # Exports keep the ambient spans even with editor selection.
                    expected = Capture(v)
                    data = main.BuildProjectData(includeHistory = False, includeActivity = False)
                    observations = []
                    draw = RenderingMixin.DrawSceneMeasurements

                    def Draw(viewport, *args, **kwargs):
                        result = draw(viewport, *args, **kwargs)
                        observations.append(Signature(viewport))
                        assert not viewport.selectionMeasurements
                        return result

                    with patch.object(RenderingMixin, "DrawSceneMeasurements", Draw):
                        for kind in ("png", "svg"):
                            result = RenderPlan(folder / "overlay.plan", 80, (-6500, -6500, 13000, 13000),
                                                outputFormat = kind, projectData = data, applyTheme = False)
                            assert not result.isNull() if kind == "png" else QtSvg.QSvgRenderer(result).isValid()
                    assert observations and all(spans == expected for spans in observations)
            # Turning ambient dimensions off still permits selection overlays.
            v.showMeasurements = False
            v.SetSelection([(window, None)])
            assert not Capture(v) and v.selectionMeasurements
            v.showMeasurements = True
        # All-mode one-sided and unsplit preferences are also independent of
        # selection, not just the two-sided opening chains tested above.
        v.wallMeasurementMode = "All"
        window.measurementHidden = walls[0].measurementHidden = False
        for split in (0, 1, 2):
            v.measurementSettings.update(doors = split, windows = split)
            v.SetSelection([])
            baseline = Capture(v)
            for entries in ([(window, None)], [(walls[0], None)], [(door, None), (window, None)]):
                v.SetSelection(entries)
                assert Capture(v) == baseline
    print("PASS: selection-independent world chains in all modes/references, rotated/hidden objects, groups, cache and exports")


if __name__ == "__main__":
    Main()
