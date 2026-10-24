"""Columns share pillar editing and transport, with elliptical physical geometry."""
import os
import math
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Column, Wall
from planner_app.project_codec import DecodeProject
from planner_app.models import Furnishing
from planner_app.graphics.svg_preview import SvgPreviewRenderer
from planner_app.graphics.column import ColumnPath, ColumnPolygon, ColumnContains


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v, point = main.viewport, QtCore.QPointF
    v.unitsMode = "Adaptive Metric"
    v.snapEnabled = False
    v.newWallMaterial = "Brick"
    assert not main.columnButton.icon().isNull()
    mime = QtCore.QMimeData()
    mime.setData("application/x-planner-column", b"column")
    position = v.WorldToViewport(point())
    enter = QtGui.QDragEnterEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    v.dragEnterEvent(enter)
    move = QtGui.QDragMoveEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    v.dragMoveEvent(move)
    assert type(v.arrowPreview) is Column and v.arrowPreview.material == "Brick"
    v.grab()
    drop = QtGui.QDropEvent(position, QtCore.Qt.DropAction.CopyAction, mime,
        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    v.dropEvent(drop)
    column = v.walls[0]
    assert drop.isAccepted() and type(column) is Column and column.width == column.length == 300
    assert "Column (#" in main.selectionLabel.text() and not main.materialField.isHidden()
    assert len(v.FurnishingHandles(column)) == 13
    main.sizeLinkButton.setChecked(False)
    main.EditProperty("width", 60)
    main.EditProperty("length", .9)
    main.EditProperty("angle", 37)
    main.EditMaterial("Concrete")
    assert column.width == 600 and abs(column.length - 900) < .001 and abs(column.angle - 37) < .001
    column.angle = 0
    column.firstVertex, column.secondVertex = point(0, -300), point(0, 300)
    nativePath = ColumnPath(column)
    assert nativePath.elementCount() == 13
    assert any(nativePath.elementAt(index).type == QtGui.QPainterPath.ElementType.CurveToElement
               for index in range(nativePath.elementCount()))
    # A point just inside the true circle but beyond an approximation chord
    # must still be clickable. The polygon is reserved for collision geometry.
    polygon = ColumnPolygon(column)
    angle = math.pi / len(polygon)
    nearEdge = point(299.99 * math.cos(angle), 299.99 * math.sin(angle))
    assert ColumnContains(column, nearEdge)
    assert not polygon.containsPoint(nearEdge, QtCore.Qt.FillRule.OddEvenFill)
    pathCache, polygonCache = column.ellipsePathCache, column.ellipsePolygonCache
    column.firstVertex += point(12, 8)
    column.secondVertex += point(12, 8)
    assert ColumnPath(column) == nativePath.translated(12, 8)
    assert ColumnPolygon(column) == polygon.translated(12, 8)
    assert column.ellipsePathCache is pathCache and column.ellipsePolygonCache is polygonCache
    column.firstVertex -= point(12, 8)
    column.secondVertex -= point(12, 8)
    v.SetSelection([])
    assert v.HitTest(v.WorldToViewport(point())) == (column, None)
    assert v.HitTest(v.WorldToViewport(point(280, 280))) == (None, None)
    assert v.HitTest(v.WorldToViewport(nearEdge)) == (column, None)
    other = Furnishing({"key": "fixture", "width": 20, "length": 20}, point(280, 280))
    assert not v.ObjectsOverlap(column, other)
    other.firstVertex, other.secondVertex = point(-10, -10), point(-10, 10)
    assert v.ObjectsOverlap(column, other)
    wall = Wall(point(-1800, 0), point(1800, 0), 240, material = "Brick")
    for objects in ([column, wall], [wall, column]):
        v.walls = objects
        path = v.ConnectedWallPath(objects)
        assert path.contains(v.WorldToViewport(point(0, 250)))
        assert not path.contains(v.WorldToViewport(point(280, 280)))
        v.grab()
        assert v.wallMaterialPaths[id(column)].contains(point())
        assert any(v.wallMaterialPaths[id(column)].elementAt(index).type == QtGui.QPainterPath.ElementType.CurveToElement
                   for index in range(v.wallMaterialPaths[id(column)].elementCount()))
        assert not v.wallMaterialPaths[id(wall)].contains(point())
    assert v.grab().save(str(Path(__file__).resolve().parent.parent / "diagnostics/column-wall-native-preview.png"))
    neighbor = Column(point(200, -300), point(200, 300), 600)
    v.walls = [column, neighbor]
    v.grab()
    overlapPoint = point(100 * v.basePixelsPerMillimeter, 0)
    assert v.wallGeometryPath.contains(overlapPoint)
    assert len(v.columnOutlinePaths) == 3
    # An overlapping ellipse must not cancel the winding fill of its neighbor.
    assert all(path.contains(overlapPoint) for path in v.columnMaterialPaths.values())
    column.angle = 37
    assert ColumnContains(column, point())
    assert not ColumnContains(column, point(500, 500))
    ColumnPath(column)
    assert column.ellipsePathCache is not pathCache
    v.walls = [column]
    v.undoHistory = []
    v.redoHistory = []
    v.SetSelection([(column, None)])
    assert v.CopySelection() and v.PasteSelection()
    assert type(v.selectedWall) is Column
    v.Undo()
    assert len(v.walls) == 1
    v.Redo()
    assert len(v.walls) == 2 and all(type(obj) is Column for obj in v.walls)
    data = main.BuildProjectData()
    decoded = DecodeProject(data, v.furnishingDefinitions)
    assert all(type(obj) is Column for obj in decoded[0])
    main.ApplyProject(decoded, None)
    v.Undo()
    assert len(v.walls) == 1 and type(v.walls[0]) is Column
    main.sidebarTabs.setCurrentWidget(main.exportPanel)
    image = main.exportPanel.Render("png")
    assert not image.isNull() and SvgPreviewRenderer(main.exportPanel.Render("svg")).isValid()
    image.save(str(Path(__file__).resolve().parent.parent / "diagnostics" / "column-export-preview.png"))
    main.close()
    app.clipboard().clear()
    print("PASS: column drop, ellipse hit/collision, material joins, properties, clipboard, history and PNG/SVG")


if __name__ == "__main__":
    Main()
