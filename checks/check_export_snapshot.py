"""Successful exports freeze inherited settings; failures keep sparse overrides."""
import copy
from pathlib import Path
import os
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall
from planner_app.export_plan import RenderPlan
from planner_app.graphics import palette
from planner_app.project_codec import DecodeProject
from planner_app.units import measurementPrecisions


def Main():
    with ExampleWindow() as (main, folder):
        v, panel = main.viewport, main.exportPanel
        InstallScene(main, [Wall(QtCore.QPointF(-1500, 0), QtCore.QPointF(1500, 0))])
        v.unitsMode = "Centimeters"
        main.sidebarTabs.setCurrentWidget(panel)
        expectedKeys = {"fileType", "canvasTheme", "canvasColor", "linesColor", "gridColor", "borderColor",
                        "showGrid", "roomStyle", "solidRooms", "solidObjects", "wallStyle", "viewportSettings",
                        "lineworkSettings", "measurementVisibility", "measurementSettings", "wallMeasurementMode",
                        "wallMeasurementReference", "measurementPrecision", "visibility", "unitsMode", "bounds",
                        "gridOrigin", "scale", "scaleUnits", "scaleMode", "architecturalScale", "dpi", "border",
                        "borderSize", "texture", "textureAngle", "textureScale", "textureStrength", "textureHighlights",
                        "textureMidtones", "textureShadows", "vignetteEnabled", "vignetteStrength"}
        for kind in ("PNG", "SVG", "PNG_OPTIMIZED"):
            panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
            panel.overrides = {"fileType": kind, "viewportSettings": {"minor": .23}, "canvasColor": "#faf8f0"}
            panel.ApplyView(panel.ResolvedView())
            panel.RefreshControls()
            panel.fileNameField.setText(kind.lower())
            panel.ResetExportHistory()
            sparse = copy.deepcopy(panel.overrides)
            expectedView = copy.deepcopy(panel.ResolvedView())
            # Declining an overwrite, cancellation and a worker failure must not
            # pin values or create a new undo entry.
            path = panel.OutputPath()
            path.write_bytes(b"existing")
            with patch.object(main, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.No):
                panel.Export()
            assert panel.overrides == sparse and not panel.exportUndoHistory
            path.unlink()
            for error in (None, "Export worker failed"):
                with patch("planner_app.ui.export_progress.ExportProgressDialog") as factory, \
                     patch.object(main, "ShowAppMessage"):
                    factory.return_value.exec.return_value = QtWidgets.QDialog.DialogCode.Rejected
                    factory.return_value.error = error
                    panel.Export()
                assert panel.overrides == sparse and not panel.exportUndoHistory
            with patch("planner_app.ui.export_progress.ExportProgressDialog") as factory:
                factory.return_value.exec.return_value = QtWidgets.QDialog.DialogCode.Accepted
                factory.return_value.error = None
                panel.Export()
            frozen = copy.deepcopy(panel.overrides)
            colors = dict(palette.themeColors)
            panel.ApplyView(panel.ResolvedView())
            assert palette.themeColors == colors
            assert set(frozen) == expectedKeys, (set(frozen) - expectedKeys, expectedKeys - set(frozen))
            assert frozen["fileType"] == kind and frozen["unitsMode"] == "Centimeters"
            for key in ("viewportSettings", "lineworkSettings", "measurementSettings", "visibility"):
                assert frozen[key] == expectedView[key], key
            assert frozen["measurementVisibility"] == expectedView["measurementVisibility"]
            assert frozen["bounds"] == list(v.exportOverlay.bounds)
            assert frozen["gridOrigin"] == list(v.gridOrigin)
            assert frozen["canvasColor"] == "#faf8f0"
            assert all(frozen[key] is None for key in ("linesColor", "gridColor", "borderColor"))
            assert frozen["textureScale"] == 1 and frozen["textureStrength"] == .5
            assert all(frozen["texture" + key] == 1 for key in ("Highlights", "Midtones", "Shadows"))
            assert DecodeProject(main.BuildProjectData(), v.furnishingDefinitions)[5]["exportSettings"] == frozen
            assert len(panel.exportUndoHistory) == 1
            panel.UndoExport()
            assert panel.overrides == sparse
            panel.RedoExport()
            assert panel.overrides == frozen
        # Later editor changes, including complete nested groups, cannot leak
        # into the captured export settings. Save/open preserves that boundary.
        main.sidebarTabs.setCurrentIndex(0)
        v.unitsMode = "Inches"
        v.showGrid = not frozen["showGrid"]
        v.measurementPrecision = next(key for key in measurementPrecisions if key != frozen["measurementPrecision"])
        v.gridIntensities = {key: .71 for key in v.gridIntensities}
        v.visibility = {key: False for key in v.visibility}
        main.sidebarTabs.setCurrentWidget(panel)
        resolved = panel.ResolvedView()
        assert resolved["unitsMode"] == frozen["unitsMode"] and resolved["showGrid"] == frozen["showGrid"]
        assert resolved["viewportSettings"] == frozen["viewportSettings"]
        assert resolved["visibility"] == frozen["visibility"]
        assert resolved["measurementPrecision"] == frozen["measurementPrecision"]
        main.sidebarTabs.setCurrentIndex(0)
        plan = folder / "frozen.plan"
        assert main.SaveProject(plan) and main.OpenProject(plan)
        assert panel.overrides == frozen
        rendered = RenderPlan(plan, 100, useExportSettings = True)
        assert rendered is not None and not rendered.isNull()
        # The editor master being off must stay off in exported dimensions even
        # after the editor enables it later.
        v.showMeasurements = False
        main.sidebarTabs.setCurrentWidget(panel)
        panel.overrides = {}
        captured = panel.CaptureExportOverrides()
        assert not any(captured["measurementVisibility"].values())
        panel.overrides = {"texture": "fixture_t6.png"}
        captured = panel.CaptureExportOverrides()
        assert captured["textureScale"] is None
        panel.overrides = captured
        panel.RefreshControls()
        assert DecodeProject(main.BuildProjectData(), v.furnishingDefinitions)[5]["exportSettings"]["textureScale"] is None
    print("PASS: every export option captured, Theme colors, persistence, undo, isolation and cancellation/failure safety")


if __name__ == "__main__":
    Main()
