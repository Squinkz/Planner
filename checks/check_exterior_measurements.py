"""Exterior wall dimensions, settings persistence, export and retained caches."""
import copy
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets, QtSvg
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_room_detection import Rectangle
from check_scene_render_cache import CompareDirect
from planner_app.models import Wall, Door, Counter
from planner_app.project_codec import DecodeProject
from planner_app.project_recovery import RecoverProject
from planner_app.export_plan import RenderPlan
from planner_app.viewport.rendering import RenderingMixin
from planner_app.viewport.widget import DrawingViewport


def Dimensions(viewport):
    viewport.grab()
    return viewport.sceneMeasurements[1]


def Main():
    p = QtCore.QPointF
    with ExampleWindow() as (main, folder):
        v = main.viewport
        walls = Rectangle(0, 0, 4000, 4000)
        partition = Wall(p(2000, 0), p(2000, 4000), 200)
        island = Wall(p(500, 1000), p(1500, 1000), 100)
        InstallScene(main, walls + [partition, island])
        v.showMeasurements = True
        v.measurementVisibility = dict.fromkeys(v.measurementVisibility, False)
        v.measurementVisibility["walls"] = True
        v.measurementSettings["doors"] = 0
        main.ShowSettings()
        panel = main.settingsWindow
        field = panel.wallMeasurementModeField
        assert field.currentText() == v.wallMeasurementMode == "Exterior stacked"
        assert panel.wallMeasurementHeading.titleLabel.text() == "Walls"
        assert panel.wallMeasurementHeading.objectName() == "sectionHeading"
        field.setCurrentText("All")
        assert [field.itemText(index) for index in range(field.count())] == ["All", "Exterior", "Exterior stacked"]
        assert field.model().item(2).isEnabled()
        allSpans = Dimensions(v)
        assert len(allSpans) > 4 and any(island in owners for first, second, owners in allSpans)
        field.setCurrentText("Exterior")
        exterior = Dimensions(v)
        assert len(exterior) == 4, exterior
        assert all(partition not in owners and island not in owners for first, second, owners in exterior)
        assert all((first.x() == second.x() and first.x() in (-100, 4100))
                   or (first.y() == second.y() and first.y() in (-100, 4100)) for first, second, owners in exterior)
        CompareDirect(v)
        cached = v.sceneMeasurements
        v.panOffset += p(13, -7)
        assert Dimensions(v) == exterior and v.sceneMeasurements is cached
        # Selection must not restore a culled interior wall through the fallback.
        v.SetSelection([(partition, None)])
        assert all(partition not in owners for first, second, owners in Dimensions(v))
        v.SetSelection([])
        # Exterior door splits retain their ordinary opening ownership.
        door = Door(walls[0], .25, .5)
        v.windows = [door]
        split = Dimensions(v)
        assert len(split) == 6 and any(door in owners for first, second, owners in split)
        v.windows = []
        counter = Counter(p(500, 1500), p(1500, 1500), 400)
        v.walls.append(counter)
        v.measurementVisibility["counters"] = True
        counterExterior = [(first, second) for first, second, owners in Dimensions(v) if counter in owners]
        field.setCurrentText("All")
        assert counterExterior == [(first, second) for first, second, owners in Dimensions(v) if counter in owners]
        # Concave outlines and disconnected buildings retain their actual edges.
        points = [p(0, 0), p(4000, 0), p(4000, 2000), p(2000, 2000), p(2000, 4000), p(0, 4000)]
        concave = [Wall(first, second, 200) for first, second in zip(points, points[1:] + points[:1])]
        InstallScene(main, concave)
        field.setCurrentText("Exterior")
        assert len(Dimensions(v)) == 6
        InstallScene(main, walls + Rectangle(-6000, -5000, 3000, 3000))
        assert len(Dimensions(v)) == 8
        # Save/open and recovery retain the mode; old files default to All.
        path = folder / "exterior.plan"
        assert main.SaveProject(path)
        data = main.BuildProjectData()
        assert data["settings"]["wallMeasurementMode"] == "Exterior"
        recovered, repairs = RecoverProject(data, v.furnishingDefinitions, main.defaultProjectData)
        assert not repairs and recovered[5]["wallMeasurementMode"] == "Exterior"
        field.setCurrentText("All")
        assert main.OpenProject(path)
        assert v.wallMeasurementMode == field.currentText() == "Exterior"
        assert len(Dimensions(v)) == 8
        legacy = copy.deepcopy(data)
        legacy["settings"].pop("wallMeasurementMode")
        assert DecodeProject(legacy, v.furnishingDefinitions)[5]["wallMeasurementMode"] == "All"
        invalid = copy.deepcopy(data)
        invalid["settings"]["wallMeasurementMode"] = "Unknown mode"
        try:
            DecodeProject(invalid, v.furnishingDefinitions)
        except ValueError:
            pass
        else:
            raise AssertionError("Unimplemented mode was accepted")
        # Settings changes while Export is active update the project and preview.
        main.sidebarTabs.setCurrentWidget(main.exportPanel)
        field.setCurrentText("All")
        assert v.wallMeasurementMode == main.exportPanel.projectView["wallMeasurementMode"] == "All"
        field.setCurrentText("Exterior")
        assert v.wallMeasurementMode == main.exportPanel.projectView["wallMeasurementMode"] == "Exterior"
        source = DrawingViewport()
        v.exportOverlay.ConfigureSnapshotViewport(source)
        assert source.wallMeasurementMode == "Exterior"
        source.close()
        main.sidebarTabs.setCurrentIndex(0)
        assert v.wallMeasurementMode == "Exterior"
        observed = []
        draw = RenderingMixin.DrawSceneMeasurements

        def DrawSceneMeasurements(viewport, *args, **kwargs):
            result = draw(viewport, *args, **kwargs)
            observed.append((viewport.wallMeasurementMode, len(viewport.sceneMeasurements[1])))
            return result

        with patch.object(RenderingMixin, "DrawSceneMeasurements", DrawSceneMeasurements):
            for format in ("png", "svg"):
                image = RenderPlan(path, 100, bounds = [-7000, -6000, 13000, 12000],
                                   projectData = data, outputFormat = format, applyTheme = False, useExportSettings = True)
                assert image if format == "png" else QtSvg.QSvgRenderer(image).isValid()
        assert observed and all(mode == "Exterior" and count == 8 for mode, count in observed), observed
    print("PASS: exterior-only measurements, splits, cache invalidation, persistence and PNG/SVG export")


if __name__ == "__main__":
    Main()
