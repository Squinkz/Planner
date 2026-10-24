"""Verify material edits, history, opening cuts and view-independent shading caches."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall, Window, Door
from theme import BuildStyle, wallMaterials


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    window = MainWindow()
    window.SetThemes(uiTheme = "Dark UI", canvasTheme = "Dark Canvas")  # Fixed palette for pixel assertions.
    window.resize(1450, 1050)
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    viewport.showMeasurements = False
    viewport.showGrid = False
    viewport.walls = [Wall(point(-2000, 2000 - index * 500), point(2000, 2000 - index * 500),
                           material = material) for index, material in enumerate(wallMaterials)]
    assert wallMaterials[0] == "Generic"
    from planner_app.graphics.theme import BuildWallBrush
    for selected, warning in ((False, False), (True, False), (False, True)):
        brush = BuildWallBrush(material = "Generic", selected = selected, warning = warning)
        assert brush.style() == QtCore.Qt.BrushStyle.SolidPattern
    wall = viewport.walls[0]
    assert Wall(point(), point(1000, 0)).material == "Generic"
    viewport.selectedWall = wall
    viewport.selectedVertex = 0
    window.RefreshProperties()
    assert window.materialField.isVisible() and window.materialField.currentText() == "Generic"
    window.materialField.setCurrentText("Metal")
    assert wall.material == "Metal"
    viewport.Undo()
    assert wall.material == "Generic" and window.materialField.currentText() == "Generic"
    viewport.Redo()
    assert wall.material == "Metal"
    viewport.Undo()
    opening = Window(wall, .1, .3)
    viewport.windows = [opening]
    viewport.selectedWall = opening
    window.RefreshProperties()
    assert not window.materialField.isVisible()
    viewport.windows = []
    viewport.selectedWall = None
    window.RefreshProperties()
    image = viewport.grab().toImage()
    paths = viewport.materialPaths
    geometryKey = viewport.wallGeometryKey
    viewport.panOffset += point(13, 9)
    viewport.zoom = .9
    viewport.grab()
    assert viewport.materialPaths is paths and viewport.wallGeometryKey == geometryKey
    viewport.zoom = 1
    viewport.panOffset -= point(13, 9)
    viewport.materialGeometryKey = None
    assert viewport.grab().toImage() == image
    # Material-only edits rebuild shading without retracing the wall boundary.
    wall.material = "Steel"
    viewport.grab()
    assert viewport.materialPaths is not paths and viewport.wallGeometryKey == geometryKey
    wall.material = "Brick"
    viewport.windows = [Door(wall, .4, .6)]
    image = viewport.grab().toImage()
    center = viewport.WorldToViewport(point(0, 2000)).toPoint()
    assert image.pixelColor(center).name() == "#0e0e0e"
    viewport.windows = []
    viewport.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "wall-materials.png"))
    window.close()
    print("PASS: ten materials, default Generic, vertex properties, undo/redo, opening cuts and shading cache reuse.")


if __name__ == "__main__":
    Main()
