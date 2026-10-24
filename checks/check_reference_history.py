"""Reference edits share chronological scene history, including saved journals."""
import os
import json
import copy
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow
from planner_app.models import Wall
from planner_app.project_history import DecodeHistory
from planner_app.project_codec import DecodeProject


def Main():
    with ExampleWindow() as (main, folder):
        v, reference = main.viewport, main.referenceImage
        path = Path(folder) / "reference.png"
        image = QtGui.QImage(200, 100, QtGui.QImage.Format.Format_RGB32)
        image.fill("red")
        assert image.save(str(path)) and reference.Load(path)
        assert not reference.active and not v.undoHistory
        main.SetViewOption("editReferenceImage")
        assert reference.active
        v.snapEnabled = False
        scene = v.CaptureState()
        before = reference.Snapshot()
        position = v.WorldToViewport(QtCore.QPointF(*before["center"]))
        QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, pos = position.toPoint())
        for offset in (20, 40, 60):
            QtTest.QTest.mouseMove(v, (position + QtCore.QPointF(offset, 20)).toPoint())
        QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, pos = (position + QtCore.QPointF(60, 20)).toPoint())
        moved = reference.Snapshot()
        assert moved != before and len(v.undoHistory) == 1
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier)
        assert reference.Snapshot() == before and reference.active
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier | QtCore.Qt.KeyboardModifier.ShiftModifier)
        assert reference.Snapshot() == moved
        reference.BeginPropertyDrag()
        for value in (1100, 1200, 1300):
            reference.fields["width"].setValue(value)
        reference.FinishPropertyDrag(False)
        assert len(v.undoHistory) == 2
        resized = reference.Snapshot()
        v.Undo()
        assert reference.Snapshot() == moved, {key: (moved[key], reference.state[key]) for key in moved if moved[key] != reference.state[key]}
        v.Redo()
        assert reference.Snapshot() == resized
        reference.BeginPropertyDrag()
        reference.fields["x"].setValue(500)
        reference.FinishPropertyDrag(True)
        assert reference.Snapshot() == resized and len(v.undoHistory) == 2
        reference.opacitySlider.setSliderDown(True)
        for value in (30, 40, 70):
            reference.opacitySlider.setValue(value)
        reference.opacitySlider.setSliderDown(False)
        assert len(v.undoHistory) == 3
        v.Undo()
        assert reference.Snapshot() == resized
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Right)
        assert reference.state["center"] != resized["center"]
        v.Undo()
        assert reference.Snapshot() == resized
        reference.fields["angle"].setValue(25)
        assert not v.redoHistory
        rotated = reference.Snapshot()
        reference.calibration.Start()
        reference.calibration.points = [QtCore.QPointF(0, 0), QtCore.QPointF(1000, 0)]
        assert reference.calibration.Apply(2000) is None
        reference.calibration.Stop()
        v.Undo()
        assert reference.Snapshot() == rotated
        reference.Hide()
        beforeScene = v.CaptureState()
        wall = Wall(QtCore.QPointF(0, -2000), QtCore.QPointF(3000, -2000), 200)
        v.walls.append(wall)
        v.RecordEdit(beforeScene)
        v.Undo()
        assert v.CaptureState() == scene and reference.Snapshot() == rotated
        v.Undo()
        assert reference.Snapshot() == resized and not reference.active
        v.Redo()
        assert reference.Snapshot() == rotated and not reference.active
        v.Redo()
        assert any(obj is wall for obj in v.walls)
        v.Undo()
        count = len(v.undoHistory)
        main.SetViewOption("referenceImage")
        assert not reference.state["visible"] and not reference.active
        main.SetViewOption("referenceImage")
        assert reference.state["visible"] and not reference.active and len(v.undoHistory) == count
        # Real checkbox clicks must not also invoke the row's edit action.
        tree, item = main.visibilityTree, main.referenceImageItem
        index = tree.indexFromItem(item)
        option = QtWidgets.QStyleOptionViewItem()
        tree.itemDelegate().initStyleOption(option, index)
        option.rect, option.widget = tree.visualRect(index), tree
        checkRect = tree.style().subElementRect(QtWidgets.QStyle.SubElement.SE_ItemViewItemCheckIndicator, option, tree)
        for enabled in (False, True):
            QtTest.QTest.mouseClick(tree.viewport(), QtCore.Qt.MouseButton.LeftButton, pos = checkRect.center())
            assert reference.state["visible"] == enabled and not reference.active
        row = tree.visualItemRect(item)
        QtTest.QTest.mouseClick(tree.viewport(), QtCore.Qt.MouseButton.LeftButton, pos = QtCore.QPoint(row.left() + 90, row.center().y()))
        assert reference.active and len(v.undoHistory) == count
        v.Undo()
        assert reference.state["angle"] == resized["angle"] and reference.state["visible"]
        assert v.CaptureState() == scene
        main.ShowHeaderMenu("Edit")
        assert main.menuButtons["Redo"].isEnabled()
        main.headerMenus["Edit"].hide()
        previous = reference.Snapshot()
        image.fill("blue")
        assert image.save(str(path)) and reference.Load(path)
        assert reference.active and reference.image.pixelColor(0, 0) == QtGui.QColor("blue")
        v.Undo()
        assert reference.Snapshot() == previous and reference.image.pixelColor(0, 0) == QtGui.QColor("red")
        v.Redo()
        assert reference.image.pixelColor(0, 0) == QtGui.QColor("blue")
        reference.Hide()
        beforeScene = v.CaptureState()
        v.walls.append(wall)
        v.RecordEdit(beforeScene)
        project = Path(folder) / "reference-history.plan"
        data = main.BuildProjectData()
        assert len(DecodeHistory(data["history"], data["settings"], v.furnishingDefinitions, v)["undo"]) == len(v.undoHistory)
        assert main.SaveProject(project)
        savedData = json.loads(project.read_text(encoding = "utf-8"))
        assert len(DecodeHistory(savedData["history"], savedData["settings"], v.furnishingDefinitions, v)["undo"]) == len(v.undoHistory)
        assert len(DecodeProject(savedData, v.furnishingDefinitions)[5]["history"]["undo"]) == len(v.undoHistory), "Project decoder dropped mixed history"
        for field, value in (("width", -1), ("opacity", 2), ("data", "invalid")):
            damaged = copy.deepcopy(savedData)
            entry = next(edit for edit in reversed(damaged["history"]["undo"]) if "referenceImage" in edit)
            entry["referenceImage"]["changes"][field] = [value, reference.state[field]]
            decoded = DecodeProject(damaged, v.furnishingDefinitions)
            assert decoded[5]["history"] == {"undo": [], "redo": []} and len(decoded[0]) == len(v.walls), field
        assert main.OpenProject(project)
        assert not reference.active and reference.image.pixelColor(0, 0) == QtGui.QColor("blue")
        v.Undo()
        assert not v.walls, (len(v.undoHistory), len(v.redoHistory), [type(edit).__name__ for edit in v.undoHistory])
        v.Undo()
        assert reference.Snapshot() == previous and reference.image.pixelColor(0, 0) == QtGui.QColor("red")
        v.Redo()
        v.Redo()
        assert len(v.walls) == 1 and reference.image.pixelColor(0, 0) == QtGui.QColor("blue")
    print("Reference history: shared scene chronology, closed controls, gestures, cancellation, replacement, saved journals and visibility passed")


if __name__ == "__main__":
    Main()
