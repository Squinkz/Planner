"""Frozen native column assembly and occluder preparation before this pass."""
from planner_app.viewport.geometry import *
from planner_app.viewport.widget import DrawingViewport


class ReferenceViewport(DrawingViewport):
    def ConnectedColumnWallPath(self, walls, traceContours):
        geometryKey = (self.basePixelsPerMillimeter, traceContours, tuple((id(wall), wall.firstVertex.x(),
            wall.firstVertex.y(), wall.secondVertex.x(), wall.secondVertex.y(), wall.width,
            wall.firstMiter, wall.secondMiter) for wall in walls))
        origin = self.WorldToViewport(QtCore.QPointF())
        viewTransform = QtGui.QTransform().translate(origin.x(), origin.y()).scale(self.zoom, self.zoom)
        if geometryKey == self.wallGeometryKey:
            return viewTransform.map(self.wallGeometryPath)
        if "columnWallWorkspace" not in self.__dict__:
            self.columnWallWorkspace = FootprintGeometry(self.basePixelsPerMillimeter, self)
        workspace = self.columnWallWorkspace
        workspace.basePixelsPerMillimeter = self.basePixelsPerMillimeter
        regularWalls = [wall for wall in walls if not isinstance(wall, Column)]
        workspace.ConnectedWallPath(regularWalls, traceContours)
        regularPath = workspace.wallGeometryPath
        transform = QtGui.QTransform().scale(self.basePixelsPerMillimeter, -self.basePixelsPerMillimeter)
        columns = [(wall, transform.map(ColumnPath(wall)).toReversed()) for wall in walls if isinstance(wall, Column)]
        columnFill = QtGui.QPainterPath()
        columnFill.setFillRule(QtCore.Qt.FillRule.WindingFill)
        for wall, path in columns:
            columnFill.addPath(path)
        # Curves stay native for paint and ownership. Qt's boolean union is
        # used only for the exterior footprint consumed by measurements.
        combined = QtGui.QPainterPath(regularPath)
        self.columnOutlinePaths = [(regularPath, columnFill)]
        for index, (wall, path) in enumerate(columns):
            if combined.boundingRect().intersects(path.boundingRect()):
                combined = Paths.Union(combined, path)
            else:
                combined.addPath(path)
            occluders = QtGui.QPainterPath(regularPath)
            for otherIndex, (other, otherPath) in enumerate(columns):
                if index != otherIndex and path.boundingRect().intersects(otherPath.boundingRect()):
                    occluders.addPath(otherPath)
            self.columnOutlinePaths.append((path, occluders))
        self.columnMaterialPaths = {id(wall): path for wall, path in columns}
        self.wallGeometryPath = combined
        self.wallFillPolygons = list(workspace.wallFillPolygons)
        # Collision ownership and measurement cutters still consume polygons;
        # generate them only here, using the cached world-tolerance footprint.
        self.wallFillPolygons.extend((wall, transform.map(ColumnPolygon(wall))) for wall, path in columns)
        self.wallGeometryComponents = []
        self.wallGeometryKey = geometryKey
        return viewTransform.map(combined)
