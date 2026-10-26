"""Selection overrides measurement visibility, splitting, and obstruction."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Wall, Pillar, Column, Stair, Counter, Railing, Window, Door, Furnishing, Label, Arrow, MeasurementGuide
from planner_app.viewport.widget import DrawingViewport


class MeasurementPainter(QtGui.QPainter):
    def __init__(self, image):
        super().__init__(image)
        self.labels = []

    def drawText(self, *arguments):
        self.labels.append(arguments[-1])
        return super().drawText(*arguments)


def RenderLabels(viewport):
    image = QtGui.QImage(viewport.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.GlobalColor.black)
    painter = MeasurementPainter(image)
    viewport.DrawScene(painter, viewport.DrawingRect(), viewport.WorldToViewport(QtCore.QPointF()),
                       viewport.basePixelsPerMillimeter * viewport.zoom)
    painter.end()
    return painter.labels


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    v = DrawingViewport()
    v.resize(1800, 1200)
    v.zoom = 2
    v.wallMeasurementMode = "All"  # Exercise full selected dimensions, including interior/contained walls.
    point = QtCore.QPointF
    host = Wall(point(-1000, 0), point(1000, 0), 240)
    fixtures = [(Wall(point(-500, 0), point(500, 0)), 2),
                (Stair(point(-500, 0), point(500, 0), 600), 4),
                (Counter(point(-500, 0), point(500, 0)), 4),
                (Railing(point(-500, 0), point(500, 0)), 2),
                (Pillar(point(0, -150), point(0, 150), 300), 4),
                (Furnishing(v.furnishingDefinitions["desk"], point()), 4),
                (Label(point(), text = "Selected label"), 4),
                (Window(host, .25, .75), 4),
                (Arrow(point(-500, 0), point(500, 0)), 1)]
    for obj, expected in fixtures:
        v.DeselectAll()
        v.walls = [host, obj] if isinstance(obj, Window) else [obj] if isinstance(obj, Wall) else []
        v.windows = [obj] if isinstance(obj, Window) else []
        if isinstance(obj, Window):
            v.walls = [host]
        v.furnishings = [obj] if isinstance(obj, Furnishing) and not isinstance(obj, Label) else []
        v.labels = [obj] if isinstance(obj, Label) else []
        v.showMeasurements = False
        v.measurementVisibility = dict.fromkeys(v.measurementVisibility, False)
        assert not RenderLabels(v), type(obj)
        v.SetSelection([(obj, None)])
        assert len(RenderLabels(v)) == expected, (type(obj), RenderLabels(v))
        # Category switches cannot hide the selection even with the master on.
        v.showMeasurements = True
        assert len(RenderLabels(v)) == expected
        v.DeselectAll()
        assert not RenderLabels(v)
    # Selecting both control vertices must not duplicate an object's labels.
    arrow = fixtures[-1][0]
    v.labels, v.furnishings, v.windows, v.walls = [], [], [], [arrow]
    v.SetSelection([(arrow, 0), (arrow, 1)])
    assert len(RenderLabels(v)) == 1
    # Every selected object in a mixed selection contributes measurements.
    stair = Stair(point(-500, -600), point(500, -600), 400)
    counter = Counter(point(-500, 600), point(500, 600), 400)
    v.walls = [stair, counter]
    v.showMeasurements = False
    v.SetSelection([(stair, None), (counter, None)])
    assert len(RenderLabels(v)) == 8
    v.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots/selected-measurements.png"))
    v.isPanning = True
    assert len(RenderLabels(v)) == 8
    v.isPanning = False
    # Actual groups use only their combined bounds, including mixed object classes.
    v.groupModeEnabled = True
    v.objectGroups = [(stair, counter)]
    v.unitsMode = "Meters"
    for show in (False, True):
        v.showMeasurements = show
        v.measurementVisibility = dict.fromkeys(v.measurementVisibility, show)
        v.SetSelection([(stair, None)])
        labels = RenderLabels(v)
        assert sorted(labels) == ["1", "1", "1.6", "1.6"], labels
        # Reusing cached dimensions does not restore member annotations.
        assert RenderLabels(v) == labels
    v.groupModeEnabled = False
    v.SetSelection([(stair, None)])
    v.showMeasurements = False
    assert len(RenderLabels(v)) == 4, "An individually selected group member lost its own dimensions"
    v.groupModeEnabled = True
    v.SetSelection([(stair, None)])
    counter.secondVertex = point(1000, 600)
    labels = RenderLabels(v)
    assert sorted(labels) == ["1.5", "1.5", "1.6", "1.6"], labels
    v.objectGroups = []
    v.SetSelection([(stair, None), (counter, None)])
    assert len(RenderLabels(v)) == 8, "Ungrouped multi-selection was treated as a group"
    v.unitsMode = "Adaptive Metric"
    v.showMeasurements = False
    v.measurementVisibility = dict.fromkeys(v.measurementVisibility, False)
    # Selected short objects retain their labels below the normal zoom cutoff.
    tiny = Wall(point(), point(10, 0))
    v.walls = [tiny]
    v.SetSelection([(tiny, None)])
    assert len(RenderLabels(v)) == 2
    v.hiddenObjects, v.hiddenObjectIds = [tiny], {id(tiny)}
    assert not RenderLabels(v)
    v.hiddenObjects, v.hiddenObjectIds = [], set()
    # Collapsed footprints can remain selected during edits and view changes.
    # They have no measurable sides, but must not abort the entire paint pass.
    originalUnits, originalPrecision = v.unitsMode, v.measurementPrecision
    for objectType in (Wall, Railing, Counter, Stair, Pillar, Column):
        collapsed = objectType(point(), point(), 240)
        v.walls = [collapsed]
        v.SetSelection([(collapsed, None)])
        for mode in ("Meters", "Centimeters", "Inches", "Feet and Inches"):
            v.unitsMode = mode
            for precision in ("High", "Medium", "Low"):
                v.measurementPrecision = precision
                assert not RenderLabels(v), (objectType, mode, precision)
        v.showMeasurements = True
        v.measurementVisibility = dict.fromkeys(v.measurementVisibility, True)
        v.DeselectAll()
        assert not RenderLabels(v), objectType
        v.showMeasurements = False
        v.measurementVisibility = dict.fromkeys(v.measurementVisibility, False)
    v.unitsMode, v.measurementPrecision = originalUnits, originalPrecision
    # Door and structural splitting must disappear and return without changing
    # the settings, including already-cached measurement components.
    wall = Wall(point(), point(4000, 0))
    other = Wall(point(0, 3000), point(1000, 3000))
    cutter = Counter(point(1500, 420), point(2500, 420), 600)
    opening = Door(wall, .1, .3)
    v.walls, v.windows = [wall, other, cutter], [opening]
    v.measurementSettings["doors"] = 0
    v.measurementSettings["counters"] = 0
    v.DeselectAll()
    path = v.ConnectedWallPath([wall, other])
    baseline = v.WallDimensions([wall, other], path, cachedBoundary = True)
    assert len(baseline) > 4
    v.SetSelection([(wall, None)])
    selected = v.WallDimensions([wall, other], path, cachedBoundary = True)
    assert sorted(round(QtCore.QLineF(first, second).length()) for first, second, owners in selected) == [1000, 1000, 4000, 4000]
    v.DeselectAll()
    assert v.WallDimensions([wall, other], path, cachedBoundary = True) == baseline
    # Wall/furniture obstruction must not remove selected stair/counter sides.
    for cls in (Stair, Counter):
        obj = cls(point(), point(2000, 0), 600)
        blocker = Wall(point(500, 420), point(1500, 420))
        v.walls, v.windows = [obj, blocker], []
        v.DeselectAll()
        baseline = v.StairDimensions([obj]) if cls is Stair else v.ConnectedCounterPath([obj])[1]
        assert len(baseline) == 5
        v.SetSelection([(obj, None)])
        selected = v.StairDimensions([obj]) if cls is Stair else v.ConnectedCounterPath([obj])[1]
        assert len(selected) == 4
        v.DeselectAll()
        assert (v.StairDimensions([obj]) if cls is Stair else v.ConnectedCounterPath([obj])[1]) == baseline
    # Fully merged walls still have dimensions while selected.
    inner = Wall(point(-200, 0), point(200, 0), 100)
    pillar = Pillar(point(0, -500), point(0, 500), 1000)
    v.walls = [inner, pillar]
    v.SetSelection([(inner, None)])
    assert len(RenderLabels(v)) == 2
    v.SetSelection([(pillar, None)])
    assert len(RenderLabels(v)) == 4
    guide = MeasurementGuide(point(-500, 0), point(500, 0))
    v.walls = [guide]
    v.SetSelection([(guide, None)])
    assert len(RenderLabels(v)) == 1


if __name__ == "__main__":
    Main()
