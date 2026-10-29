"""Qt model materialization for portable detached construction plans."""
from PySide6 import QtCore
from .models import (Wall, Pillar, Column, Elevator, Stair, Counter, Railing, Arrow, MeasurementGuide,
    BoundaryLine, DashedLine, SolidLine, AngleGuide, Furnishing, NorthArrow, Label, RoomLabel)
from .object_schema import openingClasses

linearClasses = {cls.__name__: cls for cls in (Wall, Pillar, Column, Elevator, Stair, Counter, Railing, Arrow,
    MeasurementGuide, BoundaryLine, DashedLine, SolidLine, AngleGuide)}


def ConstructDetachedObject(plan, definitions):
    first, second = QtCore.QPointF(*plan.first), QtCore.QPointF(*plan.second)
    if plan.category == "walls":
        obj = linearClasses[plan.kind](first, second, plan.width, plan.firstMiter, plan.secondMiter, plan.material)
    elif plan.kind in ("Label", "RoomLabel"):
        obj = (RoomLabel if plan.kind == "RoomLabel" else Label)(text = plan.fields["text"], intensity = plan.fields["intensity"])
    elif plan.kind == "NorthArrow":
        obj = NorthArrow()
    else:
        obj = Furnishing(definitions.get(plan.fields["definitionKey"], definitions["null"]))
    # Planned fields are plain validated scalars, with no property setters.
    # The object is detached and has no render observers yet. Native coordinate
    # fields still go through model setters so they acquire their owning points.
    obj.__dict__.update(plan.fields)
    if plan.points:
        for name, value in plan.points.items():
            setattr(obj, name, QtCore.QPointF(*value))
    if plan.category != "walls":
        obj.firstVertex, obj.secondVertex, obj.width = first, second, plan.width
    return obj


def ConstructProjectOpening(plan, parent):
    obj = openingClasses[plan.kind](parent, plan.firstFraction, plan.secondFraction)
    # Preserve model property behavior and the ordering of recovery fields.
    for name, value in plan.fields.items():
        setattr(obj, name, value)
    return obj
