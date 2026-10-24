"""Compound creation preserves actual canvas layering, including back-layer copies."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow
from furnishings import Furnishing


def Main():
    app = QtWidgets.QApplication([])
    source = Path(__file__).resolve().parent.parent / "planner-main/furnishings"
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        shutil.copytree(source / "definitions", folder / "definitions")
        shutil.copytree(source / "images", folder / "images")
        main = MainWindow()
        main.show()
        app.processEvents()
        v = main.viewport
        v.furnishingsFolder = folder
        v.walls, v.windows, v.labels = [], [], []
        v.showGrid = v.showMeasurements = False
        v.zoom = .4
        v.hoverPosition = None
        point = QtCore.QPointF
        table = Furnishing(v.furnishingDefinitions["table_dining_round_6"])
        chair = Furnishing(v.furnishingDefinitions["chair_dining"], point(0, 580))
        chair.behindCounters = True
        # A duplicated back-layer chair was appended after the foreground table.
        v.furnishings = [table, chair]
        v.SetSelection([])
        beforeImage = v.grab().toImage()
        v.SetSelection([(chair, None), (table, None)])

        def SaveDialog():
            dialog = app.activeModalWidget()
            dialog.findChild(QtWidgets.QLineEdit, "furnishingName").setText("Draw Order Test")
            dialog.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.StandardButton.Save).click()

        QtCore.QTimer.singleShot(0, SaveDialog)
        main.CreateFurnishingFromSelection([table, chair])
        definition = json.loads((folder / "definitions_user/draw_order_test.json").read_text())
        assert [child["furnishing"] for child in definition["children"]] == ["chair_dining", "table_dining_round_6"]
        assert [child["zIndex"] for child in definition["children"]] == [0, 1]
        compound = v.furnishings[0]
        assert not compound.behindCounters
        v.SetSelection([])
        afterImage = v.grab().toImage()
        # Probe the chair/table intersection: table fill must still hide chair ink.
        pixel = v.WorldToViewport(point(0, 330)).toPoint()
        assert afterImage.pixelColor(pixel) == beforeImage.pixelColor(pixel)
        v.Undo()
        assert v.furnishings == [table, chair] and chair.behindCounters
        v.Redo()
        assert v.furnishings == [compound]
        v.DecomposeFurnishings([compound])
        assert [obj.definition["key"] for obj in v.furnishings] == ["chair_dining", "table_dining_round_6"]
        # A compound made entirely from back-layer objects remains behind counters.
        for obj in v.furnishings:
            obj.behindCounters = True
        QtCore.QTimer.singleShot(0, SaveDialog)
        main.CreateFurnishingFromSelection(list(v.furnishings))
        assert len(v.furnishings) == 1 and v.furnishings[0].behindCounters
        main.close()
    print("PASS: compounds preserve canvas draw order, back-layer priority, undo/redo and decomposition.")


if __name__ == "__main__":
    Main()
