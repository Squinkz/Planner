"""Bound clip caches and reuse model preparations across export appearance edits."""
import os
from pathlib import Path
import sys
from unittest.mock import patch
from xml.etree import ElementTree

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg
from shiboken6 import isValid
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.graphics import svg_preview
from planner_app.graphics.object_composite import ObjectPaintDevice
from planner_app.graphics.furnishings import FurnishingRendererMap
from planner_app.models import Wall, Furnishing


class ClipTrackingPainter(QtGui.QPainter):
    def setClipPath(self, path, operation = QtCore.Qt.ClipOperation.ReplaceClip):
        assert operation == QtCore.Qt.ClipOperation.ReplaceClip, "SVG accumulated nested native clip intersections"
        super().setClipPath(path, operation)


def Main():
    with ExampleWindow() as (main, folder):
        size = QtCore.QSize(700, 500)
        device = ObjectPaintDevice(size, "white")
        with QtGui.QPainter(device) as painter:
            clip = QtGui.QPainterPath()
            clip.addRect(10, 10, 680, 480)
            for index in range(80):
                clip.addEllipse(25 + index % 10 * 65, 25 + index // 10 * 56, 22, 22)
            painter.setClipPath(clip)
            painter.setPen(QtGui.QPen(QtGui.QColor("black"), 1))
            for index in range(150):
                painter.save()
                painter.translate(index % 10 * 65, index // 10 * 30)
                painter.rotate(index % 5)
                painter.setBrush(QtGui.QColor("white"))
                painter.drawRoundedRect(0, 0, 50, 20, 4, 4)
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawLine(0, 0, 55, 27)
                painter.restore()
        data = QtCore.QByteArray()
        buffer = QtCore.QBuffer(data)
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        generator = QtSvg.QSvgGenerator()
        generator.setOutputDevice(buffer)
        generator.setSize(size)
        generator.setViewBox(QtCore.QRect(QtCore.QPoint(), size))
        with ClipTrackingPainter(generator) as painter:
            painter.setClipRect(QtCore.QRectF(0, 0, 700, 500))
            device.engine.Replay(painter, QtCore.QRectF(0, 0, 700, 500))
        assert svg_preview.SvgPreviewRenderer(bytes(data)).isValid()
        # Cache hits must return independent Qt values, with the fill rule in
        # their key. Repeated edits cannot accumulate unbounded XML/native data.
        element = ElementTree.Element("path", d = "M0 0 L10 0 L10 10 Z", **{"clip-rule": "evenodd"})
        first = svg_preview.SvgClipPath(element)
        first.lineTo(30, 30)
        second = svg_preview.SvgClipPath(element)
        assert second != first and second.fillRule() == QtCore.Qt.FillRule.OddEvenFill
        element.set("clip-rule", "nonzero")
        assert svg_preview.SvgClipPath(element).fillRule() == QtCore.Qt.FillRule.WindingFill
        for index in range(300):
            svg_preview.SvgClipPath(ElementTree.Element("path", d = f"M{index} 0 L{index + 1} 0 L{index + 1} 10 Z"))
        assert len(svg_preview.clipPathCache) <= 256
        assert svg_preview.clipPathCacheElements <= 262144 and svg_preview.clipPathCacheBytes <= 4 * 1024 * 1024
        v, panel = main.viewport, main.exportPanel
        renderers = FurnishingRendererMap(v.furnishingDefinitions, solidBackground = False)
        solid = renderers.Copy(solidBackground = True)["washer"]
        assert "washer" in renderers.solidVariants
        assert renderers.Copy(solidBackground = True)["washer"] is solid
        points = [QtCore.QPointF(x, y) for x, y in ((0, 0), (7000, 0), (7000, 5000), (0, 5000))]
        InstallScene(main, [*[Wall(points[index], points[(index + 1) % 4], 200) for index in range(4)],
                            Furnishing(v.furnishingDefinitions["washer"], QtCore.QPointF(2000, 2000))])
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("scaleMode", "Print")
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        overlay = v.exportOverlay
        v.grab()
        assert not overlay.previewError, overlay.previewError
        retained = overlay.printVectorRenderer
        assert retained is not None
        with patch.object(overlay, "renderPrintScene", side_effect = AssertionError("Solid Rooms rebuilt SVG model")):
            for solid in (not v.solidRooms, v.solidRooms):
                panel.SetOverride("solidRooms", solid)
                v.grab()
                assert not overlay.previewError, overlay.previewError
                assert overlay.printVectorRenderer is retained
        with patch.object(overlay, "renderPrintScene", wraps = overlay.renderPrintScene):
            panel.SetScaleOption("architecturalScale", 75)
            v.grab()
            assert not overlay.previewError, overlay.previewError
            assert not isValid(retained), "Old native SVG scene remained alive after replacement"
        # An off-sheet object must not force a million-unit SVG/background
        # capture when only one local sheet is selected.
        v.walls.append(Wall(QtCore.QPointF(1_000_000, 0), QtCore.QPointF(1_007_000, 0), 200))
        v.EnsureObjectIds()
        width, height = panel.PrintLayout()["paperTile"]
        overlay.bounds = (0, 0, width, height)
        panel.SetBounds(overlay.bounds)
        v.zoom = min(v.DrawingRect().width() / width, v.DrawingRect().height() / height) * .9 / v.basePixelsPerMillimeter
        v.panOffset += v.DrawingRect().center() - v.WorldToViewport(QtCore.QPointF(width / 2, height / 2))
        v.grab()
        assert not overlay.previewError, overlay.previewError
        assert overlay.printVectorBounds[2] < width * 4
        assert overlay.snapshotBounds[2] < width * 6


if __name__ == "__main__":
    Main()
