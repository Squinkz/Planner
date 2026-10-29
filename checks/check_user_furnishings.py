"""Selection export, styled dialog, duplicate names, unique keys and live refresh."""
import json
import os
import shutil
import sys
import tempfile
import warnings
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtWidgets
from furnishings import LoadFurnishings, Furnishing
from planner import MainWindow, Wall, Label
from theme import BuildStyle
from check_context_menus import OpenMenu, Click


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    source = Path(__file__).resolve().parent.parent / "planner-main/furnishings"
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory) / "furnishings"
        shutil.copytree(source / "definitions", folder / "definitions")
        shutil.copytree(source / "images", folder / "images")
        originals = {path.name: path.read_bytes() for path in (folder / "definitions").glob("*.json")}
        main = MainWindow()
        main.show()
        app.processEvents()
        v = main.viewport
        v.furnishingsFolder = folder
        v.ResetView()
        v.snapEnabled = False
        v.walls, v.windows, v.labels = [], [], []
        desk = Furnishing(v.furnishingDefinitions["desk"], QtCore.QPointF(-500, 0))
        chair = Furnishing(v.furnishingDefinitions["chair_dining"], QtCore.QPointF(500, 0))
        chair.angle = 90
        chair.width = 550
        v.furnishings = [desk, chair]
        v.SetSelection([(chair, None), (desk, None)])  # Selection order differs from draw order.
        main.sidebarTabs.setCurrentIndex(1)
        assert "Create Furnishing from Selection…" in OpenMenu(v, QtCore.QPointF(-500, 0))
        button = next(action.defaultWidget() for action in v.objectContextMenu.actions()
                      if not action.isSeparator() and action.defaultWidget().accessibleName() == "Create Furnishing from Selection…")
        label = button.findChild(QtWidgets.QLabel, "menuTextLabel")
        assert label.width() >= label.sizeHint().width(), (label.width(), label.sizeHint().width())
        originalCorners = [point for obj in v.furnishings for point in v.ObjectCorners(obj)]
        historyCount = len(v.undoHistory)

        def FillDialog():
            dialog = app.activeModalWidget()
            assert isinstance(dialog, QtWidgets.QDialog) and dialog.windowTitle() == "Create Furnishing"
            assert not dialog.windowIcon().isNull()
            field = dialog.findChild(QtWidgets.QLineEdit, "furnishingName")
            category = dialog.findChild(QtWidgets.QComboBox, "furnishingCategory")
            buttons = dialog.findChild(QtWidgets.QDialogButtonBox)
            save = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Save)
            assert not save.isEnabled()
            field.setText("Work Corner")
            category.setCurrentText("Study")
            dialog.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots/create-furnishing-dialog.png"))
            save.click()

        QtCore.QTimer.singleShot(0, FillDialog)
        Click(v, "Create Furnishing from Selection…")
        path = folder / "definitions_user/work_corner.json"
        data = json.loads(path.read_text())
        assert data["name"] == "Work Corner" and data["category"] == "Study"
        assert [child["furnishing"] for child in data["children"]] == ["desk", "chair_dining"]
        assert [child["zIndex"] for child in data["children"]] == [0, 1]
        assert data["children"][1]["width"] == 550 and data["children"][1]["angle"] == 90
        assert "work_corner" in main.furnishingDimensions and not main.furnishingThumbnails.Icon(main.viewport.furnishingDefinitions["work_corner"]).isNull()
        assert main.sidebarTabs.count() == 4 and main.sidebarTabs.currentIndex() == 1
        saved = v.furnishingDefinitions["work_corner"]
        corners = [point for obj in v.furnishings for point in v.ObjectCorners(obj)]
        assert abs(saved["width"] - (max(point.x() for point in corners) - min(point.x() for point in corners))) < 1e-6
        assert saved["isUser"] and saved["sourcePath"] == path
        assert len(v.furnishings) == 1
        compound = v.furnishings[0]
        assert compound.definition is saved and compound.objectId is not None
        assert len(v.undoHistory) == historyCount + 1
        assert v.SelectionEntries() == [(compound, None)]
        for coordinate in (lambda point: point.x(), lambda point: point.y()):
            assert abs(min(map(coordinate, corners)) - min(map(coordinate, originalCorners))) < 1e-6
            assert abs(max(map(coordinate, corners)) - max(map(coordinate, originalCorners))) < 1e-6
        v.Undo()
        assert v.furnishings == [desk, chair]
        v.Redo()
        assert v.furnishings == [compound]
        menuItems = OpenMenu(v, (compound.firstVertex + compound.secondVertex) / 2)
        assert "Create Furnishing from Selection…" not in menuItems and "Decompose" in menuItems
        Click(v, "Decompose")
        assert len(v.furnishings) == 2 and compound not in v.furnishings
        for original, part in zip((desk, chair), v.furnishings):
            assert part.definition["key"] == original.definition["key"]
            assert QtCore.QLineF(part.firstVertex, original.firstVertex).length() < 1e-6
            assert QtCore.QLineF(part.secondVertex, original.secondVertex).length() < 1e-6
            assert abs(part.width - original.width) < 1e-6
        assert len({part.objectId for part in v.furnishings}) == 2
        v.Undo()
        assert v.furnishings == [compound]
        v.Redo()
        assert len(v.furnishings) == 2
        desk = v.furnishings[0]
        v.SetSelection([(desk, None)])
        assert "Create Furnishing from Selection…" not in OpenMenu(v, (desk.firstVertex + desk.secondVertex) / 2)
        v.objectContextMenu.hide()
        messages = []

        def Message(title, text, kind = "info", **kwargs):
            messages.append((title, text, kind, kwargs))
            return QtWidgets.QMessageBox.StandardButton.Cancel

        with patch.object(main, "ShowAppMessage", side_effect = Message):
            for name in ("Desk", "desk", "DESK", "Null"):
                assert main.SaveUserFurnishing(name, "Study", data["children"])
            assert main.SaveUserFurnishing("work corner", "Changed", data["children"])
            assert not messages, messages
            assert json.loads(path.read_text())["category"] == "Study"
        with patch.object(main, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.Save):
            assert main.SaveUserFurnishing("WORK CORNER", "Changed", data["children"])
        assert json.loads(path.read_text())["category"] == "Study"
        assert len(list((folder / "definitions_user").glob("*.json"))) == 7
        assert v.furnishingDefinitions["work_corner"]["category"] == "Study"
        assert v.furnishingDefinitions["work_corner_2"]["category"] == "Changed"
        assert {v.furnishingDefinitions[key]["name"] for key in ("desk_2", "desk_3", "desk_4")} == {"Desk", "desk", "DESK"}
        assert all(path.read_bytes() == originals[path.name] for path in (folder / "definitions").glob("*.json"))
        assert any(item["key"] == "work_corner" for item in LoadFurnishings(folder))
        # Manually installed user definitions override the built-in file key.
        (folder / "definitions_user/desk.json").write_text(json.dumps({"name": "Custom Desk", "image": "desk", "width": 1400}))
        (folder / "definitions_user/shadow.json").write_text(json.dumps({"name": "Desk", "children": data["children"]}))
        with warnings.catch_warnings(record = True):
            loaded = {item["key"]: item for item in LoadFurnishings(folder)}
        assert loaded["desk"]["isUser"] and loaded["desk"]["name"] == "Custom Desk" and loaded["desk"]["width"] == 1400
        assert loaded["shadow"]["name"] == "Desk"
        # Invalid new definitions do not damage existing same-name definitions.
        before = path.read_bytes()
        with patch.object(main, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.Save):
            assert not main.SaveUserFurnishing("WORK CORNER", "Changed", [{"furnishing": "work_corner", "width": -1}])
        assert path.read_bytes() == before
        v.walls = [Wall(QtCore.QPointF(-1000, 1000), QtCore.QPointF(1000, 1000))]
        v.SetSelection([(desk, None), (v.walls[0], None)])
        assert "Create Furnishing from Selection…" not in OpenMenu(v, QtCore.QPointF(-500, 0))
        v.labels = [Label(QtCore.QPointF(0, 1300))]
        v.SetSelection([(v.labels[0], None)])
        assert "Create Furnishing from Selection…" not in OpenMenu(v, v.labels[0].origin)
        for action in v.objectContextMenu.actions():
            button = action.defaultWidget() if not action.isSeparator() else None
            if button is not None and button.accessibleName() in ("Cut", "Copy"):
                assert button.isEnabled(), "Labels must remain available for cut/copy"
        v.objectContextMenu.hide()
        assert v.CopySelection()
        payload = json.loads(app.clipboard().text())
        assert len(payload["objects"]) == 1 and payload["objects"][0]["type"] == "Label"
        assert payload["objects"][0]["text"] == v.labels[0].text
        missing = Furnishing(v.furnishingDefinitions["null"])
        assert v.ObjectsHaveAssetErrors([v.labels[0], missing]), "Labels must not bypass errors in other selected furnishings"
        app.clipboard().clear()
        main.close()
    app.processEvents()


if __name__ == "__main__":
    Main()
