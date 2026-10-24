"""Arrow placement, chain tips, endpoint joins, appearance and persistence."""
import os
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Arrow, Wall, Counter, Stair
from planner_app.models import Label, Furnishing
from planner_app.graphics.theme import BuildStyle
from planner_app.graphics.arrows import ArrowPaths, ConnectedArrowDirections, ConnectedArrowCorners
from planner_app.project_codec import DecodeProject
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
    point = QtCore.QPointF
    # Both tails must fill the missing outer quarter at a shared right-angle
    # corner, even when rotated or authored in reverse scene order.
    for angle in range(0, 360, 15):
        transform = QtGui.QTransform().rotate(angle).translate(137, -83)
        for widths in ((40, 40), (20, 60)):
            incoming = Arrow(transform.map(point(0, 1000)), transform.map(point()), widths[0])
            outgoing = Arrow(transform.map(point()), transform.map(point(1000, 0)), widths[1])
            for arrows in ([incoming, outgoing], [outgoing, incoming]):
                directions = ConnectedArrowDirections(arrows)
                joins = ConnectedArrowCorners(arrows, directions)
                assert not directions[id(incoming)][2] and directions[id(outgoing)][2]
                merged = QtGui.QPainterPath()
                merged.setFillRule(QtCore.Qt.FillRule.WindingFill)
                for arrow in arrows:
                    first, second, showTip = directions[id(arrow)]
                    tail, head = ArrowPaths(first, second, arrow.width, arrow.solidTip, arrow.tipSize, 1,
                                            showTip, joins[id(arrow)])
                    merged.addPath(tail)
                    merged.addPath(head)
                corner = transform.map(point(-widths[0] * .45, -widths[1] * .45))
                assert merged.contains(corner), (angle, widths)
                assert not merged.contains(transform.map(point(-widths[0], -widths[1])))
    # Joining two starting vertices also merges tails without reversing arrows.
    north = Arrow(point(), point(0, 1000), 40)
    east = Arrow(point(), point(1000, 0), 40)
    directions = ConnectedArrowDirections([north, east])
    joins = ConnectedArrowCorners([north, east], directions)
    assert all(value[2] for value in directions.values())
    assert joins[id(north)] and joins[id(east)]
    # The actual added corner belongs to the adjoining arrow for hit testing.
    viewport.walls = [north, east]
    hitObject, vertexIndex = viewport.HitTest(viewport.WorldToViewport(point(-18, -18)))
    assert hitObject in (north, east)
    viewport.walls = []
    noModifiers = QtCore.Qt.KeyboardModifier.NoModifier
    left = QtCore.Qt.MouseButton.LeftButton
    main.snapButton.setChecked(False)
    assert not main.arrowButton.icon().isNull()
    mime = QtCore.QMimeData()
    mime.setData("application/x-planner-arrow", b"arrow")
    position = viewport.WorldToViewport(point())
    enter = QtGui.QDragEnterEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime, left, noModifiers)
    app.sendEvent(viewport, enter)
    move = QtGui.QDragMoveEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime, left, noModifiers)
    app.sendEvent(viewport, move)
    assert enter.isAccepted() and isinstance(viewport.arrowPreview, Arrow)
    viewport.grab()
    drop = QtGui.QDropEvent(position, QtCore.Qt.DropAction.CopyAction, mime, left, noModifiers)
    app.sendEvent(viewport, drop)
    assert drop.isAccepted() and viewport.arrowPreview is None
    arrow = viewport.walls[0]
    assert isinstance(arrow, Arrow) and arrow.objectId is not None
    assert main.arrowProperties.isVisible() and main.wallProperties.isHidden()
    propertiesLayout = main.arrowProperties.parentWidget().layout()
    assert propertiesLayout.indexOf(main.arrowProperties) < propertiesLayout.indexOf(main.vertexProperties)
    assert "Arrow (#" in main.selectionLabel.text()
    viewport.Undo()
    assert not viewport.walls
    viewport.Redo()
    assert viewport.walls[0] is arrow

    # Every endpoint pairing gets exact vertex priority over nearby grid/alignment.
    main.snapButton.setChecked(True)
    viewport.alignmentSnapEnabled = False
    viewport.midpointSnapEnabled = False
    for firstIndex in (0, 1):
        for secondIndex in (0, 1):
            target = point(147, 263)
            other = Arrow(target if secondIndex == 0 else point(600, 700),
                          target if secondIndex == 1 else point(600, 700))
            source = Arrow(point(-600, -300), point(-600, 400))
            viewport.walls = [source, other]
            viewport.SetSelection([(source, firstIndex)])
            opposite = source.secondVertex if firstIndex == 0 else source.firstVertex
            snapped = viewport.SnapStairVertex(target + point(4, 3), opposite, source, noModifiers)
            assert snapped == target and viewport.snapPriority == 0
    main.snapButton.setChecked(False)

    # Endpoint joins never reverse an arrow. Only a tip-to-tail continuation hides a head.
    first = Arrow(point(-1200, 0), point(0, 0))
    second = Arrow(point(1200, 0), point(0, 0))
    third = Arrow(point(1200, 0), point(1200, 1000))
    viewport.walls = [first, second, third]
    directions = ConnectedArrowDirections(viewport.walls)
    for arrow in viewport.walls:
        assert directions[id(arrow)] == (arrow.firstVertex, arrow.secondVertex, True)
    assert ConnectedArrowDirections([third])[id(third)] == (third.firstVertex, third.secondVertex, True)
    directed = [Arrow(point(-1000, 100), point(0, 0)), Arrow(point(0, 0), point(1000, 200)),
                Arrow(point(1000, 200), point(1000, 1000))]
    for ordered in (directed, list(reversed(directed)), [directed[1], directed[2], directed[0]]):
        directions = ConnectedArrowDirections(ordered)
        for index, arrow in enumerate(directed):
            assert directions[id(arrow)] == (arrow.firstVertex, arrow.secondVertex, index == 2)
    loop = directed + [Arrow(directed[-1].secondVertex, directed[0].firstVertex)]
    assert not any(showTip for start, end, showTip in ConnectedArrowDirections(loop).values())
    viewport.SetSelection([(first, 1)])
    Drag(viewport, viewport.WorldToViewport(point()).toPoint(), viewport.WorldToViewport(point(100, 100)).toPoint())
    assert first.secondVertex == second.secondVertex == point(100, 100)
    viewport.Undo()
    assert first.secondVertex == second.secondVertex == point()
    # Arrows cannot attach a wall at coincident endpoints.
    wall = Wall(point(), point(0, -1000))
    viewport.walls.append(wall)
    viewport.SetSelection([(first, 1)])
    assert all(isinstance(obj, Arrow) for obj, index, original in viewport.AttachedVertices(first))

    # Fixed-size heads, straight caps and sharp vertices at arbitrary run lengths.
    for solid in (True, False):
        smallTail, smallHead = ArrowPaths(point(), point(200, 0), 10, solid, 3, .2)
        longTail, longHead = ArrowPaths(point(), point(800, 0), 10, solid, 3, .2)
        shifted = QtGui.QTransform().translate(600, 0).map(smallHead)
        assert shifted == longHead
        assert smallTail.boundingRect().left() == 0
        assert all(smallHead.elementAt(index).type != QtGui.QPainterPath.ElementType.CurveToElement
                   for index in range(smallHead.elementCount()))
    assert Arrow(point(), point(200, 0)).tipSize == 60
    for solid in (True, False):
        thinTail, thinHead = ArrowPaths(point(), point(200, 0), 5, solid, 60, .2)
        thickTail, thickHead = ArrowPaths(point(), point(200, 0), 25, solid, 60, .2)
        assert thinHead.boundingRect() == thickHead.boundingRect()
        if solid:
            assert thinHead == thickHead
    for headSize in (.1, 30, 60, 193):
        solidTail, solidHead = ArrowPaths(point(), point(800, 0), 23, True, headSize, .2)
        openTail, openHead = ArrowPaths(point(), point(800, 0), 23, False, headSize, .2)
        assert openHead.boundingRect() == solidHead.boundingRect()
        assert openHead.subtracted(solidHead).isEmpty()
    # Open-head bands must stay hollow and symmetric across angle, position and zoom.
    for angle in range(0, 360, 7):
        direction = point(math.cos(math.radians(angle)), math.sin(math.radians(angle)))
        normal = point(-direction.y(), direction.x())
        for offset in (point(), point(613.25, 86.125), point(-12345.625, 9876.25)):
            for scale in (.04, .2, 2):
                tip = offset + direction * 530
                tail, head = ArrowPaths(offset, tip, 24, False, 24 * 15.99, scale)
                halfWidth = 24 * 15.99 * scale / 2
                headLength = halfWidth * 24 / 7
                base = tip - direction * headLength
                assert not head.contains(base + direction * (headLength / 2))
                for side in (-1, 1):
                    sample = base + direction * (headLength / 2) + normal * (side * (halfWidth / 2 - 24 * scale * .3))
                    assert head.contains(sample)
                path = QtGui.QPainterPath(tail)
                path.setFillRule(QtCore.Qt.FillRule.WindingFill)
                path.addPath(head)
                assert path.contains(tip - direction * (24 * scale))
                assert not tail.contains(tip - direction * (.1 * 24 * scale))
                for polygon in tail.toSubpathPolygons():
                    for vertex in polygon:
                        depth = QtCore.QPointF.dotProduct(tip - vertex, direction)
                        if depth <= headLength:
                            across = abs(QtCore.QPointF.dotProduct(vertex - tip, normal))
                            assert across <= halfWidth * depth / headLength + 1e-7

    # No collision in either direction; arrows also leave counter dimensions intact.
    arrow = Arrow(point(-500, 0), point(500, 0))
    arrow.solidTip, arrow.tipSize, arrow.intensity = False, 80, .7
    viewport.walls = [arrow]
    blockers = [Wall(point(-500, 0), point(500, 0)), Counter(point(-500, 0), point(500, 0)),
                Stair(point(-500, 0), point(500, 0)), Label(), Furnishing(viewport.furnishingDefinitions["desk"])]
    for blocker in blockers:
        assert not viewport.ObjectsOverlap(arrow, blocker)
        assert not viewport.JoinedObjectsOverlap(blocker, arrow)
    viewport.walls.append(blockers[0])
    viewport.SetSelection([(arrow, None)])
    Drag(viewport, viewport.WorldToViewport(point()).toPoint(), viewport.WorldToViewport(point(0, 200)).toPoint())
    assert arrow.firstVertex == point(-500, 200)
    viewport.Undo()
    assert arrow.firstVertex == point(-500, 0)
    viewport.walls = [arrow]

    # Appearance edits are undoable and all measurement display modes are honored.
    viewport.SetSelection([(arrow, None)])
    main.arrowFields["width"].setValue(20)
    assert arrow.width == 20 and arrow.tipSize == 80
    viewport.Undo()
    assert arrow.width == 10
    main.arrowFields["solidTip"].setChecked(True)
    assert arrow.solidTip and main.arrowFields["tipSize"].suffix() == " mm"
    viewport.Undo()
    assert not arrow.solidTip
    assert main.arrowFields["tipSize"].suffix() == " mm" and main.arrowFields["tipSize"].value() == arrow.tipSize
    main.arrowFields["intensity"].setValue(45)
    assert arrow.intensity == .45
    viewport.Undo()
    for mode, suffix in (("Meters", " m"), ("Centimeters", " cm"), ("Millimeters", " mm")):
        viewport.unitsMode = mode
        main.RefreshProperties()
        assert main.arrowFields["width"].suffix() == suffix
        assert main.arrowFields["tipSize"].suffix() == suffix
    viewport.unitsMode = "Adaptive Metric"
    main.RefreshProperties()
    main.arrowFields["length"].setValue(1.5)
    assert QtCore.QLineF(arrow.firstVertex, arrow.secondVertex).length() == 1500
    viewport.Undo()

    # Multi-selection appearance and Shift copies retain custom values.
    second = Arrow(point(-500, 1000), point(500, 1000))
    viewport.walls.append(second)
    viewport.SetSelection([(arrow, None), (second, None)])
    main.arrowFields["width"].setValue(15)
    assert arrow.width == second.width == 15
    viewport.Undo()
    viewport.SetSelection([(arrow, None)])
    Drag(viewport, viewport.WorldToViewport(point()).toPoint(), viewport.WorldToViewport(point(0, -300)).toPoint(),
         QtCore.Qt.KeyboardModifier.ShiftModifier)
    copy = viewport.selectedWall
    assert copy is not arrow and (copy.solidTip, copy.tipSize, copy.intensity) == (arrow.solidTip, arrow.tipSize, arrow.intensity)
    viewport.Undo()
    viewport.SetSelection([(arrow, None)])
    try:
        assert viewport.CopySelection() and viewport.ReadClipboardSelection() is not None
        assert viewport.PasteSelection(viewport.WorldToViewport(point()))
        copy = viewport.selectedWall
        assert isinstance(copy, Arrow) and copy.tipSize == arrow.tipSize and copy.intensity == arrow.intensity
        viewport.Undo()
    finally:
        app.clipboard().clear()
        app.processEvents()
    data = main.BuildProjectData()
    decoded = DecodeProject(data, viewport.furnishingDefinitions)
    restored = decoded[0][0]
    assert isinstance(restored, Arrow) and (restored.solidTip, restored.tipSize, restored.intensity) == (arrow.solidTip, arrow.tipSize, arrow.intensity)
    legacy = data["scene"]["objects"][0]
    legacy.pop("tipSizeMode")
    legacy["tipSize"] = 193
    assert DecodeProject(data, viewport.furnishingDefinitions)[0][0].tipSize == 35
    legacy["tipSizeMode"] = "multiplier"
    legacy["tipSize"] = 6
    assert DecodeProject(data, viewport.furnishingDefinitions)[0][0].tipSize == 6 * arrow.width
    legacy.pop("tipSizeMode")
    legacy["solidTip"] = True
    assert DecodeProject(data, viewport.furnishingDefinitions)[0][0].tipSize == 6 * arrow.width
    viewport.visibility["Walls"] = False
    assert viewport.IsObjectVisible(arrow)
    viewport.visibility["Arrows"] = False
    assert not viewport.IsObjectVisible(arrow)
    viewport.visibility["Arrows"] = True
    assert main.WriteSession(wait = True)
    main.close()
    main = MainWindow()
    main.show()
    app.processEvents()
    assert any(isinstance(obj, Arrow) for obj in main.viewport.walls)
    main.viewport.walls = [Arrow(point(-1200, 550), point(1000, 1100)),
                           Arrow(point(-1000, 0), point(0, 0)), Arrow(point(1000, 0), point(0, 0)),
                           Arrow(point(1000, 0), point(1000, -700))]
    main.viewport.walls[0].width = 24
    main.viewport.walls[0].solidTip = False
    main.viewport.walls[0].tipSize = 24 * 15.99
    main.viewport.SetSelection([(main.viewport.walls[0], None)])
    main.resize(1500, 950)
    main.mainSplitter.setSizes([1000, 500])
    app.processEvents()
    main.viewport.grab().save("screenshots/arrows.png")
    main.close()
    print("PASS: arrow placement, all endpoint joins, terminal tips, movement, properties, copy/paste and recovery")


if __name__ == "__main__":
    Main()
