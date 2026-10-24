"""Compound gaps, nested affine footprints and wall-drawing validity feedback."""
import math
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from planner import MainWindow
from planner_app.models import Furnishing, Wall, Counter
from planner_app.graphics.furnishings import CompoundFurnishingSvg
from planner_app.furnishing_parts import FurnishingCollisionFootprints
from planner_app.viewport.geometry import CollisionPass


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v, point = main.viewport, QtCore.QPointF
    v.walls, v.windows, v.furnishings, v.labels = [], [], [], []
    v.collisionSettings = dict.fromkeys(v.collisionSettings, True)
    leaf = dict(v.furnishingDefinitions["null"], graphicData =
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="white"/></svg>')
    components = [dict(definition = leaf, x = x, y = 0, width = 400, length = 1600, angle = 0, zIndex = 0)
                  for x in (-800, 800)]
    components.append(dict(definition = leaf, x = 0, y = 600, width = 1200, length = 400, angle = 0, zIndex = 0))
    svg, width, length, center = CompoundFurnishingSvg(components)
    definition = dict(leaf, key = "collision-test", components = components, compoundCenter = center,
                      width = width, length = length, graphicData = svg)
    compound = Furnishing(definition)
    gap = Wall(point(0, -450), point(0, 50), 100)
    occupied = Wall(point(-800, -450), point(-800, 50), 100)
    v.furnishings = [compound]
    v.walls = [gap]
    assert v.WallFits(gap) and v.FurnishingFits(compound)
    for query in (v.ObjectsOverlap, v.JoinedObjectsOverlap):
        assert not query(compound, gap) and not query(gap, compound)
        assert query(compound, occupied) and query(occupied, compound)
    v.walls = [occupied]
    assert not v.WallFits(occupied) and not v.FurnishingFits(compound)
    counter = Counter(point(0, -450), point(0, 50), 100)
    assert not v.JoinedObjectsOverlap(compound, counter)
    probe = Furnishing(dict(leaf, width = 100, length = 100), point(0, -200))
    assert not v.JoinedObjectsOverlap(compound, probe)
    probe.firstVertex += point(-800, 0)
    probe.secondVertex += point(-800, 0)
    assert v.JoinedObjectsOverlap(compound, probe)
    # Retained pair results must also change when a mirror moves a gap/child.
    probe = Wall(point(0, 550), point(0, 650), 100)
    v.walls = [probe]
    validate = CollisionPass(lambda viewport: viewport.JoinedObjectsOverlap(compound, probe))
    assert validate(v)
    compound.flipVertical = True
    assert not validate(v)
    compound.flipVertical = False
    assert validate(v)
    # Connected Objects uses child contact too, including recursive edge contact.
    gapObject = Furnishing(dict(leaf, width = 100, length = 100), point(0, -200))
    touching = Furnishing(dict(leaf, width = 200, length = 200), point(-1100, -200))
    chained = Furnishing(dict(leaf, width = 200, length = 200), point(-1300, -200))
    v.furnishings = [compound, gapObject, touching, chained]
    v.connectedEnabled = v.connectedObjectsEnabled = True
    v.selectedVertex = None
    for seed, expected in ((compound, {id(touching), id(chained)}), (gapObject, set()),
                           (touching, {id(compound), id(chained)})):
        assert {id(obj) for obj, index, vertex in v.AttachedVertices(seed)} == expected
    v.selectedWall = compound
    v.dragVertices = (point(compound.firstVertex), point(compound.secondVertex))
    v.dragAttachments = v.AttachedVertices(compound, captureAll = True)
    assert {id(obj) for obj, index, vertex in v.ActiveAttachments()} == {id(touching), id(chained)}
    v.dragVertices, v.selectedWall = None, None
    # Compare exact nested child geometry against the actual SVG renderer.
    nestedComponents = [dict(definition = definition, x = 700, y = -300, width = width * 1.3,
        length = length * .6, angle = 31, zIndex = 0, flipHorizontal = True, flipVertical = False)]
    svg, width, length, center = CompoundFurnishingSvg(nestedComponents)
    nested = Furnishing(dict(leaf, key = "nested-collision", components = nestedComponents,
        compoundCenter = center, width = width, length = length, graphicData = svg), point(700, 400))
    nested.width *= 1.7
    nested.firstVertex, nested.secondVertex = point(700, -200), point(700, 1000)
    nested.angle = 37
    nested.flipVertical = True
    v.walls, v.furnishings = [], [nested]
    image = QtGui.QImage(240, 240, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(image)
    renderer = QtSvg.QSvgRenderer(svg)
    renderer.render(painter, QtCore.QRectF(0, 0, 240, 240))
    painter.end()
    cosine, sine = math.cos(math.radians(37)), math.sin(math.radians(37))
    for x in range(10, 231, 20):
        for y in range(10, 231, 20):
            # Ignore edge pixels, where antialiasing/tolerance has a different contract.
            alphas = {image.pixelColor(x + dx, y + dy).alpha() for dx in (-2, 0, 2) for dy in (-2, 0, 2)}
            if alphas not in ({0}, {255}):
                continue
            localX, localY = (x / 240 - .5) * nested.width, (y / 240 - .5) * nested.length
            world = point(700 + localX * cosine - localY * sine, 400 + localX * sine + localY * cosine)
            probe = Furnishing(dict(leaf, width = .1, length = .1), world)
            assert v.ObjectsOverlap(nested, probe, contactTolerance = 0) == (alphas == {255}), (x, y)
    cached = FurnishingCollisionFootprints(nested)
    assert FurnishingCollisionFootprints(nested) is cached
    nested.width *= 1.1
    assert FurnishingCollisionFootprints(nested) is not cached
    # A newly drawn single wall uses the same invalid overlay as a dragged wall.
    desk = Furnishing(v.furnishingDefinitions["desk"])
    v.furnishings, v.walls = [desk], []
    v.pendingWall = Wall(point(-1000, 0), point(1000, 0), 200)
    v.showMeasurements = False
    for offset, invalid in ((0, True), (2000, False)):
        v.pendingWall.firstVertex, v.pendingWall.secondVertex = point(-1000, offset), point(1000, offset)
        image = QtGui.QImage(v.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(image)
        try:
            state = v.DrawScene(painter, v.DrawingRect(), v.WorldToViewport(point()),
                v.basePixelsPerMillimeter * v.zoom, drawAnnotations = False)
        finally:
            painter.end()
        assert (id(v.pendingWall) in state[3]) == invalid
    v.pendingWall = None
    main.MarkProjectClean()
    main.close()


if __name__ == "__main__":
    Main()
