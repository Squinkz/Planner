"""Export room style and solid rooms inherit, render, undo and persist independently."""
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
            assert (panel.roomStyleField.currentText() == "Tinted") == inherited and v.floors == inherited
            assert "roomStyle" not in panel.overrides
            main.sidebarTabs.setCurrentIndex(0)
            assert v.floors == inherited
        assert panel.roomStyleField.accessibleName() == "Room Style"
        assert [panel.roomStyleField.itemText(index) for index in range(panel.roomStyleField.count())] == ["Canvas", "Tinted"]
        assert panel.solidRoomsField.accessibleName() == "Solid Rooms" and not panel.solidRoomsField.isChecked()
        form = next(form for form in panel.findChildren(QtWidgets.QGridLayout) if form.indexOf(panel.solidRoomsField) >= 0)
        solidRow, solidColumn, *_ = form.getItemPosition(form.indexOf(panel.solidObjectsField))
        floorRow, floorColumn, *_ = form.getItemPosition(form.indexOf(panel.solidRoomsField))
        assert floorRow + 1 == solidRow and floorColumn == solidColumn

        main.sidebarTabs.setCurrentWidget(panel)
        panel.borderField.setCurrentText("None")
        panel.scaleField.setValue(100)
        panel.SetBounds([-2000, -2000, 4000, 4000])
        for outputFormat in ("PNG", "SVG"):
            panel.typeField.setCurrentIndex(panel.typeField.findData(outputFormat))
            for enabled in (True, False, True):
                panel.roomStyleField.setCurrentText("Tinted" if enabled else "Canvas")
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
        # Solid rooms suppress grid ink for both room styles, including vector export.
        panel.showGridField.setChecked(True)
        panel.SetOverride("viewportSettings", dict(overall = 1.0, origin = 1.0, major = 1.0, minor = 1.0))
        for style in ("Canvas", "Tinted"):
            panel.roomStyleField.setCurrentText(style)
            fill = QtGui.QColor(palette.themeColors["roomFill" if style == "Tinted" else "canvas"])
            exterior = None
            for solid in (False, True, False):
                panel.solidRoomsField.setChecked(solid)
                png = panel.Render("png")
                sample = QtCore.QPoint(png.width() // 2, png.height() // 2)
                assert (png.pixelColor(sample) == fill) == solid, (style, solid, "png")
                outside = png.pixelColor(sample + QtCore.QPoint(150, 0))
                assert outside != QtGui.QColor(palette.themeColors["canvas"])
                assert exterior is None or exterior == outside
                exterior = outside
                svg = panel.Render("svg")
                vector = QtGui.QImage(png.size(), QtGui.QImage.Format.Format_ARGB32)
                vector.fill(0)
                with QtGui.QPainter(vector) as painter:
                    QtSvg.QSvgRenderer(svg).render(painter)
                assert (vector.pixelColor(sample) == fill) == solid, (style, solid, "svg")
                preview = v.grab().toImage()
                center = (v.WorldToViewport(QtCore.QPointF()) * v.devicePixelRatioF()).toPoint()
                assert (preview.pixelColor(center) == fill) == solid, (style, solid, "preview")
        panel.solidRoomsField.setChecked(True)
        panel.UndoExport()
        assert not panel.solidRoomsField.isChecked() and not v.solidRooms
        panel.RedoExport()
        assert panel.solidRoomsField.isChecked() and v.solidRooms
        panel.solidRoomsField.setChecked(False)
        panel.showGridField.setChecked(False)
        panel.roomStyleField.setCurrentText("Tinted")
        # Object fill and room detection/areas remain independent of this paint toggle.
        panel.solidObjectsField.setChecked(False)
        assert panel.roomStyleField.isEnabled() and (panel.roomStyleField.currentText() == "Tinted")
        assert panel.Render("png").pixelColor(200, 200) == QtGui.QColor(palette.themeColors["roomFill"])
        panel.roomStyleField.setCurrentText("Canvas")
        panel.UndoExport()
        assert (panel.roomStyleField.currentText() == "Tinted") and v.floors
        panel.RedoExport()
        assert not (panel.roomStyleField.currentText() == "Tinted") and not v.floors

        # Marked borders must not suppress floor shading.
        panel.borderField.setCurrentText("Marked")
        panel.roomStyleField.setCurrentText("Tinted")
        marked = panel.Render("png")
        middle = QtCore.QPoint(marked.width() // 2, marked.height() // 2)
        assert marked.pixelColor(middle) == QtGui.QColor(palette.themeColors["roomFill"])
        panel.borderField.setCurrentText("None")

        # The real worker path supports the toggle for PNG, SVG and Optimized PNG.
        panel.showGridField.setChecked(True)
        panel.solidRoomsField.setChecked(True)
        for kind in ("PNG", "SVG", "PNG_OPTIMIZED"):
            panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
            panel.roomStyleField.setCurrentText("Canvas")
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
        assert settings["roomStyle"] == "Tinted" and settings["exportSettings"]["roomStyle"] == "Canvas"
        assert not settings["solidRooms"] and settings["exportSettings"]["solidRooms"]
        cli = RenderPlan(project, 100, projectData = data, useExportSettings = True)
        assert cli.pixelColor(200, 200) == QtGui.QColor(palette.themeColors["canvas"])
        main.sidebarTabs.setCurrentIndex(0)
        assert v.floors and not v.solidRooms
        assert main.OpenProject(project)
        main.sidebarTabs.setCurrentWidget(panel)
        assert not (panel.roomStyleField.currentText() == "Tinted") and not v.floors
        assert panel.projectView["roomStyle"] == "Tinted"
        assert panel.solidRoomsField.isChecked() and v.solidRooms and not panel.projectView["solidRooms"]
        panel.grab().save(str(Path(__file__).resolve().parents[1] / "diagnostics/export-room-options.png"))
        legacy = copy.deepcopy(data)
        legacy["settings"].pop("roomStyle", None)
        legacy["settings"]["floors"] = False
        legacy["settings"]["exportSettings"] = {"floors": True}
        migrated = DecodeProject(legacy, v.furnishingDefinitions)[5]
        assert migrated["roomStyle"] == "Canvas" and migrated["exportSettings"]["roomStyle"] == "Tinted"
        assert not migrated["solidRooms"]
        for field, value in (("roomStyle", "Unknown"), ("roomStyle", False), ("solidRooms", 1)):
            bad = copy.deepcopy(data)
            bad["settings"]["exportSettings"][field] = value
            try:
                DecodeProject(bad, v.furnishingDefinitions)
            except ValueError:
                pass
            else:
                raise AssertionError("Accepted an invalid room option")
        for value in (0, "yes", None):
            bad = copy.deepcopy(data)
            bad["settings"]["exportSettings"]["floors"] = value
            try:
                DecodeProject(bad, v.furnishingDefinitions)
            except ValueError:
                pass
            else:
                raise AssertionError("Accepted a non-boolean floor override")
    print("PASS: room styles, solid room grid clipping, PNG/SVG previews, worker formats, CLI, undo, migration and persistence")


if __name__ == "__main__":
    Main()
