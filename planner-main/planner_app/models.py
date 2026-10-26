"""Scene object data and derived dimensions, including text bounds."""

import math
from dataclasses import dataclass, field
from itertools import count
from PySide6 import QtCore, QtGui
from planner_app.graphics import palette
from planner_app.scene_changes import SceneObject
from planner_app.geometry.editing import AngleEndpoints
from planner_app.geometry.opening_placement import OpeningVertexFraction, FireplaceCenter


objectIdCounter = count(1)


@dataclass
class Wall(SceneObject):
    firstVertex: QtCore.QPointF
    secondVertex: QtCore.QPointF
    width: float = 240.0
    # Historical field names; values are chamfer amounts (0 sharp, 1 full cut).
    firstMiter: float = 0.0
    secondMiter: float = 0.0
    material: str = "Generic"
    objectId: int | None = field(default = None, init = False, compare = False)


@dataclass
class Counter(Wall):
    width: float = 600.0


@dataclass
class Railing(Wall):
    width: float = 80.0
    autosize: bool = True
    manualPostCount: int = 2
    spacingBounds: tuple = (900.0, 1500.0, 1200.0)

    @property
    def postCount(self):
        length = QtCore.QLineF(self.firstVertex, self.secondVertex).length()
        if not self.autosize:
            return max(2, self.manualPostCount)
        minimum, maximum, target = self.spacingBounds
        minimumCount = max(1, math.ceil(length / maximum - 1e-10))
        maximumCount = max(1, math.floor(length / minimum + 1e-10))
        if minimumCount <= maximumCount:
            count = max(minimumCount, min(maximumCount, int(length / target + .5)))
        else:
            count = min({minimumCount, maximumCount}, key = lambda count:
                        (max(minimum - length / count, 0, length / count - maximum), abs(length / count - target)))
        return count + 1

    @property
    def segmentWidth(self):
        return QtCore.QLineF(self.firstVertex, self.secondVertex).length() / (self.postCount - 1)

    def SetAutosize(self, enabled):
        if self.autosize and not enabled:
            self.manualPostCount = self.postCount
        self.autosize = enabled

    def SetPostCount(self, count):
        self.manualPostCount = max(2, int(count))

    def SetSegmentWidth(self, size):
        length = QtCore.QLineF(self.firstVertex, self.secondVertex).length()
        self.manualPostCount = max(1, int(length / max(size, .001) + .5)) + 1


@dataclass
class MeasurementGuide(Wall):
    width: float = 0.0
    textOffset: QtCore.QPointF = field(default_factory = QtCore.QPointF)


class BoundaryLine(MeasurementGuide):
    """A dash-dot annotation whose dimensions appear only while selected."""


lineWeightClasses = {"Walls": ("wallOutline", "walls"), "Objects": ("objectOutline", "architectural"),
                     "Furnishings": ("objectOutline", "furnishings"), "Measurements": ("measurementLine", "dimensions")}


class DashedLine(BoundaryLine):
    weightClass = "Objects"


class SolidLine(DashedLine):
    pass


class AngleGuide(MeasurementGuide):
    """A free angle: two outer points, a translating vertex, and a label offset."""
    def __init__(self, firstVertex, secondVertex, width = 0.0, firstMiter = 0.0, secondMiter = 0.0,
                 material = "Generic", middleVertex = None):
        super().__init__(firstVertex, secondVertex, width, firstMiter, secondMiter, material)
        self.middleVertex = QtCore.QPointF(middleVertex if middleVertex is not None else
                                          QtCore.QPointF(firstVertex.x(), secondVertex.y()))
        self.textOffset = QtCore.QPointF()

    @property
    def angle(self):
        first, second = self.firstVertex - self.middleVertex, self.secondVertex - self.middleVertex
        if math.hypot(first.x(), first.y()) < 1e-8 or math.hypot(second.x(), second.y()) < 1e-8:
            return None
        return abs(math.degrees(math.atan2(first.x() * second.y() - first.y() * second.x(),
                                          QtCore.QPointF.dotProduct(first, second))))

    def SetAngle(self, degrees, arms = None):
        if not math.isfinite(degrees) or not 0 <= degrees <= 180:
            return False
        first, second = arms if arms is not None else (self.firstVertex - self.middleVertex, self.secondVertex - self.middleVertex)
        firstLength, secondLength = math.hypot(first.x(), first.y()), math.hypot(second.x(), second.y())
        radius = min(firstLength, secondLength)
        if radius < 1e-8:
            return False
        directions = [first / firstLength, second / secondLength]
        # Smaller Y component means a larger unsigned angle from north (+Y).
        # Ties rotate the last arm. Preserve the current side of the fixed arm.
        moving = 0 if directions[0].y() < directions[1].y() - 1e-10 else 1
        fixed = directions[1 - moving]
        cross = fixed.x() * directions[moving].y() - fixed.y() * directions[moving].x()
        orientation = -1 if cross < -1e-10 else 1
        angle = math.atan2(fixed.y(), fixed.x()) + orientation * math.radians(degrees)
        directions[moving] = QtCore.QPointF(math.cos(angle), math.sin(angle))
        self.firstVertex = self.middleVertex + directions[0] * radius
        self.secondVertex = self.middleVertex + directions[1] * radius
        return True


def ObjectControlPoints(obj):
    # Preserve the existing endpoint indices; the angle's middle handle is 2.
    return (obj.firstVertex, obj.secondVertex, obj.middleVertex) if isinstance(obj, AngleGuide) else (obj.firstVertex, obj.secondVertex)


def SetControlPoint(obj, index, point):
    setattr(obj, ("firstVertex", "secondVertex", "middleVertex")[index], QtCore.QPointF(point))


@dataclass
class Arrow(Wall):
    width: float = 10.0
    solidTip: bool = True
    tipSize: float = 60.0
    intensity: float = 1.0
    directionReversed: bool = False


@dataclass(init = False)
class Stair(Wall):
    width: float = 1000.0
    sceneStairs: list = field(default_factory = list, init = False, compare = False, repr = False)
    directionReversed: bool = False
    autosize: bool = True
    manualStepCount: int = 1
    stepSizeBounds: tuple = (250.0, 300.0)

    def __init__(self, firstVertex, secondVertex, width = 1000.0, firstMiter = 0.0, secondMiter = 0.0,
                 material = "Generic", directionReversed = False):
        super().__init__(firstVertex, secondVertex, width, firstMiter, secondMiter, material)
        self.sceneStairs = []
        self.directionReversed = directionReversed
        self.autosize = True
        self.manualStepCount = 1
        self.stepSizeBounds = (250.0, 300.0)

    @property
    def stepCount(self):
        if not self.autosize:
            treadCount, stepSize, landingCount = self.StepLayout()
            return treadCount + landingCount
        treadCount, stepSize, landingCount = self.StepLayout()
        return treadCount + landingCount

    @property
    def stepSize(self):
        treadCount, stepSize, landingCount = self.StepLayout()
        return stepSize

    def LandingTrims(self, stairs):
        trims = []
        for vertex, endpoint in ((self.firstVertex, self.secondVertex), (self.secondVertex, self.firstVertex)):
            direction = endpoint - vertex
            length = math.hypot(direction.x(), direction.y())
            trim = 0.0
            if length > 1e-10:
                direction /= length
                for other in stairs:
                    if other is self:
                        continue
                    otherDirection = None
                    if QtCore.QLineF(vertex, other.firstVertex).length() <= .01:
                        otherDirection = other.secondVertex - other.firstVertex
                    elif QtCore.QLineF(vertex, other.secondVertex).length() <= .01:
                        otherDirection = other.firstVertex - other.secondVertex
                    if otherDirection is None:
                        continue
                    otherLength = math.hypot(otherDirection.x(), otherDirection.y())
                    if otherLength < 1e-10:
                        continue
                    otherDirection /= otherLength
                    cross = abs(direction.x() * otherDirection.y() - direction.y() * otherDirection.x())
                    if cross < 1e-6:
                        continue
                    dot = QtCore.QPointF.dotProduct(direction, otherDirection)
                    innerDistance = (other.width / 2 + self.width / 2 * dot) / cross
                    intersectionDistance = math.hypot(self.width / 2, innerDistance)
                    if dot < 0 and abs(self.width - other.width) > 1e-6 and intersectionDistance > 2 * max(self.width, other.width):
                        continue
                    trim = max(trim, min(length, max(0.0, innerDistance)))
            trims.append(trim)
        return tuple(trims)

    def StepLayout(self, trims = None):
        firstTrim, secondTrim = self.LandingTrims(self.sceneStairs) if trims is None else trims
        runLength = max(0.0, QtCore.QLineF(self.firstVertex, self.secondVertex).length() - firstTrim - secondTrim)
        landingCount = int(firstTrim > 1e-8) + int(secondTrim > 1e-8)
        if runLength < 1e-8:
            return 0, 0.0, landingCount
        if not self.autosize:
            treadCount = max(1, self.manualStepCount - landingCount)
            return treadCount, runLength / treadCount, landingCount
        minimumSize, maximumSize = self.stepSizeBounds
        targetSize = (minimumSize + maximumSize) / 2
        minimumCount = max(1, math.ceil(runLength / maximumSize - 1e-10))
        maximumCount = math.floor(runLength / minimumSize + 1e-10)
        if minimumCount <= maximumCount:
            treadCount = max(minimumCount, min(maximumCount, round(runLength / targetSize)))
        else:
            # Short runs sometimes cannot fit a whole number of treads within the range.
            # Choose the count with the smallest deviation from that range.
            candidates = {minimumCount, max(1, maximumCount)}
            treadCount = min(candidates, key = lambda count: (max(minimumSize - runLength / count, 0, runLength / count - maximumSize),
                                                             abs(runLength / count - targetSize)))
        return treadCount, runLength / treadCount, landingCount

    def SetAutosize(self, enabled):
        if self.autosize and not enabled:
            self.manualStepCount = self.stepCount
        self.autosize = enabled

    def SetStepCount(self, count):
        firstTrim, secondTrim = self.LandingTrims(self.sceneStairs)
        landingCount = int(firstTrim > 1e-8) + int(secondTrim > 1e-8)
        self.manualStepCount = max(landingCount + 1, int(count))

    def SetStepSize(self, size):
        firstTrim, secondTrim = self.LandingTrims(self.sceneStairs)
        runLength = max(0.0, QtCore.QLineF(self.firstVertex, self.secondVertex).length() - firstTrim - secondTrim)
        landingCount = int(firstTrim > 1e-8) + int(secondTrim > 1e-8)
        self.manualStepCount = max(1, int(runLength / max(size, .001) + .5)) + landingCount


@dataclass(init = False)
class Window(SceneObject):
    parentWall: Wall
    centerFraction: float
    length: float
    objectId: int | None = field(default = None, init = False, compare = False)

    def __init__(self, parentWall, firstFraction, secondFraction, swingsOutwards = False):
        if type(self) is Window:
            self.swingsOutwards = swingsOutwards
        self.parentWall = parentWall
        self.objectId = None
        self.measurementFlipped = False
        self.windowWell = False
        self.wellDepth = 600.0
        self.wellDashed = False
        self.SetFractions(firstFraction, secondFraction)

    def SetFractions(self, firstFraction, secondFraction):
        self.centerFraction = (firstFraction + secondFraction) / 2
        self.length = (secondFraction - firstFraction) * QtCore.QLineF(self.parentWall.firstVertex, self.parentWall.secondVertex).length()

    @property
    def firstFraction(self):
        parentLength = QtCore.QLineF(self.parentWall.firstVertex, self.parentWall.secondVertex).length()
        if "opening_bounds" in getattr(self, "geometryIssues", ()):
            return self.centerFraction - self.length / (2 * max(parentLength, 1e-8))
        halfSpan = min(0.5, self.length / (2 * parentLength)) if parentLength > 1e-10 else 0.5
        center = max(halfSpan, min(1 - halfSpan, self.centerFraction))
        return center - halfSpan

    @firstFraction.setter
    def firstFraction(self, value):
        self.SetFractions(value, self.secondFraction)

    @property
    def secondFraction(self):
        parentLength = QtCore.QLineF(self.parentWall.firstVertex, self.parentWall.secondVertex).length()
        if "opening_bounds" in getattr(self, "geometryIssues", ()):
            return self.centerFraction + self.length / (2 * max(parentLength, 1e-8))
        halfSpan = min(0.5, self.length / (2 * parentLength)) if parentLength > 1e-10 else 0.5
        center = max(halfSpan, min(1 - halfSpan, self.centerFraction))
        return center + halfSpan

    @secondFraction.setter
    def secondFraction(self, value):
        self.SetFractions(self.firstFraction, value)

    @property
    def firstVertex(self):
        return self.parentWall.firstVertex + (self.parentWall.secondVertex - self.parentWall.firstVertex) * self.firstFraction

    @property
    def secondVertex(self):
        return self.parentWall.firstVertex + (self.parentWall.secondVertex - self.parentWall.firstVertex) * self.secondFraction

    @property
    def width(self):
        return self.parentWall.width

    def SetVertex(self, vertexIndex, position):
        first, second = self.parentWall.firstVertex, self.parentWall.secondVertex
        fraction = OpeningVertexFraction((first.x(), first.y()), (second.x(), second.y()), (position.x(), position.y()),
                                         vertexIndex, self.secondFraction if vertexIndex == 0 else self.firstFraction)
        if fraction is not None:
            if vertexIndex == 0:
                self.firstFraction = fraction
            else:
                self.secondFraction = fraction



class OpenDoorway(Window):
    """A wall opening with exposed jambs and no leaf or facing direction."""


class Fireplace(Window):
    """Wall-bound opening: length stores its span; depth is its front-to-back size."""
    def __init__(self, parentWall, firstFraction, secondFraction, swingsOutwards = False):
        super().__init__(parentWall, firstFraction, secondFraction)
        self.swingsOutwards = swingsOutwards
        self.depth = max(self.width * 5 / 12, parentWall.width)
        self.depthOffset = 0.0
        self.material = parentWall.material

    @property
    def width(self):
        return self.length

    @width.setter
    def width(self, value):
        self.length = max(1.0, value)

    @property
    def depth(self):
        if "fireplace_bounds" in getattr(self, "geometryIssues", ()):
            return self.manualDepth
        return max(self.parentWall.width, self.manualDepth)

    @depth.setter
    def depth(self, value):
        self.manualDepth = max(self.parentWall.width, value)

    @property
    def depthOffset(self):
        if "fireplace_bounds" in getattr(self, "geometryIssues", ()):
            return self.manualDepthOffset
        limit = max(0.0, (self.depth - self.parentWall.width) / 2)
        return max(-limit, min(limit, self.manualDepthOffset))

    @depthOffset.setter
    def depthOffset(self, value):
        limit = max(0.0, (self.depth - self.parentWall.width) / 2)
        self.manualDepthOffset = max(-limit, min(limit, value))

    def Axes(self):
        direction = self.parentWall.secondVertex - self.parentWall.firstVertex
        direction /= max(QtCore.QLineF(self.parentWall.firstVertex, self.parentWall.secondVertex).length(), 1e-8)
        return direction, QtCore.QPointF(-direction.y(), direction.x())

    def HandleBox(self):
        direction, normal = self.Axes()
        center = (self.firstVertex + self.secondVertex) / 2 + normal * self.depthOffset
        # Preserve historical stored width/length aliases for the opening span;
        # the UI box uses length along the wall and width through it.
        box = Furnishing({"key": "fireplace", "name": "Fireplace", "width": self.depth, "length": self.length}, center)
        box.firstVertex = center - direction * (self.length / 2)
        box.secondVertex = center + direction * (self.length / 2)
        return box

    def SetCenter(self, position):
        direction, normal = self.Axes()
        wallLength = QtCore.QLineF(self.parentWall.firstVertex, self.parentWall.secondVertex).length()
        first = self.parentWall.firstVertex
        self.centerFraction, offset = FireplaceCenter((first.x(), first.y()), (direction.x(), direction.y()),
            (normal.x(), normal.y()), wallLength, self.width, (position.x(), position.y()))
        self.depthOffset = offset



class CasementWindow(Window):
    def __init__(self, parentWall, firstFraction, secondFraction, swingsOutwards = False, hingeAtSecond = False):
        super().__init__(parentWall, firstFraction, secondFraction)
        self.swingsOutwards = swingsOutwards
        self.hingeAtSecond = hingeAtSecond


class AwningWindow(Window):
    def __init__(self, parentWall, firstFraction, secondFraction, swingsOutwards = False):
        super().__init__(parentWall, firstFraction, secondFraction)
        self.swingsOutwards = swingsOutwards


class DoubleCasementWindow(Window):
    """Two opposed casement leaves in one continuous frame."""
    def __init__(self, parentWall, firstFraction, secondFraction, swingsOutwards = False):
        super().__init__(parentWall, firstFraction, secondFraction)
        self.swingsOutwards = swingsOutwards


class SilledWindow(Window):
    def __init__(self, parentWall, firstFraction, secondFraction, swingsOutwards = False, sillDepth = 40.0):
        super().__init__(parentWall, firstFraction, secondFraction)
        self.swingsOutwards = swingsOutwards
        self.sillDepth = sillDepth


@dataclass(init = False)
class Door(Window):
    hingeAtSecond: bool = False
    swingsOutwards: bool = False

    def __init__(self, parentWall, firstFraction, secondFraction, hingeAtSecond = False, swingsOutwards = False):
        super().__init__(parentWall, firstFraction, secondFraction)
        self.hingeAtSecond = hingeAtSecond
        self.swingsOutwards = swingsOutwards


class SwingingDoor(Window):
    """A double-acting door with one hinge side and no facing direction."""
    def __init__(self, parentWall, firstFraction, secondFraction, hingeAtSecond = False):
        super().__init__(parentWall, firstFraction, secondFraction)
        self.hingeAtSecond = hingeAtSecond


class DoubleDoor(Window):
    """Two opposed standard door leaves sharing one swing direction."""
    def __init__(self, parentWall, firstFraction, secondFraction, swingsOutwards = False):
        super().__init__(parentWall, firstFraction, secondFraction)
        self.swingsOutwards = swingsOutwards


@dataclass(init = False)
class SlidingDoor(Window):
    # Shared orientation flag: reverse the slide direction rather than a hinge.
    hingeAtSecond: bool = False
    panelsFlipped: bool = False

    def __init__(self, parentWall, firstFraction, secondFraction, hingeAtSecond = False, panelsFlipped = False):
        super().__init__(parentWall, firstFraction, secondFraction)
        self.hingeAtSecond = hingeAtSecond
        self.panelsFlipped = panelsFlipped


@dataclass(init = False)
class PocketDoor(Window):
    hingeAtSecond: bool = False

    def __init__(self, parentWall, firstFraction, secondFraction, hingeAtSecond = False):
        super().__init__(parentWall, firstFraction, secondFraction)
        self.hingeAtSecond = hingeAtSecond


@dataclass(init = False)
class BarnDoor(PocketDoor):
    swingsOutwards: bool = False

    def __init__(self, parentWall, firstFraction, secondFraction, hingeAtSecond = False, swingsOutwards = False):
        super().__init__(parentWall, firstFraction, secondFraction, hingeAtSecond)
        self.swingsOutwards = swingsOutwards


@dataclass(init = False)
class BifoldDoor(Window):
    swingsOutwards: bool = False

    def __init__(self, parentWall, firstFraction, secondFraction, swingsOutwards = False):
        super().__init__(parentWall, firstFraction, secondFraction)
        self.swingsOutwards = swingsOutwards


class Furnishing(SceneObject):
    behindCounters = False
    flipHorizontal = False
    flipVertical = False

    def __init__(self, definition, center = QtCore.QPointF()):
        self.definition = definition
        self.width = definition["width"]
        length = definition["length"]
        self.firstVertex = center - QtCore.QPointF(0, length / 2)
        self.secondVertex = center + QtCore.QPointF(0, length / 2)
        self.objectId = None

    @property
    def length(self):
        return QtCore.QLineF(self.firstVertex, self.secondVertex).length()

    @property
    def angle(self):
        direction = self.secondVertex - self.firstVertex
        return (math.degrees(math.atan2(direction.y(), direction.x())) - 90) % 360

    @angle.setter
    def angle(self, value):
        first, second = AngleEndpoints((self.firstVertex.x(), self.firstVertex.y()),
                                       (self.secondVertex.x(), self.secondVertex.y()), self.length, value)
        self.firstVertex, self.secondVertex = QtCore.QPointF(*first), QtCore.QPointF(*second)

    def Clone(self):
        copy = Furnishing(self.definition)
        copy.behindCounters = self.behindCounters
        copy.flipHorizontal = self.flipHorizontal
        copy.flipVertical = self.flipVertical
        copy.measurementHidden = self.measurementHidden
        copy.definitionKey = getattr(self, "definitionKey", self.definition["key"])
        copy.firstVertex = QtCore.QPointF(self.firstVertex)
        copy.secondVertex = QtCore.QPointF(self.secondVertex)
        copy.width = self.width
        return copy


@dataclass
class Pillar(Wall):
    width: float = 300.0
    # Rectangular sizing and rotation use the same axis convention as furnishings.
    length = Furnishing.length
    angle = Furnishing.angle


class Column(Pillar):
    """An elliptical pillar with the same sizing, materials and handles."""


@dataclass
class Elevator(Pillar):
    """Architectural SVG object with rectangular furnishing-style handles."""
    width: float = 1200.0


class NorthArrow(Furnishing):
    """A non-colliding annotation with the same rectangular handles as furnishings."""
    def __init__(self, center = QtCore.QPointF()):
        super().__init__({"key": "north-arrow", "name": "North Marker", "width": 600.0, "length": 1000.0}, center)
        self.intensity = 1.0

    def Clone(self):
        copy = NorthArrow((self.firstVertex + self.secondVertex) / 2)
        copy.intensity = self.intensity
        copy.measurementHidden = self.measurementHidden
        copy.firstVertex, copy.secondVertex = QtCore.QPointF(self.firstVertex), QtCore.QPointF(self.secondVertex)
        copy.width = self.width
        return copy


class Label(Furnishing):
    def __init__(self, origin = QtCore.QPointF(), text = "Label", intensity = 1.0):
        self.text = text
        self.intensity = intensity
        self.objectId = None
        self.UpdateBounds(origin)

    @property
    def origin(self):
        direction = (self.secondVertex - self.firstVertex) / self.length
        return self.firstVertex + QtCore.QPointF(-direction.y(), direction.x()) * (self.width / 2)

    @property
    def length(self):
        return QtCore.QLineF(self.firstVertex, self.secondVertex).length()

    def Font(self):
        font = QtGui.QFont(palette.labelFont)
        font.setPointSize(18)
        # Canvas label layout retains its own metrics, independently of UI hinting.
        font.setHintingPreference(QtGui.QFont.HintingPreference.PreferDefaultHinting)
        return font

    def TextLayout(self):
        """Retain only the current text/font layout; geometry and color are independent."""
        font = self.Font()
        resolved = QtGui.QFontInfo(font)
        key = (self.text, font.toString(), resolved.family(), resolved.styleName(), resolved.pixelSize())
        if key == getattr(self, "textLayoutKey", None):
            return self.textLayout
        metrics = QtGui.QFontMetricsF(font)
        lines = self.text.split("\n")
        advances = [metrics.horizontalAdvance(line) for line in lines]
        textWidth = max(1.0, max(advances))
        textHeight = metrics.lineSpacing() * len(lines)
        textBounds = QtCore.QRectF()
        positions = []
        for index, (line, advance) in enumerate(zip(lines, advances)):
            position = QtCore.QPointF(-advance / 2, -textHeight / 2 + metrics.ascent() + index * metrics.lineSpacing())
            positions.append((line, position))
            textBounds = textBounds.united(metrics.boundingRect(line).translated(position))
        self.textLayout = (font, textWidth, textHeight, textBounds, tuple(positions))
        self.textLayoutKey = key
        return self.textLayout

    def UpdateBounds(self, origin = None):
        if origin is None:
            origin = self.origin
        font, textWidth, textHeight, textBounds, lines = self.TextLayout()
        # New labels default to 32 points at the fixed 1:20 reference.
        scale = 32 * (25.4 * 20 / 72) / QtGui.QFontInfo(font).pixelSize()
        self.width = textWidth * scale
        height = textHeight * scale
        self.firstVertex = origin + QtCore.QPointF(self.width / 2, 0)
        self.secondVertex = self.firstVertex + QtCore.QPointF(0, height)

    def SetText(self, text):
        pointSize = self.pointSize
        self.text = text
        self.SetPointSize(pointSize)

    @property
    def pointSize(self):
        font, textWidth, textHeight, textBounds, lines = self.TextLayout()
        # Label points always use a fixed 1:20 reference, independent of output scale.
        return self.length / textHeight * QtGui.QFontInfo(font).pixelSize() * 72 / (25.4 * 20)

    def SetPointSize(self, value):
        font, textWidth, textHeight, textBounds, lines = self.TextLayout()
        origin = self.origin
        north = (self.secondVertex - self.firstVertex) / self.length
        east = QtCore.QPointF(north.y(), -north.x())
        scale = value * (25.4 * 20 / 72) / QtGui.QFontInfo(font).pixelSize()
        self.width = textWidth * scale
        height = textHeight * scale
        self.firstVertex = origin + east * (self.width / 2)
        self.secondVertex = self.firstVertex + north * height

    def Clone(self):
        copy = type(self)(QtCore.QPointF(self.origin), self.text, self.intensity)
        copy.measurementHidden = self.measurementHidden
        copy.firstVertex, copy.secondVertex = QtCore.QPointF(self.firstVertex), QtCore.QPointF(self.secondVertex)
        copy.width = self.width
        if isinstance(self, RoomLabel):
            copy.unitsOverride = self.unitsOverride
        return copy


class RoomLabel(Label):
    """A centered room name with a derived, nonserialized area line."""
    areaSquareMillimeters = None
    areaUnitsMode = "Adaptive Metric"
    unitsOverride = None

    def __init__(self, origin = QtCore.QPointF(), text = "ROOM", intensity = 1.0):
        super().__init__(QtCore.QPointF(), " ".join(text.splitlines()), intensity)
        self.SetPointSize(32)
        offset = origin - (self.firstVertex + self.secondVertex) / 2
        self.firstVertex += offset
        self.secondVertex += offset

    def SetText(self, text):
        super().SetText(" ".join(text.splitlines()))

    def TextLayout(self):
        from .units import FormatArea
        font = self.Font()
        area = FormatArea(self.areaSquareMillimeters, self.areaUnitsMode)
        resolved = QtGui.QFontInfo(font)
        key = self.text, area, font.toString(), resolved.family(), resolved.styleName(), resolved.pixelSize()
        if key == getattr(self, "textLayoutKey", None):
            return self.textLayout
        areaFont = QtGui.QFont(font)
        areaFont.setPointSizeF(font.pointSizeF() * .55)
        nameLines = self.text.split("\n")
        entries = [(line, font) for line in nameLines] + [(area, areaFont)]
        metrics = [QtGui.QFontMetricsF(lineFont) for line, lineFont in entries]
        height = sum(metric.lineSpacing() for metric in metrics)
        # Reserve a stable area box. Derived area/unit changes must not resize
        # stored geometry or silently invalidate the shared undo journal.
        width = max(1.0, QtGui.QFontMetricsF(areaFont).horizontalAdvance("000,000,000 mm²"),
                    *(QtGui.QFontMetricsF(font).horizontalAdvance(line) for line in nameLines))
        positions = []
        bounds = QtCore.QRectF()
        top = -height / 2
        for (line, lineFont), metric in zip(entries, metrics):
            position = QtCore.QPointF(-metric.horizontalAdvance(line) / 2, top + metric.ascent())
            positions.append((line, position, lineFont))
            bounds = bounds.united(metric.boundingRect(line).translated(position))
            top += metric.lineSpacing()
        self.textLayout = font, width, height, bounds, tuple(positions)
        self.textLayoutKey = key
        return self.textLayout

    def SetPointSize(self, value):
        center = (self.firstVertex + self.secondVertex) / 2
        super().SetPointSize(value)
        offset = center - (self.firstVertex + self.secondVertex) / 2
        self.firstVertex += offset
        self.secondVertex += offset


