"""Counter placement, connected endpoints, black joins and persistence."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Counter, Wall, Window
from planner_app.models import Furnishing
from planner_app.project_codec import DecodeProject
from theme import BuildStyle
from planner_app.graphics.palette import themeColors
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    app.processEvents()
    viewport = main.viewport
    viewport.unitsMode = "Adaptive Metric"  # Dimension assertions below use cm/m.
    main.sizeLinkButton.setChecked(False)
    point = QtCore.QPointF
    main.snapButton.setChecked(False)
    assert main.counterButton.toolTip() == "Counter" and not main.counterButton.icon().isNull()
    palette = main.buildObjectLayouts["Miscellaneous"]
    assert [palette.itemAt(i).widget().findChild(QtWidgets.QPushButton).objectType
            for i in range(palette.count())] == ["stair", "counter", "railing", "pillar", "column", "fireplace", "elevator"]
    mime = QtCore.QMimeData()
    mime.setData("application/x-planner-counter", b"counter")
    position = viewport.WorldToViewport(point())
    enter = QtGui.QDragEnterEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                 QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    app.sendEvent(viewport, enter)
    assert enter.isAccepted()
    move = QtGui.QDragMoveEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                               QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    app.sendEvent(viewport, move)
    assert isinstance(viewport.counterPreview, Counter)
    viewport.grab()
    drop = QtGui.QDropEvent(position, QtCore.Qt.DropAction.CopyAction, mime,
                           QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    app.sendEvent(viewport, drop)
    assert drop.isAccepted() and len(viewport.walls) == 1
    counter = viewport.walls[0]
    assert type(counter) is Counter and counter.width == 600
    assert counter.firstVertex == point(-500, 0) and counter.secondVertex == point(500, 0)
    assert counter.objectId is not None and "Counter (#" in main.selectionLabel.text()
    assert main.propertyFields["width"].value() == 60 and main.materialField.isHidden()
    assert viewport.FindWindowPlacement(position, openingType = Window) is None
    viewport.Undo()
    assert not viewport.walls
    viewport.Redo()
    assert viewport.walls[0] is counter
    # Counters join and connected vertex dragging deforms both segments.
    second = Counter(point(500, 0), point(500, 1000))
    before = viewport.CaptureState()
    viewport.walls.append(second)
    viewport.RecordEdit(before)
    viewport.SetSelection([(counter, 1)])
    start = viewport.WorldToViewport(point(500, 0)).toPoint()
    end = viewport.WorldToViewport(point(700, 200)).toPoint()
    Drag(viewport, start, end)
    assert counter.secondVertex == second.firstVertex == point(700, 200)
    viewport.Undo()
    assert counter.secondVertex == second.firstVertex == point(500, 0)
    viewport.SetSelection([])
    image = viewport.grab().toImage()
    for position in (point(), point(500, 0), point(500, 500)):
        pixel = viewport.WorldToViewport(position).toPoint()
        assert image.pixelColor(pixel).name() == QtGui.QColor(themeColors["canvas"]).name()
    image.save(str(Path(__file__).resolve().parent.parent / "screenshots" / "counters.png"))
    assert main.visibilityItems["Counters"].text(0) == "Counters (2 objects)"
    assert main.visibilityItems["Walls"].text(0) == "Walls (0 objects)"
    viewport.SetSelection([(counter, None), (second, None)])
    assert "2 Counters" in main.selectionLabel.text()
    main.propertyFields["width"].setValue(70)
    assert counter.width == second.width == 700
    viewport.Undo()
    assert counter.width == second.width == 600
    try:
        assert viewport.CopySelection() and viewport.ReadClipboardSelection() is not None
        assert viewport.PasteSelection(viewport.WorldToViewport(point(-1500, -1500)))
        assert len(viewport.walls) == 4 and all(type(obj) is Counter for obj in viewport.walls)
        viewport.Undo()
    finally:
        app.clipboard().clear()
        app.processEvents()
    data = main.BuildProjectData()
    decoded = DecodeProject(data, viewport.furnishingDefinitions)
    assert len(decoded[0]) == 2 and all(type(obj) is Counter and obj.width == 600 for obj in decoded[0])
    assert decoded[0][0].secondVertex == decoded[0][1].firstVertex
    data["settings"]["visibility"].pop("Counters")
    assert DecodeProject(data, viewport.furnishingDefinitions)[5]["visibility"]["Counters"]
    viewport.visibility["Walls"] = False
    assert viewport.IsObjectVisible(counter)
    viewport.visibility["Counters"] = False
    assert not viewport.IsObjectVisible(counter)
    viewport.visibility["Counters"] = True
    # Invalid placement keeps a preview but refuses the drop.
    desk = Furnishing(viewport.furnishingDefinitions["desk"], point(-1500, 0))
    viewport.furnishings = [desk]
    assert viewport.CounterFits(Counter(point(-2000, 0), point(-1000, 0)))
    blocker = Wall(point(-2000, 0), point(-1000, 0))
    viewport.walls.append(blocker)
    position = viewport.WorldToViewport(point(-1500, 0))
    enter = QtGui.QDragEnterEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                 QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    app.sendEvent(viewport, enter)
    move = QtGui.QDragMoveEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                               QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    app.sendEvent(viewport, move)
    assert viewport.counterPreview is not None and not viewport.CounterFits(viewport.counterPreview)
    viewport.grab()
    drop = QtGui.QDropEvent(position, QtCore.Qt.DropAction.CopyAction, mime,
                           QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    app.sendEvent(viewport, drop)
    assert not drop.isAccepted() and len(viewport.walls) == 3 and viewport.counterPreview is None
    viewport.walls.remove(blocker)
    viewport.walls.append(Wall(point(-2000, 2000), point(2000, 2000)))
    viewport.SetSelection([(counter, None)])
    viewport.HideSelection()
    assert not viewport.IsObjectVisible(counter)
    viewport.UnhideObjects()
    assert viewport.IsObjectVisible(counter)
    main.close()
    app.processEvents()
    recovered = MainWindow()
    assert sum(type(obj) is Counter for obj in recovered.viewport.walls) == 2
    assert recovered.viewport.visibility["Counters"]
    recovered.close()
    app.processEvents()


if __name__ == "__main__":
    Main()
