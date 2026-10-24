"""Touching furniture follows recursively through drags and precise transforms."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from planner import MainWindow
from planner_app.models import Furnishing, Label, NorthArrow
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v, point = main.viewport, QtCore.QPointF
    v.ResetView()
    v.snapEnabled = False
    main.connectedOptions["vertices"].setChecked(False)
    main.connectedOptions["objects"].setChecked(True)
    furnishings = []
    for x in (0, 600, 1100, 1800):
        obj = Furnishing(v.furnishingDefinitions["desk"], point(x, 0))
        obj.width = 600
        obj.firstVertex, obj.secondVertex = point(x, -300), point(x, 300)
        furnishings.append(obj)
    a, b, c, distant = furnishings
    marker, label = NorthArrow(point(600, 0)), Label(point(600, 0), "Annotation")
    v.walls, v.windows, v.labels = [], [], [label]
    v.furnishings = furnishings + [marker]
    v.SetSelection([(a, None)])
    attachments = v.AttachedVertices(a)
    assert {(id(obj), index) for obj, index, vertex in attachments} == {(id(obj), index) for obj in (b, c) for index in (0, 1)}
    initial = [(obj, point(obj.firstVertex), point(obj.secondVertex)) for obj in furnishings + [marker, label]]
    delta = point(200, 100)
    start = v.WorldToViewport(point()).toPoint()
    finish = start + QtCore.QPoint(40, -20)
    Drag(v, start, finish)
    for obj, first, second in initial:
        offset = delta if obj in (a, b, c) else point()
        assert obj.firstVertex == first + offset and obj.secondVertex == second + offset
    v.Undo()
    assert all(obj.firstVertex == first and obj.secondVertex == second for obj, first, second in initial)
    v.Redo()
    assert b.firstVertex == initial[1][1] + delta
    v.Undo()
    assert v.MoveSpecial(200, 100, 0) is None
    assert c.firstVertex == initial[2][1] + delta and distant.firstVertex == initial[3][1]
    v.Undo()
    assert v.MoveSpecial(0, 0, 90) is None
    for obj, first, second in initial[:3]:
        assert QtCore.QLineF(obj.firstVertex, point(-first.y(), first.x())).length() < 1e-6
        assert QtCore.QLineF(obj.secondVertex, point(-second.y(), second.x())).length() < 1e-6
    v.Undo()
    # Rotated footprints connect by actual contact, not just shared endpoints.
    b.angle = 45
    assert {id(obj) for obj, index, vertex in v.AttachedVertices(a)} == {id(b), id(c)}
    b.angle = 0
    # Vertex-only mode never stretches or carries neighboring furniture.
    main.connectedOptions["objects"].setChecked(False)
    main.connectedOptions["vertices"].setChecked(True)
    Drag(v, start, finish)
    assert b.firstVertex == initial[1][1] and c.firstVertex == initial[2][1]
    v.Undo()
    main.connectedOptions["objects"].setChecked(True)
    # Changing the option during a drag restores/reapplies the original cluster.
    QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, pos = start)
    v.UpdateInteraction(point(finish), QtCore.Qt.KeyboardModifier.NoModifier)
    assert b.firstVertex == initial[1][1] + delta
    main.connectedOptions["objects"].setChecked(False)
    assert b.firstVertex == initial[1][1]
    main.connectedOptions["objects"].setChecked(True)
    assert b.firstVertex == initial[1][1] + delta
    v.CancelInteraction()
    assert all(obj.firstVertex == first and obj.secondVertex == second for obj, first, second in initial)
    # Duplicating the selected object does not pull or duplicate its neighbors.
    Drag(v, start, finish, QtCore.Qt.KeyboardModifier.ShiftModifier)
    assert len(v.furnishings) == 6
    assert b.firstVertex == initial[1][1] and c.firstVertex == initial[2][1]
    v.Undo()
    v.SetSelection([(a, None), (b, None)])
    Drag(v, start, finish)
    assert c.firstVertex == initial[2][1] + delta
    assert a.firstVertex == initial[0][1] + delta and b.firstVertex == initial[1][1] + delta
    main.close()
    print("PASS: recursive furniture contact/overlap, drag/transform, undo/redo, live options, cancellation and duplication")


if __name__ == "__main__":
    Main()
