"""Manual stair sizing, property widgets, history, clipboard and project recovery."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Stair
from planner_app.project_codec import DecodeProject
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    app.setStyle("Fusion")
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    v = main.viewport
    v.unitsMode = "Adaptive Metric"
    point = QtCore.QPointF
    stair = Stair(point(), point(2200, 0))
    v.walls = [stair]
    v.SetSelection([(stair, None)])
    main.RefreshProperties()
    assert stair.autosize and stair.stepCount == 8 and stair.stepSize == 275
    assert main.stairStepWidgets["stepCount"].currentIndex() == 0
    main.autosizeField.setChecked(False)
    assert not stair.autosize and stair.stepCount == 8 and stair.stepSize == 275
    assert main.stairStepWidgets["stepCount"].currentIndex() == 1
    main.propertyFields["stepCount"].setValue(10)
    assert stair.stepCount == 10 and stair.stepSize == 220
    v.Undo()
    assert not stair.autosize and stair.stepCount == 8
    v.Redo()
    assert stair.stepCount == 10
    main.EditProperty("length", 3)
    assert stair.stepCount == 10 and stair.stepSize == 300
    main.propertyFields["stepSize"].setValue(27)
    assert stair.stepCount == 11 and abs(stair.stepSize - 3000 / 11) < 1e-8
    assert main.propertyFields["stepSize"].value() == 27.27
    main.autosizeField.setChecked(True)
    assert stair.autosize and stair.stepCount == 11
    main.EditProperty("length", 2.2)
    assert stair.stepCount == 8 and stair.stepSize == 275
    # Connected stairs count landings and use the trimmed tread run.
    other = Stair(point(2200, 0), point(2200, 2200))
    v.walls.append(other)
    v.EnsureObjectIds()
    main.RefreshProperties()
    count, size = stair.stepCount, stair.stepSize
    main.autosizeField.setChecked(False)
    assert stair.stepCount == count and stair.stepSize == size
    main.EditProperty("stepCount", 6)
    assert stair.stepCount == 6 and stair.StepLayout()[0] == 5
    assert stair.stepSize == 1700 / 5
    main.EditProperty("stepSize", 30)
    assert stair.stepCount == 7 and abs(stair.stepSize - 1700 / 6) < 1e-8
    # Editing both stairs applies atomically, with a mixed Autosize indicator.
    v.SetSelection([(stair, None), (other, None)])
    main.RefreshProperties()
    assert main.autosizeField.checkState() == QtCore.Qt.CheckState.PartiallyChecked
    main.EditStairAutosize(False)
    assert not stair.autosize and not other.autosize
    main.EditProperty("stepCount", 9)
    assert stair.stepCount == other.stepCount == 9
    v.Undo()
    assert stair.stepCount == 7
    v.Redo()
    assert stair.stepCount == other.stepCount == 9
    app.processEvents()
    main.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "stair-autosize.png"))
    v.SetSelection([(stair, None)])
    v.zoom = .25
    main.snapButton.setChecked(False)
    try:
        assert v.CopySelection() and v.PasteSelection(v.WorldToViewport(point(6000, 0)))
    finally:
        app.clipboard().clear()
        app.processEvents()
    copied = v.selectedWall
    assert copied is not stair and not copied.autosize and copied.manualStepCount == 9
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "Stairs.plan"
        assert main.SaveProject(path)
        assert main.NewProject() and main.OpenProject(path)
        assert all(not obj.autosize and obj.manualStepCount == 9 for obj in v.walls)
        legacy = main.BuildProjectData()
        for record in legacy["scene"]["objects"]:
            record.pop("autosize")
            record.pop("manualStepCount")
        assert all(obj.autosize for obj in DecodeProject(legacy, v.furnishingDefinitions)[0])
    main.close()
    restored = MainWindow()
    assert all(not obj.autosize and obj.manualStepCount == 9 for obj in restored.viewport.walls)
    restored.close()
    print("PASS: autosize/manual controls, quantized size, fixed count on resize, landing counts, bulk edits, undo, copy and recovery.")


if __name__ == "__main__":
    Main()
