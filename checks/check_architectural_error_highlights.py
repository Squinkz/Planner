"""Stationary architectural placement errors use canvas warnings, never export colors."""
import copy
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Pillar, Column, Counter, Stair, Railing, Elevator, Door, Window, Fireplace
from planner_app.graphics.palette import themeColors
from planner_app.scene_problems import FindSceneProblems
from planner_app.export_plan import RenderPlan
from planner_app.graphics.svg_preview import SvgPreviewRenderer
from check_scene_render_cache import CompareDirect


def WarningPixels(image):
    image = image.convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
    color = QtGui.QColor(themeColors["warningOutline"])
    return bytes(image.constBits()).count(bytes((color.red(), color.green(), color.blue(), 255)))


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.showGrid = v.showMeasurements = False
        v.verifyRenderRevisions = True
        point = QtCore.QPointF
        for cls in (Wall, Pillar, Column, Counter, Stair, Railing, Elevator, Door, Window, Fireplace):
            v.collisionSettings = dict.fromkeys(v.collisionSettings, True)
            if cls in (Door, Window, Fireplace):
                parent = Wall(point(-2500, 0), point(2500, 0), 240)
                obj, blocker = cls(parent, .2, .6), Window(parent, .4, .7)
                objects = [parent, obj, blocker]
            else:
                obj = cls(point(-1800, 0), point(1800, 0), 600)
                blocker = Elevator(point(1000, -200), point(1000, 600), 800)
                objects = [obj, blocker]
            InstallScene(main, objects)
            assert not v.ArchitecturalPlacementFits(obj), cls.__name__
            assert any(issue["object"] is obj for issue in FindSceneProblems(v, includePotential = False)), cls.__name__
            before = v.CaptureState()
            image = v.grab().toImage()
            assert id(obj) in v.scenePreparation[1]["invalidArchitecture"], cls.__name__
            assert WarningPixels(image) > 0, cls.__name__ + " has no stationary error highlight"
            assert v.CaptureState() == before, "Drawing warnings edited geometry"
            # Collision switches are render-key inputs, including direct changes.
            v.collisionSettings = dict.fromkeys(v.collisionSettings, False)
            image = v.grab().toImage()
            expectedInvalid = {id(other) for other in objects if not v.ArchitecturalPlacementFits(other)}
            assert v.scenePreparation[1]["invalidArchitecture"] == expectedInvalid
            # Overlapping openings on the same wall remain intrinsically invalid,
            # even when optional collision categories are disabled.
            assert bool(WarningPixels(image)) == bool(expectedInvalid), cls.__name__

        v.collisionSettings = dict.fromkeys(v.collisionSettings, True)
        # An isolated duplicate counter must supply its own warning pixels.
        # Checking only a mixed scene can accidentally count its blocker instead.
        oldWidth = v.lineWidths["architectural"]
        v.collisionSettings = dict.fromkeys(v.collisionSettings, False)
        for cls in (Counter, Railing):
            first, second = [cls(point(-1800, 0), point(1800, 0), 600) for repeat in range(2)]
            InstallScene(main, [first, second])
            v.lineWidths["architectural"] = 6
            for selected in (False, True):
                v.SetSelection([(second, None)] if selected else [])
                image = v.grab().toImage()
                assert WarningPixels(image) > 0, cls.__name__ + " lost its duplicate highlight"
                # Sample the middle of a long outer edge, away from handles.
                # A surface-only clip leaves a black half-stroke here.
                center = v.WorldToViewport(point(-900, 300)) * image.devicePixelRatioF()
                colors = [image.pixelColor(round(center.x()), round(center.y()) + offset)
                          for offset in range(-2, 3)]
                assert QtGui.QColor(themeColors["wallOutline"]) not in colors, (cls.__name__, selected, [color.name() for color in colors])
        v.lineWidths["architectural"] = oldWidth
        v.collisionSettings = dict.fromkeys(v.collisionSettings, True)
        obj = Counter(point(-1800, 0), point(1800, 0), 600)
        blocker = Elevator(point(1000, -200), point(1000, 600), 800)
        InstallScene(main, [obj, blocker])
        v.grab()
        v.grab()
        with patch.object(v, "ArchitecturalPlacementFits", wraps = v.ArchitecturalPlacementFits) as validate:
            for offset in range(3):
                v.hoverPosition = point(20 + offset, 20)
                v.grab()
            v.panOffset += point(2, 1)
            v.grab()
            assert validate.call_count == 0, "Warm navigation repeated placement checks"
        before = v.CaptureState()
        blocker.firstVertex += point(10000, 0)
        blocker.secondVertex += point(10000, 0)
        v.RecordEdit(before)
        CompareDirect(v)
        assert WarningPixels(v.grab().toImage()) == 0
        v.Undo()
        CompareDirect(v)
        assert WarningPixels(v.grab().toImage()) > 0

        # PNG, SVG and export preview retain ordinary artwork. Changing collision
        # checks alone must not change the rendered file or its geometry.
        data = main.BuildProjectData(includeHistory = False)
        disabled = copy.deepcopy(data)
        disabled["settings"]["collisionSettings"] = dict.fromkeys(v.collisionSettings, False)
        for outputFormat in ("png", "svg"):
            options = dict(bounds = (-3000, -1500, 6000, 3500), outputFormat = outputFormat,
                           applyTheme = False, furnishingDefinitions = v.furnishingDefinitions)
            actual = RenderPlan("Architecture.plan", 100, projectData = data, **options)
            expected = RenderPlan("Architecture.plan", 100, projectData = disabled, **options)
            if outputFormat == "svg":
                assert actual == expected, "Editor warning changed vector export"
                renderer = SvgPreviewRenderer(actual)
                image = QtGui.QImage(600, 350, QtGui.QImage.Format.Format_ARGB32)
                image.fill("white")
                with QtGui.QPainter(image) as painter:
                    renderer.render(painter)
                actual = image
            else:
                assert actual == expected, "Editor warning changed PNG export"
            assert WarningPixels(actual) == 0
        main.sidebarTabs.setCurrentWidget(main.exportPanel)
        v.grab()
        assert getattr(v.exportOverlay.snapshotViewport, "exportRender", False)
    print("Architectural error highlights: all types, checker agreement, collision toggles, cached navigation, undo and export isolation passed")


if __name__ == "__main__":
    Main()
