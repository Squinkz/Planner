"""Print page lattice, offset gestures and per-page raster effects."""
import math
from datetime import date
from xml.etree import ElementTree
from PySide6 import QtCore, QtGui
from planner_app.graphics.palette import themeColors
from planner_app.graphics import palette
from planner_app.graphics.svg_preview import SvgPreviewRenderer
from planner_app.graphics.print_vector_page import PrintVectorPage
from planner_app.graphics.text import PathTextPainter
from planner_app.graphics.export_border import DrawExportBorder, DrawRulerZones
from planner_app.graphics.title_block import TitleBlockLayout, DrawTitleBlock
from planner_app.graphics.scale_bar import DrawScaleBar
from planner_app.graphics.compositing import DrawNormalTexture, DrawVignette
from planner_app.print_layout import PrintPageLayout, PrintDrawingBounds, SelectedPrintPages
from planner_app.export_crop import MoveCropOrigin


class PrintPagesMixin:
    def ClearPrintVectors(self):
        if self.printVectorRenderer is not None:
            from shiboken6 import delete, isValid
            if isValid(self.printVectorRenderer):
                # This renderer is no longer being painted. Free its thousands
                # of native SVG children before constructing a replacement,
                # rather than holding both scenes until the next idle turn.
                delete(self.printVectorRenderer)
        self.printVectorRenderer = self.printVectorKey = self.printVectorBounds = None
        self.printVectorColorKey = None
        self.printVectorBytes = 0

    def PreparePrintVectors(self, limit):
        v = self.viewport
        # Page dimensions, borders, title blocks and offsets never affect model
        # vectors. Grid/room background is recorded separately for each page.
        recolorable = ("canvas", "objectOutline", "wallOutline")
        colors = tuple((role, themeColors[role]) for role in palette.canvasRoles
                       if role not in (*recolorable, "grid", "rulerBackground", "exportOutsideShade"))
        alpha = tuple(QtGui.QColor(themeColors[role]).alpha() for role in recolorable)
        paints = tuple(QtGui.QColor(themeColors[role]).name() for role in recolorable)
        key = v.SceneRenderKey((self.scale, colors, alpha, v.font().toString(), palette.labelFont, v.unitsMode,
                               v.wallStyle, v.floors, v.solidObjects, limit),
                              appearanceRevision = v.renderChanges.appearance - self.colorAppearanceRevisions)
        layout = self.PrintLayout()
        selected = SelectedPrintPages(self.bounds, layout["paperTile"], self.pageOrigin, stride = layout["paperStride"])
        requested = QtCore.QRectF()
        for page in selected:
            requested = requested.united(QtCore.QRectF(*PrintDrawingBounds(page, layout, self.pageOrigin)))
        try:
            modelBounds = QtCore.QRectF(*self.AutomaticModelBounds()).adjusted(-1000, -1000, 1000, 1000)
        except ValueError:
            modelBounds = QtCore.QRectF(*self.autoBounds)
        needed = requested.intersected(modelBounds)
        covered = (self.printVectorBounds is None or needed.isEmpty()
                   or QtCore.QRectF(*self.printVectorBounds).adjusted(-.001, -.001, .001, .001).contains(needed))
        if key == self.printVectorKey and covered:
            if self.printVectorRenderer is not None and paints != self.printVectorColorKey:
                data = self.printVectorRenderer.Recolor(themeColors)
                self.printVectorBytes = len(data)
            self.printVectorColorKey = paints
            return self.printVectorBounds is not None
        # Only selected sheets consume these sharp vectors. Keep some
        # overscan for crop/origin gestures, rather than exporting the entire
        # project at extreme magnification for a small piece of one sheet.
        width, height = layout["tile"]
        coverage = requested.adjusted(-width / 4, -height / 4, width / 4, height / 4).intersected(modelBounds)
        if coverage.isEmpty():
            coverage = requested
        bounds = (coverage.x(), coverage.y(), coverage.width(), coverage.height())
        data = self.renderPrintScene(bounds)
        if data is None:
            return True if self.printVectorRenderer is not None else None
        self.ClearPrintVectors()
        dataBytes = len(ElementTree.tostring(data, encoding = "unicode").encode("utf-8")) if isinstance(data, ElementTree.Element) else len(data)
        if dataBytes > max(4096, limit // 2):
            # A very large project can still fit as individually clipped pages.
            # Remember this decision until scene settings or the budget change.
            self.ClearPrintVectors()
            self.printVectorKey = key
            return False
        renderer = SvgPreviewRenderer.FromDocument(data, self)
        if not renderer.isValid():
            renderer.deleteLater()
            renderer = None
        self.printVectorRenderer, self.printVectorKey, self.printVectorBounds = renderer, key, bounds
        self.printVectorColorKey = paints
        self.printVectorBytes = dataBytes
        return True

    def ReservePrintVectors(self, dataBytes, pages, limit):
        while self.printVectorBytes + sum(self.printPageDataBytes.values()) + dataBytes > max(4096, limit // 2):
            unused = next((item for item in self.printPageCache if item not in pages), None)
            if unused is None:
                raise ValueError("Zoom in to preview fewer complete pages.")
            self.DropPrintPage(unused)

    def PrintLayout(self):
        border = self.borderSize if self.drawRuler else 0
        key = (self.scale, border, self.outputFormat, tuple(sorted(self.titleBlock.items())),
               tuple(self.printSettings.get("pageOverlap", (0, 0))),
               tuple(self.printSettings.get("pageOverlapOffset", (0, 0))),
               tuple((name, self.printSettings.get(name)) for name in ("dpi", "architecturalScale", "pageSize", "pageOrientation")))
        if key != getattr(self, "printLayoutKey", None):
            self.printLayoutValue = PrintPageLayout(self.printSettings, border, self.titleBlock, self.outputFormat)
            self.printLayoutKey = key
        return self.printLayoutValue

    def PreviewBounds(self):
        if not self.printMode or self.bounds is None:
            return self.bounds
        try:
            layout = self.PrintLayout()
            pages = SelectedPrintPages(self.bounds, layout["paperTile"], self.pageOrigin, fullyEnclosed = False, stride = layout["paperStride"])
            if not pages:
                return self.bounds
            pages = [PrintDrawingBounds(page, layout, self.pageOrigin) for page in pages]
        except ValueError:
            return self.bounds
        left = min(page[0] for page in pages)
        bottom = min(page[1] for page in pages)
        right = max(page[0] + page[2] for page in pages)
        top = max(page[1] + page[3] for page in pages)
        return left, bottom, right - left, top - bottom

    def HitPrintGuide(self, position):
        if not self.printMode or position is None or not self.viewport.DrawingRect().contains(position):
            return None
        try:
            layout = self.PrintLayout()
        except ValueError:
            return None
        v = self.viewport
        world = v.ViewportToWorld(position)
        distances = [min(abs(coordinate - (origin + round((coordinate - origin - offset) / step) * step + offset))
                         for offset in (0, extent)) * v.basePixelsPerMillimeter * v.zoom
                     for coordinate, origin, step, extent in zip((world.x(), world.y()), self.pageOrigin, layout["paperStride"], layout["paperTile"])]
        axis = min(range(2), key = distances.__getitem__)
        if distances[axis] > 6:
            return None
        edge = self.HitEdge(position)
        if edge is not None:
            x, y, width, height = self.bounds
            first = v.WorldToViewport(QtCore.QPointF(x, y))
            second = v.WorldToViewport(QtCore.QPointF(x + width, y + height))
            cropDistance = abs((position.x() if edge < 2 else position.y()) -
                               (first.x(), second.x(), first.y(), second.y())[edge])
            if cropDistance <= distances[axis] + 1:
                return None
        return axis

    def MovePrintOrigin(self, position, modifiers = QtCore.Qt.KeyboardModifier.NoModifier):
        v = self.viewport
        world = v.ViewportToWorld(position)
        origin = list(self.pageOrigin)
        axis = self.dragPage
        coordinate = (world.x() if axis == 0 else world.y()) - self.pageDragOffset
        if v.snapEnabled != bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier):
            step = v.GridSteps(self.scale / 1000)[1]
            boundary = coordinate + self.pageDragBoundary - v.gridOrigin[axis]
            coordinate = (v.gridOrigin[axis] + MoveCropOrigin((0, 0), axis, boundary, step)[axis]
                          - self.pageDragBoundary)
        origin[axis] = coordinate
        if tuple(origin) != self.pageOrigin:
            self.pageOrigin = tuple(origin)
            self.pageOriginChanged.emit(self.pageOrigin)
            self.viewport.update()

    def DrawPrintGuides(self, painter, drawingRect):
        if not self.printMode:
            return
        v = self.viewport
        try:
            layout = self.PrintLayout()
        except ValueError as error:
            painter.save()
            painter.setPen(QtGui.QColor(themeColors["rulerText"]))
            painter.drawText(drawingRect.adjusted(20, 20, -20, -20), QtCore.Qt.AlignmentFlag.AlignCenter |
                             QtCore.Qt.TextFlag.TextWordWrap, str(error))
            painter.restore()
            return
        first = v.ViewportToWorld(drawingRect.topLeft())
        second = v.ViewportToWorld(drawingRect.bottomRight())
        painter.save()
        try:
            painter.setClipRect(drawingRect)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
            background = QtGui.QColor(themeColors["canvas"])
            channels = (background.redF(), background.greenF(), background.blueF())
            backgroundLuminance = sum(weight * (value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4)
                                      for value, weight in zip(channels, (.2126, .7152, .0722)))
            target = 0 if backgroundLuminance > .179 else 1
            # Prefer an existing theme ink with strong canvas contrast and
            # the greatest separation from both crop guides and grid ink.
            nearby = [QtGui.QColor(themeColors[role]) for role in ("selectionOutline", "grid")]
            candidates = []
            for role in ("groupSelectionOutline", "warningOutline", "errorText", "missing", "objectOutline", "rulerText"):
                ink = QtGui.QColor(themeColors[role])
                for step in range(11):
                    blend = step / 10
                    channels = tuple(value * (1 - blend) + target * blend for value in (ink.redF(), ink.greenF(), ink.blueF()))
                    luminance = sum(weight * (value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4)
                                    for value, weight in zip(channels, (.2126, .7152, .0722)))
                    color = QtGui.QColor.fromRgbF(*channels)
                    if (max(luminance, backgroundLuminance) + .05) / (min(luminance, backgroundLuminance) + .05) >= 4.5:
                        break
                separation = min(sum((a - b) ** 2 for a, b in zip(channels, (other.redF(), other.greenF(), other.blueF())))
                                 for other in nearby)
                candidates.append((step == 0, separation, color))
            color = max(candidates, key = lambda candidate: candidate[:2])[2]
            hovered = self.dragPage if self.dragPage is not None else self.HitPrintGuide(self.hoverPosition)
            for axis, (a, b, origin, step, extent) in enumerate(zip((first.x(), first.y()), (second.x(), second.y()), self.pageOrigin,
                                                                   layout["paperStride"], layout["paperTile"])):
                low = math.floor((min(a, b) - origin - extent) / step)
                high = math.ceil((max(a, b) - origin) / step)
                stride = max(1, math.ceil((high - low + 1) / 512))
                ratio = painter.device().devicePixelRatioF()
                stroke = max(1, math.floor((3 if axis == hovered else 2) * ratio + .5))
                offset = .5 if stroke % 2 else 0
                pen = QtGui.QPen(color, stroke / ratio, QtCore.Qt.PenStyle.DotLine)
                pen.setCapStyle(QtCore.Qt.PenCapStyle.FlatCap)
                painter.setPen(pen)
                for index in range(low, high + 1, stride):
                    for boundary in ((0,) if abs(step - extent) < 1e-9 else (0, extent)):
                        coordinate = origin + index * step + boundary
                        point = v.WorldToViewport(QtCore.QPointF(coordinate, 0) if axis == 0 else QtCore.QPointF(0, coordinate))
                        point.setX((math.floor(point.x() * ratio) + offset) / ratio)
                        point.setY((math.floor(point.y() * ratio) + offset) / ratio)
                        line = (QtCore.QLineF(point.x(), drawingRect.top(), point.x(), drawingRect.bottom()) if axis == 0 else
                                QtCore.QLineF(drawingRect.left(), point.y(), drawingRect.right(), point.y()))
                        painter.drawLine(line)
        finally:
            painter.restore()

    def ClearPrintPreview(self):
        for page in self.printPageCache.values():
            if not isinstance(page, QtGui.QImage):
                page.deleteLater()
        self.printPageCache.clear()
        self.printPageSampling.clear()
        self.printPageDataBytes.clear()
        self.printPageImages.clear()
        self.printDragImages.clear()
        self.printDragKey = None
        self.printRenderArguments = None
        self.printPageKey = None
        self.svgViewImage = self.svgViewKey = None

    def DrawPrintDrag(self, painter, drawingRect, pages, layout, key):
        v = self.viewport
        contextBytes = self.snapshot.sizeInBytes() if self.snapshot is not None else 0
        nativeBytes = max(1, len(pages)) * layout["pixels"][0] * layout["pixels"][1] * 4
        sampling = min(1, max(512 / max(layout["pixels"]), v.basePixelsPerMillimeter * v.zoom * 1000 / self.scale * v.devicePixelRatioF()),
                       math.sqrt(max(0, v.viewportRasterByteLimit - contextBytes) / nativeBytes))
        dragKey = (key, tuple(pages), self.pageOrigin, sampling)
        if dragKey != self.printDragKey:
            # This path paints the shared context plus new decorations; the old
            # complete pages are not drawn. Release them before reserving the
            # replacement, especially when zoom makes it as large as the page.
            # Keep printPageKey so subsequent edits still use this fast path.
            for page in list(self.printPageCache):
                self.DropPrintPage(page)
            self.printPageImages.clear()
            self.svgViewImage = self.svgViewKey = None
            self.printDragImages.clear()
            width, height = (max(1, math.floor(value * sampling)) for value in layout["pixels"])
            for page in pages:
                if not self.ReservePrintRaster(width * height * 4, pages, sampling, layout):
                    raise ValueError("Insufficient memory budget for the page preview.")
                self.printDragImages[page] = self.renderPrintPage(page, sampling, decorationsOnly = True)
            self.printDragKey = dragKey
        border = self.borderSize if self.drawRuler else 0
        for page in pages:
            target = self.PrintPageRect(page)
            factor = target.width() / layout["baselinePixels"][0]
            plan = QtCore.QRectF(target.topLeft() + QtCore.QPointF(border * factor, border * factor),
                                QtCore.QSizeF(layout["drawingPixels"][0] * factor, layout["drawingPixels"][1] * factor))
            mask = QtGui.QPainterPath()
            mask.setFillRule(QtCore.Qt.FillRule.OddEvenFill)
            mask.addRect(target)
            mask.addRect(plan)
            painter.save()
            painter.setClipPath(mask, QtCore.Qt.ClipOperation.IntersectClip)
            painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawImage(target, self.printDragImages[page])
            painter.restore()
            painter.save()
            try:
                painter.translate(target.topLeft())
                painter.scale(factor, factor)
                painter.setFont(v.font())
                self.DrawScaleBarDecoration(painter, QtCore.QRectF(border, border, *layout["drawingPixels"]),
                                           PrintDrawingBounds(page, layout, self.pageOrigin))
            finally:
                painter.restore()
            if self.outputFormat == "png":
                painter.save()
                painter.setClipRect(target.intersected(drawingRect))
                DrawNormalTexture(painter, target, self.texture, self.textureAngle, layout["pixels"], **self.textureSettings)
                DrawVignette(painter, target, self.vignetteStrength, layout["pixels"])
                painter.restore()

    def DrawCachedPrintPages(self, painter, drawingRect, pages, layout, key, limit, sampling):
        v = self.viewport
        v.rasterCacheBudget.Clear("scaleBar", "complete-pages")
        # An edit can return to the original appearance key (for example undo
        # or deleting the character just typed). Its temporary buffers are
        # still obsolete even though the complete-page key did not change.
        self.printDragImages.clear()
        self.printDragKey = None
        self.printCachedFormat = self.outputFormat
        if key != self.printPageKey:
            self.ClearPrintPreview()
            self.printPageKey = key
        if pages and limit < 4096:
            raise ValueError("Insufficient memory budget for the page preview.")
        sharedVectors = self.PreparePrintVectors(limit) if self.outputFormat == "svg" and pages else False
        if sharedVectors is None:
            return
        for page in pages:
            cached = self.printPageCache.get(page)
            if cached is not None and (self.outputFormat == "svg" or self.printPageSampling[page] >= sampling * .9):
                self.printPageCache[page] = self.printPageCache.pop(page)
                continue
            if cached is not None:
                self.DropPrintPage(page)
            while len(self.printPageCache) >= max(8, len(pages)):
                unused = next((item for item in self.printPageCache if item not in pages), None)
                if unused is None:
                    break
                self.DropPrintPage(unused)
            width, height = (max(1, math.floor(value * sampling)) for value in layout["pixels"])
            if self.outputFormat == "png" and not self.ReservePrintRaster(width * height * 4, pages, sampling, layout):
                raise ValueError("Insufficient memory budget for the page preview.")
            if self.outputFormat == "svg" and not sharedVectors:
                data = self.renderPrintPage(page, sampling)
                self.ReservePrintVectors(len(data), pages, limit)
                self.printPageDataBytes[page] = len(data)
                result = SvgPreviewRenderer.FromDocument(data, self)
                if not result.isValid():
                    result.deleteLater()
                    raise ValueError("Could not display the page preview.")
            elif self.outputFormat == "svg":
                drawing = PrintDrawingBounds(page, layout, self.pageOrigin)
                border = self.borderSize if self.drawRuler else 0
                if self.snapshotViewport is None:
                    from .widget import DrawingViewport
                    self.snapshotViewport = DrawingViewport(v, furnishingDefinitions = v.furnishingDefinitions)
                    self.snapshotViewport.setMinimumSize(0, 0)
                    self.snapshotViewport.hide()
                    self.snapshotSceneKey = None
                source = self.snapshotViewport
                self.ConfigureSnapshotViewport(source)
                previous = (source.size(), source.rulerSize, source.zoom, QtCore.QPointF(source.panOffset))
                grid = QtGui.QPicture()
                decorations = QtGui.QPicture()
                try:
                    source.rulerSize = border
                    source.resize(layout["drawingPixels"][0] + 2 * border, layout["drawingPixels"][1] + 2 * border)
                    scale = self.scale / 1000
                    source.zoom = scale / source.basePixelsPerMillimeter
                    origin = QtCore.QPointF(border - drawing[0] * scale, border + (drawing[1] + drawing[3]) * scale)
                    source.panOffset = origin - QtCore.QPointF(source.width() / 2, source.height() / 2)
                    with PathTextPainter(grid) as gridPainter:
                        gridPainter.setFont(source.font())
                        source.DrawGridBackground(gridPainter, QtCore.QRectF(border, border, *layout["drawingPixels"]), origin, scale, gridOnly = True)
                    with PathTextPainter(decorations) as framePainter:
                        framePainter.setFont(source.font())
                        plot = QtCore.QRectF(border, border, *layout["drawingPixels"])
                        if self.borderStyle in ("Ruler", "Marked"):
                            unit = source.DrawGridBackground(framePainter, plot, origin, scale, drawGrid = False, allEdges = True,
                                                             markingsOnly = self.borderStyle == "Marked")
                            source.DrawRulerFrame(framePainter, unit, allEdges = True, drawUnits = self.borderStyle != "Marked")
                        elif self.borderStyle == "Ruler + Reference Zones":
                            DrawRulerZones(framePainter, plot, border, source, origin, scale)
                        elif self.borderStyle != "None":
                            DrawExportBorder(framePainter, plot, border, self.borderStyle, borderTextSize = source.borderTextSize)
                        if self.titleBlock.get("enabled", False):
                            fitWidth = self.titleBlock.get("position", "Right") == "Bottom"
                            width, height, block = TitleBlockLayout(source.width(), source.height(), self.titleBlock,
                                self.scale, self.architecturalScale, "svg", 300, fitWidth = fitWidth, pageSize = layout["paper"])
                            DrawTitleBlock(framePainter, block, self.titleBlock, self.scale,
                                           self.architecturalScale, "svg", 300, fitWidth = fitWidth, pageSize = layout["paper"])
                        DrawScaleBar(framePainter, plot, self.scaleBar, self.scale, source.unitsMode,
                                     bounds = drawing, gridOrigin = source.gridOrigin, measurementTextSize = source.measurementTextSize)
                finally:
                    source.resize(previous[0])
                    source.rulerSize, source.zoom, source.panOffset = previous[1:]
                dataBytes = grid.size() + decorations.size()
                self.ReservePrintVectors(dataBytes, pages, limit)
                self.printPageDataBytes[page] = dataBytes
                result = PrintVectorPage(self.printVectorRenderer, self.printVectorBounds, drawing, grid,
                    decorations, layout, border, themeColors["canvas"], self)
                if not result.isValid():
                    result.deleteLater()
                    raise ValueError("Could not display the page preview.")
            else:
                result = self.renderPrintPage(page, sampling)
                if result is None:
                    continue
            self.printPageCache[page] = result
            self.printPageSampling[page] = sampling
        if self.outputFormat == "svg" and pages:
            self.DrawPrintVectors(painter, drawingRect, pages, layout)
        else:
            painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
            for page in pages:
                if page in self.printPageCache:
                    painter.drawImage(self.PrintPageRect(page), self.printPageCache[page])

    def DropPrintPage(self, page):
        rendered = self.printPageCache.pop(page)
        if not isinstance(rendered, QtGui.QImage):
            rendered.deleteLater()
        self.printPageSampling.pop(page, None)
        self.printPageDataBytes.pop(page, None)
        self.printPageImages.pop(page, None)

    def ReservePrintRaster(self, requested, visiblePages, sampling, layout):
        v = self.viewport
        while v.rasterCacheBudget.RetainedBytes() + requested > v.viewportRasterByteLimit:
            unused = next((page for page in self.printPageCache if page not in visiblePages), None)
            if unused is not None:
                self.DropPrintPage(unused)
                continue
            larger = next((page for page, image in self.printPageCache.items() if isinstance(image, QtGui.QImage)
                           and self.printPageSampling[page] > sampling + 1e-9), None)
            if larger is not None:
                width, height = (max(1, math.floor(value * sampling)) for value in layout["pixels"])
                self.printPageCache[larger] = self.printPageCache[larger].scaled(width, height,
                    QtCore.Qt.AspectRatioMode.IgnoreAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation)
                self.printPageSampling[larger] = sampling
                continue
            break
        return v.rasterCacheBudget.Prepare("printPages", requested, preserve = ("snapshot",), replace = False)

    def DrawPrintContext(self, painter, drawingRect, layout, colors):
        v = self.viewport
        first = v.ViewportToWorld(drawingRect.topLeft())
        last = v.ViewportToWorld(drawingRect.bottomRight())
        visible = (min(first.x(), last.x()), min(first.y(), last.y()), abs(first.x() - last.x()), abs(first.y() - last.y()))
        pages = SelectedPrintPages(visible, layout["paperTile"], self.pageOrigin, maximum = 4096, fullyEnclosed = False, stride = layout["paperStride"])
        requested = QtCore.QRectF()
        for page in pages:
            requested = requested.united(QtCore.QRectF(*PrintDrawingBounds(page, layout, self.pageOrigin)))
        key = v.SceneRenderKey((self.scale, colors, v.font().toString(), palette.labelFont,
                               v.showGrid, tuple(v.gridIntensities.items()), v.gridOrigin, v.unitsMode,
                               v.wallStyle, v.floors, v.solidRooms, v.solidObjects, v.viewportRasterByteLimit))
        try:
            modelBounds = QtCore.QRectF(*self.AutomaticModelBounds()).adjusted(-1000, -1000, 1000, 1000)
        except ValueError:
            modelBounds = QtCore.QRectF(*self.autoBounds)
        needed = requested.intersected(modelBounds)
        covered = (self.snapshotBounds is not None and (needed.isEmpty()
                   or QtCore.QRectF(*self.snapshotBounds).adjusted(-.001, -.001, .001, .001).contains(needed)))
        if key != self.snapshotKey or self.snapshot is None or not covered:
            width, height = layout["tile"]
            coverage = requested.adjusted(-width, -height, width, height).intersected(modelBounds)
            if coverage.isEmpty():
                coverage = requested
            self.BuildSnapshot(coverage)
            self.snapshotKey = key
        if self.snapshot is None:
            return
        sourceX, sourceY, sourceWidth, sourceHeight = self.snapshotBounds
        samplingX, samplingY = self.snapshot.width() / sourceWidth, self.snapshot.height() / sourceHeight
        border = self.borderSize if self.drawRuler else 0
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
        for page in pages:
            x, y, width, height = PrintDrawingBounds(page, layout, self.pageOrigin)
            target = self.PrintPageRect(page)
            factor = target.width() / layout["baselinePixels"][0]
            target = QtCore.QRectF(target.topLeft() + QtCore.QPointF(border * factor, border * factor),
                                  QtCore.QSizeF(layout["drawingPixels"][0] * factor, layout["drawingPixels"][1] * factor))
            source = QtCore.QRectF((x - sourceX) * samplingX, (sourceY + sourceHeight - y - height) * samplingY,
                                   width * samplingX, height * samplingY)
            painter.drawImage(target, self.snapshot, source)
        # Plain plan context remains outside the crop; page decorations do not.
        self.Draw(painter, drawingRect, drawGuides = False)

    def DrawPrintVectors(self, painter, drawingRect, pages, layout):
        v = self.viewport
        navigation = v.isPanning or self.navigationTimer.isActive()
        targets = []
        for page in pages:
            target = self.PrintPageRect(page)
            targets.append((target.x(), target.y(), target.width(), target.height()))
        viewKey = (self.printPageKey, tuple(pages), tuple(targets), drawingRect, v.devicePixelRatioF())
        if not navigation and viewKey != self.svgViewKey:
            v.rasterCacheBudget.Clear("vectorView", "print-view")
            available = max(0, v.viewportRasterByteLimit - v.rasterCacheBudget.RetainedBytes())
            ratio = min(v.devicePixelRatioF(), math.sqrt(available / max(1, drawingRect.width() * drawingRect.height() * 4)))
            width, height = max(1, math.floor(drawingRect.width() * ratio)), max(1, math.floor(drawingRect.height() * ratio))
            if ratio > 0 and v.rasterCacheBudget.Prepare("vectorView", width * height * 4, preserve = ("printPages", "snapshot")):
                image = QtGui.QImage(width, height, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                image.setDevicePixelRatio(ratio)
                image.fill(QtCore.Qt.GlobalColor.transparent)
                with QtGui.QPainter(image) as cachePainter:
                    cachePainter.translate(-drawingRect.left(), -drawingRect.top())
                    cachePainter.setClipRect(drawingRect)
                    cachePainter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
                    for page in pages:
                        self.printPageCache[page].render(cachePainter, self.PrintPageRect(page))
                self.svgViewImage = image
            self.svgViewKey = viewKey
        if not navigation and self.svgViewImage is not None:
            painter.drawImage(drawingRect.topLeft(), self.svgViewImage)
            return
        # Whole-page navigation bitmaps avoid replaying SVG paths during a drag.
        for page in pages:
            if page not in self.printPageImages:
                sampling = min(1, 1024 / max(layout["pixels"]))
                width, height = (max(1, math.floor(value * sampling)) for value in layout["pixels"])
                source = None
                saved = self.svgViewKey
                if self.svgViewImage is not None and saved is not None and saved[0] == self.printPageKey and page in saved[1]:
                    previous = QtCore.QRectF(*saved[2][saved[1].index(page)])
                    # A fully visible page is already present in the sharp view.
                    # Reuse those pixels for the first zoom/pan frame instead of
                    # replaying its model and clips just to make a smaller image.
                    if saved[3].contains(previous) and v.rasterCacheBudget.RetainedBytes() + width * height * 4 <= v.viewportRasterByteLimit:
                        ratio = self.svgViewImage.devicePixelRatioF()
                        source = QtCore.QRectF((previous.x() - saved[3].x()) * ratio, (previous.y() - saved[3].y()) * ratio,
                                              previous.width() * ratio, previous.height() * ratio)
                if self.ReservePrintRaster(width * height * 4, pages, sampling, layout):
                    image = QtGui.QImage(width, height, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                    image.fill(QtCore.Qt.GlobalColor.transparent)
                    with QtGui.QPainter(image) as cachePainter:
                        cachePainter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
                        if source is not None:
                            cachePainter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
                            cachePainter.drawImage(QtCore.QRectF(0, 0, width, height), self.svgViewImage, source)
                        else:
                            self.printPageCache[page].render(cachePainter)
                    self.printPageImages[page] = image
            if page in self.printPageImages:
                painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
                painter.drawImage(self.PrintPageRect(page), self.printPageImages[page])
            else:
                self.printPageCache[page].render(painter, self.PrintPageRect(page))

    def PrintPageRect(self, page):
        x, y, width, height = page
        first = self.viewport.WorldToViewport(QtCore.QPointF(x, y + height))
        last = self.viewport.WorldToViewport(QtCore.QPointF(x + width, y))
        return QtCore.QRectF(first, last).normalized()

    def DrawPrintPreview(self, painter, drawingRect):
        v = self.viewport
        if self.outputFormat != "svg" and self.printVectorKey is not None:
            self.ClearPrintVectors()
        for name in ("navigation", "detail", "rulers", "titleBlock"):
            v.rasterCacheBudget.Clear(name, "print-pages")
        if self.svgRenderer is not None:
            self.svgRenderer.deleteLater()
            self.svgRenderer = self.svgData = self.svgKey = None
        painter.fillRect(v.rect(), QtGui.QColor(themeColors["canvas"]))
        origin = v.WorldToViewport(QtCore.QPointF())
        rulerUnit = v.DrawGridBackground(painter, drawingRect, origin, v.basePixelsPerMillimeter * v.zoom, drawGrid = False)
        painter.save()
        try:
            painter.setClipRect(drawingRect)
            layout = self.PrintLayout()
            selected = SelectedPrintPages(self.bounds, layout["paperTile"], self.pageOrigin, stride = layout["paperStride"])
            pages = [page for page in selected if self.PrintPageRect(page).intersects(drawingRect)]
            colors = tuple((role, themeColors[role]) for role in palette.canvasRoles)
            settings = repr({name: value for name, value in self.printSettings.items()
                             if name not in ("bounds", "pageOrigin") and not name.startswith(("texture", "vignette"))})
            limit = v.viewportRasterByteLimit
            appearance = v.SceneRenderKey((self.scale, self.outputFormat, colors, settings, repr(self.titleBlock),
                                          v.font().toString(), palette.labelFont, date.today(), limit))
            # Complete pages bake effects into their pixels; interactive
            # decoration buffers do not. Only the former depend on these values.
            effects = (self.texture, self.textureAngle, tuple(self.textureSettings.items()), self.vignetteStrength)
            renderKey = (appearance, effects)
            if renderKey != self.printRenderKey:
                self.printRenderArguments = None
                self.printRenderKey = renderKey
            from planner_app.export_preview import PreviewProcess
            worker = PreviewProcess(self)
            liveComposite = self.compositeGesture and self.outputFormat == "png"
            if worker is not None:
                worker.BeginFrame((renderKey, self.pageOrigin))
                # Selected sheets are useful before the surrounding context.
                # Queue them first; never decode a cached result twice merely
                # to prefetch it. Constrained PNG budgets resolve sampling after
                # the context allocation, as in the synchronous renderer.
                worker.prefetching = True
                try:
                    interacting = self.dragPage is not None or self.dragEdge is not None or liveComposite
                    if not interacting and self.outputFormat == "svg":
                        self.PreparePrintVectors(limit)
                    elif not interacting and len(pages) * layout["pixels"][0] * layout["pixels"][1] * 4 + min(16_000_000, limit // 2) <= limit:
                        for page in pages:
                            if (renderKey, self.pageOrigin) != self.printPageKey or page not in self.printPageCache:
                                self.renderPrintPage(page)
                finally:
                    worker.prefetching = False
            self.DrawPrintContext(painter, drawingRect, layout, colors)
            nativeBytes = max(1, len(pages)) * layout["pixels"][0] * layout["pixels"][1] * 4
            contextBytes = self.snapshot.sizeInBytes() if self.snapshot is not None else 0
            sampling = min(1, math.sqrt(max(0, limit - contextBytes) / nativeBytes)) if self.outputFormat == "png" else 1
            key = (renderKey, self.pageOrigin)
            if (self.dragPage is not None or self.dragEdge is not None or liveComposite or self.printPreviewTimer.isActive() and self.printPageKey is not None
                    and self.printPageKey != key and getattr(self, "printCachedFormat", None) == self.outputFormat):
                self.DrawPrintDrag(painter, drawingRect, pages, layout, (appearance, self.pageOrigin))
            else:
                self.DrawCachedPrintPages(painter, drawingRect, pages, layout, key, limit, sampling)
            self.previewError = ""
        except Exception as error:
            self.previewError = str(error)
            painter.setPen(QtGui.QColor(themeColors["rulerText"]))
            painter.drawText(drawingRect.adjusted(20, 20, -20, -20), QtCore.Qt.AlignmentFlag.AlignCenter |
                             QtCore.Qt.TextFlag.TextWordWrap, self.previewError)
        finally:
            painter.restore()
        self.DrawPrintGuides(painter, drawingRect)
        self.Draw(painter, drawingRect, shade = False)
        v.DrawRulerFrame(painter, rulerUnit)
