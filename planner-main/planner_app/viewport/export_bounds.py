"""Raster/vector export previews, crop guides and read-only mouse gestures."""
from planner_app.graphics.text import PathTextPainter
import math
from datetime import date
from PySide6 import QtCore, QtGui
from planner_app.export_bounds import AutomaticBounds
from planner_app.print_layout import ConstrainPrintBounds, PrintPaperGeometry
from planner_app.export_crop import MoveCropOrigin, MoveCropEdge, HitCropEdge, HitCropRuler
from planner_app.graphics.palette import themeColors
from planner_app.graphics import palette
from planner_app.graphics.compositing import DrawVignette, DrawNormalTexture
from planner_app.graphics.svg_preview import SvgPreviewRenderer
from planner_app.graphics.export_border import DrawExportBorder, DrawRulerZones
from planner_app.export_settings import ExportPixelSize
from planner_app.graphics.title_block import DrawTitleBlock, TitleBlockLayout, RenderTitleBlockBitmap
from planner_app.graphics.scale_bar import DrawScaleBar, ScaleBarLayout
from planner_app.graphics.preview_bitmap import PictureBitmap, DrawPictureTiles
from .print_pages import PrintPagesMixin


class ExportBoundsOverlay(PrintPagesMixin, QtCore.QObject):
    boundsChanged = QtCore.Signal(object)
    originChanged = QtCore.Signal(object)
    pageOriginChanged = QtCore.Signal(object)
    pageDragStarted = QtCore.Signal()
    pageDragFinished = QtCore.Signal()

    def __init__(self, viewport):
        super().__init__(viewport)
        self.viewport = viewport
        self.active = False
        self.bounds = None
        self.autoBounds = None
        self.modelBoundsKey = self.modelBounds = None
        self.dragEdge = None
        self.dragRuler = None
        self.dragOffset = 0.0
        self.pageDragBoundary = 0.0
        self.hoverPosition = None
        self.scale = 100.0
        self.rasterDensity = 1.0
        self.snapshotFurnishingKey = self.snapshotFurnishingRenderers = None
        self.outputFormat = "png"
        self.renderVector = None
        self.vectorSceneOnly = False
        self.svgClipCache = {}
        self.colorAppearanceRevisions = 0
        self.svgColorKey = None
        self.svgRenderer = None
        self.svgData = None
        self.vectorBounds = None
        self.svgKey = None
        self.svgFamilyKey = None
        self.svgAlternate = None
        self.svgNavigationImage = None
        self.svgViewImage = None
        self.svgViewKey = None
        self.navigationTimer = QtCore.QTimer(self)
        self.navigationTimer.setSingleShot(True)
        self.navigationTimer.setInterval(180)
        self.navigationTimer.timeout.connect(viewport.update)
        self.printPreviewTimer = QtCore.QTimer(self)
        self.printPreviewTimer.setSingleShot(True)
        self.printPreviewTimer.setInterval(180)
        self.printPreviewTimer.timeout.connect(viewport.update)
        self.snapshot = None
        self.snapshotKey = None
        self.snapshotBounds = None
        self.snapshotViewport = None
        self.snapshotSampling = 1.0
        self.detailImage = self.detailBounds = self.detailKey = None
        self.previewError = ""
        self.previewPending = False
        self.previewProcess = None
        self.failedBounds = None
        self.drawRuler = False
        self.borderStyle = "Ruler + Reference Zones"
        self.borderSize = 56
        self.vignetteStrength = 0
        self.texture = None
        self.textureAngle = 0
        self.textureSettings = {}
        self.titleBlock = {}
        self.scaleBar = {}
        self.titleBlockDpi = 300
        self.architecturalScale = None
        self.printMode = False
        self.printSettings = {}
        self.pageOrigin = (0, 0)
        self.dragPage = None
        self.previewGesture = False
        self.compositeGesture = False
        self.pageDragOffset = 0
        self.printPageCache = {}
        self.printPageNumbers = {}
        self.printPageSampling = {}
        self.printPageDataBytes = {}
        self.printPageImages = {}
        self.printDragImages = {}
        self.printDragKey = None
        self.printRenderArguments = None
        self.printRenderKey = None
        self.printSceneCache = None
        self.printPageKey = None
        self.renderPrintPage = None
        self.renderPrintScene = None
        self.printVectorRenderer = self.printVectorKey = self.printVectorBounds = None
        self.printVectorColorKey = None
        self.printVectorBytes = 0
        self.titleBlockPicture = self.titleBlockKey = None
        self.titleBlockImage = self.titleBlockImageKey = None
        self.scaleBarImage = self.scaleBarImageKey = self.scaleBarImageRect = None
        self.rulerKey = None
        self.rulerPicture = self.rulerPictureKey = None
        self.rulerStrips = []
        viewport.installEventFilter(self)

    def SetActive(self, active, bounds = None):
        if self.previewProcess is not None:
            self.previewProcess.Close()
        self.ClearPrintPreview()
        self.ClearPrintVectors()
        if self.printSceneCache is not None:
            self.printSceneCache.Clear()
        if self.dragPage is not None:
            self.pageDragFinished.emit()
        self.svgClipCache.clear()
        self.colorAppearanceRevisions = 0
        self.svgColorKey = None
        self.active = active
        self.scaleBarImage = self.scaleBarImageKey = self.scaleBarImageRect = None
        self.titleBlockPicture = self.titleBlockKey = None
        self.titleBlockImage = self.titleBlockImageKey = None
        if self.svgRenderer is not None:
            self.svgRenderer.deleteLater()
        if self.svgAlternate is not None:
            self.svgAlternate[2].deleteLater()
            self.svgAlternate = None
        self.svgFamilyKey = None
        self.svgRenderer = self.svgData = self.svgKey = None
        self.vectorBounds = None
        self.svgNavigationImage = self.svgViewImage = self.svgViewKey = None
        self.navigationTimer.stop()
        self.printPreviewTimer.stop()
        self.previewError = ""
        self.snapshot = self.snapshotKey = self.snapshotBounds = None
        self.detailImage = self.detailBounds = self.detailKey = None
        self.failedBounds = None
        self.rulerKey = None
        self.rulerPicture = self.rulerPictureKey = None
        self.rulerStrips = []
        self.dragEdge = self.hoverPosition = None
        self.dragRuler = None
        self.dragPage = None
        v = self.viewport
        self.pageDragBoundary = 0.0
        for name in ("background", "scene", "pan"):
            v.rasterCacheBudget.Clear(name, "export-transition")
        v.isPanning = False
        if active:
            v.CancelInteraction()
            if v.guiDragActive:
                v.CancelGuiDrag()
            v.SetSelection([])
            v.hoverPosition = v.lastInteractionPosition = None
            v.objectContextMenu.hide()
            try:
                self.autoBounds = self.AutomaticModelBounds()
            except ValueError:
                # An empty canvas still offers a useful two-meter crop at the origin.
                self.autoBounds = (-1000.0, -1000.0, 2000.0, 2000.0)
            self.bounds = self.ConstrainTitleBlockBounds(tuple(bounds) if bounds is not None else self.autoBounds)
        self.UpdateCursor()
        v.update()

    def AutomaticModelBounds(self):
        v = self.viewport
        key = v.SceneRenderKey((v.sceneRevision, v.font().toString(), v.unitsMode, id(v.furnishingRenderers)))
        if key != self.modelBoundsKey:
            # Bounds include rendered opening symbols and furnishing artwork.
            # Keep only the result, never native paths or object references.
            self.modelBoundsKey = None
            self.modelBounds = AutomaticBounds(v)
            self.modelBoundsKey = key
        return self.modelBounds

    def StartVectorNavigation(self):
        if self.active and (self.outputFormat == "svg" or self.snapshotSampling < 1):
            self.navigationTimer.start()

    def HitEdge(self, position):
        v = self.viewport
        if position is None or not v.DrawingRect().contains(position) or self.bounds is None:
            return None
        x, y, width, height = self.bounds
        first = v.WorldToViewport(QtCore.QPointF(x, y))
        second = v.WorldToViewport(QtCore.QPointF(x + width, y + height))
        return HitCropEdge((position.x(), position.y()), (first.x(), first.y()), (second.x(), second.y()))

    def HitRuler(self, position):
        v = self.viewport
        if position is None:
            return None
        if 0 <= position.y() < v.rulerSize and v.rulerSize <= position.x() < v.width():
            return 0
        if 0 <= position.x() < v.rulerSize and v.rulerSize <= position.y() < v.height():
            return 1
        if self.bounds is None or self.borderStyle not in ("Ruler", "Marked", "Ruler + Reference Zones") or not v.DrawingRect().contains(position):
            return None
        if self.HitEdge(position) is not None:
            return None
        if self.printMode:
            if self.HitPrintGuide(position) is not None:
                return None
            try:
                layout = self.PrintLayout()
            except ValueError:
                return None
            world = v.ViewportToWorld(position)
            width, height = layout["paperTile"]
            stepX, stepY = layout["paperStride"]
            x = self.pageOrigin[0] + math.floor((world.x() - self.pageOrigin[0]) / stepX) * stepX
            y = self.pageOrigin[1] + math.floor((world.y() - self.pageOrigin[1]) / stepY) * stepY
            # Only complete selected sheets draw page rulers. Test the sheet
            # under the pointer rather than traversing the entire page lattice.
            if not QtCore.QRectF(*self.bounds).adjusted(-.001, -.001, .001, .001).contains(QtCore.QRectF(x, y, width, height)):
                return None
            target = self.PrintPageRect((x, y, width, height))
            factor = target.width() / layout["baselinePixels"][0]
            crop = QtCore.QRectF(target.topLeft() + QtCore.QPointF(self.borderSize * factor, self.borderSize * factor),
                                QtCore.QSizeF(layout["drawingPixels"][0] * factor, layout["drawingPixels"][1] * factor))
            border = (self.borderSize // 2 if self.borderStyle == "Ruler + Reference Zones" else self.borderSize) * factor
            return HitCropRuler((position.x(), position.y()),
                                (crop.left(), crop.top(), crop.right(), crop.bottom()), border)
        x, y, width, height = self.bounds
        crop = QtCore.QRectF(v.WorldToViewport(QtCore.QPointF(x, y + height)),
                            v.WorldToViewport(QtCore.QPointF(x + width, y))).normalized()
        border = self.borderSize * v.basePixelsPerMillimeter * v.zoom / (self.scale / 1000)
        if self.borderStyle == "Ruler + Reference Zones":
            border = (self.borderSize // 2) * v.basePixelsPerMillimeter * v.zoom / (self.scale / 1000)
        return HitCropRuler((position.x(), position.y()),
                            (crop.left(), crop.top(), crop.right(), crop.bottom()), border)

    def MoveOrigin(self, axis, coordinate, modifiers = QtCore.Qt.KeyboardModifier.NoModifier):
        v = self.viewport
        step = v.GridSteps(self.scale / 1000)[1] if v.snapEnabled != bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier) else None
        origin = MoveCropOrigin(v.gridOrigin, axis, coordinate, step)
        if tuple(origin) != v.gridOrigin:
            self.originChanged.emit(origin)
            v.update()

    def UpdateCursor(self):
        edge = self.dragEdge if self.dragEdge is not None else self.HitEdge(self.hoverPosition)
        ruler = self.dragRuler if self.dragRuler is not None else self.HitRuler(self.hoverPosition)
        page = self.dragPage if self.dragPage is not None else self.HitPrintGuide(self.hoverPosition)
        if page is not None and self.dragEdge is None:
            edge = None
        shape = (QtCore.Qt.CursorShape.ClosedHandCursor if self.viewport.isPanning
                 else QtCore.Qt.CursorShape.SizeHorCursor if ruler == 0 or edge in (0, 1)
                 else QtCore.Qt.CursorShape.SizeVerCursor if ruler == 1 or edge in (2, 3)
                 else QtCore.Qt.CursorShape.SizeHorCursor if page == 0
                 else QtCore.Qt.CursorShape.SizeVerCursor if page == 1
                 else QtCore.Qt.CursorShape.ArrowCursor)
        self.viewport.setCursor(shape)

    def ConstrainTitleBlockBounds(self, bounds, edge = None):
        if self.printMode:
            return ConstrainPrintBounds(bounds, self.printSettings, self.pageOrigin, edge)
        if bounds is None or not (self.titleBlock.get("enabled", False) or self.scaleBar.get("enabled", False)):
            return bounds
        minimumWidth = minimumHeight = 1
        if self.titleBlock.get("enabled", False):
            width, height, block = TitleBlockLayout(1, 1, self.titleBlock, self.scale,
                                                    self.architecturalScale, self.outputFormat, self.titleBlockDpi)
            border = 2 * self.borderSize if self.drawRuler else 0
            minimumWidth, minimumHeight = max(1, block[2] - border), max(1, block[3] - border)
        if self.scaleBar.get("enabled", False):
            layout = ScaleBarLayout(QtCore.QRectF(0, 0, 1000000, 1000000), self.scaleBar, self.scale,
                                    self.viewport.unitsMode, self.viewport.font(), measurementTextSize = self.viewport.measurementTextSize)
            minimumWidth = max(minimumWidth, math.ceil(layout["minimum"].width()))
            minimumHeight = max(minimumHeight, math.ceil(layout["minimum"].height()))
        minimumWidth *= 1000 / self.scale
        minimumHeight *= 1000 / self.scale
        x, y, width, height = bounds
        if width < minimumWidth:
            if edge == 0:
                x -= minimumWidth - width
            width = minimumWidth
        if height < minimumHeight:
            if edge == 2:
                y -= minimumHeight - height
            height = minimumHeight
        return x, y, width, height

    def MoveEdge(self, edge, coordinate, reset = False, modifiers = QtCore.Qt.KeyboardModifier.NoModifier):
        v = self.viewport
        step = v.GridSteps(self.scale / 1000)[1] if not reset and v.snapEnabled != bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier) else None
        if step is not None and self.printMode and self.dragEdge == edge:
            axis = 0 if edge < 2 else 1
            coordinate = v.gridOrigin[axis] + MoveCropOrigin((0, 0), axis, coordinate - v.gridOrigin[axis], step)[axis]
        bounds = MoveCropEdge(self.bounds, edge, coordinate, reset, step, v.gridOrigin[0 if edge < 2 else 1])
        bounds = self.ConstrainTitleBlockBounds(bounds, edge)
        if self.printMode and not reset and self.dragEdge == edge:
            pageBounds = self.ConstrainTitleBlockBounds(MoveCropEdge(self.bounds, edge, coordinate), edge)
            axis = 0 if edge < 2 else 1
            boundary = pageBounds[axis] + (pageBounds[axis + 2] if edge % 2 else 0)
            displacement = coordinate - boundary
            if displacement * (1 if edge % 2 == 0 else -1) > 1e-8:
                # Finish shrinking to the last complete page first. The page
                # origin handler then translates this crop and the lattice as
                # one edit. Reversing outward naturally resumes crop resizing.
                self.bounds = pageBounds
                origin = list(self.pageOrigin)
                origin[axis] += displacement
                self.pageOrigin = tuple(origin)
                self.pageOriginChanged.emit(self.pageOrigin)
                v.update()
                return
            dimension = PrintPaperGeometry(self.printSettings)[0][axis]
            pageIndex = (boundary - self.pageOrigin[axis]) / dimension
            if (abs(displacement) < 1e-8 and pageBounds[axis + 2] < dimension * 2 - 1e-8
                    and abs(pageIndex - round(pageIndex)) < 1e-9):
                # A release/modifier event at the contact point must not snap
                # the handle off the page just pushed to a non-grid position.
                bounds = pageBounds
        if bounds != self.bounds:
            self.bounds = bounds
            self.boundsChanged.emit(bounds)
            self.viewport.update()

    def eventFilter(self, watched, event):
        if not self.active:
            return False
        v = self.viewport
        eventType = event.type()
        if (eventType in (QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease)
                and event.key() == QtCore.Qt.Key.Key_Alt and (self.dragEdge is not None or self.dragRuler is not None or self.dragPage is not None) and self.hoverPosition is not None):
            modifiers = (event.modifiers() | QtCore.Qt.KeyboardModifier.AltModifier if eventType == QtCore.QEvent.Type.KeyPress
                         else event.modifiers() & ~QtCore.Qt.KeyboardModifier.AltModifier)
            world = v.ViewportToWorld(self.hoverPosition)
            if self.dragPage is not None:
                self.MovePrintOrigin(self.hoverPosition, modifiers)
            elif self.dragRuler is not None:
                coordinate = world.x() if self.dragRuler == 0 else world.y()
                self.MoveOrigin(self.dragRuler, coordinate - self.dragOffset, modifiers)
            else:
                coordinate = world.x() if self.dragEdge < 2 else world.y()
                self.MoveEdge(self.dragEdge, coordinate - self.dragOffset, modifiers = modifiers)
            self.dragMoved = True
            event.accept()
            return True
        if eventType in (QtCore.QEvent.Type.DragEnter, QtCore.QEvent.Type.DragMove, QtCore.QEvent.Type.Drop):
            event.ignore()
            return True
        if eventType == QtCore.QEvent.Type.Leave:
            self.hoverPosition = None
            self.UpdateCursor()
            v.update()
            return True
        if eventType not in (QtCore.QEvent.Type.MouseButtonPress, QtCore.QEvent.Type.MouseButtonRelease,
                             QtCore.QEvent.Type.MouseButtonDblClick, QtCore.QEvent.Type.MouseMove):
            return False
        position = event.position()
        self.hoverPosition = position
        if self.printMode:
            if eventType == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.LeftButton:
                page = self.HitPrintGuide(position)
                if page is not None:
                    v.setFocus()
                    self.pageDragStarted.emit()
                    self.dragPage = page
                    world = v.ViewportToWorld(position)
                    self.pageDragOffset = (world.x() if page == 0 else world.y()) - self.pageOrigin[page]
                    step = self.PrintLayout()["paperStride"][page]
                    self.pageDragBoundary = round(self.pageDragOffset / step) * step
                    self.UpdateCursor()
                    return True
            elif self.dragPage is not None and eventType in (QtCore.QEvent.Type.MouseMove, QtCore.QEvent.Type.MouseButtonRelease):
                self.MovePrintOrigin(position, event.modifiers())
                if eventType == QtCore.QEvent.Type.MouseButtonRelease:
                    self.dragPage = None
                    self.pageDragBoundary = 0.0
                    self.pageDragFinished.emit()
                self.UpdateCursor()
                return True
            elif eventType == QtCore.QEvent.Type.MouseButtonDblClick and event.button() == QtCore.Qt.MouseButton.LeftButton:
                page = self.HitPrintGuide(position)
                if page is not None:
                    origin = list(self.pageOrigin)
                    origin[page] = 0
                    self.dragPage = None
                    self.pageDragBoundary = 0.0
                    self.pageDragStarted.emit()
                    self.pageOrigin = tuple(origin)
                    self.pageOriginChanged.emit(tuple(origin))
                    self.pageDragFinished.emit()
                    v.update()
                    return True
        if eventType == QtCore.QEvent.Type.MouseButtonPress:
            v.setFocus()
            if event.button() == QtCore.Qt.MouseButton.MiddleButton:
                self.dragEdge = None
                self.dragRuler = None
                v.isPanning = True
                v.lastPanPosition = position
            elif event.button() == QtCore.Qt.MouseButton.LeftButton:
                self.dragRuler = self.HitRuler(position)
                self.dragEdge = self.HitEdge(position) if self.dragRuler is None else None
                self.dragMoved = False
                if self.dragRuler is not None:
                    world = v.ViewportToWorld(position)
                    coordinate = world.x() if self.dragRuler == 0 else world.y()
                    self.dragOffset = coordinate - v.gridOrigin[self.dragRuler]
                elif self.dragEdge is not None:
                    x, y, width, height = self.bounds
                    world = v.ViewportToWorld(position)
                    coordinate = world.x() if self.dragEdge < 2 else world.y()
                    self.dragOffset = coordinate - (x, x + width, y, y + height)[self.dragEdge]
        elif eventType == QtCore.QEvent.Type.MouseMove:
            if v.isPanning:
                if event.buttons() & QtCore.Qt.MouseButton.MiddleButton:
                    v.panOffset += position - v.lastPanPosition
                    v.lastPanPosition = position
                    self.StartVectorNavigation()
                else:
                    v.EndPan()
            elif self.dragRuler is not None:
                self.dragMoved = True
                world = v.ViewportToWorld(position)
                coordinate = world.x() if self.dragRuler == 0 else world.y()
                self.MoveOrigin(self.dragRuler, coordinate - self.dragOffset, event.modifiers())
            elif self.dragEdge is not None:
                self.dragMoved = True
                world = v.ViewportToWorld(position)
                coordinate = world.x() if self.dragEdge < 2 else world.y()
                self.MoveEdge(self.dragEdge, coordinate - self.dragOffset, modifiers = event.modifiers())
        elif eventType == QtCore.QEvent.Type.MouseButtonRelease:
            if event.button() == QtCore.Qt.MouseButton.MiddleButton:
                v.EndPan()
            elif event.button() == QtCore.Qt.MouseButton.LeftButton:
                if self.dragRuler is not None and self.dragMoved:
                    world = v.ViewportToWorld(position)
                    coordinate = world.x() if self.dragRuler == 0 else world.y()
                    self.MoveOrigin(self.dragRuler, coordinate - self.dragOffset, event.modifiers())
                elif self.dragEdge is not None and self.dragMoved:
                    world = v.ViewportToWorld(position)
                    coordinate = world.x() if self.dragEdge < 2 else world.y()
                    self.MoveEdge(self.dragEdge, coordinate - self.dragOffset, modifiers = event.modifiers())
                self.dragEdge = None
                self.dragRuler = None
        elif event.button() == QtCore.Qt.MouseButton.LeftButton:
            ruler = self.HitRuler(position)
            edge = self.HitEdge(position)
            self.dragEdge = None
            self.dragRuler = None
            self.dragMoved = False
            if ruler is not None:
                origin = list(v.gridOrigin)
                origin[ruler] = 0.0
                if tuple(origin) != v.gridOrigin:
                    self.originChanged.emit(origin)
            elif edge is not None:
                x, y, width, height = self.autoBounds
                self.MoveEdge(edge, (x, x + width, y, y + height)[edge], reset = True)
            elif v.DrawingRect().contains(position):
                # Match an export pixel/SVG unit to one physical screen pixel,
                # including Windows display scaling, without changing the crop.
                oldZoom = v.zoom
                v.zoom = self.scale / (1000 * v.basePixelsPerMillimeter * v.devicePixelRatioF())
                center = v.DrawingRect().center()
                v.panOffset = position - center - (position - center - v.panOffset) * (v.zoom / oldZoom)
                self.StartVectorNavigation()
        self.UpdateCursor()
        v.update()
        event.accept()
        return True

    def Draw(self, painter, drawingRect, shade = True, drawGuides = True):
        if not self.active or self.bounds is None:
            return
        x, y, width, height = self.bounds
        first = self.viewport.WorldToViewport(QtCore.QPointF(x, y))
        second = self.viewport.WorldToViewport(QtCore.QPointF(x + width, y + height))
        crop = QtCore.QRectF(first, second).normalized()
        painter.save()
        painter.setClipRect(drawingRect)
        outside = QtGui.QPainterPath()
        outside.addRect(drawingRect)
        outside.addRect(crop)
        outside.setFillRule(QtCore.Qt.FillRule.OddEvenFill)
        if shade:
            painter.fillPath(outside, QtGui.QColor(themeColors["exportOutsideShade"]))
        lines = (QtCore.QLineF(first.x(), drawingRect.top(), first.x(), drawingRect.bottom()),
                 QtCore.QLineF(second.x(), drawingRect.top(), second.x(), drawingRect.bottom()),
                 QtCore.QLineF(drawingRect.left(), first.y(), drawingRect.right(), first.y()),
                 QtCore.QLineF(drawingRect.left(), second.y(), drawingRect.right(), second.y()))
        hovered = self.dragEdge if self.dragEdge is not None else self.HitEdge(self.hoverPosition)
        # Crop guides are screen overlays. Use whole device-pixel strokes and
        # align their centres so fractional zoom/pan cannot change coverage.
        ratio = painter.device().devicePixelRatioF()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        for edge, line in enumerate(lines):
            strokeWidth = max(1, math.floor((2.5 if edge == hovered else 1.5) * ratio + .5))
            pixelOffset = .5 if strokeWidth % 2 else 0
            firstPoint, secondPoint = line.p1(), line.p2()
            for point in (firstPoint, secondPoint):
                point.setX((math.floor(point.x() * ratio) + pixelOffset) / ratio)
                point.setY((math.floor(point.y() * ratio) + pixelOffset) / ratio)
            line = QtCore.QLineF(firstPoint, secondPoint)
            pen = QtGui.QPen(QtGui.QColor(themeColors["selectionOutline"]), strokeWidth / ratio,
                            QtCore.Qt.PenStyle.DashLine)
            pen.setCapStyle(QtCore.Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            if drawGuides:
                painter.drawLine(line)
        painter.restore()

    def DrawPreview(self, painter, drawingRect):
        from planner_app.graphics import palette
        v = self.viewport
        self.previewPending = bool(self.previewProcess is not None and (self.previewProcess.current is not None or self.previewProcess.queue))
        if self.printMode:
            self.DrawPrintPreview(painter, drawingRect)
            return
        if self.printSceneCache is not None:
            self.printSceneCache.Clear()
        v.rasterCacheBudget.Clear("printPages", "mode-switch")
        # Viewing zoom/pan are intentionally absent: only export appearance and
        # scene changes invalidate the source bitmap.
        separatedColors = {"rulerBackground"}
        vectorColors = self.outputFormat == "svg" and self.vectorSceneOnly
        if vectorColors:
            separatedColors.update(("canvas", "objectOutline", "wallOutline", "grid"))
        sceneColors = tuple((name, color) for name, color in themeColors.items() if name not in separatedColors)
        colorAlpha = tuple(QtGui.QColor(themeColors[role]).alpha() for role in
                           ("canvas", "objectOutline", "wallOutline", "grid")) if vectorColors else None
        key = v.SceneRenderKey((self.scale, self.rasterDensity, v.viewportRasterByteLimit, v.font().toString(), palette.labelFont, sceneColors,
                                v.showGrid, tuple(v.gridIntensities.items()), v.gridOrigin, v.unitsMode, v.wallStyle,
                                tuple(v.collisionSettings.items()), tuple(v.stairStepSizes.items()),
                                tuple(v.railingSpacings.items()), tuple((kind, tuple(values.items())) for kind, values in v.imperialAutoSizes.items()), v.autoSizingUnitsMode,
                                colorAlpha, v.floors, v.solidRooms, v.solidObjects),
                               appearanceRevision = v.renderChanges.appearance - self.colorAppearanceRevisions if vectorColors else None)
        if self.outputFormat == "svg":
            v.rasterCacheBudget.Clear("detail", "format-switch")
            v.rasterCacheBudget.Clear("snapshot", "format-switch")
            self.DrawVectorPreview(painter, drawingRect, key)
            self.DrawTitleBlockPreview(painter, drawingRect)
            self.DrawScaleBarPreview(painter, drawingRect)
            self.DrawPrintGuides(painter, drawingRect)
            return
        v.rasterCacheBudget.Clear("navigation", "format-switch")
        v.rasterCacheBudget.Clear("vectorView", "format-switch")
        if self.svgRenderer is not None:
            self.svgRenderer.deleteLater()
            self.svgRenderer = self.svgData = self.svgKey = None
        if self.svgAlternate is not None:
            self.svgAlternate[2].deleteLater()
            self.svgAlternate = None
        self.svgFamilyKey = None
        requested = QtCore.QRectF(*self.PreviewBounds())
        coverage = QtCore.QRectF(*self.snapshotBounds) if self.snapshotBounds is not None else QtCore.QRectF()
        if (key != self.snapshotKey or not coverage.contains(requested)
                or self.snapshot is None and requested != self.failedBounds):
            try:
                auto = QtCore.QRectF(*self.AutomaticModelBounds())
            except ValueError:
                auto = QtCore.QRectF(*self.autoBounds)
            coverage = auto.united(requested)
            if key == self.snapshotKey:
                coverage = coverage.united(QtCore.QRectF(*self.snapshotBounds))
            # Leave room for ordinary crop adjustments without regenerating on
            # every mouse move when a guide passes the current capture edge.
            coverage = coverage.adjusted(-1000, -1000, 1000, 1000)
            pixelsPerMillimeter = self.scale / 1000
            width, height = math.ceil(coverage.width() * pixelsPerMillimeter), math.ceil(coverage.height() * pixelsPerMillimeter)
            if (width > 32767 or height > 32767 or width * height > 100_000_000
                    or width * height * 4 > v.viewportRasterByteLimit):
                # A tight custom crop can still be previewed at native scale
                # when capturing the whole plan would exceed the bitmap limit.
                coverage = requested
            self.BuildSnapshot(coverage)
            self.failedBounds = QtCore.QRectF(requested) if self.snapshot is None else None
            self.snapshotKey = key
        painter.fillRect(v.rect(), QtGui.QColor(themeColors["canvas"]))
        origin = v.WorldToViewport(QtCore.QPointF())
        displayScale = v.basePixelsPerMillimeter * v.zoom
        rulerUnit = v.DrawGridBackground(painter, drawingRect, origin, displayScale, drawGrid = False)
        painter.save()
        painter.setClipRect(drawingRect)
        if self.drawRuler and not self.printMode:
            x, y, width, height = self.bounds
            cropFirst = v.WorldToViewport(QtCore.QPointF(x, y + height))
            cropSecond = v.WorldToViewport(QtCore.QPointF(x + width, y))
            painter.setClipRect(QtCore.QRectF(cropFirst, cropSecond), QtCore.Qt.ClipOperation.IntersectClip)
        if self.snapshot is not None:
            x, y, width, height = self.snapshotBounds
            first = v.WorldToViewport(QtCore.QPointF(x, y + height))
            second = v.WorldToViewport(QtCore.QPointF(x + width, y))
            painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawImage(QtCore.QRectF(first, second), self.snapshot)
            if self.snapshotSampling < self.rasterDensity:
                self.DrawRasterDetail(painter, drawingRect, key)
        painter.restore()
        self.Draw(painter, drawingRect, drawGuides = False)
        if self.drawRuler and self.snapshot is not None and not self.printMode:
            self.DrawCropRulers(painter, drawingRect)
        self.DrawTitleBlockPreview(painter, drawingRect)
        self.DrawScaleBarPreview(painter, drawingRect)
        compositeError = ""
        if self.snapshot is not None and not self.printMode and (self.vignetteStrength > 0 or self.texture is not None):
            x, y, width, height = self.bounds
            pixelsPerMillimeter = self.scale / 1000
            factor = displayScale / pixelsPerMillimeter
            border = self.borderSize if self.drawRuler else 0
            imageWidth = max(1, math.ceil(round(width * pixelsPerMillimeter, 8))) + 2 * border
            imageHeight = max(1, math.ceil(round(height * pixelsPerMillimeter, 8))) + 2 * border
            imageWidth, imageHeight, block = TitleBlockLayout(imageWidth, imageHeight, self.titleBlock, self.scale,
                                                              self.architecturalScale, self.outputFormat, self.titleBlockDpi)
            first = v.WorldToViewport(QtCore.QPointF(x, y + height)) - QtCore.QPointF(border * factor, border * factor)
            frame = QtCore.QRectF(first, QtCore.QSizeF(imageWidth * factor, imageHeight * factor))
            painter.save()
            try:
                painter.setClipRect(drawingRect)
                DrawNormalTexture(painter, frame, self.texture, self.textureAngle, (imageWidth, imageHeight), **self.textureSettings)
                DrawVignette(painter, frame, self.vignetteStrength, (imageWidth, imageHeight))
            except (OSError, ValueError) as error:
                compositeError = str(error)
            finally:
                painter.restore()
        self.DrawPrintGuides(painter, drawingRect)
        self.Draw(painter, drawingRect, shade = False)
        v.DrawRulerFrame(painter, rulerUnit)
        if self.previewError or compositeError:
            painter.save()
            painter.setPen(QtGui.QColor(themeColors["rulerText"]))
            painter.setFont(v.font())
            painter.drawText(drawingRect.adjusted(20, 20, -20, -20),
                             QtCore.Qt.AlignmentFlag.AlignCenter | QtCore.Qt.TextFlag.TextWordWrap, self.previewError or compositeError)
            painter.restore()

    def DrawScaleBarPreview(self, painter, drawingRect):
        if self.printMode or not self.scaleBar.get("enabled", False):
            self.viewport.rasterCacheBudget.Clear("scaleBar", "disabled")
            return
        v = self.viewport
        x, y, width, height = self.bounds
        factor = v.basePixelsPerMillimeter * v.zoom / (self.scale / 1000)
        first = v.WorldToViewport(QtCore.QPointF(x, y + height))
        painter.save()
        try:
            painter.setClipRect(drawingRect)
            painter.translate(first)
            painter.scale(factor, factor)
            painter.setFont(v.font())
            self.DrawScaleBarDecoration(painter, QtCore.QRectF(0, 0, width * self.scale / 1000, height * self.scale / 1000), self.bounds)
        finally:
            painter.restore()

    def DrawScaleBarDecoration(self, painter, plot, bounds):
        v = self.viewport
        if not self.scaleBar.get("enabled", False) or self.outputFormat == "svg":
            v.rasterCacheBudget.Clear("scaleBar", "disabled-or-vector")
            DrawScaleBar(painter, plot, self.scaleBar, self.scale, v.unitsMode, bounds, v.gridOrigin, v.measurementTextSize)
            return
        key = (tuple(bounds), plot, repr(self.scaleBar), self.scale, v.unitsMode, v.gridOrigin, v.measurementTextSize,
               painter.font().toString(), self.rasterDensity, themeColors["objectOutline"], themeColors["canvas"])
        if self.scaleBarImage is None or key != self.scaleBarImageKey:
            v.rasterCacheBudget.Clear("scaleBar", "replacement")
            layout = ScaleBarLayout(plot, self.scaleBar, self.scale, v.unitsMode, painter.font(), bounds, v.gridOrigin, v.measurementTextSize)
            picture = QtGui.QPicture()
            with PathTextPainter(picture) as source:
                source.setFont(painter.font())
                DrawScaleBar(source, plot, self.scaleBar, self.scale, v.unitsMode, bounds, v.gridOrigin, v.measurementTextSize)
            rect = layout["rect"]
            width, height = (math.ceil(value * self.rasterDensity) + 2 for value in (rect.width(), rect.height()))
            if max(width, height) <= 32767 and v.rasterCacheBudget.Prepare("scaleBar", width * height * 4,
                    preserve = ("snapshot", "detail", "printPages", "titleBlock", "rulers")):
                self.scaleBarImageRect, self.scaleBarImage = PictureBitmap(picture, rect, self.rasterDensity)
                self.scaleBarImageKey = key
            else:
                DrawPictureTiles(painter, picture, rect, self.rasterDensity)
                return
        painter.save()
        painter.setClipRect(plot, QtCore.Qt.ClipOperation.IntersectClip)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(self.scaleBarImageRect, self.scaleBarImage)
        painter.restore()

    def DrawTitleBlockPreview(self, painter, drawingRect):
        if self.printMode or not self.titleBlock.get("enabled", False):
            self.titleBlockPicture = self.titleBlockKey = None
            self.viewport.rasterCacheBudget.Clear("titleBlock", "disabled")
            return
        border = self.borderSize if self.drawRuler else 0
        width, height = ExportPixelSize(self.bounds, self.scale, border)
        key = (width, height, tuple(sorted(self.titleBlock.items())), self.scale,
               self.architecturalScale, self.outputFormat, self.titleBlockDpi, date.today(),
               tuple(themeColors[role] for role in ("canvas", "objectOutline", "rulerMajorTick", "rulerMinorTick")))
        if key != self.titleBlockKey:
            self.titleBlockLayout = TitleBlockLayout(width, height, self.titleBlock, self.scale,
                                                      self.architecturalScale, self.outputFormat, self.titleBlockDpi)
            outputWidth, outputHeight, block = self.titleBlockLayout
            picture = None
            if self.outputFormat == "svg":
                picture = QtGui.QPicture()
                with PathTextPainter(picture) as blockPainter:
                    DrawTitleBlock(blockPainter, block, self.titleBlock, self.scale,
                                   self.architecturalScale, self.outputFormat, self.titleBlockDpi)
            self.titleBlockPicture, self.titleBlockKey = picture, key
        outputWidth, outputHeight, block = self.titleBlockLayout
        v = self.viewport
        if self.outputFormat == "png":
            imageKey = (block[2:], *key[2:], self.rasterDensity, v.viewportRasterByteLimit)
            if self.titleBlockImage is None or self.titleBlockImageKey != imageKey:
                v.rasterCacheBudget.Clear("titleBlock", "replacement")
                snapshotBytes = self.snapshot.sizeInBytes() if self.snapshot is not None else 0
                available = max(0, min(v.viewportRasterByteLimit // 4, v.viewportRasterByteLimit - snapshotBytes))
                sampling = min(self.rasterDensity, 32767 / block[2], 32767 / block[3],
                               math.sqrt(available / (4 * block[2] * block[3])))
                imageWidth = max(1, math.floor(block[2] * sampling))
                imageHeight = max(1, math.floor(block[3] * sampling))
                if v.rasterCacheBudget.Prepare("titleBlock", imageWidth * imageHeight * 4, preserve = ("snapshot",)):
                    image = RenderTitleBlockBitmap(block, self.titleBlock, self.scale, self.architecturalScale,
                                                    pixelSize = (imageWidth, imageHeight), dpi = self.titleBlockDpi)
                    self.titleBlockImage, self.titleBlockImageKey = image, imageKey
        else:
            v.rasterCacheBudget.Clear("titleBlock", "format-switch")
        x, y, worldWidth, worldHeight = self.bounds
        factor = v.basePixelsPerMillimeter * v.zoom / (self.scale / 1000)
        first = v.WorldToViewport(QtCore.QPointF(x, y + worldHeight)) - QtCore.QPointF(border * factor, border * factor)
        painter.save()
        try:
            painter.setClipRect(drawingRect)
            painter.translate(first)
            painter.scale(factor, factor)
            # Match the extra background area for exports below the minimum size.
            if outputWidth > width:
                painter.fillRect(QtCore.QRectF(width, 0, outputWidth - width, height), QtGui.QColor(themeColors["canvas"]))
            if outputHeight > height:
                painter.fillRect(QtCore.QRectF(0, height, width, outputHeight - height), QtGui.QColor(themeColors["canvas"]))
            if self.outputFormat == "png":
                if self.titleBlockImage is not None:
                    painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
                    painter.drawImage(QtCore.QRectF(*block), self.titleBlockImage)
            else:
                painter.drawPicture(QtCore.QPointF(), self.titleBlockPicture)
        finally:
            painter.restore()

    def DrawVectorPreview(self, painter, drawingRect, sceneKey):
        v = self.viewport
        if self.vectorSceneOnly:
            requested = QtCore.QRectF(*self.PreviewBounds())
            coverage = QtCore.QRectF(*self.vectorBounds) if self.vectorBounds is not None else QtCore.QRectF()
            if not coverage.contains(requested):
                try:
                    coverage = coverage.united(QtCore.QRectF(*self.AutomaticModelBounds()))
                except ValueError:
                    pass
                coverage = coverage.united(requested).adjusted(-1000, -1000, 1000, 1000)
                self.vectorBounds = (coverage.x(), coverage.y(), coverage.width(), coverage.height())
            key = (sceneKey, self.vectorBounds)
        else:
            key = (sceneKey, self.PreviewBounds(), self.printMode, self.drawRuler, self.borderStyle, self.borderSize,
                   themeColors["rulerBackground"])
        colorKey = tuple(themeColors[role] for role in ("canvas", "objectOutline", "wallOutline", "grid"))
        geometryChanged = key != self.svgKey
        familyKey = ((sceneKey[0][:-1],) + sceneKey[1:],) + key[1:] if self.vectorSceneOnly else None
        preparedData = None
        pending = False
        from planner_app.export_preview import PreviewProcess
        worker = PreviewProcess(self)
        if worker is not None and geometryChanged and not (self.svgAlternate is not None and self.svgAlternate[0] == key):
            worker.BeginFrame(("vector", key))
            def RenderArguments():
                render = v.window().exportPanel.RenderArguments("svg", preview = True, previewScene = True)
                render["clipCache"] = None
                return render
            try:
                preparedData = worker.Request("vector", (key, colorKey), RenderArguments, "svg")
                pending = preparedData is None
            except Exception as error:
                self.previewError = str(error)
                pending = True
        if not pending and (geometryChanged or self.vectorSceneOnly and colorKey != self.svgColorKey):
            previousRenderer = self.svgRenderer
            previousData = self.svgData
            cached = None
            if geometryChanged:
                if self.svgAlternate is not None:
                    if self.svgAlternate[0] == key:
                        cached = self.svgAlternate
                    else:
                        self.svgAlternate[2].deleteLater()
                    self.svgAlternate = None
                if previousRenderer is not None:
                    # Keep at most one alternate solid-fill state, with bounded
                    # source size. Raster previews still share the normal budget.
                    if familyKey is not None and familyKey == self.svgFamilyKey and previousData is not None and len(previousData) <= 8_000_000:
                        self.svgAlternate = (self.svgKey, previousData, previousRenderer, self.svgColorKey)
                    else:
                        previousRenderer.deleteLater()
            self.svgRenderer = self.svgData = None
            self.svgNavigationImage = self.svgViewImage = self.svgViewKey = None
            self.previewError = ""
            try:
                if cached is not None:
                    unusedKey, data, renderer, cachedColors = cached
                    if cachedColors != colorKey:
                        data = renderer.Recolor(themeColors)
                elif geometryChanged or previousData is None:
                    data = preparedData if preparedData is not None else self.renderVector("svg")
                    renderer = SvgPreviewRenderer.FromDocument(data, self)
                else:
                    renderer = previousRenderer
                    data = renderer.Recolor(themeColors)
                if not renderer.isValid():
                    renderer.deleteLater()
                    raise ValueError("Could not display the SVG preview.")
                self.svgRenderer, self.svgData = renderer, data
                size = renderer.defaultSize()
                # Keep a full-frame navigation bitmap so panning never exposes
                # uncaptured regions. Its bounded size is independent of zoom.
                factor = min(1.0, 4096 / max(size.width(), size.height()),
                             math.sqrt(min(4_000_000, v.viewportRasterByteLimit / 16) / (size.width() * size.height())))
                imageWidth, imageHeight = max(1, math.floor(size.width() * factor)), max(1, math.floor(size.height() * factor))
                if not v.rasterCacheBudget.Prepare("navigation", imageWidth * imageHeight * 4):
                    raise ValueError("SVG navigation preview exceeds the raster cache budget.")
                image = QtGui.QImage(imageWidth, imageHeight, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                if image.isNull():
                    raise ValueError("Could not create the SVG navigation preview.")
                image.fill(QtCore.Qt.GlobalColor.transparent)
                cachePainter = PathTextPainter(image)
                try:
                    cachePainter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                    renderer.render(cachePainter)
                finally:
                    cachePainter.end()
                self.svgNavigationImage = image
            except Exception as error:
                self.previewError = str(error)
            self.svgKey = key
            self.svgFamilyKey = familyKey
            self.svgColorKey = colorKey

        painter.fillRect(v.rect(), QtGui.QColor(themeColors["canvas"]))
        origin = v.WorldToViewport(QtCore.QPointF())
        displayScale = v.basePixelsPerMillimeter * v.zoom
        rulerUnit = v.DrawGridBackground(painter, drawingRect, origin, displayScale, drawGrid = False)
        self.Draw(painter, drawingRect, drawGuides = False)
        if self.svgRenderer is not None:
            x, y, width, height = self.vectorBounds if self.vectorSceneOnly else self.PreviewBounds()
            first = v.WorldToViewport(QtCore.QPointF(x, y + height))
            ratio = displayScale / (self.scale / 1000)
            border = self.borderSize if self.drawRuler and not self.vectorSceneOnly else 0
            first -= QtCore.QPointF(border * ratio, border * ratio)
            size = self.svgRenderer.defaultSize()
            target = QtCore.QRectF(first, QtCore.QSizeF(size.width() * ratio, size.height() * ratio))
            navigation = v.isPanning or self.navigationTimer.isActive()
            deviceRatio = v.devicePixelRatioF()
            viewKey = (target.x(), target.y(), target.width(), target.height(),
                       drawingRect.x(), drawingRect.y(), drawingRect.width(), drawingRect.height(), deviceRatio)
            if not navigation and viewKey != self.svgViewKey:
                # Resolve the vectors once at the final viewing zoom. Capture
                # only the viewport, avoiding giant bitmaps when zoomed in.
                imageWidth = math.ceil(drawingRect.width() * deviceRatio)
                imageHeight = math.ceil(drawingRect.height() * deviceRatio)
                self.svgViewImage = None
                navigationBytes = self.svgNavigationImage.sizeInBytes() if self.svgNavigationImage is not None else 0
                available = max(0, v.viewportRasterByteLimit - navigationBytes)
                if imageWidth * imageHeight * 4 > available or imageWidth > 32767 or imageHeight > 32767:
                    # Keep a stationary view cache at a lower viewing density;
                    # this changes preview sampling, never the SVG export scale.
                    roundingBytes = (imageWidth + imageHeight + 1) * 4
                    deviceRatio = min(deviceRatio, 32767 / drawingRect.width(), 32767 / drawingRect.height(),
                                      math.sqrt(max(0, available - roundingBytes) / (drawingRect.width() * drawingRect.height() * 4)))
                    imageWidth = max(1, math.ceil(drawingRect.width() * deviceRatio))
                    imageHeight = max(1, math.ceil(drawingRect.height() * deviceRatio))
                if (deviceRatio > 0 and imageWidth <= 32767 and imageHeight <= 32767
                        and v.rasterCacheBudget.Prepare("vectorView", imageWidth * imageHeight * 4, preserve = ("navigation",))):
                    image = QtGui.QImage(imageWidth, imageHeight, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                    if not image.isNull():
                        image.setDevicePixelRatio(deviceRatio)
                        image.fill(QtCore.Qt.GlobalColor.transparent)
                        cachePainter = PathTextPainter(image)
                        try:
                            cachePainter.translate(-drawingRect.left(), -drawingRect.top())
                            cachePainter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                            self.svgRenderer.render(cachePainter, target)
                        finally:
                            cachePainter.end()
                        self.svgViewImage = image
                self.svgViewKey = viewKey
            painter.save()
            painter.setClipRect(drawingRect)
            if self.vectorSceneOnly:
                x, y, width, height = self.bounds
                crop = QtCore.QRectF(v.WorldToViewport(QtCore.QPointF(x, y + height)),
                                     v.WorldToViewport(QtCore.QPointF(x + width, y)))
                painter.setClipRect(crop, QtCore.Qt.ClipOperation.IntersectClip)
            if not navigation and self.svgViewImage is not None:
                painter.drawImage(drawingRect.topLeft(), self.svgViewImage)
            elif self.svgNavigationImage is not None:
                painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
                painter.drawImage(target, self.svgNavigationImage)
            painter.restore()
        if self.vectorSceneOnly and self.drawRuler and self.svgRenderer is not None and not self.printMode:
            self.DrawCropRulers(painter, drawingRect)
        if self.printMode:
            self.Draw(painter, drawingRect, drawGuides = False)
        self.Draw(painter, drawingRect, shade = False)
        v.DrawRulerFrame(painter, rulerUnit)
        if self.previewError:
            painter.save()
            painter.setPen(QtGui.QColor(themeColors["rulerText"]))
            painter.setFont(v.font())
            painter.drawText(drawingRect.adjusted(20, 20, -20, -20),
                             QtCore.Qt.AlignmentFlag.AlignCenter | QtCore.Qt.TextFlag.TextWordWrap, self.previewError)
            painter.restore()

    def BuildSnapshot(self, coverage):
        v = self.viewport
        previous = (self.snapshot, self.snapshotBounds, self.snapshotSampling)
        pixelsPerMillimeter = self.scale / 1000
        width = math.ceil(coverage.width() * pixelsPerMillimeter)
        height = math.ceil(coverage.height() * pixelsPerMillimeter)
        self.snapshot = None
        self.previewError = ""
        self.snapshotBounds = (coverage.x(), coverage.y(), width / pixelsPerMillimeter, height / pixelsPerMillimeter)
        v.rasterCacheBudget.Clear("rulers", "snapshot-change")
        v.rasterCacheBudget.Clear("detail", "snapshot-change")
        self.snapshotSampling = self.rasterDensity
        pixelLimit = min(4_000_000, v.viewportRasterByteLimit // 8)
        nativeLimit = pixelLimit if self.printMode else min(100_000_000, v.viewportRasterByteLimit / 4)
        if (width * self.rasterDensity > 32767 or height * self.rasterDensity > 32767
                or width * height * self.rasterDensity ** 2 > nativeLimit):
            # A preview may sample fewer pixels without changing export scale.
            self.snapshotSampling = min(self.rasterDensity, 32767 / width, 32767 / height, math.sqrt(max(0, pixelLimit) / (width * height)))
        if self.snapshotSampling <= 0 or v.viewportRasterByteLimit < 4096:
            self.previewError = "Insufficient memory budget for the export preview."
            return
        self.snapshot = self.CaptureRaster(QtCore.QRectF(*self.snapshotBounds), self.snapshotSampling, "snapshot")
        if self.snapshot is None and self.previewPending and previous[0] is not None:
            self.snapshot, self.snapshotBounds, self.snapshotSampling = previous
        if self.snapshot is None and not self.previewPending:
            self.previewError = "Could not create the preview bitmap. Choose a smaller scale."

    def CaptureRaster(self, coverage, sampling, slot):
        from .widget import DrawingViewport
        v = self.viewport
        pixelsPerMillimeter = self.scale / 1000
        width, height = math.ceil(coverage.width() * pixelsPerMillimeter), math.ceil(coverage.height() * pixelsPerMillimeter)
        imageWidth, imageHeight = max(1, math.floor(width * sampling)), max(1, math.floor(height * sampling))
        if not v.rasterCacheBudget.Prepare(slot, imageWidth * imageHeight * 4, preserve = ("snapshot",) if slot == "detail" else ()):
            return None
        imageFormat = QtGui.QImage.Format.Format_RGB32 if QtGui.QColor(themeColors["canvas"]).alpha() == 255 else QtGui.QImage.Format.Format_ARGB32
        from planner_app.export_preview import PreviewProcess
        worker = PreviewProcess(self)
        if worker is not None:
            def RenderKey():
                return v.SceneRenderKey((slot, self.scale, sampling, coverage.x(), coverage.y(), coverage.width(), coverage.height(),
                    tuple(palette.themeColors.items()), v.wallStyle, v.floors, v.solidRooms, v.solidObjects, v.unitsMode, v.showGrid,
                    tuple(v.gridIntensities.items()), v.gridOrigin, v.font().toString()))
            key = RenderKey()
            if not self.printMode:
                # Overview and zoom-detail requests belong to the same scene.
                # Changing their extents must not cancel each other's result.
                worker.BeginFrame(("raster", key[0][1], key[0][7:], key[1:]))
            def RenderArguments():
                render = v.window().exportPanel.RenderArguments("png", preview = True)
                density = max(1, math.ceil(sampling))
                render.update(bounds = (coverage.x(), coverage.y(), coverage.width(), coverage.height()), border = "None",
                              ruler = False, borderSize = 28, titleBlock = {}, scaleBar = {}, pageSize = None,
                              scale = self.scale, architecturalScale = self.architecturalScale,
                              dpi = 300 * density if self.architecturalScale is not None else None,
                              rasterSampling = sampling / density if self.architecturalScale is not None else sampling,
                              texture = None, vignetteStrength = 0)
                return render
            image = worker.Request(slot, key, RenderArguments, "png", isCurrent = lambda: RenderKey() == key)
            if image is None:
                return None
            # The worker already prepared and painted this scene. Bitmap
            # adoption needs no duplicate local scene; SVG page decoration
            # builds/configures its own source explicitly when required.
            return image
        else:
            image = QtGui.QImage(imageWidth, imageHeight, imageFormat)
            if image.isNull():
                return None
        if self.snapshotViewport is None:
            self.snapshotViewport = DrawingViewport(v, furnishingDefinitions = v.furnishingDefinitions)
            self.snapshotSceneKey = None
            self.snapshotViewport.setMinimumSize(0, 0)
            self.snapshotViewport.hide()
        source = self.snapshotViewport
        self.ConfigureSnapshotViewport(source)
        if self.architecturalScale is not None:
            from planner_app.graphics.furnishings import FurnishingRendererMap
            factor = math.sqrt(imageWidth / width * imageHeight / height)
            key = (id(v.furnishingRenderers), source.lineWidths["furnishings"], factor, source.solidObjects)
            if key != self.snapshotFurnishingKey:
                self.snapshotFurnishingRenderers = FurnishingRendererMap(source.furnishingDefinitions,
                    lineWidth = source.lineWidths["furnishings"] * factor, solidBackground = source.solidObjects)
                self.snapshotFurnishingKey = key
            source.furnishingRenderers = self.snapshotFurnishingRenderers
        source.rulerSize = 0
        source.resize(min(width, 16_777_215), min(height, 16_777_215))
        source.zoom = pixelsPerMillimeter / source.basePixelsPerMillimeter
        origin = QtCore.QPointF(-coverage.x() * pixelsPerMillimeter, (coverage.y() + coverage.height()) * pixelsPerMillimeter)
        source.panOffset = origin - QtCore.QPointF(source.width() / 2, source.height() / 2)
        image.fill(QtGui.QColor(themeColors["canvas"]))
        painter = PathTextPainter(image)
        try:
            painter.scale(imageWidth / width, imageHeight / height)
            painter.setFont(source.font())
            rect = QtCore.QRectF(0, 0, width, height)
            source.DrawGridBackground(painter, rect, origin, pixelsPerMillimeter, gridOnly = True)
            painter.setClipRect(rect)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.setFont(source.font())
            source.DrawScene(painter, rect, origin, pixelsPerMillimeter)
            source.DrawLabels(painter, pixelsPerMillimeter, drawingRect = rect)
        finally:
            painter.end()
        if self.architecturalScale is not None:
            self.snapshotFurnishingRenderers = source.furnishingRenderers
        return image

    def ConfigureSnapshotViewport(self, source):
        v = self.viewport
        # The bounded overview and detail share an unselected, export-styled view.
        sceneKey = v.SceneRenderKey(None, appearanceRevision = v.renderChanges.appearance - self.colorAppearanceRevisions)
        prepared = getattr(self, "snapshotSceneKey", None) == sceneKey
        sceneNames = ("walls", "windows", "furnishings", "labels", "objectGroups", "hiddenObjectIds")
        for name in ("walls", "windows", "furnishings", "labels", "objectGroups", "hiddenObjectIds", "visibility",
                     "showGrid", "gridOrigin", "showMeasurements", "measurementPrecision", "measurementTextSize", "borderTextSize", "measurementVisibility", "measurementSettings", "wallMeasurementMode", "wallMeasurementReference", "collisionSettings",
                     "stairStepSizes", "railingSpacings", "imperialAutoSizes", "autoSizingUnitsMode", "unitsMode", "wallStyle", "solidObjects", "floors", "solidRooms", "drawOpeningOutlines", "lineworkSettings", "lineWidths", "gridIntensities",
                     "furnishingDefinitions", "furnishingRenderers", "materialBrushes", "warningMaterialBrushes", "groupedMaterialBrushes"):
            if not prepared or name not in sceneNames:
                setattr(source, name, getattr(v, name))
        source.setFont(v.font())
        source.measurementPixelsPerMillimeter = (self.scale * self.architecturalScale / 1000
                                                if self.architecturalScale is not None else 300 / 25.4)
        source.ensurePolished()
        if not prepared:
            from planner_app.export_scene import PrepareExportScene
            PrepareExportScene(source)
            self.snapshotSceneKey = sceneKey
        elif source.floors or source.solidRooms:
            source.roomDetection.Refresh(force = True)

    def DrawRasterDetail(self, painter, drawingRect, sceneKey):
        v = self.viewport
        nativeScale = self.scale / 1000
        sampling = min(self.rasterDensity, v.basePixelsPerMillimeter * v.zoom * v.devicePixelRatioF() / nativeScale)
        if sampling <= self.snapshotSampling * 1.1 or self.previewPending or v.isPanning or self.navigationTimer.isActive():
            return
        coverage = QtCore.QRectF(v.ViewportToWorld(drawingRect.topLeft()), v.ViewportToWorld(drawingRect.bottomRight())).normalized()
        coverage = coverage.intersected(QtCore.QRectF(*self.snapshotBounds))
        if coverage.isEmpty():
            return
        key = (sceneKey, tuple((coverage.x(), coverage.y(), coverage.width(), coverage.height())), sampling)
        if key != self.detailKey or self.detailImage is None:
            pixels = math.ceil(coverage.width() * nativeScale) * math.ceil(coverage.height() * nativeScale)
            available = max(0, v.viewportRasterByteLimit - (self.snapshot.sizeInBytes() if self.snapshot is not None else 0))
            sampling = min(sampling, math.sqrt(min(4_000_000, available // 8) / max(1, pixels)))
            if sampling <= self.snapshotSampling:
                return
            self.detailImage = self.CaptureRaster(coverage, sampling, "detail")
            self.detailBounds, self.detailKey = coverage, key
        if self.detailImage is not None:
            first = v.WorldToViewport(self.detailBounds.topLeft())
            second = v.WorldToViewport(self.detailBounds.bottomRight())
            painter.drawImage(QtCore.QRectF(first, second).normalized(), self.detailImage)

    def DrawCropRulers(self, painter, drawingRect):
        v = self.viewport
        if self.outputFormat == "svg":
            v.rasterCacheBudget.Clear("rulers", "vector-border")
        if self.snapshotViewport is None:
            from .widget import DrawingViewport
            self.snapshotViewport = DrawingViewport(v)
            self.snapshotSceneKey = None
            self.snapshotViewport.setMinimumSize(0, 0)
            self.snapshotViewport.hide()
        self.snapshotViewport.setFont(v.font())
        self.snapshotViewport.unitsMode = v.unitsMode
        self.snapshotViewport.gridOrigin = v.gridOrigin
        x, y, width, height = self.bounds
        pixelsPerMillimeter = self.scale / 1000
        pixelWidth, pixelHeight = math.ceil(round(width * pixelsPerMillimeter, 8)), math.ceil(round(height * pixelsPerMillimeter, 8))
        rulerSize = self.borderSize
        imageWidth, imageHeight = pixelWidth + 2 * rulerSize, pixelHeight + 2 * rulerSize
        directRulers = self.outputFormat == "svg"
        rulerColors = tuple((name, themeColors[name]) for name in
                            ("rulerBackground", "rulerText", "rulerMajorTick", "rulerMinorTick", "border"))
        key = (self.bounds, self.scale, self.rasterDensity, rulerSize, self.borderStyle, v.gridOrigin, v.unitsMode, v.font().toString(), v.borderTextSize, rulerColors, self.outputFormat)
        if key != self.rulerKey:
            source = self.snapshotViewport
            source.exportRender = True
            source.measurementTextSize = v.measurementTextSize
            source.borderTextSize = v.borderTextSize
            source.measurementPixelsPerMillimeter = 300 / 25.4
            source.rulerSize = rulerSize
            source.resize(imageWidth, imageHeight)
            source.zoom = pixelsPerMillimeter / source.basePixelsPerMillimeter
            origin = QtCore.QPointF(rulerSize - x * pixelsPerMillimeter, rulerSize + (y + height) * pixelsPerMillimeter)
            rect = QtCore.QRectF(rulerSize, rulerSize, width * pixelsPerMillimeter, height * pixelsPerMillimeter)
            if self.rulerPictureKey != key:
                picture = QtGui.QPicture()
                with PathTextPainter(picture) as picturePainter:
                    picturePainter.setFont(source.font())
                    if self.borderStyle in ("Plain", "Frame", "Corner Marks", "Reference Zones"):
                        DrawExportBorder(picturePainter, rect, rulerSize, self.borderStyle, borderTextSize = source.borderTextSize)
                    elif self.borderStyle == "Ruler + Reference Zones":
                        DrawRulerZones(picturePainter, rect, rulerSize, source, origin, pixelsPerMillimeter)
                    else:
                        unit = source.DrawGridBackground(picturePainter, rect, origin, pixelsPerMillimeter, drawGrid = False, allEdges = True,
                                                         markingsOnly = self.borderStyle == "Marked")
                        source.DrawRulerFrame(picturePainter, unit, allEdges = True, drawUnits = self.borderStyle != "Marked")
                self.rulerPicture, self.rulerPictureKey = picture, key
            self.rulerStrips = []
            if directRulers:
                # Only SVG previews play vector commands on the screen painter.
                first = v.WorldToViewport(QtCore.QPointF(x, y + height))
                factor = v.basePixelsPerMillimeter * v.zoom / pixelsPerMillimeter
                painter.save()
                painter.setClipRect(drawingRect)
                painter.translate(first - QtCore.QPointF(rulerSize * factor, rulerSize * factor))
                painter.scale(factor, factor)
                painter.setFont(source.font())
                painter.drawPicture(0, 0, self.rulerPicture)
                painter.restore()
                return
            density = self.rasterDensity
            nativeWidth, nativeHeight = (math.ceil(round(value * density, 8)) for value in (imageWidth, imageHeight))
            topRows = min(math.ceil(rulerSize * density), nativeHeight // 2)
            bottomStart = max(topRows, math.floor((imageHeight - rulerSize) * density))
            leftColumns = min(math.ceil(rulerSize * density), nativeWidth // 2)
            rightStart = max(leftColumns, math.floor((imageWidth - rulerSize) * density))
            strips = [QtCore.QRectF(px / density, py / density, pw / density, ph / density)
                      for px, py, pw, ph in ((0, 0, nativeWidth, topRows), (0, bottomStart, nativeWidth, nativeHeight - bottomStart),
                                            (0, topRows, leftColumns, bottomStart - topRows),
                                            (rightStart, topRows, nativeWidth - rightStart, bottomStart - topRows)) if pw > 0 and ph > 0]
            rulerBytes = sum((round(strip.width() * density) + 2) * (round(strip.height() * density) + 2) * 4 for strip in strips)
            if max(nativeWidth, nativeHeight) + 2 > 32767 or not v.rasterCacheBudget.Prepare("rulers", rulerBytes,
                    preserve = ("snapshot", "detail", "navigation", "vectorView", "titleBlock", "scaleBar")):
                first = v.WorldToViewport(QtCore.QPointF(x, y + height))
                factor = v.basePixelsPerMillimeter * v.zoom / pixelsPerMillimeter
                painter.save()
                try:
                    painter.setClipRect(drawingRect)
                    painter.translate(first - QtCore.QPointF(rulerSize * factor, rulerSize * factor))
                    painter.scale(factor, factor)
                    for strip in strips:
                        DrawPictureTiles(painter, self.rulerPicture, strip, density)
                finally:
                    painter.restore()
                return
            # Retain only native-density border pixels, including during edits.
            for strip in strips:
                capture, image = PictureBitmap(self.rulerPicture, strip.adjusted(-1 / density, -1 / density, 1 / density, 1 / density), density)
                self.rulerStrips.append((capture.left(), capture.top(), image, strip))
            self.rulerKey = key
        first = v.WorldToViewport(QtCore.QPointF(x, y + height))
        ratio = v.basePixelsPerMillimeter * v.zoom / pixelsPerMillimeter
        frameOrigin = first - QtCore.QPointF(rulerSize * ratio, rulerSize * ratio)
        painter.save()
        painter.setClipRect(drawingRect)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
        for offsetX, offsetY, strip, clip in self.rulerStrips:
            target = QtCore.QRectF(frameOrigin.x() + offsetX * ratio, frameOrigin.y() + offsetY * ratio,
                                  strip.width() / self.rasterDensity * ratio, strip.height() / self.rasterDensity * ratio)
            painter.save()
            painter.setClipRect(QtCore.QRectF(frameOrigin.x() + clip.left() * ratio, frameOrigin.y() + clip.top() * ratio,
                                             clip.width() * ratio, clip.height() * ratio), QtCore.Qt.ClipOperation.IntersectClip)
            painter.drawImage(target, strip)
            painter.restore()
        painter.restore()
