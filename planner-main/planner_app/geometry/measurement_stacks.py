"""Compact exterior chains for openings, room divisions and overall spans."""
from PySide6 import QtCore
from planner_app.models import Wall, Window
from .measurement_stack_layout import StackWall, StackSpan, PlanMeasurementStacks
from .dimension_chains import ComputeStackedDimensionLengths, VisibleDimensionPieces


def StackedDimensionLengths(inner, additional, unitsMode, precision):
    """Sum displayed inner segments in integer ticks, without changing geometry."""
    if not additional:
        return []
    innerRecords = [((first.x(), first.y()), (second.x(), second.y()),
                     tuple(id(owner.parentWall if isinstance(owner, Window) else owner) for owner in owners))
                    for first, second, owners in inner]
    additionalRecords = [((first.x(), first.y()), (second.x(), second.y()), tuple(id(owner) for owner in owners), tier)
                         for first, second, owners, tier in additional]
    return ComputeStackedDimensionLengths(innerRecords, additionalRecords, unitsMode, precision)


def VisibleWallDimensionSpans(spans):
    """Trim mixed wall ownership before stacking, without changing room geometry."""
    result = []
    for first, second, owners in spans:
        visible = [owner for owner in owners if not owner.measurementHidden]
        if not visible:
            continue
        if len(visible) == len(owners) or any(type(owner) is not Wall for owner in owners):
            result.append((first, second, visible))
            continue
        records = [(owner, (owner.firstVertex.x(), owner.firstVertex.y()), (owner.secondVertex.x(), owner.secondVertex.y()),
                    not owner.measurementHidden) for owner in owners]
        pieces = VisibleDimensionPieces((first.x(), first.y()), (second.x(), second.y()), records)
        result.extend((QtCore.QPointF(*a), QtCore.QPointF(*b), members) for a, b, members in pieces)
    return result


def BuildMeasurementStacks(totals, openingSpans, walls, rooms, reference = "Wall faces"):
    if not totals:
        return [], []
    wallRecords = [StackWall((wall.firstVertex.x(), wall.firstVertex.y()),
        (wall.secondVertex.x(), wall.secondVertex.y()), wall.width) for wall in walls if type(wall) is Wall]
    spanRecords = []
    for first, second, owners in totals:
        owner = next((owner for owner in owners if type(owner) is Wall), None) if reference == "Centerline" else None
        spanRecords.append(StackSpan((first.x(), first.y()), (second.x(), second.y()), owners,
            max((owner.width for owner in owners), default = 0),
            (owner.firstVertex.x(), owner.firstVertex.y()) if owner is not None else None))
    openingRecords = [((first.x(), first.y()), (second.x(), second.y()), owners) for first, second, owners in openingSpans]
    def RoomAtPoint(point):
        position = QtCore.QPointF(*point)
        return next((index for index, room in enumerate(rooms) if room.contains(position)), None)
    inner, additional = PlanMeasurementStacks(spanRecords, openingRecords, wallRecords, RoomAtPoint if rooms else None, reference,
        distance = lambda x, y: QtCore.QLineF(0.0, 0.0, x, y).length())
    return ([(QtCore.QPointF(*first), QtCore.QPointF(*second), owners) for first, second, owners in inner],
            [(QtCore.QPointF(*first), QtCore.QPointF(*second), owners, tier) for first, second, owners, tier in additional])
