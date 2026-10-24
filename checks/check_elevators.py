"""Elevators use architectural rendering and collisions with furnishing-style editing."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Elevator, Wall, Counter, Railing
from planner_app.models import Furnishing
from planner_app.project_codec import DecodeProject
from planner_app.graphics.svg_preview import SvgPreviewRenderer


def Mouse(viewport, eventType, position):
    left = QtCore.Qt.MouseButton.LeftButton
    buttons = QtCore.Qt.MouseButton.NoButton if eventType == QtCore.QEvent.Type.MouseButtonRelease else left
    button = QtCore.Qt.MouseButton.NoButton if eventType == QtCore.QEvent.Type.MouseMove else left
    event = QtGui.QMouseEvent(eventType, position, QtCore.QPointF(viewport.mapToGlobal(position.toPoint())),
                             button, buttons, QtCore.Qt.KeyboardModifier.NoModifier)
    QtWidgets.QApplication.sendEvent(viewport, event)


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v, point = main.viewport, QtCore.QPointF
    v.snapEnabled = False
    assert not main.elevatorButton.icon().isNull()
    mime = QtCore.QMimeData()
    mime.setData("application/x-planner-elevator", b"elevator")
    position = v.WorldToViewport(point())
    enter = QtGui.QDragEnterEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    v.dragEnterEvent(enter)
    move = QtGui.QDragMoveEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    v.dragMoveEvent(move)
    assert type(v.arrowPreview) is Elevator
    v.grab()
    drop = QtGui.QDropEvent(position, QtCore.Qt.DropAction.CopyAction, mime,
        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    v.dropEvent(drop)
    elevator = v.walls[0]
    assert drop.isAccepted() and type(elevator) is Elevator
    assert elevator.width == elevator.length == 1200
    assert "Elevator (#" in main.selectionLabel.text()
    assert not main.wallProperties.layout().isRowVisible(main.materialField)
    assert len(v.FurnishingHandles(elevator)) == 13
    # These values use the adaptive property's cm width and m length.
    v.unitsMode = "Adaptive Metric"
    main.sizeLinkButton.setChecked(False)
    main.EditProperty("width", 150)
    main.EditProperty("length", 1.8)
    main.EditProperty("angle", 25)
    assert elevator.width == 1500 and abs(elevator.length - 1800) < .001 and abs(elevator.angle - 25) < .001
    before = v.CaptureState()
    v.SetSelection([])
    assert v.HitTest(v.WorldToViewport(point())) == (elevator, None)
    v.SetSelection([(elevator, None)])
    assert v.CaptureState() == before
    elevator.angle = 0
    handle = next(handle for handle in v.FurnishingHandles(elevator) if handle[0] == "resize" and handle[1] == "width" and handle[2] == 1)
    start = handle[3]
    finish = start + point(100 * v.basePixelsPerMillimeter * v.zoom, 0)
    oldWidth = elevator.width
    Mouse(v, QtCore.QEvent.Type.MouseButtonPress, start)
    Mouse(v, QtCore.QEvent.Type.MouseMove, finish)
    Mouse(v, QtCore.QEvent.Type.MouseButtonRelease, finish)
    assert abs(elevator.width - oldWidth - 100) < .001
    blockers = [Wall(point(-100, 0), point(100, 0)), Counter(point(-100, 0), point(100, 0)),
                Railing(point(-100, 0), point(100, 0)),
                Furnishing({"key": "fixture", "width": 100, "length": 100}, point())]
    for blocker in blockers:
        v.walls = [elevator] + ([] if isinstance(blocker, Furnishing) else [blocker])
        v.furnishings = [blocker] if isinstance(blocker, Furnishing) else []
        assert not v.WallFits(elevator), type(blocker).__name__
        if isinstance(blocker, Wall):
            assert not v.WallFits(blocker), type(blocker).__name__
    v.walls, v.furnishings = [elevator], []
    v.SetSelection([])
    v.showMeasurements = True
    v.measurementVisibility["elevators"] = True
    v.grab()
    assert id(elevator) not in v.wallMaterialPaths
    assert any(elevator in owners for first, second, owners in v.sceneMeasurements[1])
    assert any(key[2] == v.lineWidths["architectural"] for key in v.elevatorRenderers)
    v.measurementVisibility["elevators"] = False
    v.grab()
    assert not any(elevator in owners for first, second, owners in v.sceneMeasurements[1])
    v.SetSelection([(elevator, None)])
    v.grab()
    assert any(elevator in owners for first, second, owners in v.sceneMeasurements[1])
    v.visibility["Elevators"] = False
    assert not v.IsObjectVisible(elevator)
    v.visibility["Elevators"] = True
    v.undoHistory, v.redoHistory = [], []
    v.zoom = .25
    assert v.CopySelection() and v.PasteSelection(v.WorldToViewport(point(4000, 0)))
    assert type(v.selectedWall) is Elevator
    v.Undo()
    assert len(v.walls) == 1
    v.Redo()
    assert len(v.walls) == 2 and all(type(obj) is Elevator for obj in v.walls)
    data = main.BuildProjectData()
    decoded = DecodeProject(data, v.furnishingDefinitions)
    assert all(type(obj) is Elevator for obj in decoded[0])
    main.ApplyProject(decoded, None)
    main.sidebarTabs.setCurrentWidget(main.exportPanel)
    image = main.exportPanel.Render("png")
    assert not image.isNull() and SvgPreviewRenderer(main.exportPanel.Render("svg")).isValid()
    main.close()
    app.clipboard().clear()
    print("PASS: elevator placement, editing, architectural rendering/collisions, measurements, persistence and export")


if __name__ == "__main__":
    Main()
