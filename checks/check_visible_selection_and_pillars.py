"""Select-all excludes hidden group members; walls and pillars share bulk properties."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from planner import MainWindow
from planner_app.models import Wall, Pillar, Stair, Counter, Label


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    v.unitsMode = "Adaptive Metric"
    point = QtCore.QPointF
    wall = Wall(point(), point(1000, 0), 120)
    pillar = Pillar(point(2000, 1500), point(2000, 2000), 300, material = "Brick")
    stair = Stair(point(0, 3000), point(1000, 3000), 500)
    counter = Counter(point(0, 4500), point(1000, 4500))
    label = Label(point(0, 6000))
    v.walls, v.labels = [wall, pillar, stair, counter], [label]
    v.windows, v.furnishings = [], []
    v.objectGroups = [(wall, stair, label)]
    v.groupModeEnabled = True
    v.hiddenObjects, v.hiddenObjectIds = [pillar], {id(pillar)}
    v.visibility["Stairs"] = False
    v.visibility["Labels"] = False
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_A, QtCore.Qt.KeyboardModifier.ControlModifier)
    assert {id(obj) for obj, index in v.SelectionEntries()} == {id(wall), id(counter)}
    # Neither group expansion nor the Walls visibility category may reintroduce
    # objects that the user cannot currently see.
    v.hiddenObjects, v.hiddenObjectIds = [], set()
    v.visibility["Walls"] = False
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_A, QtCore.Qt.KeyboardModifier.ControlModifier)
    assert v.SelectionEntries() == [(counter, None)]
    v.visibility["World"] = False
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_A, QtCore.Qt.KeyboardModifier.ControlModifier)
    assert not v.SelectionEntries()
    v.visibility = dict.fromkeys(v.visibility, True)
    v.objectGroups = []
    for entries in ([(wall, None), (pillar, None)], [(pillar, None), (wall, None)]):
        v.SetSelection(entries)
        assert main.wallProperties.isVisible()
        assert main.selectionLabel.text() == "2 Walls selected"
        assert main.wallProperties.layout().isRowVisible(main.materialField)
        assert not main.wallProperties.layout().isRowVisible(main.propertyFields["angle"])
        assert main.propertyFields["width"].mixedValue
        assert main.propertyFields["width"].lineEdit().placeholderText() == "(different)"
        before = v.CaptureState()
        main.EditProperty("width", 40)
        assert wall.width == pillar.width == 400
        v.Undo()
        assert v.CaptureState()[0] == before[0]
        main.EditMaterial("Concrete")
        assert wall.material == pillar.material == "Concrete"
        v.Undo()
        assert wall.material == "Generic" and pillar.material == "Brick"
        main.EditProperty("length", 1.5)
        assert abs(QtCore.QLineF(wall.firstVertex, wall.secondVertex).length() - 1500) < .01
        assert abs(pillar.length - 1500) < .01
        v.Undo()
    position = v.WorldToViewport(point(500, 0))
    v.ShowObjectContextMenu(position, v.mapToGlobal(position.toPoint()))
    labels = [action.defaultWidget().accessibleName() for action in v.objectContextMenu.actions() if not action.isSeparator()]
    assert "Material" in labels and "Subdivide Wall" not in labels
    v.objectContextMenu.hide()
    main.close()


if __name__ == "__main__":
    Main()
