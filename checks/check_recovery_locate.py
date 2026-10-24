"""Recovery entries locate individual or grouped missing furnishings."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets, QtTest
from planner import MainWindow
from furnishings import Furnishing
from planner_app.models import NorthArrow
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    v.walls, v.windows, v.labels, v.objectGroups = [], [], [], []
    first = Furnishing(v.furnishingDefinitions["null"])
    second = Furnishing(v.furnishingDefinitions["null"])
    for obj, x in ((first, -20000), (second, 10000)):
        obj.definitionKey = "Missing Stove"
        obj.firstVertex = QtCore.QPointF(x, 3000)
        obj.secondVertex = QtCore.QPointF(x, 4000)
        obj.width = 600
    north = NorthArrow(QtCore.QPointF(0, 0))
    v.furnishings = [north]
    assert north.definition["key"] not in v.furnishingDefinitions
    assert main.RecoveryObjectEntries() == {}, 'Built-in north arrows are not missing catalog assets'
    v.furnishings = [first, second, north]
    assert main.RecoveryObjectEntries() == {"Missing Stove": [first, second]}
    v.EnsureObjectIds()
    original = [(QtCore.QPointF(obj.firstVertex), QtCore.QPointF(obj.secondVertex), obj.width) for obj in v.furnishings]
    v.hiddenObjects = [second]
    v.hiddenObjectIds = {id(second)}
    v.visibility["Furnishings"] = False
    errors = []

    def ClickEntry(individual):
        message = main.recoveryWindow
        try:
            tree = message.findChild(QtWidgets.QTreeWidget, "recoveryObjects")
            assert tree is not None and tree.topLevelItemCount() == 1
            parent = tree.topLevelItem(0)
            assert parent.text(0) == "Missing Stove — 2 objects"
            assert parent.childCount() == 2
            if not individual:
                message.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "recovery-locate.png"))
            for childIndex in (None, 0, 1 if individual else None):
                parent = tree.topLevelItem(0)
                item = parent if childIndex is None else parent.child(childIndex)
                tree.scrollToItem(item)
                expected = {id(obj) for obj in item.data(0, QtCore.Qt.ItemDataRole.UserRole)}
                QtTest.QTest.mouseClick(tree.viewport(), QtCore.Qt.MouseButton.LeftButton,
                                       pos = tree.visualItemRect(item).center())
                app.processEvents()
                assert message.isVisible() and app.activeModalWidget() is None
                assert {id(obj) for obj, index in v.SelectionEntries()} == expected
        except Exception as error:
            errors.append(error)
        finally:
            message.reject()

    repairs = ["Missing furnishing Missing Stove: 2 objects affected."]
    for individual in (False, True):
        main.ReportRecoveredProject(Path("Missing.plan"), Path("Backup.plan"), repairs)
        app.processEvents()
        ClickEntry(individual)
        assert not errors, errors
        expected = {id(second)} if individual else {id(first), id(second)}
        assert {id(obj) for obj, index in v.SelectionEntries()} == expected, (individual, v.selection, v.selectedWall, v.exportOverlay.active)
        assert v.IsObjectVisible(second)
        if individual:
            assert main.selectionLabel.text() == f"Missing Stove (missing) (#{second.objectId:04d})"
        else:
            assert main.selectionLabel.text() == "2 Missing Stove (missing) objects selected"
        for obj, index in v.SelectionEntries():
            bounds = v.ObjectFootprint(obj)[0]
            assert v.DrawingRect().contains(v.WorldToViewport(bounds.topLeft()))
            assert v.DrawingRect().contains(v.WorldToViewport(bounds.bottomRight()))
            if individual:
                screenBounds = QtCore.QRectF(v.WorldToViewport(bounds.topLeft()), v.WorldToViewport(bounds.bottomRight())).normalized()
                assert screenBounds.width() < v.DrawingRect().width() * .4
                assert screenBounds.height() < v.DrawingRect().height() * .4
    assert [(obj.firstVertex, obj.secondVertex, obj.width) for obj in v.furnishings] == original
    # Canvas deletion and undo update the same non-modal report, including zero remaining.
    main.ReportRecoveredProject(Path("Missing.plan"), Path("Backup.plan"), repairs)
    message = main.recoveryWindow
    app.processEvents()
    tree = message.recoveryTree
    v.SetSelection([(second, None)])
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Delete)
    app.processEvents()
    assert message.isVisible() and tree.topLevelItem(0).childCount() == 1
    assert tree.topLevelItem(0).text(0) == "Missing Stove — 1 object"
    v.Undo()
    app.processEvents()
    assert tree.topLevelItem(0).childCount() == 2
    v.SetSelection([(first, None), (second, None)])
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Delete)
    app.processEvents()
    assert message.isVisible() and tree.topLevelItemCount() == 0
    assert tree.headerItem().text(0) == "No missing objects remain"
    v.Undo()
    app.processEvents()
    assert tree.topLevelItem(0).childCount() == 2
    message.close()
    assert main.recoveryWindow is None
    second.definitionKey = "Missing Fridge"
    v.SetSelection([(first, None), (second, None)])
    assert main.selectionLabel.text() == "2 Furnishings selected"
    second.definitionKey = "null"
    v.SetSelection([(second, None)])
    assert main.selectionLabel.text() == f"Null (#{second.objectId:04d})"
    second.definitionKey = "Missing Stove"
    # A missing nested dependency locates its owning compound on the canvas.
    compound = dict(v.furnishingDefinitions["null"], key = "Compound", components = [
        {"definition": first.definition, "definitionKey": "Missing Child"}])
    second.definition = compound
    second.definitionKey = "Compound"
    v.furnishingDefinitions["Compound"] = compound
    with patch.object(main, "ShowAppMessage") as report:
        main.ReportRecoveredProject(Path("Missing.plan"), Path("Backup.plan"), repairs)
    entries = report.call_args.kwargs["locateEntries"]
    assert entries["Missing Child"] == [second]
    assert entries["Missing Stove"] == [first]
    assert north.definition["key"] not in entries
    second.definition = first.definition
    second.definitionKey = "Missing Stove"
    del v.furnishingDefinitions["Compound"]
    main.projectDirty = False
    main.close()


if __name__ == "__main__":
    Main()
