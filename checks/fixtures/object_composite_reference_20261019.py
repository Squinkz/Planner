"""Frozen pre-optimization transparent replay for independent pixel comparisons."""
import math
from planner_app.geometry.path_operations import ClipPathCoverage
from planner_app.graphics.path_operations import Paths
from PySide6 import QtCore, QtGui, QtSvg
from planner_app.graphics.furnishing_mask import BackgroundPathDevice, BackgroundPathEngine


class ObjectPaintEngine(BackgroundPathEngine):
    def __init__(self, background):
        super().__init__()
        self.background = QtGui.QColor(background)
        self.commands = []
        self.captureBackground = True

    def drawPath(self, path):
        painter = self.painter()
        clip = self.transform.map(painter.clipPath()) if painter.hasClipping() else None
        pen = QtGui.QPen(painter.pen())
        brush = QtGui.QBrush(self.brush)
        mask = QtGui.QPainterPath()
        if (self.captureBackground and brush.style() == QtCore.Qt.BrushStyle.SolidPattern
                and brush.color() == self.background):
            mask = self.transform.map(path)
            brush = QtGui.QBrush(QtCore.Qt.BrushStyle.NoBrush)
        if self.captureBackground and pen.style() != QtCore.Qt.PenStyle.NoPen and pen.color() == self.background:
            stroke = Paths.PreparePenStroke(pen)
            mask = Paths.Union(mask, self.transform.map(stroke(path)))
            pen = QtGui.QPen(QtCore.Qt.PenStyle.NoPen)
        if clip is not None:
            mask = Paths.Intersection(mask, clip)
        if self.opacity <= 0:
            return
        self.commands.append((QtGui.QPainterPath(path), pen, brush, QtGui.QTransform(self.transform),
                              self.opacity, clip, mask, painter.renderHints(), painter.brushOrigin()))

    def drawPolygon(self, points, mode):
        if mode != QtGui.QPaintEngine.PolygonDrawMode.PolylineMode:
            super().drawPolygon(points, mode)
            return
        path = QtGui.QPainterPath()
        if points:
            path.moveTo(points[0])
            for point in points[1:]:
                path.lineTo(point)
        self.drawPath(path)

    def drawLines(self, lines):
        path = QtGui.QPainterPath()
        for line in lines:
            path.moveTo(line.p1())
            path.lineTo(line.p2())
        self.drawPath(path)

    def drawTextItem(self, point, item):
        path = QtGui.QPainterPath()
        path.addText(QtCore.QPointF(point), item.font(), item.text())
        # QPainter uses its pen as the text fill, never as a glyph outline.
        # Replay the same filled ink rather than thickening it with a stroke.
        painter = self.painter()
        textBrush = painter.pen().brush()
        painter.save()
        try:
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(textBrush)
            painter.drawPath(path)
        finally:
            painter.restore()

    def drawPixmap(self, rect, pixmap, source):
        self.drawImage(rect, pixmap.toImage(), source)

    def drawImage(self, rect, image, source, flags = QtCore.Qt.ImageConversionFlag.AutoColor):
        painter = self.painter()
        clip = self.transform.map(painter.clipPath()) if painter.hasClipping() else None
        self.commands.append(((QtCore.QRectF(rect), QtGui.QImage(image), QtCore.QRectF(source)),
                              QtGui.QPen(), QtGui.QBrush(), QtGui.QTransform(self.transform), self.opacity,
                              clip, QtGui.QPainterPath(), painter.renderHints(), painter.brushOrigin()))

    def Replay(self, painter, rect, clipCache = None):
        bakeStrokes = isinstance(painter.device(), QtSvg.QSvgGenerator)
        geometry = []
        for command in self.commands:
            path, pen, brush, transform, opacity, clip, mask, hints, brushOrigin = command
            bounds = transform.mapRect(path[0]) if isinstance(path, tuple) else transform.map(path).boundingRect()
            margin = 1.0
            if pen.style() != QtCore.Qt.PenStyle.NoPen:
                width = pen.widthF() or 1.0
                scale = (1.0 if pen.isCosmetic() else math.sqrt(transform.m11() ** 2 + transform.m12() ** 2
                         + transform.m21() ** 2 + transform.m22() ** 2))
                margin += width * scale / 2
            bounds = bounds.adjusted(-margin, -margin, margin, margin).intersected(rect)
            geometry.append(((bounds.x(), bounds.y(), bounds.width(), bounds.height()), mask))
        # These clips depend on ordered bounds and background silhouettes, not
        # paint colors. Reuse native booleans across recolors, checking every
        # input so moved/resized/reordered objects still invalidate immediately.
        clips = clipCache.get("clips") if clipCache is not None and clipCache.get("geometry") == geometry else None
        if clips is None:
            covered = []
            clips = []
            for boundsValues, mask in reversed(geometry):
                bounds = QtCore.QRectF(*boundsValues)
                origin = bounds.center()
                localCanvas = QtGui.QPainterPath()
                localCanvas.addRect(bounds.translated(-origin))
                masks = (background.translated(-origin) for background, backgroundBounds in covered
                         if backgroundBounds.intersects(bounds))
                # Intersect captured doorway clips separately during painting;
                # merging them here can invert holes at a cropped wall edge.
                visible = ClipPathCoverage(Paths, localCanvas, masks)
                clips.append(visible.translated(origin))
                if not mask.isEmpty():
                    covered.append((mask, mask.boundingRect()))
            if clipCache is not None:
                clipCache.clear()
                if len(geometry) <= 8192 and sum(path.elementCount() for path in clips) + sum(mask.elementCount() for bounds, mask in geometry) <= 262144:
                    clipCache.update(geometry = geometry, clips = clips)
        for command, visible in zip(self.commands, reversed(clips)):
            path, pen, brush, transform, opacity, clip, mask, hints, brushOrigin = command
            if pen.style() == QtCore.Qt.PenStyle.NoPen and brush.style() == QtCore.Qt.BrushStyle.NoBrush:
                continue
            painter.save()
            try:
                painter.setClipPath(visible, QtCore.Qt.ClipOperation.IntersectClip)
                if clip is not None:
                    painter.setClipPath(clip, QtCore.Qt.ClipOperation.IntersectClip)
                painter.setWorldTransform(transform, True)
                painter.setOpacity(opacity)
                painter.setRenderHints(hints)
                painter.setBrushOrigin(brushOrigin)
                painter.setPen(pen)
                painter.setBrush(brush)
                if isinstance(path, tuple):
                    painter.drawImage(*path)
                elif bakeStrokes and pen.style() != QtCore.Qt.PenStyle.NoPen and pen.isCosmetic():
                    # Cosmetic widths are export units here, not SVG-viewer pixels.
                    # Outline the transformed stroke so later SVG resizing scales it.
                    painter.setPen(QtCore.Qt.PenStyle.NoPen)
                    painter.drawPath(path)
                    stroker = Paths.PreparePenStroke(pen, width = pen.widthF() if pen.widthF() > 0 else 1)
                    outline = stroker(painter.worldTransform().map(path))
                    painter.resetTransform()
                    painter.fillPath(outline, pen.brush())
                else:
                    painter.drawPath(path)
            finally:
                painter.restore()


class ObjectPaintDevice(BackgroundPathDevice):
    def __init__(self, size, background):
        super().__init__(size)
        self.engine = ObjectPaintEngine(background)
