"""Issue/recovery/settings events, duplicate suppression and safe activity decoding."""
import base64
import copy
import json
import os
from pathlib import Path
import sys
import zlib
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtWidgets, QtTest
from fixtures.parity_examples import ExampleWindow
from planner_app.models import Wall
from planner_app.activity_log import DecodeActivityLog
from planner_app.project_codec import DecodeProject
from planner_app.scene_problems import FindSceneProblems, RepairPotentialIssue
from planner_app.project_recovery import RecoverProject


def Main():
    with ExampleWindow() as (main, folder):
        v, log = main.viewport, main.activityLog
        clean = main.BuildProjectData()
        point = QtCore.QPointF
        before = v.CaptureState()
        first = Wall(point(-1000, 0), point(1000, 0), 200)
        second = Wall(point(-1000, 0), point(1000, 0), 200)
        v.walls.extend([first, second])
        v.RecordEdit(before)
        duplicateData = main.BuildProjectData()
        assert main.problemsWindow is None
        QtTest.QTest.qWait(220)
        assert any(entry["kind"] == "Problem" and "Coincident wall" in entry["summary"] for entry in log.entries)
        before = v.CaptureState()
        v.walls.remove(second)
        v.RecordEdit(before)
        QtTest.QTest.qWait(220)
        assert any(entry["kind"] == "Resolution" and "Coincident wall" in entry["summary"] for entry in log.entries)
        main.ApplyProject(DecodeProject(duplicateData, v.furnishingDefinitions), None)
        QtTest.QTest.qWait(220)
        assert log.issues and main.problemsWindow is None
        main.ApplyProject(DecodeProject(clean, v.furnishingDefinitions), None)
        main.ShowSettings()
        main.settingsWindow.SetUnitsMode("Inches")
        log.FlushSettings()
        assert any(entry["kind"] == "Settings" and "units" in entry["summary"] for entry in log.entries)
        main.settingsWindow.SetUnitsMode("Millimeters")
        log.FlushSettings()
        main.settingsWindow.hide()
        point = QtCore.QPointF
        before = v.CaptureState()
        wall = Wall(point(), point(2000, 5), 200)
        v.walls.append(wall)
        v.RecordEdit(before)
        issues = FindSceneProblems(v, gridStep = 100)
        log.ObserveIssues(issues, 100)
        count = len(log.entries)
        log.ObserveIssues(issues, 100)
        assert len(log.entries) == count
        potential = next(issue for issue in issues if issue.get("potential") and issue.get("repair"))
        assert RepairPotentialIssue(v, potential)[0]
        log.RecheckIssues()
        assert any(entry["kind"] == "Resolution" and entry["summary"].startswith("Resolved") for entry in log.entries)
        # Opening/rechecking the Problems window does not repeat identical findings.
        main.ShowProblems()
        problems = main.problemsWindow
        count = len(log.entries)
        problems.Recheck()
        assert len(log.entries) == count
        before = v.CaptureState()
        wall.secondVertex = point(2000, 5)
        v.RecordEdit(before)
        problems.Recheck()
        problems.tabs.setCurrentIndex(1)
        root = next(problems.tree.topLevelItem(index) for index in range(problems.tree.topLevelItemCount())
                    if any(issue.get("repair") for issue in problems.tree.topLevelItem(index).data(0, QtCore.Qt.ItemDataRole.UserRole)))
        problems.tree.setCurrentItem(root.child(0))
        problems.IgnoreCurrent()
        assert any(entry["summary"].startswith("Ignored:") for entry in log.entries)
        problems.RestoreIgnored()
        assert log.entries[-1]["kind"] in ("Problem", "Potential issue", "Resolution")
        root = next(problems.tree.topLevelItem(index) for index in range(problems.tree.topLevelItemCount())
                    if any(issue.get("repair") for issue in problems.tree.topLevelItem(index).data(0, QtCore.Qt.ItemDataRole.UserRole)))
        problems.tree.setCurrentItem(root.child(0))
        problems.RepairCurrent()
        repair = next(entry for entry in reversed(log.entries) if entry["kind"] == "Repair")
        assert repair["summary"].startswith("Auto-repaired:") and log.Position(repair) is not None
        problems.close()
        QtWidgets.QApplication.processEvents()
        # Recovery entries are attached to the incoming project, not the previous one.
        with patch.object(main, "ShowAppMessage"):
            main.ReportRecoveredProject(folder / "damaged.plan", folder / "backup.plan", ["Restored missing visibility setting."])
        assert any(entry["kind"] == "Recovery" and entry["summary"] == "Restored missing visibility setting." for entry in log.entries)
        data = main.BuildProjectData()
        assert DecodeActivityLog(data["activityLog"])["entries"] == log.entries
        decoded = DecodeProject(data, v.furnishingDefinitions)
        assert decoded[5]["activityLog"]["entries"] == log.entries
        assert len(json.dumps(data["activityLog"])) < len(json.dumps(log.entries))
        malformed = [dict(version = 1, encoding = "zlib-base64", data = "not base64!"),
                     dict(version = True, encoding = "zlib-base64", data = data["activityLog"]["data"]),
                     dict(version = 2, encoding = "zlib-base64", data = data["activityLog"]["data"])]
        raw = DecodeActivityLog(data["activityLog"])
        for change in ({"id": True}, {"time": "yesterday"}, {"summary": ["not text"]},
                       {"anchor": {"scope": "filesystem", "edit": 1, "side": "after"}}):
            invalid = copy.deepcopy(raw)
            invalid["entries"][0].update(change)
            malformed.append(dict(version = 1, encoding = "zlib-base64",
                data = base64.b64encode(zlib.compress(json.dumps(invalid).encode())).decode()))
        for invalid in malformed:
            try:
                DecodeActivityLog(invalid)
            except ValueError:
                pass
            else:
                raise AssertionError("Malformed activity metadata accepted")
        import planner_app.activity_log as activityModule
        with patch.object(activityModule, "activityByteLimit", 1024):
            bomb = dict(version = 1, encoding = "zlib-base64",
                data = base64.b64encode(zlib.compress(b" " * 4096)).decode())
            try:
                DecodeActivityLog(bomb)
            except ValueError:
                pass
            else:
                raise AssertionError("Oversized decompressed activity data accepted")
        broken = copy.deepcopy(data)
        broken["activityLog"] = malformed[0]
        recovered, notices = RecoverProject(broken, v.furnishingDefinitions, main.defaultProjectData)
        assert recovered[5]["activityLog"] is None and "Removed invalid activity log." in notices
        # Untrusted log text is rendered as plain text; it is never executed.
        log.Add("Notice", "<script>alert('test')</script>")
        log.Show()
        window = log.window
        window.table.selectRow(window.proxy.rowCount() - 1)
        assert "<script>" in window.details.toPlainText()
        # Recovery checkpoint includes the complete compressed log, independent
        # of the normal undo retention budget.
        assert main.WriteSession(wait = True)
        session = json.loads(main.sessionPath.read_text(encoding = "utf-8"))
        assert DecodeActivityLog(session["project"]["activityLog"])["entries"] == log.entries
        # Failed Open stages an empty project before reporting errors. Its
        # application notice must survive restoration of the previous project.
        assert main.SaveProject(folder / "original.plan")
        count = len(log.entries)
        brokenPath = folder / "broken.plan"
        brokenPath.write_text("{broken", encoding = "utf-8")
        with patch.object(main, "ShowAppMessage", side_effect = lambda title, text, *args, **kwargs:
                          log.Message(title + ": " + text, kind = "Application")):
            assert not main.OpenProject(brokenPath)
        assert len(log.entries) == count + 1 and log.entries[-1]["summary"].startswith("Cannot Open Project:")
        window.close()
    print("PASS: settings, issue transitions/deduplication, recovery, checkpoint persistence and bounded safe log decoding")


if __name__ == "__main__":
    Main()
