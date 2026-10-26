"""Export floor shading inherits editor state and remains independent and persistent."""
import copy
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_room_detection import Rectangle
from planner_app.graphics import palette
from planner_app.project_codec import DecodeProject
from planner_app.export_plan import RenderPlan


def Main():
    with ExampleWindow() as (main, folder):
        v, panel = main.viewport, main.exportPanel
        InstallScene(main, Rectangle(-1000, -1000, 2000, 2000))
        v.showGrid = v.showMeasurements = v.showTips = False
        for inherited in (False, True):
            v.floors = inherited
            main.sidebarTabs.setCurrentWidget(panel)
            assert panel.floorsField.isChecked() == inherited and v.floors == inherited
            assert "floors" not in panel.overrides
            main.sidebarTabs.setCurrentIndex(0)
            assert v.floors == inherited
        assert panel.floorsField.accessibleName() == "Floors" and not panel.floorsField.text()
        form = next(form for form in panel.findChildren(QtWidgets.QGridLayout) if form.indexOf(panel.floorsField) >= 0)
        solidRow, solidColumn, *_ = form.getItemPosition(form.indexOf(panel.solidObjectsField))
        floorRow, floorColumn, *_ = form.getItemPosition(form.indexOf(panel.floorsField))
        assert floorRow == solidRow + 1 and floorColumn == solidColumn

        main.sidebarTabs.setCurrentWidget(panel)
        panel.borderField.setCurrentText("None")
        panel.scaleField.setValue(100)
        panel.SetBounds([-2000, -2000, 4000, 4000])
        for outputFormat in ("PNG", "SVG"):
            panel.typeField.setCurrentIndex(panel.typeField.findData(outputFormat))
            for enabled in (True, False, True):
                panel.floorsField.setChecked(enabled)
                expected = QtGui.QColor(palette.themeColors["roomFill" if enabled else "canvas"])
                png = panel.Render("png")
                assert png.pixelColor(200, 200) == expected, (outputFormat, enabled)
                assert png.pixelColor(350, 50) == QtGui.QColor(palette.themeColors["canvas"])
                svg = panel.Render("svg")
                renderer = QtSvg.QSvgRenderer(svg)
                vector = QtGui.QImage(png.size(), QtGui.QImage.Format.Format_ARGB32)
                vector.fill(0)
                with QtGui.QPainter(vector) as painter:
                    renderer.render(painter)
                assert vector.pixelColor(200, 200) == expected
                preview = v.grab().toImage()
                center = (v.WorldToViewport(QtCore.QPointF()) * v.devicePixelRatioF()).toPoint()
                assert preview.pixelColor(center) == expected, (outputFormat, enabled, center)
                assert not v.exportOverlay.previewError
        # Object fill and room detection/areas remain independent of this paint toggle.
        panel.solidObjectsField.setChecked(False)
        assert panel.floorsField.isEnabled() and panel.floorsField.isChecked()
        assert panel.Render("png").pixelColor(200, 200) == QtGui.QColor(palette.themeColors["roomFill"])
        panel.floorsField.setChecked(False)
        panel.UndoExport()
        assert panel.floorsField.isChecked() and v.floors
        panel.RedoExport()
        assert not panel.floorsField.isChecked() and not v.floors

        # Marked borders must not suppress floor shading.
        panel.borderField.setCurrentText("Marked")
        panel.floorsField.setChecked(True)
        marked = panel.Render("png")
        middle = QtCore.QPoint(marked.width() // 2, marked.height() // 2)
        assert marked.pixelColor(middle) == QtGui.QColor(palette.themeColors["roomFill"])
        panel.borderField.setCurrentText("None")

        # The real worker path supports the toggle for PNG, SVG and Optimized PNG.
        for kind in ("PNG", "SVG", "PNG_OPTIMIZED"):
            panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
            panel.floorsField.setChecked(False)
            panel.folderField.setText(str(folder))
            panel.fileNameField.setText("floor-test-" + kind.lower() + (".svg" if kind == "SVG" else ".png"))
            path = panel.OutputPath()
            with patch.object(main, "ShowAppMessage") as notice:
                panel.Export()
            assert not notice.called, notice.call_args
            if kind != "SVG":
                assert QtGui.QImage(str(path)).pixelColor(200, 200) == QtGui.QColor(palette.themeColors["canvas"])
            else:
                assert path.exists() and QtSvg.QSvgRenderer(str(path)).isValid()
        project = folder / "floors.plan"
        assert main.SaveProject(project)
        data = main.BuildProjectData(includeHistory = False)
        settings = DecodeProject(data, v.furnishingDefinitions)[5]
        assert settings["floors"] and settings["exportSettings"]["floors"] is False
        cli = RenderPlan(project, 100, projectData = data, useExportSettings = True)
        assert cli.pixelColor(200, 200) == QtGui.QColor(palette.themeColors["canvas"])
        main.sidebarTabs.setCurrentIndex(0)
        assert v.floors
        assert main.OpenProject(project)
        main.sidebarTabs.setCurrentWidget(panel)
        assert not panel.floorsField.isChecked() and not v.floors
        assert panel.projectView["floors"]
        for value in (0, "yes", None):
            bad = copy.deepcopy(data)
            bad["settings"]["exportSettings"]["floors"] = value
            try:
                DecodeProject(bad, v.furnishingDefinitions)
            except ValueError:
                pass
            else:
                raise AssertionError("Accepted a non-boolean floor override")
    print("PASS: floor inheritance, PNG/SVG previews, all file types, CLI, undo and project persistence")


if __name__ == "__main__":
    Main()
