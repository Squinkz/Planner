"""Selective SVG paints and exact adjacent-mask consolidation preserve pixels."""
import os
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.svg_preview import SvgPreviewRenderer, SvgClipPath
from fixtures.svg_preview_reference_20261019 import SvgPreviewRenderer as ReferenceSvgPreviewRenderer


def Render(renderer, scale, pan):
    image = QtGui.QImage(440, 330, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    with QtGui.QPainter(image) as painter:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setClipRect(QtCore.QRectF(3, 4, 430, 320))
        scaleX, scaleY = scale if isinstance(scale, tuple) else (scale, scale)
        renderer.render(painter, QtCore.QRectF(pan.x(), pan.y(), 320 * scaleX, 220 * scaleY))
    return image


def Main():
    app = QtWidgets.QApplication([])
    data = b'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
                   width="320" height="220" viewBox="0 0 320 220">
      <defs>
        <clipPath id="a"><path clip-rule="evenodd" d="M10 10H310V210H10Z M100 70H200V150H100Z"/></clipPath>
        <clipPath id="b"><path clip-rule="evenodd" d="M10 10H310V210H10Z M100 70H200V150H100Z"/></clipPath>
        <clipPath id="shifted"><path clip-rule="evenodd" d="M0 0H300V200H0Z M90 60H190V140H90Z"/></clipPath>
        <clipPath id="different"><path clip-rule="evenodd" d="M10 10H310V210H10Z M101 70H200V150H101Z"/></clipPath>
        <clipPath id="winding"><path clip-rule="nonzero" d="M10 10H310V210H10Z M100 70H200V150H100Z"/></clipPath>
        <clipPath id="curve"><path d="M20 110C20 5 300 5 300 110C300 215 20 215 20 110Z"/></clipPath>
        <clipPath id="curveAlias"><path d="M20 110C20 5 300 5 300 110C300 215 20 215 20 110Z"/></clipPath>
        <linearGradient id="gradient"><stop offset="0" stop-color="#606060" data-planner-stop-color="grid"/>
          <stop offset="1" stop-color="#c0c0c0"/></linearGradient>
        <linearGradient id="gradientAlias" xlink:href="#gradient"/>
      </defs>
      <rect width="320" height="220" fill="#101010" data-planner-fill="canvas"/>
      <g clip-path="url(#a)" fill="#ffffff" data-planner-fill="objectOutline">
        <rect x="0" y="15" width="240" height="95" opacity="0.65"/>
      </g>
      <g clip-path="url(#b)" fill="#ffffff" data-planner-fill="wallOutline" opacity="0.6">
        <ellipse cx="210" cy="100" rx="100" ry="90"/>
      </g>
      <g transform="matrix(1,0,0,1,10,10)" clip-path="url(#shifted)">
        <path d="M0 150H290" stroke="#009000" stroke-width="8"/>
      </g>
      <g clip-path="url(#different)"><rect x="90" y="75" width="25" height="65" fill="#ff8000"/></g>
      <g clip-path="url(#winding)"><rect x="110" y="80" width="20" height="50" fill="#00a0f0"/></g>
      <g clip-path="url(#a)"><g clip-path="url(#b)"><path d="M5 170H315" stroke="#ffffff" stroke-width="7" data-planner-stroke="objectOutline"/></g></g>
      <g clip-path="url(#b)"><g clip-path="url(#a)"><path d="M5 190H315" stroke="#ffff00" stroke-width="7"/></g></g>
      <g clip-path="url(#curve)"><rect x="0" y="0" width="320" height="35" fill="url(#gradientAlias)"/></g>
      <g clip-path="url(#curveAlias)"><rect x="0" y="35" width="320" height="30" fill="url(#gradientAlias)" opacity="0.7"/></g>
      <rect x="0" y="215" width="320" height="5" fill="#ff00ff"/>
    </svg>'''
    with patch("planner_app.graphics.svg_preview.SvgClipPath", wraps = SvgClipPath) as parse:
        actual = SvgPreviewRenderer(data)
        assert parse.call_count == 5, "Repeated clip definitions were parsed again"
    for source in actual.layerSources:
        ids = {element.get("id") for element in source.iter() if element.get("id")}
        if "gradientAlias" not in ids:
            assert "gradient" not in ids, "Unused definitions were copied into a preview layer"
    reference = ReferenceSvgPreviewRenderer(data)
    assert len(actual.layers) == len(reference.layers) - 4, (len(actual.layers), len(reference.layers))
    colors = {"canvas": "#101010", "objectOutline": "#ffffff", "wallOutline": "#ffffff", "grid": "#606060"}
    for role, color in ((None, None), ("canvas", "#283746"), ("objectOutline", "#e95c32"),
                        ("wallOutline", "#32c5e9"), ("grid", "#bc812e"), ("grid", "#bc812e")):
        if role is not None:
            colors[role] = color
            with ExitStack() as stack:
                loads = [stack.enter_context(patch.object(renderer, "load", wraps = renderer.load))
                         for clipPaths, renderer in actual.layers]
                previous = dict(actual.paintValues)
                assert actual.Recolor(colors) == reference.Recolor(colors)
                expected = actual.paintLayers.get(role, ()) if previous[role] != color else ()
                assert {index for index, load in enumerate(loads) if load.call_count} == set(expected)
                assert all(load.call_count <= 1 for load in loads)
            if role == "grid":
                assert len(actual.paintLayers[role]) == 1, "Unreferenced gradient definitions triggered unrelated layer loads"
        for scale, pan in ((.43, QtCore.QPointF(13.37, 21.71)), (1, QtCore.QPointF()),
                           (2.7, QtCore.QPointF(-87.21, -102.3)), ((1.7, .65), QtCore.QPointF(-60.2, 31.8)),
                           (80, QtCore.QPointF(-7900, -6950))):
            assert Render(actual, scale, pan) == Render(reference, scale, pan), (role, scale, pan)
    # Identical geometry with different fill rules remains separate; a one-unit
    # hole change also remains separate. Both are covered by the exact pixels.
    assert actual.layers[2][0] != actual.layers[3][0]
    translucent = data.replace(b'width="320" height="220" viewBox=', b'opacity="0.55" width="320" height="220" viewBox=', 1)
    actual, reference = SvgPreviewRenderer(translucent), ReferenceSvgPreviewRenderer(translucent)
    assert Render(actual, 1.37, QtCore.QPointF(-12.3, 7.1)) == Render(reference, 1.37, QtCore.QPointF(-12.3, 7.1))


if __name__ == "__main__":
    Main()
