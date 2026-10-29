"""Desktop adapters for portable connected-stair annotation plans."""
import math
from PySide6 import QtCore
from planner_app.graphics.path_operations import Paths
from .stair_annotation_plans import (StairAnnotationRecord, PrepareStairInset, PlanStairInsetLines,
    PlanStairArrowRuns, StairEndpointNeighbors as NumericStairNeighbors)


def NativeStairDistance(x, y):
    # Retain native tolerance/tie rounding at the desktop geometry boundary.
    return QtCore.QLineF(0.0, 0.0, x, y).length()


def StairContactDistance(x, y):
    # Only the <= .01 contact decision consumes this metric. Away from the
    # threshold the numeric norm avoids constructing a native line per contact.
    length = math.hypot(x, y)
    return NativeStairDistance(x, y) if abs(length - .01) <= 1e-12 else length


def ReadStairRecords(stairs):
    return [StairAnnotationRecord(id(stair), (stair.firstVertex.x(), stair.firstVertex.y()),
        (stair.secondVertex.x(), stair.secondVertex.y()), stair.width, getattr(stair, "directionReversed", False)) for stair in stairs]


def StairEndpointNeighbors(stairs):
    models = {id(stair): stair for stair in stairs}
    return NumericStairNeighbors(ReadStairRecords(stairs), StairContactDistance, models)


def StairInsetLines(components, polygons, scale):
    lines, footprints = [], {}
    for owner, polygon in polygons:
        footprints.setdefault(id(owner), []).append(polygon)
    stairs = [stair for key, members, boundary in components for stair in members]
    models = {id(stair): stair for stair in stairs}
    records = ReadStairRecords(stairs)
    byKey = {record.key: record for record in records}
    neighbors = NumericStairNeighbors(records, StairContactDistance)
    for key, members, boundary in components:
        if len(members) == 1:
            continue
        owned = [(id(stair), polygon) for stair in members for polygon in footprints.get(id(stair), ())]
        inset, terminals = PrepareStairInset([byKey[id(stair)] for stair in members], neighbors, scale)
        stroke = Paths.PrepareStroke(width = 2 * inset, cap = 'square', join = 'miter')
        inside = Paths.Difference(boundary, stroke(boundary))
        def OwnerAtPoint(point):
            midpoint = QtCore.QPointF(*point)
            return next((identity for identity, footprint in owned
                         if footprint.containsPoint(midpoint, QtCore.Qt.FillRule.WindingFill)), id(members[0]))
        contours = ([(point.x(), point.y()) for point in polygon] for polygon in Paths.Contours(inside))
        lines.extend((models[key], QtCore.QLineF(*first, *second)) for key, first, second in
            PlanStairInsetLines(contours, terminals, inset, scale, OwnerAtPoint, NativeStairDistance))
    return lines


def StairArrowRuns(stairs, neighbors, trims):
    models = {id(stair): stair for stair in stairs}
    external = {id(peer): peer for peers in neighbors.values() for peer in peers if id(peer) not in models}
    numericNeighbors = {key: [id(peer) for peer in peers] for key, peers in neighbors.items()}
    return [(models[key], QtCore.QPointF(*start), QtCore.QPointF(*tip), showTip)
        for key, start, tip, showTip in PlanStairArrowRuns(ReadStairRecords(stairs), numericNeighbors, trims,
            NativeStairDistance, ReadStairRecords(external.values()))]
