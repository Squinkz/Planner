"""Expand a compound using its authored layout and current canvas transform."""
import math
from PySide6 import QtCore, QtGui
from .models import Furnishing
from .furnishing_limits import FurnishingExpansionSizes
from .geometry.compound_furnishings import (ComponentFrame, CompoundTransform, PlanCompoundFootprints, PlanFurnishingParts)


def NativeCompoundAffine(operation, *values):
    """Retain native affine rounding where Qt uses fuzzy matrix fast paths."""
    if operation == "root":
        center, angle, scaleX, scaleY, authored = values
        transform = QtGui.QTransform().translate(*center).rotate(angle).scale(scaleX, scaleY).translate(-authored[0], -authored[1])
    elif operation == "compose":
        transform = QtGui.QTransform(*values[0]) * QtGui.QTransform(*values[1])
    elif operation == "nested":
        frame, scaleX, scaleY, center = values
        transform = QtGui.QTransform(*frame).scale(scaleX, scaleY).translate(-center[0], -center[1])
    elif operation == "rectangle":
        frame, width, length = values
        polygon = QtGui.QTransform(*frame).map(QtGui.QPolygonF([QtCore.QPointF(x, y)
            for x, y in ((-width, -length), (width, -length), (width, length), (-width, length))]))
        bounds = polygon.boundingRect()
        return (bounds.x(), bounds.y(), bounds.width(), bounds.height()), tuple((point.x(), point.y()) for point in polygon)
    else:
        raise ValueError("Unknown affine operation")
    return transform.m11(), transform.m12(), transform.m21(), transform.m22(), transform.dx(), transform.dy()


def ComponentTransform(component, transform, allowFixed = True):
    if not transform.isAffine():
        local = QtGui.QTransform().translate(component["x"], component["y"]).rotate(component["angle"])
        actual = local * transform
        if not allowFixed or not component.get("fixedSize", False):
            return actual
        xLength = math.hypot(transform.m11(), transform.m12())
        largestScale = (math.hypot(transform.m11() + transform.m22(), transform.m12() - transform.m21())
                        + math.hypot(transform.m11() - transform.m22(), transform.m12() + transform.m21())) / 2
        if xLength <= 0 or largestScale <= 0:
            return actual
        shrink = min(1.0, abs(transform.determinant()) / largestScale)
        cosine, sine = transform.m11() / xLength, transform.m12() / xLength
        facing = -1 if transform.determinant() < 0 else 1
        uniform = QtGui.QTransform(cosine * shrink, sine * shrink, -sine * shrink * facing, cosine * shrink * facing, 0, 0)
        desired = local * uniform
        offset = actual.map(QtCore.QPointF()) - desired.map(QtCore.QPointF())
        return QtGui.QTransform(desired.m11(), desired.m12(), desired.m21(), desired.m22(),
                                desired.dx() + offset.x(), desired.dy() + offset.y())
    frame = transform.m11(), transform.m12(), transform.m21(), transform.m22(), transform.dx(), transform.dy()
    return QtGui.QTransform(*ComponentFrame(component, frame, allowFixed, NativeCompoundAffine))


def FurnishingCollisionFootprints(parent):
    """Adapt portable child footprints while preserving the existing cache."""
    definition = parent.definition
    FurnishingExpansionSizes([definition])
    key = (id(definition), parent.firstVertex.x(), parent.firstVertex.y(), parent.secondVertex.x(),
           parent.secondVertex.y(), parent.width, parent.flipHorizontal, parent.flipVertical)
    cached = getattr(parent, "compoundCollisionCache", None)
    if cached is not None and cached[0] == key:
        return cached[1]
    center = (parent.firstVertex + parent.secondVertex) / 2
    frame = CompoundTransform((center.x(), center.y()), parent.angle, parent.width, parent.length,
        definition, parent.flipHorizontal, parent.flipVertical, NativeCompoundAffine)
    result = tuple((QtCore.QRectF(*bounds), corners, axes) for bounds, corners, axes in
        PlanCompoundFootprints(definition, frame, validated = True, backend = NativeCompoundAffine))
    parent.compoundCollisionCache = (key, result)
    return result


def FurnishingParts(parent):
    center = (parent.firstVertex + parent.secondVertex) / 2
    frame = CompoundTransform((center.x(), center.y()), parent.angle, parent.width, parent.length,
        parent.definition, parent.flipHorizontal, parent.flipVertical, NativeCompoundAffine)
    scaleX = parent.width / parent.definition["width"] * (-1 if parent.flipHorizontal else 1)
    scaleY = parent.length / parent.definition["length"] * (-1 if parent.flipVertical else 1)
    parts = []
    for definition, key, center, width, halfLength, angle, flipHorizontal, flipVertical in PlanFurnishingParts(
            parent.definition, frame, scaleX * scaleY < 0, NativeCompoundAffine):
        position = QtCore.QPointF(*center)
        part = Furnishing(definition, position)
        part.measurementHidden = parent.measurementHidden
        part.behindCounters = parent.behindCounters
        part.flipHorizontal, part.flipVertical = flipHorizontal, flipVertical
        part.definitionKey = key
        part.width = width
        part.firstVertex = position - QtCore.QPointF(0, halfLength)
        part.secondVertex = position + QtCore.QPointF(0, halfLength)
        part.angle = angle
        parts.append(part)
    return parts
