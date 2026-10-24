"""Expand a compound using its authored layout and current canvas transform."""
import math
from PySide6 import QtCore, QtGui
from .models import Furnishing
from .geometry.footprints import PolygonAxes


def ComponentTransform(component, transform, allowFixed = True):
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


def FurnishingCollisionFootprints(parent):
    """Keep exact affine child footprints, including nested and mirrored layouts."""
    definition = parent.definition
    from .furnishing_limits import FurnishingExpansionSizes
    FurnishingExpansionSizes([definition])
    key = (id(definition), parent.firstVertex.x(), parent.firstVertex.y(), parent.secondVertex.x(),
           parent.secondVertex.y(), parent.width, parent.flipHorizontal, parent.flipVertical)
    cached = getattr(parent, "compoundCollisionCache", None)
    if cached is not None and cached[0] == key:
        return cached[1]
    center = (parent.firstVertex + parent.secondVertex) / 2
    transform = QtGui.QTransform().translate(center.x(), center.y()).rotate(parent.angle)
    transform.scale(parent.width / definition["width"] * (-1 if parent.flipHorizontal else 1),
                    parent.length / definition["length"] * (-1 if parent.flipVertical else 1))
    transform.translate(-definition["compoundCenter"][0], -definition["compoundCenter"][1])
    footprints = []
    pending = [(definition, transform, True)]
    while pending:
        current, transform, allowFixed = pending.pop()
        for component in current["components"]:
            child = component["definition"]
            local = ComponentTransform(component, transform, allowFixed)
            if child.get("components"):
                local.scale(component["width"] / child["width"] * (-1 if component.get("flipHorizontal", False) else 1),
                            component["length"] / child["length"] * (-1 if component.get("flipVertical", False) else 1))
                local.translate(-child["compoundCenter"][0], -child["compoundCenter"][1])
                pending.append((child, local, allowFixed and not component.get("fixedSize", False)))
                continue
            width, length = component["width"] / 2, component["length"] / 2
            polygon = local.map(QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in
                ((-width, -length), (width, -length), (width, length), (-width, length))]))
            corners = tuple((point.x(), point.y()) for point in polygon)
            # Uniform winding makes overlapping child polygons a union, even
            # when nested mirroring reverses an individual child's orientation.
            if sum(corners[index][0] * corners[(index + 1) % 4][1] - corners[(index + 1) % 4][0] * corners[index][1]
                   for index in range(4)) < 0:
                corners = tuple(reversed(corners))
            footprints.append((polygon.boundingRect(), corners, tuple(PolygonAxes(corners))))
    result = tuple(footprints)
    parent.compoundCollisionCache = (key, result)
    return result


def FurnishingParts(parent):
    from .furnishing_limits import FurnishingExpansionSizes
    FurnishingExpansionSizes([parent.definition])
    center = (parent.firstVertex + parent.secondVertex) / 2
    authoredX, authoredY = parent.definition["compoundCenter"]
    scaleX = parent.width / parent.definition["width"]
    scaleY = parent.length / parent.definition["length"]
    if parent.flipHorizontal:
        scaleX = -scaleX
    if parent.flipVertical:
        scaleY = -scaleY
    transform = QtGui.QTransform().translate(center.x(), center.y()).rotate(parent.angle)
    transform.scale(scaleX, scaleY)
    transform.translate(-authoredX, -authoredY)
    parts = []
    for index, component in sorted(enumerate(parent.definition["components"]), key = lambda entry: (entry[1]["zIndex"], entry[0])):
        local = ComponentTransform(component, transform)
        position = local.map(QtCore.QPointF())
        part = Furnishing(component["definition"], position)
        part.measurementHidden = parent.measurementHidden
        part.behindCounters = parent.behindCounters
        part.flipHorizontal = component.get("flipHorizontal", False) != (scaleX * scaleY < 0)
        part.flipVertical = component.get("flipVertical", False)
        part.definitionKey = component.get("definitionKey", component["definition"]["key"])
        # Rectangular furniture cannot retain affine shear. Preserve center,
        # axis lengths and direction, matching the manual Decompose command.
        part.width = component["width"] * math.hypot(local.m11(), local.m12())
        halfLength = component["length"] * math.hypot(local.m21(), local.m22()) / 2
        part.firstVertex = position - QtCore.QPointF(0, halfLength)
        part.secondVertex = position + QtCore.QPointF(0, halfLength)
        part.angle = math.degrees(math.atan2(local.m22(), local.m21())) - 90
        parts.append(part)
    return parts
