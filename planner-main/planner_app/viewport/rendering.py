"""Viewport grid, scene painting, dimensions, rulers and selection feedback."""
from planner_app.models import AngleGuide, ObjectControlPoints

from planner_app.models import Elevator
from planner_app.models import lineWeightClasses

import math
from contextlib import ExitStack
from itertools import chain
from time import perf_counter
from planner_app.graphics.path_operations import Paths
from PySide6 import QtCore, QtGui

from planner_app.graphics.north_arrow import DrawNorthArrow
from planner_app.graphics.fireplace import FireplacePath
from planner_app.graphics.object_composite import ObjectPaintDevice
from planner_app.graphics.palette import themeColors
from planner_app.graphics.fonts import fontFamily
from planner_app.graphics import palette
from planner_app.graphics.linework import LinePen
from planner_app.graphics.furnishings import DrawFurnishing, SelectedFurnishingRenderer, FurnishingArtworkBounds, FurnishingRenderer
from planner_app.paths import furnishingsDirectory
from planner_app.graphics.symbols import DrawOpeningSymbol, DrawStairSymbol, DrawStairArrows
from planner_app.geometry.stair_annotations import StairArrowRuns
from planner_app.graphics.arrows import ArrowPaths, ConnectedArrowDirections, ConnectedArrowCorners
from planner_app.models import OpenDoorway, Door, SwingingDoor, DoubleDoor, Furnishing, PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, SlidingDoor, MeasurementGuide, BoundaryLine, DashedLine, SolidLine, Arrow, Counter, Railing, Stair, Wall, Pillar, Column, Label, Window, NorthArrow, Fireplace
from planner_app.units import MetricUnit, FormatLength, PropertyUnit, GridUnit, imperialModes
from planner_app.graphics.measurement_text import MeasurementTextPath
from planner_app.geometry.measurement_stacks import BuildMeasurementStacks
from .geometry import CollisionPass
from .diagnostics import MeasurePaint
from .edit_cache import EditPaintCacheMixin

toolTipRows = {
    "searchFurnishings": ("Space", "Search furnishings"),
    "holdDoor": ("D", "(Hold) Place door"),
    "holdWindow": ("S", "(Hold) Place window"),
    "thickness": ("Q/W", "Set wall thickness"),
    "placeDoor": ("Left mouse", "Place door"),
    "placeWindow": ("Left mouse", "Place window"),
    "releaseDoor": ("D", "(Release) Cancel"),
    "releaseWindow": ("S", "(Release) Cancel"),
    "doorType": ("Scroll", "Set door type"),
    "windowType": ("Scroll", "Set window type"),
    "select": ("Left mouse", "Select or move object"),
    "placeWall": ("Right mouse", "(Drag) Place wall"),
    "segments": ("Scroll", "Change segment count"),
    "square": ("Ctrl", "Constrain to a square"),
    "circle": ("Ctrl", "Constrain to a circle"),
    "center": ("Shift", "Expand from center"),
    "cancelDraw": ("Left mouse", "Cancel"),
    "angle": ("Ctrl", "Snap to 15\u00b0 increments"),
    "extrude": ("Shift", "Extrude"),
    "duplicate": ("Shift", "Duplicate object"),
    "axes": ("Ctrl", "Constrain to axes"),
    "localAxes": ("Ctrl", "Constrain to local axes"),
    "localAngle": ("Ctrl", "Snap to local 15\u00b0 increments"),
    "axisOrigin": ("Scroll", "Switch axis origin"),
    "face": ("Ctrl", "Face cursor"),
    "hinge": ("Ctrl", "Adjust hinge side"),
    "cancelMove": ("Right mouse", "Cancel"),
    "calibrationPlace": ("Left Mouse", "Place point"),
    "calibrationConfirm": ("Enter", "Confirm"),
    "calibrationCancel": ("Escape", "Cancel"),
}


class RenderingMixin(EditPaintCacheMixin):
    @MeasurePaint
    @CollisionPass
    def paintEvent(self, event):
        renderStart = perf_counter()
        diagnostics = self.renderDiagnostics if self.renderDiagnostics is not None and self.renderDiagnostics.enabled else None
        self.rasterCacheBudget.Enforce()
        with QtGui.QPainter(self) as painter:
            drawingRect = self.DrawingRect()
            origin = self.WorldToViewport(QtCore.QPointF())
            pixelsPerMillimeter = self.basePixelsPerMillimeter * self.zoom
            ratio = self.devicePixelRatioF()
            coverageLeft, coverageTop = math.floor(drawingRect.left() * ratio), math.floor(drawingRect.top() * ratio)
            coverageRight, coverageBottom = math.ceil(drawingRect.right() * ratio), math.ceil(drawingRect.bottom() * ratio)
            rasterRect = QtCore.QRectF(coverageLeft / ratio, coverageTop / ratio,
                                      (coverageRight - coverageLeft) / ratio, (coverageBottom - coverageTop) / ratio)
            if self.exportOverlay.active:
                self.rasterCacheBudget.Clear("edit", "export")
                self.exportOverlay.DrawPreview(painter, drawingRect)
                self.renderSamples.append((renderStart, (perf_counter() - renderStart) * 1000.0))
                return

            stableScene = (bool(self.walls or self.windows or self.furnishings or self.labels)
                           and self.dragStart is None and not self.isDragging and self.pendingWall is None and not self.pendingShapeWalls
                           and self.furnishingHandleDrag is None and not self.guiDragActive
                           and all(preview is None for preview in (self.furnishingPreview, self.windowDropPreview,
                                   self.inactiveOpeningPreview, self.counterPreview, self.arrowPreview, self.labelPreview)))

            if not stableScene:
                self.viewportPanRaster = self.viewportPanKey = self.viewportPanOrigin = self.viewportPanState = None

            backgroundKey = (self.width(), self.height(), self.devicePixelRatioF(), origin.x(), origin.y(),
                             self.zoom, self.basePixelsPerMillimeter, self.rulerSize, self.showGrid, self.unitsMode,
                             tuple(self.gridIntensities.items()), self.font().toString(), tuple(themeColors.items()),
                             self.referenceImage.revision if self.referenceImage is not None else 0,
                             self.roomDetection.Check())
            backgroundChanged = backgroundKey != self.viewportBackgroundKey
            frameBytes = math.ceil(self.width() * ratio) * math.ceil(self.height() * ratio) * 4
            frameFitsBudget = frameBytes <= min(self.viewportSceneByteLimit, self.viewportRasterByteLimit)
            cacheEdit = frameFitsBudget and self.CanCacheEditScene()
            if not cacheEdit:
                self.rasterCacheBudget.Clear("edit", "inactive")
            cachePan = (stableScene and self.isPanning
                        and frameFitsBudget)
            panKey = ((self.viewportSceneByteLimit, self.SceneRenderKey(backgroundKey[:3] + backgroundKey[5:]))
                      if stableScene and frameFitsBudget and (self.isPanning or self.viewportPanRaster is not None) else None)
            cacheScene = stableScene and not self.isPanning and frameFitsBudget
            sceneKey = self.SceneRenderKey(backgroundKey) if cacheScene else None
            if (cacheScene and self.viewportPanRaster is not None and self.viewportPanState is not None
                    and panKey == self.viewportPanKey and origin == self.viewportPanOrigin):
                # The pan raster owns only the canvas pixels; its ruler pixels may
                # be from an earlier camera position. Composite it with that clip.
                self.rasterCacheBudget.Clear("scene", "pan-transfer")
                self.viewportScene = self.viewportPanRaster
                self.viewportSceneState = self.viewportPanState
                self.viewportSceneKey = sceneKey
                self.viewportPanRaster = self.viewportPanKey = self.viewportPanOrigin = self.viewportPanState = None
                if self.showMeasurements:
                    with QtGui.QPainter(self.viewportScene) as scenePainter:
                        scenePainter.setFont(self.viewportBackgroundFont)
                        scenePainter.setClipRect(drawingRect)
                        scenePainter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                        self.DrawSceneMeasurements(scenePainter, drawingRect, self.viewportSceneState, retainCommands = True)
                        self.DrawLabels(scenePainter, pixelsPerMillimeter, self.viewportSceneState[1],
                                        drawOutlines = False, drawingRect = drawingRect, commandKey = panKey)
                if diagnostics is not None:
                    diagnostics.RecordCache("scene", "hit", "pan-transfer")
            if not self.isPanning:
                self.viewportPanRaster = self.viewportPanKey = self.viewportPanOrigin = self.viewportPanState = None
            reuseScene = cacheScene and sceneKey == self.viewportSceneKey and self.viewportScene is not None
            if not reuseScene:
                self.rasterCacheBudget.Clear("scene", "changed-or-inactive")
            reusePanRaster = False
            if cachePan and self.viewportPanRaster is not None:
                panTranslation = origin - self.viewportPanOrigin
                ratio = self.devicePixelRatioF()
                pixelX, pixelY = panTranslation.x() * ratio, panTranslation.y() * ratio
                reusePanRaster = (abs(pixelX - round(pixelX)) < 1e-7 and abs(pixelY - round(pixelY)) < 1e-7
                                  and abs(pixelX) < drawingRect.width() * ratio and abs(pixelY) < drawingRect.height() * ratio
                                  and panKey == self.viewportPanKey)
            if diagnostics is not None and self.isPanning:
                reason = ("reused" if reusePanRaster else "live-edit" if not stableScene else
                          "budget" if not cachePan else "cold" if self.viewportPanRaster is None else
                          "fractional-movement" if abs(pixelX - round(pixelX)) >= 1e-7 or abs(pixelY - round(pixelY)) >= 1e-7 else
                          "outside-coverage" if abs(pixelX) >= drawingRect.width() * ratio or abs(pixelY) >= drawingRect.height() * ratio else
                          "scene-changed")
                diagnostics.RecordCache("pan", "hit" if reusePanRaster else "miss", reason)
            if reusePanRaster or reuseScene:
                self.viewportRulerUnit = self.DrawGridBackground(painter, drawingRect, origin, pixelsPerMillimeter, drawGrid = False)
                self.viewportBackgroundFont = painter.font()
                # This frame's grid comes from the scrolled raster. Rebuild the full
                # background when leaving pan or returning to fractional movement.
                self.viewportBackgroundKey = self.viewportBackground = None
            elif backgroundChanged:
                ratio = self.devicePixelRatioF()
                if self.rasterCacheBudget.Prepare("background", frameBytes):
                    self.viewportBackground = QtGui.QPixmap(math.ceil(self.width() * ratio), math.ceil(self.height() * ratio))
                    self.viewportBackground.setDevicePixelRatio(ratio)
                    self.viewportBackground.fill(QtGui.QColor(themeColors["canvas"]))
                    with QtGui.QPainter(self.viewportBackground) as backgroundPainter:
                        self.viewportRulerUnit = self.DrawGridBackground(backgroundPainter, drawingRect, origin, pixelsPerMillimeter)
                        self.viewportBackgroundFont = backgroundPainter.font()
                    self.viewportBackgroundKey = backgroundKey
                else:
                    painter.fillRect(rasterRect, QtGui.QColor(themeColors["canvas"]))
                    self.viewportRulerUnit = self.DrawGridBackground(painter, drawingRect, origin, pixelsPerMillimeter)
                    self.viewportBackgroundFont = painter.font()
            if not reusePanRaster and not reuseScene and not cachePan and self.viewportBackground is not None:
                painter.drawPixmap(0, 0, self.viewportBackground)
            elif cachePan and not reusePanRaster:
                # The first pan raster is drawn with a canvas-only clip below.
                # Paint rulers now, even before the pointer has moved.
                self.viewportRulerUnit = self.DrawGridBackground(painter, drawingRect, origin, pixelsPerMillimeter, drawGrid = False)
            painter.setFont(self.viewportBackgroundFont)

            if self.referenceImage is None or not self.referenceImage.active:
                self.DrawSnapGuides(painter, drawingRect)

            painter.save()
            painter.setClipRect(drawingRect)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            # The retained scene excludes cursor handles and overlays. During edits
            # render directly so previews and validity feedback always stay current.
            if cacheScene:
                if diagnostics is not None:
                    diagnostics.RecordCache("scene", "hit" if sceneKey == self.viewportSceneKey else "miss",
                                            "reused" if sceneKey == self.viewportSceneKey else "cold-or-changed")
                if sceneKey != self.viewportSceneKey:
                    # Paint on the same opaque background as the direct path;
                    # flattening translucent strokes on transparency changes rounding.
                    # Transfer the opaque background instead of retaining a duplicate.
                    scene = self.viewportBackground
                    self.viewportBackground = self.viewportBackgroundKey = None
                    with QtGui.QPainter(scene) as scenePainter:
                        scenePainter.setFont(painter.font())
                        scenePainter.setClipRect(drawingRect)
                        scenePainter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                        self.viewportSceneState = self.DrawScene(scenePainter, drawingRect, origin, pixelsPerMillimeter, retainAnnotations = True)
                        self.DrawLabels(scenePainter, pixelsPerMillimeter, self.viewportSceneState[1],
                                        drawOutlines = False, drawingRect = drawingRect)
                    self.viewportScene, self.viewportSceneKey = scene, sceneKey
                # Keep current rulers outside the retained canvas, using physical
                # coverage so fractional edge pixels are not attenuated twice.
                painter.setClipRect(rasterRect)
                painter.drawPixmap(0, 0, self.viewportScene)
                painter.setClipRect(drawingRect)
                sceneState = self.viewportSceneState
            else:
                if diagnostics is not None and stableScene and not self.isPanning:
                    diagnostics.RecordCache("scene", "miss", "budget")
                self.viewportSceneKey = None
                self.viewportScene = None
                self.viewportSceneState = None
                # Scroll only whole device pixels. Repaint exposed strips using the
                # original coordinates; fractional movement gets a fresh raster.
                if cachePan:
                    if reusePanRaster:
                        deltaX, deltaY = round(pixelX), round(pixelY)
                        if deltaX or deltaY:
                            pixelRect = QtCore.QRect(math.ceil(drawingRect.left() * ratio), math.ceil(drawingRect.top() * ratio),
                                                     math.floor(drawingRect.right() * ratio) - math.ceil(drawingRect.left() * ratio),
                                                     math.floor(drawingRect.bottom() * ratio) - math.ceil(drawingRect.top() * ratio))
                            self.viewportPanRaster.scroll(deltaX, deltaY, pixelRect)
                            dirtyPath = QtGui.QPainterPath()
                            dirtyPath.setFillRule(QtCore.Qt.FillRule.WindingFill)
                            dirtyRects = []
                            if deltaX:
                                left = pixelRect.left() if deltaX > 0 else pixelRect.x() + pixelRect.width() + deltaX
                                dirtyRects.append(QtCore.QRectF(left / ratio, pixelRect.top() / ratio,
                                                               abs(deltaX) / ratio, pixelRect.height() / ratio))
                            if deltaY:
                                top = pixelRect.top() if deltaY > 0 else pixelRect.y() + pixelRect.height() + deltaY
                                dirtyRects.append(QtCore.QRectF(pixelRect.left() / ratio, top / ratio,
                                                               pixelRect.width() / ratio, abs(deltaY) / ratio))
                            # Scroll the fully covered physical pixels. Repaint the
                            # fractional fringe so clipped edge pixels never enter
                            # the interior or keep stale content after translation.
                            left, top = pixelRect.x() / ratio, pixelRect.y() / ratio
                            right = (pixelRect.x() + pixelRect.width()) / ratio
                            bottom = (pixelRect.y() + pixelRect.height()) / ratio
                            if left > drawingRect.left():
                                dirtyRects.append(QtCore.QRectF(rasterRect.left(), rasterRect.top(), 1 / ratio, rasterRect.height()))
                            if top > drawingRect.top():
                                dirtyRects.append(QtCore.QRectF(rasterRect.left(), rasterRect.top(), rasterRect.width(), 1 / ratio))
                            if right < drawingRect.right():
                                dirtyRects.append(QtCore.QRectF(right, rasterRect.top(), 1 / ratio, rasterRect.height()))
                            if bottom < drawingRect.bottom():
                                dirtyRects.append(QtCore.QRectF(rasterRect.left(), bottom, rasterRect.width(), 1 / ratio))
                            for rect in dirtyRects:
                                dirtyPath.addRect(rect)
                            with QtGui.QPainter(self.viewportPanRaster) as panPainter:
                                panPainter.setFont(painter.font())
                                panPainter.setClipPath(dirtyPath)
                                panPainter.fillRect(drawingRect, QtGui.QColor(themeColors["canvas"]))
                                self.DrawGridBackground(panPainter, drawingRect, origin, pixelsPerMillimeter, gridOnly = True)
                                panPainter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                                self.viewportPanState = self.DrawScene(panPainter, drawingRect, origin, pixelsPerMillimeter,
                                                                      dirtyRects = dirtyRects, drawAnnotations = not self.showMeasurements, retainAnnotations = True)
                                if not self.showMeasurements:
                                    self.DrawLabels(panPainter, pixelsPerMillimeter, self.viewportPanState[1],
                                                drawOutlines = False, drawingRect = drawingRect, dirtyRects = dirtyRects)
                    else:
                        self.viewportPanRaster = self.viewportBackground
                        self.viewportBackground = self.viewportBackgroundKey = None
                        with QtGui.QPainter(self.viewportPanRaster) as panPainter:
                            panPainter.setFont(painter.font())
                            panPainter.setClipRect(drawingRect)
                            panPainter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                            self.viewportPanState = self.DrawScene(panPainter, drawingRect, origin, pixelsPerMillimeter,
                                                                  drawAnnotations = not self.showMeasurements, retainAnnotations = True)
                            if not self.showMeasurements:
                                self.DrawLabels(panPainter, pixelsPerMillimeter, self.viewportPanState[1],
                                            drawOutlines = False, drawingRect = drawingRect)
                    self.viewportPanKey, self.viewportPanOrigin = panKey, QtCore.QPointF(origin)
                    painter.setClipRect(rasterRect)
                    painter.drawPixmap(0, 0, self.viewportPanRaster)
                    painter.setClipRect(drawingRect)
                    sceneState = self.viewportPanState
                    if self.showMeasurements:
                        self.DrawSceneMeasurements(painter, drawingRect, sceneState, retainCommands = True)
                        self.DrawLabels(painter, pixelsPerMillimeter, sceneState[1],
                                        drawOutlines = False, drawingRect = drawingRect, commandKey = panKey)
                else:
                    self.viewportPanRaster = self.viewportPanKey = self.viewportPanState = None
                    sceneState = (self.DrawEditScene(painter, drawingRect, rasterRect, origin, pixelsPerMillimeter, backgroundKey)
                                  if cacheEdit else None)
                    if sceneState is None:
                        sceneState = self.DrawScene(painter, drawingRect, origin, pixelsPerMillimeter, retainAnnotations = stableScene)
                        self.DrawLabels(painter, pixelsPerMillimeter, sceneState[1],
                                        drawOutlines = False, drawingRect = drawingRect)
            (highlightedObjects, highlightedIds, selectedVertexKeys, invalidWalls, invalidCounterIds, invalidStairs,
             visibleWalls, visibleCounters, visibleWindows, visibleStairs, visibleRailings, visibleArrows, visibleGuides) = sceneState
            if self.referenceImage is not None and self.referenceImage.active:
                self.DrawReferenceFocus(painter, drawingRect, origin, pixelsPerMillimeter, backgroundKey)
                self.DrawSnapGuides(painter, drawingRect)
            else:
                self.rasterCacheBudget.Clear("referenceFocus", "inactive")
            # Inspection highlights are presentation-only and never enter scene
            # caches, project data or export rendering. Include hidden targets.
            problemHighlights = ((self.potentialProblemObjects, "warningOutline"), (self.problemObjects, "invalidOutline"))
            for problemObjects, color in problemHighlights:
                if not problemObjects:
                    continue
                painter.save()
                painter.setPen(QtGui.QPen(QtGui.QColor(themeColors[color]), 2, QtCore.Qt.PenStyle.DashLine))
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                for obj in problemObjects:
                    try:
                        corners = self.ObjectCorners(obj)
                        if corners and all(math.isfinite(point.x()) and math.isfinite(point.y()) for point in corners):
                            painter.drawPolygon(QtGui.QPolygonF([self.WorldToViewport(point) for point in corners]))
                    except (ValueError, ZeroDivisionError, OverflowError):
                        # Unrepresentable geometry is still listed in the window.
                        continue
                painter.restore()
            # Nearby handles do not depend on Snap. Draw the selection last at shared vertices.
            handleWalls = [wall for wall in visibleWalls + visibleCounters + visibleWindows + visibleStairs + visibleRailings + visibleArrows + visibleGuides if id(wall) not in highlightedIds]
            if self.selectedWall is not None and self.inactiveOpeningPreview is None:
                handleWalls.extend(highlightedObjects)
            hoverPosition = self.hoverPosition
            if hoverPosition is not None and not drawingRect.contains(hoverPosition):
                hoverPosition = None
            hoveredWall, hoveredVertex = (None, None)
            hoverHit = None
            if (self.pendingWall is None and self.dragStart is None and hoverPosition is not None
                    and not self.isPanning and self.inactiveOpeningPreview is None):
                hoverHit = self.HitTest(hoverPosition)
                hoveredWall, hoveredVertex, hoveredHandle = self.SelectionTarget(hoverPosition, hoverHit = hoverHit)
                if hoveredWall is not None and not self.IsObjectVisible(hoveredWall):
                    hoveredWall, hoveredVertex = None, None
                if hoveredVertex is not None:
                    handleWalls = [wall for wall in handleWalls if wall is not hoveredWall] + [hoveredWall]
            self.UpdateCanvasCursor(hoverHit = hoverHit)
            self.hoveredAngleGuide = (hoveredWall if isinstance(hoveredWall, AngleGuide)
                                      and not self.guiDragActive and self.openingPlacementMode is None
                                      and self.boxStart is None and not self.exportOverlay.active
                                      and not (self.referenceImage is not None and self.referenceImage.active) else None)
            if self.hoveredAngleGuide is not None and id(self.hoveredAngleGuide) not in highlightedIds:
                # Keep this transient preview outside the retained scene and
                # measurement pictures; it must never appear in exports.
                self.DrawAngleGuide(painter, self.hoveredAngleGuide, False, hovered = True)
            worldHover = self.ViewportToWorld(hoverPosition) if hoverPosition is not None else None
            hoverMargin = self.vertexHoverRange / pixelsPerMillimeter
            for wall in handleWalls:
                if isinstance(wall, (Furnishing, Label, Pillar, Fireplace)):
                    continue
                isSelected = id(wall) in highlightedIds and self.inactiveOpeningPreview is None
                angleHovered = wall is self.hoveredAngleGuide and not isSelected
                if not isSelected:
                    if hoverPosition is None:
                        continue
                    bounds = self.ObjectFootprint(wall)[0]
                    if not bounds.adjusted(-hoverMargin, -hoverMargin, hoverMargin, hoverMargin).contains(worldHover):
                        continue
                for vertexIndex, vertex in enumerate(ObjectControlPoints(wall)):
                    position = self.WorldToViewport(vertex)
                    if not isSelected and not angleHovered and (hoverPosition is None or QtCore.QLineF(position, hoverPosition).length() > self.vertexHoverRange):
                        continue
                    isHovered = wall is hoveredWall and vertexIndex == hoveredVertex
                    if angleHovered:
                        hoverColor = self.AngleHoverColor()
                        painter.setPen(QtGui.QPen(hoverColor, 1.5))
                        painter.setBrush(hoverColor if isHovered else QtGui.QColor(themeColors["canvas"]))
                        painter.drawEllipse(position, 7, 7)
                        continue
                    painter.setPen(QtGui.QPen(QtGui.QColor(themeColors["invalidOutline"] if wall in invalidStairs or id(wall) in invalidWalls or id(wall) in invalidCounterIds else
                                                         self.SelectionColor(wall) if isSelected else themeColors["selectionOutline"] if isHovered else themeColors["wallOutline"]), 1.5))
                    painter.setBrush(QtGui.QColor(themeColors["invalidOutline"] if (wall in invalidStairs or id(wall) in invalidWalls or id(wall) in invalidCounterIds) and isSelected and (id(wall), vertexIndex) in selectedVertexKeys else
                                                 self.SelectionColor(wall) if wall not in invalidStairs and id(wall) not in invalidWalls and id(wall) not in invalidCounterIds and isSelected and (id(wall), vertexIndex) in selectedVertexKeys else
                                                 themeColors["selectionOutline"] if wall not in invalidStairs and id(wall) not in invalidWalls and id(wall) not in invalidCounterIds and isHovered else themeColors["windowBackground"]))
                    painter.drawEllipse(position, 7, 7)
            self.DrawLabels(painter, pixelsPerMillimeter, highlightedIds, hoveredWall,
                            drawText = False, drawingRect = drawingRect)
            # Selection bounds are interaction overlays, independent of scene draw priority.
            handleMembers = self.furnishingHandleDrag["members"] if self.furnishingHandleDrag is not None else []
            invalidHandleGroup = any(self.furnishingValidationCache.get(id(state[0]), (None, False))[1]
                                     for state in handleMembers)
            memberIds = {id(state[0]) for state in handleMembers}
            for furnishing in self.furnishings:
                if id(furnishing) not in highlightedIds or not self.IsObjectVisible(furnishing):
                    continue
                invalid = (self.furnishingValidationCache.get(id(furnishing), (None, False))[1]
                           or id(furnishing) in memberIds and invalidHandleGroup)
                painter.save()
                if invalid:
                    painter.setOpacity(.4)
                painter.setPen(QtGui.QPen(QtGui.QColor(themeColors["invalidOutline"] if invalid else self.SelectionColor(furnishing)), 1.5))
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawPolygon(self.WallPolygon(furnishing))
                painter.restore()
            self.DrawFurnishingHandles(painter, hoverHit)
            if len(highlightedObjects) > 1:
                corners = [self.WorldToViewport(corner) for obj in highlightedObjects for corner in self.ObjectCorners(obj)]
                if corners:
                    bounds = QtCore.QRectF(QtCore.QPointF(min(corner.x() for corner in corners), min(corner.y() for corner in corners)),
                                          QtCore.QPointF(max(corner.x() for corner in corners), max(corner.y() for corner in corners)))
                    painter.setPen(QtGui.QPen(QtGui.QColor(themeColors["selectionOutline"]), 1, QtCore.Qt.PenStyle.DashLine))
                    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                    painter.drawRect(bounds)
            if self.boxStart is not None and self.boxEnd is not None:
                painter.setPen(QtGui.QPen(QtGui.QColor(themeColors["selectionOutline"]), 1, QtCore.Qt.PenStyle.DashLine))
                painter.setBrush(QtGui.QColor(themeColors["selectionBoxFill"]))
                painter.drawRect(QtCore.QRectF(self.boxStart, self.boxEnd).normalized())
            painter.restore()

            self.DrawRulerFrame(painter, self.viewportRulerUnit)
            overlayTop = drawingRect.top() + 12
            if self.hiddenObjects:
                painter.save()
                painter.setFont(self.font())
                count = len(self.hiddenObjects)
                label = f"({count} {'object' if count == 1 else 'objects'} hidden)"
                labelRect = QtCore.QRectF(drawingRect.left() + 12, overlayTop,
                                          painter.fontMetrics().horizontalAdvance(label) + 16, painter.fontMetrics().height() + 10)
                painter.fillRect(labelRect, QtGui.QColor(themeColors["overlayFill"]))
                painter.setPen(QtGui.QColor(themeColors["rulerText"]))
                painter.drawText(labelRect, QtCore.Qt.AlignmentFlag.AlignCenter, label)
                overlayTop = labelRect.bottom() + 8
                painter.restore()
            infoRows = []
            infoObject = None
            reference = self.referenceImage if self.referenceImage is not None and self.referenceImage.active else None
            referenceDrag = reference.drag if reference is not None else None
            referenceMode = ((referenceDrag["handle"][0] if referenceDrag["handle"] is not None else "move")
                             if referenceDrag is not None and referenceDrag["moved"] else None)
            if referenceMode == "rotate":
                angle = round(reference.state["angle"] % 360, 1) % 360
                infoRows = [("Angle", f"{angle:g}\u00b0")]
            elif referenceMode == "resize":
                infoObject = reference.proxy
            elif self.pendingWall is not None and self.wallDrawShape == "circle" and self.pendingShapeWalls:
                lengths = [QtCore.QLineF(wall.firstVertex, wall.secondVertex).length() for wall in self.pendingShapeWalls]
                shortest, longest = min(lengths), max(lengths)
                lengthText = FormatLength(shortest, self.unitsMode)
                if longest - shortest > .0001:
                    lengthText += " \u2013 " + FormatLength(longest, self.unitsMode)
                infoRows = [("Segments", str(len(lengths))), ("Segment Length", lengthText)]
            elif self.furnishingHandleDrag is not None:
                infoObject = self.furnishingHandleDrag["object"]
                if self.furnishingHandleDrag["handle"][0] == "rotate":
                    angle = round(infoObject.angle % 360, 1) % 360
                    infoRows = [("Angle", f"{angle:g}\u00b0")]
                    infoObject = None
            elif self.dragStart is not None and self.selectedVertex is not None:
                infoObject = self.selectedWall
            if infoObject is not None:
                length = QtCore.QLineF(infoObject.firstVertex, infoObject.secondVertex).length()
                lengthUnit = PropertyUnit("length", infoObject, "Adaptive Metric")[1]
                widthUnit = PropertyUnit("width", infoObject, "Adaptive Metric")[1]
                infoRows = [("Length", FormatLength(length, self.unitsMode, adaptive = lengthUnit))]
                if not isinstance(infoObject, MeasurementGuide):
                    infoRows.append(("Width", FormatLength(infoObject.width, self.unitsMode, adaptive = widthUnit)))
            if infoRows:
                painter.save()
                painter.setClipRect(drawingRect)
                painter.setFont(self.font())
                metrics = painter.fontMetrics()
                keyWidth = max(metrics.horizontalAdvance(key) for key in
                               [row[0] for row in toolTipRows.values()] + ["Segments", "Segment Length", "Length", "Width", "Angle"])
                valueWidth = max(metrics.horizontalAdvance(value) for key, value in infoRows)
                labelRect = QtCore.QRectF(drawingRect.left() + 12, overlayTop,
                                          keyWidth + 16 + valueWidth + 16,
                                          metrics.lineSpacing() * len(infoRows) + 10)
                painter.fillRect(labelRect, QtGui.QColor(themeColors["overlayFill"]))
                for index, (key, value) in enumerate(infoRows):
                    baseline = labelRect.top() + 5 + metrics.ascent() + index * metrics.lineSpacing()
                    painter.setPen(QtGui.QColor(themeColors["rulerText"]))
                    painter.drawText(QtCore.QPointF(labelRect.left() + 8, baseline), key)
                    painter.setPen(QtGui.QColor(themeColors["objectOutline"]))
                    painter.drawText(QtCore.QPointF(labelRect.left() + 8 + keyWidth + 16, baseline), value)
                overlayTop = labelRect.bottom() + 8
                painter.restore()
            tips = []
            if reference is not None:
                if reference.calibration.active:
                    if reference.calibration.draggedPoint is not None:
                        tips = ["angle", "cancelMove"]
                    else:
                        tips = ["calibrationConfirm" if len(reference.calibration.points) == 2 else "calibrationPlace", "calibrationCancel"]
                elif referenceMode is not None:
                    tips = ["cancelMove"]
                    if referenceMode == "resize":
                        tips.insert(0, "center")
                    elif referenceMode in ("move", "pivot"):
                        tips.insert(0, "axes")
            elif self.pendingWall is not None:
                if self.wallDrawShape in ("square", "circle"):
                    tips = ["segments"] if self.wallDrawShape == "circle" else []
                    tips.extend([self.wallDrawShape, "center", "cancelDraw"])
                else:
                    tips = ["angle", "cancelDraw"]
            elif self.guiDragActive and not self.guiDragCancelled:
                tips = ["cancelMove"]
                if (isinstance(self.windowDropPreview, Window)
                        and not isinstance(self.windowDropPreview, OpenDoorway)):
                    tips.insert(0, "hinge" if isinstance(self.windowDropPreview, SwingingDoor) else "face")
            elif self.openingPlacementMode is not None:
                doorMode = self.openingPlacementMode == "Door"
                tips = ["doorType" if doorMode else "windowType"]
                if isinstance(self.windowDropPreview, Window):
                    if not isinstance(self.windowDropPreview, OpenDoorway):
                        tips.insert(0, "hinge" if isinstance(self.windowDropPreview, SwingingDoor) else "face")
                    tips.append("placeDoor" if doorMode else "placeWindow")
                tips.append("releaseDoor" if doorMode else "releaseWindow")
            elif self.furnishingHandleDrag is not None:
                tips = ["cancelMove"]
                if self.furnishingHandleDrag["handle"][0] == "resize":
                    tips.insert(0, "center")
                if self.furnishingHandleDrag["handle"][0] == "rotate":
                    tips.insert(0, "duplicate")
                if self.furnishingHandleDrag["handle"][0] == "pivot":
                    tips.insert(0, "localAxes" if self.localTransforms else "axes")
            elif self.dragStart is not None and self.selectedWall is not None:
                wholeObjects = (all(index is None for obj, index in self.groupSourceEntries)
                                if self.groupDrag else self.selectedVertex is None)
                tips = ["duplicate"] if wholeObjects else ["center" if isinstance(self.selectedWall, Window) else "extrude"]
                if not wholeObjects:
                    controlTip = None if isinstance(self.selectedWall, Window) else "localAngle" if self.localTransforms else "angle"
                elif (not self.groupDrag and isinstance(self.selectedWall, Window)
                      and not isinstance(self.selectedWall, OpenDoorway) and self.inactiveOpeningPreview is None):
                    controlTip = "hinge" if isinstance(self.selectedWall, SwingingDoor) else "face"
                elif (not self.groupDrag and isinstance(self.selectedWall, Window)
                      and not isinstance(self.selectedWall, OpenDoorway)):
                    controlTip = None
                else:
                    controlTip = "localAxes" if self.localTransforms else "axes"
                if controlTip is not None:
                    tips.append(controlTip)
                if (not wholeObjects and not isinstance(self.selectedWall, Window)
                        and self.isDragging and self.axisConstraintOrigin is not None):
                    tips.append("axisOrigin")
                tips.append("cancelMove")
            elif (self.dragStart is None and self.boxStart is None and self.rightClickStart is None
                  and not self.isPanning and self.openingPlacementMode is None
                  and all(preview is None for preview in (self.furnishingPreview, self.labelPreview,
                                                          self.counterPreview, self.windowDropPreview, self.inactiveOpeningPreview))
                  and not self.objectContextMenu.isVisible()):
                tips = ["select", "placeWall", "holdDoor", "holdWindow", "thickness", "searchFurnishings"]
            if self.exportOverlay.active:
                tips = []
            if tips and self.showTips:
                painter.save()
                painter.setClipRect(drawingRect)
                painter.setFont(self.font())
                metrics = painter.fontMetrics()
                keyWidth = max(metrics.horizontalAdvance(key) for key in
                               [row[0] for row in toolTipRows.values()] + ["Segments", "Segment Length", "Length", "Width", "Angle"])
                descriptionWidth = max(metrics.horizontalAdvance(description) for key, description in toolTipRows.values())
                labelRect = QtCore.QRectF(drawingRect.left() + 12, overlayTop,
                                          keyWidth + 16 + descriptionWidth + 16,
                                          metrics.lineSpacing() * len(tips) + 10)
                painter.fillRect(labelRect, QtGui.QColor(themeColors["overlayFill"]))
                for index, tip in enumerate(tips):
                    key, description = toolTipRows[tip]
                    baseline = labelRect.top() + 5 + metrics.ascent() + index * metrics.lineSpacing()
                    painter.setPen(QtGui.QColor(themeColors["objectOutline"]))
                    painter.drawText(QtCore.QPointF(labelRect.left() + 8, baseline), key)
                    painter.setPen(QtGui.QColor(themeColors["rulerText"]))
                    painter.drawText(QtCore.QPointF(labelRect.left() + 8 + keyWidth + 16, baseline), description)
                painter.restore()
            if self.clipboardError:
                painter.save()
                painter.setClipRect(drawingRect)
                painter.setFont(self.font())
                textFlags = QtCore.Qt.AlignmentFlag.AlignCenter | QtCore.Qt.TextFlag.TextWordWrap
                textWidth = max(1, drawingRect.width() - 56)
                textRect = painter.fontMetrics().boundingRect(QtCore.QRect(0, 0, int(textWidth), 1000),
                                                             textFlags, self.clipboardError)
                overlayRect = QtCore.QRectF(0, 0, textRect.width() + 24, textRect.height() + 20)
                overlayRect.moveCenter(QtCore.QPointF(drawingRect.center().x(),
                                                      drawingRect.bottom() - 16 - overlayRect.height() / 2))
                painter.setPen(QtGui.QPen(QtGui.QColor(themeColors["errorBorder"]), 1))
                painter.setBrush(QtGui.QColor(themeColors["errorFill"]))
                painter.drawRoundedRect(overlayRect, 5, 5)
                painter.setPen(QtGui.QColor(themeColors["errorText"]))
                painter.drawText(overlayRect.adjusted(12, 10, -12, -10), textFlags, self.clipboardError)
                painter.restore()
            painter.save()
            painter.setClipRect(drawingRect)
            painter.setFont(self.font())
            if hoverPosition is not None:
                position = self.ViewportToWorld(hoverPosition)
                if self.dragStart is not None and self.selectedWall is not None:
                    obj = (self.furnishingHandleDrag["object"] if self.furnishingHandleDrag is not None else
                           self.inactiveOpeningPreview if self.inactiveOpeningPreview is not None else self.selectedWall)
                    if self.selectedVertex is not None and self.furnishingHandleDrag is None:
                        position = obj.firstVertex if self.selectedVertex == 0 else obj.secondVertex
                    else:
                        position = obj.origin if isinstance(obj, Label) else (obj.firstVertex + obj.secondVertex) / 2
                elif self.pendingWall is not None:
                    position = self.pendingWall.secondVertex
                else:
                    preview = (self.labelPreview if self.labelPreview is not None else self.furnishingPreview if self.furnishingPreview is not None else
                               self.windowDropPreview if self.windowDropPreview is not None else self.inactiveOpeningPreview)
                    if preview is not None:
                        position = preview.origin if isinstance(preview, Label) else (preview.firstVertex + preview.secondVertex) / 2
                if self.unitsMode in imperialModes:
                    label = f"x: {FormatLength(position.x(), self.unitsMode)}   y: {FormatLength(position.y(), self.unitsMode)}"
                else:
                    divisor, unit = MetricUnit(self.unitsMode)
                    decimals = 0 if self.unitsMode == "Millimeters" else 3
                    x = round(position.x() / divisor, decimals) or 0.0
                    y = round(position.y() / divisor, decimals) or 0.0
                    label = f"x: {x:.{decimals}f} {unit}   y: {y:.{decimals}f} {unit}"
            else:
                label = "x: --   y: --"
            labelRect = QtCore.QRectF(0, 0, painter.fontMetrics().horizontalAdvance(label) + 16,
                                      painter.fontMetrics().height() + 10)
            labelRect.moveBottomRight(QtCore.QPointF(drawingRect.right() - 12,
                                       overlayRect.top() - 8 if self.clipboardError else drawingRect.bottom() - 12))
            painter.fillRect(labelRect, QtGui.QColor(themeColors["overlayFill"]))
            painter.setPen(QtGui.QColor(themeColors["rulerText"]))
            painter.drawText(labelRect, QtCore.Qt.AlignmentFlag.AlignCenter, label)
            painter.restore()
            self.exportOverlay.Draw(painter, drawingRect)
            if self.referenceImage is not None:
                self.referenceImage.DrawHandles(painter, drawingRect)
        self.renderSamples.append((renderStart, (perf_counter() - renderStart) * 1000.0))

    def DrawReferenceFocus(self, painter, drawingRect, origin, pixelsPerMillimeter, backgroundKey):
        # Blend the original background back over scene ink, preserving the
        # image's color/opacity and leaving normal scene caches untouched.
        ratio = self.devicePixelRatioF()
        width, height = math.ceil(self.width() * ratio), math.ceil(self.height() * ratio)
        if self.referenceFocusKey != backgroundKey:
            if self.rasterCacheBudget.Prepare("referenceFocus", width * height * 4,
                                             preserve = ("background", "scene", "pan", "edit")):
                background = QtGui.QPixmap(width, height)
                background.setDevicePixelRatio(ratio)
                background.fill(QtGui.QColor(themeColors["canvas"]))
                with QtGui.QPainter(background) as backgroundPainter:
                    self.DrawGridBackground(backgroundPainter, drawingRect, origin, pixelsPerMillimeter)
                self.referenceFocusBackground, self.referenceFocusKey = background, backgroundKey
        painter.save()
        painter.setClipRect(drawingRect, QtCore.Qt.ClipOperation.IntersectClip)
        painter.setOpacity(.5)
        if self.referenceFocusBackground is not None:
            painter.drawPixmap(0, 0, self.referenceFocusBackground)
        else:
            # Bounded temporary tiles retain the effect under a tight cache budget.
            for top in range(0, height, 256):
                for left in range(0, width, 256):
                    tile = QtGui.QPixmap(min(256, width - left), min(256, height - top))
                    tile.setDevicePixelRatio(ratio)
                    tile.fill(QtGui.QColor(themeColors["canvas"]))
                    with QtGui.QPainter(tile) as tilePainter:
                        tilePainter.translate(-left / ratio, -top / ratio)
                        self.DrawGridBackground(tilePainter, drawingRect, origin, pixelsPerMillimeter)
                    painter.drawPixmap(QtCore.QPointF(left / ratio, top / ratio), tile)
        painter.restore()

    def DrawSnapGuides(self, painter, drawingRect):
        calibrationDragging = (self.referenceImage is not None and self.referenceImage.active
                               and self.referenceImage.calibration.active and self.referenceImage.calibration.draggedPoint is not None)
        if self.axisConstraintOrigin is not None and (self.dragStart is not None and self.isDragging or self.pendingWall is not None or calibrationDragging):
            position = self.WorldToViewport(self.axisConstraintOrigin)
            painter.save()
            painter.setClipRect(drawingRect)
            painter.setPen(QtGui.QPen(QtGui.QColor(themeColors["selectionOutline"]), 1,
                                     QtCore.Qt.PenStyle.DashLine))
            vertexDrag = (calibrationDragging or self.dragStart is not None and self.selectedVertex is not None
                          and not isinstance(self.selectedWall, Window)
                          and not (isinstance(self.selectedWall, AngleGuide) and self.selectedVertex == 2))
            if self.axisConstraintDirection is not None:
                extent = math.hypot(self.width(), self.height()) * 2
                axis = self.axisConstraintDirection
                direction = QtCore.QPointF(axis.x(), -axis.y()) * extent
                painter.drawLine(QtCore.QLineF(position - direction, position + direction))
            elif vertexDrag:
                # At the origin there is no selected ray yet.
                pass
            elif self.localTransforms:
                extent = math.hypot(self.width(), self.height()) * 2
                for axis in self.TranslationAxes():
                    direction = QtCore.QPointF(axis.x(), -axis.y()) * extent
                    painter.drawLine(QtCore.QLineF(position - direction, position + direction))
            else:
                painter.drawLine(QtCore.QLineF(position.x(), drawingRect.top(), position.x(), drawingRect.bottom()))
                painter.drawLine(QtCore.QLineF(drawingRect.left(), position.y(), drawingRect.right(), position.y()))
            painter.restore()
        if self.alignmentGuides and (self.dragStart is not None or self.pendingWall is not None or self.windowDropPreview is not None or self.furnishingPreview is not None or calibrationDragging):
            for axis, coordinate in self.alignmentGuides:
                position = self.WorldToViewport(QtCore.QPointF(coordinate, coordinate))
                painter.save()
                painter.setClipRect(drawingRect)
                painter.setPen(QtGui.QPen(QtGui.QColor(themeColors["selectionOutline"]), 1.5))
                if axis == 0:
                    painter.drawLine(QtCore.QLineF(position.x(), drawingRect.top(), position.x(), drawingRect.bottom()))
                else:
                    painter.drawLine(QtCore.QLineF(drawingRect.left(), position.y(), drawingRect.right(), position.y()))
                painter.restore()

    def SceneRenderKey(self, backgroundKey, appearanceRevision = None):
        diagnostics = self.renderDiagnostics if self.renderDiagnostics is not None and self.renderDiagnostics.enabled else None
        started = perf_counter() if diagnostics is not None else None
        changes = self.renderChanges
        selection = self.pendingShiftSelection[0] if self.pendingShiftSelection is not None else self.SelectionEntries()
        key = (backgroundKey, palette.labelFont, changes.geometry, changes.appearance, changes.topology,
               changes.DefinitionKeys(),
               tuple(self.lineWidths.items()), tuple((id(obj), index) for obj, index in selection),
               changes.visibility, tuple(self.visibility.items()), self.showMeasurements, self.measurementPrecision,
               tuple(self.measurementVisibility.items()), tuple(self.measurementSettings.items()), self.wallMeasurementMode, self.wallMeasurementReference,
               tuple(self.collisionSettings.items()), getattr(self, "exportRender", False))
        if self.verifyRenderRevisions:
            reference = self.SceneRenderValueKey(backgroundKey)
            previous = self.renderRevisionReference
            if previous is not None and previous[0] == key and previous[1] != reference:
                raise AssertionError("Scene mutation bypassed render revisions")
            self.renderRevisionReference = (key, reference)
        if diagnostics is not None:
            diagnostics.RecordPhase("scene-key", started)
        if appearanceRevision is not None:
            key = key[:3] + (appearanceRevision,) + key[4:]
        return key

    def SceneRenderValueKey(self, backgroundKey):
        diagnostics = self.renderDiagnostics if self.renderDiagnostics is not None and self.renderDiagnostics.enabled else None
        started = perf_counter() if diagnostics is not None else None
        # Capture mutable properties as values: settings/property tools and
        # history can edit objects in place without changing sceneRevision.
        objectKeys = []
        for obj in self.walls + self.windows + self.furnishings + self.labels:
            first, second = obj.firstVertex, obj.secondVertex
            key = (id(obj), type(obj), first.x(), first.y(), second.x(), second.y(), obj.width, obj.measurementHidden)
            if isinstance(obj, MeasurementGuide):
                key += (obj.textOffset.x(), obj.textOffset.y())
            if isinstance(obj, DashedLine):
                key += (obj.weightClass,)
            if isinstance(obj, AngleGuide):
                key += (obj.middleVertex.x(), obj.middleVertex.y())
            if isinstance(obj, Window):
                key += (id(obj.parentWall), obj.measurementFlipped,
                        getattr(obj, "hingeAtSecond", None), getattr(obj, "swingsOutwards", None),
                        getattr(obj, "panelsFlipped", None), getattr(obj, "sillDepth", None),
                        getattr(obj, "windowWell", False), getattr(obj, "wellDepth", 600.0), getattr(obj, "wellDashed", False))
                if isinstance(obj, Fireplace):
                    key += (obj.depth, obj.depthOffset, obj.material)
            elif isinstance(obj, Label):
                key += (obj.text, obj.intensity)
            elif isinstance(obj, NorthArrow):
                key += (obj.intensity,)
            elif isinstance(obj, Furnishing):
                definitionKey = obj.definition["key"]
                key += (definitionKey, id(self.furnishingRenderers[definitionKey]),
                        id(self.selectedFurnishingRenderers[definitionKey]), obj.flipHorizontal, obj.flipVertical)
            else:
                key += (obj.material, obj.firstMiter, obj.secondMiter)
                if isinstance(obj, Stair):
                    key += (obj.directionReversed, obj.autosize, obj.manualStepCount, obj.stepSizeBounds)
                elif isinstance(obj, Railing):
                    key += (obj.autosize, obj.manualPostCount, obj.spacingBounds)
                elif isinstance(obj, Arrow):
                    key += (obj.solidTip, obj.tipSize, obj.intensity)
            objectKeys.append(key)
        selection = self.pendingShiftSelection[0] if self.pendingShiftSelection is not None else self.SelectionEntries()
        key = (backgroundKey, palette.labelFont, tuple(self.lineWidths.items()), tuple(objectKeys), tuple((id(obj), index) for obj, index in selection),
                tuple(tuple(id(obj) for obj in group) for group in self.objectGroups),
                frozenset(self.hiddenObjectIds), tuple(self.visibility.items()), self.showMeasurements, self.measurementPrecision,
                tuple(self.measurementVisibility.items()), tuple(self.measurementSettings.items()), self.wallMeasurementMode, self.wallMeasurementReference,
                tuple(self.collisionSettings.items()), getattr(self, "exportRender", False))
        if diagnostics is not None:
            diagnostics.RecordPhase("scene-key", started)
        return key

    def DrawScene(self, painter, drawingRect, origin, pixelsPerMillimeter, dirtyRects = None,
                  drawAnnotations = True, retainAnnotations = False):
        if not self.solidObjects:
            device = ObjectPaintDevice(self.size(), themeColors["canvas"])
            sourcePainter = QtGui.QPainter(device)
            originalRenderers = (self.furnishingRenderers, self.selectedFurnishingRenderers, self.groupedFurnishingRenderers)
            try:
                sourcePainter.setFont(painter.font())
                sourcePainter.setRenderHints(painter.renderHints())
                sourcePainter.setClipRect(drawingRect)
                self.solidObjects = True
                self.objectCaptureEngine = device.engine
                self.furnishingRenderers, self.selectedFurnishingRenderers, self.groupedFurnishingRenderers = (
                    (renderers.Copy(solidBackground = True) if hasattr(renderers, "Copy") else
                     {key: getattr(renderer, "solidRenderer", renderer) for key, renderer in renderers.items()})
                    for renderers in originalRenderers)
                sceneState = self.DrawScene(sourcePainter, drawingRect, origin, pixelsPerMillimeter,
                                            dirtyRects, drawAnnotations = False)
            finally:
                sourcePainter.end()
                self.solidObjects = False
                self.objectCaptureEngine = None
                self.furnishingRenderers, self.selectedFurnishingRenderers, self.groupedFurnishingRenderers = originalRenderers
            device.engine.Replay(painter, drawingRect, clipCache = self.objectClipCache)
            if drawAnnotations:
                self.DrawSceneMeasurements(painter, drawingRect, sceneState, dirtyRects, retainCommands = retainAnnotations)
            return sceneState
        stablePreparation = (self.dragStart is None and not self.isDragging and self.pendingWall is None
                             and not self.pendingShapeWalls and self.furnishingHandleDrag is None and not self.guiDragActive
                             and all(preview is None for preview in (self.furnishingPreview, self.windowDropPreview,
                                     self.inactiveOpeningPreview, self.counterPreview, self.arrowPreview, self.labelPreview)))
        changes = self.renderChanges
        preparationKey = (changes.geometry, changes.appearance, changes.topology, changes.visibility,
                          tuple(self.visibility.items()), tuple(self.collisionSettings.items()),
                          getattr(self, "exportRender", False), self.basePixelsPerMillimeter)
        preparation = getattr(self, "scenePreparation", None)
        if not stablePreparation or preparation is None or preparation[0] != preparationKey:
            prepared = {}
            if stablePreparation:
                self.scenePreparation = (preparationKey, prepared)
        else:
            prepared = preparation[1]
        containedObjects = prepared.get("containedObjects")
        if containedObjects is None:
            containedObjects = prepared["containedObjects"] = ([] if getattr(self, "exportRender", False) else
                self.ContainedWalls([obj for obj in self.walls if self.IsObjectVisible(obj)]))
        advisoryIds = prepared.get("architecturalAdvisories")
        if advisoryIds is None:
            advisoryIds = prepared["architecturalAdvisories"] = ({id(obj) for obj in containedObjects + self.DuplicateArchitecturalObjects()}
                if not getattr(self, "exportRender", False) else set())
        invalidArchitecture = prepared.get("invalidArchitecture")
        if invalidArchitecture is None:
            invalidArchitecture = prepared["invalidArchitecture"] = {
                id(obj) for obj in self.walls + self.windows
                if not getattr(self, "exportRender", False) and self.IsObjectVisible(obj)
                and (isinstance(obj, Window) or type(obj) in (Wall, Pillar, Column, Counter, Stair, Railing, Elevator))
                and not self.ArchitecturalPlacementFits(obj)}
        highlightedWall = (self.windowDropPreview if self.windowDropPreview is not None else
                           self.counterPreview if self.counterPreview is not None else
                           self.pendingWall if self.pendingWall is not None else
                           None if self.inactiveOpeningPreview is not None and self.dragStart is not None else self.selectedWall)
        renderedSelection = (self.pendingShiftSelection[0] if self.pendingShiftSelection is not None and not self.isDragging
                             else self.SelectionEntries())
        highlightedObjects = [obj for obj, index in renderedSelection]
        if self.inactiveOpeningPreview is not None:
            highlightedObjects = []
        if self.windowDropPreview is not None or self.counterPreview is not None or self.pendingWall is not None:
            highlightedObjects = self.pendingShapeWalls or [highlightedWall]
        highlightedObjects = list({id(obj): obj for obj in highlightedObjects}.values())
        highlightedObjects = [obj for obj in highlightedObjects if self.IsObjectVisible(obj)]
        highlightedIds = {id(obj) for obj in highlightedObjects}
        groupedIds = prepared.get("groups")
        if groupedIds is None:
            groupedIds = prepared["groups"] = {id(obj) for group in self.objectGroups for obj in group}
        movingFurnishingIds = {id(obj) for obj, index, position in self.ActiveAttachments() if isinstance(obj, Furnishing)}
        if isinstance(self.selectedWall, Furnishing) and self.dragStart is not None:
            movingFurnishingIds.add(id(self.selectedWall))
        handleMembers = self.furnishingHandleDrag["members"] if self.furnishingHandleDrag is not None else []
        handleMemberIds = {id(state[0]) for state in handleMembers}
        movingFurnishingIds.update(handleMemberIds)
        handleState = self.furnishingHandleDrag
        invalidHandleGroup = (not handleState["rotationValid"] if handleState is not None and handleState.get("structuralRotation", False)
                              else any(not self.FurnishingFits(state[0]) for state in handleMembers))
        invalidWalls = {id(wall): wall for wall in self.walls
                        if type(wall) in (Wall, Pillar, Column, Elevator) and id(wall) in invalidArchitecture}
        if self.pendingShapeWalls:
            extent = self.pendingWall.secondVertex - self.pendingWall.firstVertex
            if abs(extent.x()) < 1 or abs(extent.y()) < 1 or any(not self.WallFits(wall) for wall in self.pendingShapeWalls):
                invalidWalls.update({id(wall): wall for wall in self.pendingShapeWalls})
        elif self.pendingWall is not None and not self.WallFits(self.pendingWall):
            invalidWalls[id(self.pendingWall)] = self.pendingWall
        selectedVertexKeys = {(id(obj), index) for obj, index in renderedSelection if index is not None}
        visibleCounters = prepared.get("counters")
        if visibleCounters is None:
            visibleCounters = [counter for counter in self.walls if isinstance(counter, Counter)]
            if self.counterPreview is not None:
                visibleCounters.append(self.counterPreview)
            visibleCounters = prepared["counters"] = [counter for counter in visibleCounters if self.IsObjectVisible(counter)]
        self.preparedCounterMembers = visibleCounters if stablePreparation else None
        validationKey = prepared.get("blockers")
        if validationKey is None:
            blockerKeys = []
            for wall in self.walls:
                self.ObjectFootprint(wall)
                blockerKeys.append((id(wall), wall.footprintCache[0]))
            validationKey = prepared["blockers"] = tuple(blockerKeys)
        if validationKey != self.furnishingValidationKey:
            self.furnishingValidationKey = validationKey
            self.furnishingValidationCache = {}
        validationCache = dict(self.furnishingValidationCache) if dirtyRects is not None else {}
        duplicateIds = prepared.get("duplicateFurnishings")
        if duplicateIds is None:
            duplicateIds = prepared["duplicateFurnishings"] = {id(obj) for obj in self.DuplicateFurnishings()}
        furnishingLayers = prepared.get("furnishingLayers")
        if furnishingLayers is None:
            furnishingLayers = {True: [], False: []}
            for obj in self.furnishings + ([self.furnishingPreview] if self.furnishingPreview is not None else []):
                if not isinstance(obj, NorthArrow) and self.IsObjectVisible(obj):
                    furnishingLayers[obj.behindCounters].append(obj)
            prepared["furnishingLayers"] = furnishingLayers
        furnishingBounds = prepared.setdefault("furnishingBounds", {})
        occludedFurnishings = prepared.get("occludedFurnishings")
        if occludedFurnishings is None:
            occludedFurnishings = prepared["occludedFurnishings"] = {
                id(obj) for group in self.CoincidentObjectGroups() if type(group[0]) is Furnishing for obj in group[:-1]}
        def DrawFurnishings(behindCounters):
            for obj in furnishingLayers[behindCounters]:
                # Exact rear copies cannot contribute visible artwork. Painting
                # their dark strokes under the warning leaves dark antialias fringes.
                if id(obj) in occludedFurnishings:
                    continue
                bounds = furnishingBounds.get(id(obj))
                if bounds is None:
                    bounds = self.ObjectFootprint(obj)[0].united(FurnishingArtworkBounds(obj, self.furnishingRenderers[obj.definition["key"]]))
                    furnishingBounds[id(obj)] = bounds
                screenBounds = QtCore.QRectF(self.WorldToViewport(bounds.topLeft()), self.WorldToViewport(bounds.bottomRight())).normalized()
                if not screenBounds.adjusted(-2, -2, 2, 2).intersects(drawingRect):
                    continue
                padding = self.lineWidths["furnishings"] + 2
                if dirtyRects is not None and not any(screenBounds.adjusted(-padding, -padding, padding, padding).intersects(rect) for rect in dirtyRects):
                    continue
                self.ObjectFootprint(obj)
                key = obj.footprintCache[0]
                cached = self.furnishingValidationCache.get(id(obj))
                if self.dragStart is not None and obj is not self.furnishingPreview and id(obj) not in movingFurnishingIds:
                    invalid = False
                    # Suppression is not a validated result. Keep this entry
                    # absent so release/cancel performs the real check.
                    validationCache.pop(id(obj), None)
                else:
                    invalid = cached[1] if cached is not None and cached[0] == key else not self.FurnishingFits(obj)
                    validationCache[id(obj)] = (key, invalid)
                if id(obj) in handleMemberIds and invalidHandleGroup:
                    invalid = True
                renderers = self.selectedFurnishingRenderers if id(obj) in highlightedIds and not invalid else self.furnishingRenderers
                if id(obj) in highlightedIds and id(obj) in groupedIds and not invalid:
                    key = obj.definition["key"]
                    if key not in self.groupedFurnishingRenderers:
                        self.groupedFurnishingRenderers[key] = SelectedFurnishingRenderer(obj.definition.get("graphicData") or obj.definition["imagePath"], self.SelectionColor(obj),
                            lineWidth = self.lineWidths["furnishings"], nominalSize = (obj.definition["width"], obj.definition["length"]))
                    renderers = self.groupedFurnishingRenderers
                duplicate = id(obj) in duplicateIds
                if duplicate and not invalid:
                    warningRenderers = prepared.setdefault("duplicateRenderers", {})
                    key = obj.definition["key"]
                    if key not in warningRenderers:
                        warningRenderers[key] = FurnishingRenderer(obj.definition.get("graphicData") or obj.definition["imagePath"],
                            selectionColor = themeColors["warningOutline"], lineWidth = self.lineWidths["furnishings"],
                            nominalSize = (obj.definition["width"], obj.definition["length"]))
                    renderers = warningRenderers
                painter.save()
                try:
                    DrawFurnishing(painter, obj, self.WorldToViewport(obj.firstVertex), self.WorldToViewport(obj.secondVertex),
                                   pixelsPerMillimeter, renderers[obj.definition["key"]],
                                   id(obj) in highlightedIds, invalid, selectionColor = themeColors["warningOutline"] if duplicate else self.SelectionColor(obj),
                                   drawBounds = id(obj) not in highlightedIds)
                finally:
                    painter.restore()
        DrawFurnishings(True)
        invalidCounterIds = set()
        if visibleCounters:
            painter.save()
            counterPath, _, counterPolygons = self.ConnectedCounterPath(visibleCounters, False)
            painter.fillPath(counterPath, QtGui.QColor(themeColors["canvas"]))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(LinePen(themeColors["wallOutline"], self.lineWidths["architectural"]))
            painter.drawPath(counterPath)
            movingCounterIds = {id(obj) for obj, index, position in self.ActiveAttachments() if isinstance(obj, Counter)}
            if self.dragStart is not None and isinstance(self.selectedWall, Counter):
                movingCounterIds.add(id(self.selectedWall))
            if self.counterPreview is not None:
                movingCounterIds.add(id(self.counterPreview))
            for counter in visibleCounters:
                invalid = id(counter) in invalidArchitecture or id(counter) in movingCounterIds and not self.CounterFits(counter)
                warning = id(counter) in advisoryIds or id(counter) in invalidArchitecture and self.dragStart is None
                if invalid:
                    invalidCounterIds.add(id(counter))
                if id(counter) not in highlightedIds and not invalid and not warning:
                    continue
                clip = QtGui.QPainterPath()
                clip.setFillRule(QtCore.Qt.FillRule.WindingFill)
                for owner, polygon in counterPolygons:
                    if owner is counter:
                        clip.addPolygon(polygon)
                        clip.closeSubpath()
                clip = QtGui.QTransform().translate(origin.x(), origin.y()).scale(self.zoom, self.zoom).map(clip)
                # Merging coincident counters can assign their entire surface to
                # the rear owner. The front warning still owns its footprint.
                if clip.isEmpty() and (invalid or warning):
                    clip.addPolygon(self.WallPolygon(counter))
                    clip.closeSubpath()
                painter.save()
                painter.setClipPath(clip, QtCore.Qt.ClipOperation.IntersectClip)
                if id(counter) in highlightedIds and not invalid and not warning:
                    painter.fillPath(counterPath, QtGui.QColor(themeColors["groupSelectionFill"] if id(counter) in groupedIds else themeColors["selectionFill"]))
                painter.restore()
                # Include the full stroke, rather than leaving half the normal
                # outline visible outside the surface clip.
                stroke = QtGui.QPainterPathStroker()
                stroke.setWidth(self.lineWidths["architectural"] + 2)
                painter.save()
                painter.setClipPath(clip.united(stroke.createStroke(clip)), QtCore.Qt.ClipOperation.IntersectClip)
                color = (themeColors["warningOutline"] if warning else
                         themeColors["invalidOutline"] if invalid else self.SelectionColor(counter))
                painter.setPen(LinePen(color, self.lineWidths["architectural"]))
                painter.drawPath(counterPath)
                painter.restore()
            painter.restore()
        DrawFurnishings(False)
        self.furnishingValidationCache = validationCache
        previewWalls = self.pendingShapeWalls or ([self.pendingWall] if self.pendingWall is not None else [])
        visibleWalls = prepared.get("walls")
        if visibleWalls is None:
            visibleWalls = [wall for wall in self.walls if type(wall) in (Wall, Pillar, Column)] + previewWalls
        if isinstance(self.arrowPreview, Pillar) and not isinstance(self.arrowPreview, Elevator):
            visibleWalls.append(self.arrowPreview)
            if not self.WallFits(self.arrowPreview):
                invalidWalls[id(self.arrowPreview)] = self.arrowPreview
        if "walls" not in prepared:
            visibleWalls = prepared["walls"] = [wall for wall in visibleWalls if self.IsObjectVisible(wall)]
        containedWalls = prepared.get("contained")
        if containedWalls is None:
            containedWalls = prepared["contained"] = [obj for obj in containedObjects if type(obj) in (Wall, Pillar, Column)]
            if previewWalls:
                containedWalls = prepared["contained"] = list({id(obj): obj for obj in
                    containedWalls + self.ContainedWalls(visibleWalls)}.values())
        self.preparedWallMembers = visibleWalls if stablePreparation else None
        self.preparedWallRevision = preparationKey
        combinedPath = self.ConnectedWallPath(visibleWalls)
        # Validation can reuse the exact owner fills prepared for this frame.
        if self.dragStart is not None and self.isDragging:
            movingWalls = {id(wall): wall for wall in [self.selectedWall] + [wall for wall, index, position in self.ActiveAttachments()]}
            blockers = self.furnishings + [wall for wall in self.walls if isinstance(wall, (Counter, Railing, Stair, Elevator))]
            invalidWalls.update({wallId: wall for wallId, wall in movingWalls.items()
                                 if type(wall) in (Wall, Pillar, Column, Elevator) and not self.WallFits(wall, blockers = blockers)})
        # Share one pattern origin so hatching continues across wall junctions.
        painter.setBrushOrigin(origin)
        detachedIds = {id(obj) for obj, index in self.groupEntries} if self.groupOpeningPreviews else {id(self.selectedWall)}
        visibleWindows = [opening for opening in self.windows
                          if not (self.inactiveOpeningPreview is not None and self.dragStart is not None
                                  and id(opening) in detachedIds)] + ([self.windowDropPreview] if isinstance(self.windowDropPreview, Window) else [])
        visibleWindows = [opening for opening in visibleWindows if self.IsObjectVisible(opening)]
        painter.save()
        doorwayClip = QtGui.QPainterPath()
        doorwayClip.setFillRule(QtCore.Qt.FillRule.OddEvenFill)
        doorwayClip.addRect(drawingRect)
        doorwayOpenings = QtGui.QPainterPath()
        doorwayOpenings.setFillRule(QtCore.Qt.FillRule.WindingFill)
        openingClipRect = drawingRect.adjusted(-2, -2, 2, 2)
        for opening in visibleWindows:
            if isinstance(opening, (Door, SwingingDoor, DoubleDoor, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway, Fireplace)):
                firstPoint = self.WorldToViewport(opening.firstVertex)
                secondPoint = self.WorldToViewport(opening.secondVertex)
                direction = secondPoint - firstPoint
                length = math.hypot(direction.x(), direction.y())
                if length > 1e-10:
                    openingHalfWidth = (opening.parentWall.width if isinstance(opening, Fireplace) else opening.width) * pixelsPerMillimeter / 2
                    normal = QtCore.QPointF(-direction.y(), direction.x()) / length * (openingHalfWidth + self.lineWidths["walls"])
                    if isinstance(opening, PocketDoor):
                        midpoint = (firstPoint + secondPoint) / 2
                        openingEnd = secondPoint if opening.hingeAtSecond else firstPoint
                        pocketEnd = firstPoint if opening.hingeAtSecond else secondPoint
                        pocketNormal = QtCore.QPointF(-direction.y(), direction.x()) / length * (openingHalfWidth * .4)
                        spans = ((openingEnd, midpoint, normal),) if isinstance(opening, BarnDoor) else ((openingEnd, midpoint, normal), (midpoint, pocketEnd, pocketNormal))
                        for start, end, halfWidth in spans:
                            polygon = QtGui.QPolygonF([start + halfWidth, end + halfWidth,
                                                      end - halfWidth, start - halfWidth])
                            for path in (doorwayClip, doorwayOpenings):
                                if self.isPanning and path is doorwayClip and not polygon.boundingRect().intersects(openingClipRect):
                                    continue
                                path.addPolygon(polygon)
                                path.closeSubpath()
                    else:
                        polygon = QtGui.QPolygonF([firstPoint + normal, secondPoint + normal,
                                                  secondPoint - normal, firstPoint - normal])
                        for path in (doorwayClip, doorwayOpenings):
                            if self.isPanning and path is doorwayClip and not polygon.boundingRect().intersects(openingClipRect):
                                continue
                            path.addPolygon(polygon)
                            path.closeSubpath()
        painter.setClipPath(doorwayClip, QtCore.Qt.ClipOperation.IntersectClip)
        materialKey = prepared.get("materials")
        if materialKey is None:
            materialKey = prepared["materials"] = (self.wallGeometryKey, tuple((type(wall), wall.material) for wall in visibleWalls))
        if materialKey != self.materialGeometryKey:
            self.materialPaths = {}
            self.wallMaterialPaths = {}
            ownerPolygons = {}
            for wall, polygon in self.wallFillPolygons:
                ownerPolygons.setdefault(id(wall), (wall, []))[1].append(polygon)
            columnPaths = getattr(self, "columnMaterialPaths", {})
            columnFill = QtGui.QPainterPath()
            columnFill.setFillRule(QtCore.Qt.FillRule.WindingFill)
            for path in columnPaths.values():
                columnFill.addPath(path)
            for wall, polygons in ownerPolygons.values():
                polygons = tuple(polygons)
                cached = self.wallMaterialPathCache.get(id(wall))
                if isinstance(wall, Column):
                    wallPath = columnPaths[id(wall)]
                elif cached is None or cached[0] != polygons:
                    wallPath = QtGui.QPainterPath()
                    wallPath.setFillRule(QtCore.Qt.FillRule.WindingFill)
                    for polygon in polygons:
                        area = sum(polygon[index].x() * polygon[(index + 1) % len(polygon)].y()
                                   - polygon[(index + 1) % len(polygon)].x() * polygon[index].y()
                                   for index in range(len(polygon)))
                        polygon = QtGui.QPolygonF(list(reversed(polygon))) if area < 0 else polygon
                        wallPath.addPolygon(polygon)
                        wallPath.closeSubpath()
                    self.wallMaterialPathCache[id(wall)] = (polygons, wallPath)
                else:
                    wallPath = cached[1]
                if not isinstance(wall, Column) and not columnFill.isEmpty() and wallPath.boundingRect().intersects(columnFill.boundingRect()):
                    wallPath = Paths.Difference(wallPath, columnFill)
                path = self.materialPaths.setdefault(wall.material, QtGui.QPainterPath())
                path.setFillRule(QtCore.Qt.FillRule.WindingFill)
                path.addPath(wallPath)
                self.wallMaterialPaths[id(wall)] = wallPath
            self.wallMaterialPathCache = {wallId: cached for wallId, cached in self.wallMaterialPathCache.items()
                                          if wallId in self.wallMaterialPaths}
            self.materialGeometryKey = materialKey
        viewTransform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(self.zoom, self.zoom)
        captureEngine = getattr(self, "objectCaptureEngine", None)
        if captureEngine is not None:
            captureEngine.captureBackground = False
        if self.wallStyle != "Outline":
            materialPaths = self.materialPaths
            if dirtyRects is not None and self.viewportEditRaster is not None and self.CanCacheEditScene():
                materialPaths = {}
                owners = {id(wall): wall for wall in visibleWalls}
                for wallId, path in self.wallMaterialPaths.items():
                    bounds = viewTransform.mapRect(path.boundingRect()).adjusted(-2, -2, 2, 2)
                    if any(bounds.intersects(rect) for rect in dirtyRects):
                        material = owners[wallId].material
                        localPath = materialPaths.setdefault(material, QtGui.QPainterPath())
                        localPath.setFillRule(QtCore.Qt.FillRule.WindingFill)
                        localPath.addPath(path)
            for material, path in materialPaths.items():
                brush = QtGui.QBrush(QtGui.QColor(themeColors["wallOutline"])) if self.wallStyle == "Solid" else self.materialBrushes[(material, False)]
                painter.fillPath(viewTransform.map(path), brush)
        if captureEngine is not None:
            captureEngine.captureBackground = True
        for selectedObject in highlightedObjects:
            if isinstance(selectedObject, (Arrow, MeasurementGuide, Counter, Railing, Stair, Furnishing, Label, Fireplace, Elevator)) or id(selectedObject) in invalidWalls:
                continue
            selectionPath = QtGui.QPainterPath()
            if isinstance(selectedObject, Column):
                selectionPath = viewTransform.map(self.columnMaterialPaths[id(selectedObject)])
            else:
                selectionPath.addPolygon(self.WallPolygon(selectedObject))
                selectionPath.closeSubpath()
            # This polygon is already included in combinedPath. A boolean
            # intersection at coincident angled edges can spill into neighbors.
            material = selectedObject.material if isinstance(selectedObject, Wall) else "Generic"
            painter.save()
            if isinstance(selectedObject, Wall):
                painter.setClipPath(viewTransform.map(self.wallMaterialPaths.get(id(selectedObject), QtGui.QPainterPath())),
                                    QtCore.Qt.ClipOperation.IntersectClip)
            brush = self.groupedMaterialBrushes[material] if id(selectedObject) in groupedIds else self.materialBrushes[(material, True)]
            painter.fillPath(selectionPath, brush)
            painter.restore()
        painter.save()
        lumberClipSet = not self.isPanning
        if lumberClipSet:
            painter.setClipPath(combinedPath, QtCore.Qt.ClipOperation.IntersectClip)
        for wall in visibleWalls:
            if wall.material == "Lumber":
                polygon = self.WallPolygon(wall)
                if len(polygon) == 4 and polygon.boundingRect().intersects(drawingRect):
                    if not lumberClipSet:
                        painter.setClipPath(combinedPath, QtCore.Qt.ClipOperation.IntersectClip)
                        lumberClipSet = True
                    painter.save()
                    painter.setClipPath(viewTransform.map(self.wallMaterialPaths.get(id(wall), QtGui.QPainterPath())),
                                        QtCore.Qt.ClipOperation.IntersectClip)
                    painter.setPen(QtGui.QPen(QtGui.QColor(self.SelectionColor(wall) if id(wall) in highlightedIds and id(wall) not in invalidWalls else themeColors["invalidOutline"]), 1))
                    cuts = {0.0, 1.0}
                    for opening in visibleWindows:
                        if opening.parentWall is wall:
                            cuts.update((max(0.0, min(1.0, opening.firstFraction)),
                                         max(0.0, min(1.0, opening.secondFraction))))
                    cuts = sorted(cuts)
                    firstEdge = polygon[1] - polygon[0]
                    secondEdge = polygon[2] - polygon[3]
                    for start, end in zip(cuts, cuts[1:]):
                        if end - start < 1e-10:
                            continue
                        painter.drawLine(QtCore.QLineF(polygon[0] + firstEdge * start,
                                                       polygon[3] + secondEdge * end))
                        painter.drawLine(QtCore.QLineF(polygon[3] + secondEdge * start,
                                                       polygon[0] + firstEdge * end))
                    painter.restore()
        painter.restore()
        windowOutlineClip = QtGui.QPainterPath()
        windowOutlineClip.setFillRule(QtCore.Qt.FillRule.OddEvenFill)
        windowOutlineClip.addRect(drawingRect)
        for window in visibleWindows:
            if isinstance(window, (Door, SwingingDoor, DoubleDoor, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway, Fireplace)):
                continue
            openingPath = QtGui.QPainterPath()
            openingPath.addPolygon(self.WallPolygon(window))
            openingPath.closeSubpath()
            painter.fillPath(openingPath, QtGui.QColor(themeColors["canvas"]))
            firstPoint, secondPoint = self.WorldToViewport(window.firstVertex), self.WorldToViewport(window.secondVertex)
            direction = secondPoint - firstPoint
            length = math.hypot(direction.x(), direction.y())
            if length > 1e-10:
                # Suppress the heavy wall outline within the window span. Its
                # perimeter is drawn afterward using the architectural weight.
                normal = QtCore.QPointF(-direction.y(), direction.x()) / length * (
                    window.width * pixelsPerMillimeter / 2 + self.lineWidths["walls"] + 1)
                outlineHole = QtGui.QPolygonF([firstPoint + normal, secondPoint + normal,
                                               secondPoint - normal, firstPoint - normal])
                # Distant openings cannot mask visible outlines. Including their
                # holes extends Qt's clip raster far beyond the viewport.
                if not self.isPanning or outlineHole.boundingRect().intersects(openingClipRect):
                    windowOutlineClip.addPolygon(outlineHole)
                    windowOutlineClip.closeSubpath()
        painter.save()
        painter.setClipPath(windowOutlineClip, QtCore.Qt.ClipOperation.IntersectClip)
        painter.setPen(LinePen(themeColors["wallOutline"], self.lineWidths["walls"]))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        columnOutlines = getattr(self, "columnOutlinePaths", ())
        if columnOutlines:
            for path, occluders in columnOutlines:
                painter.save()
                if not occluders.isEmpty() and path.boundingRect().intersects(occluders.boundingRect()):
                    clip = QtGui.QPainterPath()
                    clip.addRect(drawingRect)
                    painter.setClipPath(Paths.Difference(clip, viewTransform.map(occluders)),
                                        QtCore.Qt.ClipOperation.IntersectClip)
                painter.drawPath(viewTransform.map(path))
                painter.restore()
        else:
            strokeDrawn = False
            if (self.isPanning and captureEngine is None and self.viewportSceneByteLimit > 0
                    and painter.pen().style() == QtCore.Qt.PenStyle.SolidLine):
                # Qt's complete stroke preserves caps/joins. Preparing it in a
                # retained device-pixel phase avoids restroking on integer pans,
                # without introducing another raster/compositing pass.
                pen = painter.pen()
                ratio = painter.device().devicePixelRatioF()
                strokeKey = (self.wallGeometryKey, self.zoom, ratio, pen.widthF(), pen.capStyle(),
                             pen.joinStyle(), pen.miterLimit())
                cachedStroke = prepared.get("wallStroke")
                if cachedStroke is None or cachedStroke[0] != strokeKey:
                    stroke = Paths.PreparePenStroke(pen)
                    bounds = tuple(polygon.boundingRect() for polygon in Paths.Contours(combinedPath))
                    cachedStroke = (strokeKey, stroke(combinedPath), QtCore.QPointF(origin), bounds)
                    prepared["wallStroke"] = cachedStroke
                delta = origin - cachedStroke[2]
                if (abs(delta.x() * ratio - round(delta.x() * ratio)) < 1e-7
                        and abs(delta.y() * ratio - round(delta.y() * ratio)) < 1e-7
                        and any(bounds.translated(delta).contains(drawingRect) for bounds in cachedStroke[3])):
                    # Large spanning contours are costly to restroke. For smaller
                    # contours, native dirty-contour culling avoids filling the
                    # complete scene's stroke and remains the cheaper path.
                    self.DrawPanWallStroke(painter, cachedStroke[1].translated(delta), pen.brush(), dirtyRects,
                                           (doorwayClip, windowOutlineClip), drawingRect)
                    strokeDrawn = True
            if not strokeDrawn and dirtyRects is not None and (self.isPanning or self.viewportEditRaster is not None and self.CanCacheEditScene()):
                self.DrawDirtyWallOutline(painter, combinedPath, dirtyRects, wholeContours = self.isPanning)
            elif not strokeDrawn:
                painter.drawPath(combinedPath)
        painter.save()
        for wallId in invalidWalls:
            invalidPath = viewTransform.map(self.wallMaterialPaths.get(wallId, QtGui.QPainterPath()))
            warning = wallId in invalidArchitecture and self.dragStart is None
            painter.setOpacity(1 if warning else .55)
            painter.fillPath(invalidPath, self.warningMaterialBrushes[invalidWalls[wallId].material] if warning else QtGui.QColor(themeColors["canvas"]))
            painter.setOpacity(1)
            painter.setPen(LinePen(themeColors["warningOutline"] if warning else themeColors["invalidOutline"], self.lineWidths["walls"]))
            painter.drawPath(invalidPath)
        painter.restore()
        painter.restore()
        painter.restore()
        from planner_app.geometry_recovery import ActiveGeometryIssues
        recoveryErrorIds = {id(opening) for opening in self.windows if getattr(opening, "geometryIssues", ()) and ActiveGeometryIssues(opening, self)}
        openingPreviews = self.groupOpeningPreviews or ([self.inactiveOpeningPreview] if isinstance(self.inactiveOpeningPreview, Window) else [])
        previewIds = {id(opening) for opening in openingPreviews} | invalidArchitecture
        for opening in visibleWindows + openingPreviews:
            if not self.IsObjectVisible(opening):
                continue
            if dirtyRects is not None:
                bounds = QtCore.QRectF(self.WorldToViewport(opening.firstVertex), self.WorldToViewport(opening.secondVertex)).normalized()
                # Swing tips extend a full leaf length from a hinge on the wall
                # face, not its centerline. Include that offset when a door
                # re-enters a newly exposed pan strip.
                padding = (opening.length + opening.width / 2 + getattr(opening, "sillDepth", 0)
                           + (opening.wellDepth + 150 if opening.windowWell else 0)) * pixelsPerMillimeter + max(self.lineWidths.values()) + 2
                if not any(bounds.adjusted(-padding, -padding, padding, padding).intersects(rect) for rect in dirtyRects):
                    continue
            warning = id(opening) in recoveryErrorIds or id(opening) in advisoryIds or id(opening) in invalidArchitecture and self.dragStart is None
            color = (themeColors["warningOutline"] if warning else
                     themeColors["invalidOutline"] if id(opening) in previewIds or id(opening.parentWall) in invalidWalls else
                     self.SelectionColor(opening) if id(opening) in highlightedIds else themeColors["objectOutline"])
            if isinstance(opening, Fireplace):
                transform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(pixelsPerMillimeter, -pixelsPerMillimeter)
                bodyColor = (themeColors["warningOutline"] if warning else
                             themeColors["invalidOutline"] if id(opening) in previewIds or id(opening.parentWall) in invalidWalls else
                             self.SelectionColor(opening) if id(opening) in highlightedIds else themeColors["wallOutline"])
                path = transform.map(FireplacePath(opening))
                if self.wallStyle != "Outline":
                    brush = (QtGui.QBrush(QtGui.QColor(bodyColor)) if self.wallStyle == "Solid" else
                             self.materialBrushes[(opening.material, id(opening) in highlightedIds)])
                    if captureEngine is not None:
                        captureEngine.captureBackground = False
                    painter.fillPath(path, brush)
                    if captureEngine is not None:
                        captureEngine.captureBackground = True
                painter.setPen(LinePen(bodyColor, self.lineWidths["walls"]))
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawPath(path)
                continue
            DrawOpeningSymbol(painter, self.WorldToViewport(opening.firstVertex), self.WorldToViewport(opening.secondVertex),
                              opening.width * pixelsPerMillimeter, type(opening),
                              opening.hingeAtSecond if isinstance(opening, (Door, SwingingDoor, SlidingDoor, PocketDoor, CasementWindow)) else False,
                              opening.swingsOutwards if type(opening) in (Window, Door, DoubleDoor, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, BarnDoor, BifoldDoor) else False, color,
                              opening.panelsFlipped if isinstance(opening, SlidingDoor) else False, pixelsPerMillimeter,
                              opening.sillDepth if isinstance(opening, SilledWindow) else 40.0,
                              lineWidth = self.lineWidths["architectural"], wallLineWidth = self.lineWidths["walls"],
                              wallColor = themeColors["warningOutline"] if warning else
                              themeColors["invalidOutline"] if id(opening) in invalidArchitecture or id(opening.parentWall) in invalidWalls else themeColors["wallOutline"],
                              windowWell = opening.windowWell, wellDepth = opening.wellDepth, wellDashed = opening.wellDashed)
        visibleStairs = [wall for wall in self.walls if isinstance(wall, Stair)]
        invalidStairs = []
        movingStairs = ([self.selectedWall] if isinstance(self.selectedWall, Stair) else []) + [
            wall for wall, index, position in self.ActiveAttachments() if isinstance(wall, Stair)]
        if movingStairs and self.dragStart is not None and not self.OpeningsValid():
            invalidStairs = list({id(stair): stair for stair in movingStairs}.values())
        invalidStairs = list({id(stair): stair for stair in invalidStairs + [
            stair for stair in visibleStairs if id(stair) in invalidArchitecture or id(stair) in advisoryIds]}.values())
        if isinstance(self.windowDropPreview, Stair):
            visibleStairs.append(self.windowDropPreview)
        visibleStairs = [stair for stair in visibleStairs if self.IsObjectVisible(stair)]
        if visibleStairs:
            endpointKey = tuple((id(stair), stair.firstVertex.x(), stair.firstVertex.y(), stair.secondVertex.x(), stair.secondVertex.y()) for stair in visibleStairs)
            if endpointKey != getattr(self, "stairEndpointKey", None):
                buckets = {}
                neighbors = {}
                for stair in visibleStairs:
                    for vertex in (stair.firstVertex, stair.secondVertex):
                        cell = (math.floor(vertex.x() / .01), math.floor(vertex.y() / .01))
                        buckets.setdefault(cell, []).append((stair, vertex))
                for stair in visibleStairs:
                    for index, vertex in enumerate((stair.firstVertex, stair.secondVertex)):
                        x, y = math.floor(vertex.x() / .01), math.floor(vertex.y() / .01)
                        neighbors[(id(stair), index)] = [other for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                            for other, point in buckets.get((x + dx, y + dy), ())
                            if other is not stair and QtCore.QLineF(vertex, point).length() <= .01]
                self.stairEndpointKey, self.stairEndpointNeighbors = endpointKey, neighbors
            stairPath = self.ConnectedStairPath(visibleStairs)
            connectedStairIds = {id(stair) for stair in visibleStairs
                                 if self.stairEndpointNeighbors[(id(stair), 0)] or self.stairEndpointNeighbors[(id(stair), 1)]}
            trims = {id(stair): self.StairLandingTrims(stair, self.stairEndpointNeighbors[(id(stair), 0)] + self.stairEndpointNeighbors[(id(stair), 1)])
                     for stair in visibleStairs}
            arrowKey = (self.stairGeometryKey, tuple((id(stair), stair.directionReversed) for stair in visibleStairs))
            if arrowKey != getattr(self, "stairArrowKey", None):
                self.stairArrowRuns = StairArrowRuns(visibleStairs, self.stairEndpointNeighbors, trims)
                self.stairArrowKey = arrowKey
            # Keep wall fills and their full stroke above stairs at shared edges.
            # Cache this independently of stair edits, which do not alter walls.
            wallClipKey = (self.wallGeometryKey, self.zoom, self.lineWidths["walls"], self.lineWidths["architectural"],
                           tuple((id(opening), type(opening), opening.firstVertex.x(), opening.firstVertex.y(),
                                  opening.secondVertex.x(), opening.secondVertex.y(), opening.width,
                                  getattr(opening, "hingeAtSecond", False)) for opening in visibleWindows))
            if wallClipKey != getattr(self, "stairWallClipKey", None):
                # Keep occlusion in scaled coordinates relative to the world origin.
                # Translation only maps this cached geometry; no path booleans are
                # needed merely because the camera or viewport rectangle changed.
                walls = QtGui.QTransform().scale(self.zoom, self.zoom).map(self.wallGeometryPath)
                occlusion = walls
                boundaryWidth = max(self.lineWidths["walls"], self.lineWidths["architectural"])
                if boundaryWidth > 0 and not walls.isEmpty():
                    stroke = Paths.PrepareStroke(width = boundaryWidth, join = 'bevel', cap = 'square')
                    occlusion = Paths.Union(occlusion, stroke(walls))
                # Door openings remove the wall fill and stroke above, so
                # stair outlines remain visible inside those same openings.
                openings = QtGui.QTransform().translate(-origin.x(), -origin.y()).map(doorwayOpenings)
                if not openings.isEmpty():
                    occlusion = Paths.Difference(occlusion, openings)
                self.stairWallClipKey, self.stairWallOcclusion = wallClipKey, occlusion
                self.stairWallClipViewKey = None
            viewKey = (origin.x(), origin.y(), drawingRect)
            if viewKey != self.stairWallClipViewKey:
                clip = QtGui.QPainterPath()
                clip.setFillRule(QtCore.Qt.FillRule.OddEvenFill)
                clip.addRect(drawingRect)
                clip.addPath(QtGui.QTransform().translate(origin.x(), origin.y()).map(self.stairWallOcclusion))
                self.stairWallClip, self.stairWallClipViewKey = clip, viewKey
            painter.save()
            painter.setClipPath(self.stairWallClip, QtCore.Qt.ClipOperation.IntersectClip)
            painter.fillPath(stairPath, QtGui.QColor(themeColors["canvas"]))
            painter.save()
            painter.setClipPath(stairPath, QtCore.Qt.ClipOperation.IntersectClip)
            for stair in visibleStairs:
                if not self.WallPolygon(stair).boundingRect().intersects(drawingRect):
                    continue
                if dirtyRects is not None:
                    bounds = self.WallPolygon(stair).boundingRect()
                    padding = self.lineWidths["architectural"] + 2
                    if not any(bounds.adjusted(-padding, -padding, padding, padding).intersects(rect) for rect in dirtyRects):
                        continue
                if id(stair) in highlightedIds and stair not in invalidStairs:
                    selectedPath = QtGui.QPainterPath()
                    selectedPath.addPolygon(self.WallPolygon(stair))
                    painter.fillPath(selectedPath, QtGui.QColor(themeColors["stairGroupSelectionFill"] if id(stair) in groupedIds else themeColors["stairSelectionFill"]))
                firstTrim, secondTrim = self.StairLandingTrims(stair, self.stairEndpointNeighbors[(id(stair), 0)] + self.stairEndpointNeighbors[(id(stair), 1)])
                treadCount, stepSize, landingCount = stair.StepLayout((firstTrim, secondTrim))
                DrawStairSymbol(painter, self.WorldToViewport(stair.firstVertex), self.WorldToViewport(stair.secondVertex),
                                stair.width * pixelsPerMillimeter, treadCount, stair.directionReversed,
                                self.SelectionColor(stair) if id(stair) in highlightedIds else themeColors["objectOutline"], outline = False,
                                firstTrim = firstTrim * pixelsPerMillimeter, secondTrim = secondTrim * pixelsPerMillimeter, clipRect = drawingRect,
                                lineWidth = self.lineWidths["architectural"], edgeInset = 25 * pixelsPerMillimeter,
                                drawInsetEdges = id(stair) not in connectedStairIds, drawArrow = id(stair) not in connectedStairIds)
                # Keep two joined end steps from becoming one double-depth step.
                for vertexIndex, (vertex, otherVertex) in enumerate(((stair.firstVertex, stair.secondVertex), (stair.secondVertex, stair.firstVertex))):
                    direction = otherVertex - vertex
                    length = math.hypot(direction.x(), direction.y())
                    if length < 1e-10:
                        continue
                    direction /= length
                    for other in self.stairEndpointNeighbors[(id(stair), vertexIndex)]:
                        if other is stair:
                            continue
                        shared = None
                        if QtCore.QLineF(vertex, other.firstVertex).length() <= .01:
                            shared = other.secondVertex - other.firstVertex
                        elif QtCore.QLineF(vertex, other.secondVertex).length() <= .01:
                            shared = other.firstVertex - other.secondVertex
                        if shared is not None and QtCore.QPointF.dotProduct(direction, shared) < 0:
                            cross = direction.x() * shared.y() - direction.y() * shared.x()
                            if abs(cross) < 1e-6:
                                center = self.WorldToViewport(vertex)
                                width = min(stair.width, other.width)
                                normal = QtCore.QPointF(-direction.y(), direction.x()) * ((width / 2 - min(25, width / 4)) * pixelsPerMillimeter)
                                painter.setPen(LinePen(self.SelectionColor(stair) if id(stair) in highlightedIds else themeColors["objectOutline"], self.lineWidths["architectural"]))
                                painter.drawLine(QtCore.QLineF(center - normal, center + normal))
                                break
            insetTransform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(self.zoom, self.zoom)
            for stair, line in self.stairInsetLines:
                if stair in invalidStairs:
                    continue
                color = self.SelectionColor(stair) if id(stair) in highlightedIds else themeColors["objectOutline"]
                painter.setPen(LinePen(color, self.lineWidths["architectural"]))
                painter.drawLine(insetTransform.map(line))
            arrows = [(self.WorldToViewport(start), self.WorldToViewport(tip),
                       self.SelectionColor(stair) if id(stair) in highlightedIds else themeColors["objectOutline"], showTip)
                      for stair, start, tip, showTip in self.stairArrowRuns if stair not in invalidStairs and id(stair) in connectedStairIds]
            DrawStairArrows(painter, arrows, self.lineWidths["architectural"])
            painter.restore()
            painter.setPen(LinePen(themeColors["wallOutline"], self.lineWidths["architectural"]))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            origin = self.WorldToViewport(QtCore.QPointF())
            stairTransform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(self.zoom, self.zoom)
            # The traced outline consists of independent line spans. Batched
            # lines avoid stroking a large path again on every fractional pan.
            painter.drawLines([stairTransform.map(line) for line in self.stairOutlineLines])
            painter.restore()
            for stair in invalidStairs:
                firstTrim, secondTrim = self.StairLandingTrims(stair, self.stairEndpointNeighbors[(id(stair), 0)] + self.stairEndpointNeighbors[(id(stair), 1)])
                treadCount, stepSize, landingCount = stair.StepLayout((firstTrim, secondTrim))
                DrawStairSymbol(painter, self.WorldToViewport(stair.firstVertex), self.WorldToViewport(stair.secondVertex),
                                stair.width * pixelsPerMillimeter, treadCount, stair.directionReversed,
                                themeColors["warningOutline"] if id(stair) in advisoryIds or id(stair) in invalidArchitecture and self.dragStart is None else themeColors["invalidOutline"],
                                firstTrim = firstTrim * pixelsPerMillimeter, secondTrim = secondTrim * pixelsPerMillimeter, clipRect = drawingRect,
                                lineWidth = self.lineWidths["architectural"], edgeInset = 25 * pixelsPerMillimeter)
        if isinstance(self.inactiveOpeningPreview, Stair):
            stair = self.inactiveOpeningPreview
            DrawStairSymbol(painter, self.WorldToViewport(stair.firstVertex), self.WorldToViewport(stair.secondVertex),
                            stair.width * pixelsPerMillimeter, stair.stepCount, stair.directionReversed, themeColors["invalidOutline"],
                            lineWidth = self.lineWidths["architectural"], edgeInset = 25 * pixelsPerMillimeter)
        visibleRailings = [obj for obj in self.walls if isinstance(obj, Railing) and self.IsObjectVisible(obj)]
        if isinstance(self.arrowPreview, Railing) and self.IsObjectVisible(self.arrowPreview):
            visibleRailings.append(self.arrowPreview)
        paintRailings = False
        if visibleRailings:
            railingPath, _ = self.ConnectedRailingPath(visibleRailings, False)
            padding = self.lineWidths["architectural"] + 2
            bounds = railingPath.boundingRect().adjusted(-padding, -padding, padding, padding)
            # Retain the complete list for handles and measurements, but avoid
            # rasterizing the wall-occlusion mask for railings outside this paint.
            paintRailings = (not self.isPanning or any(bounds.intersects(rect)
                             for rect in (dirtyRects if dirtyRects is not None else [drawingRect])))
        if paintRailings:
            # Railings cover counters and stairs, while solid walls remain above them.
            painter.save()
            railingClip = QtGui.QPainterPath()
            railingClip.addRect(drawingRect)
            painter.setClipPath(Paths.Difference(railingClip, combinedPath), QtCore.Qt.ClipOperation.IntersectClip)
            invalidRailing = isinstance(self.arrowPreview, Railing) and not self.WallFits(self.arrowPreview)
            painter.setPen(LinePen(themeColors["invalidOutline"] if invalidRailing else themeColors["objectOutline"], self.lineWidths["architectural"]))
            painter.setBrush(QtGui.QColor(themeColors["canvas"]))
            painter.drawPath(railingPath)
            origin = self.WorldToViewport(QtCore.QPointF())
            postTransform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(self.zoom, self.zoom)
            postOutlines = postTransform.map(self.railingPostOutlinePath)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawPath(postOutlines)
            for railing in visibleRailings:
                if id(railing) in highlightedIds or id(railing) in invalidArchitecture or id(railing) in advisoryIds:
                    selectionClip = QtGui.QPainterPath()
                    selectionClip.addPolygon(self.WallPolygon(railing))
                    selectionClip.closeSubpath()
                    stroke = QtGui.QPainterPathStroker()
                    stroke.setWidth(self.lineWidths["architectural"] + 2)
                    selectionClip = selectionClip.united(stroke.createStroke(selectionClip))
                    painter.save()
                    painter.setClipPath(selectionClip, QtCore.Qt.ClipOperation.IntersectClip)
                    color = (themeColors["warningOutline"] if id(railing) in advisoryIds or id(railing) in invalidArchitecture and self.dragStart is None else
                             themeColors["invalidOutline"] if id(railing) in invalidArchitecture else self.SelectionColor(railing))
                    painter.setPen(LinePen(color, self.lineWidths["architectural"]))
                    painter.setBrush(QtGui.QColor(themeColors["canvas"] if id(railing) in invalidArchitecture or id(railing) in advisoryIds else themeColors["stairSelectionFill"]))
                    painter.drawPath(railingPath)
                    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                    painter.drawPath(postOutlines)
                    painter.restore()
            painter.restore()
        # Containment is an advisory warning, independent of drag validity.
        # Draw these footprints above the merged wall surfaces so they remain visible.
        painter.save()
        painter.setClipPath(doorwayClip, QtCore.Qt.ClipOperation.IntersectClip)
        painter.setPen(LinePen(themeColors["warningOutline"], self.lineWidths["architectural"]))
        for wall in containedWalls:
            polygon = self.WallPolygon(wall)
            padding = self.lineWidths["architectural"] + 2
            if dirtyRects is not None and not any(polygon.boundingRect().adjusted(-padding, -padding, padding, padding).intersects(rect) for rect in dirtyRects):
                continue
            painter.setBrush(self.warningMaterialBrushes[wall.material])
            painter.drawPolygon(polygon)
            if wall.material == "Lumber" and len(polygon) == 4:
                painter.drawLine(QtCore.QLineF(polygon[0], polygon[2]))
                painter.drawLine(QtCore.QLineF(polygon[1], polygon[3]))
        painter.restore()
        if captureEngine is not None:
            captureEngine.captureBackground = False
        visibleElevators = [obj for obj in self.walls if isinstance(obj, Elevator) and self.IsObjectVisible(obj)]
        if isinstance(self.arrowPreview, Elevator) and self.IsObjectVisible(self.arrowPreview):
            visibleElevators.append(self.arrowPreview)
        elevatorRenderers = getattr(self, "elevatorRenderers", {})
        self.elevatorRenderers = elevatorRenderers
        if captureEngine is not None:
            captureEngine.captureBackground = True
        for elevator in visibleElevators:
            selected = id(elevator) in highlightedIds
            invalid = id(elevator) in invalidArchitecture or (elevator is self.arrowPreview or selected and (self.isDragging or self.furnishingHandleDrag is not None)) and not self.WallFits(elevator)
            warning = id(elevator) in advisoryIds or id(elevator) in invalidArchitecture and self.dragStart is None
            color = (themeColors["warningOutline"] if warning else themeColors["invalidOutline"] if invalid else
                     self.SelectionColor(elevator) if selected else themeColors["objectOutline"])
            key = (color, themeColors["canvas"], self.lineWidths["architectural"], palette.labelFont)
            if key not in elevatorRenderers:
                if len(elevatorRenderers) >= 8:
                    elevatorRenderers.pop(next(iter(elevatorRenderers)))
                elevatorRenderers[key] = FurnishingRenderer(furnishingsDirectory / "images/elevator.svg",
                    palette = {"outline": color, "background": themeColors["canvas"], "missing": themeColors["missing"]},
                    lineWidth = self.lineWidths["architectural"])
            DrawFurnishing(painter, elevator, self.WorldToViewport(elevator.firstVertex), self.WorldToViewport(elevator.secondVertex),
                           pixelsPerMillimeter, elevatorRenderers[key], selected, invalid and not warning, selectionColor = color, drawBounds = False)
        if captureEngine is not None:
            captureEngine.captureBackground = False
        visibleArrows = [obj for obj in self.walls if isinstance(obj, Arrow) and self.IsObjectVisible(obj)]
        if isinstance(self.arrowPreview, Arrow) and self.IsObjectVisible(self.arrowPreview):
            visibleArrows.append(self.arrowPreview)
        arrowDirections = ConnectedArrowDirections(visibleArrows)
        arrowCorners = ConnectedArrowCorners(visibleArrows, arrowDirections)
        arrowPath = QtGui.QPainterPath()
        arrowPath.setFillRule(QtCore.Qt.FillRule.WindingFill)
        arrowColor = None
        for arrow in visibleArrows:
            first, second, showTip = arrowDirections[id(arrow)]
            tail, head = ArrowPaths(self.WorldToViewport(first), self.WorldToViewport(second), arrow.width,
                                    arrow.solidTip, arrow.tipSize, pixelsPerMillimeter, showTip,
                                    [[self.WorldToViewport(point) for point in polygon] for polygon in arrowCorners[id(arrow)]])
            color = QtGui.QColor(themeColors["invalidOutline"] if arrow is self.arrowPreview else
                                 self.SelectionColor(arrow) if id(arrow) in highlightedIds else themeColors["objectOutline"])
            color.setAlphaF(arrow.intensity)
            # Fill adjoining shapes of the same appearance in one operation.
            # Separate antialiased fills leave a seam at their shared diagonal
            # and apply intensity twice wherever the shafts overlap.
            if arrowColor is not None and color != arrowColor:
                painter.fillPath(arrowPath, arrowColor)
                arrowPath = QtGui.QPainterPath()
                arrowPath.setFillRule(QtCore.Qt.FillRule.WindingFill)
            arrowColor = color
            arrowPath.addPath(tail)
            arrowPath.addPath(head)
        if arrowColor is not None:
            painter.fillPath(arrowPath, arrowColor)
        visibleGuides = [obj for obj in self.walls if isinstance(obj, MeasurementGuide) and self.IsObjectVisible(obj)]
        if isinstance(self.arrowPreview, MeasurementGuide) and self.IsObjectVisible(self.arrowPreview):
            visibleGuides.append(self.arrowPreview)
        visibleBoundaries = [guide for guide in visibleGuides if isinstance(guide, BoundaryLine)]
        if visibleBoundaries:
            painter.save()
            for guide in visibleBoundaries:
                colorRole, widthRole = lineWeightClasses[guide.weightClass] if isinstance(guide, DashedLine) else ("measurementLine", "dimensions")
                color = self.SelectionColor(guide) if id(guide) in highlightedIds else themeColors[colorRole]
                lineWidth = self.lineWidths[widthRole]
                style = QtCore.Qt.PenStyle.SolidLine if isinstance(guide, SolidLine) else QtCore.Qt.PenStyle.DashLine if isinstance(guide, DashedLine) else QtCore.Qt.PenStyle.DashDotLine
                pen = LinePen(color, lineWidth, style)
                if lineWidth > 0:
                    # Qt measures dash lengths in stroke widths. Keep thin
                    # dimension strokes from collapsing the pattern to pixels.
                    unit = max(1, lineWidth) / lineWidth
                    if isinstance(guide, DashedLine) and not isinstance(guide, SolidLine):
                        pen.setDashPattern([6 * unit, 3 * unit])
                    elif not isinstance(guide, SolidLine):
                        pen.setDashPattern([6 * unit, 3 * unit, unit, 3 * unit])
                painter.setPen(pen)
                painter.drawLine(QtCore.QLineF(self.WorldToViewport(guide.firstVertex), self.WorldToViewport(guide.secondVertex)))
            painter.restore()
        sceneState = (highlightedObjects, highlightedIds, selectedVertexKeys, invalidWalls, invalidCounterIds, invalidStairs,
                      visibleWalls, visibleCounters, visibleWindows, visibleStairs, visibleRailings, visibleArrows, visibleGuides)
        if drawAnnotations:
            self.DrawSceneMeasurements(painter, drawingRect, sceneState, dirtyRects, retainCommands = retainAnnotations)
        return sceneState

    def DrawSceneMeasurements(self, painter, drawingRect, sceneState, dirtyRects = None, retainCommands = False):
        """Retain world-space spans across camera movement and restore annotations on release."""
        (highlightedObjects, highlightedIds, selectedVertexKeys, invalidWalls, invalidCounterIds, invalidStairs,
                      visibleWalls, visibleCounters, visibleWindows, visibleStairs, visibleRailings, visibleArrows, visibleGuides) = sceneState
        drawMeasurements = self.showMeasurements and not self.isPanning
        renderedSelection = (self.pendingShiftSelection[0] if self.pendingShiftSelection is not None and not self.isDragging
                             else self.SelectionEntries())
        measurementSelectedIds = {id(obj) for obj, index in renderedSelection if self.IsObjectVisible(obj)}
        if not drawMeasurements and not measurementSelectedIds and not visibleGuides:
            return
        stableMeasurements = (self.dragStart is None and not self.isDragging and self.pendingWall is None and not self.pendingShapeWalls
                              and self.furnishingHandleDrag is None and not self.guiDragActive
                              and all(preview is None for preview in (self.furnishingPreview, self.windowDropPreview,
                                      self.inactiveOpeningPreview, self.counterPreview, self.arrowPreview, self.labelPreview)))
        measurementKey = self.SceneRenderKey((self.zoom, self.basePixelsPerMillimeter, drawMeasurements)) if stableMeasurements else None
        origin = self.WorldToViewport(QtCore.QPointF())
        measurementFont = QtGui.QFont(painter.font())
        measurementFont.setFamily(fontFamily)
        pictureKey = (measurementKey, self.unitsMode, measurementFont.toString(), painter.renderHints(), tuple(themeColors.items()),
                      painter.device().logicalDpiX(), painter.device().logicalDpiY())
        pictures = getattr(self, "measurementPictures", ())
        if stableMeasurements and retainCommands:
            for key, picture, pictureOrigin in pictures:
                if key == pictureKey:
                    painter.save()
                    painter.translate(origin - pictureOrigin)
                    painter.drawPicture(QtCore.QPointF(), picture)
                    painter.restore()
                    return
        cachedMeasurements = getattr(self, "sceneMeasurements", None)
        if measurementKey is not None and cachedMeasurements is not None and cachedMeasurements[0] == measurementKey:
            dimensions = cachedMeasurements[1]
            stackedDimensions = cachedMeasurements[2]
        else:
            stackedDimensions = []
            selectedBodies = {id(obj) for obj, index in renderedSelection if index is None and self.IsObjectVisible(obj)}
            groupedSelectedIds = set()
            groupDimensions = []
            for group in self.objectGroups:
                members = [obj for obj in group if self.IsObjectVisible(obj) and not isinstance(obj, Elevator)]
                if len(members) < 2 or not all(id(obj) in selectedBodies for obj in members):
                    continue
                bounds = QtCore.QRectF(self.ObjectFootprint(members[0])[0])
                for obj in members[1:]:
                    bounds = bounds.united(self.ObjectFootprint(obj)[0])
                groupedSelectedIds.update(id(obj) for obj in members)
                corners = (bounds.topLeft(), bounds.bottomLeft(), bounds.bottomRight(), bounds.topRight())
                groupDimensions.extend((corners[index], corners[(index + 1) % 4], members) for index in range(4))
            combinedPath = self.ConnectedWallPath(visibleWalls)
            counterDimensions = (self.ConnectedCounterPath(visibleCounters, True)[1]
                                 if visibleCounters and (drawMeasurements and self.measurementVisibility["counters"]
                                 or any(id(obj) in measurementSelectedIds for obj in visibleCounters)) else [])
            stairDimensions = (self.StairDimensions(visibleStairs)
                               if visibleStairs and (drawMeasurements and self.measurementVisibility["stairs"]
                               or any(id(obj) in measurementSelectedIds for obj in visibleStairs)) else [])
            railingDimensions = (self.ConnectedRailingPath(visibleRailings, True)[1]
                                 if visibleRailings and (drawMeasurements and self.measurementVisibility["railings"]
                                 or any(id(obj) in measurementSelectedIds for obj in visibleRailings)) else [])
            dimensions = [(guide.firstVertex, guide.secondVertex, [guide]) for guide in visibleGuides
                          if not isinstance(guide, AngleGuide) and id(guide) not in groupedSelectedIds
                          and (not isinstance(guide, BoundaryLine) or id(guide) in measurementSelectedIds)]
            stacked = self.wallMeasurementMode == "Exterior stacked"
            exteriorOnly = self.wallMeasurementMode != "All"
            measurementBoundary = combinedPath
            rooms = []
            if exteriorOnly:
                scale = self.basePixelsPerMillimeter * self.zoom
                self.roomDetection.UpdateBoundary()
                if stacked:
                    rooms = [region["path"] for region in self.roomDetection.regions]
                toView = QtGui.QTransform(scale, 0, 0, -scale, origin.x(), origin.y())
                measurementBoundary = toView.map(self.roomDetection.exteriorPath)
            splitSettings = dict(self.measurementSettings, doors = 0, windows = 0, stairs = 2, counters = 2) if stacked else None
            wallDimensions = (self.WallDimensions(visibleWalls, measurementBoundary, visibleWindows,
                                                 cachedBoundary = not exteriorOnly, measurementSettings = splitSettings)
                              if drawMeasurements and self.measurementVisibility["walls"] or
                              any(id(obj) in measurementSelectedIds for obj in visibleWalls) else [])
            if stacked and wallDimensions:
                totals = self.WallDimensions(visibleWalls, measurementBoundary, visibleWindows,
                                            measurementSettings = dict(self.measurementSettings, doors = 2, windows = 2, stairs = 2, counters = 2))
                wallDimensions, rows = BuildMeasurementStacks(totals, wallDimensions, visibleWalls, rooms, self.wallMeasurementReference)
                for first, second, owners, tier in rows:
                    owners = [obj for obj in owners if id(obj) not in groupedSelectedIds
                              and (not isinstance(obj, Pillar) or id(obj) not in measurementSelectedIds)
                              and (not obj.measurementHidden or id(obj) in measurementSelectedIds)]
                    if owners and (drawMeasurements and self.measurementVisibility["walls"]
                                   or any(id(obj) in measurementSelectedIds for obj in owners)):
                        stackedDimensions.append((first, second, owners, tier))
            for category, spans in (("walls", wallDimensions), ("railings", railingDimensions),
                                    ("stairs", stairDimensions), ("counters", counterDimensions)):
                for first, second, owners in spans:
                    # Pillars use their complete bounds below while selected,
                    # including sides hidden inside adjoining wall geometry.
                    owners = [obj for obj in owners if id(obj) not in groupedSelectedIds
                              and (not isinstance(obj, Pillar) or id(obj) not in measurementSelectedIds)]
                    if not owners:
                        continue
                    if (drawMeasurements and self.measurementVisibility[category]
                            or any(id(obj) in measurementSelectedIds for obj in owners)):
                        dimensions.append((first, second, owners))
            measuredIds = {id(obj) for first, second, owners in dimensions for obj in owners}
            if drawMeasurements and self.measurementVisibility["walls"] and not exteriorOnly:
                for column in visibleWalls:
                    if isinstance(column, Column) and id(column) not in measurementSelectedIds:
                        corners = self.ObjectCorners(column)
                        dimensions.extend((corners[index], corners[(index + 1) % len(corners)], [column]) for index in range(len(corners)))
            for obj in {id(obj): obj for obj, index in renderedSelection}.values():
                if id(obj) not in measurementSelectedIds or id(obj) in groupedSelectedIds or isinstance(obj, (MeasurementGuide, Elevator)):
                    continue
                if isinstance(obj, (Window, Furnishing, Label, Pillar)):
                    corners = self.ObjectCorners(obj)
                    dimensions.extend((corners[index], corners[(index + 1) % len(corners)], [obj]) for index in range(len(corners)))
                elif isinstance(obj, Arrow):
                    dimensions.append((obj.firstVertex, obj.secondVertex, [obj]))
                elif id(obj) not in measuredIds:
                    if type(obj) is Wall and exteriorOnly:
                        continue
                    # An object entirely inside joined geometry still needs its
                    # own dimensions when selected, even without exposed edges.
                    corners = self.ObjectCorners(obj)
                    if not corners:
                        continue
                    indices = range(len(corners)) if isinstance(obj, (Stair, Counter)) else (0, 2)
                    dimensions.extend((corners[index], corners[(index + 1) % len(corners)], [obj]) for index in indices)
            dimensions.extend(groupDimensions)
            dimensions = [(first, second, visibleOwners) for first, second, owners in dimensions
                          if (visibleOwners := [obj for obj in owners if not obj.measurementHidden or id(obj) in measurementSelectedIds])]
            self.sceneMeasurements = (measurementKey, dimensions, stackedDimensions) if stableMeasurements else None
        targetPainter = painter
        unusedDivisor, measurementUnit = GridUnit(self.GridSteps()[0], self.unitsMode)
        picture = None
        candidate = QtGui.QPicture() if stableMeasurements and retainCommands else None
        with ExitStack() as painterScope:
            targetPainter.save()
            painterScope.callback(targetPainter.restore)
            targetPainter.setFont(measurementFont)
            if (candidate is not None and candidate.logicalDpiX() == targetPainter.device().logicalDpiX()
                    and candidate.logicalDpiY() == targetPainter.device().logicalDpiY()):
                picture = candidate
                painter = painterScope.enter_context(QtGui.QPainter(picture))
                painter.setFont(targetPainter.font())
                painter.setRenderHints(targetPainter.renderHints())
            for guide in visibleGuides:
                if isinstance(guide, AngleGuide) and (not guide.measurementHidden or id(guide) in measurementSelectedIds):
                    self.DrawAngleGuide(painter, guide, id(guide) in highlightedIds)
            for firstVertex, secondVertex, owners, tier in chain(
                    ((first, second, owners, 0) for first, second, owners in dimensions), stackedDimensions):
                isSelected = any(id(wall) in highlightedIds and id(wall) not in invalidWalls and id(wall) not in invalidCounterIds for wall in owners)
                selectedColor = next((self.SelectionColor(wall) for wall in owners
                                      if id(wall) in highlightedIds and id(wall) not in invalidWalls and id(wall) not in invalidCounterIds), themeColors["selectionOutline"])
                firstPoint = self.WorldToViewport(firstVertex)
                secondPoint = self.WorldToViewport(secondVertex)
                direction = secondPoint - firstPoint
                screenLength = math.hypot(direction.x(), direction.y())
                margin = max(80, 40 + 30 * tier)
                bounds = QtCore.QRectF(firstPoint, secondPoint).normalized().adjusted(-margin, -margin, margin, margin)
                manualGuide = owners[0] if len(owners) == 1 and type(owners[0]) in (MeasurementGuide, BoundaryLine, DashedLine, SolidLine) else None
                boundary = isinstance(manualGuide, BoundaryLine)
                if manualGuide is not None:
                    bounds = bounds.united(self.MeasurementLabelLayout(manualGuide, painter.fontMetrics())[3].boundingRect())
                if picture is None and not bounds.intersects(drawingRect):
                    continue
                if screenLength >= 24 - 1e-6 or ((isSelected or isinstance(owners[0], MeasurementGuide)) and screenLength > 1e-8):
                    angle = math.degrees(math.atan2(direction.y(), direction.x()))
                    if angle > 90:
                        angle -= 180
                    elif angle < -90:
                        angle += 180
                    # Traced contours have wall fill on their left. Place dimensions
                    # to their right, into the empty room or exterior space.
                    normal = QtCore.QPointF(direction.y(), -direction.x()) / screenLength
                    offset = 0 if isinstance(owners[0], MeasurementGuide) and len(owners) == 1 else 20 + 30 * tier
                    dimensionStart = firstPoint + normal * offset
                    dimensionEnd = secondPoint + normal * offset
                    labelPosition = (dimensionStart + dimensionEnd) / 2
                    label = FormatLength(QtCore.QLineF(firstVertex, secondVertex).length(), self.unitsMode,
                                         adaptive = measurementUnit, includeUnit = False, precision = self.measurementPrecision)
                    labelPath = (MeasurementTextPath(label, painter.font().toString(), painter.device().logicalDpiY())
                                 if self.unitsMode in imperialModes else None)
                    labelWidth = (labelPath.boundingRect().width() if labelPath is not None else painter.fontMetrics().horizontalAdvance(label)) + 12
                    labelRect = QtCore.QRectF(-labelWidth / 2, -10, labelWidth, 20)
                    if manualGuide is not None:
                        labelPosition, angle, labelRect, labelHitPath = self.MeasurementLabelLayout(
                            manualGuide, painter.fontMetrics(), label, labelPath)
                    painter.setPen(LinePen(selectedColor if isSelected else themeColors["measurementLine"], self.lineWidths["dimensions"]))
                    if not boundary:
                        painter.drawLine(QtCore.QLineF(dimensionStart, dimensionEnd))
                    if manualGuide is not None and not manualGuide.textOffset.isNull():
                        painter.drawLine(QtCore.QLineF((dimensionStart + dimensionEnd) / 2, labelPosition))
                    for endpoint, dimensionPoint in (() if boundary else ((firstPoint, dimensionStart), (secondPoint, dimensionEnd))):
                        painter.drawLine(QtCore.QLineF(endpoint + normal * 4, dimensionPoint + normal * 4))
                        tick = (direction / screenLength + normal) * 3
                        painter.drawLine(QtCore.QLineF(dimensionPoint - tick, dimensionPoint + tick))
                    painter.save()
                    painter.translate(labelPosition)
                    painter.rotate(angle)
                    painter.fillRect(labelRect, QtGui.QColor(themeColors["canvas"]))
                    painter.setPen(QtGui.QColor(selectedColor if isSelected else themeColors["objectOutline"]))
                    if labelPath is not None:
                        painter.translate(-labelPath.boundingRect().center())
                        painter.fillPath(labelPath, painter.pen().color())
                    else:
                        painter.drawText(labelRect, QtCore.Qt.AlignmentFlag.AlignCenter, label)
                    painter.restore()

        if picture is not None:
            # Retain two annotation modes, with a bounded vector payload. The
            # recording covers offscreen spans so camera movement needs no
            # Python geometry/text preparation; the target painter clips it.
            if picture.size() <= 4 * 1024 * 1024:
                previous = [(key, cached, position) for key, cached, position in pictures if key != pictureKey]
                self.measurementPictures = [(pictureKey, picture, QtCore.QPointF(origin))] + previous[:1]
            targetPainter.save()
            targetPainter.drawPicture(QtCore.QPointF(), picture)
            targetPainter.restore()

    def DrawLabels(self, painter, pixelsPerMillimeter, highlightedIds = (), hoveredWall = None,
                   drawText = True, drawOutlines = True, drawingRect = None, dirtyRects = None, commandKey = None):
        """Draw scene labels for both viewport painting and offscreen exports."""
        if commandKey is not None and drawText and not drawOutlines and self.labelPreview is None:
            key = (commandKey, painter.font().toString(), painter.renderHints(), painter.device().logicalDpiX(), painter.device().logicalDpiY())
            cached = getattr(self, "panLabelCommands", None)
            if cached is None or cached[0] != key:
                picture = QtGui.QPicture()
                if (picture.logicalDpiX() == painter.device().logicalDpiX()
                        and picture.logicalDpiY() == painter.device().logicalDpiY()):
                    with QtGui.QPainter(picture) as recorder:
                        recorder.setFont(painter.font())
                        recorder.setRenderHints(painter.renderHints())
                        self.DrawLabels(recorder, pixelsPerMillimeter, highlightedIds, drawOutlines = False,
                                        drawingRect = QtCore.QRectF(-1e12, -1e12, 2e12, 2e12))
                    cached = (key, picture, self.WorldToViewport(QtCore.QPointF()))
                    self.panLabelCommands = cached if picture.size() <= 4 * 1024 * 1024 else (key, None)
                else:
                    cached = self.panLabelCommands = (key, None)
            if cached[1] is not None:
                painter.save()
                painter.translate(self.WorldToViewport(QtCore.QPointF()) - cached[2])
                painter.drawPicture(QtCore.QPointF(), cached[1])
                painter.restore()
                return
        drawingRect = self.DrawingRect() if drawingRect is None else drawingRect
        for label in self.labels + ([self.labelPreview] if self.labelPreview is not None else []):
            if not self.IsObjectVisible(label):
                continue
            isOutlined = drawOutlines and (id(label) in highlightedIds or label is hoveredWall)
            if not drawText and not isOutlined:
                continue
            if drawText:
                font, textWidth, textHeight, textBounds, lines = label.TextLayout()
                transform = QtGui.QTransform().translate(*self.WorldToViewport((label.firstVertex + label.secondVertex) / 2).toTuple())
                transform.rotate(-label.angle)
                transform.scale(label.width * pixelsPerMillimeter / textWidth, label.length * pixelsPerMillimeter / textHeight)
                # Use glyph bounds, including bearings/accents, rather than the
                # nominal label box; rotation and nonuniform scaling both matter.
                bounds = transform.mapRect(textBounds).adjusted(-2, -2, 2, 2)
                if bounds.intersects(drawingRect) and (dirtyRects is None or any(bounds.intersects(rect) for rect in dirtyRects)):
                    painter.save()
                    painter.setWorldTransform(transform, True)
                    painter.setFont(font)
                    painter.setOpacity(label.intensity)
                    painter.setPen(QtGui.QColor(self.SelectionColor(label) if id(label) in highlightedIds else themeColors["objectOutline"]))
                    for entry in lines:
                        line, position = entry[:2]
                        if len(entry) == 3:
                            painter.setFont(entry[2])
                        painter.drawText(position, line)
                    painter.restore()
            if isOutlined and self.WallPolygon(label).boundingRect().adjusted(-2, -2, 2, 2).intersects(drawingRect):
                painter.setPen(QtGui.QPen(QtGui.QColor(self.SelectionColor(label) if id(label) in highlightedIds else themeColors["objectOutline"]), 1, QtCore.Qt.PenStyle.DotLine))
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawPolygon(self.WallPolygon(label))

        if drawText:
            for obj in self.furnishings + ([self.furnishingPreview] if isinstance(self.furnishingPreview, NorthArrow) else []):
                if not isinstance(obj, NorthArrow) or not self.IsObjectVisible(obj):
                    continue
                center = self.WorldToViewport((obj.firstVertex + obj.secondVertex) / 2)
                color = self.SelectionColor(obj) if id(obj) in highlightedIds else themeColors["objectOutline"]
                painter.save()
                painter.setOpacity(painter.opacity() * obj.intensity)
                DrawNorthArrow(painter, center, obj.width * pixelsPerMillimeter, obj.length * pixelsPerMillimeter,
                               obj.angle, color, self.lineWidths["furnishings"], solidBackground = self.solidObjects)
                painter.restore()

    def DrawRulerFrame(self, painter, rulerUnit, allEdges = False, drawUnits = True):
        """Finish rulers with canvas separators, the unit corner and outer frame."""
        cornerRects = [QtCore.QRectF(0, 0, self.rulerSize, self.rulerSize)]
        if allEdges:
            right = self.width() - self.rulerSize
            bottom = self.height() - self.rulerSize
            for cornerX, cornerY in ((right, 0), (0, bottom), (right, bottom)):
                cornerRects.append(QtCore.QRectF(cornerX, cornerY, self.rulerSize, self.rulerSize))
        for cornerRect in cornerRects:
            painter.fillRect(cornerRect, QtGui.QColor(themeColors["rulerBackground"]))
        # Clear ticks from the unit corners before drawing their shared edges.
        # Each separator spans the frame so every corner has both inner sides.
        painter.setPen(QtGui.QColor(themeColors["rulerMinorTick"]))
        painter.drawLine(QtCore.QLineF(0, self.rulerSize, self.width(), self.rulerSize))
        painter.drawLine(QtCore.QLineF(self.rulerSize, 0, self.rulerSize, self.height()))
        if allEdges:
            painter.drawLine(QtCore.QLineF(0, bottom, self.width(), bottom))
            painter.drawLine(QtCore.QLineF(right, 0, right, self.height()))
        painter.setPen(QtGui.QColor(themeColors["rulerText"]))
        if drawUnits:
            for cornerRect in cornerRects:
                painter.drawText(cornerRect, QtCore.Qt.AlignmentFlag.AlignCenter, rulerUnit)

        painter.setPen(QtGui.QPen(QtGui.QColor(themeColors["border"]), 1.0))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def DrawGridBackground(self, painter, drawingRect, origin, pixelsPerMillimeter, gridOnly = False, drawGrid = True,
                           allEdges = False, markingsOnly = False):
        # Choose a metric 1/2/5 interval with enough room for ruler labels.
        majorStep, minorStep = self.GridSteps()
        roomClip = QtGui.QPainterPath()
        if drawGrid and not markingsOnly and not getattr(self, "exportRender", False):
            cachedRooms = self.roomDetection.path
            if not cachedRooms.isEmpty():
                transform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(pixelsPerMillimeter, -pixelsPerMillimeter)
                roomClip = transform.map(cachedRooms)
        if not roomClip.isEmpty():
            painter.save()
            painter.setClipRect(drawingRect, QtCore.Qt.ClipOperation.IntersectClip)
            painter.fillPath(roomClip, QtGui.QColor(themeColors["roomFill"]))
            painter.restore()
        origin = origin + QtCore.QPointF(self.gridOrigin[0] * pixelsPerMillimeter, -self.gridOrigin[1] * pixelsPerMillimeter)
        gridSpacing = minorStep * pixelsPerMillimeter
        majorEvery = max(1, round(majorStep / minorStep))
        millimetersPerUnit, rulerUnit = GridUnit(majorStep, self.unitsMode)
        labelStep = majorStep / millimetersPerUnit
        decimalPlaces = max(0, -math.floor(math.log10(labelStep)))
        if self.unitsMode == "Millimeters":
            decimalPlaces = 0

        if drawGrid and not markingsOnly and self.referenceImage is not None:
            self.referenceImage.Draw(painter, drawingRect)

        if not gridOnly:
            painter.fillRect(QtCore.QRectF(0, 0, self.width(), self.rulerSize), QtGui.QColor(themeColors["rulerBackground"]))
            painter.fillRect(QtCore.QRectF(0, 0, self.rulerSize, self.height()), QtGui.QColor(themeColors["rulerBackground"]))
            if allEdges:
                painter.fillRect(QtCore.QRectF(0, self.height() - self.rulerSize, self.width(), self.rulerSize),
                                 QtGui.QColor(themeColors["rulerBackground"]))
                painter.fillRect(QtCore.QRectF(self.width() - self.rulerSize, 0, self.rulerSize, self.height()),
                                 QtGui.QColor(themeColors["rulerBackground"]))
        rulerFont = QtGui.QFont(self.font())
        rulerFont.setPointSizeF(8.0)
        painter.setFont(rulerFont)
        # Keep the ordinary 28-pixel label/tick band against the canvas edge;
        # additional border width extends outward beyond the ruler labels.
        labelOffset = max(0, self.rulerSize - 28)

        for axis in (0, 1):
            axisOrigin = origin.x() if axis == 0 else origin.y()
            extent = drawingRect.right() if axis == 0 else drawingRect.bottom()
            # Include strokes whose centers lie just outside the canvas.
            # Their visible fringe must exist before a cached pan scrolls it
            # inward. The widest grid pen (the origin) is 1.5 logical pixels.
            firstIndex = math.ceil(((drawingRect.left() if axis == 0 else drawingRect.top()) - axisOrigin - .75) / gridSpacing)
            lastIndex = math.floor((extent - axisOrigin + .75) / gridSpacing)
            gridLines = {"origin": [], "major": [], "minor": []}
            tickLines = {True: [], False: []}
            majorLabels = []
            for gridIndex in range(firstIndex, lastIndex + 1):
                position = axisOrigin + gridIndex * gridSpacing
                # Stabilize aliased grid strokes at fractional DPI. Equivalent
                # whole-device-pixel positions can otherwise land on opposite
                # sides of a floating-point stroke-coverage threshold.
                ratio = painter.device().devicePixelRatioF()
                position = (round(position * ratio, 6) + .000001) / ratio
                isMajor = gridIndex % majorEvery == 0
                gridKind = "origin" if gridIndex == 0 else "major" if isMajor else "minor"
                tickLength = 9 if isMajor else 4
                if axis == 0:
                    gridLines[gridKind].append(QtCore.QLineF(position, drawingRect.top(), position, drawingRect.bottom()))
                    tickLines[isMajor].append(QtCore.QLineF(position, self.rulerSize - tickLength, position, self.rulerSize))
                else:
                    gridLines[gridKind].append(QtCore.QLineF(drawingRect.left(), position, drawingRect.right(), position))
                    tickLines[isMajor].append(QtCore.QLineF(self.rulerSize - tickLength, position, self.rulerSize, position))
                if isMajor:
                    if self.unitsMode in imperialModes:
                        label = FormatLength(abs(gridIndex * minorStep), self.unitsMode, decimals = 4)
                    else:
                        value = abs(gridIndex * minorStep) / millimetersPerUnit
                        label = f"{value:,.{decimalPlaces}f}"
                        if decimalPlaces:
                            label = label.rstrip("0").rstrip(".")
                    majorLabels.append((position, label))

            # Batch each pen/clip combination instead of resetting painter state
            # for every line. Grid pan cost then scales mainly with line drawing.
            if self.showGrid and drawGrid:
                painter.save()
                painter.setClipRect(drawingRect, QtCore.Qt.ClipOperation.IntersectClip)
                for gridKind, lines in gridLines.items():
                    intensity = self.gridIntensities["overall"] * self.gridIntensities[gridKind]
                    if lines and intensity > 0:
                        color = QtGui.QColor(themeColors["grid"])
                        color.setAlphaF(min(1.0, intensity))
                        painter.setPen(QtGui.QPen(color, 1.5 if gridKind == "origin" else 1.0))
                        painter.drawLines(lines)
                painter.restore()

            if gridOnly:
                continue
            painter.save()
            painter.setClipRect(QtCore.QRectF(self.rulerSize, 0, self.width() - self.rulerSize, self.rulerSize) if axis == 0 else
                                QtCore.QRectF(0, self.rulerSize, self.rulerSize, self.height() - self.rulerSize))
            for isMajor, lines in tickLines.items():
                if lines:
                    painter.setPen(QtGui.QColor(themeColors["rulerMajorTick"] if isMajor else themeColors["rulerMinorTick"]))
                    painter.drawLines(lines)
            painter.setPen(QtGui.QColor(themeColors["rulerText"]))
            for position, label in (() if markingsOnly else majorLabels):
                if axis == 0:
                    painter.drawText(QtCore.QRectF(position - 42, labelOffset, 84, 18), QtCore.Qt.AlignmentFlag.AlignCenter, label)
                else:
                    painter.save()
                    painter.translate(labelOffset, position)
                    painter.rotate(-90)
                    painter.drawText(QtCore.QRectF(-42, 0, 84, 18), QtCore.Qt.AlignmentFlag.AlignCenter, label)
                    painter.restore()
            painter.restore()

            if allEdges:
                painter.save()
                edge = self.height() - self.rulerSize if axis == 0 else self.width() - self.rulerSize
                painter.setClipRect(QtCore.QRectF(self.rulerSize, edge, drawingRect.width(), self.rulerSize) if axis == 0 else
                                    QtCore.QRectF(edge, self.rulerSize, self.rulerSize, drawingRect.height()))
                for isMajor, lines in tickLines.items():
                    if lines:
                        painter.setPen(QtGui.QColor(themeColors["rulerMajorTick"] if isMajor else themeColors["rulerMinorTick"]))
                        if axis == 0:
                            oppositeLines = [QtCore.QLineF(line.x1(), self.height() - line.y1(), line.x2(), self.height() - line.y2())
                                             for line in lines]
                        else:
                            oppositeLines = [QtCore.QLineF(self.width() - line.x1(), line.y1(), self.width() - line.x2(), line.y2())
                                             for line in lines]
                        painter.drawLines(oppositeLines)
                painter.setPen(QtGui.QColor(themeColors["rulerText"]))
                for position, label in (() if markingsOnly else majorLabels):
                    if axis == 0:
                        painter.drawText(QtCore.QRectF(position - 42, self.height() - 18 - labelOffset, 84, 18),
                                         QtCore.Qt.AlignmentFlag.AlignCenter, label)
                    else:
                        painter.save()
                        painter.translate(self.width() - 18 - labelOffset, position)
                        painter.rotate(-90)
                        painter.drawText(QtCore.QRectF(-42, 0, 84, 18), QtCore.Qt.AlignmentFlag.AlignCenter, label)
                        painter.restore()
                painter.restore()

        return rulerUnit

