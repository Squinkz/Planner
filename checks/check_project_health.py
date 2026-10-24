"""Refactor boundaries and regressions discovered during the health audit."""
import json
import os
import sys
import tempfile
import warnings
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtTest, QtWidgets
from planner import MainWindow, Stair, Wall, Window, Door
from furnishings import Furnishing, LoadFurnishings, SelectedFurnishingRenderer
from planner_app.models import Wall as ModelWall
from planner_app.paths import appDirectory, assetsDirectory, furnishingsDirectory
from planner_app.ui.main_window import MainWindow as AppMainWindow
from theme import BuildStyle
from planner_app.graphics import palette


def Main():
    app = QtWidgets.QApplication([])
    palette.SetThemes("Dark UI", "Dark Canvas")
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    assert Wall is ModelWall and MainWindow is AppMainWindow
    assert assetsDirectory == appDirectory / "assets"
    assert furnishingsDirectory == appDirectory / "furnishings"
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        (folder / "definitions").mkdir()
        (folder / "images").mkdir()
        defaults = {"name": "Null", "image": "null", "width": 1000, "length": 1000,
                    "icon": None, "category": "Miscellaneous", "inherits": None}
        (folder / "definitions/null.json").write_text(json.dumps(defaults))
        (folder / "definitions/bad_encoding.json").write_bytes(b'\xff\xfe')
        (folder / "definitions/overflow.json").write_text(json.dumps({"width": 10 ** 1000}))
        (folder / "definitions/cycle.json").write_text(json.dumps({"inherits": "cycle"}))
        with warnings.catch_warnings(record = True) as caught:
            definitions = LoadFurnishings(folder)
        assert len(caught) == 3 and [item["key"] for item in definitions] == ["null"]
        svgPath = folder / "images/class-styles.svg"
        svgPath.write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
          <style>.background {fill: #ffffff;} .line {stroke: #000000; fill: none; stroke-width: 2;}</style>
          <rect class="background" width="100" height="100"/>
          <path class="line" d="M10 50.5 H90"/>
        </svg>''')
        selected = SelectedFurnishingRenderer(svgPath)
        image = QtGui.QImage(100, 100, QtGui.QImage.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(image)
        selected.render(painter, QtCore.QRectF(0, 0, 100, 100))
        painter.end()
        assert image.pixelColor(50, 50).name() == "#72b8ff"
        assert image.pixelColor(50, 25).name() == "#0e0e0e"
        originalDirectory = Path.cwd()
        try:
            os.chdir(folder)
            assert {item["key"] for item in LoadFurnishings()} >= {"null", "desk"}
            assert QtSvg.QSvgRenderer(str(assetsDirectory / "icons_ui/objects/door.svg")).isValid()
        finally:
            os.chdir(originalDirectory)
    window = MainWindow()
    window.SetThemes(uiTheme = "Dark UI", canvasTheme = "Dark Canvas")  # Fixed palette for pixel assertions.
    window.show()
    app.processEvents()
    viewport = window.viewport
    point = QtCore.QPointF
    desk = Furnishing(viewport.furnishingDefinitions["desk"])
    viewport.furnishings = [desk]
    wall = Wall(point(-2000, 0), point(2000, 0), 240)
    viewport.walls = [wall]
    center = viewport.WorldToViewport(point())
    assert viewport.HitTest(center)[0] is wall
    stair = Stair(point(-2000, 0), point(2000, 0))
    viewport.walls = [stair]
    assert viewport.HitTest(center)[0] is stair
    viewport.walls = [wall, stair]
    viewport.windows = [Window(wall, .1, .2), Door(wall, .6, .8)]
    viewport.SetSelection([(wall, 0)])
    viewport.setFocus()
    QtTest.QTest.keyClick(viewport, QtCore.Qt.Key.Key_A, QtCore.Qt.KeyboardModifier.ControlModifier)
    assert len(viewport.SelectionEntries()) == 5
    assert all(index is None for obj, index in viewport.SelectionEntries())
    viewport.walls = []
    viewport.windows = []
    viewport.furnishings = []
    assert not viewport.SelectionEntries()
    window.close()
    print("PASS: compatibility imports, resource paths, malformed catalogs, CSS selection colors, stacking hit tests and select-all.")


if __name__ == "__main__":
    Main()
