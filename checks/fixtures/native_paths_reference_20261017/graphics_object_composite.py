"""Replay physical artwork with transparent, occluding background silhouettes."""
import math
from PySide6 import QtCore, QtGui, QtSvg
from .furnishing_mask import BackgroundPathDevice, BackgroundPathEngine


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
            stroke = QtGui.QPainterPathStroker(pen)
            mask = mask.united(self.transform.map(stroke.createStroke(path)))
            pen = QtGui.QPen(QtCore.Qt.PenStyle.NoPen)
        if clip is not None:
            mask = mask.intersected(clip)
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

    def Replay(self, painter, rect):
        bakeStrokes = isinstance(painter.device(), QtSvg.QSvgGenerator)
        covered = []
        clips = []
        for command in reversed(self.commands):
            path, pen, brush, transform, opacity, clip, mask, hints, brushOrigin = command
            bounds = transform.mapRect(path[0]) if isinstance(path, tuple) else transform.map(path).boundingRect()
            margin = 1.0
            if pen.style() != QtCore.Qt.PenStyle.NoPen:
                width = pen.widthF() or 1.0
                scale = (1.0 if pen.isCosmetic() else math.sqrt(transform.m11() ** 2 + transform.m12() ** 2
                         + transform.m21() ** 2 + transform.m22() ** 2))
                margin += width * scale / 2
            bounds = bounds.adjusted(-margin, -margin, margin, margin).intersected(rect)
            origin = bounds.center()
            localCanvas = QtGui.QPainterPath()
            localCanvas.addRect(bounds.translated(-origin))
            localCovered = QtGui.QPainterPath()
            # Boolean operations on a full, translated scene can lose curved
            # contours at certain bitmap origins. Clip only relevant masks near
            # this command's own origin, where coordinates remain small.
            for background, backgroundBounds in covered:
                if backgroundBounds.intersects(bounds):
                    localCovered = localCovered.united(background.translated(-origin))
            visible = localCanvas.subtracted(localCovered)
            if clip is not None:
                visible = visible.intersected(clip.translated(-origin))
            clips.append(visible.translated(origin))
            if not command[6].isEmpty():
                covered.append((mask, mask.boundingRect()))
        for command, visible in zip(self.commands, reversed(clips)):
            path, pen, brush, transform, opacity, clip, mask, hints, brushOrigin = command
            if pen.style() == QtCore.Qt.PenStyle.NoPen and brush.style() == QtCore.Qt.BrushStyle.NoBrush:
                continue
            painter.save()
            try:
                painter.setClipPath(visible, QtCore.Qt.ClipOperation.IntersectClip)
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
                    stroker = QtGui.QPainterPathStroker(pen)
                    stroker.setWidth(pen.widthF() if pen.widthF() > 0 else 1)
                    outline = stroker.createStroke(painter.worldTransform().map(path))
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
