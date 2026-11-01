"""Exact retained/previous annotation pixels, cache reuse and edit handoffs."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_room_detection import Rectangle
from planner_app.models import Wall, Door, Window, Furnishing, MeasurementGuide, AngleGuide
from planner_app.units import unitModes
from planner_app.graphics import palette
from planner_app.project_codec import DecodeProject


def Compare(v, context = "", zoomChanged = True):
    v.viewportSceneKey = None
    v.measurementPictures = []
    v.measurementPaintZoom = v.zoom / (1.1 if zoomChanged else 1)
    actual = v.grab().toImage()
    v.viewportSceneKey = None
    v.measurementPictures = []
    v.measurementPaintZoom = v.zoom / (1.1 if zoomChanged else 1)
    with patch.object(v, "DrawRetainedMeasurements", return_value = False):
        expected = v.grab().toImage()
    if actual != expected:
        output = Path(__file__).resolve().parents[1] / "diagnostics"
        actual.save(str(output / "retained-dimensions-actual.png"))
        expected.save(str(output / "retained-dimensions-expected.png"))
        raise AssertionError((context, v.devicePixelRatioF(), v.zoom, v.unitsMode, "Retained/previous pixels differ"))
    return actual


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        p = QtCore.QPointF
        walls = Rectangle(-4700, -3200, 9400, 6400)
        angled = Wall(p(-5200, 4400), p(3000, 6300), 180)
        door, window = Door(walls[0], .2, .37), Window(walls[2], .4, .6)
        furnishing = Furnishing(v.furnishingDefinitions["desk"], p(1600, 1300))
        objects = [*walls, angled, door, window, furnishing, *Rectangle(45000, 45000, 5000, 5000)]
        InstallScene(main, objects)
        v.setFixedSize(1001, 701)
        v.showMeasurements = True
        v.showTips = False
        v.zoom = .32
        for mode in ("All", "Exterior", "Exterior stacked"):
            v.wallMeasurementMode = mode
            for reference in ("Wall faces", "Centerline"):
                v.wallMeasurementReference = reference
                Compare(v, (mode, reference))
                Compare(v, (mode, reference, "complete recording"), zoomChanged = False)
                retained = v.retainedMeasurements
                assert retained is not None and retained.entries
                for factor in (1.12, .8, 1.6, .7):
                    v.ZoomBy(factor, v.DrawingRect().center() + p(63, -47))
                    Compare(v, (mode, reference, factor))
                    assert v.retainedMeasurements is retained, "Zoom replaced retained world ownership"
                v.panOffset += p(17.3, -29.7)
                Compare(v, "fractional pan")
        for units in unitModes:
            v.unitsMode = units
            Compare(v, units)
        for selection in ([(walls[0], None)], [(furnishing, None)], [(walls[1], 0)], []):
            v.SetSelection(selection)
            Compare(v, "selection")
        for width in (0, .4, .7, 1, 1.6):
            v.lineWidths["dimensions"] = width
            Compare(v, ("line width", width))
        for precision in ("High", "Medium", "Low"):
            v.measurementPrecision = precision
            Compare(v, precision)
        for mode in ("Adaptive Metric", "Adaptive Imperial"):
            if mode not in unitModes:
                continue
            v.unitsMode = mode
            retained = None
            for zoom in (.03, .3, 3, 30):
                v.zoom = zoom
                v.panOffset = p(0, walls[0].firstVertex.y() * v.basePixelsPerMillimeter * zoom)
                Compare(v, ("adaptive threshold", mode, zoom))
                if retained is not None:
                    assert v.retainedMeasurements is retained
                retained = v.retainedMeasurements
        v.zoom = .32
        v.panOffset = p()
        with patch.dict(palette.themeColors, {"measurementLine": "#807b878c", "objectOutline": "#c0d8e3e9"}):
            Compare(v, "translucent ink")
        for theme in ("Light Canvas", "Deep Blueprint Canvas", "Dark Canvas"):
            if theme in palette.themeDefinitions:
                main.SetThemes(canvasTheme = theme)
                Compare(v, theme)
        font = QtGui.QFont(v.font())
        font.setPointSizeF(12)
        v.setFont(font)
        Compare(v, "font")
        retained = v.retainedMeasurements
        angled.firstVertex.setX(angled.firstVertex.x() - 250)
        Compare(v, "in-place geometry")
        assert v.retainedMeasurements is not retained
        door.measurementHidden = True
        Compare(v, "hidden opening dimension")
        v.visibility["Windows"] = False
        Compare(v, "visibility")
        v.showMeasurements = False
        v.SetSelection([(furnishing, None)])
        Compare(v, "selected dimensions with global dimensions off")
        v.showMeasurements = True
        v.SetSelection([])
        v.isPanning = True
        v.panOffset += p(21, -13)
        v.grab()
        v.isPanning = False
        Compare(v, "pan release")
        v.isDragging = True
        Compare(v, "live edit fallback")
        v.isDragging = False
        Compare(v, "edit release")
        guide = MeasurementGuide(p(-3500, 5000), p(3500, 5000))
        guide.textOffset = p(300, -200)
        guide.depth = 450
        for extra in (guide, AngleGuide(p(2000, 0), p(0, 2000), middleVertex = p())):
            InstallScene(main, objects + [extra])
            Compare(v, "guide fallback")
            assert v.retainedMeasurements is None, "Manual guides entered ordinary dimension cache"
        InstallScene(main, objects)
        Compare(v, "guide removed")
        assert v.retainedMeasurements is not None
        v.exportRender = True
        Compare(v, "export fallback")
        assert v.retainedMeasurements is None
        v.exportRender = False
        initial = Compare(v, "before history")
        before = v.CaptureState()
        v.walls[0].firstVertex.setX(v.walls[0].firstVertex.x() - 325)
        v.RecordEdit(before)
        changed = Compare(v, "recorded edit")
        v.Undo()
        assert Compare(v, "undo") == initial
        v.Redo()
        assert Compare(v, "redo") == changed
        project = main.BuildProjectData()
        old = v.retainedMeasurements
        main.ApplyProject(DecodeProject(project, v.furnishingDefinitions), None)
        Compare(v, "project replacement")
        assert v.retainedMeasurements is not old
        InstallScene(main, [])
        Compare(v, "empty project")
        assert v.retainedMeasurements is None or not v.retainedMeasurements.entries
    print("Exact retained/previous pixels, native reuse, units, styles, selections, geometry, pan/edit and guide/export handoffs passed")


if __name__ == "__main__":
    Main()
