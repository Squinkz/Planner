"""Authored SVG dimension markers must not clip or resize protruding artwork."""
import os
import sys
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets, QtSvg
from planner_app.graphics.object_composite import ObjectPaintDevice
from planner_app.paths import furnishingsDirectory
from planner_app.graphics.furnishings import (
    ApplyFurnishingBounds, CompoundFurnishingSvg, FurnishingRenderer,
    FurnishingArtworkBounds, SelectedFurnishingRenderer,
)
from planner_app.models import Furnishing
from planner_app.export_bounds import AutomaticBounds
from planner_app.viewport.widget import DrawingViewport
from planner_app.viewport import rendering
from check_pan_dpi import CompareDirect


def Main():
    app = QtWidgets.QApplication([])
    # Qt treats rx=0 as square even when Inkscape displays rounding from ry.
    # Verify the actual rendered bodies retain curves, not merely SVG attributes.
    for filename, bodyId in (("wardrobe_single.svg", "rect1"), ("drawers.svg", "rect1"),
                             ("treadmill.svg", "rect1-8-5-7")):
        renderer = FurnishingRenderer(furnishingsDirectory / "images" / filename)
        device = ObjectPaintDevice(QtCore.QSize(800, 600), "white")
        with QtGui.QPainter(device) as painter:
            QtSvg.QSvgRenderer.render(renderer, painter, bodyId, QtCore.QRectF(0, 0, 800, 600))
        assert any(not isinstance(path, tuple) and any(path.elementAt(index).type == QtGui.QPainterPath.ElementType.CurveToElement
                   for index in range(path.elementCount())) for path, *unused in device.engine.commands), filename
    artwork = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 110">
      <rect x="20" y="30" width="100" height="60" fill="white" stroke="black"/>
      <rect x="120" y="50" width="20" height="20" fill="black"/>
      <g style="display:none"><rect id="planner-bounds" x="20" y="30"
        width="100" height="60" fill="red" stroke="red" stroke-width="50"/></g>
    </svg>'''.encode()
    target = QtCore.QRectF(100, 100, 200, 120)
    for renderer in (FurnishingRenderer(artwork), SelectedFurnishingRenderer(artwork),
                     FurnishingRenderer(artwork, solidBackground = False)):
        assert renderer.viewBoxF() == QtCore.QRectF(20, 30, 100, 60)
        image = QtGui.QImage(450, 350, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        with QtGui.QPainter(image) as painter:
            renderer.render(painter, target)
        assert image.pixelColor(320, 160).alpha() == 255, 'Handle must extend beyond dimension bounds'
        assert image.pixelColor(80, 160).alpha() == 0, 'Metadata rectangle must not paint'
        if hasattr(renderer, 'backgroundPath'):
            assert renderer.backgroundPath.contains(QtCore.QPointF(60, 60))
            assert not renderer.backgroundPath.contains(QtCore.QPointF(130, 60))

    # Inkscape may transform the rectangle itself and its hidden parent layer.
    transformed = ElementTree.fromstring('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500">
      <g transform="translate(100 200)" style="display:none">
        <rect id="planner-bounds" x="10" y="20" width="80" height="60"
          transform="scale(2 3)" stroke="black" stroke-width="100"/>
      </g></svg>''')
    assert ApplyFurnishingBounds(transformed) == QtCore.QRectF(120, 260, 160, 180)
    rotated = ElementTree.fromstring('''<svg xmlns="http://www.w3.org/2000/svg">
      <g transform="translate(100 200) rotate(90)"><rect id="planner-bounds"
        width="80" height="60" style="display:none"/></g></svg>''')
    bounds = ApplyFurnishingBounds(rotated)
    assert abs(bounds.x() - 40) < 1e-8 and abs(bounds.y() - 200) < 1e-8
    assert abs(bounds.width() - 60) < 1e-8 and abs(bounds.height() - 80) < 1e-8
    # Inkscape can convert the bounds rectangle to a path while editing other
    # details. It still defines the body, including alongside fixed-size ink.
    pathArtwork = artwork.replace(
        b'<rect id="planner-bounds" x="20" y="30"\n        width="100" height="60"',
        b'<path id="planner-bounds" d="M 20 30 h 100 v 60 h -100 z"')
    pathArtwork = pathArtwork.replace(b'<rect x="120"', b'<rect id="planner-fixed-handle" x="120"')
    for renderFactory in (FurnishingRenderer, SelectedFurnishingRenderer, FurnishingRenderer):
        renderer = renderFactory(pathArtwork, nominalSize = (200, 120))
        assert renderer.viewBoxF() == QtCore.QRectF(20, 30, 100, 60)
        assert len(renderer.fixedElements) == 1
        image = QtGui.QImage(600, 400, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        with QtGui.QPainter(image) as painter:
            renderer.render(painter, QtCore.QRectF(100, 100, 400, 240), worldSize = (400, 240))
        assert image.pixelColor(530, 220).alpha() == 255, 'Fixed handle must remain beyond the authored body'
        assert image.pixelColor(80, 220).alpha() == 0, 'Path metadata must not paint'
    pathBounds = ElementTree.fromstring('''<svg xmlns="http://www.w3.org/2000/svg">
      <g transform="translate(100 200) rotate(90)" style="display:none">
        <path id="planner-bounds" d="M 0 0 H 80 V 60 H 0 Z"/>
      </g></svg>''')
    assert ApplyFurnishingBounds(pathBounds) == bounds
    openPathBounds = ElementTree.fromstring('''<svg xmlns="http://www.w3.org/2000/svg">
      <path id="planner-bounds" d="M 20 30 L 120 90"/>
    </svg>''')
    assert ApplyFurnishingBounds(openPathBounds) == QtCore.QRectF(20, 30, 100, 60)
    for filename, width in (("cabinet.svg", 60), ("cabinet_single.svg", 30)):
        source = (furnishingsDirectory / "images" / filename).read_bytes()
        renderer = FurnishingRenderer(source, nominalSize = (width * 10, 350))
        assert renderer.viewBoxF() == QtCore.QRectF(0, 2.5, width, 35), filename
        assert renderer.fixedElements, filename
        child = {"definition": {"graphicData": source, "width": width * 10, "length": 350},
                 "width": width * 10, "length": 350, "x": 0, "y": 0, "angle": 0, "zIndex": 0}
        compound, *unused = CompoundFurnishingSvg([child])
        compoundRenderer = FurnishingRenderer(compound, nominalSize = (width * 10, 350))
        assert compoundRenderer.viewBoxF() == QtCore.QRectF(-width * 5, -175, width * 10, 350)
        assert compoundRenderer.fixedElements
    for marker in ('', '<rect id="planner-bounds" width="0" height="60"/>',
                   '<path id="planner-bounds" d="M 0 0 Z"/>'):
        source = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 110">{marker}<rect width="100" height="60"/></svg>'.encode()
        assert FurnishingRenderer(source).viewBoxF() == QtCore.QRectF(0, 0, 160, 110)

    # Definitions retain their physical dimensions, including in compounds.
    definition = {"key": "test", "width": 200, "length": 120, "graphicData": artwork}
    furnishing = Furnishing(definition)
    renderer = FurnishingRenderer(artwork)
    assert furnishing.width == 200 and furnishing.length == 120
    assert FurnishingArtworkBounds(furnishing, renderer).right() >= 140
    furnishing.angle = 90
    assert FurnishingArtworkBounds(furnishing, renderer).top() <= -100
    child = {"definition": definition, "width": 200, "length": 120, "x": 0, "y": 0, "angle": 0, "zIndex": 0}
    graphic, width, length, center = CompoundFurnishingSvg([child])
    assert width == 200 and length == 120 and center == (0, 0)
    compoundRenderer = FurnishingRenderer(graphic)
    assert compoundRenderer.viewBoxF() == QtCore.QRectF(-100, -60, 200, 120)
    image = QtGui.QImage(450, 350, QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    with QtGui.QPainter(image) as painter:
        compoundRenderer.render(painter, target)
    assert image.pixelColor(320, 160).alpha() == 255
    assert image.pixelColor(80, 160).alpha() == 0

    class ExportFixture:
        walls = windows = labels = []
        furnishings = [Furnishing(definition)]
        furnishingRenderers = {"test": renderer}

        def IsObjectVisible(self, obj):
            return True

        def ObjectFootprint(self, obj):
            return None, [QtCore.QPointF(-100, -60), QtCore.QPointF(100, 60)], None

    assert AutomaticBounds(ExportFixture())[2] >= 2240
    # Paint protrusions even when the physical body is outside the viewport.
    viewport = DrawingViewport()
    viewport.resize(600, 400)
    viewport.performanceTimer.stop()
    viewport.basePixelsPerMillimeter = 1
    viewport.zoom = 1
    viewport.showMeasurements = False
    viewport.furnishingDefinitions['test'] = definition
    viewport.furnishingRenderers['test'] = renderer
    viewport.selectedFurnishingRenderers['test'] = SelectedFurnishingRenderer(artwork)
    center = viewport.ViewportToWorld(QtCore.QPointF(viewport.rulerSize - 130, 200))
    viewport.furnishings = [Furnishing(definition, center)]
    viewport.show()
    app.processEvents()
    viewport.performanceLabel.hide()
    viewport.isPanning = True
    with patch.object(rendering, 'DrawFurnishing', wraps = rendering.DrawFurnishing) as draw:
        viewport.viewportPanRaster = None
        viewport.grab()
        assert draw.call_count > 0, 'Visible handles must not be culled with the offscreen body'
    for delta in (QtCore.QPointF(3, 1), QtCore.QPointF(-5, -2), QtCore.QPointF(8, 3)):
        viewport.panOffset += delta
        CompareDirect(viewport)
    viewport.close()
    print('PASS: hidden markers, transforms, protruding ink, masks, fallback, compounds, exports and pan culling.')


if __name__ == '__main__':
    Main()
