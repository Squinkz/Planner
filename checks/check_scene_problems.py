"""Current-problem inspection, recovery repairs, navigation, live updates and undo."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow
from planner_app.models import Furnishing, NorthArrow, Wall, Window
from planner_app.scene_problems import FindSceneProblems
from planner_app.geometry_recovery import ActiveGeometryIssues
from planner_app.graphics.icons import UiIcon


def SelectIssue(window, obj, code):
    for tree in window.trees:
        for index in range(tree.topLevelItemCount()):
            group = tree.topLevelItem(index)
            for childIndex in range(group.childCount()):
                child = group.child(childIndex)
                issue = child.data(0, QtCore.Qt.ItemDataRole.UserRole)[0]
                if issue["object"] is obj and issue["code"] == code:
                    window.tabs.setCurrentWidget(tree)
                    tree.setCurrentItem(child)
                    window.RefreshActions()
                    return child
    raise AssertionError((obj, code, window.problems))


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        point = QtCore.QPointF
        wall = Wall(point(0, 0), point(2000, 0), 200)
        opening = Window(wall, .35, .65)
        opening.centerFraction = 1.05
        opening.geometryIssues = ("opening_bounds",)
        missing = Furnishing(v.furnishingDefinitions["null"], point(-6000, 2000))
        missing.definitionKey = "missing_stove"
        north = NorthArrow(point(5000, 5000))
        v.walls, v.windows, v.furnishings, v.labels = [wall], [opening], [missing, north], []
        v.objectGroups, v.hiddenObjects, v.hiddenObjectIds = [], [], set()
        v.EnsureObjectIds()
        v.undoHistory.clear()
        before = main.BuildProjectData(includeHistory = False)
        problems = FindSceneProblems(v)
        assert any(issue["object"] is opening and issue["code"] == "opening_bounds" and issue["repair"] for issue in problems)
        assert any(issue["object"] is missing and issue["code"] == "asset:missing_stove" for issue in problems)
        assert not any(issue["object"] is north for issue in problems)
        assert main.BuildProjectData(includeHistory = False) == before and not v.undoHistory
        assert main.menuButtons["Check for Problems…"].shortcutLabel.text() == "Alt + P"
        main.activateWindow()
        v.setFocus()
        QtWidgets.QApplication.processEvents()
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_P, QtCore.Qt.KeyboardModifier.AltModifier)
        QtWidgets.QApplication.processEvents()
        window = main.problemsWindow
        assert window.windowIcon().pixmap(32, 32).toImage() == UiIcon("report").pixmap(32, 32).toImage()
        assert main.menuButtons["Check for Problems…"].iconLabel.pixmap().toImage() == UiIcon("report").pixmap(18, 18).toImage()
        main.menuButtons["Check for Problems…"].click()
        assert main.problemsWindow is window
        assert window.isVisible() and not window.isModal() and QtWidgets.QApplication.activeModalWidget() is None
        assert {id(obj) for obj in v.problemObjects} == {id(opening), id(missing)}
        assert not v.SelectionEntries(), "Inspection should highlight without selecting every problem"
        main.ShowProblems()
        assert main.problemsWindow is window
        item = SelectIssue(window, opening, "opening_bounds")
        window.tree.itemClicked.emit(item, 0)
        assert v.SelectionEntries() == [(opening, None)] and window.isVisible()
        assert window.repairButton.text() == "Auto-Repair"
        assert "Jump to" not in [button.text() for button in window.findChildren(QtWidgets.QPushButton)]
        assert window.repairButton.isEnabled() and "Position along wall" in window.description.text()
        QtWidgets.QApplication.processEvents()
        capture = Path(__file__).resolve().parents[1] / "diagnostics" / "problem-checker-20261023.png"
        assert window.grab().save(str(capture))
        window.repairButton.click()
        assert not ActiveGeometryIssues(opening, v) and abs(opening.centerFraction - .85) < 1e-8
        assert len(v.undoHistory) == 1
        assert not any(issue["object"] is opening for issue in window.problems)
        v.Undo()
        QtTest.QTest.qWait(150)
        assert opening.centerFraction == 1.05
        assert any(issue["code"] == "opening_bounds" for issue in window.problems)
        v.Redo()
        QtTest.QTest.qWait(150)
        assert not any(issue["object"] is opening for issue in window.problems)
        SelectIssue(window, missing, "asset:missing_stove")
        assert not window.repairButton.isEnabled() and window.deleteButton.isEnabled()
        v.hiddenObjects, v.hiddenObjectIds = [missing], {id(missing)}
        v.visibility["Furnishings"] = False
        window.tree.itemClicked.emit(window.tree.currentItem(), 0)
        assert v.IsObjectVisible(missing) and v.SelectionEntries() == [(missing, None)]
        assert window.isVisible() and v.zoom <= 1
        # Deleting a listed object must not delete unrelated grouped members.
        v.objectGroups = [(missing, north)]
        v.groupModeEnabled = True
        window.deleteButton.click()
        assert missing not in v.furnishings and north in v.furnishings
        assert window.summary.text() == "No problems found." and not v.problemObjects
        v.Undo()
        QtTest.QTest.qWait(150)
        assert missing in v.furnishings and v.problemObjects
        # An ordinary canvas deletion refreshes the modeless list as well.
        main.LocateRecoveryObjects([missing], expandGroups = False)
        v.DeleteSelected()
        QtTest.QTest.qWait(150)
        assert not window.problems and window.isVisible()
        window.close()
        assert main.problemsWindow is None and not v.problemObjects
        # Existing collision and duplicate highlights are included, even without
        # recovery flags, and obey the current collision settings.
        desk = Furnishing(v.furnishingDefinitions["desk"], point())
        copy = desk.Clone()
        v.walls, v.windows, v.furnishings = [wall], [], [desk, copy]
        v.objectGroups = []
        problems = FindSceneProblems(v)
        assert any(issue["code"] == "duplicate" and issue["object"] is copy for issue in problems)
        assert any(issue["code"] == "placement" and issue["object"] is desk for issue in problems)
        v.hiddenObjects, v.hiddenObjectIds = [copy], {id(copy)}
        assert any(issue["code"] == "duplicate" and issue["object"] is copy for issue in FindSceneProblems(v))
        v.hiddenObjects, v.hiddenObjectIds = [], set()
        small = Wall(point(500, 0), point(1000, 0), 100)
        v.walls, v.furnishings = [wall, small], []
        assert any(issue["code"] == "contained" and issue["object"] is small for issue in FindSceneProblems(v))
        # A missing component belongs to its compound owner; built-in annotation
        # definitions and intentional Null placeholders are not missing assets.
        compound = dict(next(definition for definition in v.furnishingDefinitions.values() if definition.get("components")))
        compound["components"] = [dict(component) for component in compound["components"]]
        compound["components"][0]["definitionKey"] = "missing_child"
        owner = Furnishing(compound, point(10000, 10000))
        v.walls, v.furnishings = [], [owner, north, Furnishing(v.furnishingDefinitions["null"], point(-10000, 0))]
        problems = FindSceneProblems(v)
        assert any(issue["object"] is owner and issue["code"] == "asset:missing_child" for issue in problems)
        assert not any(issue["object"] is north or issue["object"] is v.furnishings[-1] for issue in problems)
        artwork = dict(v.furnishingDefinitions["desk"], assetError = "Graphic unavailable")
        badGraphic = Furnishing(artwork, point())
        v.furnishings = [badGraphic]
        assert any(issue["object"] is badGraphic and issue["code"] == "asset:desk" for issue in FindSceneProblems(v))
        # Presentation highlights do not change serialized data or cached scene
        # output. Closing the tool restores the same editing pixels.
        v.furnishings = [missing]
        v.SetSelection([])
        v.panOffset = point(600, 200)
        QtWidgets.QApplication.processEvents()
        baseline = v.grab().toImage()
        main.ShowProblems()
        highlighted = v.grab().toImage()
        assert highlighted != baseline
        # A removed list target must never make Delete act on a newer selection.
        SelectIssue(main.problemsWindow, missing, "asset:missing_stove")
        v.furnishings = [north]
        v.SetSelection([(north, None)])
        main.problemsWindow.DeleteCurrent()
        assert v.furnishings == [north]
        v.furnishings = [missing]
        v.SetSelection([])
        main.problemsWindow.close()
        assert v.grab().toImage() == baseline
    print("PASS: live scene checks, modeless menu window, missing assets/children, navigation, repairs, deletion, highlights and undo")


if __name__ == "__main__":
    Main()
