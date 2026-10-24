"""Pillars merge as walls and retain rectangular sizing through handles/history."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Pillar, Wall, Stair, Counter
from planner_app.models import Furnishing
from theme import BuildStyle
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    app.processEvents()
    v, point = main.viewport, QtCore.QPointF
    v.unitsMode = "Adaptive Metric"  # Width/length edits below use centimeters/meters.
    v.snapEnabled = False
    v.newWallMaterial = "Brick"
    assert main.pillarButton.toolTip() == "Pillar" and not main.pillarButton.icon().isNull()
    mime = QtCore.QMimeData()
    mime.setData("application/x-planner-pillar", b"pillar")
    position = v.WorldToViewport(point())
    enter = QtGui.QDragEnterEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    app.sendEvent(v, enter)
    move = QtGui.QDragMoveEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    app.sendEvent(v, move)
    assert isinstance(v.arrowPreview, Pillar) and v.arrowPreview.material == "Brick"
    v.grab()
    drop = QtGui.QDropEvent(position, QtCore.Qt.DropAction.CopyAction, mime,
        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    app.sendEvent(v, drop)
    assert drop.isAccepted() and len(v.walls) == 1
    pillar = v.walls[0]
    assert type(pillar) is Pillar and pillar.width == pillar.length == 300 and pillar.material == "Brick"
    assert "Pillar (#" in main.selectionLabel.text() and pillar.objectId is not None
    assert not main.materialField.isHidden() and main.vertexProperties.isHidden()
    assert v.HitTest(v.WorldToViewport(pillar.firstVertex)) == (pillar, None)
    assert len(v.VisibleFurnishingHandles()) == 1 and not v.AttachedVertices(pillar)
    main.sizeLinkButton.setChecked(False)  # Independent dimension editing is tested here.
    main.EditProperty("width", 60)
    main.EditProperty("length", .9)
    main.EditProperty("angle", 37)
    assert pillar.width == 600 and abs(pillar.length - 900) < 1e-6 and abs(pillar.angle - 37) < 1e-6
    assert (pillar.firstVertex + pillar.secondVertex) / 2 == point()
    main.EditMaterial("Concrete")
    assert pillar.material == "Concrete"
    main.RefreshVisibilityCounts()
    assert main.visibilityItems["Walls"].text(0) == "Walls (1 object)"
    # Four corners and the center supply snaps, with no axis endpoint targets.
    v.SetSelection([])
    targets = list(v.SnapVertices())
    assert targets == v.ObjectCorners(pillar)
    assert pillar.firstVertex not in targets and pillar.secondVertex not in targets
    assert point() in list(v.SnapMidpoints())
    v.SetSelection([(pillar, None)])
    # Resize is local to the rotated rectangle; Right Mouse cancels all geometry.
    handle = next(handle for handle in v.FurnishingHandles(pillar) if handle[:3] == ("resize", "width", 1))
    start = handle[3]
    end = start + QtCore.QPointF(100, 30)
    original = (point(pillar.firstVertex), point(pillar.secondVertex), pillar.width)
    v.BeginFurnishingHandleDrag(pillar, handle, start)
    v.UpdateInteraction(end, QtCore.Qt.KeyboardModifier.NoModifier)
    assert pillar.width != original[2]
    v.CancelInteraction()
    assert (pillar.firstVertex, pillar.secondVertex, pillar.width) == original
    v.BeginFurnishingHandleDrag(pillar, handle, start)
    v.UpdateInteraction(end, QtCore.Qt.KeyboardModifier.NoModifier)
    release = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonRelease, end,
        QtCore.QPointF(v.mapToGlobal(end.toPoint())), QtCore.Qt.MouseButton.LeftButton,
        QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier)
    app.sendEvent(v, release)
    resized = (point(pillar.firstVertex), point(pillar.secondVertex), pillar.width)
    v.Undo()
    assert (pillar.firstVertex, pillar.secondVertex, pillar.width) == original
    v.Redo()
    assert (pillar.firstVertex, pillar.secondVertex, pillar.width) == resized
    # Pillars merge with walls, without participating in endpoint miter rays.
    pillar.angle = 0
    pillar.width = 600
    pillar.firstVertex, pillar.secondVertex = point(0, -300), point(0, 300)
    wall = Wall(point(-1800, 0), point(1800, 0), 240, material = "Concrete")
    v.walls = [wall, pillar]
    path = v.ConnectedWallPath(v.walls)
    assert path.contains(v.WorldToViewport(point(0, 250)))
    assert not path.contains(v.WorldToViewport(point(350, 250)))
    assert v.WallFits(pillar)
    # Pillar material wins over crossing walls in either scene order, even
    # when the wall is selected or shares a material with another object.
    wall.material = "Brick"
    for objects in ([wall, pillar], [pillar, wall]):
        v.walls = objects
        v.SetSelection([(wall, None)])
        v.grab()
        origin = point()
        assert v.wallMaterialPaths[id(pillar)].contains(origin)
        assert not v.wallMaterialPaths[id(wall)].contains(origin)
        assert v.materialPaths["Concrete"].contains(origin)
        assert not v.materialPaths["Brick"].contains(origin)
        assert v.HitTest(v.WorldToViewport(point())) == (wall, None)
        assert v.HitTest(v.WorldToViewport(point(250, 0))) == (wall, None)
        v.SetSelection([])
        assert v.HitTest(v.WorldToViewport(point())) == (pillar, None)
        # Selected endpoint handles remain reachable through the pillar footprint.
        endpointWall = Wall(point(), point(1800, 0), 240)
        v.walls = objects + [endpointWall]
        v.SetSelection([(endpointWall, 0)])
        assert v.HitTest(v.WorldToViewport(point())) == (endpointWall, 0)
        v.walls = objects
    v.SetSelection([(pillar, None)])
    v.grab()
    assert len(v.WallDimensions([pillar], v.ConnectedWallPath([pillar]), [])) == 4
    for cls in (Stair, Counter):
        other = cls(point(-1000, 0), point(1000, 0))
        assert v.JoinedObjectsOverlap(pillar, other)
    furnishing = Furnishing(v.furnishingDefinitions["desk"], point())
    assert v.JoinedObjectsOverlap(pillar, furnishing)
    v.furnishings = [furnishing]
    assert not v.WallFits(pillar)
    v.furnishings = []
    # Normal body dragging duplicates pillars rather than extruding control vertices.
    v.walls = [pillar]
    v.SetSelection([(pillar, None)])
    Drag(v, v.WorldToViewport(point()).toPoint(), v.WorldToViewport(point(1000, 500)).toPoint(),
        QtCore.Qt.KeyboardModifier.ShiftModifier)
    assert len(v.walls) == 2 and all(type(obj) is Pillar for obj in v.walls)
    clone = v.selectedWall
    assert clone.material == pillar.material and clone.width == pillar.width
    assert v.CopySelection() and v.PasteSelection()
    assert type(v.selectedWall) is Pillar and v.selectedWall.material == pillar.material
    with tempfile.TemporaryDirectory() as directory:
        filename = Path(directory) / "pillars.plan"
        assert main.SaveProject(filename)
        assert main.NewProject() and main.OpenProject(filename)
        assert len(v.walls) == 3 and all(type(obj) is Pillar for obj in v.walls)
        assert all(obj.material == "Concrete" for obj in v.walls)
    pillar = v.walls[0]
    v.walls = [pillar, wall]
    v.SetSelection([(pillar, None)])
    main.grab().save(str(Path(__file__).resolve().parents[1] / "screenshots" / "pillars.png"))
    main.close()
    app.clipboard().clear()


if __name__ == "__main__":
    Main()
