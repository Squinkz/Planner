"""Retained annotation commands agree with direct drawing across camera and selection changes."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Wall, Door, Stair, Counter, Furnishing, Label
from planner_app.viewport.widget import DrawingViewport
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.graphics.palette import themeColors


def AnnotationImage(v, state, direct):
    image = QtGui.QImage(v.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QtGui.QColor(themeColors["canvas"]))
    painter = QtGui.QPainter(image)
    painter.setFont(v.font())
    painter.setClipRect(v.DrawingRect())
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    previous = v.isDragging
    try:
        # Live interaction uses the direct preparation/drawing path, allowing
        # an independent comparison against retained command playback.
        v.isDragging = direct
        v.DrawSceneMeasurements(painter, v.DrawingRect(), state, retainCommands = not direct)
    finally:
        v.isDragging = previous
        painter.end()
    return image


def CompareAnnotations(cached, direct, context):
    if cached != direct:
        changes = [(x, y, cached.pixelColor(x, y).getRgb(), direct.pixelColor(x, y).getRgb())
                   for y in range(cached.height()) for x in range(cached.width()) if cached.pixel(x, y) != direct.pixel(x, y)]
        maximum = max(abs(a - b) for x, y, first, second in changes for a, b in zip(first, second))
        # Match the existing pan comparison's narrow Qt
        # antialiasing tolerance; no change to that check's limits.
        assert maximum <= 3 and len(changes) <= max(64, cached.width() * cached.height() // 1000), (
            context, maximum, len(changes), changes[:8])


def LabelImage(v, highlightedIds, commandKey):
    image = QtGui.QImage(v.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QtGui.QColor(themeColors["canvas"]))
    painter = QtGui.QPainter(image)
    painter.setFont(v.font())
    painter.setClipRect(v.DrawingRect())
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    v.DrawLabels(painter, v.basePixelsPerMillimeter * v.zoom, highlightedIds,
                 drawOutlines = False, commandKey = commandKey)
    painter.end()
    return image


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    v = DrawingViewport()
    v.performanceTimer.stop()
    v.resize(1001, 701)
    point = QtCore.QPointF
    wall = Wall(point(-2100, 1700), point(1900, 1700))
    v.walls = [wall, Stair(point(-800, 800), point(-800, -1300), 700),
               Counter(point(500, -1500), point(1800, -1500))]
    v.windows = [Door(wall, .2, .4)]
    v.furnishings = [Furnishing(v.furnishingDefinitions["desk"], point(500, 600))]
    v.labels = [Label(point(-1000, -1800), "Translucent label", .4)]
    v.show()
    app.processEvents()
    v.performanceLabel.hide()
    unitImages = []
    for units in ("Meters", "Millimeters"):
        v.unitsMode = units
        v.isPanning = True
        v.grab()
        state = v.viewportPanState
        v.EndPan()
        cached = AnnotationImage(v, state, False)
        direct = AnnotationImage(v, state, True)
        # Unit strings must invalidate commands even when geometry is unchanged.
        CompareAnnotations(cached, direct, units)
        unitImages.append(cached)
    assert unitImages[0] != unitImages[1], "Unit change left old annotation text"
    for zoom in (.25, .8):
        v.zoom = zoom
        for selection in ([], [(wall, None)], [(v.furnishings[0], None)]):
            v.SetSelection(selection)
            v.isPanning = True
            v.grab()
            state = v.viewportPanState
            commandKey = v.viewportPanKey
            v.EndPan()
            for pan in (point(), point(.7, -.3), point(2000, -1100)):
                v.panOffset = pan
                cached = AnnotationImage(v, state, False)
                direct = AnnotationImage(v, state, True)
                CompareAnnotations(cached, direct, (zoom, selection, pan))
                CompareAnnotations(LabelImage(v, state[1], commandKey), LabelImage(v, state[1], None),
                                   (zoom, selection, pan, "labels"))
            assert len(v.measurementPictures) <= 2
            assert sum(picture.size() for key, picture, origin in v.measurementPictures) <= 8 * 1024 * 1024
    v.close()


if __name__ == "__main__":
    Main()
