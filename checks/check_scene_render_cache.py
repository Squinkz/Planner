"""Retained scene pixels, invalidation, hover reuse and edit-mode fallback."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Wall, Door, SilledWindow, SlidingDoor, Stair, Counter, Railing, Arrow, MeasurementGuide, Furnishing, Label
from planner_app.viewport.widget import DrawingViewport
from planner_app.graphics.theme import BuildStyle


def CompareDirect(viewport):
    viewport.grab()
    cached = viewport.grab().toImage()
    limit = viewport.viewportSceneByteLimit
    panCache = (viewport.viewportPanRaster, viewport.viewportPanKey, viewport.viewportPanOrigin, viewport.viewportPanState)
    viewport.viewportSceneByteLimit = 0
    direct = viewport.grab().toImage()
    viewport.viewportSceneByteLimit = limit
    viewport.viewportPanRaster, viewport.viewportPanKey, viewport.viewportPanOrigin, viewport.viewportPanState = panCache
    assert cached == direct, "Retained scene differs from direct painting"


def Main():
    app = QtWidgets.QApplication([])
    app.setStyleSheet(BuildStyle())
    viewport = DrawingViewport()
    viewport.resize(1200, 900)
    viewport.performanceTimer.stop()
    point = QtCore.QPointF
    wall = Wall(point(-2500, 2000), point(2500, 2000))
    branch = Wall(point(2500, 2000), point(2500, -2000), 120, material = "Lumber")
    contained = Wall(point(-200, 2000), point(200, 2000), 80)
    stair = Stair(point(-2300, 0), point(-2300, -1800), 800)
    counter = Counter(point(-1500, -1500), point(1000, -1500))
    railing = Railing(point(-500, -2500), point(2000, -2500))
    arrow = Arrow(point(-1000, 1000), point(1500, 1000), tipSize = 200)
    guide = MeasurementGuide(point(-1800, 2700), point(1800, 2700))
    desk = Furnishing(viewport.furnishingDefinitions["desk"], point())
    label = Label(point(0, -3000), "Render check")
    door, window, slider = Door(wall, .1, .3), SilledWindow(wall, .4, .6), SlidingDoor(branch, .2, .4)
    viewport.walls = [wall, branch, contained, stair, counter, railing, arrow, guide]
    viewport.windows = [door, window, slider]
    viewport.furnishings = [desk]
    viewport.labels = [label]
    viewport.EnsureObjectIds()
    viewport.show()
    app.processEvents()
    viewport.performanceLabel.hide()

    # Automatic measurements remain hidden during pan; release restores them.
    beforePan = viewport.grab().toImage()
    position = point(600, 450)
    press = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonPress, position,
                             point(viewport.mapToGlobal(position.toPoint())),
                             QtCore.Qt.MouseButton.MiddleButton, QtCore.Qt.MouseButton.MiddleButton,
                             QtCore.Qt.KeyboardModifier.NoModifier)
    release = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonRelease, position,
                               point(viewport.mapToGlobal(position.toPoint())),
                               QtCore.Qt.MouseButton.MiddleButton, QtCore.Qt.MouseButton.NoButton,
                               QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(viewport, press)
    duringPan = viewport.grab().toImage()
    assert viewport.isPanning and viewport.showMeasurements
    viewport.showMeasurements = False
    assert viewport.grab().toImage() == duringPan
    viewport.showMeasurements = True
    viewport.grab()
    QtWidgets.QApplication.sendEvent(viewport, release)
    assert not viewport.isPanning and viewport.showMeasurements
    assert viewport.grab().toImage() == beforePan

    # A release after actual camera movement transfers the pan image without rebuilding geometry.
    QtWidgets.QApplication.sendEvent(viewport, press)
    viewport.panOffset += point(17, 9)
    viewport.grab()
    QtWidgets.QApplication.sendEvent(viewport, release)
    with patch.object(viewport, "DrawScene", wraps = viewport.DrawScene) as sceneDraw:
        viewport.grab()
        assert sceneDraw.call_count == 0 and viewport.viewportScene is not None
        viewport.grab()
        assert sceneDraw.call_count == 0, "Pan release rebuilt the scene on the next frame"
    CompareDirect(viewport)

    # Cancellation ends navigation and restores annotations without moving the camera.
    QtWidgets.QApplication.sendEvent(viewport, press)
    pan = point(viewport.panOffset)
    viewport.CancelInteraction()
    assert not viewport.isPanning and viewport.panOffset == pan
    assert viewport.cursor().shape() != QtCore.Qt.CursorShape.ClosedHandCursor
    viewport.grab()
    assert viewport.viewportPanRaster is None
    CompareDirect(viewport)

    # Scrolled pan pixels must remain exact across pixel-aligned and
    # fractional moves, zooms, and pans beyond the recorded area.
    viewport.isPanning = True
    for zoom in (.2, .7, 1.3):
        viewport.zoom = zoom
        for pan in (point(21.3, -17.7), point(24.3, -16.7), point(24.6, -16.2), point(19.6, -21.2), point(28.6, -16.2), point(1600, -1200)):
            viewport.panOffset = pan
            CompareDirect(viewport)
    viewport.viewportSceneByteLimit = 1
    viewport.grab()
    assert viewport.viewportPanRaster is None
    viewport.viewportSceneByteLimit = 64 * 1024 * 1024
    viewport.isPanning = False

    viewport.grab()
    assert viewport.viewportPanRaster is None, "Pan raster survived after the gesture"
    for zoom in (.2, .7, 1.3):
        viewport.zoom = zoom
        viewport.panOffset = point(21.3, -17.7)
        for selection in ([], [(wall, 0)], [(desk, None)], [(wall, None), (desk, None)]):
            viewport.SetSelection(selection, notify = False)
            for hover in (point(100, 150), viewport.WorldToViewport(point()), viewport.WorldToViewport(wall.firstVertex)):
                viewport.hoverPosition = hover
                CompareDirect(viewport)

    viewport.SetSelection([], notify = False)
    viewport.grab()
    with patch.object(viewport, "DrawScene", wraps = viewport.DrawScene) as sceneDraw:
        with patch.object(viewport, "HitTest", wraps = viewport.HitTest) as hitTest:
            for frame in range(8):
                viewport.hoverPosition = point(100 + frame, 150)
                viewport.grab()
            assert sceneDraw.call_count == 0, "Cursor movement repainted the retained scene"
            assert hitTest.call_count == 8, "Hover hit-test was duplicated"

        mutations = [(wall, "width", 340), (wall, "material", "Brick"),
                     (wall, "firstMiter", .5), (wall, "firstVertex", point(-2700, 2000)),
                     (door, "hingeAtSecond", True), (door, "swingsOutwards", True),
                     (door, "measurementFlipped", True), (door, "length", 700),
                     (window, "sillDepth", 180), (slider, "panelsFlipped", True),
                     (stair, "directionReversed", True), (stair, "autosize", False),
                     (stair, "manualStepCount", 8), (stair, "stepSizeBounds", (200, 330)),
                     (railing, "spacingBounds", (800, 1200, 1000)), (railing, "autosize", False),
                     (railing, "manualPostCount", 7), (arrow, "solidTip", False),
                     (arrow, "tipSize", 300), (arrow, "intensity", .5),
                     (desk, "angle", 31), (desk, "width", 1500), (label, "text", "Changed")]
        for obj, name, value in mutations:
            previous = sceneDraw.call_count
            setattr(obj, name, value)
            viewport.grab()
            assert sceneDraw.call_count == previous + 1, f"Stale scene after changing {type(obj).__name__}.{name}"
            CompareDirect(viewport)
        for name, value in (("showMeasurements", False), ("unitsMode", "Meters" if viewport.unitsMode != "Meters" else "Millimeters"),
                            ("visibility", {**viewport.visibility, "Stairs": False}),
                            ("measurementVisibility", {"walls": False, "stairs": True, "counters": True, "railings": False}),
                            ("measurementSettings", {**viewport.measurementSettings, "walls": 0}),
                            ("objectGroups", [[wall, desk]]), ("hiddenObjectIds", {id(counter)})):
            viewport.grab()
            previous = sceneDraw.call_count
            setattr(viewport, name, value)
            viewport.grab()
            assert sceneDraw.call_count == previous + 1, f"Stale scene after changing {name}"
            CompareDirect(viewport)
        viewport.walls.append(Wall(point(-4000, 0), point(-3000, 0)))
        CompareDirect(viewport)
        viewport.walls.pop()
        CompareDirect(viewport)
        viewport.isPanning = True
        previous = sceneDraw.call_count
        viewport.grab()
        viewport.grab()
        assert sceneDraw.call_count == previous + 1 and viewport.viewportScene is None
        assert viewport.viewportPanRaster is not None
        viewport.isPanning = False
        viewport.furnishingPreview = Furnishing(desk.definition, point(1000, 1000))
        previous = sceneDraw.call_count
        viewport.grab()
        viewport.grab()
        assert sceneDraw.call_count == previous + 2 and viewport.viewportScene is None
        viewport.furnishingPreview = None
        CompareDirect(viewport)
    # Exercise in-place history restoration as well as direct property changes.
    before = viewport.CaptureState()
    wall.secondVertex += point(500, 0)
    viewport.RecordEdit(before)
    CompareDirect(viewport)
    viewport.Undo()
    CompareDirect(viewport)
    viewport.Redo()
    CompareDirect(viewport)
    viewport.close()
    print("PASS: exact cached/direct pixels, property/settings/history invalidation, single hover test and live-edit fallback.")


if __name__ == "__main__":
    Main()
