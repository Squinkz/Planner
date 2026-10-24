"""Numeric grid intervals, ordered target lookup and constrained point snapping."""
import math
from bisect import bisect_left, bisect_right


def GridIntervals(pixelsPerMillimeter, imperial):
    minimumStep = 90.0 / pixelsPerMillimeter
    if imperial:
        minimumInches = minimumStep / 25.4
        intervals = (1 / 16, 1 / 8, 1 / 4, .5, 1, 2, 4, 6, 12, 24, 48)
        inches = next((step for step in intervals if step >= minimumInches), None)
        if inches is None:
            inches = 48 * 2 ** math.ceil(math.log2(minimumInches / 48))
        majorStep = inches * 25.4
        return majorStep, majorStep / 4
    magnitude = 10.0 ** math.floor(math.log10(minimumStep))
    majorStep = next(multiplier * magnitude for multiplier in (1, 2, 5, 10)
                     if multiplier * magnitude >= minimumStep)
    return majorStep, majorStep / 5.0


def PrepareTargetIndex(targets):
    orderedX = sorted((target[0], index) for index, target in enumerate(targets))
    orderedY = sorted((target[1], index) for index, target in enumerate(targets))
    return ([value for value, index in orderedX], [index for value, index in orderedX],
            [value for value, index in orderedY], [index for value, index in orderedY])


def NearbyTargetIndices(position, margin, targetIndex, alignment = True):
    """Preserve source order, including duplicate targets and equal-distance ties."""
    xValues, xIndices, yValues, yIndices = targetIndex
    positionX, positionY = position
    indices = set(xIndices[bisect_left(xValues, positionX - margin):bisect_right(xValues, positionX + margin)])
    if alignment:
        indices.update(yIndices[bisect_left(yValues, positionY - margin):bisect_right(yValues, positionY + margin)])
    return sorted(indices)


def NearbyPointIndices(position, margin, targetIndex):
    """Ordered square broad phase; the caller retains its native distance test."""
    xValues, xIndices, yValues, yIndices = targetIndex
    positionX, positionY = position
    xStart, xEnd = bisect_left(xValues, positionX - margin), bisect_right(xValues, positionX + margin)
    yStart, yEnd = bisect_left(yValues, positionY - margin), bisect_right(yValues, positionY + margin)
    return sorted(set(xIndices[xStart:xEnd]).intersection(yIndices[yStart:yEnd]))


def SnapPoint(position, targets, scale, vertexRange, alignmentEnabled, gridStep,
              angleAnchor = None, angleDirection = None, targetIndex = None):
    """Return (point, applied, priority, guides); targets are (x, y, direct)."""
    positionX, positionY = position
    nearestVertex, nearestDistance = None, vertexRange
    alignments = {}
    alignmentRange = 20.0
    indices = range(len(targets))
    if targetIndex is not None and angleAnchor is None:
        indices = NearbyTargetIndices(position, max(vertexRange, alignmentRange) / scale,
                                      targetIndex, alignmentEnabled)
    for index in indices:
        vertexX, vertexY, directSnap = targets[index]
        distance = math.hypot(positionX - vertexX, positionY - vertexY) * scale
        onAngleLine = True
        if angleAnchor is not None:
            offsetX, offsetY = vertexX - angleAnchor[0], vertexY - angleAnchor[1]
            onAngleLine = abs(offsetX * angleDirection[1] - offsetY * angleDirection[0]) <= .01
            onAngleLine = onAngleLine and offsetX * angleDirection[0] + offsetY * angleDirection[1] >= 0
        if directSnap and onAngleLine and distance < nearestDistance:
            nearestVertex, nearestDistance = (vertexX, vertexY), distance
        if alignmentEnabled:
            for axis, coordinate, pixelDistance in (
                    (0, vertexX, abs(positionX - vertexX) * scale),
                    (1, vertexY, abs(positionY - vertexY) * scale)):
                intersection = None
                if angleAnchor is not None:
                    component = angleDirection[axis]
                    if abs(component) < 1e-10:
                        continue
                    along = (coordinate - angleAnchor[axis]) / component
                    if along < 0:
                        continue
                    intersection = (angleAnchor[0] + angleDirection[0] * along,
                                    angleAnchor[1] + angleDirection[1] * along)
                    pixelDistance = math.hypot(positionX - intersection[0], positionY - intersection[1]) * scale
                if pixelDistance < alignments.get(axis, (None, alignmentRange, None))[1]:
                    alignments[axis] = (coordinate, pixelDistance, intersection)
    if nearestVertex is not None:
        return nearestVertex, True, 0, []
    snappedPosition, applied, priority = position, False, 3
    if gridStep is not None:
        priority = 2
        if angleAnchor is None:
            applied = True
            snappedPosition = (round(positionX / gridStep) * gridStep, round(positionY / gridStep) * gridStep)
        else:
            candidates = []
            for coordinate, anchorCoordinate, component in (
                    (positionX, angleAnchor[0], angleDirection[0]),
                    (positionY, angleAnchor[1], angleDirection[1])):
                if abs(component) > 1e-10:
                    along = (round(coordinate / gridStep) * gridStep - anchorCoordinate) / component
                    if along >= 0:
                        candidates.append((angleAnchor[0] + angleDirection[0] * along,
                                           angleAnchor[1] + angleDirection[1] * along))
            if candidates:
                applied = True
                snappedPosition = min(candidates, key = lambda candidate:
                    math.hypot(positionX - candidate[0], positionY - candidate[1]))
    guides = []
    if alignments:
        applied, priority = True, 1
        if angleAnchor is not None:
            snappedPosition = min(alignments.values(), key = lambda target: target[1])[2]
            guides = [(axis, target[0]) for axis, target in sorted(alignments.items())
                      if abs(snappedPosition[axis] - target[0]) <= .01]
        else:
            coordinates = list(snappedPosition)
            for axis, (coordinate, distance, intersection) in sorted(alignments.items()):
                coordinates[axis] = coordinate
                guides.append((axis, coordinate))
            snappedPosition = tuple(coordinates)
    return snappedPosition, applied, priority, guides


from PySide6 import QtCore

from planner_app.models import *

class ReferenceSnapping:

    def SnapPosition(self, worldPosition, modifiers, angleAnchor = None, angleDirection = None, snapTargets = None,
                     alignmentTargets = None, preparedTargets = None, preparedTargetIndex = None, numericTargets = None):
        self.alignmentGuides = []
        self.snapApplied = False
        self.snapPriority = 3
        altHeld = bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier)
        if self.snapEnabled == altHeld:
            return worldPosition
        if numericTargets is None:
            if preparedTargets is None:
                targets = self.SnapVertices() if snapTargets is None else snapTargets
                numericTargets = [(vertex.x(), vertex.y(), self.vertexSnapEnabled) for vertex in targets]
                if alignmentTargets is not None:
                    numericTargets.extend((vertex.x(), vertex.y(), False) for vertex in alignmentTargets)
                if self.midpointSnapEnabled:
                    numericTargets.extend((vertex.x(), vertex.y(), True) for vertex in self.SnapMidpoints())
            else:
                # Retain the public prepared Qt-target layout for existing
                # callers; the portable core receives only coordinates/policy.
                numericTargets = [(x, y, directSnap) for x, y, vertex, directSnap in preparedTargets]
        gridStep = self.GridSteps()[1] if self.gridSnapEnabled else None
        point, self.snapApplied, self.snapPriority, self.alignmentGuides = SnapPoint(
            (worldPosition.x(), worldPosition.y()), numericTargets,
            self.basePixelsPerMillimeter * self.zoom, self.vertexSnapRange,
            self.alignmentSnapEnabled, gridStep,
            (angleAnchor.x(), angleAnchor.y()) if angleAnchor is not None else None,
            (angleDirection.x(), angleDirection.y()) if angleAnchor is not None else None,
            preparedTargetIndex)
        return QtCore.QPointF(*point)

    def SnapObjectMovement(self, anchors, delta, modifiers, snapTargets = None, travelDirection = None):
        if self.controlHeld:
            modifiers |= QtCore.Qt.KeyboardModifier.ControlModifier
        direction = travelDirection
        if direction is not None:
            delta = direction * QtCore.QPointF.dotProduct(delta, direction)
            if QtCore.QPointF.dotProduct(delta, direction) < 0:
                direction = -direction
        elif modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            if self.dragStart is not None:
                self.axisConstraintOrigin = self.ViewportToWorld(self.dragStart)
            if self.localTransforms and self.dragStart is not None and self.selectedWall is not None:
                axes = self.TranslationAxes()
                direction = max(axes, key = lambda axis: abs(QtCore.QPointF.dotProduct(delta, axis)))
                if QtCore.QPointF.dotProduct(delta, direction) < 0:
                    direction = -direction
            elif abs(delta.x()) >= abs(delta.y()):
                direction = QtCore.QPointF(-1 if delta.x() < 0 else 1, 0)
            else:
                direction = QtCore.QPointF(0, -1 if delta.y() < 0 else 1)
            delta = direction * QtCore.QPointF.dotProduct(delta, direction)
        numericTargets = []
        if self.snapEnabled != bool(modifiers & QtCore.Qt.KeyboardModifier.AltModifier):
            targets = self.SnapVertices() if snapTargets is None else snapTargets
            numericTargets = [(vertex.x(), vertex.y(), self.vertexSnapEnabled) for vertex in targets]
            if self.midpointSnapEnabled:
                numericTargets.extend((vertex.x(), vertex.y(), True) for vertex in self.SnapMidpoints())
        candidates = []
        preparedTargetIndex = None
        if direction is None and len(numericTargets) > 32:
            preparedTargetIndex = PrepareTargetIndex(numericTargets)
        for anchor in anchors:
            moved = anchor + delta
            snapped = self.SnapPosition(moved, modifiers, anchor if direction is not None else None,
                                        direction, snapTargets = snapTargets, preparedTargets = [],
                                        preparedTargetIndex = preparedTargetIndex, numericTargets = numericTargets)
            if self.snapApplied:
                candidates.append((self.snapPriority, QtCore.QLineF(moved, snapped).length(),
                                   snapped - anchor, list(self.alignmentGuides)))
        self.alignmentGuides = []
        self.snapApplied = bool(candidates)
        self.snapPriority = 3
        if candidates:
            priority, distance, delta, guides = min(candidates, key = lambda candidate: candidate[:2])
            self.snapPriority = priority
            self.alignmentGuides = guides if priority == 1 else []
        if direction is not None:
            # Enforce the movement line after choosing a snap, independently of
            # the snapping calculation. Snapping can only change travel distance.
            delta = direction * max(0.0, QtCore.QPointF.dotProduct(delta, direction))
        return delta
