"""Ordered connected discovery and exact opening-jamb pixels versus frozen code."""
import math
import os
from pathlib import Path
import random
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from planner_app import models
from planner_app.geometry.attachments import ConnectedAttachments
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.text import PathTextPainter
from planner_app.graphics.furnishings import CompoundFurnishingSvg
from planner_app.viewport.geometry import CollisionPass
from planner_app.viewport.widget import DrawingViewport
from planner_app.viewport import scene
from planner_app.viewport import rendering
from fixtures.qt_connections_openings_reference_20261030 import (
    ReferenceViewport, ConnectedAttachments as ReferenceConnectedAttachments)


def Sync(view, reference):
    for name in ("walls", "windows", "furnishings", "labels", "hiddenObjectIds", "visibility", "collisionSettings",
                 "zoom", "panOffset", "lineWidths", "solidObjects", "floors", "solidRooms", "showMeasurements",
                 "connectedObjectsEnabled", "selectedWall", "selectedVertex", "dragStart", "isDragging"):
        setattr(reference, name, getattr(view, name))
    reference.SetSelection(view.SelectionEntries(), notify = False)
    reference.selectedWall, reference.selectedVertex = view.selectedWall, view.selectedVertex


@CollisionPass
def SceneImage(view, svg = False, ratio = 1):
    image = QtGui.QImage(round(view.width() * ratio), round(view.height() * ratio), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(ratio)
    image.fill(QtCore.Qt.GlobalColor.white)
    data = QtCore.QBuffer()
    generator = None
    if svg:
        data.open(QtCore.QIODevice.OpenModeFlag.ReadWrite)
        generator = QtSvg.QSvgGenerator()
        generator.setOutputDevice(data)
        generator.setSize(view.size())
        generator.setViewBox(QtCore.QRectF(view.rect()))
    with PathTextPainter(generator if svg else image) as painter:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setClipRect(view.DrawingRect())
        view.DrawScene(painter, view.DrawingRect(), view.WorldToViewport(QtCore.QPointF()), view.basePixelsPerMillimeter * view.zoom)
    if svg:
        renderer = QtSvg.QSvgRenderer(data.data())
        with QtGui.QPainter(image) as painter:
            renderer.render(painter, QtCore.QRectF(view.rect()))
    return image


def Main():
    app = QtWidgets.QApplication([])
    app.setStyle("Fusion")
    LoadApplicationFonts(app)
    point = QtCore.QPointF
    rng = random.Random(20261030)
    for count in (2, 31, 32, 65, 128, 512):
        for offset in (0, 1e8, 1e11):
            records = [(index, (offset + index * 10, offset), (offset + (index + 1) * 10, offset)) for index in range(count)]
            rng.shuffle(records)
            for root in (records[0], records[count // 2]):
                assert ConnectedAttachments(root, records) == ReferenceConnectedAttachments(root, records)
            records[0] = (records[0][0], (offset, offset + .010001), (offset, offset + 10))
            assert ConnectedAttachments(records[-1], records) == ReferenceConnectedAttachments(records[-1], records)
    # Nonfinite endpoint data keeps the original full-sweep behavior.
    records = [(index, (index, 0), (index + 1, 0)) for index in range(64)]
    records[17] = (17, (float("nan"), 0), (18, 0))
    assert ConnectedAttachments(records[0], records) == ReferenceConnectedAttachments(records[0], records)
    for offset in (0, 1e8, 1e11):
        for gap in (.009999, .01, .010001):
            records = [(0, (offset, offset), (offset + 10, offset)),
                       (1, (offset + 10, offset + gap), (offset + 20, offset + gap))]
            records += [(index, (offset + 100 * index, offset), (offset + 100 * index + 10, offset)) for index in range(2, 65)]
            assert ConnectedAttachments(records[0], records) == ReferenceConnectedAttachments(records[0], records)
    records = [(index, (0, 0), (1, 0)) for index in range(256)]
    assert ConnectedAttachments(records[0], records) == ReferenceConnectedAttachments(records[0], records)

    view = DrawingViewport()
    reference = ReferenceViewport(furnishingDefinitions = view.furnishingDefinitions)
    for viewport in (view, reference):
        viewport.resize(1000, 750)
        viewport.showMeasurements = viewport.showTips = False
        viewport.connectedObjectsEnabled = True
    definition = dict(view.furnishingDefinitions["desk"], width = 200, length = 1000)
    for cls in (models.Wall, models.Pillar, models.Column, models.Elevator, models.Counter, models.Stair, models.Railing,
                models.Furnishing, models.Arrow, models.MeasurementGuide):
        objects = []
        for index in range(65):
            obj = cls(definition) if cls is models.Furnishing else cls(point(), point(1000, 0), 200)
            obj.firstVertex, obj.secondVertex = point(index * 1000, 0), point((index + 1) * 1000, 0)
            objects.append(obj)
        rng.shuffle(objects)
        view.walls = [] if cls is models.Furnishing else objects
        view.furnishings = objects if cls is models.Furnishing else []
        view.windows, view.labels = [], []
        for selectedVertex in (None, 0, 1):
            view.selectedVertex = selectedVertex
            Sync(view, reference)
            for root in (objects[0], objects[32]):
                for captureAll in (False, True):
                    actual = view.AttachedVertices(root, captureAll = captureAll)
                    expected = reference.AttachedVertices(root, captureAll = captureAll)
                    assert [(id(obj), index, vertex.x(), vertex.y()) for obj, index, vertex in actual] == [
                        (id(obj), index, vertex.x(), vertex.y()) for obj, index, vertex in expected], (cls.__name__, selectedVertex, captureAll)
        if cls in (models.MeasurementGuide, models.Arrow, models.Elevator):
            view.selectedVertex = None
            with patch.object(scene.Paths, "Union", side_effect = AssertionError("Endpoint-only discovery constructed shape paths")):
                view.AttachedVertices(objects[0], captureAll = True)

    leaf = dict(view.furnishingDefinitions["null"], graphicData =
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="white"/></svg>')
    components = [dict(definition = leaf, x = x, y = 0, width = 400, length = 1600, angle = 0, zIndex = 0) for x in (-800, 800)]
    components.append(dict(definition = leaf, x = 0, y = 600, width = 1200, length = 400, angle = 0, zIndex = 0))
    svg, width, length, center = CompoundFurnishingSvg(components)
    compoundDefinition = dict(leaf, key = "connected-compound", components = components, compoundCenter = center,
                              width = width, length = length, graphicData = svg)
    compounds = [models.Furnishing(compoundDefinition, point(index * 2000, 0)) for index in range(40)]
    gapObject = models.Furnishing(dict(leaf, width = 100, length = 100), point(0, -200))
    view.walls, view.furnishings = [], compounds + [gapObject]
    view.selectedVertex = None
    Sync(view, reference)
    for captureAll in (False, True):
        actual = view.AttachedVertices(compounds[0], captureAll = captureAll)
        expected = reference.AttachedVertices(compounds[0], captureAll = captureAll)
        assert [(id(obj), index) for obj, index, vertex in actual] == [(id(obj), index) for obj, index, vertex in expected]
        if not captureAll:
            assert all(obj is not gapObject for obj, index, vertex in actual), "Compound holes became shape contacts"

    view.walls = [models.Wall(point(index * 1000, 0), point((index + 1) * 1000, 0), 200) for index in range(512)]
    view.furnishings = []
    view.selectedVertex = None
    with patch.object(scene.Paths, "Intersects", wraps = scene.Paths.Intersects) as contact:
        assert len(view.AttachedVertices(view.walls[0], captureAll = True)) == 1022
        assert contact.call_count <= 1024, ("Quadratic contact sweep", contact.call_count)

    openingTypes = (models.Door, models.Window, models.SilledWindow, models.CasementWindow, models.PocketDoor,
                    models.BarnDoor, models.DoubleDoor, models.BifoldDoor, models.SwingingDoor, models.Fireplace,
                    models.SlidingDoor, models.OpenDoorway)
    for matrix in range(24):
        host = models.Wall(point(-2500, 0), point(2500, 0), 240)
        opening = openingTypes[matrix % len(openingTypes)](host, .35, .65)
        if isinstance(opening, models.Window) and not isinstance(opening, models.Fireplace):
            opening.windowWell = matrix % 2 == 0
            opening.wellDepth = 800
        offset = (0, .099999, .1, .100001)[matrix % 4]
        firstJamb, secondJamb = opening.firstVertex, opening.secondVertex
        branch = models.Wall(firstJamb + point(offset, 0), firstJamb + point(offset, 1500), 120)
        pillar = models.Pillar(secondJamb - point(0, 100), secondJamb + point(0, 100), 300)
        column = models.Column(firstJamb - point(0, 150), firstJamb + point(0, 150), 400)
        far = [models.Wall(point(index * 3000, 15000), point(index * 3000 + 1500, 15000), 200) for index in range(36)]
        view.walls = [host, branch, pillar, column] + far
        extraOpenings = [models.Door(wall, .2, .7) for wall in far[:3]] if matrix % 6 else []
        view.windows, view.furnishings, view.labels = extraOpenings + [opening], [], []
        view.hiddenObjectIds = {id(branch)} if matrix % 5 == 0 else set()
        view.zoom = (.2, .5, 1, 1.7)[matrix % 4]
        view.panOffset = point(matrix * .37, -matrix * .71)
        view.solidObjects = matrix % 3 != 0
        view.floors, view.solidRooms = matrix % 2 == 0, matrix % 4 == 0
        view.lineWidths = {**view.lineWidths, "walls": (1, 2.5, 5)[matrix % 3]}
        view.selectedWall, view.selectedVertex = host, None
        view.dragStart, view.isDragging = point(400, 300), True
        Sync(view, reference)
        for svg in (False, True):
            assert SceneImage(view, svg, (1, 1.25, 2)[matrix % 3]) == SceneImage(
                reference, svg, (1, 1.25, 2)[matrix % 3]), ("jamb pixels", matrix, svg)
        if not extraOpenings:
            with patch.object(rendering, "BoundsIndex", side_effect = AssertionError("A single opening built a jamb index")):
                SceneImage(view)
        # The actual editor path includes retained/background/selection layers.
        if matrix % 4 == 0:
            actual = QtGui.QImage(view.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
            expected = QtGui.QImage(reference.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
            view.render(actual)
            reference.render(expected)
            assert actual == expected, ("editor pixels", matrix)
    for viewport in (view, reference):
        viewport.close()
    print("PASS: ordered endpoint/path connectivity, bounded contact calls and exact jamb/editor pixels across 24 raster/SVG scenes.")


if __name__ == "__main__":
    Main()
