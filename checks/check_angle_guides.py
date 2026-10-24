"""Free angular annotation placement, three-point editing, snap isolation and persistence."""
import math
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets, QtTest
from planner import MainWindow
from planner_app.models import AngleGuide, ObjectControlPoints, Wall
from planner_app.project_codec import DecodeProject
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.path_operations import Paths
from planner_app.export_plan import RenderPlan
from planner_app.export_bounds import AutomaticBounds
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    point = QtCore.QPointF
    none = QtCore.Qt.KeyboardModifier.NoModifier
    v.snapEnabled = False
    assert not main.angleGuideButton.icon().isNull()
    annotationButtons = main.buildObjectLayouts["Annotations"]
    assert annotationButtons.count() == 5
    mime = QtCore.QMimeData()
    mime.setData("application/x-planner-angle-guide", b"angle-guide")
    position = v.WorldToViewport(point())
    enter = QtGui.QDragEnterEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime, QtCore.Qt.MouseButton.LeftButton, none)
    app.sendEvent(v, enter)
    move = QtGui.QDragMoveEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime, QtCore.Qt.MouseButton.LeftButton, none)
    app.sendEvent(v, move)
    assert enter.isAccepted() and isinstance(v.arrowPreview, AngleGuide)
    v.grab()
    drop = QtGui.QDropEvent(position, QtCore.Qt.DropAction.CopyAction, mime, QtCore.Qt.MouseButton.LeftButton, none)
    app.sendEvent(v, drop)
    assert drop.isAccepted() and len(v.walls) == 1
    guide = v.walls[0]
    assert guide.angle == 90 and guide.width == 0 and guide.objectId is not None
    assert main.selectionLabel.text().startswith("Angle Guide (#") and "90" not in main.selectionLabel.text()
    assert main.angleGuideAngleField.value() == 90
    original = tuple(point(vertex) for vertex in ObjectControlPoints(guide))
    # Construction arms are selection-only. Standalone marker ends get short
    # radial extensions, suppressed independently by aligned visible geometry.
    middle = v.WorldToViewport(guide.middleVertex)
    firstArm = v.WorldToViewport(guide.firstVertex) - middle
    lastArm = v.WorldToViewport(guide.secondVertex) - middle
    radius = 12
    firstDirection = firstArm / firstArm.manhattanLength()
    lastDirection = lastArm / lastArm.manhattanLength()
    firstMarker = middle + firstDirection * (radius + 9)
    lastMarker = middle + lastDirection * (radius + 9)
    armProbe = middle + firstArm * .4
    stroke = Paths.PrepareStroke(width = 2)
    assert Paths.Contains(stroke(v.AngleLayout(guide)[0]), armProbe)
    v.SetSelection([])
    path = stroke(v.AngleLayout(guide)[0])
    assert not Paths.Contains(path, armProbe)
    assert Paths.Contains(path, firstMarker) and Paths.Contains(path, lastMarker)
    assert v.HitTest(armProbe)[0] is None, "An invisible construction arm must not remain a body hit target"
    reference = Wall(point(-200, 0), point(1800, 0), width = 100)
    v.walls.append(reference)
    path = stroke(v.AngleLayout(guide)[0])
    assert not Paths.Contains(path, firstMarker) and Paths.Contains(path, lastMarker)
    v.visibility["Walls"] = False
    assert Paths.Contains(stroke(v.AngleLayout(guide)[0]), firstMarker), "Hidden geometry cannot explain an arc end"
    v.visibility["Walls"] = True
    v.walls = [guide, Wall(point(860, -500), point(860, 500), width = 100)]
    assert Paths.Contains(stroke(v.AngleLayout(guide)[0]), firstMarker), "A crossing edge cannot replace the angle direction"
    v.walls = [guide]
    v.SetSelection([(guide, None)])
    # The middle handle carries its two children with one rigid translation.
    delta = point(-500, -400)
    Drag(v, v.WorldToViewport(guide.middleVertex).toPoint(), v.WorldToViewport(guide.middleVertex + delta).toPoint())
    for actual, before in zip(ObjectControlPoints(guide), original):
        assert QtCore.QLineF(actual, before + delta).length() < 10, (actual, before + delta)
    assert math.isclose(guide.angle, 90)
    v.Undo()
    assert ObjectControlPoints(guide) == original
    # Whole-body duplication retains the middle point; Delete and Undo retain
    # the entire annotation rather than treating a selected handle as an object.
    v.SetSelection([(guide, None)])
    arcStart = v.WorldToViewport(guide.middleVertex) + point(150, 0)
    assert v.HitTest(arcStart)[0] is guide and v.HitTest(arcStart)[1] is None
    Drag(v, arcStart.toPoint(), (arcStart + point(-80, 120)).toPoint(), QtCore.Qt.KeyboardModifier.ShiftModifier)
    assert len(v.walls) == 2 and math.isclose(v.walls[-1].angle, 90)
    assert v.walls[-1].firstVertex - v.walls[-1].middleVertex == guide.firstVertex - guide.middleVertex
    v.Undo()
    assert len(v.walls) == 1
    v.SetSelection([(guide, 2)])
    v.DeleteSelected()
    assert not v.walls
    v.Undo()
    assert v.walls[0] is guide and ObjectControlPoints(guide) == original
    v.Redo()
    v.Undo()
    # An outer point changes only its own arm.
    target = guide.firstVertex + point(0, -600)
    Drag(v, v.WorldToViewport(guide.firstVertex).toPoint(), v.WorldToViewport(target).toPoint())
    assert QtCore.QLineF(guide.firstVertex, target).length() < 10
    assert guide.secondVertex == original[1] and guide.middleVertex == original[2]
    assert 90 < guide.angle < 180
    v.Undo()
    # Snap only the handle being moved. The stationary handles cannot attract it.
    v.snapEnabled = True
    v.gridSnapEnabled = v.midpointSnapEnabled = False
    v.alignmentSnapEnabled = False
    start = v.WorldToViewport(guide.firstVertex).toPoint()
    nearMiddle = v.WorldToViewport(guide.middleVertex) + point(4, 3)
    QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, none, start)
    v.UpdateInteraction(nearMiddle, none)
    assert not v.snapApplied and QtCore.QLineF(guide.firstVertex, guide.middleVertex).length() > 1
    assert not list(v.SnapVertices()) and not v.StairSnapTargets(guide) and not list(v.SnapMidpoints())
    v.CancelInteraction()
    assert ObjectControlPoints(guide) == original
    # An external control point remains eligible.
    wall = Wall(point(1200, -500), point(1200, -1500))
    v.walls.append(wall)
    Drag(v, v.WorldToViewport(guide.firstVertex).toPoint(), (v.WorldToViewport(wall.firstVertex) + point(3, 2)).toPoint())
    assert QtCore.QLineF(guide.firstVertex, wall.firstVertex).length() < 1e-5
    assert guide.secondVertex == original[1] and guide.middleVertex == original[2]
    v.Undo()
    v.walls = [guide]
    v.snapEnabled = False
    # Text is independently draggable and retains horizontal layout with a leader.
    v.SetSelection([(guide, None)])
    path, rect, label, arcMiddle = v.AngleLayout(guide)
    Drag(v, rect.center().toPoint(), (rect.center() + point(80, -40)).toPoint())
    assert guide.textOffset.manhattanLength() > 1 and ObjectControlPoints(guide) == original
    v.Undo()
    assert guide.textOffset == point()
    v.SetSelection([(guide, 3)])
    v.NudgeSelection(QtCore.Qt.Key.Key_Right)
    assert guide.textOffset.x() > 0 and ObjectControlPoints(guide) == original
    v.Undo()
    assert guide.textOffset == point()
    # Collapsed arms are valid editable annotations; their value disappears.
    before = v.CaptureState()
    guide.firstVertex = point(guide.middleVertex)
    v.RecordEdit(before)
    assert guide.angle is None and v.AngleLayout(guide)[2] == ""
    assert v.OpeningsValid()
    decoded = DecodeProject(main.BuildProjectData(), v.furnishingDefinitions)
    assert decoded[0][0].angle is None
    v.Undo()
    guide.secondVertex = point(-900, 0)
    assert guide.angle == 180 and v.AngleLayout(guide)[2] == "180°"
    guide.secondVertex = point(original[1])
    # Smaller-angle selection works in every quadrant and either endpoint order.
    for degrees in (0, 30, 90, 135, 179, 180, 181, 225, 270, 330):
        guide.secondVertex = point(900 * math.cos(math.radians(degrees)), 900 * math.sin(math.radians(degrees)))
        assert math.isclose(guide.angle, min(degrees, 360 - degrees), abs_tol = 1e-6)
    guide.secondVertex = point(original[1])
    v.SetSelection([(guide, None)])
    assert v.CopySelection() and v.ReadClipboardSelection()["objects"][0]["type"] == "AngleGuide"
    assert v.PasteSelection(v.WorldToViewport(point(-1200, -1200)))
    copy = v.walls[-1]
    assert copy is not guide and math.isclose(copy.angle, guide.angle)
    assert copy.firstVertex - copy.middleVertex == guide.firstVertex - guide.middleVertex
    v.Undo()
    assert len(v.walls) == 1
    v.SetSelection([(guide, None)])
    assert v.MoveSpecial(200, -100, 45) is None
    assert math.isclose(guide.angle, 90)
    v.Undo()
    assert ObjectControlPoints(guide) == original
    # Persist the third point, label placement and edit history, then replay it.
    before = v.CaptureState()
    guide.middleVertex += point(100, 50)
    guide.textOffset = point(250, -100)
    v.RecordEdit(before)
    saved = tuple(point(vertex) for vertex in ObjectControlPoints(guide))
    with tempfile.TemporaryDirectory() as folder:
        file = Path(folder) / "Angles.plan"
        assert main.SaveProject(file)
        assert main.NewProject() and main.OpenProject(file)
        guide = v.walls[0]
        assert isinstance(guide, AngleGuide) and ObjectControlPoints(guide) == saved and guide.textOffset == point(250, -100)
        v.Undo()
        assert ObjectControlPoints(guide) == original and guide.textOffset == point()
        v.Redo()
        assert ObjectControlPoints(guide) == saved
    v.visibility["Measurement guides"] = False
    assert not v.IsObjectVisible(guide)
    v.visibility["Measurement guides"] = True
    v.SetSelection([(guide, None)])
    v.showMeasurements = False
    # Angular annotations survive PNG and SVG export with automatic dimensions off.
    data = main.BuildProjectData()
    image = RenderPlan("Angles.plan", 200, (-2000, -2000, 5000, 5000), projectData = data, applyTheme = False)
    assert not image.isNull()
    svg = RenderPlan("Angles.plan", 200, (-2000, -2000, 5000, 5000), projectData = data, applyTheme = False, outputFormat = "svg")
    assert b"<svg" in svg and b"<path" in svg
    data["settings"]["visibility"]["Measurement guides"] = False
    hidden = RenderPlan("Angles.plan", 200, (-2000, -2000, 5000, 5000), projectData = data, applyTheme = False)
    assert image != hidden
    hiddenSvg = RenderPlan("Angles.plan", 200, (-2000, -2000, 5000, 5000), projectData = data, applyTheme = False, outputFormat = "svg")
    assert len(svg) > len(hiddenSvg) + 100, "Angle geometry and text outlines are missing from SVG export"
    image.save(str(root / "diagnostics/angle-guide-export.png"))
    offset = point(guide.textOffset)
    guide.textOffset = point(20000, 20000)
    x, y, width, height = AutomaticBounds(v)
    assert x + width > 19000 and y + height > 19000, "Automatic crop lost an independently positioned angle label"
    guide.textOffset = offset
    app.processEvents()
    main.buildScrollArea.verticalScrollBar().setValue(main.buildScrollArea.verticalScrollBar().maximum())
    app.processEvents()
    main.grab().save(str(root / "diagnostics/angle-guides.png"))
    app.clipboard().clear()
    main.MarkProjectClean()
    main.close()
    print("PASS: angle placement, three handles, snap isolation, collapsed arms, text, transforms, clipboard, history and project round-trip")


if __name__ == "__main__":
    Main()
