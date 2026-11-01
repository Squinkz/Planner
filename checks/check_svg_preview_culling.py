"""Off-screen SVG layers are skipped without changing pixels, clips or strokes."""
import os
from contextlib import ExitStack
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.svg_preview import SvgPreviewRenderer
from fixtures.svg_preview_reference_20261019 import SvgPreviewRenderer as ReferenceSvgPreviewRenderer


def Main():
    app = QtWidgets.QApplication([])
    definitions, content = [], []
    for index in range(300):
        x, y = -80 + index % 20 * 95, -60 + index // 20 * 95
        definitions.append(f'<clipPath id="c{index}"><path d="M{x} {y}h70v70h-70Z"/></clipPath>')
        content.append(f'<g clip-path="url(#c{index})"><rect x="{x - 2}" y="{y - 2}" width="74" height="74" '
                       f'fill="#{index * 7919 % 0xffffff:06x}"/><path d="M{x} {y}l70 70" stroke="#ffffff" stroke-width="2"/></g>')
    # Device-sized strokes must remain visible even if their thin transformed
    # geometry lies just beyond the viewport's logical bounds.
    content.append('<path d="M-400 30H300" transform="matrix(0.01,0,0,0.01,0,0)" '
                   'stroke="#de425b" stroke-width="8" vector-effect="non-scaling-stroke" fill="none"/>')
    data = ('<svg xmlns="http://www.w3.org/2000/svg" width="2000" height="1600" viewBox="-100 -80 2000 1600">'
            '<defs>' + ''.join(definitions) + '</defs>' + ''.join(content) + '</svg>').encode()
    actual, reference = SvgPreviewRenderer(data), ReferenceSvgPreviewRenderer(data)
    for ratio in (1, 1.5):
        for target in (QtCore.QRectF(0, 0, 400, 320), QtCore.QRectF(-1300, -900, 4000, 3200),
                       QtCore.QRectF(-3990, -2500, 12000, 9600), QtCore.QRectF(600, 600, 200, 160)):
            images = []
            with ExitStack() as stack:
                calls = [stack.enter_context(patch.object(renderer, "render", wraps = renderer.render))
                         for paths, renderer in actual.layers]
                for renderer in (actual, reference):
                    image = QtGui.QImage(round(240 * ratio), round(180 * ratio), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                    image.setDevicePixelRatio(ratio)
                    image.fill(QtCore.Qt.GlobalColor.transparent)
                    with QtGui.QPainter(image) as painter:
                        painter.translate(10, -4)
                        painter.rotate(-5)
                        painter.scale(1.1, .8)
                        painter.setClipRect(QtCore.QRectF(20, 10, 190, 140))
                        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
                        renderer.render(painter, target)
                    images.append(image)
                assert sum(call.call_count for call in calls) < len(actual.layers) / 2, "Replayed off-screen SVG layers"
            if images[0] != images[1]:
                images[0].save(str(Path(__file__).resolve().parents[1] / "diagnostics" / "svg-layer-actual.png"))
                images[1].save(str(Path(__file__).resolve().parents[1] / "diagnostics" / "svg-layer-reference.png"))
            assert images[0] == images[1], (ratio, target, "Visibility culling changed SVG pixels")
    print("SVG visibility indexing preserves exact pixels under zoom, clipping, transforms and display scaling")


if __name__ == "__main__":
    Main()
