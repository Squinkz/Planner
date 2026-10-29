"""Shared, geometry-cached wall boundaries for room tinting and measurements."""
from PySide6 import QtCore, QtGui
from .models import Wall, Pillar, Column, Elevator, RoomLabel, Stair
from .measurement_units import imperialModes
from .geometry.spatial_index import BoundsIndex
from .geometry.room_regions import ClassifyRoomContours, PlanRoomRegions, FindContainingRegion


def PrepareRoomContours(contours):
    coordinates = [[(point.x(), point.y()) for point in polygon] for polygon in contours]
    bounds = []
    for polygon in contours:
        rect = polygon.boundingRect()
        bounds.append((rect.left(), rect.top(), rect.right(), rect.bottom()))
    contains = lambda index, point: contours[index].containsPoint(QtCore.QPointF(*point), QtCore.Qt.FillRule.OddEvenFill)
    return coordinates, bounds, contains


def ClassifyBoundaryContours(contours):
    return ClassifyRoomContours(*PrepareRoomContours(contours))


def BuildRoomBoundary(occupied):
    """Classify a world-space wall boundary once for all of its consumers."""
    contours = [polygon for polygon in occupied.toSubpathPolygons() if len(polygon) >= 4]
    coordinates, bounds, contains = PrepareRoomContours(contours)
    depths, children = ClassifyRoomContours(coordinates, bounds, contains)
    rooms = QtGui.QPainterPath()
    rooms.setFillRule(QtCore.Qt.FillRule.OddEvenFill)
    count = 0
    exterior = QtGui.QPainterPath()
    exterior.setFillRule(QtCore.Qt.FillRule.WindingFill)
    for position, depth in depths.items():
        if depth:
            rooms.addPolygon(contours[position])
            rooms.closeSubpath()
            count += depth % 2
        else:
            exterior.addPolygon(contours[position])
            exterior.closeSubpath()
    regions = []
    for boundaries, area in PlanRoomRegions(coordinates, depths, children):
        path = QtGui.QPainterPath()
        path.setFillRule(QtCore.Qt.FillRule.OddEvenFill)
        for boundary in boundaries:
            path.addPolygon(contours[boundary])
            path.closeSubpath()
        regions.append(dict(path = path, bounds = path.boundingRect(), area = area))
    return rooms, count, tuple(regions), exterior


def AddStairBoundaries(occupied, stairs, geometry):
    if stairs:
        geometry.ConnectedStairPath(stairs)
        toWorld = QtGui.QTransform().scale(1 / geometry.basePixelsPerMillimeter, -1 / geometry.basePixelsPerMillimeter)
        occupied = occupied.united(toWorld.map(geometry.stairGeometryPath))
    return occupied


def DetectRooms(walls, geometry):
    occupied = geometry.ConnectedWallPath([obj for obj in walls if type(obj) in (Wall, Pillar, Column)])
    origin = geometry.WorldToViewport(QtCore.QPointF())
    scale = geometry.basePixelsPerMillimeter * geometry.zoom
    transform = QtGui.QTransform(1 / scale, 0, 0, -1 / scale, -origin.x() / scale, origin.y() / scale)
    occupied = AddStairBoundaries(transform.map(occupied), [obj for obj in walls if isinstance(obj, Stair)], geometry)
    rooms, count, regions, exterior = BuildRoomBoundary(occupied)
    geometry.roomRegions = tuple(regions)
    return rooms, count


class RoomDetection(QtCore.QObject):
    def __init__(self, viewport):
        super().__init__(viewport)
        self.viewport = viewport
        self.path = QtGui.QPainterPath()
        self.exteriorPath = QtGui.QPainterPath()
        self.count = self.revision = self.rebuildCount = 0
        self.requested = self.signature = None
        self.regions = ()
        self.regionIndex = BoundsIndex(1)
        self.labelKey = None
        self.labelRevision = 0

    def PreviewWalls(self):
        v = self.viewport
        previews = list(v.pendingShapeWalls or ([v.pendingWall] if v.pendingWall is not None else []))
        if isinstance(v.arrowPreview, Pillar) and not isinstance(v.arrowPreview, Elevator):
            previews.append(v.arrowPreview)
        if isinstance(v.windowDropPreview, Stair):
            previews.append(v.windowDropPreview)
        return [obj for obj in previews if type(obj) in (Wall, Pillar, Column, Stair)]

    def Check(self):
        v = self.viewport
        changes = v.renderChanges
        previews = tuple((id(obj), obj.firstVertex.x(), obj.firstVertex.y(), obj.secondVertex.x(), obj.secondVertex.y(),
                          obj.width, obj.firstMiter, obj.secondMiter) for obj in self.PreviewWalls())
        key = changes.wallGeometry, changes.stairGeometry, changes.topology, changes.visibility, tuple(v.visibility.items()), previews
        if key != self.requested:
            self.Refresh()
            self.requested = key
        self.UpdateLabels()
        return self.revision, self.labelRevision

    def Refresh(self, force = False):
        v = self.viewport
        if getattr(v, "exportRender", False) and not force:
            return
        walls = [obj for obj in list(v.walls) + self.PreviewWalls()
                 if type(obj) in (Wall, Pillar, Column) and v.IsObjectVisible(obj)]
        v.ConnectedWallPath(walls)
        self.UpdateBoundary()

    def UpdateBoundary(self):
        """Consume the viewport's already-prepared wall geometry in world units."""
        v = self.viewport
        stairs = [obj for obj in list(v.walls) + self.PreviewWalls() if isinstance(obj, Stair) and v.IsObjectVisible(obj)]
        signature = (v.wallGeometryKey, tuple((id(obj), obj.firstVertex.x(), obj.firstVertex.y(),
                     obj.secondVertex.x(), obj.secondVertex.y(), obj.width, obj.firstMiter, obj.secondMiter) for obj in stairs))
        if signature == self.signature:
            self.UpdateLabels()
            return
        self.signature = signature
        self.rebuildCount += 1
        toWorld = QtGui.QTransform().scale(1 / v.basePixelsPerMillimeter, -1 / v.basePixelsPerMillimeter)
        occupied = AddStairBoundaries(toWorld.map(v.wallGeometryPath), stairs, v)
        path, count, self.regions, self.exteriorPath = BuildRoomBoundary(occupied)
        sizes = sorted(max(region["bounds"].width(), region["bounds"].height()) for region in self.regions)
        self.regionIndex = BoundsIndex(sizes[len(sizes) // 2] if sizes else 1)
        for region in self.regions:
            rect = region["bounds"]
            self.regionIndex.Insert((rect.left(), rect.top(), rect.right(), rect.bottom()), region)
        self.count = count
        if path != self.path and not (path.isEmpty() and self.path.isEmpty()):
            self.path = path
            self.revision += 1
            v.update()
        changed = self.UpdateLabels(force = True)
        if changed:
            v.update()
            if any(isinstance(obj, RoomLabel) for obj, index in v.SelectionEntries()):
                v.selectionChanged.emit()

    def FindRoom(self, point):
        return FindContainingRegion((point.x(), point.y()), self.regionIndex,
                                    lambda region: region["path"].contains(point))

    def UpdateLabel(self, label):
        region = self.FindRoom((label.firstVertex + label.secondVertex) / 2)
        area = region["area"] if region is not None else None
        v = self.viewport
        mode = label.unitsOverride or ("Feet and Inches" if v.unitsMode in imperialModes else "Meters")
        changed = (label.areaSquareMillimeters, label.areaUnitsMode) != (area, mode)
        label.areaSquareMillimeters, label.areaUnitsMode = area, mode
        return changed

    def UpdateLabels(self, force = False):
        v = self.viewport
        changes = v.renderChanges
        key = changes.roomLabelGeometry, changes.appearance, changes.topology, self.revision, v.unitsMode
        if not force and key == self.labelKey:
            return False
        self.labelKey = key
        changed = False
        for label in v.labels:
            if isinstance(label, RoomLabel):
                changed = self.UpdateLabel(label) or changed
        if changed:
            self.labelRevision += 1
        return changed
