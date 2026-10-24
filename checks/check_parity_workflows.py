"""Replay documented editing workflows; --record explicitly refreshes checkpoints."""
import json
import os
import sys
from itertools import count
from pathlib import Path

workspace = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(workspace / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner_app import models
from planner_app.project_codec import EncodeScene
from fixtures.parity_examples import ExampleWindow, InstallScene, WorkflowState, CompareExamples, referenceDirectory


def RunWorkflow(name):
    models.objectIdCounter = count(1)
    states = []
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.unitsMode = "Millimeters"
        # These authored examples use 240 mm walls, independently of tool presets.
        v.newWallWidth = 240
        main.snapButton.setChecked(False)
        main.connectedOptions["vertices"].setChecked(False)
        main.connectedOptions["objects"].setChecked(False)
        point = QtCore.QPointF
        if name == "room-to-export":
            # Real viewport pointer events: four wall drawing gestures.
            corners = [point(-2000, -1500), point(2000, -1500), point(2000, 1500), point(-2000, 1500)]
            for first, second in zip(corners, corners[1:] + corners[:1]):
                start, finish = v.WorldToViewport(first).toPoint(), v.WorldToViewport(second).toPoint()
                right = QtCore.Qt.MouseButton.RightButton
                QtTest.QTest.mousePress(v, right, pos = start)
                event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, point(finish), point(v.mapToGlobal(finish)),
                                         QtCore.Qt.MouseButton.NoButton, right, QtCore.Qt.KeyboardModifier.NoModifier)
                QtWidgets.QApplication.sendEvent(v, event)
                QtTest.QTest.mouseRelease(v, right, pos = finish)
            assert len(v.walls) == 4 and len(v.undoHistory) == 4
            states.append(("draw-room", WorkflowState(main)))
            # Exercise the viewport's actual MIME drop adapter, without an OS drag loop.
            for kind, value, location in (("door", "Door", point(0, -1500)),
                                           ("silled-window", "SilledWindow", point(0, 1500)),
                                           ("furnishing", "desk", point(-900, -400)),
                                           ("furnishing", "chair_dining", point(900, -400))):
                mime = QtCore.QMimeData()
                mime.setData("application/x-planner-" + kind, value.encode("utf-8"))
                drop = QtGui.QDropEvent(v.WorldToViewport(location), QtCore.Qt.DropAction.CopyAction, mime,
                                        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
                v.dropEvent(drop)
                assert drop.isAccepted(), kind
            assert len(v.windows) == 2 and len(v.furnishings) == 2
            states.append(("place-openings-and-furniture", WorkflowState(main)))
            v.SetSelection([(obj, None) for obj in v.furnishings])
            v.GroupSelection()
            assert len(v.objectGroups) == 1
            assert v.MoveSpecial(100, 200, 15) is None
            moved = EncodeScene(v)
            states.append(("group-and-transform", WorkflowState(main)))
            v.Undo()
            assert EncodeScene(v) != moved
            states.append(("undo-transform", WorkflowState(main)))
            v.Redo()
            assert EncodeScene(v) == moved
            states.append(("redo-transform", WorkflowState(main)))
        elif name == "attachment-lifecycle":
            wall = models.Wall(point(-2000, 0), point(2000, 0), 240)
            door = models.Door(wall, .1, .3)
            fireplace = models.Fireplace(wall, .6, .9)
            InstallScene(main, [wall, door, fireplace])
            assert abs(fireplace.depth - 500) < 1e-8
            v.SetSelection([(wall, None)])
            states.append(("attached-objects", WorkflowState(main)))
            v.HideSelection()
            assert len(v.hiddenObjects) == 3
            states.append(("hide-parent-and-children", WorkflowState(main)))
            v.Undo()
            assert not v.hiddenObjects
            v.SetSelection([(wall, None)])
            v.DeleteSelected()
            assert not v.walls and not v.windows
            states.append(("delete-parent-and-children", WorkflowState(main)))
            v.Undo()
            assert len(v.walls) == 1 and len(v.windows) == 2
            v.SetSelection([(wall, None)])
            main.EditProperty("width", 800)
            assert wall.width == 800 and fireplace.depth == 800
            states.append(("thicker-parent-fits-fireplace", WorkflowState(main)))
            v.Undo()
            assert wall.width == 240 and abs(fireplace.depth - 500) < 1e-8
            states.append(("undo-parent-width", WorkflowState(main)))
        else:
            raise AssertionError(name)

        # Both workflows cross the real project save/reopen boundary.
        before = EncodeScene(v)
        path = folder / "workflow.plan"
        main.SaveProjectAs(str(path))
        assert path.is_file() and not main.projectDirty
        main.NewProject()
        assert not v.walls
        main.OpenProject(str(path))
        assert EncodeScene(v) == before
        states.append(("save-new-reopen", WorkflowState(main)))
        project = json.loads(path.read_text(encoding = "utf-8"))

        # Export history must never undo or delete the saved building.
        savedGrid = v.showGrid
        main.sidebarTabs.setCurrentWidget(main.exportPanel)
        panel = main.exportPanel
        panel.ResetExportHistory()
        sceneUndo = len(v.undoHistory)
        panel.SetOverride("showGrid", not savedGrid)
        panel.RecordExportHistory()
        assert v.showGrid != savedGrid and len(panel.exportUndoHistory) == 1
        states.append(("export-override", WorkflowState(main)))
        v.Undo()
        assert v.showGrid == savedGrid and EncodeScene(v) == before and len(v.undoHistory) == sceneUndo
        states.append(("export-undo", WorkflowState(main)))
        v.Redo()
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Delete)
        assert EncodeScene(v) == before and len(v.undoHistory) == sceneUndo
        states.append(("export-redo-and-blocked-delete", WorkflowState(main)))
        main.sidebarTabs.setCurrentIndex(0)
        assert v.showGrid == savedGrid
        states.append(("return-to-build", WorkflowState(main)))
    return {"workflow": name, "checkpoints": [{"id": key, "state": value} for key, value in states]}, project


def Main():
    target = referenceDirectory / "workflows"
    record = "--record" in sys.argv
    if record:
        target.mkdir(exist_ok = True)
    count = 0
    for name in ("room-to-export", "attachment-lifecycle"):
        actual, project = RunWorkflow(name)
        path = target / (name + ".json")
        if record:
            path.write_text(json.dumps(actual, indent = 2, ensure_ascii = False), encoding = "utf-8", newline = "\n")
            (target / (name + ".plan")).write_text(json.dumps(project, indent = 2, ensure_ascii = False), encoding = "utf-8", newline = "\n")
        else:
            CompareExamples(actual, json.loads(path.read_text(encoding = "utf-8")), name)
        count += len(actual["checkpoints"])
    print(f"{'Recorded' if record else 'PASS:'} 2 workflows, {count} checkpoints with independent behavioral assertions")


if __name__ == "__main__":
    Main()
