"""Verify the frozen app without opening windows or using real user state."""
import json
import os
from pathlib import Path
import sys
import traceback


def RunSmokeTest(reportPath):
    reportPath = Path(reportPath).resolve()
    report = {"ok": False}
    try:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PySide6 import QtCore, QtGui, QtWidgets
        from planner_app.paths import appDirectory, externalDirectory, furnishingsDirectory, fontsDirectory, themesDirectory, texturesDirectory, helpDirectory
        from planner_app.graphics.theme import ApplyApplicationTheme
        from planner_app.graphics import palette
        from planner_app.models import Wall, Furnishing, Label
        from planner_app.project_codec import DecodeProject
        from planner_app.graphics.svg_preview import SvgPreviewRenderer
        from planner_app.optimized_png import EncodeOptimizedPng
        from planner_app.ui.main_window import MainWindow
        assert getattr(sys, "frozen", False)
        assert appDirectory == externalDirectory / "_internal"
        resources = {"furnishings": furnishingsDirectory, "fonts": fontsDirectory,
                     "themes": themesDirectory, "textures": texturesDirectory, "help": helpDirectory}
        for name, directory in resources.items():
            assert directory.is_dir() and directory.is_relative_to(externalDirectory)
            assert not directory.is_relative_to(appDirectory), name
        app = QtWidgets.QApplication([])
        app.setApplicationName("Planner")
        app.setStyle("Fusion")
        ApplyApplicationTheme(app)
        callbackErrors = []
        sys.excepthook = lambda *args: callbackErrors.append("".join(traceback.format_exception(*args)))
        window = MainWindow()
        viewport = window.viewport
        window.sessionTimer.stop()
        window.sessionPollTimer.stop()
        point = QtCore.QPointF
        viewport.walls = [Wall(point(0, 0), point(4000, 0), 200)]
        viewport.windows = []
        viewport.furnishings = [Furnishing(viewport.furnishingDefinitions["desk"], point(2000, 1500))]
        viewport.labels = [Label(point(2000, 3000), "Packaged Planner")]
        viewport.objectGroups, viewport.hiddenObjects = [], []
        viewport.EnsureObjectIds()
        assert len(DecodeProject(window.BuildProjectData(includeHistory = False), viewport.furnishingDefinitions)[2]) == 1
        window.ShowHelp("drawing.md")
        app.processEvents()
        assert "Drawing walls" in window.helpWindow.browser.toPlainText()
        assert Path(window.helpWindow.browser.source().toLocalFile()).resolve() == helpDirectory / "drawing.md"
        movie = QtGui.QMovie(str(helpDirectory / "images/draw_wall.gif"))
        assert movie.isValid(), "GIF plugin or external help image is unavailable"
        window.helpWindow.close()
        panel = window.exportPanel
        panel.overrides = {"border": "None", "bounds": [-1000, -1000, 6000, 6000], "scale": 50}
        window.sidebarTabs.setCurrentWidget(panel)
        panel.SetOverride("texture", "cardboard_t1_75_25_5_5.png")
        viewport.resize(800, 600)
        panel.SetOverride("gridOrigin", [337.25, -123.75])
        for position, expected in ((point(viewport.rulerSize + 20, viewport.rulerSize / 2), (0, -123.75)),
                                   (point(viewport.rulerSize / 2, viewport.rulerSize + 20), (0, 0))):
            event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonDblClick, position, position,
                                     QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.NoButton,
                                     QtCore.Qt.KeyboardModifier.NoModifier)
            viewport.exportOverlay.eventFilter(viewport, event)
            assert viewport.gridOrigin == expected, "Export ruler axis reset failed"
        png, svg = panel.Render("png"), panel.Render("svg")
        assert not png.isNull() and SvgPreviewRenderer(svg).isValid()
        optimizedData = EncodeOptimizedPng(png)
        optimized = QtGui.QImage.fromData(optimizedData, "PNG")
        assert optimized.size() == png.size(), "QtQml/UPNG export failed"
        for name in ("OFL.txt", "OFL-D-DIN.txt", "OFL-DraftingSmallCaps.txt", "FONTLOG.txt"):
            assert (fontsDirectory / name).is_file(), "Missing font notice: " + name
        assert not callbackErrors, callbackErrors
        report.update({"ok": True, "python": sys.version.split()[0], "qt": QtCore.qVersion(),
                       "externalResources": {name: str(path) for name, path in resources.items()},
                       "furnishings": len(viewport.furnishingDefinitions), "themes": len(palette.themeDefinitions),
                       "fonts": len(app.plannerFontIds), "pngSize": [png.width(), png.height()],
                       "svgBytes": len(svg), "optimizedPngBytes": len(optimizedData)})
        window.MarkProjectClean()
        window.close()
    except BaseException:
        report["error"] = traceback.format_exc()
    reportPath.write_text(json.dumps(report, indent = 2), encoding = "utf-8")
    return 0 if report["ok"] else 1
