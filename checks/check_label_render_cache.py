"""Independent label pixels, glyph-bound culling and retained text/layout reuse."""
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Label
from planner_app.graphics import palette
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.viewport.widget import DrawingViewport
from check_pan_dpi import CompareDirect


def LegacyLabels(viewport, painter, scale):
    # The original renderer supplies an independent pixel baseline; it performs
    # all font metrics and text calls even for labels outside the canvas.
    for label in viewport.labels:
        if not viewport.IsObjectVisible(label):
            continue
        painter.save()
        painter.translate(viewport.WorldToViewport((label.firstVertex + label.secondVertex) / 2))
        painter.rotate(-label.angle)
        metrics = QtGui.QFontMetricsF(label.Font())
        lines = label.text.split("\n")
        width = max(1.0, max(metrics.horizontalAdvance(line) for line in lines))
        height = metrics.lineSpacing() * len(lines)
        painter.scale(label.width * scale / width, label.length * scale / height)
        painter.setFont(label.Font())
        painter.setOpacity(label.intensity)
        painter.setPen(QtGui.QColor(palette.themeColors["objectOutline"]))
        for index, line in enumerate(lines):
            painter.drawText(QtCore.QPointF(-metrics.horizontalAdvance(line) / 2,
                                           -height / 2 + metrics.ascent() + index * metrics.lineSpacing()), line)
        painter.restore()


def Render(viewport, legacy = False):
    image = QtGui.QImage(viewport.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QtGui.QColor(palette.themeColors["canvas"]))
    painter = QtGui.QPainter(image)
    painter.setClipRect(viewport.DrawingRect())
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    scale = viewport.basePixelsPerMillimeter * viewport.zoom
    if legacy:
        LegacyLabels(viewport, painter, scale)
    else:
        viewport.DrawLabels(painter, scale, drawOutlines = False)
    painter.end()
    return image


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    viewport = DrawingViewport()
    viewport.resize(1000, 700)
    viewport.performanceTimer.stop()
    point = QtCore.QPointF
    first = Label(point(-1200, -200), "Wide line\nshort", .4)
    second = Label(point(600, -500), "j\u0301 Åg\n\n世界", .75)
    second.angle = 31
    second.width *= .6
    viewport.labels = [first, second] + [Label(point(50000 + index * 1500, 50000), f"Offscreen {index}")
                                        for index in range(200)]
    viewport.showGrid = False
    viewport.show()
    app.processEvents()
    viewport.performanceLabel.hide()
    assert Render(viewport) == Render(viewport, legacy = True)
    layouts = [obj.textLayout for obj in viewport.labels]
    with patch.object(QtGui, "QFontMetricsF", wraps = QtGui.QFontMetricsF) as metrics:
        for repeat in range(5):
            Render(viewport)
        assert metrics.call_count == 0, "Warm labels rebuilt font metrics"
    assert all(obj.textLayout is layout for obj, layout in zip(viewport.labels, layouts))

    # Hover outlines and camera-independent text belong to separate passes.
    # Unchanged labels-only scenes must retain text just like wall scenes.
    drawn = []
    labelLines = {line for label in viewport.labels for line in label.text.split("\n")}

    class TextPainter(QtGui.QPainter):
        def drawText(self, *args):
            if len(args) == 2 and isinstance(args[0], QtCore.QPointF) and args[1] in labelLines:
                drawn.append(args[1])
            return super().drawText(*args)

    with patch.object(QtGui, "QPainter", TextPainter):
        Render(viewport)
    assert drawn == first.text.split("\n") + second.text.split("\n"), drawn
    directCalls = len(drawn)
    drawn.clear()
    viewport.grab()
    with patch.object(QtGui, "QPainter", TextPainter), \
         patch.object(QtGui, "QFontMetricsF", wraps = QtGui.QFontMetricsF) as metrics:
        for repeat in range(8):
            viewport.hoverPosition = viewport.WorldToViewport((first.firstVertex + first.secondVertex) / 2)
            viewport.grab()
        assert not drawn and metrics.call_count == 0, ("Hover repainted retained text", drawn, metrics.call_count)
    CompareDirect(viewport)

    # Text/font rebuild layout; geometric/color changes reuse it while still
    # invalidating scene pixels. Compare multiline Unicode against the original.
    previous = first.textLayout
    first.text = "Edited\nlabel"
    assert Render(viewport) == Render(viewport, legacy = True)
    assert first.textLayout is not previous
    previous = first.textLayout
    for attribute, value in (("angle", 73), ("width", first.width * 1.4), ("intensity", .13)):
        setattr(first, attribute, value)
        assert Render(viewport) == Render(viewport, legacy = True)
        assert first.textLayout is previous
        CompareDirect(viewport)
    originalFont = palette.labelFont
    try:
        palette.labelFont = "monospace"
        assert Render(viewport) == Render(viewport, legacy = True)
        assert first.textLayout is not previous
        CompareDirect(viewport)
    finally:
        palette.labelFont = originalFont

    # Rotated, nonuniform text and accents cross each canvas edge during pans.
    for offset in (point(350, 0), point(-350, 0), point(0, 240), point(0, -240)):
        viewport.panOffset = offset
        viewport.isPanning = True
        viewport.viewportPanRaster = None
        viewport.grab()
        for delta in (point(3, 1), point(-9, -3), point(6, 2)):
            viewport.panOffset += delta
            assert Render(viewport) == Render(viewport, legacy = True)
            CompareDirect(viewport)
    viewport.isPanning = False
    viewport.SetSelection([(second, None)], notify = False)
    CompareDirect(viewport)
    viewport.visibility["Labels"] = False
    CompareDirect(viewport)
    viewport.close()
    report = {"offscreenLabels": 200, "visibleLineDraws": directCalls, "warmLayoutRebuilds": 0,
              "hoverFrames": 8, "hoverTextDraws": 0}
    (Path(__file__).resolve().parent.parent / "diagnostics/label-rendering-20261008.json").write_text(
        json.dumps(report, indent = 2) + "\n", encoding = "utf-8")
    print("PASS: independent text pixels, rotated glyph bounds, retained text, layout invalidation and pan edges.")


if __name__ == "__main__":
    Main()
