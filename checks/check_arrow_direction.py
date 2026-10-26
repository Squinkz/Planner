"""Arrow reversal and direction-preserving arrow/stair endpoint extrusion."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Arrow, Stair
from planner_app.graphics.arrows import ConnectedArrowDirections
from planner_app.graphics.theme import HeaderIcon
from planner_app.project_codec import DecodeProject, EncodeScene
from check_history import Drag


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        p = QtCore.QPointF
        v.snapEnabled = False
        first = Arrow(p(-2000, 0), p(-500, 0), 30, .2, .4)
        second = Arrow(p(500, 0), p(2000, 0), 50)
        InstallScene(main, [first, second])
        v.SetSelection([(first, 0), (second, None)])
        assert main.arrowDirectionButton.isVisibleTo(main.propertiesPanel)
        assert main.arrowDirectionButton.icon().pixmap(24, 24).toImage() == HeaderIcon("Redo").pixmap(24, 24).toImage()
        form = main.arrowProperties.layout()
        assert form.getWidgetPosition(main.arrowFields["length"])[0] < form.getWidgetPosition(main.arrowDirectionButton)[0]
        assert form.getWidgetPosition(main.arrowDirectionButton)[0] < form.getWidgetPosition(main.arrowFields["solidTip"])[0]
        QtTest.QTest.mouseClick(main.arrowDirectionButton, QtCore.Qt.MouseButton.LeftButton)
        assert first.firstVertex == p(-500, 0) and first.secondVertex == p(-2000, 0)
        assert second.firstVertex == p(2000, 0) and second.secondVertex == p(500, 0)
        assert (first.firstMiter, first.secondMiter) == (.4, .2)
        assert v.SelectionEntries()[0] == (first, 1)
        assert len(v.undoHistory) == 1
        assert first.directionReversed and second.directionReversed
        assert main.arrowDirectionButton.icon().pixmap(24, 24).toImage() == HeaderIcon("Undo").pixmap(24, 24).toImage()
        v.Undo()
        assert first.firstVertex == p(-2000, 0) and second.firstVertex == p(500, 0)
        assert not first.directionReversed and not second.directionReversed
        assert main.arrowDirectionButton.icon().pixmap(24, 24).toImage() == HeaderIcon("Redo").pixmap(24, 24).toImage()
        v.Redo()
        assert first.secondVertex == p(-2000, 0)
        assert main.arrowDirectionButton.icon().pixmap(24, 24).toImage() == HeaderIcon("Undo").pixmap(24, 24).toImage()
        data = main.BuildProjectData()
        decoded = DecodeProject(data, v.furnishingDefinitions, validatePlacement = False)
        assert all(obj.directionReversed for obj in decoded[0])
        assert v.CloneLinearObject(first).directionReversed
        try:
            assert v.CopySelection()
            assert all(record["directionReversed"] for record in v.ReadClipboardSelection()["objects"])
        finally:
            QtWidgets.QApplication.clipboard().clear()
        v.SetSelection([(first, None)])
        pos = v.WorldToViewport(p(-1250, 0))
        v.ShowObjectContextMenu(pos, v.mapToGlobal(pos.toPoint()))
        button = next(action.defaultWidget() for action in v.objectContextMenu.actions()
                      if not action.isSeparator() and action.defaultWidget().accessibleName() == "Flip Direction")
        QtTest.QTest.mouseClick(button, QtCore.Qt.MouseButton.LeftButton)
        assert first.firstVertex == p(-2000, 0) and first.secondVertex == p(-500, 0)
        assert not first.directionReversed
        data = main.BuildProjectData()
        decoded = DecodeProject(data, v.furnishingDefinitions, validatePlacement = False)
        assert decoded[0][0].firstVertex == first.firstVertex and decoded[0][0].secondVertex == first.secondVertex
        for cls in (Arrow, Stair):
            for reversedDirection in (False, True):
                for index in (0, 1):
                    source = cls(p(-1000, 0), p(1000, 0), 200)
                    source.directionReversed = reversedDirection
                    if cls is Stair:
                        source.directionReversed = reversedDirection
                        source.stepSizeBounds = (220, 330)
                    InstallScene(main, [source])
                    v.SetSelection([(source, index)])
                    anchor = p(source.firstVertex if index == 0 else source.secondVertex)
                    target = anchor + p(-1000 if index == 0 else 1000, 0)
                    Drag(v, v.WorldToViewport(anchor).toPoint(), v.WorldToViewport(target).toPoint(),
                         QtCore.Qt.KeyboardModifier.ShiftModifier)
                    assert len(v.walls) == 2, (cls, reversedDirection, index)
                    extension = next(obj for obj in v.walls if obj is not source)
                    endpoints = (extension.firstVertex, extension.secondVertex)
                    assert endpoints[1 - index] == anchor, (cls, reversedDirection, index, endpoints)
                    assert QtCore.QLineF(endpoints[index], target).length() < 20
                    assert source.firstVertex == p(-1000, 0) and source.secondVertex == p(1000, 0)
                    assert extension.directionReversed == reversedDirection
                    if cls is Stair:
                        assert extension.directionReversed == reversedDirection
                        assert extension.stepSizeBounds == source.stepSizeBounds
                    else:
                        directions = ConnectedArrowDirections(v.walls)
                        assert sum(value[2] for value in directions.values()) == 1
                        assert directions[id(source if index == 0 else extension)][2]
                    expected = EncodeScene(v)
                    v.Undo()
                    assert len(v.walls) == 1 and v.walls[0] is source
                    v.Redo()
                    assert EncodeScene(v) == expected
    print("PASS: arrow direction buttons, multi-selection, endpoint identity, persistence, both-end arrow/stair extrusion and undo")


if __name__ == "__main__":
    Main()
