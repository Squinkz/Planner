"""Startup/replacement use Build; cancelled opens and saves preserve Export."""
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_export_preview_process import WaitForPreview
from planner_app.models import Wall
from planner_app.ui.export_panel import ExportPanel
from planner_app.ui.main_window import MainWindow


def AssertBuild(main):
    assert main.sidebarTabs.currentWidget() is main.buildScrollArea
    assert main.exportPanel.projectView is None and not main.viewport.exportOverlay.active
    assert main.exportActionPanel.isHidden()
    worker = main.viewport.exportOverlay.previewProcess
    if worker is not None:
        assert worker.process.state() == QtCore.QProcess.ProcessState.NotRunning
        assert worker.current is None and not worker.queue


def Main():
    with ExampleWindow() as (main, folder):
        AssertBuild(main)
        panel, v = main.exportPanel, main.viewport
        InstallScene(main, [Wall(QtCore.QPointF(0, 0), QtCore.QPointF(4000, 0), 200)])
        path = folder / "Project.plan"
        assert main.SaveProject(path)
        with patch.object(main, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.Discard):
            for action in (main.NewProject, main.CloseProject, main.RevertProject, lambda: main.OpenProject(path)):
                assert main.OpenProject(path)
                main.sidebarTabs.setCurrentWidget(panel)
                assert v.exportOverlay.active
                assert action()
                AssertBuild(main)
            assert main.OpenProject(path)
            before = v.CaptureState()
            v.walls[0].width += 10
            v.RecordEdit(before)
            main.RefreshProjectDirty()
            assert main.projectDirty
            with patch.object(main, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.Cancel):
                for action in (main.NewProject, main.CloseProject, main.RevertProject):
                    main.sidebarTabs.setCurrentWidget(panel)
                    assert not action()
                    AssertBuild(main)
                    assert v.walls[0].width == 210
                main.sidebarTabs.setCurrentWidget(panel)
                assert not main.OpenProject(path)
                assert main.sidebarTabs.currentWidget() is panel and v.exportOverlay.active
                assert v.walls[0].width == 210
            for action, dialog in ((main.OpenProject, "getOpenFileName"), (main.SaveProjectAs, "getSaveFileName")):
                main.sidebarTabs.setCurrentWidget(panel)
                with patch.object(QtWidgets.QFileDialog, dialog, return_value = ("", "")):
                    assert not action()
                assert main.sidebarTabs.currentWidget() is panel and v.exportOverlay.active
            invalid = folder / "Broken.plan"
            invalid.write_text("not JSON", encoding = "utf-8")
            main.sidebarTabs.setCurrentWidget(panel)
            assert not main.OpenProject(invalid)
            assert main.sidebarTabs.currentWidget() is panel and v.exportOverlay.active
            assert v.walls[0].width == 210
        # A live worker must stop when an actual project is opened from Export.
        assert main.SaveProject(path)
        os.environ.pop("PLANNER_SYNCHRONOUS_PREVIEW", None)
        try:
            main.sidebarTabs.setCurrentWidget(panel)
            WaitForPreview(v, "png")
            worker = v.exportOverlay.previewProcess
            assert worker.process.processId()
            processId = worker.process.processId()
            assert main.SaveProject(path)
            assert main.sidebarTabs.currentWidget() is panel and v.exportOverlay.active
            assert worker.process.processId() == processId, "Saving restarted the active export worker"
            saved = json.loads(path.read_text(encoding = "utf-8"))
            assert saved["view"]["zoom"] == panel.projectZoom
            assert saved["view"]["pan"] == [panel.projectPanOffset.x(), panel.projectPanOffset.y()]
            assert main.OpenProject(path)
            AssertBuild(main)
        finally:
            os.environ["PLANNER_SYNCHRONOUS_PREVIEW"] = "1"
        # Save a real checkpoint on Export. Recovery must never even activate
        # that tab briefly, before or after the deferred layout restoration.
        panel.SetOverride("titleBlock", dict(enabled = True, logoMode = "None"))
        main.sidebarTabs.setCurrentWidget(panel)
        main.sessionTimer.stop()
        main.sessionPollTimer.stop()
        assert main.WriteSession(wait = True)
        checkpoint = json.loads(main.sessionPath.read_text(encoding = "utf-8"))
        assert checkpoint["ui"]["tab"] == main.sidebarTabs.indexOf(panel)
        main.sidebarTabs.setCurrentWidget(main.buildScrollArea)
        activated = []
        originalActive = ExportPanel.SetActive

        def SetActive(panel, active):
            if active:
                activated.append(panel)
            return originalActive(panel, active)

        with patch.object(ExportPanel, "SetActive", SetActive):
            restored = MainWindow()
            try:
                assert restored.sessionRestored
                AssertBuild(restored)
                restored.show()
                QtWidgets.QApplication.processEvents()
                AssertBuild(restored)
                assert not activated, "Recovery briefly activated Export"
                assert restored.exportPanel.overrides["titleBlock"]["enabled"]
            finally:
                restored.close()
                restored.deleteLater()
                QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        # A startup template can carry export settings, but cannot select Export.
        main.startupPath.write_text(json.dumps(main.BuildProjectData(includeHistory = False)), encoding = "utf-8")
        with patch.dict(os.environ, PLANNER_SESSION_PATH = str(folder / "fresh-session.json")), \
                patch.object(ExportPanel, "SetActive", SetActive):
            activated.clear()
            fresh = MainWindow()
            try:
                assert fresh.startupRestored and not fresh.sessionRestored
                AssertBuild(fresh)
                assert not activated
            finally:
                fresh.close()
                fresh.deleteLater()
                QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    print("Startup/replacement use Build; cancelled/failed opens and saves preserve Export; successful opens stop its worker")


if __name__ == "__main__":
    Main()
