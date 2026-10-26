"""Shared, geometry-cached wall boundaries for room tinting and measurements."""
import math
from PySide6 import QtCore, QtGui
from .models import Wall, Pillar, Column, Elevator, RoomLabel
from .viewport.spatial_index import BoundsIndex


def ClassifyBoundaryContours(contours):
    """Return nesting depths and immediate children without flattening geometry."""
    bounds = [polygon.boundingRect() for polygon in contours]
    sizes = sorted(max(rect.width(), rect.height()) for rect in bounds if not rect.isEmpty())
    index = BoundsIndex(sizes[len(sizes) // 2] if sizes else 1)
    for position, rect in enumerate(bounds):
        index.Insert(rect, position)
    depths, children = {}, {}
    for position, polygon in enumerate(contours):
        point = polygon[0]
        # A traced corner can lie a few floating-point steps outside its parent
        # contour. Sample just inside an edge instead, close enough to preserve
        # nesting even when the contour contains another wall island.
        vertices = list(polygon)
        for first, second in zip(vertices, vertices[1:]):
            delta = second - first
            length = math.hypot(delta.x(), delta.y())
            if not length:
                continue
            midpoint = (first + second) / 2
            epsilon = min(length / 1000, max(1e-6, 16 * math.ulp(max(abs(midpoint.x()), abs(midpoint.y()), 1))))
            offset = QtCore.QPointF(-delta.y(), delta.x()) * (epsilon / length)
            candidates = [candidate for candidate in (midpoint + offset, midpoint - offset)
                          if polygon.containsPoint(candidate, QtCore.Qt.FillRule.OddEvenFill)]
            if candidates:
                point = candidates[0]
                break
        candidates = index.Query(QtCore.QRectF(point.x() - .0001, point.y() - .0001, .0002, .0002))
        containing = [other for other in candidates if other != position
                      and contours[other].containsPoint(point, QtCore.Qt.FillRule.OddEvenFill)]
        depth = len(containing)
        depths[position] = depth
        if containing:
            parent = min(containing, key = lambda other: bounds[other].width() * bounds[other].height())
            children.setdefault(parent, []).append(position)
    return depths, children


def BuildRoomBoundary(occupied):
    """Classify a world-space wall boundary once for all of its consumers."""
    contours = [polygon for polygon in occupied.toSubpathPolygons() if len(polygon) >= 4]
    depths, children = ClassifyBoundaryContours(contours)
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
    for position, depth in depths.items():
        if depth % 2 == 0:
            continue
        path = QtGui.QPainterPath()
        path.setFillRule(QtCore.Qt.FillRule.OddEvenFill)
        area = 0.0
        for boundary in [position] + children.get(position, []):
            polygon = contours[boundary]
            path.addPolygon(polygon)
            path.closeSubpath()
            # Subtract an origin before the shoelace sum to retain precision
            # for small rooms at large positive or negative world coordinates.
            origin = polygon[0]
            points = [point - origin for point in polygon]
            value = abs(sum(first.x() * second.y() - second.x() * first.y()
                            for first, second in zip(points, points[1:] + points[:1]))) / 2
            area += value if boundary == position else -value
        regions.append(dict(path = path, bounds = path.boundingRect(), area = max(0.0, area)))
    return rooms, count, tuple(regions), exterior


def DetectRooms(walls, geometry):
    occupied = geometry.ConnectedWallPath(walls)
    origin = geometry.WorldToViewport(QtCore.QPointF())
    scale = geometry.basePixelsPerMillimeter * geometry.zoom
    transform = QtGui.QTransform(1 / scale, 0, 0, -1 / scale, -origin.x() / scale, origin.y() / scale)
    rooms, count, regions, exterior = BuildRoomBoundary(transform.map(occupied))
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
        return [obj for obj in previews if type(obj) in (Wall, Pillar, Column)]

    def Check(self):
        v = self.viewport
        changes = v.renderChanges
        previews = tuple((id(obj), obj.firstVertex.x(), obj.firstVertex.y(), obj.secondVertex.x(), obj.secondVertex.y(),
                          obj.width, obj.firstMiter, obj.secondMiter) for obj in self.PreviewWalls())
        key = changes.wallGeometry, changes.topology, changes.visibility, tuple(v.visibility.items()), previews
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
        signature = v.wallGeometryKey
        if signature == self.signature:
            self.UpdateLabels()
            return
        self.signature = signature
        self.rebuildCount += 1
        toWorld = QtGui.QTransform().scale(1 / v.basePixelsPerMillimeter, -1 / v.basePixelsPerMillimeter)
        path, count, self.regions, self.exteriorPath = BuildRoomBoundary(toWorld.map(v.wallGeometryPath))
        sizes = sorted(max(region["bounds"].width(), region["bounds"].height()) for region in self.regions)
        self.regionIndex = BoundsIndex(sizes[len(sizes) // 2] if sizes else 1)
        for region in self.regions:
            self.regionIndex.Insert(region["bounds"], region)
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
        for region in self.regionIndex.Query(QtCore.QRectF(point.x() - .0001, point.y() - .0001, .0002, .0002)):
            if region["path"].contains(point):
                return region
        return None

    def UpdateLabel(self, label):
        region = self.FindRoom((label.firstVertex + label.secondVertex) / 2)
        area = region["area"] if region is not None else None
        v = self.viewport
        mode = label.unitsOverride or v.unitsMode
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
