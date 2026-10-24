"""One color source, preserved alpha and theme propagation through widgets/rendering."""
import ast
import os
import re
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from planner_app.graphics.palette import themeColors
from planner_app.graphics import palette
from planner_app.graphics.theme import ApplyApplicationTheme, BuildStyle, BuildCanvasStyle, BuildWallBrush
from planner_app.graphics.furnishings import FurnishingRenderer, SelectedFurnishingRenderer
from planner_app.graphics.symbols import DrawStairSymbol, DrawOpeningSymbol
from planner_app.graphics.icons import uiIconColors
from planner_app.paths import furnishingsDirectory


def AuditThemeSource(path, source):
    if path == Path("graphics/palette.py"):
        return
    tree = ast.parse(source)
    # Exact statements scoped to a module and function/method. These colors
    # encode material IDs or probe/mask geometry; none supplies display paint.
    internalAssignments = {
        (Path("export_plan.py"), "RenderPlan"): "marker = QtGui.QColor(1, 0, index + 1).name()",
        (Path("graphics/furnishings.py"), "FurnishingSvgRenderer.LetteringBounds"):
            'device = ObjectPaintDevice(self.defaultSize(), "#ffffff")',
        (Path("graphics/furnishings.py"), "FurnishingRenderer"):
            'maskPalette = {"outline": "#000000", "background": "#ffffff", "missing": "#000000"}',
    }
    internalColors = set()
    scopes = [(node.name, node) for node in tree.body if isinstance(node, ast.FunctionDef)]
    scopes.extend((cls.name + "." + method.name, method) for cls in tree.body if isinstance(cls, ast.ClassDef)
                  for method in cls.body if isinstance(method, ast.FunctionDef))
    for name, function in scopes:
        allowed = internalAssignments.get((path, name))
        if allowed is None:
            continue
        expected = ast.dump(ast.parse(allowed).body[0])
        for statement in ast.walk(function):
            if isinstance(statement, ast.Assign) and ast.dump(statement) == expected:
                internalColors.update(ast.walk(statement))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert node in internalColors or not re.search(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(\s*\d", node.value), (path, node.lineno, node.value)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "QColor":
            assert node in internalColors or not any(
                isinstance(argument, ast.Constant) and type(argument.value) is int for argument in node.args), (path, node.lineno)


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    palette.SetThemes("Dark UI", "Dark Canvas")  # Fixed reference colors are independent of application defaults.
    allowed = "def RenderPlan():\n    marker = QtGui.QColor(1, 0, index + 1).name()\n"
    AuditThemeSource(Path("export_plan.py"), allowed)
    maskSource = 'def FurnishingRenderer():\n    maskPalette = {"outline": "#000000", "background": "#ffffff", "missing": "#000000"}\n'
    probeSource = 'class FurnishingSvgRenderer:\n    def LetteringBounds(self):\n        device = ObjectPaintDevice(self.defaultSize(), "#ffffff")\n'
    AuditThemeSource(Path("graphics/furnishings.py"), maskSource + probeSource)
    for path, source in (
            ("ui/export_plan.py", allowed),
            ("export_plan.py", allowed.replace("RenderPlan", "DrawButton")),
            ("export_plan.py", allowed.replace("marker =", "buttonColor =")),
            ("export_plan.py", allowed.replace("1, 0, index + 1", "255, 0, 0")),
            ("export_plan.py", allowed + "    ink = QtGui.QColor(255, 0, 0)\n"),
            ("export_plan.py", allowed + "    ink = '#ff0000'\n"),
            ("graphics/furnishings.py", maskSource.replace("#ffffff", "#ff0000")),
            ("graphics/furnishings.py", probeSource.replace("FurnishingSvgRenderer", "ButtonRenderer")),
            ("graphics/furnishings.py", maskSource + "    ink = '#ff0000'\n"),
            ("ui/widgets.py", "ink = '#ff0000'\n"),
            ("ui/palette.py", "ink = '#ff0000'\n")):
        try:
            AuditThemeSource(Path(path), source)
        except AssertionError:
            pass
        else:
            raise AssertionError((path, "Audit accepted a hardcoded display color", source))
    root = Path(__file__).resolve().parent.parent / "planner-main/planner_app"
    for path in root.rglob("*.py"):
        AuditThemeSource(path.relative_to(root), path.read_text(encoding = "utf-8"))
    assert uiIconColors is themeColors
    for key, rgba in (("selectionBoxFill", (114, 184, 255, 35)), ("overlayFill", (14, 14, 14, 230)),
                      ("errorFill", (35, 20, 20, 240))):
        assert QtGui.QColor(themeColors[key]).getRgb() == rgba
    previous = dict(themeColors)
    main = None
    try:
        main = MainWindow()
        themeColors.update(windowBackground = "#152433", canvas = "#183020", objectOutline = "#ffc040",
                           selectionOutline = "#ee33aa", groupSelectionOutline = "#aabb22",
                           activeBackground = "#253a64", text = "#abcdef", wallFill = "#314253",
                           fieldBackground = "#203040", invalidOutline = "#a030c0")
        style = BuildStyle()
        assert "__COLOR_" not in style and "__ICON_" not in style
        for key in ("windowBackground", "text", "activeBackground", "controlBackground"):
            assert themeColors[key] in style
        assert themeColors["selectionOutline"] in BuildCanvasStyle()
        ApplyApplicationTheme(app)
        main.show()
        app.processEvents()
        v = main.viewport
        v.walls, v.windows, v.furnishings, v.labels = [], [], [], []
        v.objectGroups, v.hiddenObjects = [], []
        v.hiddenObjectIds = set()
        v.SetSelection([])
        v.showGrid = False
        v.ResetView()
        # Sample clear canvas away from the tool tips in its upper-left corner.
        assert v.grab().toImage().pixelColor(v.DrawingRect().center().toPoint()).name() == themeColors["canvas"]
        assert BuildWallBrush().color().name() == themeColors["wallFill"]
        assert v.SelectionColor(object()) == themeColors["selectionOutline"]
        member = object()
        v.objectGroups = [(member, object())]
        assert v.SelectionColor(member) == themeColors["groupSelectionOutline"]
        v.objectGroups = []
        field = QtWidgets.QPlainTextEdit()
        field.setObjectName("labelTextField")
        field.resize(100, 100)
        field.show()
        app.processEvents()
        actualBackground = field.grab().toImage().pixelColor(30, 30).name()
        assert actualBackground == themeColors["fieldBackground"], (actualBackground, themeColors["fieldBackground"])
        field.close()
        square = furnishingsDirectory / "images/square.svg"
        for renderer, target in ((FurnishingRenderer(square), themeColors["objectOutline"]),
                                 (SelectedFurnishingRenderer(square), themeColors["selectionOutline"])):
            image = QtGui.QImage(120, 120, QtGui.QImage.Format.Format_ARGB32)
            image.fill(QtCore.Qt.GlobalColor.transparent)
            painter = QtGui.QPainter(image)
            renderer.render(painter, QtCore.QRectF(10, 10, 100, 100))
            painter.end()
            assert image.pixelColor(60, 60).name() == themeColors["canvas"]
            actual, expected = image.pixelColor(9, 60), QtGui.QColor(target)
            assert all(abs(channel - reference) <= 2 for channel, reference in zip(actual.getRgb()[:3], expected.getRgb()[:3]))
        # Default arguments must read the current theme instead of freezing import-time colors.
        for draw, key in ((DrawStairSymbol, "objectOutline"), (DrawOpeningSymbol, "invalidOutline")):
            image = QtGui.QImage(140, 100, QtGui.QImage.Format.Format_ARGB32)
            image.fill(QtCore.Qt.GlobalColor.transparent)
            painter = QtGui.QPainter(image)
            draw(painter, QtCore.QPointF(20, 50), QtCore.QPointF(120, 50), 30)
            painter.end()
            assert any(image.pixelColor(x, y).name() == themeColors[key] for x in range(140) for y in range(100))
        assert palette.activeUITheme == "Dark UI"
        assert not {"uiTheme", "canvasTheme"} & main.BuildProjectData()["settings"].keys()
    finally:
        themeColors.clear()
        themeColors.update(previous)
        app.setStyleSheet(BuildStyle())
        if main is not None:
            main.close()
    app.processEvents()


if __name__ == "__main__":
    Main()
