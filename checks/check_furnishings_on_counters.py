"""Furnishings overlap counters, paint above them and remain selectable."""
import os
import sys
import copy
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Counter, Stair, Wall
from furnishings import Furnishing
from check_history import Drag
from planner_app.export_plan import RenderPlan
from planner_app.project_codec import DecodeProject
from planner_app.graphics.svg_preview import SvgPreviewRenderer


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    viewport = main.viewport
    viewport.ResetView()
    viewport.snapEnabled = False
    viewport.showMeasurements = False
    viewport.showGrid = False
    point = QtCore.QPointF
    furnishing = Furnishing(viewport.furnishingDefinitions["desk"], point())
    furnishing.width = 1000
    furnishing.firstVertex, furnishing.secondVertex = point(0, -500), point(0, 500)
    viewport.furnishings = [furnishing]
    viewport.walls, viewport.windows, viewport.labels = [], [], []
    viewport.SetSelection([])
    baseline = viewport.grab().toImage()
    counter = Counter(point(-1000, 0), point(1000, 0))
    viewport.walls = [counter]
    assert viewport.FurnishingFits(furnishing) and viewport.CounterFits(counter) and viewport.OpeningsValid()
    image = viewport.grab().toImage()
    # The desk and its opaque interior cover both counter fill and outline.
    for position in (point(), point(200, 300)):
        pixel = viewport.WorldToViewport(position).toPoint()
        assert image.pixelColor(pixel) == baseline.pixelColor(pixel), (position, image.pixelColor(pixel).name())
        assert viewport.HitTest(point(pixel))[0] is furnishing
    assert viewport.HitTest(viewport.WorldToViewport(point(800, 0)))[0] is counter
    # Explicit layer commands override the counter priority, even for one furnishing.
    viewport.furnishings = []
    counterImage = viewport.grab().toImage()
    viewport.furnishings = [furnishing]
    viewport.MoveFurnishingLayer(furnishing, False)
    assert furnishing.behindCounters
    center = viewport.WorldToViewport(point()).toPoint()
    assert viewport.grab().toImage().pixelColor(center) == counterImage.pixelColor(center)
    viewport.Undo()
    assert not furnishing.behindCounters
    assert viewport.grab().toImage().pixelColor(center) == image.pixelColor(center)
    viewport.Redo()
    assert furnishing.behindCounters
    assert furnishing.Clone().behindCounters
    saved = main.BuildProjectData()
    main.ApplyProject(DecodeProject(saved, viewport.furnishingDefinitions), None)
    furnishing = viewport.furnishings[0]
    counter = viewport.walls[0]
    assert furnishing.behindCounters
    viewport.Undo()
    assert not furnishing.behindCounters
    viewport.Redo()
    assert furnishing.behindCounters
    viewport.SetSelection([(furnishing, None)])
    assert viewport.CopySelection()
    zoom = viewport.zoom
    viewport.zoom = .1
    assert viewport.PasteSelection(viewport.WorldToViewport(point(3000, 0)))
    assert viewport.furnishings[-1].behindCounters
    app.clipboard().clear()
    viewport.Undo()
    viewport.zoom = zoom
    viewport.SetSelection([])
    saved = main.BuildProjectData(includeHistory = False)
    counterOnly = copy.deepcopy(saved)
    counterOnly["scene"]["objects"] = counterOnly["scene"]["objects"][:1]
    counterOnly["scene"]["groups"] = []
    counterOnly["scene"]["hidden"] = []
    for solid in (True, False):
        for outputFormat in ("png", "svg"):
            images = []
            for project in (saved, counterOnly):
                result = RenderPlan("counter-layer.plan", 250, bounds = (-1500, -1000, 3000, 2000),
                                    projectData = project, outputFormat = outputFormat, solidObjects = solid,
                                    applyTheme = False)
                if outputFormat == "svg":
                    renderer = SvgPreviewRenderer(result)
                    assert renderer.isValid()
                    result = QtGui.QImage(750, 500, QtGui.QImage.Format.Format_ARGB32)
                    result.fill(QtCore.Qt.GlobalColor.transparent)
                    with QtGui.QPainter(result) as painter:
                        renderer.render(painter)
                images.append(result)
            assert images[0].pixelColor(375, 250) == images[1].pixelColor(375, 250), (solid, outputFormat)
    viewport.MoveFurnishingLayer(furnishing, True)
    assert not furnishing.behindCounters
    assert viewport.grab().toImage().pixelColor(center) == image.pixelColor(center)
    # An unselected counter endpoint underneath a furnishing is also behind it.
    short = Counter(point(-200, 0), point(200, 0))
    viewport.walls = [short]
    assert viewport.HitTest(viewport.WorldToViewport(short.firstVertex))[0] is furnishing
    viewport.walls = [counter]
    for blocker in (Wall(point(-1000, 0), point(1000, 0)), Stair(point(-1000, 0), point(1000, 0))):
        viewport.walls = [blocker]
        assert not viewport.FurnishingFits(furnishing)
        assert not viewport.CounterFits(counter)
    viewport.walls = [counter]
    furnishing.firstVertex += point(0, 1100)
    furnishing.secondVertex += point(0, 1100)
    original = point(furnishing.firstVertex)
    Drag(viewport, viewport.WorldToViewport(point(0, 1100)).toPoint(), viewport.WorldToViewport(point()).toPoint())
    assert QtCore.QLineF((furnishing.firstVertex + furnishing.secondVertex) / 2, point()).length() < .01
    assert viewport.FurnishingFits(furnishing)
    viewport.Undo()
    assert furnishing.firstVertex == original
    viewport.Redo()
    first = point(counter.firstVertex)
    Drag(viewport, viewport.WorldToViewport(point(800, 0)).toPoint(), viewport.WorldToViewport(point(800, 100)).toPoint())
    assert counter.firstVertex == first + point(0, 100)
    assert viewport.CounterFits(counter)
    viewport.Undo()
    assert counter.firstVertex == first
    main.close()
    app.processEvents()


if __name__ == "__main__":
    Main()
