"""Frozen pre-final-pass methods; journal layout adapted to current observer."""
"""Viewport grid, scene painting, dimensions, rulers and selection feedback."""
from planner_app.graphics.text import PathTextPainter
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
from planner_app.graphics.symbols import DrawOpeningSymbol, DrawStairSymbol, DrawStairArrows, WallOpeningPolygons
from planner_app.geometry.stair_annotations import StairArrowRuns, StairEndpointNeighbors
from planner_app.graphics.arrows import ArrowPaths, ConnectedArrowDirections, ConnectedArrowCorners
from planner_app.models import OpenDoorway, Door, SwingingDoor, DoubleDoor, Furnishing, PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, SlidingDoor, MeasurementGuide, BoundaryLine, DashedLine, SolidLine, Arrow, Counter, Railing, Stair, Wall, Pillar, Column, Label, Window, NorthArrow, Fireplace
from planner_app.units import MetricUnit, FormatLength, PropertyUnit, GridUnit, imperialModes
from planner_app.graphics.measurement_text import MeasurementTextPath
from planner_app.graphics.retained_dimensions import RetainedDimensions
from planner_app.geometry.measurement_stacks import BuildMeasurementStacks, VisibleWallDimensionSpans, StackedDimensionLengths
from planner_app.geometry.measurements import GuideDepthOffset
from planner_app.viewport.geometry import CollisionPass
from planner_app.viewport.spatial_index import BoundsIndex
from planner_app.viewport.diagnostics import MeasurePaint
from planner_app.viewport.edit_cache import EditPaintCacheMixin
from planner_app.viewport.polygon_clipping import SubtractConvexPolygon

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



"""Selection, connected objects, group movement and undo/redo history."""
from planner_app.models import AngleGuide, NorthArrow, ObjectControlPoints, SetControlPoint, DashedLine, Elevator

import math
import time
from planner_app.object_schema import openingFields
from planner_app.geometry.attachments import AttachedVertexIndices, ConnectedAttachments
from planner_app.geometry.editing import TransformPoint, OpeningTransformTarget, ReattachTransformedOpening, RebaseMergedOpening, ChooseWallSplit, OpeningOrientationChanges, PointerRotation
from planner_app.selection_copy import OpeningCopyTargets, RemapCopiedGroups
from planner_app.geometry.selection_edits import MoveObjectRecord, ReflectionObjectRecord, PlanMoveSelection, PlanSelectionReflection
from planner_app.geometry.linear_edits import PlanSubdivision, PlanDissolution
from planner_app.geometry.group_movement import (OpeningTransferLength, PlanOpeningTransfer, ProjectGroupTravel, GroupOpeningLimits,
    BoundGroupTravel, TranslatedOpeningFraction, AttachedConstraintPoint)
from planner_app.viewport.geometry import CollisionPass
from planner_app.viewport.spatial_index import BoundsIndex
from planner_app.scene_changes import SceneObject
from planner_app.history_edits import SceneEdit, ReferenceImageEdit
from planner_app.furnishing_parts import FurnishingParts, FurnishingCollisionFootprints
from planner_app.furnishing_imports import ResolveFurnishingImports
from planner_app.project_codec import EncodeFurnishingDefinitions
from planner_app.graphics.path_operations import Paths
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import (
    Door, SwingingDoor, DoubleDoor, Furnishing, PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, SlidingDoor, MeasurementGuide, Arrow, Counter, Railing, Stair, Wall, Pillar, Column, Label, Window, Fireplace, objectIdCounter,
)


def SnapshotPointMatches(point, x, y):
    pointX, pointY = point.x(), point.y()
    if pointX != x or pointY != y:
        return False
    # Signed zero can affect angle calculations; retain snapshot signs as well.
    return ((x != 0 or math.copysign(1, pointX) == math.copysign(1, x))
            and (y != 0 or math.copysign(1, pointY) == math.copysign(1, y)))


def SnapshotPointData(points):
    """Compare mutable baseline coordinates exactly using native serialization."""
    data = QtCore.QByteArray()
    stream = QtCore.QDataStream(data, QtCore.QIODevice.OpenModeFlag.WriteOnly)
    stream << QtGui.QPolygonF(points)
    return data


def NativeEditAffine(operation, *values):
    if operation == "reflection":
        center, angle, horizontal = values
        transform = QtGui.QTransform().translate(*center).rotate(angle)
        transform.scale(-1 if horizontal else 1, 1 if horizontal else -1)
        transform.rotate(-angle).translate(-center[0], -center[1])
        return transform.m11(), transform.m12(), transform.m21(), transform.m22(), transform.dx(), transform.dy()
    if operation == "point":
        point, frame = values
        target = QtGui.QTransform(*frame).map(QtCore.QPointF(*point))
        return target.x(), target.y()
    raise ValueError("Unknown edit affine operation")



"""Grid, alignment, endpoint and oriented-footprint snapping."""
from planner_app.geometry.endpoint_snapping import NearestRunControlTarget
from planner_app.models import AngleGuide, ObjectControlPoints

import math
from planner_app.geometry.snapping import GridIntervals, SnapPoint, PrepareTargetIndex, PrepareRayTargets
from planner_app.geometry.measurements import GuideDepthOffset
from planner_app.geometry.movement_snapping import (MovementAxes, ConstraintAxes, ConstrainedAngle,
    ConstrainMovement, SnapMovement)
from planner_app.geometry.endpoint_snapping import CapEndpoint, AlignmentPlacementCandidates, SelectEndpointSnap
from planner_app.graphics.path_operations import Paths
from PySide6 import QtCore
from planner_app.models import Furnishing, MeasurementGuide, Arrow, Counter, Railing, Stair, Wall, Pillar, Column, Label, Window, Fireplace
from planner_app.units import imperialModes
from planner_app.viewport.geometry import CollisionPass


class CornerSnapPoint(QtCore.QPointF):
    """A footprint or joined-boundary target, distinct from a control point."""


def MovementSnapDistance(x, y):
    # Qt and Python hypot can differ by one bit. Keep the native metric so
    # equally close anchors retain the same winning alignment guide.
    return QtCore.QLineF(0.0, 0.0, x, y).length()



"""Placement previews, opening fitting, collision validation and sidebar drops."""
from planner_app.models import AngleGuide

from planner_app.models import Elevator

import math
from contextlib import contextmanager
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import OpenDoorway, Door, SwingingDoor, DoubleDoor, Furnishing, PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, SlidingDoor, MeasurementGuide, BoundaryLine, DashedLine, SolidLine, Arrow, Counter, Railing, Stair, Wall, Pillar, Column, Label, RoomLabel, Window, NorthArrow, Fireplace
from planner_app.viewport.geometry import CollisionPass
from planner_app.geometry.opening_placement import (ProjectOpening, OpeningGap,
    BlockedOpeningIntervals, OpeningPlacementSpan, CenteredOpeningSpan, OpeningVertexFraction)
from planner_app.geometry.opening_collisions import OpeningCollisionIndex
from planner_app.geometry.reserved_doors import ReservedDoorWithinHost, ReservedDoorWallContact, ReservedDoorPlacementBounds, ReservedDoorEditCenter
from planner_app.geometry.opening_candidates import OpeningFacingChanges, FireplaceDepthSnap, FireplacePlacementCandidates
from planner_app.viewport.placement_types import OpeningFacingPolicy
from planner_app.viewport.spatial_index import BoundsIndex
from planner_app.geometry.attachments import FitOpeningCenters, OpeningWithinWall, OpeningIntervalsOverlap
from planner_app.placement_sizing import NominalPlacementSize, FurnishingPlacementSize



from fixtures.movement_reference_20261031 import SnapMovement
from planner_app.viewport.widget import DrawingViewport


class ReferenceViewport(DrawingViewport):
    def DrawScene(self, painter, drawingRect, origin, pixelsPerMillimeter, dirtyRects = None,
                  drawAnnotations = True, retainAnnotations = False, bakePassageClips = False, passageClearance = None):
        bakePassageClips = (bakePassageClips or bool(self.windows)
                           and painter.paintEngine().type() == QtGui.QPaintEngine.Type.SVG)
        if passageClearance is None:
            passageClearance = 0
            # Remove clipped wall-stroke fringes in both room styles. Canvas
            # passages get explicit thin edges instead of leftover stroke ink.
            # Retain destination sampling/DPR through transparent recording.
            inverseDevice, invertible = painter.deviceTransform().inverted()
            if invertible:
                passageClearance = math.hypot(inverseDevice.m11(), inverseDevice.m12(), inverseDevice.m21(), inverseDevice.m22())
        if not self.solidObjects:
            retainCapture = getattr(self, "retainExportCapture", False) and isinstance(painter.device(), QtGui.QImage)
            captures = getattr(self, "exportObjectCaptures", [])
            captureKey = None
            retained = None
            if retainCapture:
                captureKey = self.SceneRenderKey((self.zoom, self.basePixelsPerMillimeter,
                    self.width(), self.height(), drawingRect.x(), drawingRect.y(), drawingRect.width(), drawingRect.height(),
                    origin.x(), origin.y(), pixelsPerMillimeter, bakePassageClips, passageClearance,
                    self.floors, self.wallStyle, self.font().toString(), painter.font().toString(),
                    painter.renderHints().value, painter.device().logicalDpiX(), painter.device().logicalDpiY(),
                    tuple(themeColors.items())))
                for index, capture in enumerate(captures):
                    if capture[0] == captureKey:
                        retained = capture
                        captures.append(captures.pop(index))
                        break
            if retained is not None:
                device, sceneState = retained[1:3]
            else:
                device = ObjectPaintDevice(self.size(), themeColors["canvas"])
                sourcePainter = PathTextPainter(device)
                originalRenderers = (self.furnishingRenderers, self.selectedFurnishingRenderers, self.groupedFurnishingRenderers)
                try:
                    sourcePainter.setFont(painter.font())
                    sourcePainter.setRenderHints(painter.renderHints())
                    sourcePainter.setClipRect(drawingRect)
                    self.solidObjects = True
                    self.objectCaptureEngine = device.engine
                    captureRenderers = (
                        (renderers.Copy(solidBackground = True) if hasattr(renderers, "Copy") else
                         {key: getattr(renderer, "solidRenderer", renderer) for key, renderer in renderers.items()})
                        for renderers in originalRenderers)
                    # These are temporary paint resources, not a scene edit.
                    # Bypass the viewport's edit observer while borrowing them,
                    # then restore the exact original maps and their ownership.
                    for name, renderers in zip(("furnishingRenderers", "selectedFurnishingRenderers", "groupedFurnishingRenderers"), captureRenderers):
                        object.__setattr__(self, name, renderers)
                    sceneState = self.DrawScene(sourcePainter, drawingRect, origin, pixelsPerMillimeter,
                                                dirtyRects, drawAnnotations = False, bakePassageClips = bakePassageClips,
                                                passageClearance = passageClearance)
                finally:
                    sourcePainter.end()
                    self.solidObjects = False
                    self.objectCaptureEngine = None
                    for name, renderers in zip(("furnishingRenderers", "selectedFurnishingRenderers", "groupedFurnishingRenderers"), originalRenderers):
                        object.__setattr__(self, name, renderers)
                if retainCapture:
                    elements = imageBytes = 0
                    seenClips = set()
                    for path, pen, brush, transform, opacity, clip, mask, hints, brushOrigin in device.engine.commands:
                        if isinstance(path, tuple):
                            imageBytes += path[1].sizeInBytes()
                        else:
                            elements += path.elementCount()
                        elements += mask.elementCount()
                        if clip is not None and id(clip) not in seenClips:
                            seenClips.add(id(clip))
                            elements += clip.elementCount()
                    captures.append((captureKey, device, sceneState, elements, imageBytes))
                    # Retain original Qt commands, not a serialized or scaled
                    # picture. Bound both native geometry and embedded images.
                    while captures and (len(captures) > 4 or sum(len(item[1].engine.commands) for item in captures) > 8192
                            or sum(item[3] for item in captures) > 262144 or sum(item[4] for item in captures) > 16 * 1024 * 1024):
                        captures.pop(0)
                    self.exportObjectCaptures = captures
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
        coincidentGroups = prepared.get("coincidentGroups")
        if coincidentGroups is None:
            coincidentGroups = prepared["coincidentGroups"] = self.CoincidentObjectGroups()
        if advisoryIds is None:
            advisoryIds = prepared["architecturalAdvisories"] = ({id(obj) for obj in containedObjects + self.DuplicateArchitecturalObjects(groups = coincidentGroups)}
                if not getattr(self, "exportRender", False) else set())
        invalidArchitecture = prepared.get("invalidArchitecture")
        if invalidArchitecture is None:
            invalidArchitecture = prepared["invalidArchitecture"] = self.InvalidArchitecturalObjects()
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
                id(obj) for group in coincidentGroups if type(group[0]) is Furnishing for obj in group[:-1]}
        def DrawFurnishings(behindCounters):
            for obj in furnishingLayers[behindCounters]:
                # Exact rear copies cannot contribute visible artwork. Painting
                # their dark strokes under the warning leaves dark antialias fringes.
                if id(obj) in occludedFurnishings:
                    continue
                bounds = furnishingBounds.get(id(obj))
                if bounds is None:
                    renderers = self.furnishingRenderers
                    artwork = (renderers.ArtworkGeometry(obj.definition["key"]) if hasattr(renderers, "ArtworkGeometry")
                               else renderers[obj.definition["key"]])
                    bounds = self.ObjectFootprint(obj)[0].united(FurnishingArtworkBounds(obj, artwork))
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
        # Parent projection/fraction clamping is scene geometry, not camera work.
        # Keep detached world endpoints under the existing revision key, then
        # transform them at the exact current camera position for native pixels.
        worldOpeningPositions = prepared.get("openingPositions")
        if worldOpeningPositions is None:
            worldOpeningPositions = prepared["openingPositions"] = {
                id(opening): (opening.firstVertex, opening.secondVertex) for opening in visibleWindows}
        openingPositions = {key: (self.WorldToViewport(first), self.WorldToViewport(second))
                            for key, (first, second) in worldOpeningPositions.items()}
        painter.save()
        doorwayClip = QtGui.QPainterPath()
        doorwayClip.setFillRule(QtCore.Qt.FillRule.OddEvenFill)
        doorwayClip.addRect(drawingRect)
        openingClipRect = drawingRect.adjusted(-2, -2, 2, 2)
        # A scrolled pan raster only paints these exposed strips. Distant holes
        # enlarge Qt's clip work even though none of their pixels can be written.
        openingPaintRects = ([rect.adjusted(-2, -2, 2, 2) for rect in dirtyRects]
                             if self.isPanning and dirtyRects is not None else (openingClipRect,))
        jambNeighbors = prepared.setdefault("openingJambNeighbors", {})
        jambIndex = prepared.get("openingJambIndex")
        jambWork = 0
        openingCuts = []
        openingCutPolygons = []
        for opening in visibleWindows:
            # Actual wall cuts end at the square-capped jambs. Do not enlarge
            # them along with the separate stair occlusion clearance below.
            firstPoint, secondPoint = openingPositions[id(opening)]
            # Clear the stroke's antialias fringe across passages. Only
            # the wall-normal clearance grows; jamb positions stay exact.
            for polygonIndex, polygon in enumerate(WallOpeningPolygons(opening, firstPoint, secondPoint, pixelsPerMillimeter, self.lineWidths["walls"],
                                                                       outlineClearance = passageClearance)):
                convexCuts = [polygon]
                if passageClearance > 0 and (not isinstance(opening, PocketDoor) or polygonIndex == 0):
                    # Protect a jamb only where another wall actually meets it;
                    # blanket protection leaves short fringes at small scales.
                    along = polygon[1] - polygon[0]
                    length = math.hypot(along.x(), along.y())
                    across = polygon[0] - polygon[3]
                    thickness = math.hypot(across.x(), across.y())
                    if length > 1e-10 and thickness > 1e-10:
                        neighborKey = id(opening), polygonIndex
                        protected = jambNeighbors.get(neighborKey)
                        if protected is None:
                            worldFirst, worldSecond = worldOpeningPositions[id(opening)]
                            worldDirection = worldSecond - worldFirst
                            worldLength = math.hypot(worldDirection.x(), worldDirection.y())
                            halfWidth = (opening.parentWall.width if isinstance(opening, Fireplace) else opening.width) / 2
                            worldNormal = QtCore.QPointF(-worldDirection.y(), worldDirection.x()) * (halfWidth / max(worldLength, 1e-20))
                            jambTolerance = .1
                            run = secondPoint - firstPoint
                            runSquared = QtCore.QPointF.dotProduct(run, run)
                            protected = []
                            for endpoint in ((polygon[0] + polygon[3]) / 2, (polygon[1] + polygon[2]) / 2):
                                fraction = QtCore.QPointF.dotProduct(endpoint - firstPoint, run) / max(runSquared, 1e-20)
                                position = worldFirst + (worldSecond - worldFirst) * fraction
                                jambPoints = (position, position + worldNormal, position - worldNormal)
                                # Amortize setup only after linear probes have
                                # shown enough work; early nearby matches stay cheap.
                                if (jambIndex is None and len(visibleWalls) >= 32 and len(visibleWindows) >= 4
                                        and jambWork >= len(visibleWalls)):
                                    wallIndex, wallFootprints, fallback = BoundsIndex(2000), [], []
                                    for wallIndexPosition, wall in enumerate(visibleWalls):
                                        bounds, corners, _ = self.ObjectFootprint(wall)
                                        expanded = bounds.adjusted(-jambTolerance, -jambTolerance, jambTolerance, jambTolerance)
                                        wallFootprints.append((expanded, corners))
                                        if all(math.isfinite(value) for value in expanded.getCoords()):
                                            wallIndex.Insert(expanded.normalized(), wallIndexPosition)
                                        else:
                                            fallback.append(wallIndexPosition)
                                    jambIndex = prepared["openingJambIndex"] = wallIndex, wallFootprints, fallback
                                if jambIndex is not None and all(math.isfinite(value) for point in jambPoints for value in (point.x(), point.y())):
                                    wallIndex, wallFootprints, fallback = jambIndex
                                    wallCandidates = sorted(set(fallback).union(*(wallIndex.PointCandidates((point.x(), point.y())) for point in jambPoints)))
                                else:
                                    wallCandidates = range(len(visibleWalls))
                                touchesWall = False
                                for wallIndexPosition in wallCandidates:
                                    jambWork += 1
                                    wall = visibleWalls[wallIndexPosition]
                                    if wall is opening.parentWall:
                                        continue
                                    if jambIndex is None:
                                        bounds, corners, _ = self.ObjectFootprint(wall)
                                        expanded = bounds.adjusted(-jambTolerance, -jambTolerance, jambTolerance, jambTolerance)
                                    else:
                                        expanded, corners = jambIndex[1][wallIndexPosition]
                                    if not any(expanded.contains(jambPoint) for jambPoint in jambPoints):
                                        continue
                                    footprint = QtGui.QPolygonF(corners)
                                    if any(footprint.containsPoint(jambPoint + offset, QtCore.Qt.FillRule.OddEvenFill)
                                           for jambPoint in jambPoints
                                           for offset in (QtCore.QPointF(), QtCore.QPointF(jambTolerance, 0), QtCore.QPointF(-jambTolerance, 0),
                                                          QtCore.QPointF(0, jambTolerance), QtCore.QPointF(0, -jambTolerance),
                                                          QtCore.QPointF(jambTolerance, jambTolerance), QtCore.QPointF(-jambTolerance, jambTolerance),
                                                          QtCore.QPointF(jambTolerance, -jambTolerance), QtCore.QPointF(-jambTolerance, -jambTolerance))):
                                        touchesWall = True
                                        break
                                protected.append(touchesWall)
                            jambNeighbors[neighborKey] = protected
                        if any(protected):
                            inset = along / length * min(self.lineWidths["walls"] / 2, length / 2)
                            firstInset = inset if protected[0] else QtCore.QPointF()
                            secondInset = inset if protected[1] else QtCore.QPointF()
                            guard = across / thickness * (passageClearance + self.lineWidths["walls"] / 2)
                            first, second, third, fourth = polygon
                            polygon = QtGui.QPolygonF([first - guard, first + firstInset - guard, first + firstInset,
                                second - secondInset, second - secondInset - guard, second - guard,
                                third + guard, third - secondInset + guard, third - secondInset,
                                fourth + firstInset, fourth + firstInset + guard, fourth + guard])
                            convexCuts = [QtGui.QPolygonF([first + firstInset, second - secondInset,
                                                          third - secondInset, fourth + firstInset])]
                            if protected[0]:
                                convexCuts.append(QtGui.QPolygonF([first - guard, first + firstInset - guard,
                                                                   fourth + firstInset + guard, fourth + guard]))
                            if protected[1]:
                                convexCuts.append(QtGui.QPolygonF([second - secondInset - guard, second - guard,
                                                                   third + guard, third - secondInset + guard]))
                if self.isPanning and not any(polygon.boundingRect().intersects(rect) for rect in openingPaintRects):
                    continue
                doorwayClip.addPolygon(polygon)
                doorwayClip.closeSubpath()
                if bakePassageClips:
                    openingCutPolygons.extend((cut.boundingRect(), cut) for cut in convexCuts)
                    cut = QtGui.QPainterPath()
                    cut.addPolygon(polygon)
                    cut.closeSubpath()
                    openingCuts.append(cut)
        if not bakePassageClips:
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
            if bakePassageClips:
                # Clip each owner's simple footprint before regrouping fills.
                # A boolean against the building-sized compound path can lose
                # unrelated wall strips when nearly coincident edges collapse.
                materialPaths = {}
                owners = {id(wall): wall for wall in visibleWalls}
                columnPaths = getattr(self, "columnMaterialPaths", {})
                clippedOwners = set()
                for owner, polygon in self.wallFillPolygons:
                    if isinstance(owner, Column):
                        continue
                    if columnPaths:
                        if id(owner) in clippedOwners:
                            continue
                        clippedOwners.add(id(owner))
                        # These owner paths already exclude native column fills.
                        fragments = [list(polygon) for polygon in viewTransform.map(self.wallMaterialPaths[id(owner)]).toFillPolygons()]
                    else:
                        fragments = [list(viewTransform.map(polygon))]
                    material = owner.material
                    localPath = materialPaths.setdefault(material, QtGui.QPainterPath())
                    localPath.setFillRule(QtCore.Qt.FillRule.WindingFill)
                    localPath.addPath(self.CutOpeningPolygons(fragments, openingCutPolygons))
                for wallId, ownerPath in self.wallMaterialPaths.items():
                    if not isinstance(owners[wallId], Column):
                        continue
                    clipped = viewTransform.map(ownerPath)
                    for cut in openingCuts:
                        if clipped.boundingRect().intersects(cut.boundingRect()):
                            clipped = clipped.subtracted(cut)
                    localPath = materialPaths.setdefault(owners[wallId].material, QtGui.QPainterPath())
                    localPath.setFillRule(QtCore.Qt.FillRule.WindingFill)
                    localPath.addPath(clipped)
            for material, path in materialPaths.items():
                brush = QtGui.QBrush(QtGui.QColor(themeColors["wallOutline"])) if self.wallStyle == "Solid" else self.materialBrushes[(material, False)]
                fillPath = path if bakePassageClips else viewTransform.map(path)
                painter.fillPath(fillPath, brush)
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
        # Installing a building-sized clip can dominate SVG rendering even
        # when there are no lumber cross-lines to draw. Submit it lazily for
        # the first visible lumber wall, just as during panning.
        lumberClipSet = False
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
        windowOutlineCuts = []
        windowOutlineClip.setFillRule(QtCore.Qt.FillRule.OddEvenFill)
        windowOutlineClip.addRect(drawingRect)
        for window in visibleWindows:
            if isinstance(window, (Door, SwingingDoor, DoubleDoor, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway, Fireplace)):
                continue
            polygon = self.WallPolygon(window)
            if self.isPanning:
                bounds = polygon.boundingRect().adjusted(-self.lineWidths["walls"] - 2, -self.lineWidths["walls"] - 2,
                                                         self.lineWidths["walls"] + 2, self.lineWidths["walls"] + 2)
                if not any(bounds.intersects(rect) for rect in openingPaintRects):
                    continue
            openingPath = QtGui.QPainterPath()
            openingPath.addPolygon(polygon)
            openingPath.closeSubpath()
            painter.fillPath(openingPath, QtGui.QColor(themeColors["canvas"]))
            firstPoint, secondPoint = openingPositions[id(window)]
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
                if not self.isPanning or any(outlineHole.boundingRect().intersects(rect) for rect in openingPaintRects):
                    windowOutlineClip.addPolygon(outlineHole)
                    windowOutlineClip.closeSubpath()
                    if bakePassageClips:
                        windowOutlineCuts.append((outlineHole.boundingRect(), outlineHole))
        painter.save()
        if not bakePassageClips:
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
                outlinePath = viewTransform.map(path)
                if bakePassageClips:
                    # SVG viewers differ in their support for inverse clips.
                    # Cut the actual stroke/fill geometry at passage openings.
                    if painter.pen().style() != QtCore.Qt.PenStyle.NoPen:
                        stroke = Paths.PreparePenStroke(painter.pen())
                        outlinePath = stroke(outlinePath).intersected(windowOutlineClip)
                        for cut in openingCuts:
                            outlinePath = outlinePath.subtracted(cut)
                        if not occluders.isEmpty():
                            outlinePath = outlinePath.subtracted(viewTransform.map(occluders))
                        painter.fillPath(outlinePath, painter.pen().brush())
                else:
                    painter.drawPath(outlinePath)
                painter.restore()
        else:
            strokeDrawn = False
            if bakePassageClips:
                if painter.pen().style() != QtCore.Qt.PenStyle.NoPen:
                    stroke = Paths.PreparePenStroke(painter.pen())
                    # The stroker emits overlapping winding contours. Normalize
                    # those before booleans: near-coincident edges can otherwise
                    # turn a room-sized hole into filled ink in SVG previews.
                    outlinePath = self.CutOpeningPolygons(stroke(combinedPath).simplified().toFillPolygons(),
                                                          openingCutPolygons + windowOutlineCuts)
                    painter.fillPath(outlinePath, painter.pen().brush())
                strokeDrawn = True
            if (not strokeDrawn and self.isPanning and captureEngine is None and self.viewportSceneByteLimit > 0
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
            positions = openingPositions.get(id(opening))
            firstPoint, secondPoint = (positions if positions is not None else
                                       (self.WorldToViewport(opening.firstVertex), self.WorldToViewport(opening.secondVertex)))
            if dirtyRects is not None or self.isPanning or not getattr(self, "exportRender", False):
                bounds = QtCore.QRectF(firstPoint, secondPoint).normalized()
                # Swing tips extend a full leaf length from a hinge on the wall
                # face, not its centerline. Include that offset when a door
                # re-enters a newly exposed pan strip.
                reach = max(opening.length, opening.depth + abs(opening.depthOffset) if isinstance(opening, Fireplace) else 60)
                padding = (reach + opening.width / 2 + getattr(opening, "sillDepth", 0)
                           + (opening.wellDepth + 150 if opening.windowWell else 0)) * pixelsPerMillimeter + max(self.lineWidths.values()) + 24
                if not any(bounds.adjusted(-padding, -padding, padding, padding).intersects(rect)
                           for rect in (dirtyRects if dirtyRects is not None else (drawingRect,))):
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
            DrawOpeningSymbol(painter, firstPoint, secondPoint,
                              opening.width * pixelsPerMillimeter, type(opening),
                              opening.hingeAtSecond if isinstance(opening, (Door, SwingingDoor, SlidingDoor, PocketDoor, CasementWindow)) else False,
                              opening.swingsOutwards if type(opening) in (Window, Door, DoubleDoor, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, BarnDoor, BifoldDoor) else False, color,
                              opening.panelsFlipped if isinstance(opening, SlidingDoor) else False, pixelsPerMillimeter,
                              opening.sillDepth if isinstance(opening, SilledWindow) else 40.0,
                              lineWidth = self.lineWidths["architectural"], wallLineWidth = self.lineWidths["walls"],
                              wallColor = themeColors["warningOutline"] if warning else
                              themeColors["invalidOutline"] if id(opening) in invalidArchitecture or id(opening.parentWall) in invalidWalls else themeColors["wallOutline"],
                              windowWell = opening.windowWell, wellDepth = opening.wellDepth, wellDashed = opening.wellDashed,
                              # Keep the corrected passage policy; retain frozen rendering preparation.
                              drawPassageEdges = self.drawOpeningOutlines if getattr(self, "exportRender", False) or self.exportOverlay.active else True)
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
                neighbors = StairEndpointNeighbors(visibleStairs)
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
                openings = QtGui.QPainterPath()
                openings.setFillRule(QtCore.Qt.FillRule.WindingFill)
                for opening in visibleWindows:
                    first = QtCore.QPointF(opening.firstVertex.x(), -opening.firstVertex.y()) * pixelsPerMillimeter
                    second = QtCore.QPointF(opening.secondVertex.x(), -opening.secondVertex.y()) * pixelsPerMillimeter
                    # A cut exactly tangent to the stroke's outer edge can make
                    # Qt's subtraction fill an enclosed room at certain scales.
                    # Cross that edge fully, keeping the jamb endpoints fixed.
                    for polygon in WallOpeningPolygons(opening, first, second, pixelsPerMillimeter,
                                                        self.lineWidths["walls"], outlineClearance = boundaryWidth / 2):
                        openings.addPolygon(polygon)
                        openings.closeSubpath()
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
                    with PathTextPainter(picture) as recorder:
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

    def UpdateGroupDrag(self, position, modifiers):
        if self.controlHeld:
            modifiers |= QtCore.Qt.KeyboardModifier.ControlModifier
        if (position - self.dragStart).manhattanLength() >= QtWidgets.QApplication.startDragDistance():
            self.isDragging = True
        if not self.isDragging:
            return
        self.groupOpeningPreviews = []
        self.inactiveOpeningPreview = None
        movementBefore = None
        if any(type(obj) is Wall for obj, index in self.groupEntries) and any(isinstance(opening, PocketDoor) for opening in self.windows):
            movedPoints = {(id(obj), index): (obj, index, QtCore.QPointF(ObjectControlPoints(obj)[index]))
                           for obj, index, original in self.groupMovedVertices}
            for obj, index, parent, fraction, normalOffset in self.dragConstraints:
                movedPoints.setdefault((id(obj), index), (obj, index, QtCore.QPointF(ObjectControlPoints(obj)[index])))
            movementBefore = tuple(movedPoints.values()), self.CaptureOpeningStates()
        before = self.interactionBefore
        self.RestoreGroupBaseline(before)
        connectionKey = (self.connectedEnabled, self.connectedVerticesEnabled, self.connectedObjectsEnabled)
        if not self.dragCopies and connectionKey != self.groupConnectionKey:
            self.StartGroupDrag()
        duplicate = all(index is None for obj, index in self.groupSourceEntries) and bool(
            modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier) and not self.ObjectsHaveAssetErrors(
                obj for obj, index in self.groupSourceEntries)
        if duplicate != bool(self.dragCopies):
            movementBefore = None  # A changed copy selection has no previous frame to restore.
            copyIds = {id(obj) for obj in self.dragCopies}
            self.walls = [obj for obj in self.walls if id(obj) not in copyIds]
            self.windows = [obj for obj in self.windows if id(obj) not in copyIds]
            self.furnishings = [obj for obj in self.furnishings if id(obj) not in copyIds]
            self.labels = [obj for obj in self.labels if id(obj) not in copyIds]
            self.dragCopies = []
            self.objectGroups = list(before[6])
            if duplicate:
                copies = self.DuplicateSelectionObjects([obj for obj, index in self.groupSourceEntries], before[6])
                self.dragCopies = list(copies.values())
                self.SetSelection([(copies[id(obj)], index) for obj, index in self.groupSourceEntries])
            else:
                self.SetSelection(self.groupSourceEntries)
            self.StartGroupDrag()
        self.RestoreOpeningStates(self.groupOpeningStates)
        delta = self.ViewportToWorld(position) - self.ViewportToWorld(self.dragStart)
        if self.ReattachOpeningGroup(delta, modifiers):
            self.selectionChanged.emit()
            self.update()
            return
        movingIds = {id(obj) for obj, index, vertex in self.groupMovedVertices}
        movingIds.update(id(obj) for obj, index in self.groupMovedOpenings)
        fixedOpenings = [(obj, index) for obj, index in self.groupMovedOpenings if id(obj.parentWall) not in movingIds]
        # Openings on fixed walls constrain the common group translation to
        # their wall axis. Nonparallel fixed parents have no shared travel axis.
        parentGeometry = {}
        for opening, index in fixedOpenings:
            parent = opening.parentWall
            if id(parent) not in parentGeometry:
                direction = parent.secondVertex - parent.firstVertex
                parentGeometry[id(parent)] = ((direction.x(), direction.y()), math.hypot(direction.x(), direction.y()))
        numericDelta, numericTravel, travelBlocked = ProjectGroupTravel((delta.x(), delta.y()),
            (parentGeometry[id(opening.parentWall)][0] for opening, index in fixedOpenings))
        delta = QtCore.QPointF(*numericDelta)
        travel = QtCore.QPointF(*numericTravel) if numericTravel is not None else None
        targets, anchors = [], []
        if self.snapEnabled != bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier):
            for obj in self.walls + self.windows + self.furnishings + self.labels:
                if not self.IsObjectVisible(obj) or id(obj) in movingIds or isinstance(obj, Window) and id(obj.parentWall) in movingIds:
                    continue
                targets.extend(ObjectControlPoints(obj))
                targets.extend(self.GuideDepthEndpoints(obj))
            anchors = [vertex for obj, index, vertex in self.groupMovedVertices if not isinstance(obj, AngleGuide)]
            if any(isinstance(obj, Furnishing) for obj, index in self.groupEntries) or all(isinstance(obj, Wall) and index is None for obj, index in self.groupEntries):
                targets = self.StairSnapTargets() + list(self.SnapVertices())
                anchors = [anchor for obj, index in self.groupEntries if not isinstance(obj, AngleGuide)
                           for anchor in self.ObjectCorners(obj) + [(obj.firstVertex + obj.secondVertex) / 2]]
                anchors.extend(vertex for obj, index, vertex in self.groupMovedVertices
                               if isinstance(obj, Wall) and not isinstance(obj, (Pillar, AngleGuide)))
            for opening, index in fixedOpenings:
                anchors.extend(((opening.firstVertex, opening.secondVertex, (opening.firstVertex + opening.secondVertex) / 2)
                                if index is None else (opening.firstVertex if index == 0 else opening.secondVertex,)))
            anchors.extend(self.groupGuideDepthAnchors)
        for obj, index in self.groupEntries:
            if isinstance(obj, AngleGuide):
                anchors.append(ObjectControlPoints(obj)[2 if index is None or index == 3 else index])
        if len(self.groupEntries) == 1 and isinstance(self.groupEntries[0][0], AngleGuide):
            obj, index = self.groupEntries[0]
            targets = self.StairSnapTargets(obj) + list(self.SnapVertices())
        if not travelBlocked:
            if (isinstance(self.selectedWall, AngleGuide) and self.selectedVertex in (0, 1)
                    and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier):
                original = ObjectControlPoints(self.selectedWall)[self.selectedVertex]
                target = self.SnapStairVertex(original + delta, self.selectedWall.middleVertex, self.selectedWall, modifiers)
                delta = target - original
            elif (self.selectedVertex is not None and not isinstance(self.selectedWall, (Window, AngleGuide))
                    and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier):
                vertices = self.dragSourceVertices or self.dragVertices
                original = vertices[self.selectedVertex]
                target = self.SnapStairVertex(original + delta, vertices[1 - self.selectedVertex], self.selectedWall, modifiers)
                delta = target - original
            else:
                delta = self.SnapObjectMovement(anchors, delta, modifiers, snapTargets = targets, travelDirection = travel)
                if isinstance(self.selectedWall, AngleGuide) and modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
                    self.axisConstraintOrigin = QtCore.QPointF(self.selectedWall.middleVertex)
                    self.axisConstraintDirection = None
        openingStates = {id(state[0]): state for state in self.groupOpeningStates} if fixedOpenings else {}
        if travel is not None and not travelBlocked:
            # Prepare stationary neighbours once, retaining their scene order.
            # Copies intentionally ignore these intervals until final validation.
            stationary = {}
            if not self.dragCopies:
                for other in self.windows:
                    parentId = id(other.parentWall)
                    if parentId in parentGeometry and id(other) not in movingIds:
                        stationary.setdefault(parentId, []).append((other.centerFraction, other.firstFraction, other.secondFraction))
            limits = GroupOpeningLimits(numericTravel,
                ((id(opening.parentWall), *parentGeometry[id(opening.parentWall)],
                  openingStates[id(opening)][2], opening.length, index, self.OpeningTravelBounds(opening)) for opening, index in fixedOpenings),
                stationary, bool(self.dragCopies))
            boundedDelta = QtCore.QPointF(*BoundGroupTravel((delta.x(), delta.y()), numericTravel, *limits))
            if QtCore.QLineF(delta, boundedDelta).length() > .01:
                self.alignmentGuides = []
                self.snapApplied = False
            delta = boundedDelta
        for obj, index, vertex in self.groupMovedVertices:
            SetControlPoint(obj, index, vertex + delta)
        selectedKeys = {(id(obj), vertexIndex) for obj, index in self.groupEntries
                        for vertexIndex in ((0, 1) if index is None else (index,))}
        for iteration in range(len(self.dragConstraints) + 1):
            for attached, index, parent, fraction, normalOffset in self.dragConstraints:
                if (id(attached), index) in selectedKeys:
                    continue
                first, second = parent.firstVertex, parent.secondVertex
                vertex = QtCore.QPointF(*AttachedConstraintPoint((first.x(), first.y()), (second.x(), second.y()),
                                                                fraction, normalOffset))
                if index == 0:
                    attached.firstVertex = vertex
                else:
                    attached.secondVertex = vertex
        for opening, index in fixedOpenings:
            parent = opening.parentWall
            direction = parent.secondVertex - parent.firstVertex
            lengthSquared = QtCore.QPointF.dotProduct(direction, direction)
            if lengthSquared <= 1e-10:
                continue
            if index is None:
                opening.centerFraction = TranslatedOpeningFraction(openingStates[id(opening)][2],
                    (delta.x(), delta.y()), (direction.x(), direction.y()))
            else:
                vertex = opening.firstVertex if index == 0 else opening.secondVertex
                self.SetOpeningVertex(opening, index, vertex + delta)
        fitValid = not fixedOpenings or self.GroupOpeningsFit(fixedOpenings)
        if fitValid:
            fixedIds = {id(obj) for obj, index in fixedOpenings}
            openingBefore = (tuple((state[0], state[1], state[0].centerFraction, *state[3:])
                                  if id(state[0]) in fixedIds else state for state in before[3])
                             if fixedIds else before[3])
            # Preview painting validates moving furnishings; release validates the
            # entire scene. Repeating that collision pass here changes no geometry.
            fitValid = self.FitWallOpenings((before[0], before[1], before[2], openingBefore), validateFurnishings = False, validateScene = False)
        if not fitValid and movementBefore is not None:
            points, openings = movementBefore
            for obj, index, point in points:
                SetControlPoint(obj, index, point)
            self.RestoreOpeningStates(openings)
            self.alignmentGuides = []
            self.snapApplied = False
        self.selectionChanged.emit()
        self.update()

    def SnapObjectMovement(self, anchors, delta, modifiers, snapTargets = None, travelDirection = None):
        constrained = self.controlHeld or bool(modifiers & QtCore.Qt.KeyboardModifier.ControlModifier)
        axes = None
        if travelDirection is None and constrained:
            if self.dragStart is not None:
                self.axisConstraintOrigin = self.ViewportToWorld(self.dragStart)
            if self.localTransforms and self.dragStart is not None and self.selectedWall is not None:
                axes = tuple((axis.x(), axis.y()) for axis in self.TranslationAxes())
        delta, direction = ConstrainMovement((delta.x(), delta.y()),
            (travelDirection.x(), travelDirection.y()) if travelDirection is not None else None, constrained, axes)
        if self.snapEnabled == bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier):
            # No target collection or anchor copies on the disabled path.
            delta, self.snapApplied, self.snapPriority, self.alignmentGuides = SnapMovement(
                (), delta, (), 1, 0, False, None, direction)
            return QtCore.QPointF(*delta)
        numericTargets = self.NumericSnapTargets(snapTargets)
        if self.midpointSnapEnabled:
            numericTargets.extend((vertex.x(), vertex.y(), True) for vertex in self.SnapMidpoints())
        targetIndex, rayTargets = None, None
        if direction is None or len(anchors) >= 3:
            numericTargets, targetIndex, rayTargets = self.SnapTargetPreparation(numericTargets, constrained = direction is not None)
        gridStep = self.GridSteps()[1] if self.gridSnapEnabled and anchors else None
        delta, self.snapApplied, self.snapPriority, self.alignmentGuides = SnapMovement(
            [(anchor.x(), anchor.y()) for anchor in anchors], delta, numericTargets,
            self.basePixelsPerMillimeter * self.zoom, self.vertexSnapRange,
            self.alignmentSnapEnabled, gridStep, direction, MovementSnapDistance,
            targetIndex = targetIndex, rayTargets = rayTargets)
        return QtCore.QPointF(*delta)

    @CollisionPass
    def InvalidArchitecturalObjects(self):
        """Validate a read-only paint snapshot, retaining unaffected clear objects."""
        if getattr(self, "exportRender", False):
            return set()
        changes = self.renderChanges
        policyKey = (changes.appearance, changes.topology, changes.visibility,
                     tuple(self.visibility.items()), tuple(self.collisionSettings.items()), self.basePixelsPerMillimeter)
        key = changes.geometry, policyKey
        previous = getattr(self, "architecturalValidation", None)
        if previous is not None and previous[0] == key:
            return previous[1]
        if previous is not None and previous[0][1] == policyKey and len(previous) == 4:
            incremental = self.RefreshArchitecturalValidation(previous, key)
            if incremental is not None:
                return incremental
        records = previous[2] if previous is not None and previous[0][1] == policyKey else {}
        objects = self.walls + self.windows + self.furnishings + self.labels
        categories = {
            "wall": self.furnishings + [obj for obj in self.walls if isinstance(obj, (Counter, Railing, Stair, Elevator))] + self.windows,
            "counter": [obj for obj in self.walls if not isinstance(obj, Counter)],
            "stair": [obj for obj in objects if not isinstance(obj, (Stair, Arrow, MeasurementGuide, Label, NorthArrow))],
            "elevator": self.walls + self.windows + self.furnishings}
        scope = {"objects": objects, "categories": categories, "index": None, "nearby": {}, "furnishingBounds": {}}
        batch = self.collisionPassCache
        previousScope = batch.get("placementValidation")
        batch["placementValidation"] = scope
        invalid, current = set(), {}
        try:
            with self.OpeningCandidatePass(len(self.windows)):
                for obj in self.walls + self.windows:
                    if not self.IsObjectVisible(obj):
                        continue
                    if isinstance(obj, Window):
                        # Host fitting, shared-parent intervals and reserved-door
                        # support can depend on geometry beyond the local bounds.
                        signature = key
                    elif type(obj) in (Wall, Pillar, Column, Counter, Stair, Railing, Elevator):
                        kind = ("stair" if isinstance(obj, Stair) else "counter" if isinstance(obj, Counter)
                                else "elevator" if isinstance(obj, Elevator) else "wall")
                        blockers = self.PlacementBlockers(obj, kind)
                        # Joined footprints can change through an unchanged
                        # neighbor. Keep conservative global invalidation wherever
                        # a collision is possible; clear objects need only their
                        # own size/position checked again after movement.
                        signature = (obj.firstVertex.x(), obj.firstVertex.y(), obj.secondVertex.x(),
                                     obj.secondVertex.y(), obj.width, changes.geometry if blockers else None)
                    else:
                        continue
                    cached = records.get(id(obj))
                    fits = cached[1] if cached is not None and cached[0] == signature else self.ArchitecturalPlacementFits(obj)
                    current[id(obj)] = (signature, fits)
                    if not fits:
                        invalid.add(id(obj))
        finally:
            if previousScope is None:
                batch.pop("placementValidation", None)
            else:
                batch["placementValidation"] = previousScope
        # Reuse this immutable broad phase while only furnishings/annotations
        # move. A small overlay replaces stale furnishing entries in queries.
        scope["nearby"] = {}
        scope["movingBounds"] = {}
        scope["members"] = {id(obj): obj for obj in objects}
        state = {"scope": scope, "objects": scope["members"],
                 "architecture": {id(obj): order for order, obj in enumerate(self.walls)
                                  if id(obj) in current and type(obj) is not Counter},
                 "furnishingBounds": scope["furnishingBounds"]}
        self.architecturalValidation = key, invalid, current, state
        changes.placementChanges = {"objects": {}, "events": 0}
        return invalid

    def PlacementBlockers(self, obj, kind):
        """Ordered broad phase confined to one immutable validation scope."""
        scope = (getattr(self, "collisionPassCache", None) or {}).get("placementValidation")
        if scope is None:
            return None
        members = scope["categories"][kind]
        if not members:
            return ()
        if scope["index"] is None:
            index = BoundsIndex(2000)
            fallback = []
            for member in scope["objects"]:
                if isinstance(member, (Arrow, MeasurementGuide, Label, NorthArrow)):
                    continue
                bounds = self.JoinedObjectBounds(member)
                if type(member) is Furnishing:
                    scope["furnishingBounds"][id(member)] = bounds
                if all(math.isfinite(value) for value in bounds.getCoords()):
                    index.Insert(bounds.normalized().adjusted(-.01, -.01, .01, .01), member)
                else:
                    fallback.append(member)
            scope["index"], scope["fallback"] = index, fallback
            scope["orders"] = {name: {id(member): position for position, member in enumerate(values)}
                               for name, values in scope["categories"].items()}
        identity = id(obj), kind
        if identity not in scope["nearby"]:
            bounds = self.JoinedObjectBounds(obj)
            if not all(math.isfinite(value) for value in bounds.getCoords()):
                nearby = [member for member in members if member is not obj]
            else:
                order = scope["orders"][kind]
                movingBounds = scope.get("movingBounds", {})
                nearby = [member for member in scope["index"].Query(bounds.normalized().adjusted(-.01, -.01, .01, .01))
                          + scope["fallback"] if id(member) in order and member is not obj and id(member) not in movingBounds]
                queryBounds = bounds.normalized().adjusted(-.01, -.01, .01, .01)
                nearby.extend(scope["members"][identity] for identity, currentBounds in movingBounds.items()
                              if identity in order and identity != id(obj)
                              and queryBounds.intersects(currentBounds.normalized().adjusted(-.01, -.01, .01, .01)))
                nearby.sort(key = lambda member: order[id(member)])
            scope["nearby"][identity] = tuple(nearby)
        return scope["nearby"][identity]
