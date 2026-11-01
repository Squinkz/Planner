"""Desktop scene snapshots and model replay, independent of viewport widgets.

Named records retain the historical tuple layout for sparse edits and v1 files.
Gesture cancellation, notifications, selection policy and cache ownership remain
with the viewport; these functions only capture or restore supplied models.
"""
import math
from PySide6 import QtCore
from .history_records import WallSnapshot, OpeningSnapshot, SceneSnapshot
from .record_schema import openingFieldsByType
from .models import (SilledWindow, SlidingDoor, Fireplace, Railing, Stair,
                     DashedLine, AngleGuide, MeasurementGuide, Arrow, NorthArrow)


def SnapshotPointMatches(point, x, y):
    pointX, pointY = point.x(), point.y()
    if pointX != x or pointY != y:
        return False
    # Signed zero can affect angle calculations; retain snapshot signs as well.
    return ((x != 0 or math.copysign(1, pointX) == math.copysign(1, x))
            and (y != 0 or math.copysign(1, pointY) == math.copysign(1, y)))



def CaptureOpeningSnapshots(windows):
    snapshots = []
    for window in windows:
        fields = openingFieldsByType[type(window).__name__]
        facing = (window.swingsOutwards if "swingsOutwards" in fields else
                  window.panelsFlipped if "panelsFlipped" in fields else None)
        depth = (window.sillDepth if "sillDepth" in fields else
                 (window.depth, window.depthOffset, window.material, window.manualDepth, window.manualDepthOffset)
                 if isinstance(window, Fireplace) else None)
        snapshots.append(OpeningSnapshot(window, window.parentWall, window.centerFraction, window.length,
            window.hingeAtSecond if "hingeAtSecond" in fields else None, facing, depth,
            window.measurementFlipped, window.measurementHidden, (window.windowWell, window.wellDepth, window.wellDashed)))
    return tuple(snapshots)


def CaptureSceneSnapshot(wallObjects, windows, furnishings, labels, groups = (), hidden = (), selection = (),
                         selectedObject = None, selectedVertex = None, rotationObject = None, pivot = None):
    walls = []
    for wall in wallObjects:
        sizing = ((wall.autosize, wall.manualPostCount) if isinstance(wall, Railing) else
                  (wall.autosize, wall.manualStepCount) if isinstance(wall, Stair) else None)
        if isinstance(wall, DashedLine):
            details = (wall.weightClass, wall.textOffset.x(), wall.textOffset.y())
        elif isinstance(wall, AngleGuide):
            details = (wall.middleVertex.x(), wall.middleVertex.y(), wall.textOffset.x(), wall.textOffset.y())
        elif isinstance(wall, MeasurementGuide):
            details = ((wall.depth, wall.textOffset.x(), wall.textOffset.y()) if type(wall) is MeasurementGuide else
                       (wall.textOffset.x(), wall.textOffset.y()))
        elif isinstance(wall, Arrow):
            details = (wall.solidTip, wall.tipSize, wall.intensity, wall.directionReversed)
        else:
            details = wall.directionReversed if isinstance(wall, Stair) else None
        walls.append(WallSnapshot(wall, wall.firstVertex.x(), wall.firstVertex.y(), wall.secondVertex.x(), wall.secondVertex.y(),
                      wall.width, wall.firstMiter, wall.secondMiter, wall.material, sizing, details, wall.measurementHidden))
    walls = tuple(walls)
    windows = CaptureOpeningSnapshots(windows)
    furnishings = tuple((obj, QtCore.QPointF(obj.firstVertex), QtCore.QPointF(obj.secondVertex), obj.width,
                        obj.behindCounters, obj.flipHorizontal, obj.flipVertical,
                        *((obj.intensity,) if isinstance(obj, NorthArrow) else ()), obj.measurementHidden) for obj in furnishings)
    entries = tuple(selection)
    state = SceneSnapshot(walls, selectedObject, selectedVertex, windows, entries, furnishings,
            tuple(groups), tuple(hidden),
            tuple((obj, QtCore.QPointF(obj.firstVertex), QtCore.QPointF(obj.secondVertex), obj.width, obj.text, obj.intensity)
                  + ((obj.unitsOverride,) if hasattr(obj, "unitsOverride") else ())
                  + (obj.measurementHidden,) for obj in labels))
    if not any(obj is rotationObject for obj, index in entries):
        rotationObject = None
    pivot = pivot if entries else None
    if rotationObject is not None or pivot is not None:
        state += ((rotationObject, (pivot.x(), pivot.y()) if pivot is not None else None),)
    return state


def RestoreWallSnapshots(walls):
    for wall, firstX, firstY, secondX, secondY, width, firstMiter, secondMiter, material, sizing, details, measurementHidden in walls:
        wall.measurementHidden = measurementHidden
        wall.firstVertex = QtCore.QPointF(firstX, firstY)
        wall.secondVertex = QtCore.QPointF(secondX, secondY)
        wall.width = width
        wall.firstMiter = firstMiter
        wall.secondMiter = secondMiter
        wall.material = material
        if isinstance(wall, MeasurementGuide):
            wall.textOffset = QtCore.QPointF(*details[-2:])
            if type(wall) is MeasurementGuide:
                wall.depth = details[0] if len(details) > 2 else 0
        if isinstance(wall, DashedLine):
            wall.weightClass = details[0]
        if isinstance(wall, AngleGuide):
            wall.middleVertex = QtCore.QPointF(*details[:2])
        if isinstance(wall, Arrow):
            wall.solidTip, wall.tipSize, wall.intensity = details[:3]
            wall.directionReversed = details[3] if len(details) > 3 else False
        if isinstance(wall, Railing):
            wall.autosize, wall.manualPostCount = sizing
        if isinstance(wall, Stair):
            wall.directionReversed = details
            if isinstance(sizing, tuple):
                wall.autosize, wall.manualStepCount = sizing


def RestoreOpeningSnapshots(windows):
    for openingState in windows:
        fields = openingFieldsByType[type(openingState[0]).__name__]
        window, parentWall, centerFraction, length, hingeAtSecond, swingsOutwards, sillDepth = openingState[:7]
        # Fireplace setters also normalize stored depth/offset against the
        # restored parent. Always run those, even when visible values match.
        if (not isinstance(window, Fireplace) and window.parentWall is parentWall
                and centerFraction != 0 and window.centerFraction == centerFraction and window.length == length
                and window.measurementFlipped == (openingState[7] if len(openingState) > 7 else False)
                and window.measurementHidden == (openingState[8] if len(openingState) > 8 else False)
                and (window.windowWell, window.wellDepth, window.wellDashed) == (openingState[9] if len(openingState) > 9 else (False, 600.0, False))
                and (not isinstance(window, SilledWindow) or window.sillDepth == sillDepth)
                and ("hingeAtSecond" not in fields
                     or window.hingeAtSecond == hingeAtSecond)
                and ("swingsOutwards" not in fields
                     or window.swingsOutwards == swingsOutwards)
                and (not isinstance(window, SlidingDoor) or window.panelsFlipped == swingsOutwards)):
            continue
        window.measurementFlipped = openingState[7] if len(openingState) > 7 else False
        window.measurementHidden = openingState[8] if len(openingState) > 8 else False
        window.windowWell, window.wellDepth, window.wellDashed = openingState[9] if len(openingState) > 9 else (False, 600.0, False)
        window.parentWall = parentWall
        window.centerFraction = centerFraction
        window.length = length
        if isinstance(window, SilledWindow):
            window.sillDepth = sillDepth
        if isinstance(window, Fireplace):
            window.depth, window.depthOffset, window.material = sillDepth[:3]
            if len(sillDepth) > 3:
                window.manualDepth, window.manualDepthOffset = sillDepth[3:]
        if "hingeAtSecond" in fields:
            window.hingeAtSecond = hingeAtSecond
        if "swingsOutwards" in fields:
            window.swingsOutwards = swingsOutwards
        elif isinstance(window, SlidingDoor):
            window.panelsFlipped = swingsOutwards


def RestoreLabelSnapshots(states):
    for state in states:
        obj, first, second, width, text, intensity = state[:6]
        measurementHidden = state[-1]
        if hasattr(obj, "unitsOverride"):
            obj.unitsOverride = state[6] if len(state) > 7 else None
        if (not SnapshotPointMatches(obj.firstVertex, first.x(), first.y())
                or not SnapshotPointMatches(obj.secondVertex, second.x(), second.y())
                or (obj.width, obj.text, obj.intensity, obj.measurementHidden) != (width, text, intensity, measurementHidden)):
            obj.measurementHidden = measurementHidden
            obj.firstVertex, obj.secondVertex = QtCore.QPointF(first), QtCore.QPointF(second)
            obj.width, obj.text = width, text
            obj.intensity = intensity


def RestoreFurnishingSnapshots(states):
    for state in states:
        obj, first, second, width, behindCounters, flipHorizontal, flipVertical = state[:7]
        measurementHidden = state[-1]
        if isinstance(obj, NorthArrow):
            obj.intensity = state[7] if len(state) > 8 else 1.0
        if (not SnapshotPointMatches(obj.firstVertex, first.x(), first.y())
                or not SnapshotPointMatches(obj.secondVertex, second.x(), second.y())
                or (obj.width, obj.behindCounters, obj.flipHorizontal, obj.flipVertical, obj.measurementHidden)
                != (width, behindCounters, flipHorizontal, flipVertical, measurementHidden)):
            obj.behindCounters = behindCounters
            obj.flipHorizontal = flipHorizontal
            obj.flipVertical = flipVertical
            obj.measurementHidden = measurementHidden
            obj.firstVertex = QtCore.QPointF(first)
            obj.secondVertex = QtCore.QPointF(second)
            obj.width = width

