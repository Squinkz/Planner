"""SVG-aware picking passes through gaps without changing collision/drag boxes."""
import os
import sys
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Furnishing
from planner_app.graphics.furnishings import FurnishingContainsPoint, FurnishingRenderer
from planner_app.viewport.widget import DrawingViewport


def ArtworkPoint(obj, renderer, x, y):
    viewBox = renderer.viewBoxF()
    center = (obj.firstVertex + obj.secondVertex) / 2
    transform = QtGui.QTransform().translate(center.x(), center.y()).rotate(obj.angle)
    transform.scale(obj.width / viewBox.width(), -obj.length / viewBox.height())
    transform.scale(-1 if obj.flipHorizontal else 1, -1 if obj.flipVertical else 1)
    transform.translate(-viewBox.center().x(), -viewBox.center().y())
    return transform.map(QtCore.QPointF(x, y))


def Main():
    app = QtWidgets.QApplication([])
    v = DrawingViewport()
    v.setMinimumSize(0, 0)
    v.resize(1000, 800)
    v.zoom = 1
    v.walls, v.windows = [], []
    squareSvg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="white"/></svg>'
    backDefinition = {**v.furnishingDefinitions["null"], "key": "hit-back", "width": 300, "length": 300,
                      "graphicData": squareSvg}
    v.furnishingRenderers["hit-back"] = FurnishingRenderer(squareSvg)
    desk = Furnishing(v.furnishingDefinitions["desk_l"])
    for transparent in (False, True):
        renderer = FurnishingRenderer(desk.definition["imagePath"], solidBackground = not transparent)
        v.furnishingRenderers["desk_l"] = renderer
        source = getattr(renderer, "solidRenderer", renderer)
        with patch.object(source, "render", wraps = source.render) as render:
            for angle in (0, 37, 90, 213):
                for horizontal, vertical in ((False, False), (True, False), (False, True), (True, True)):
                    desk.angle = angle
                    desk.flipHorizontal, desk.flipVertical = horizontal, vertical
                    desk.width = desk.definition["width"] * 1.2
                    center = (desk.firstVertex + desk.secondVertex) / 2
                    halfLength = (desk.secondVertex - desk.firstVertex) / desk.length * (desk.definition["length"] * .8 / 2)
                    desk.firstVertex, desk.secondVertex = center - halfLength, center + halfLength
                    gap = ArtworkPoint(desk, renderer, 90, 100)
                    body = ArtworkPoint(desk, renderer, 90, 20)
                    empty = ArtworkPoint(desk, renderer, 20, 140)
                    back = Furnishing(backDefinition, gap)
                    v.furnishings = [back, desk]
                    v.SetSelection([])
                    assert v.HitTest(v.WorldToViewport(gap)) == (back, None), (angle, horizontal, vertical)
                    assert v.HitTest(v.WorldToViewport(body)) == (desk, None)
                    assert v.HitTest(v.WorldToViewport(empty)) == (None, None)
                    assert v.ObjectsOverlap(desk, back), "Picking changed the rectangular collision footprint"
                    v.SetSelection([(desk, None)])
                    assert v.HitTest(v.WorldToViewport(gap)) == (desk, None), "Selected drag box lost its transparent interior"
            assert render.call_count == 1, "SVG was re-rendered for an instance transform or repeated hit test"
        v.SetSelection([])
        for zoom in (.2, 1, 3):
            v.zoom = zoom
            assert v.HitTest(v.WorldToViewport(gap)) == (back, None)
            assert v.HitTest(v.WorldToViewport(body)) == (desk, None)

    # Internal holes, transforms, hidden shapes and strokes follow SVG coverage.
    fixtures = [
        (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path fill="white" fill-rule="evenodd" d="M0 0H100V100H0Z M30 30H70V70H30Z"/></svg>', (10, 50), (50, 50)),
        (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><g transform="translate(10 20)"><rect width="30" height="50" fill="white"/></g></svg>', (20, 50), (70, 50)),
        (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path d="M10 20H90" fill="none" stroke="black"/></svg>', (50, 20), (50, 70)),
        (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" display="none"/><circle cx="20" cy="20" r="10" fill="black"/></svg>', (20, 20), (70, 70)),
    ]
    for graphic, ink, hole in fixtures:
        renderer = FurnishingRenderer(graphic)
        obj = Furnishing({**backDefinition, "width": 1000, "length": 1000})
        assert FurnishingContainsPoint(obj, renderer, ArtworkPoint(obj, renderer, *ink), 5)
        assert not FurnishingContainsPoint(obj, renderer, ArtworkPoint(obj, renderer, *hole), 5), graphic
    line = FurnishingRenderer(fixtures[2][0])
    assert FurnishingContainsPoint(obj, line, ArtworkPoint(obj, line, 50, 20) + QtCore.QPointF(0, 4), 5)
    assert not FurnishingContainsPoint(obj, line, ArtworkPoint(obj, line, 50, 20) + QtCore.QPointF(0, 20), 5)

    # Only nearby definitions acquire masks; all instances share each mask.
    coldRenderer = FurnishingRenderer(squareSvg)
    coldDefinition = {**backDefinition, "key": "hit-far"}
    v.furnishingRenderers["hit-far"] = coldRenderer
    v.furnishings = [Furnishing(coldDefinition, QtCore.QPointF(10000 + index * 1000, 10000)) for index in range(500)] + [back, desk]
    v.zoom = 1
    screen = v.WorldToViewport(body)
    v.HitTest(screen)
    started = perf_counter()
    for index in range(500):
        assert v.HitTest(screen)[0] is desk
    hitMilliseconds = (perf_counter() - started) * 1000 / 500
    assert not hasattr(coldRenderer, "hitCoverage"), "Offscreen objects built unnecessary SVG masks"
    coverage = source.hitCoverage
    started = perf_counter()
    for index in range(10000):
        assert FurnishingContainsPoint(desk, source, body, 25)
    coverageMicroseconds = (perf_counter() - started) * 1000000 / 10000
    assert source.hitCoverage is coverage
    print("PASS: transparent picking, rotated/flipped/resized SVGs, drag/collision boxes, holes/strokes and lazy shared masks.")
    print(f"Warm mask lookup: {coverageMicroseconds:.1f} us; full HitTest with 502 furnishings: {hitMilliseconds:.3f} ms.")
    v.close()


if __name__ == "__main__":
    Main()
