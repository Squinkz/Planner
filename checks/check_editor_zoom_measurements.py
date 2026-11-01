"""Zoom reuses world dimension planning and exactly redraws visible annotations."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_room_detection import Rectangle
from planner_app.models import Wall, Door, Window, Furnishing, MeasurementGuide
from planner_app.viewport import rendering


def FreshFrame(v):
    v.viewportSceneKey = None
    v.viewportPanRaster = v.viewportPanKey = None
    v.sceneMeasurements = None
    v.measurementPictures = []
    v.measurementPaintZoom = v.zoom
    return v.grab().toImage()


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        p = QtCore.QPointF
        walls = Rectangle(-5000, -3500, 10000, 7000)
        partition = Wall(p(0, -3500), p(0, 3500), 200)
        door, window = Door(walls[0], .15, .3), Window(walls[2], .3, .5)
        guide = MeasurementGuide(p(-4500, 4700), p(4500, 4700))
        guide.textOffset = p(450, -200)
        furnishing = Furnishing(v.furnishingDefinitions["desk"], p(2400, 1500))
        InstallScene(main, [*walls, partition, door, window, guide, furnishing,
                            *Rectangle(50000, 50000, 8000, 6000)])
        v.setFixedSize(1000, 700)
        v.showTips = False
        v.showMeasurements = True
        v.zoom = .3
        anchor = v.DrawingRect().center() + p(95, -60)
        for mode in ("All", "Exterior", "Exterior stacked"):
            v.wallMeasurementMode = mode
            for reference in ("Wall faces", "Centerline"):
                v.wallMeasurementReference = reference
                FreshFrame(v)
                for factor in (1.1, 1.4, .6, 2.3, .5):
                    spans = v.sceneMeasurements
                    world = v.ViewportToWorld(anchor)
                    with patch.object(rendering, "BuildMeasurementStacks", side_effect = AssertionError("Zoom rebuilt world stacks")):
                        v.ZoomBy(factor, anchor)
                        actual = v.grab().toImage()
                    assert v.sceneMeasurements is spans, "Zoom rebuilt world dimension ownership"
                    assert (v.ViewportToWorld(anchor) - world).manhattanLength() < 1e-6, "Zoom anchor moved"
                    assert actual == FreshFrame(v), (mode, reference, factor, "Zoom differs from complete current-camera redraw")
                    # A clipped zoom recording must not become a pan picture.
                    v.isPanning = True
                    v.panOffset += p(19, -11)
                    v.grab()
                    v.isPanning = False
                    v.viewportSceneKey = None
                    panned = v.grab().toImage()
                    assert panned == FreshFrame(v), "Panning retained a partially recorded zoom frame"
        for index, mutate in enumerate((
                lambda: walls[0].firstVertex.setX(walls[0].firstVertex.x() - 150),
                lambda: setattr(door, "measurementHidden", True),
                lambda: v.SetSelection([(furnishing, None)]),
                lambda: v.measurementSettings.__setitem__("doors", 1 - v.measurementSettings["doors"]),
                lambda: v.visibility.__setitem__("Windows", not v.visibility["Windows"]))):
            previous = v.sceneMeasurements
            mutate()
            v.viewportSceneKey = None
            actual = v.grab().toImage()
            assert v.sceneMeasurements is not previous, (index, "Scene edit reused stale dimension geometry")
            assert actual == FreshFrame(v), "Edited dimensions differ from fresh rendering"
        assert v.rasterCacheBudget.RetainedBytes() <= v.viewportRasterByteLimit
    print("Exact zoom/full-redraw pixels, world-span reuse, cursor anchoring, pan handoff and edit invalidation passed")


if __name__ == "__main__":
    Main()
