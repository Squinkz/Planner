"""Frozen-reference validity, exact railing pixels and local drag invalidation."""
import math
import os
from pathlib import Path
import random
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from planner_app.models import (Wall, Pillar, Column, Counter, Stair, Railing, Elevator,
    Window, Door, PocketDoor, Fireplace, Furnishing, Label, MeasurementGuide)
from planner_app.viewport.widget import DrawingViewport
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.path_operations import Paths
from fixtures.qt_drag_railing_reference_20261030 import ReferenceViewport, ReferenceRailing


def CompareValidation(view, reference):
    # Share scene identities so opening hosts, hidden IDs and result sets are
    # directly comparable. Each viewport retains independent validation caches.
    for name in ("walls", "windows", "furnishings", "labels", "hiddenObjectIds", "visibility", "collisionSettings"):
        setattr(reference, name, getattr(view, name))
    actual = view.InvalidArchitecturalObjects()
    expected = reference.InvalidArchitecturalObjects()
    assert actual == expected, (actual - expected, expected - actual)
    assert view.collisionPassCache is None
    return actual


def RailingImage(view, method, members, ratio, svg = False):
    view.railingSymbolKey = None
    path = method(view, members, includeMeasurements = False)[0]
    origin = view.WorldToViewport(QtCore.QPointF())
    posts = QtGui.QTransform().translate(origin.x(), origin.y()).scale(view.zoom, view.zoom).map(view.railingPostOutlinePath)
    image = QtGui.QImage(round(view.width() * ratio), round(view.height() * ratio), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(ratio)
    image.fill(QtCore.Qt.GlobalColor.white)
    buffer = QtCore.QBuffer()
    generator = None
    if svg:
        buffer.open(QtCore.QIODevice.OpenModeFlag.ReadWrite)
        generator = QtSvg.QSvgGenerator()
        generator.setOutputDevice(buffer)
        generator.setSize(view.size())
        generator.setViewBox(QtCore.QRectF(view.rect()))
    with QtGui.QPainter(generator if svg else image) as painter:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.black, 1.3))
        painter.setBrush(QtCore.Qt.GlobalColor.white)
        painter.drawPath(path)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPath(posts)
    if svg:
        renderer = QtSvg.QSvgRenderer(buffer.data())
        with QtGui.QPainter(image) as painter:
            renderer.render(painter, QtCore.QRectF(view.rect()))
    return image


def Main():
    app = QtWidgets.QApplication([])
    app.setStyle("Fusion")
    LoadApplicationFonts(app)
    view, reference = DrawingViewport(), ReferenceViewport()
    for viewport in (view, reference):
        viewport.resize(1000, 800)
        viewport.showTips = False
        viewport.showMeasurements = False
    point = QtCore.QPointF
    view.walls = [Wall(point(index * 2000, 0), point(index * 2000 + 1000, 0)) for index in range(128)]
    CompareValidation(view, reference)
    with patch.object(view, "ArchitecturalPlacementFits", wraps = view.ArchitecturalPlacementFits) as validation:
        for frame in range(5):
            view.walls[0].secondVertex.setX(1001 + frame)
            CompareValidation(view, reference)
        assert validation.call_count == 5, "A local clear edit revalidated stationary walls"
        for frame in range(5):
            view.InvalidArchitecturalObjects()
        assert validation.call_count == 5, "Unchanged drag state repeated validation"

    # The broad phase must retain the same local behavior in a mixed scene,
    # without calculating annotation footprints that cannot collide.
    view.walls.append(Counter(point(0, 10000), point(1000, 10000), 400))
    guide = MeasurementGuide(point(-1000, 0), point(1000, 0))
    view.walls.append(guide)
    footprint = view.ObjectFootprint
    def Footprint(obj):
        assert obj is not guide, "Validation prepared a non-colliding annotation"
        return footprint(obj)
    with patch.object(view, "ObjectFootprint", side_effect = Footprint):
        CompareValidation(view, reference)
        with patch.object(view, "ArchitecturalPlacementFits", wraps = view.ArchitecturalPlacementFits) as validation:
            view.walls[0].secondVertex.setX(1010)
            CompareValidation(view, reference)
            assert validation.call_count == 1, "Distant blockers invalidated clear stationary objects"

    host = Wall(point(-2500, 1600), point(2500, 1600), 240)
    branch = Wall(point(2500, 1600), point(2500, -1200), 500, firstMiter = .8)
    counter = Counter(point(-1800, -500), point(1800, -500), 500)
    stair = Stair(point(-1500, 500), point(-1500, -1500), 750)
    railing = Railing(point(-1000, -1900), point(1800, -1900))
    pillar = Pillar(point(2000, -700), point(2000, -1200), 600)
    column = Column(point(0, 1000), point(0, 600), 500)
    elevator = Elevator(point(-2200, -700), point(-2200, -1700), 1000)
    door, window, pocket = Door(host, .05, .25), Window(host, .35, .5), PocketDoor(host, .65, .95)
    fireplace = Fireplace(host, .51, .63)
    desk = Furnishing(view.furnishingDefinitions["desk"], point(0, 0))
    view.walls = [host, branch, counter, stair, railing, pillar, column, elevator,
                  MeasurementGuide(point(-1000, 0), point(1000, 0))]
    view.windows = [door, window, pocket, fireplace]
    view.furnishings = [desk]
    view.labels = [Label(point(0, -500), "A label")]
    CompareValidation(view, reference)
    mutations = [(desk, "firstVertex", point(-5000, 0)), (desk, "secondVertex", point(-5000, 1000)),
                 (counter, "width", 1000), (branch, "firstMiter", 2.5), (branch, "width", 900),
                 (host, "secondVertex", point(3000, 1600)), (host, "firstVertex", point(-3000, 1100)),
                 (door, "length", 8000), (door, "length", 700), (pocket, "hingeAtSecond", True),
                 (fireplace, "depth", 1200), (column, "width", 900), (stair, "secondVertex", point(-1500, 500))]
    for obj, field, value in mutations:
        setattr(obj, field, value)
        CompareValidation(view, reference)
    # Hidden objects still obstruct placements; hidden/disabled categories only
    # suppress the invalid object's own editor highlight.
    view.hiddenObjectIds = {id(counter), id(desk)}
    CompareValidation(view, reference)
    view.visibility["Walls"] = False
    CompareValidation(view, reference)
    view.visibility["Walls"] = True
    for category in view.collisionSettings:
        view.collisionSettings[category] = False
        CompareValidation(view, reference)
        view.collisionSettings[category] = True
    view.walls.append(Wall(point(3000, 1600), point(6000, 1600), 240))
    CompareValidation(view, reference)
    view.walls.pop()
    CompareValidation(view, reference)
    with patch.object(view, "ArchitecturalPlacementFits", side_effect = RuntimeError("validation probe")):
        host.width += 1
        try:
            view.InvalidArchitecturalObjects()
        except RuntimeError:
            pass
        else:
            raise AssertionError("Expected the injected validation failure")
    assert view.collisionPassCache is None
    CompareValidation(view, reference)

    rng = random.Random(20261030)
    for matrix in range(24):
        view.walls = []
        view.windows = []
        view.furnishings = []
        view.labels = []
        view.hiddenObjectIds = set()
        for index in range(14):
            first = point(rng.uniform(-3000, 3000), rng.uniform(-2000, 2000))
            angle = rng.uniform(-math.pi, math.pi)
            second = first + point(math.cos(angle), math.sin(angle)) * rng.uniform(200, 2000)
            cls = rng.choice((Wall, Wall, Pillar, Column, Counter, Stair, Railing, Elevator))
            obj = cls(first, second, rng.uniform(80, 700))
            view.walls.append(obj)
            if type(obj) is Wall and index % 2 == 0:
                view.windows.append(rng.choice((Window, Door, PocketDoor))(obj, .2, .7))
        for frame in range(4):
            obj = rng.choice(view.walls)
            obj.firstVertex += point(rng.uniform(-80, 80), rng.uniform(-80, 80))
            CompareValidation(view, reference)

    # Compare actual editor frames, including moving validity colors, retained
    # state, release, zoom and transparent-object replay.
    view.walls = [host, branch, counter, railing]
    view.windows = [door, pocket]
    view.furnishings = [desk]
    CompareValidation(view, reference)
    for viewport in (view, reference):
        viewport.selectedWall = host
        viewport.dragStart = point(400, 400)
        viewport.isDragging = True
        viewport.selectedVertex = None
    for frame in range(4):
        host.width += 20
        for viewport in (view, reference):
            viewport.zoom = (.5, 1, 1.25, 1.7)[frame]
            viewport.solidObjects = frame != 3
        images = []
        for viewport in (view, reference):
            image = QtGui.QImage(viewport.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
            viewport.render(image)
            images.append(image)
        assert images[0] == images[1], ("editor frame", frame)

    # Random oblique and cardinal runs, dense overlapping posts, widest shared
    # posts, first-owner ties and tolerance boundaries, at fractional zoom/DPR.
    for matrix in range(100):
        members = []
        for index in range(1 if matrix < 35 else rng.randrange(2, 6)):
            first = point(rng.uniform(-1200, 1200), rng.uniform(-1200, 1200)) if matrix % 3 else point()
            angle = rng.uniform(-math.pi, math.pi) if matrix % 2 else (index % 4) * math.pi / 2
            run = point(math.cos(angle), math.sin(angle)) * rng.uniform(10, 3000)
            if matrix % 2 == 0:
                run = point(run.x(), 0) if index % 2 == 0 else point(0, run.y())
            members.append(Railing(first, first + run, rng.uniform(30, 450), autosize = False, manualPostCount = rng.randrange(2, 20)))
        if matrix % 10 == 0:
            members += [Railing(point(-500, 0), point(.0099, 0), 80, autosize = False),
                        Railing(point(.0101, 0), point(500, 0), 240, autosize = False)]
        view.walls = members
        view.zoom = (.37, .5, 1, 1.25, 1.7)[matrix % 5]
        ratio = (1, 1.25, 2)[matrix % 3]
        actual = RailingImage(view, DrawingViewport.ConnectedRailingPath, members, ratio, svg = matrix % 7 == 0)
        expected = RailingImage(view, ReferenceRailing.ConnectedRailingPath, members, ratio, svg = matrix % 7 == 0)
        assert actual == expected, ("railing pixels", matrix, ratio)
    for viewport in (view, reference):
        viewport.close()
    print("PASS: local drag invalidation, frozen placement parity, exact editor frames and 100 railing raster/SVG matrices.")


if __name__ == "__main__":
    Main()
