"""Metadata recovery is backed up, unsaved, reversible and geometry preserving."""
import copy
from contextlib import redirect_stderr
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Wall
from furnishings import Furnishing
from planner_app.project_codec import DecodeProject
from planner_app.project_recovery import RecoverProject
from planner_app.export_plan import RenderPlan


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    v.walls = [Wall(QtCore.QPointF(0, 0), QtCore.QPointF(2000, 0)), Wall(QtCore.QPointF(0, 2000), QtCore.QPointF(2000, 2000))]
    v.windows, v.furnishings, v.labels, v.objectGroups, v.hiddenObjects = [], [], [], [], []
    v.EnsureObjectIds()
    template = main.BuildProjectData(includeHistory = False)
    defaults = main.defaultProjectData
    definitions = dict(v.furnishingDefinitions)
    original = copy.deepcopy(template)
    decoded, notices = RecoverProject(template, definitions, defaults)
    assert not notices and template == original
    assert decoded[5]["unitsMode"] == template["settings"]["unitsMode"]
    damaged = copy.deepcopy(template)
    damaged["settings"]["unitsMode"] = "Bad Units"
    damaged["settings"]["lineworkSettings"]["baseWidth"] = -5
    damaged["settings"]["snap"] = {name: False for name in damaged["settings"]["snap"]}
    damaged["settings"]["snapEnabled"] = True
    damaged["settings"]["exportSettings"] = {"unknownOption": True, "dpi": -1, "scale": 250, "canvasColor": "bad color"}
    damaged["settings"]["canvasTheme"] = "Removed Theme"
    damaged["view"] = {"zoom": 0, "pan": "bad"}
    damaged["ui"]["mainSplitter"] = "bad"
    records = damaged["scene"]["objects"]
    records[1]["id"] = records[0]["id"]
    records[0]["material"] = "Removed Material"
    records[0]["measurementHidden"] = 1
    damaged["scene"]["groups"] = [[0, 1, 1, 999], [0, 1]]
    damaged["scene"]["hidden"] = [1, 1, "bad", 999]
    damaged["history"] = {"format": "Planner Changes", "version": 1, "undo": "bad", "redo": []}
    decoded, notices = RecoverProject(damaged, definitions, defaults)
    assert len(notices) >= 10
    assert decoded[5]["exportSettings"] == {"scale": 250}
    assert not decoded[5]["snapEnabled"]
    assert decoded[0][0].material == "Generic" and decoded[0][0].originalMaterial == "Removed Material"
    assert decoded[0][0].objectId != decoded[0][1].objectId
    assert len(decoded[3]) == 1 and decoded[4] == [decoded[0][1]]
    assert "history" not in decoded[5]
    for obj, record in zip(decoded[0], records):
        assert [obj.firstVertex.x(), obj.firstVertex.y()] == record["first"]
        assert [obj.secondVertex.x(), obj.secondVertex.y()] == record["second"]
        assert obj.width == record["width"]
    # Missing definitions retain the original lookup key while displaying Null.
    missing = copy.deepcopy(template)
    missing["scene"]["objects"] = [{"type": "Furnishing", "id": 1, "definition": "Gone", "first": [0, 0], "second": [0, 1000], "width": 800}]
    missing["furnishingDefinitions"] = {"Gone": {"svg": "<broken"}}
    decoded, notices = RecoverProject(missing, definitions, defaults)
    assert decoded[2][0].definitionKey == "Gone" and decoded[2][0].width == 800
    assert notices and decoded[2][0].definition["graphicData"]
    missing.pop("furnishingDefinitions")
    decoded, notices = RecoverProject(missing, definitions, defaults)
    assert decoded[2][0].definitionKey == "Gone" and decoded[2][0].definition["key"] == "null" and notices
    assert any("Gone: 1 object affected" in notice for notice in notices)
    # Rendering may run repeatedly for either preview format. Missing assets
    # are reported on project recovery, not re-announced by each render.
    for outputFormat in ("png", "svg", "png", "svg"):
        messages = io.StringIO()
        with redirect_stderr(messages):
            result = RenderPlan("Missing.plan", 30, (-1000, -1000, 3000, 3000),
                                outputFormat = outputFormat, projectData = missing, applyTheme = False)
        assert "missing furnishings" not in messages.getvalue().lower()
        if outputFormat == "png":
            assert not result.isNull()
        else:
            assert b"<svg" in result
    assert missing["scene"]["objects"][0]["definition"] == "Gone"
    multipleMissing = copy.deepcopy(missing)
    multipleMissing["scene"]["objects"].append(dict(multipleMissing["scene"]["objects"][0], id = 2,
                                                   first = [2000, 0], second = [2000, 1000]))
    decoded, notices = RecoverProject(multipleMissing, definitions, defaults)
    assert sum("Missing furnishing Gone: 2 objects affected" in notice for notice in notices) == 1
    remainingMissing = copy.deepcopy(multipleMissing)
    remainingMissing["scene"]["objects"].pop()
    assert any("Gone: 1 object affected" in notice for notice in RecoverProject(remainingMissing, definitions, defaults)[1])
    remainingMissing["scene"]["objects"].clear()
    assert not RecoverProject(remainingMissing, definitions, defaults)[1]
    # Damaged decomposition metadata does not destroy usable embedded artwork.
    embedded = copy.deepcopy(template)
    null = definitions["null"]
    svg = (null.get("graphicData") or Path(null["imagePath"]).read_bytes()).decode("utf-8-sig")
    record = {"name": "Portable", "category": "Miscellaneous", "keywords": [], "svg": svg, "width": 1000, "length": 1000}
    embedded["furnishingDefinitions"] = {"A": dict(record, components = [{"definition": "A"}], compoundCenter = [0, 0])}
    decoded, notices = RecoverProject(embedded, definitions, defaults)
    assert "components" not in decoded[5]["embeddedFurnishings"]["A"] and notices
    embedded["furnishingDefinitions"]["A"] = dict(record, keywords = [3, "valid"], name = None)
    decoded, notices = RecoverProject(embedded, definitions, defaults)
    assert decoded[5]["embeddedFurnishings"]["A"]["graphicData"].decode("utf-8") == svg
    assert decoded[5]["embeddedFurnishings"]["A"]["keywords"] == ["valid"]
    child = {"definition": "Missing Child", "x": 0, "y": 0, "angle": 0, "width": 500, "length": 500, "zIndex": 0}
    embedded["furnishingDefinitions"]["A"] = dict(record, components = [child], compoundCenter = [0, 0])
    decoded, notices = RecoverProject(embedded, definitions, defaults)
    assert any("Missing Child" in notice for notice in notices)
    assert decoded[5]["embeddedFurnishings"]["A"]["components"][0]["definitionKey"] == "Missing Child"
    assert any("Missing Child: 1 reference in compound definitions" in notice for notice in notices)
    embedded["furnishingDefinitions"]["A"]["components"].append(dict(child, x = 1000))
    assert any("Missing Child: 2 references in compound definitions" in notice
               for notice in RecoverProject(embedded, definitions, defaults)[1])
    # Corrupt or incompatible undo data is discarded without blocking geometry.
    for history in ({"format": "Old", "version": 0}, {"format": "Planner Changes", "version": 1, "undo": "bad", "redo": []}):
        test = copy.deepcopy(template)
        test["history"] = history
        decoded, notices = RecoverProject(test, definitions, defaults)
        assert decoded[5]["history"] == {"undo": [], "redo": []} and notices
    # Geometry is deliberately not repaired.
    for field, value in (("width", 0), ("second", [0, 0]), ("type", "Unknown Object")):
        test = copy.deepcopy(template)
        test["scene"]["objects"][0][field] = value
        try:
            RecoverProject(test, definitions, defaults)
        except (ValueError, KeyError):
            pass
        else:
            raise AssertionError("Geometry was repaired or accepted")
    messages = []
    def Message(*args, **kwargs):
        messages.append((args, kwargs))
        return QtWidgets.QMessageBox.StandardButton.Discard
    with tempfile.TemporaryDirectory() as directory, patch.object(main, "ShowAppMessage", side_effect = Message):
        folder = Path(directory)
        main.sessionPath = folder / "session.json"
        missingCountPath = folder / "Missing counts.plan"
        missingCountPath.write_text(json.dumps(multipleMissing))
        assert main.OpenProject(missingCountPath)
        report = messages[-1][1]["informativeText"]
        assert "Gone: 2 objects affected" in report
        assert "reported again until" in report
        path = folder / "Damaged.plan"
        originalBytes = b'\xef\xbb\xbf' + json.dumps(damaged).encode('utf-8')
        path.write_bytes(originalBytes)
        assert main.OpenProject(path)
        assert main.projectPath is None and main.projectDirty and "Recovered" in main.windowTitle()
        assert main.recoverySourcePath == path and main.recoveryBackupPath.read_bytes() == originalBytes
        with patch.object(main, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.Cancel) as prompt:
            assert not main.ConfirmProjectReplacement()
            assert prompt.call_args.args[1] == "Save changes to Damaged (Recovered) before continuing?"
        assert path.read_bytes() == originalBytes
        assert messages[-1][0][0] == "Project Recovered" and "detailedText" in messages[-1][1]
        assert main.WriteSession(wait = True)
        checkpoint = json.loads(main.sessionPath.read_text())
        assert checkpoint["projectRecovery"]["source"] == str(path)
        sourcePath, backupPath = main.recoverySourcePath, main.recoveryBackupPath
        main.recoverySourcePath = main.recoveryBackupPath = None
        main.RestoreSession()
        assert main.projectPath is None and main.projectDirty
        assert main.recoverySourcePath == sourcePath and main.recoveryBackupPath == backupPath
        with patch.object(main, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.Cancel) as prompt:
            assert not main.ConfirmProjectReplacement()
            assert prompt.call_args.args[1] == "Save changes to Damaged (Recovered) before continuing?"
        repairedPath = folder / "Damaged recovered.plan"
        with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value = ("", "")) as saveDialog:
            assert not main.SaveProject()
            assert saveDialog.call_args[0][2] == str(path)
        assert main.recoverySourcePath == path and main.projectDirty
        assert path.read_bytes() == originalBytes
        with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value = (str(repairedPath), "")) as saveDialog:
            assert main.SaveProject()
            assert saveDialog.call_args[0][2] == str(path)
        assert path.read_bytes() == originalBytes and not main.projectDirty
        assert main.recoverySourcePath is None and main.recoveryBackupPath is None
        saved = json.loads(repairedPath.read_text())
        assert saved["scene"]["objects"][0]["originalMaterial"] == "Removed Material"
        DecodeProject(saved, definitions)
        assert not RecoverProject(saved, definitions, defaults)[1]
        assert main.OpenProject(path)
        originalBackup = main.recoveryBackupPath
        with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value = (str(path), "")):
            assert main.SaveProject()
        assert main.projectPath == path and not main.projectDirty
        assert main.recoverySourcePath is None and "(Recovered)" not in main.windowTitle()
        assert originalBackup.read_bytes() == originalBytes
        assert main.OpenProject(path)
        assert main.projectPath == path and not main.projectDirty and main.recoverySourcePath is None
        # Restore the damaged fixture for the remaining recovery failure cases.
        path.write_bytes(originalBytes)
        assert main.OpenProject(repairedPath)
        # Refuse to install repaired data if its backup cannot be written.
        before = main.BuildProjectData()
        with patch("pathlib.Path.mkdir", side_effect = OSError("No space")):
            assert not main.OpenProject(path)
        assert main.BuildProjectData() == before and main.projectPath == repairedPath
        # An unexpected installation error restores the prior project.
        cleanPath = folder / "Clean.plan"
        cleanPath.write_text(json.dumps(template))
        apply = main.ApplyProject
        calls = []
        def Apply(decoded, target):
            calls.append(target)
            if len(calls) == 1:
                v.walls = []
                raise RuntimeError("Simulated renderer error")
            return apply(decoded, target)
        with patch.object(main, "ApplyProject", side_effect = Apply):
            assert not main.OpenProject(cleanPath)
        assert main.projectPath == repairedPath and main.BuildProjectData() == before
        # Startup templates use the same metadata repair and backup policy.
        main.startupPath = path
        main.LoadStartupProject()
        assert len(v.walls) == 2 and main.projectPath is None and main.projectDirty
        assert main.recoveryBackupPath.read_bytes() == originalBytes
        # Embedded recovery graphics must survive a session checkpoint too.
        missingPath = folder / "Missing.plan"
        missing["furnishingDefinitions"] = {"Gone": {"svg": "<broken"}}
        missingPath.write_text(json.dumps(missing))
        assert main.OpenProject(missingPath)
        assert main.WriteSession(wait = True)
        checkpoint = json.loads(main.sessionPath.read_text())
        assert "Gone" in checkpoint["project"]["furnishingDefinitions"]
        main.RestoreSession()
        assert v.furnishings[0].definitionKey == "Gone" and v.furnishings[0].definition["isEmbedded"]
    # Actual modal layout: minimum size must survive QMessageBox's own sizing.
    def CloseMessage():
        dialog = app.activeModalWidget()
        assert dialog.width() >= 440 and dialog.height() >= 180, dialog.size()
        dialog.done(int(QtWidgets.QMessageBox.StandardButton.Ok))
    QtCore.QTimer.singleShot(0, CloseMessage)
    with patch.object(QtWidgets.QMessageBox, "exec", QtWidgets.QDialog.exec):
        main.ShowAppMessage("Cannot Open Project", "Could not open spam.plan.", "error", informativeText = "Invalid embedded furnishing key.")
    main.close()
    print("PASS: settings/assets/materials/IDs/groups/history recovery, exact backup, unsaved Save As, geometry rejection, rollback and dialog size.")


if __name__ == "__main__":
    Main()
