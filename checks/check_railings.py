"""Railing sizing, joins, collision exclusions, display, persistence and history."""
import copy
import math
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall, Railing, Stair, Counter
from planner_app.project_codec import DecodeProject
from theme import BuildStyle
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    app.processEvents()
    v, point = main.viewport, QtCore.QPointF
    v.snapEnabled = False
    railing = Railing(point(), point(3600, 0))
    assert railing.width == 80 and railing.postCount == 4 and railing.segmentWidth == 1200
    for length in (100, 900, 1500, 1800, 2400, 3600, 4800):
        railing.secondVertex = point(length, 0)
        assert railing.postCount >= 2
        assert abs(railing.segmentWidth * (railing.postCount - 1) - length) < 1e-6
    railing.secondVertex = point(3600, 0)
    v.walls = [railing]
    v.SetSelection([(railing, None)])
    assert main.railingButton.toolTip() == "Railing" and not main.railingButton.icon().isNull()
    assert "Railing (#" in main.selectionLabel.text()
    assert main.wallProperties.layout().labelForField(main.stairStepWidgets["stepCount"]).text() == "Post Count"
    assert main.stairDirectionButton.isHidden() and main.materialField.isHidden()
    main.EditStairAutosize(False)
    assert railing.manualPostCount == 4
    main.EditProperty("stepCount", 5)
    assert railing.postCount == 5 and railing.segmentWidth == 900
    main.EditProperty("stepSize", 1200)  # Current project units are millimeters.
    assert railing.postCount == 4 and railing.segmentWidth == 1200
    before = v.CaptureState()
    railing.secondVertex = point(4800, 0)
    v.RecordEdit(before)
    assert railing.postCount == 4 and railing.segmentWidth == 1600
    v.Undo()
    assert railing.postCount == 4 and railing.segmentWidth == 1200
    v.Redo()
    main.EditStairAutosize(True)
    assert railing.postCount == 5
    second = Railing(point(4800, 0), point(4800, 2400))
    wall = Wall(point(), point(4800, 0))
    stair = Stair(point(), point(4800, 0))
    counter = Counter(point(), point(4800, 0))
    v.walls = [railing, second, wall, stair, counter]
    v.EnsureObjectIds()
    for other in (wall, stair, counter):
        assert not v.ObjectsOverlap(railing, other)
        assert not v.JoinedObjectsOverlap(other, railing)
    from planner_app.models import Furnishing
    furnishing = Furnishing(v.furnishingDefinitions["desk"], point(1200, 0))
    assert v.JoinedObjectsOverlap(railing, furnishing)
    v.furnishings = [furnishing]
    assert not v.WallFits(railing)
    v.furnishings = []
    assert v.WallFits(railing)
    v.selectedVertex = 1
    attached = v.AttachedVertices(railing)
    assert [(obj, index) for obj, index, original in attached] == [(second, 0)]
    v.snapEnabled = True
    v.SetSelection([(railing, 1)])
    v.dragVertices = (point(railing.firstVertex), point(railing.secondVertex))
    assert v.SnapStairVertex(point(4790, 10), railing.firstVertex, railing, QtCore.Qt.KeyboardModifier.NoModifier) == second.firstVertex
    v.dragVertices = None
    v.snapEnabled = False
    v.walls = [railing, second]
    path, dimensions = v.ConnectedRailingPath(v.walls)
    assert path.contains(v.WorldToViewport(second.firstVertex)) and dimensions
    # Post corners fill the join, with thin bars leaving gaps beside them.
    assert path.contains(v.WorldToViewport(point(4800 + 30, 30)))
    assert not path.contains(v.WorldToViewport(point(400, 35)))
    assert path.contains(v.WorldToViewport(point(1200, 30)))
    # Unequal angled runs terminate at one post, without wall-style miter wedges.
    direction = point(math.cos(math.radians(37)), math.sin(math.radians(37)))
    lowerDirection = point(-math.cos(math.radians(65)), -math.sin(math.radians(65)))
    junction = [Railing(point(-1000, 0), point(), 40, autosize = False),
                Railing(point(), direction * 1000, 320, autosize = False),
                Railing(point(), lowerDirection * 1000, 80, autosize = False)]
    expected = QtGui.QPainterPath()
    for obj in junction:
        run = obj.secondVertex - obj.firstVertex
        length = QtCore.QLineF(obj.firstVertex, obj.secondVertex).length()
        angle = math.degrees(math.atan2(run.y(), run.x()))
        transform = QtGui.QTransform().translate(obj.firstVertex.x(), obj.firstVertex.y()).rotate(angle)
        bar = QtGui.QPainterPath()
        bar.addRect(QtCore.QRectF(0, -obj.width * .75 / 2, length, obj.width * .75))
        expected = expected.united(transform.map(bar))
        for vertex in (obj.firstVertex, obj.secondVertex):
            if vertex == point():
                continue
            post = QtGui.QPainterPath()
            post.addRect(QtCore.QRectF(-obj.width / 2, -obj.width / 2, obj.width, obj.width))
            expected = expected.united(QtGui.QTransform().translate(vertex.x(), vertex.y()).rotate(angle).map(post))
    sharedPost = QtGui.QPainterPath()
    sharedPost.addRect(QtCore.QRectF(-160, -160, 320, 320))
    expected = expected.united(QtGui.QTransform().rotate(37).map(sharedPost))
    for members in (junction, list(reversed(junction))):
        v.ConnectedRailingPath(members, includeMeasurements = False)
        toBase = QtGui.QTransform().scale(v.basePixelsPerMillimeter, -v.basePixelsPerMillimeter)
        for x in range(-1150, 1151, 25):
            for y in range(-1150, 1151, 25):
                position = point(x + .3, y + .7)
                assert v.railingSymbolPath.contains(toBase.map(position)) == expected.contains(position), (x, y)
        normal = point(-direction.y(), direction.x())
        assert v.railingPostOutlinePath.contains(toBase.map((direction + normal) * 150))
    v.grab()
    # Cutters split railing measurements using the same boundary rules as walls.
    v.DeselectAll()
    cutter = Counter(point(1500, 340), point(2500, 340))
    v.walls = [railing, cutter]
    v.measurementSettings["counters"] = 0
    path, cutDimensions = v.ConnectedRailingPath([railing])
    assert len(cutDimensions) > len(v.ConnectedRailingPath([railing], False)[1])
    lengths = sorted(round(QtCore.QLineF(first, last).length()) for first, last, owners in cutDimensions)
    assert lengths == [1000, 1500, 2300, 4800], lengths
    v.SetSelection([(railing, None)])
    selectedDimensions = v.ConnectedRailingPath([railing])[1]
    assert sorted(round(QtCore.QLineF(first, last).length()) for first, last, owners in selectedDimensions) == [4800, 4800]
    # Project-specific bounds and units drive both labels and editable fields.
    main.ShowSettings()
    panel = main.settingsWindow
    panel.SetRailingSizing("target", 110, canonical = True)
    assert railing.spacingBounds == (900, 1500, 1100)
    panel.SetUnitsMode("Millimeters")
    assert panel.railingSizingFields["target"].value() == 1100
    main.EditStairAutosize(False)
    main.EditProperty("stepCount", 7)
    assert railing.manualPostCount == 7
    v.SetSelection([(railing, None)])
    assert v.CopySelection() and v.PasteSelection()
    pasted = v.selectedWall
    assert type(pasted) is Railing and not pasted.autosize and pasted.manualPostCount == 7
    with tempfile.TemporaryDirectory() as directory:
        filename = Path(directory) / "railings.plan"
        assert main.SaveProject(filename)
        assert main.NewProject()
        assert main.OpenProject(filename)
        restored = [obj for obj in v.walls if isinstance(obj, Railing)]
        assert any(not obj.autosize and obj.manualPostCount == 7 for obj in restored)
        assert v.railingSpacings["target"] == 110
    invalid = copy.deepcopy(main.BuildProjectData())
    legacy = copy.deepcopy(invalid)
    del legacy["settings"]["railingSpacings"]
    del legacy["settings"]["visibility"]["Railings"]
    legacySettings = DecodeProject(legacy, v.furnishingDefinitions)[5]
    assert legacySettings["railingSpacings"] == {"minimum": 90, "maximum": 150, "target": 120}
    assert legacySettings["visibility"]["Railings"]
    record = next(record for record in invalid["scene"]["objects"] if record["type"] == "Railing")
    record["manualPostCount"] = 1
    try:
        DecodeProject(invalid, v.furnishingDefinitions)
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid railing post count accepted")
    # Dragging a vertex with Shift extrudes and retains manual sizing.
    pasted.firstVertex, pasted.secondVertex = point(-500, 0), point(500, 0)
    v.walls = [pasted]
    v.SetSelection([(pasted, 1)])
    anchor = point(pasted.secondVertex)
    Drag(v, v.WorldToViewport(anchor).toPoint(), v.WorldToViewport(anchor + point(0, 1000)).toPoint(),
         QtCore.Qt.KeyboardModifier.ShiftModifier)
    assert len(v.walls) == 2 and v.walls[-1].manualPostCount == 7 and not v.walls[-1].autosize, (len(v.walls), v.selectedWall)
    # Palette drag/drop uses the normal cancellable preview lifecycle.
    v.walls = []
    mime = QtCore.QMimeData()
    mime.setData("application/x-planner-railing", b"railing")
    position = v.WorldToViewport(point())
    enter = QtGui.QDragEnterEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    app.sendEvent(v, enter)
    assert enter.isAccepted()
    move = QtGui.QDragMoveEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    app.sendEvent(v, move)
    assert isinstance(v.arrowPreview, Railing)
    v.CancelInteraction()
    assert v.arrowPreview is None
    drop = QtGui.QDropEvent(position, QtCore.Qt.DropAction.CopyAction, mime,
        QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    app.sendEvent(v, drop)
    assert drop.isAccepted() and type(v.walls[0]) is Railing
    # Mixed railing values use the same placeholder contract as every object.
    first = Railing(point(-2000, 0), point(0, 0), autosize = False, manualPostCount = 3)
    second = Railing(point(0, 0), point(0, 2400), autosize = False, manualPostCount = 4)
    stair = Stair(point(-500, 0), point(500, 0))
    v.walls = [stair]
    v.SetSelection([(stair, None)])
    blocker = QtCore.QSignalBlocker(main.propertyFields["stepCount"])
    main.propertyFields["stepCount"].setValue(1)
    del blocker
    v.walls = [first, second]
    v.SetSelection([(first, None), (second, None)])
    assert first.manualPostCount == 3 and second.manualPostCount == 4
    assert main.propertyFields["stepCount"].lineEdit().placeholderText() == "(different)"
    # Preview an L-shaped railing over stairs/counters and below a crossing wall.
    panel.SetUnitsMode("Adaptive Metric")
    first.SetAutosize(True)
    second.SetAutosize(True)
    v.walls += [Counter(point(-2500, 0), point(300, 0)), Stair(point(0, -1000), point(0, 2700)),
                Wall(point(-1000, -800), point(-1000, 800))]
    v.SetSelection([(first, None)])
    v.showMeasurements = False
    app.processEvents()
    image = v.grab().toImage()
    wallPixel = v.WorldToViewport(point(-1000, 0)).toPoint()
    v.visibility["Railings"] = False
    withoutRailing = v.grab().toImage()
    assert image.pixelColor(wallPixel) == withoutRailing.pixelColor(wallPixel)
    v.visibility["Railings"] = True
    screenshot = Path(__file__).resolve().parents[1] / "screenshots" / "railings.png"
    main.grab().save(str(screenshot))
    panel.grab().save(str(screenshot.with_name("railing-settings.png")))
    main.close()
    app.clipboard().clear()


if __name__ == "__main__":
    Main()
