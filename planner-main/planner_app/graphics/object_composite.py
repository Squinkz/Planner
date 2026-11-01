"""Replay physical artwork with transparent, occluding background silhouettes."""
import math
from planner_app.geometry.path_operations import ClipPathCoverage
from planner_app.graphics.path_operations import Paths
from planner_app.geometry.spatial_index import BoundsIndex
from PySide6 import QtCore, QtGui, QtSvg
from .furnishing_mask import BackgroundPathDevice, BackgroundPathEngine


class ObjectPaintEngine(BackgroundPathEngine):
    def __init__(self, background):
        super().__init__()
        self.background = QtGui.QColor(background)
        self.commands = []
        self.captureBackground = True
        self.clip = None
        self.clipDirty = True

    def updateState(self, state):
        super().updateState(state)
        flags = QtGui.QPaintEngine.DirtyFlag
        if state.state() & (flags.DirtyClipPath | flags.DirtyClipRegion | flags.DirtyClipEnabled):
            self.clipDirty = True

    def drawPath(self, path):
        painter = self.painter()
        if self.clipDirty:
            # QPainter retains clipping in device coordinates across transform
            # changes. Reading clipPath recombines all nested masks, so do it
            # only when the clip state changes, not for every SVG stroke.
            self.clip = self.transform.map(painter.clipPath()) if painter.hasClipping() else None
            self.clipDirty = False
        clip = self.clip
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
        if clip is not None and not mask.isEmpty() and not clip.contains(mask.controlPointRect().adjusted(-.001, -.001, .001, .001)):
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
        if self.clipDirty:
            self.clip = self.transform.map(painter.clipPath()) if painter.hasClipping() else None
            self.clipDirty = False
        clip = self.clip
        self.commands.append(((QtCore.QRectF(rect), QtGui.QImage(image), QtCore.QRectF(source)),
                              QtGui.QPen(), QtGui.QBrush(), QtGui.QTransform(self.transform), self.opacity,
                              clip, QtGui.QPainterPath(), painter.renderHints(), painter.brushOrigin()))

    def Replay(self, painter, rect, clipCache = None):
        bakeStrokes = isinstance(painter.device(), QtSvg.QSvgGenerator)
        outerClip = painter.clipPath() if bakeStrokes and painter.hasClipping() else None
        geometry = []
        inkGeometry = []
        commandClips = []
        for command in self.commands:
            path, pen, brush, transform, opacity, clip, mask, hints, brushOrigin = command
            bounds = transform.mapRect(path[0]) if isinstance(path, tuple) else transform.map(path).boundingRect()
            margin = 1.0
            if pen.style() != QtCore.Qt.PenStyle.NoPen:
                width = pen.widthF() or 1.0
                scale = (1.0 if pen.isCosmetic() else math.sqrt(transform.m11() ** 2 + transform.m12() ** 2
                         + transform.m21() ** 2 + transform.m22() ** 2))
                margin += width * scale / 2
            inkMargin = margin * max(1, pen.miterLimit())
            inkBounds = bounds.adjusted(-inkMargin, -inkMargin, inkMargin, inkMargin)
            # Imported SVGs inherit the whole plan's passage mask. Most small
            # strokes are wholly inside its clear interior, so retaining that
            # mask merely duplicates a complex clip in every output layer.
            capturedClip = clip if clip is not None and not clip.contains(inkBounds) else None
            outer = outerClip if outerClip is not None and not outerClip.contains(inkBounds) else None
            commandClips.append((capturedClip, outer))
            bounds = bounds.adjusted(-margin, -margin, margin, margin).intersected(rect)
            geometry.append(((bounds.x(), bounds.y(), bounds.width(), bounds.height()), mask))
            hasInk = pen.style() != QtCore.Qt.PenStyle.NoPen or brush.style() != QtCore.Qt.BrushStyle.NoBrush
            inkGeometry.append((hasInk, path, transform, pen.widthF(), pen.isCosmetic(), pen.capStyle(), pen.joinStyle(),
                                pen.miterLimit(), tuple(pen.dashPattern()), pen.dashOffset()) if hasInk and brush.style() == QtCore.Qt.BrushStyle.NoBrush
                               and not isinstance(path, tuple) else (hasInk,))
        # These clips depend on ordered bounds and background silhouettes, not
        # paint colors. Reuse native booleans across recolors, checking every
        # input so moved/resized/reordered objects still invalidate immediately.
        clips = (clipCache.get("clips") if clipCache is not None and clipCache.get("geometry") == geometry
                 and clipCache.get("inkGeometry") == inkGeometry else None)
        if clips is None:
            covered = []
            coveredIndex = BoundsIndex(max(rect.width(), rect.height()) / max(1, math.sqrt(len(self.commands))))
            clips = []
            for command, (boundsValues, mask) in zip(reversed(self.commands), reversed(geometry)):
                bounds = QtCore.QRectF(*boundsValues)
                origin = bounds.center()
                localCanvas = QtGui.QPainterPath()
                localCanvas.addRect(bounds.translated(-origin))
                # Background-only commands occlude earlier ink but emit none.
                # Their visible region is never painted, so do not union all
                # later furnishings just to discard that result during replay.
                if command[1].style() == QtCore.Qt.PenStyle.NoPen and command[2].style() == QtCore.Qt.BrushStyle.NoBrush:
                    clips.append(QtGui.QPainterPath())
                    if not mask.isEmpty():
                        maskBounds = mask.boundingRect()
                        coveredIndex.Insert((maskBounds.left(), maskBounds.top(), maskBounds.right(), maskBounds.bottom()), len(covered))
                        covered.append((mask, maskBounds))
                    continue
                masks = []
                for index in coveredIndex.Query((bounds.left(), bounds.top(), bounds.right(), bounds.bottom())):
                    background, backgroundBounds = covered[index]
                    localMask = background.translated(-origin)
                    # Bounding rectangles for walls and hollow furnishings can
                    # cover most of a room. Reject their empty interior before
                    # combining unrelated contours with the real occluders.
                    if localMask.intersects(localCanvas):
                        masks.append(localMask)
                if len(masks) > 16 and command[2].style() == QtCore.Qt.BrushStyle.NoBrush and not isinstance(command[0], tuple):
                    # A combined counter/wall outline can span the entire plan.
                    # Its empty middle does not need hundreds of furniture masks.
                    # Use a conservative ink envelope, including two device units
                    # of antialias padding, without changing the masks themselves.
                    path, pen, brush, transform = command[:4]
                    stroke = Paths.PreparePenStroke(pen, width = pen.widthF() or 1.0)
                    ink = stroke(transform.map(path)) if pen.isCosmetic() else transform.map(stroke(path))
                    envelope = QtGui.QPainterPathStroker()
                    envelope.setWidth(4)
                    ink = Paths.Union(ink, envelope.createStroke(ink)).translated(-origin)
                    masks = [mask for mask in masks if mask.intersects(ink)]
                # Intersect captured doorway clips separately during painting;
                # merging them here can invert holes at a cropped wall edge.
                # A command's own bounds already contain all its ink. With no
                # later occluders, clipping to those bounds does nothing, but
                # emits a different SVG mask for every stroke and forces Qt to
                # create thousands of independent preview renderers.
                visible = ClipPathCoverage(Paths, localCanvas, masks) if masks else None
                clips.append(visible.translated(origin) if visible is not None else None)
                if not mask.isEmpty():
                    maskBounds = mask.boundingRect()
                    coveredIndex.Insert((maskBounds.left(), maskBounds.top(), maskBounds.right(), maskBounds.bottom()), len(covered))
                    covered.append((mask, maskBounds))
            if clipCache is not None:
                clipCache.clear()
                elementCount = (sum(path.elementCount() for path in clips if path is not None) + sum(mask.elementCount() for bounds, mask in geometry)
                                + sum(ink[1].elementCount() for ink in inkGeometry if len(ink) > 1))
                if len(geometry) <= 8192 and elementCount <= 262144:
                    clipCache.update(geometry = geometry, inkGeometry = inkGeometry, clips = clips)
        for command, visible, (capturedClip, outer) in zip(self.commands, reversed(clips), commandClips):
            path, pen, brush, transform, opacity, clip, mask, hints, brushOrigin = command
            if pen.style() == QtCore.Qt.PenStyle.NoPen and brush.style() == QtCore.Qt.BrushStyle.NoBrush:
                continue
            painter.save()
            try:
                if bakeStrokes:
                    combinedClip = visible
                    for candidate in (capturedClip, outer):
                        if candidate is not None:
                            combinedClip = candidate if combinedClip is None else Paths.Intersection(combinedClip, candidate)
                    if combinedClip is not None:
                        # Qt's SVG engine can allocate enormous intermediates
                        # when accumulating nested complex clips. Resolve their
                        # geometry once and submit a single replacement mask.
                        painter.setClipping(False)
                        painter.setClipPath(combinedClip, QtCore.Qt.ClipOperation.ReplaceClip)
                else:
                    if visible is not None:
                        painter.setClipPath(visible, QtCore.Qt.ClipOperation.IntersectClip)
                    if capturedClip is not None:
                        painter.setClipPath(capturedClip, QtCore.Qt.ClipOperation.IntersectClip)
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
