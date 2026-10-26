"""Local furnishing resize, rotation and temporary pivot handles."""

import math
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets

from planner_app.graphics.palette import themeColors
from planner_app.graphics.icons import UiIconPath
from planner_app.models import Furnishing, Label, Pillar, Column, Fireplace, Wall, Window
from planner_app.geometry.editing import (TransformPoint, ResizeHandleDimensions, ResizedHandleCenter,
    PrepareSelectionMembers, SelectionSpan, FitSelectionScale, TransformSelectionMembers)


from collections import OrderedDict
handleRenderers = OrderedDict()


class FurnishingHandlesMixin:
    def FurnishingSelectionBox(self):
        entries = self.SelectionEntries()
        if len(entries) < 2 or any(not isinstance(obj, (Furnishing, Wall, Window)) or index is not None for obj, index in entries):
            return None
        if any(isinstance(obj, Window) for obj, index in entries) and not any(isinstance(obj, Wall) for obj, index in entries):
            return None
        objects = tuple(obj for obj, index in entries)
        footprints = [self.ObjectFootprint(obj) for obj in objects]
        key = tuple((id(obj), obj.footprintCache[0]) for obj in objects)
        if key != self.furnishingSelectionBoxKey:
            bounds = QtCore.QRectF(footprints[0][0])
            for footprint in footprints[1:]:
                bounds = bounds.united(footprint[0])
            box = Furnishing(self.furnishingDefinitions["null"])
            box.rotationOnly = any(not isinstance(obj, (Furnishing, Pillar)) for obj in objects)
            # Collinear measurement guides can have a zero-area footprint.
            height = max(bounds.height(), 1) if box.rotationOnly else bounds.height()
            box.firstVertex = bounds.center() - QtCore.QPointF(0, height / 2)
            box.secondVertex = bounds.center() + QtCore.QPointF(0, height / 2)
            box.width = max(bounds.width(), 1) if box.rotationOnly else bounds.width()
            box.selectionMembers = objects
            box.proportionalResize = any(isinstance(obj, Label) for obj in objects)
            self.furnishingSelectionBox = box
            self.furnishingSelectionBoxKey = key
        return self.furnishingSelectionBox

    def FurnishingHandles(self, furnishing, pivot = None):
        if isinstance(furnishing, Fireplace):
            return [handle for handle in self.FurnishingHandles(furnishing.HandleBox()) if handle[0] == "resize"]
        center = (furnishing.firstVertex + furnishing.secondVertex) / 2
        north = (furnishing.secondVertex - furnishing.firstVertex) / furnishing.length
        east = QtCore.QPointF(north.y(), -north.x())
        screenCenter = self.WorldToViewport(center)
        handles = []
        cornerHandles = []
        for field, axis, size in (("width", east, furnishing.width), ("length", north, furnishing.length)):
            if isinstance(furnishing, Label) or getattr(furnishing, "proportionalResize", False):
                continue
            for sign in (-1, 1):
                edge = self.WorldToViewport(center + axis * (size * sign / 2))
                outward = QtCore.QPointF(axis.x(), -axis.y()) * sign
                handles.append(("resize", field, sign, edge + outward * 44, outward))
        for eastSign, northSign in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            corner = self.WorldToViewport(center + east * (furnishing.width * eastSign / 2)
                                          + north * (furnishing.length * northSign / 2))
            outward = corner - screenCenter
            outward /= math.hypot(outward.x(), outward.y())
            handles.append(("rotate", None, None, corner + outward * 44, outward))
            diagonal = east * eastSign + north * northSign
            diagonal = QtCore.QPointF(diagonal.x(), -diagonal.y()) / math.sqrt(2)
            cornerHandles.append(("resize", "corner", (eastSign, northSign), corner + diagonal * 44, diagonal))
        handles.extend(cornerHandles)
        pivot = pivot if pivot is not None else self.rotationPivot if self.rotationPivot is not None else center
        handles.append(("pivot", None, None, self.WorldToViewport(pivot), QtCore.QPointF()))
        return handles

    def VisibleFurnishingHandles(self, hoverHit = None, position = None):
        if self.referenceImage is not None and self.referenceImage.active:
            return []
        if self.openingPlacementMode is not None or self.pendingWall is not None or self.isPanning:
            return []
        if (self.dragStart is not None and self.furnishingHandleDrag is None
                and not isinstance(self.selectedWall, (Furnishing, Label, Pillar))):
            return []
        selectionBox = self.FurnishingSelectionBox()
        if selectionBox is not None:
            mode = "rotate" if selectionBox.rotationOnly or any(obj is self.furnishingRotationObject for obj in selectionBox.selectionMembers) else "resize"
            return [(selectionBox, [handle for handle in self.FurnishingHandles(selectionBox)
                                    if handle[0] == mode or mode == "rotate" and handle[0] == "pivot"])]
        selectedIds = {id(obj) for obj, index in self.SelectionEntries()}
        hovered = None
        position = self.hoverPosition if position is None else position
        worldHover = self.ViewportToWorld(position) if position is not None else None
        hoverMargin = 56 / (self.basePixelsPerMillimeter * self.zoom)
        if position is not None and self.DrawingRect().contains(position):
            hovered, index = self.HitTest(position) if hoverHit is None else hoverHit
        visible = []
        for furnishing in self.furnishings + self.labels + [obj for obj in self.walls if isinstance(obj, Pillar)] + [obj for obj in self.windows if isinstance(obj, Fireplace)]:
            if not self.IsObjectVisible(furnishing):
                continue
            if id(hovered) in selectedIds and id(furnishing) not in selectedIds:
                # These handles cannot intercept the selected body. Do not
                # reveal them as if they were available under the pointer.
                continue
            if id(furnishing) not in selectedIds and furnishing is not hovered:
                if position is None:
                    continue
                bounds = self.ObjectFootprint(furnishing)[0]
                if not bounds.adjusted(-hoverMargin, -hoverMargin, hoverMargin, hoverMargin).contains(worldHover):
                    continue
            handles = self.FurnishingHandles(furnishing)
            mode = "rotate" if id(furnishing) in selectedIds and furnishing is self.furnishingRotationObject else "resize"
            handles = [handle for handle in handles if handle[0] == mode or mode == "rotate" and handle[0] == "pivot"]
            nearHandle = position is not None and any(
                QtCore.QLineF(position, handle[3]).length() <= 9 for handle in handles)
            if id(furnishing) in selectedIds or furnishing is hovered or nearHandle:
                visible.append((furnishing, handles))
        visible.sort(key = lambda item: id(item[0]) in selectedIds)
        return visible

    def HitFurnishingHandle(self, position, hoverHit = None):
        hoverHit = self.HitTest(position) if hoverHit is None else hoverHit
        selectedIds = {id(obj) for obj, index in self.SelectionEntries()}
        visible = self.VisibleFurnishingHandles(hoverHit = hoverHit, position = position)
        for furnishing, handles in reversed(visible):
            if (id(hoverHit[0]) in selectedIds and id(furnishing) not in selectedIds
                    and not getattr(furnishing, "selectionMembers", ())):
                continue
            for handle in handles:
                if QtCore.QLineF(position, handle[3]).length() <= 9:
                    return furnishing, handle
        return None, None

    def BeginFurnishingHandleDrag(self, furnishing, handle, position):
        fireplace = furnishing if isinstance(furnishing, Fireplace) else None
        if fireplace is not None:
            self.SetSelection([(fireplace, None)])
            furnishing = fireplace.HandleBox()
        self.pendingFurnishingHandleToggle = None
        members = getattr(furnishing, "selectionMembers", ())
        structuralRotation = getattr(furnishing, "rotationOnly", False)
        if members:
            furnishing = furnishing.Clone()
            furnishing.selectionMembers = members
        elif fireplace is None:
            self.SetSelection([(furnishing, None)])
        self.interactionBefore = self.CaptureState()
        self.dragStart = position
        self.isDragging = False
        center = (furnishing.firstVertex + furnishing.secondVertex) / 2
        north = (furnishing.secondVertex - furnishing.firstVertex) / furnishing.length
        pivot = QtCore.QPointF(self.rotationPivot if self.rotationPivot is not None else center)
        offset = self.ViewportToWorld(position) - pivot
        self.furnishingHandleDrag = {
            "fireplace": fireplace, "mouseStart": QtCore.QPointF(position),
            "object": furnishing, "handle": handle, "center": center, "north": north,
            "width": furnishing.width, "length": furnishing.length, "angle": furnishing.angle,
            "pivot": pivot, "previousPivot": self.rotationPivot,
            "mouseAngle": math.degrees(math.atan2(offset.y(), offset.x())),
            "members": [(obj, QtCore.QPointF(obj.firstVertex), QtCore.QPointF(obj.secondVertex), obj.width, getattr(obj, "angle", 0))
                        for obj in members],
            "sourceObject": furnishing, "sourceEntries": list(self.SelectionEntries()),
            "sourceRotationObject": self.furnishingRotationObject,
            "sourceStates": [(obj, QtCore.QPointF(obj.firstVertex), QtCore.QPointF(obj.secondVertex), obj.width, getattr(obj, "angle", 0))
                             for obj in members or [furnishing]],
            "copies": [],
            "structuralRotation": structuralRotation,
        }
        if structuralRotation:
            self.PrepareWallSelectionRotation(self.furnishingHandleDrag)
        self.UpdateCanvasCursor()
        self.update()

    def UpdateFurnishingHandleDrag(self, position, modifiers):
        state = self.furnishingHandleDrag
        furnishing = state["object"]
        if (position - self.dragStart).manhattanLength() >= QtWidgets.QApplication.startDragDistance():
            self.isDragging = True
        if not self.isDragging:
            return
        mode, field, sign, handlePosition, outward = state["handle"]
        if state["structuralRotation"] and mode == "rotate":
            self.UpdateWallSelectionRotation(state, position, modifiers)
            self.selectionChanged.emit()
            self.update()
            return
        if mode == "rotate":
            # Rotating asymmetric selections changes their axis-aligned bounds.
            # Retain the actual origin rather than following that bounds center,
            # both for the visible pivot and for subsequent rotation gestures.
            if state["members"] and self.rotationPivot is None:
                self.rotationPivot = QtCore.QPointF(state["pivot"])
            duplicate = bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier) and not self.ObjectsHaveAssetErrors(
                obj for obj, first, second, width, angle in state["sourceStates"])
            if duplicate != bool(state["copies"]):
                copyIds = {id(obj) for obj in state["copies"]}
                self.furnishings = [obj for obj in self.furnishings if id(obj) not in copyIds]
                self.labels = [obj for obj in self.labels if id(obj) not in copyIds]
                self.walls = [obj for obj in self.walls if id(obj) not in copyIds]
                self.objectGroups = list(self.interactionBefore[6])
                state["copies"] = []
                for obj, first, second, width, angle in state["sourceStates"]:
                    obj.firstVertex, obj.secondVertex, obj.width = QtCore.QPointF(first), QtCore.QPointF(second), width
                if duplicate:
                    copies = {}
                    for obj, first, second, width, angle in state["sourceStates"]:
                        if isinstance(obj, Pillar):
                            copy = type(obj)(QtCore.QPointF(first), QtCore.QPointF(second), width,
                                             obj.firstMiter, obj.secondMiter, obj.material)
                            copy.measurementHidden = obj.measurementHidden
                            self.walls.append(copy)
                        else:
                            copy = obj.Clone()
                            (self.labels if isinstance(obj, Label) else self.furnishings).append(copy)
                        copies[id(obj)] = copy
                        state["copies"].append(copy)
                    for group in self.interactionBefore[6]:
                        copiedGroup = tuple(copies[id(obj)] for obj in group if id(obj) in copies)
                        if len(copiedGroup) >= 2:
                            self.objectGroups.append(copiedGroup)
                    state["object"] = state["sourceObject"] if state["members"] else state["copies"][0]
                    if state["members"]:
                        state["members"] = [(copies[id(obj)], first, second, width, angle)
                                            for obj, first, second, width, angle in state["sourceStates"]]
                        state["object"].selectionMembers = tuple(state["copies"])
                    self.SetSelection([(obj, None) for obj in state["copies"]])
                    self.furnishingRotationObject = state["copies"][-1]
                else:
                    state["object"] = state["sourceObject"]
                    if state["members"]:
                        state["members"] = list(state["sourceStates"])
                        state["object"].selectionMembers = tuple(entry[0] for entry in state["sourceStates"])
                    self.SetSelection(state["sourceEntries"])
                    self.furnishingRotationObject = state["sourceRotationObject"]
                # Selection normally clears a temporary pivot; this selection is
                # the same gesture transferred to its duplicate.
                self.rotationPivot = QtCore.QPointF(state["pivot"])
            furnishing = state["object"]
        state["centeredResize"] = mode == "resize" and bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier)
        if mode == "pivot":
            delta = self.ViewportToWorld(position) - self.ViewportToWorld(self.dragStart)
            self.rotationPivot = state["pivot"] + self.SnapObjectMovement(
                [state["pivot"]], delta, modifiers,
                snapTargets = list(self.SnapVertices()) + self.StairSnapTargets())
            if self.axisConstraintOrigin is not None:
                self.axisConstraintOrigin = state["pivot"]
            self.selectionChanged.emit()
            self.update()
            return
        self.TransformFurnishingHandle(state, position, modifiers)
        if state["members"]:
            self.TransformFurnishingSelection(state)
        if state.get("fireplace") is not None:
            fireplace = state["fireplace"]
            parentLength = QtCore.QLineF(fireplace.parentWall.firstVertex, fireplace.parentWall.secondVertex).length()
            maxWidth, minDepth = parentLength, fireplace.parentWall.width
            if state.get("centeredResize", False):
                direction, normal = fireplace.Axes()
                offset = state["center"] - fireplace.parentWall.firstVertex
                along = QtCore.QPointF.dotProduct(offset, direction)
                maxWidth = 2 * min(along, parentLength - along)
                minDepth += 2 * abs(QtCore.QPointF.dotProduct(offset, normal))
            fireplace.length = min(furnishing.length, maxWidth)
            fireplace.depth = max(furnishing.width, minDepth)
            fireplace.SetCenter((furnishing.firstVertex + furnishing.secondVertex) / 2)
        self.selectionChanged.emit()
        self.update()

    def TransformFurnishingHandle(self, state, position, modifiers):
        """Apply the shared single-object resize/rotation math without committing an edit."""
        furnishing = state["object"]
        mode, field, sign = state["handle"][:3]
        north = state["north"]
        center = QtCore.QPointF(state["center"])
        furnishing.width = state["width"]
        furnishing.firstVertex = center - north * (state["length"] / 2)
        furnishing.secondVertex = center + north * (state["length"] / 2)
        if mode == "rotate":
            offset = self.ViewportToWorld(position) - state["pivot"]
            if math.hypot(offset.x(), offset.y()) > 1e-8:
                angle = state["angle"] + math.degrees(math.atan2(offset.y(), offset.x())) - state["mouseAngle"]
                if self.snapEnabled != bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier):
                    origin = state["angle"] if self.localTransforms else 0
                    angle = origin + round((angle - origin) / 15) * 15
                furnishing.angle = angle
                rotation = math.radians(angle - state["angle"])
                targetCenter = QtCore.QPointF(*TransformPoint((state["center"].x(), state["center"].y()),
                    (state["pivot"].x(), state["pivot"].y()), None, math.cos(rotation), math.sin(rotation)))
                furnishing.firstVertex += targetCenter - center
                furnishing.secondVertex += targetCenter - center
        else:
            delta = self.ViewportToWorld(position) - self.ViewportToWorld(state["mouseStart"])
            numericNorth = (north.x(), north.y())
            width, length = ResizeHandleDimensions(numericNorth, state["width"], state["length"],
                (delta.x(), delta.y()), field, sign, state["centeredResize"], .001 if isinstance(furnishing, Label) else 1)
            width, length = self.SnapFurnishingResize(state, width, length, modifiers)
            center = QtCore.QPointF(*ResizedHandleCenter((state["center"].x(), state["center"].y()), numericNorth,
                state["width"], state["length"], width, length, field, sign, state["centeredResize"]))
            furnishing.width = width
            furnishing.firstVertex = center - north * (length / 2)
            furnishing.secondVertex = center + north * (length / 2)

    def SnapFurnishingResize(self, state, width, length, modifiers):
        self.snapApplied = False
        self.snapPriority = 3
        self.alignmentGuides = []
        if self.snapEnabled == bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier):
            return width, length
        north = state["north"]
        east = QtCore.QPointF(north.y(), -north.x())
        field, sign = state["handle"][1:3]
        factor = 2 if state.get("centeredResize", False) else 1
        targets = self.StairSnapTargets(state.get("fireplace") or state["object"])
        if field == "corner":
            eastSign, northSign = sign
            diagonal = east * (eastSign * state["width"]) + north * (northSign * state["length"])
            anchor = state["center"] if factor == 2 else state["center"] - diagonal / 2
            corner = anchor + (east * (eastSign * width) + north * (northSign * length)) / factor
            snapped = self.SnapPosition(corner, modifiers, anchor, diagonal / math.hypot(diagonal.x(), diagonal.y()),
                                        snapTargets = targets)
            scale = factor * QtCore.QPointF.dotProduct(snapped - anchor, diagonal) / QtCore.QPointF.dotProduct(diagonal, diagonal)
            minimumSize = .001 if isinstance(state["object"], Label) else 1
            scale = max(minimumSize / min(state["width"], state["length"]), scale)
            return state["width"] * scale, state["length"] * scale
        axis = north if field == "length" else east
        tangent = east if field == "length" else north
        size = length if field == "length" else width
        halfSpan = (state["width"] if field == "length" else state["length"]) / 2
        anchor = state["center"] if factor == 2 else state["center"] - axis * (sign * state[field] / 2)
        edgeCenter = anchor + axis * (sign * size / factor)
        candidates = []
        for offset in (QtCore.QPointF(), tangent * halfSpan, -tangent * halfSpan):
            point = edgeCenter + offset
            snapped = self.SnapPosition(point, modifiers, anchor + offset, axis * sign, snapTargets = targets)
            if self.snapApplied:
                snappedSize = factor * sign * QtCore.QPointF.dotProduct(snapped - anchor - offset, axis)
                if snappedSize >= 1:
                    candidates.append((self.snapPriority, QtCore.QLineF(point, snapped).length(),
                                       snappedSize, list(self.alignmentGuides)))
        # An edge can meet a vertex anywhere along its span, not just at its ends.
        directTargets = [QtCore.QPointF(x, y) for x, y, direct in self.NumericSnapTargets(targets) if direct]
        if self.midpointSnapEnabled:
            directTargets.extend(self.SnapMidpoints())
        pixelsPerMillimeter = self.basePixelsPerMillimeter * self.zoom
        for target in directTargets:
            offset = target - edgeCenter
            if abs(QtCore.QPointF.dotProduct(offset, tangent)) > halfSpan + .01:
                continue
            distance = abs(QtCore.QPointF.dotProduct(offset, axis))
            snappedSize = factor * sign * QtCore.QPointF.dotProduct(target - anchor, axis)
            if distance * pixelsPerMillimeter < self.vertexSnapRange and snappedSize >= 1:
                candidates.append((0, distance, snappedSize, []))
        self.alignmentGuides = []
        self.snapApplied = bool(candidates)
        if candidates:
            priority, distance, size, self.alignmentGuides = min(candidates, key = lambda candidate: candidate[:2])
            self.snapPriority = priority
        return (width, size) if field == "length" else (size, length)

    def TransformFurnishingSelection(self, state):
        box = state["object"]
        center = (box.firstVertex + box.secondVertex) / 2
        rotation = math.radians(box.angle - state["angle"])
        scaleX, scaleY = box.width / state["width"], box.length / state["length"]
        prepared = self.PreparedFurnishingMembers(state)
        mode, field = state["handle"][:2]
        if mode == "resize" and field in ("width", "length"):
            axis = 0 if field == "width" else 1
            scaleX, scaleY = FitSelectionScale(prepared, scaleX, scaleY, axis, box.width if axis == 0 else box.length)
        membersById = {id(obj): obj for obj, first, second, width, angle in state["members"]}
        for key, first, second, width, angle in TransformSelectionMembers(prepared, (center.x(), center.y()), scaleX, scaleY, rotation):
            obj = membersById[key]
            obj.width = width
            obj.firstVertex, obj.secondVertex = QtCore.QPointF(*first), QtCore.QPointF(*second)
            obj.angle = angle
        if state["handle"][0] == "resize":
            bounds = QtCore.QRectF(self.ObjectFootprint(state["members"][0][0])[0])
            for obj, first, second, width, angle in state["members"][1:]:
                bounds = bounds.united(self.ObjectFootprint(obj)[0])
            field, sign = state["handle"][1:3]
            correction = center - bounds.center()
            if field == "width" and not state.get("centeredResize", False):
                anchoredX = state["center"].x() - sign * state["width"] / 2
                correction.setX(anchoredX - (bounds.center().x() - sign * bounds.width() / 2))
            elif field == "length" and not state.get("centeredResize", False):
                anchoredY = state["center"].y() - sign * state["length"] / 2
                correction.setY(anchoredY - (bounds.center().y() - sign * bounds.height() / 2))
            for obj, first, second, width, angle in state["members"]:
                obj.firstVertex += correction
                obj.secondVertex += correction

    def FurnishingSelectionSpan(self, state, scaleX, scaleY, axis):
        return SelectionSpan(self.PreparedFurnishingMembers(state), scaleX, scaleY, axis)

    def PreparedFurnishingMembers(self, state):
        # Original gesture geometry is immutable; duplicate toggles replace the
        # member list. Keep a single prepared record per gesture, not per frame.
        members = state["members"]
        origin = (state["center"].x(), state["center"].y())
        cached = state.get("preparedMemberGeometry")
        if cached is None or cached[0] is not members or cached[1] != len(members) or cached[2] != origin:
            prepared = PrepareSelectionMembers([(id(obj), (first.x(), first.y()), (second.x(), second.y()), width, angle,
                                                QtCore.QLineF(first, second).length())
                                               for obj, first, second, width, angle in members], origin)
            cached = (members, len(members), origin, prepared)
            state["preparedMemberGeometry"] = cached
        return cached[3]

    def DrawFurnishingHandles(self, painter, hoverHit = None):
        selectedIds = {id(obj) for obj, index in self.SelectionEntries()}
        for furnishing, handles in self.VisibleFurnishingHandles(hoverHit):
            members = getattr(furnishing, "selectionMembers", ())
            state = self.furnishingHandleDrag
            if state is not None and state["structuralRotation"]:
                invalid = not state["rotationValid"]
            else:
                invalid = (state is not None and
                           (any(not self.FurnishingFits(obj) for obj in members) if members else
                            furnishing is state["object"] and not self.FurnishingFits(furnishing)))
            if isinstance(furnishing, Fireplace) and self.furnishingHandleDrag is not None:
                invalid = not self.OpeningFits(furnishing)
            selectedColor = themeColors["groupSelectionOutline"] if members and any(self.SelectionColor(obj) == themeColors["groupSelectionOutline"] for obj in members) else self.SelectionColor(furnishing)
            color = QtGui.QColor(themeColors["invalidOutline"] if invalid else selectedColor if members or id(furnishing) in selectedIds else themeColors["objectOutline"])
            if members:
                painter.setPen(QtGui.QPen(color, 1, QtCore.Qt.PenStyle.DashLine))
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawPolygon(self.WallPolygon(furnishing))
            self.DrawFurnishingHandleSet(painter, handles, color)

    def DrawFurnishingHandleSet(self, painter, handles, color):
        for mode, field, sign, position, outward in handles:
            if mode == "resize":
                iconName = "handle_up_right" if field == "corner" else "handle_up"
            else:
                iconName = "refresh" if mode == "rotate" else "pivot"
            iconPath = UiIconPath(iconName, color)
            if iconPath not in handleRenderers:
                handleRenderers[iconPath] = QtSvg.QSvgRenderer(str(iconPath))
                while len(handleRenderers) > 64:
                    handleRenderers.popitem(last = False)
            else:
                handleRenderers.move_to_end(iconPath)
            painter.save()
            painter.translate(position)
            if mode == "resize":
                angle = math.degrees(math.atan2(outward.y(), outward.x()))
                painter.rotate(angle + (45 if field == "corner" else 90))
            handleRenderers[iconPath].render(painter, QtCore.QRectF(-10, -10, 20, 20))
            painter.restore()
