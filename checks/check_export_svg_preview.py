"""SVG preview matches exported bytes and magnifies without rebuilding geometry."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtTest, QtWidgets
from planner import MainWindow, Wall
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.graphics.palette import themeColors


def Main():
    with tempfile.TemporaryDirectory(dir = Path(__file__).parent) as folder:
        folder = Path(folder)
        os.environ["PLANNER_SESSION_PATH"] = str(folder / "session.json")
        os.environ["PLANNER_STARTUP_PATH"] = str(folder / "startup.plan")
        app = QtWidgets.QApplication([])
        ApplyApplicationTheme(app)
        main = MainWindow()
        main.show()
        v = main.viewport
        v.walls = [Wall(QtCore.QPointF(-1000, 0), QtCore.QPointF(1000, 0), 240)]
        v.EnsureObjectIds()
        v.sceneRevision += 1
        main.projectPath = folder / "preview.plan"
        main.sidebarTabs.setCurrentWidget(main.exportPanel)
        panel, overlay = main.exportPanel, v.exportOverlay
        panel.borderField.setCurrentText("Ruler")
        panel.scaleField.setValue(50)
        v.ResetView()
        v.grab()
        assert overlay.snapshot is not None
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        x, y, width, height = overlay.bounds
        frame = v.WorldToViewport(QtCore.QPointF(x, y + height)) - QtCore.QPointF(v.rulerSize, v.rulerSize)
        v.panOffset += QtCore.QPointF(round(frame.x()) - frame.x(), round(frame.y()) - frame.y())
        preview = v.grab().toImage().convertToFormat(QtGui.QImage.Format.Format_ARGB32)
        renderer = overlay.svgRenderer
        assert renderer is not None and renderer.isValid() and not overlay.previewError
        assert overlay.svgData == panel.Render("svg", preview = True, previewScene = True)
        expected = QtGui.QImage(renderer.defaultSize(), QtGui.QImage.Format.Format_ARGB32)
        expected.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(expected)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
        x, y, width, height = overlay.bounds
        first = v.WorldToViewport(QtCore.QPointF(x, y + height))
        frame = first - QtCore.QPointF(v.rulerSize, v.rulerSize)
        # Compare the plan interior, excluding independently drawn crop guides.
        offset = v.rulerSize + 5
        sampleWidth = expected.width() - 2 * offset
        sampleHeight = expected.height() - 2 * offset
        assert preview.copy(round(frame.x()) + offset, round(frame.y()) + offset, sampleWidth, sampleHeight) == expected.copy(offset, offset, sampleWidth, sampleHeight)
        rulerRect = QtCore.QRect(round(frame.x()), round(frame.y()), expected.width(), v.rulerSize - 2)
        for button in (QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.MiddleButton):
            QtTest.QTest.mousePress(v, button, pos = v.DrawingRect().center().toPoint())
            held = v.grab().toImage().convertToFormat(QtGui.QImage.Format.Format_ARGB32)
            assert held.copy(rulerRect) == preview.copy(rulerRect), "Ruler changed while holding a stationary mouse button"
            QtTest.QTest.mouseRelease(v, button, pos = v.DrawingRect().center().toPoint())
        wallPoint = v.WorldToViewport(QtCore.QPointF(-800, 0))
        v.ZoomBy(50, wallPoint)
        QtTest.QTest.qWait(250)
        enlarged = v.grab().toImage()
        assert enlarged.pixelColor(wallPoint.toPoint()) == QtGui.QColor(themeColors["wallFill"]), "Sharp preview loses walls at high zoom"
        v.ResetView()
        v.grab()
        data = overlay.svgData
        navigationImage = overlay.svgNavigationImage
        sharpImage = overlay.svgViewImage
        with patch.object(renderer, "render", wraps = renderer.render) as drawVector:
            for factor in (1.2, 1.2, 1.2):
                v.ZoomBy(factor, QtCore.QPointF(v.DrawingRect().center()))
                v.panOffset += QtCore.QPointF(7, 3)
                v.grab()
            assert drawVector.call_count == 0, "Zooming rerendered the SVG"
            assert overlay.svgNavigationImage is navigationImage and overlay.svgViewImage is sharpImage
            QtTest.QTest.qWait(250)
            v.grab()
            assert drawVector.call_count == 1, "Stopping zoom did not refresh the sharp preview once"
            sharpImage = overlay.svgViewImage
            v.grab()
            assert overlay.svgViewImage is sharpImage and drawVector.call_count == 1
            position = v.DrawingRect().center().toPoint()
            QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.MiddleButton, pos = position)
            for distance in (10, 20, 30):
                QtTest.QTest.mouseMove(v, position + QtCore.QPoint(distance, 0))
                v.grab()
            assert drawVector.call_count == 1, "Panning rerendered the SVG"
            QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.MiddleButton, pos = position + QtCore.QPoint(30, 0))
            QtTest.QTest.qWait(250)
            v.grab()
            assert drawVector.call_count == 2, "Stopping pan did not refresh the sharp preview"
        assert overlay.svgRenderer is renderer and overlay.svgData is data
        outputPath = panel.OutputPath()
        main.exportButton.click()
        assert outputPath.read_bytes() == panel.Render("svg")
        for change in (lambda: panel.scaleField.setValue(75),
                       lambda: overlay.MoveEdge(0, overlay.bounds[0] + 1000),
                       lambda: panel.unitsField.setCurrentText("Centimeters"),
                       lambda: panel.borderField.setCurrentText("None"),
                       lambda: panel.lineworkFields["walls"].setValue(.75),
                       lambda: panel.showGridField.setChecked(False)):
            previous = overlay.svgRenderer
            change()
            v.grab()
            assert overlay.svgRenderer is not previous and overlay.svgData == panel.Render("svg", preview = True, previewScene = True)
        panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
        v.grab()
        assert overlay.snapshot is not None and not overlay.previewError
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        with patch.object(overlay, "renderVector", side_effect = ValueError("Preview failure")):
            v.grab()
        assert overlay.svgRenderer is None and overlay.previewError == "Preview failure"
        panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
        v.grab()
        assert not overlay.previewError
        main.MarkProjectClean()
        main.close()
        print("PASS: vector preview pixels/bytes, pan/zoom cache, export changes, format switching and errors")


if __name__ == "__main__":
    Main()
