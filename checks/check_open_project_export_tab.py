"""Open leaves Export only when installing the replacement, preserving failures."""
import copy
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.geometry_recovery import GeometryLoadCancelled
from planner_app.models import Wall
from planner_app.project_codec import DecodeProject, EncodeScene
from planner_app.project_recovery import RecoverProject


def Main():
    with ExampleWindow() as (main, folder):
        panel, view = main.exportPanel, main.viewport
        wall = Wall(QtCore.QPointF(0, 0), QtCore.QPointF(5000, 0), 200)
        InstallScene(main, [wall])
        original = folder / "original.plan"
        assert main.SaveProject(original)
        incoming = copy.deepcopy(main.BuildProjectData(includeHistory = False))
        incoming["scene"]["objects"][0]["second"] = [6000, 6000]
        path = folder / "incoming.plan"
        path.write_text(json.dumps(incoming), encoding = "utf-8")
        main.sidebarTabs.setCurrentWidget(panel)
        panel.typeField.setCurrentIndex(panel.typeField.findData("PDF_RASTER"))
        panel.SetScaleOption("architecturalScale", 125)
        panel.SetScaleOption("dpi", 96)
        panel.SetTitleBlockOption("enabled", True)
        panel.SetTitleBlockOption("projectName", "Current project")
        panel.SetScaleOption("pageOrigin", [1000, 2000])
        width, height = panel.PrintLayout()["paperTile"]
        view.exportOverlay.bounds = (1000, 2000, width, height)
        panel.SetBounds(view.exportOverlay.bounds)
        # Include offscreen navigation: rollback must not helpfully recenter it.
        view.zoom, view.panOffset = .6, QtCore.QPointF(100000, -30000)
        main.MarkProjectClean()
        scene = EncodeScene(view)
        camera = view.zoom, QtCore.QPointF(view.panOffset)
        state = panel.ExportHistoryState()
        history = list(panel.exportUndoHistory), list(panel.exportRedoHistory)
        projectView = copy.deepcopy(panel.projectView)

        def CheckExport():
            assert main.sidebarTabs.currentWidget() is panel and view.exportOverlay.active
            assert main.projectPath == original and view.walls[0] is wall
            assert EncodeScene(view) == scene and panel.ExportHistoryState() == state
            assert (panel.exportUndoHistory, panel.exportRedoHistory) == history
            assert panel.projectView == projectView
            assert view.zoom == camera[0] and view.panOffset == camera[1]

        def CancelPicker(*args, **kwargs):
            CheckExport()
            return "", ""

        with patch.object(QtWidgets.QFileDialog, "getOpenFileName", side_effect = CancelPicker):
            assert not main.OpenProject()
        CheckExport()
        # Dirty-project confirmation must also remain over Export.
        main.savedSettingsSignature = bytes(32)

        def CancelReplacement(*args, **kwargs):
            CheckExport()
            assert args[0] == "Unsaved Project"
            return QtWidgets.QMessageBox.StandardButton.Cancel

        with patch.object(main, "ShowAppMessage", side_effect = CancelReplacement):
            assert not main.OpenProject(path)
        CheckExport()
        with patch.object(main, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.Save), \
                patch.object(main, "SaveProject", return_value = False):
            assert not main.OpenProject(path)
        CheckExport()
        main.MarkProjectClean()
        broken = folder / "broken.plan"
        broken.write_text("not JSON", encoding = "utf-8")
        with patch.object(panel, "SetActive", wraps = panel.SetActive) as active, \
                patch.object(main, "ShowAppMessage"):
            assert not main.OpenProject(folder / "missing.plan")
            CheckExport()
            assert not main.OpenProject(broken)
            CheckExport()
            with patch("planner_app.project_recovery.RecoverProject", side_effect = GeometryLoadCancelled):
                assert not main.OpenProject(path)
            CheckExport()
            decoded = DecodeProject(incoming, view.furnishingDefinitions)
            with patch("planner_app.project_recovery.RecoverProject", return_value = (decoded, ["Fixture repair"])), \
                    patch.object(main, "BackupProjectForRecovery", side_effect = OSError("Unavailable backup folder")):
                assert not main.OpenProject(path)
            CheckExport()
            assert not any(not call.args[0] for call in active.call_args_list), "A failed preflight deactivated the preview"

        apply = main.ApplyProject
        attempts = []

        def FailApply(decoded, target):
            attempts.append(target)
            result = apply(decoded, target)
            if len(attempts) == 1:
                raise RuntimeError("Failure after installing the incoming model")
            return result

        def OpenError(*args, **kwargs):
            CheckExport()
            assert args[0] == "Cannot Open Project", args

        with patch.object(main, "ApplyProject", side_effect = FailApply), \
                patch.object(main, "ShowAppMessage", side_effect = OpenError):
            assert not main.OpenProject(path)
        assert len(attempts) == 2
        CheckExport()

        def ReadIncoming(*args, **kwargs):
            CheckExport()
            return RecoverProject(*args, **kwargs)

        def InstallIncoming(decoded, target):
            CheckExport()
            result = apply(decoded, target)
            assert main.sidebarTabs.currentWidget() is main.buildScrollArea
            assert not view.exportOverlay.active and panel.projectView is None
            return result

        with patch("planner_app.project_recovery.RecoverProject", side_effect = ReadIncoming), \
                patch.object(main, "ApplyProject", side_effect = InstallIncoming):
            assert main.OpenProject(path)
        assert main.projectPath == path and view.walls[0] is not wall
        assert view.walls[0].secondVertex == QtCore.QPointF(6000, 6000)
    print("PASS: picker/confirmation/load/recovery failures preserve Export; failed apply restores its camera/history; successful open switches to Build")


if __name__ == "__main__":
    Main()
