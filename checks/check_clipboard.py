"""Scene clipboard snapshots, hierarchy, placement, shortcuts and atomic history."""
import os
import sys
import json
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall, Stair, Window, Door, SlidingDoor, PocketDoor, SilledWindow, OpenDoorway
from furnishings import Furnishing
from planner_app.viewport.clipboard import clipboardMimeType
from planner_app.graphics.theme import HeaderIcon


def Main():
    app = QtWidgets.QApplication([])
    try:
        QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
        main = MainWindow()
        main.show()
        app.processEvents()
        v = main.viewport
        v.snapEnabled = False
        point = QtCore.QPointF
        ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
        app.clipboard().clear()
        assert not v.PasteSelection() and not v.CopySelection()
        position = v.DrawingRect().center()
        v.ShowObjectContextMenu(position, v.mapToGlobal(position.toPoint()))
        button = v.objectContextMenu.actions()[0].defaultWidget()
        assert button.accessibleName() == "Paste" and not button.isEnabled()
        assert button.iconLabel.pixmap().toImage() == HeaderIcon("Paste").pixmap(18, 18).toImage()
        v.objectContextMenu.hide()
        parent = Wall(point(-2500, -800), point(2500, -800), 240, .6, .8, "Wood")
        types = (Window, Door, SlidingDoor, PocketDoor, SilledWindow, OpenDoorway)
        children = [kind(parent, .05 + i * .15, .13 + i * .15) for i, kind in enumerate(types)]
        children[0].swingsOutwards = True
        children[1].hingeAtSecond = True
        children[2].panelsFlipped = True
        children[3].hingeAtSecond = True
        children[4].sillDepth = 90
        v.walls, v.windows = [parent], children
        v.SetSelection([(parent, 0), (parent, 1)])
        v.EnsureObjectIds()
        history = len(v.undoHistory)
        assert v.CopySelection() and len(v.undoHistory) == history
        payload = json.loads(bytes(app.clipboard().mimeData().data(clipboardMimeType)))
        assert len(payload["objects"]) == 7
        # Mutating the source after copy cannot alter the clipboard snapshot.
        parent.material = "Brick"
        children[4].sillDepth = 40
        assert v.PasteSelection(v.WorldToViewport(point(0, 800)))
        copied = v.walls[-1]
        assert copied is not parent and copied.objectId != parent.objectId
        assert copied.material == "Wood" and copied.firstMiter == .6 and copied.secondMiter == .8
        pasted = v.windows[6:]
        assert len(pasted) == 6 and all(obj.parentWall is copied for obj in pasted)
        assert tuple(type(obj) for obj in pasted) == types
        assert pasted[0].swingsOutwards and pasted[1].hingeAtSecond and pasted[2].panelsFlipped
        assert pasted[3].hingeAtSecond and pasted[4].sillDepth == 90
        assert len({obj.objectId for obj in v.walls + v.windows}) == 14
        assert v.SelectionEntries() == [(copied, None)]
        assert len(v.undoHistory) == history + 1
        v.Undo()
        assert v.walls == [parent] and v.windows == children
        v.Redo()
        assert v.walls[-1] is copied and len(v.windows) == 12
        v.SetSelection([(copied, None)])
        assert v.CutSelection() and v.walls == [parent] and v.windows == children
        v.Undo()
        assert len(v.walls) == 2 and len(v.windows) == 12
        # Standalone openings attach to an existing destination wall.
        v.SetSelection([(children[4], None)])
        assert v.CopySelection()
        v.windows = children.copy()
        assert v.PasteSelection(v.WorldToViewport(point(0, 800)))
        opening = v.windows[-1]
        assert type(opening) is SilledWindow and opening.parentWall is copied and opening.sillDepth == 40
        assert abs(opening.length - children[4].length) < .01
        before = v.CaptureState()
        app.processEvents()
        contentGeometry = main.centralWidget().geometry()
        assert not v.clipboardError
        assert not v.PasteSelection(v.WorldToViewport(point(0, 800)))
        assert v.CaptureState() == before
        app.processEvents()
        assert v.clipboardError and v.clipboardErrorTimer.isActive()
        assert main.centralWidget().geometry() == contentGeometry
        main.grab().save('screenshots/clipboard-error-overlay.png')
        QtTest.QTest.qWait(5300)
        app.processEvents()
        assert not v.clipboardError and not v.clipboardErrorTimer.isActive()
        assert main.centralWidget().geometry() == contentGeometry
        assert not v.PasteSelection(v.WorldToViewport(point(0, 0)))
        assert v.CaptureState() == before
        # Furnishings retain angle/dimensions/order; group relative positions survive.
        v.walls, v.windows = [], []
        first = Furnishing(v.furnishingDefinitions["desk"], point(-900, -700))
        first.angle = 35
        first.width = 700
        second = Furnishing(v.furnishingDefinitions["desk"], point(-400, -700))
        v.furnishings = [first, second]
        v.SetSelection([(second, None), (first, None)])
        assert v.CopySelection()
        assert v.PasteSelection(v.WorldToViewport(point(900, 700)))
        a, b = v.furnishings[-2:]
        assert abs(a.angle - 35) < .01 and a.width == 700 and abs(a.length - first.length) < .01
        assert (b.firstVertex - a.firstVertex - (second.firstVertex - first.firstVertex)).manhattanLength() < .01
        assert len(v.SelectionEntries()) == 2
        # Collision rejection is atomic and leaves history/selection unchanged.
        v.walls = [Wall(point(200, 700), point(1700, 700), 600)]
        before = v.CaptureState()
        history = len(v.undoHistory)
        assert not v.PasteSelection(v.WorldToViewport(point(900, 700)))
        assert v.CaptureState() == before and len(v.undoHistory) == history
        v.walls, v.furnishings = [], []
        stair = Stair(point(-1000, -700), point(-400, -700), 300, directionReversed = True)
        v.walls = [stair]
        v.SetSelection([(stair, None)])
        assert v.CopySelection() and v.PasteSelection(v.WorldToViewport(point(700, 700)))
        assert isinstance(v.walls[-1], Stair) and v.walls[-1].directionReversed
        # Ctrl shortcuts and header commands use the same operations.
        v.walls, v.windows, v.furnishings = [], [], [first]
        v.SetSelection([(first, None)])
        v.setFocus()
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_C, ctrl)
        v.hoverPosition = v.WorldToViewport(point(900, 700))
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_V, ctrl)
        assert len(v.furnishings) == 2
        QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_X, ctrl)
        assert len(v.furnishings) == 1
        v.Undo()
        assert len(v.furnishings) == 2
        main.menuButtons["Copy"].click()
        v.hoverPosition = v.WorldToViewport(point(0, 0))
        main.menuButtons["Paste"].click()
        assert len(v.furnishings) == 3
        main.menuButtons["Cut"].click()
        assert len(v.furnishings) == 2
        # Editor clipboard shortcuts still operate on text, without touching objects.
        v.SetSelection([(first, None)])
        app.processEvents()
        editor = main.propertyFields["length"].lineEdit()
        editor.setFocus()
        editor.setText("12345")
        editor.selectAll()
        QtTest.QTest.keyClick(editor, QtCore.Qt.Key.Key_C, ctrl)
        assert app.clipboard().text() == "12345" + main.propertyFields["length"].suffix()
        assert not v.PasteSelection()
        # Malformed app data is ignored without modifying the scene.
        for data in ({"version": 99}, {"version": 1, "center": [0, 0], "objects": [{"type": "Wall"}]},
                     {"version": 1, "center": [float("nan"), 0], "objects": payload["objects"]}):
            mime = QtCore.QMimeData()
            mime.setData(clipboardMimeType, json.dumps(data).encode())
            app.clipboard().setMimeData(mime)
            before = v.CaptureState()
            assert not v.PasteSelection() and v.CaptureState() == before
        # The system payload can be pasted into another Planner window.
        v.SetSelection([(first, None)])
        assert v.CopySelection()
        other = MainWindow()
        other.show()
        app.processEvents()
        other.viewport.snapEnabled = False
        assert other.viewport.PasteSelection(other.viewport.WorldToViewport(point()))
        assert len(other.viewport.furnishings) == 1
        assert abs(other.viewport.furnishings[0].angle - first.angle) < .01
        other.close()
        # Empty-grid menu paste uses the clicked location, not a stale hover.
        v.setFocus()
        pastePoint = v.WorldToViewport(point(-900, 700))
        v.ShowObjectContextMenu(pastePoint, v.mapToGlobal(pastePoint.toPoint()))
        button = v.objectContextMenu.actions()[0].defaultWidget()
        assert button.accessibleName() == "Paste"
        button.click()
        pasted = v.furnishings[-1]
        assert QtCore.QLineF((pasted.firstVertex + pasted.secondVertex) / 2, point(-900, 700)).length() < .01
        main.close()
        print("PASS: portable snapshots, wall children, types/properties, independent clones, cut/paste history, reattachment, collisions, shortcuts and editor text.")
    finally:
        app.clipboard().clear()
        app.processEvents()



if __name__ == "__main__":
    Main()
