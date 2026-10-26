"""Activity persistence, journal restoration, branches, expiry and live browsing."""
import copy
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from fixtures.parity_examples import ExampleWindow
from planner_app.models import Wall
from planner_app.project_codec import DecodeProject, EncodeScene


def Main():
    with ExampleWindow() as (main, folder):
        v, log = main.viewport, main.activityLog
        point = QtCore.QPointF
        clean = main.BuildProjectData()
        assert not log.entries and "activityLog" not in clean
        assert main.menuButtons["Activity Log"] is main.activityLogButton
        before = v.CaptureState()
        wall = Wall(point(), point(2000, 0), 200)
        v.walls.append(wall)
        v.RecordEdit(before)
        created = log.entries[-1]
        assert created["summary"] == "Created Wall #0001" and created["time"]
        for delta in (point(100, 200), point(300, 400)):
            before = v.CaptureState()
            wall.firstVertex += delta
            wall.secondVertex += delta
            v.RecordEdit(before)
        moved = log.entries[-1]
        final = EncodeScene(v)
        assert moved["summary"] == "Moved Wall #0001"
        main.activityLogButton.click()
        window = log.window
        assert window.isVisible() and not window.isModal()
        assert log.Restore(created) and wall.firstVertex == point()
        assert len(v.redoHistory) == 2 and log.Position(created)[1] == log.Position(created)[2]
        assert log.Restore(moved) and EncodeScene(v) == final
        window.searchField.setText("Created Wall")
        assert window.proxy.rowCount() >= 1
        window.searchField.clear()
        window.table.selectRow(0)
        assert window.restoreButton.isEnabled()
        window.restoreButton.click()
        assert wall.firstVertex == point()
        saved = folder / "activity.plan"
        assert main.SaveProject(saved) and main.OpenProject(saved)
        restoredMove = next(entry for entry in log.entries if entry["id"] == moved["id"])
        assert log.Position(restoredMove) is not None and log.Restore(restoredMove)
        assert EncodeScene(v) == final
        # The old branch remains readable after a new edit discards its redo.
        assert log.Restore(log.entries[0])
        wall = v.walls[0]
        before = v.CaptureState()
        wall.secondVertex += point(500, 0)
        v.RecordEdit(before)
        assert not v.redoHistory and log.Position(restoredMove) is None
        assert any(entry["id"] == moved["id"] for entry in log.entries)
        count = len(log.entries)
        v.ShowClipboardError("Cannot paste here: objects overlap or an opening has no suitable wall.")
        v.ShowClipboardError("Cannot paste here: objects overlap or an opening has no suitable wall.")
        assert len(log.entries) == count + 1 and log.entries[-1]["kind"] == "Blocked action"
        v.ShowClipboardError("Startup file saved.", isError = False)
        assert log.entries[-1]["kind"] == "Notice"
        # Bounded undo never truncates the descriptive log.
        v.historyLimit = 2
        for index in range(4):
            before = v.CaptureState()
            wall.firstVertex += point(100, 0)
            wall.secondVertex += point(100, 0)
            v.RecordEdit(before)
        assert len(v.undoHistory) == 2 and log.Position(created) is None
        assert len(log.entries) > 2
        # Rapid coalesced edits update one row and its live history link.
        before = v.CaptureState()
        wall.firstVertex += point(10, 0)
        wall.secondVertex += point(10, 0)
        v.RecordEdit(before, coalesceKey = "activity-test")
        count, entryId = len(log.entries), log.entries[-1]["id"]
        before = v.CaptureState()
        wall.firstVertex += point(10, 0)
        wall.secondVertex += point(10, 0)
        v.RecordEdit(before, coalesceKey = "activity-test")
        assert len(log.entries) == count and log.entries[-1]["id"] == entryId
        assert log.Position(log.entries[-1]) is not None
        # Export restoration is independent from scene restoration.
        scene = EncodeScene(v)
        panel = main.exportPanel
        main.sidebarTabs.setCurrentWidget(panel)
        panel.showGridField.setChecked(not panel.showGridField.isChecked())
        firstExport = next(entry for entry in reversed(log.entries) if entry["kind"] == "Export")
        firstUnits = panel.unitsField.currentText()
        panel.unitsField.setCurrentText("Inches" if firstUnits != "Inches" else "Centimeters")
        assert log.Restore(firstExport)
        assert panel.unitsField.currentText() == firstUnits and EncodeScene(v) == scene
        assert log.entries[-1]["summary"].startswith("Restored export")
        main.sidebarTabs.setCurrentIndex(0)
        # Project replacement refreshes an already-open window without leaking rows.
        main.ApplyProject(DecodeProject(clean, v.furnishingDefinitions), None)
        assert log.window is window and not log.entries and window.model.rowCount() == 0
        # Reference edits participate in the same scene sequence.
        imagePath = folder / "reference.png"
        image = QtGui.QImage(100, 50, QtGui.QImage.Format.Format_RGB32)
        image.fill("white")
        assert image.save(str(imagePath)) and main.referenceImage.Load(imagePath)
        main.SetViewOption("editReferenceImage")
        reference = main.referenceImage
        baseline = reference.Snapshot()
        reference.fields["x"].setValue(reference.fields["x"].value() + 500)
        reference.Hide()
        referenceEntry = next(entry for entry in reversed(log.entries) if entry["anchor"] and entry["anchor"]["scope"] == "Scene")
        v.Undo()
        assert reference.Snapshot() == baseline
        assert log.Restore(referenceEntry) and reference.Snapshot() != baseline
        # Clear leaves undo intact, persists as an intentionally empty log and
        # must not backfill those retained edits on reopening.
        undoCount = len(v.undoHistory)
        with patch.object(main, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.Yes):
            window.clearButton.click()
        assert not log.entries and len(v.undoHistory) == undoCount
        assert main.SaveProject(saved) and main.OpenProject(saved) and not log.entries
        # Older project files can expose their retained journal without made-up times.
        legacy = main.BuildProjectData()
        legacy.pop("activityLog")
        main.ApplyProject(DecodeProject(legacy, v.furnishingDefinitions), saved)
        assert log.entries and all(entry["time"] is None for entry in log.entries)
        assert all(log.Position(entry) is not None for entry in log.entries)
        window.grab().save(str(Path(__file__).resolve().parents[1] / "diagnostics/activity-log.png"))
        window.close()
        QtWidgets.QApplication.processEvents()
        assert log.window is None
    print("PASS: activity window, edits, restore/redo, persisted links, expiry, branches, export/reference scopes and Clear Log")


if __name__ == "__main__":
    Main()
