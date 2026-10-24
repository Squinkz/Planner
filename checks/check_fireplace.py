"""Wall-bound fireplaces: depth snapping, resizing, persistence and vector output."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets, QtTest
from planner import MainWindow, Wall, Fireplace
from planner_app.project_codec import DecodeProject
from planner_app.graphics.svg_preview import SvgPreviewRenderer
from planner_app.graphics.fireplace import FireplacePath
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.resize(1300, 900)
    main.show()
    app.processEvents()
    v = main.viewport
    v.unitsMode = "Adaptive Metric"  # Property edits below use centimeters and meters.
    v.snapEnabled = False
    wall = Wall(QtCore.QPointF(-2500, 0), QtCore.QPointF(2500, 0), 240)
    v.walls = [wall]
    v.EnsureObjectIds()
    main.ShowSettings()
    settings = main.settingsWindow
    assert settings.sizeFields["Fireplace"].value() == 120
    settings.sizeFields["Fireplace"].setValue(144)
    configured = v.FindFireplacePlacement(v.WorldToViewport(QtCore.QPointF()), QtCore.Qt.KeyboardModifier.NoModifier)
    assert abs(configured.width - 1440) < .001 and abs(configured.depth - 600) < .001
    legacy = main.BuildProjectData()
    legacy["settings"]["buildSettings"]["miscSizes"].pop("Fireplace")
    assert DecodeProject(legacy, v.furnishingDefinitions)[5]["buildSettings"]["miscSizes"]["Fireplace"] == 120
    settings.buildResetButtons["Fireplace"].click()
    assert v.miscDefaultSizes["Fireplace"] == 120
    settings.hide()
    point = v.WorldToViewport(QtCore.QPointF(0, -100))
    mime = QtCore.QMimeData()
    mime.setData("application/x-planner-fireplace", b"fireplace")
    enter = QtGui.QDragEnterEvent(point.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                                QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    v.dragEnterEvent(enter)
    assert enter.isAccepted()
    move = QtGui.QDragMoveEvent(point.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
                              QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    v.dragMoveEvent(move)
    assert isinstance(v.windowDropPreview, Fireplace)
    v.grab()
    drop = QtGui.QDropEvent(point, QtCore.Qt.DropAction.CopyAction, mime,
                           QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    v.dropEvent(drop)
    assert drop.isAccepted()
    fireplace = v.windows[0]
    assert fireplace.parentWall is wall and abs(fireplace.depth - 500) < .001 and abs(fireplace.width - 1200) < .001
    assert abs(fireplace.depthOffset + 100) < .001
    assert v.HitTest(v.WorldToViewport(QtCore.QPointF(0, -100))) == (fireplace, None)
    assert all(handle[0] == "resize" for handle in v.FurnishingHandles(fireplace))
    assert len(v.FurnishingHandles(fireplace)) == 8
    assert "Fireplace" in main.selectionLabel.text()
    assert not main.propertyFields["width"].isHidden() and not main.propertyFields["width"].isReadOnly()
    assert main.propertyFields["angle"].isHidden()
    empty = v.WorldToViewport(QtCore.QPointF(0, 1500)).toPoint()
    freeMove = QtGui.QDragMoveEvent(empty, QtCore.Qt.DropAction.CopyAction, mime,
                                   QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    v.dragMoveEvent(freeMove)
    assert freeMove.isAccepted() and isinstance(v.inactiveOpeningPreview, Fireplace)
    assert v.windowDropPreview is None
    v.dragLeaveEvent(QtGui.QDragLeaveEvent())
    targetWall = Wall(QtCore.QPointF(1800, 1000), QtCore.QPointF(1800, 3000), 700)
    v.walls.append(targetWall)
    sourceDirection, sourceNormal = fireplace.Axes()
    start = (fireplace.firstVertex + fireplace.secondVertex) / 2 + sourceNormal * (fireplace.depthOffset + fireplace.depth * .2)
    end = QtCore.QPointF(1700, 2000)
    startPixel, endPixel = v.WorldToViewport(start).toPoint(), v.WorldToViewport(end).toPoint()
    QtTest.QTest.mousePress(v, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier, startPixel)
    for position, expectedParent, expectedDepth in ((endPixel, targetWall, 700), (startPixel, wall, 500)):
        move = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(position),
            QtCore.QPointF(v.mapToGlobal(position)), QtCore.Qt.MouseButton.NoButton,
            QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(v, move)
        assert fireplace.parentWall is expectedParent and fireplace.depth == expectedDepth, "Drag preview lost the initial fireplace depth"
        offWall = v.WorldToViewport(QtCore.QPointF(10000, 10000))
        move = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, offWall,
            QtCore.QPointF(v.mapToGlobal(offWall.toPoint())), QtCore.Qt.MouseButton.NoButton,
            QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(v, move)
        preview = v.inactiveOpeningPreview
        assert isinstance(preview, Fireplace)
        assert abs(preview.width - 1200) < .001 and preview.depth == 500, "Off-wall shadow changed the original proportions"
        direction, normal = preview.Axes()
        path = FireplacePath(preview)
        points = [QtCore.QPointF(path.elementAt(index).x, path.elementAt(index).y) for index in range(path.elementCount())]
        for axis, expected in ((direction, 1200), (normal, 500)):
            coordinates = [QtCore.QPointF.dotProduct(point, axis) for point in points]
            assert abs(max(coordinates) - min(coordinates) - expected) < .001
    # Direct preview creation also preserves a customized fireplace's dimensions.
    preview = v.InactiveOpening(QtCore.QPointF(), Fireplace, fireplace)
    assert abs(preview.width - fireplace.width) < .001 and preview.depth == fireplace.depth
    QtTest.QTest.mouseRelease(v, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier, startPixel)
    Drag(v, v.WorldToViewport(start).toPoint(), v.WorldToViewport(end).toPoint())
    assert fireplace.parentWall is targetWall and abs(fireplace.width - 1200) < .01 and fireplace.depth == 700
    v.Undo()
    assert fireplace.parentWall is wall and fireplace.depth == 500
    v.Redo()
    assert fireplace.parentWall is targetWall and fireplace.depth == 700
    v.Undo()
    v.walls = [wall]
    assert not main.materialField.isHidden() and fireplace.material == wall.material
    main.materialField.setCurrentText("Brick")
    assert fireplace.material == "Brick"
    saved = main.BuildProjectData()
    assert DecodeProject(saved, v.furnishingDefinitions)[1][0].material == "Brick"
    v.Undo()
    assert fireplace.material == wall.material
    v.Redo()
    assert fireplace.material == "Brick"
    v.Undo()
    originalFacing = fireplace.swingsOutwards
    main.EditDoorProperty("swing")
    assert fireplace.swingsOutwards != originalFacing
    v.Undo()
    assert fireplace.swingsOutwards == originalFacing
    main.sizeLinkButton.setChecked(False)  # Exercise independent span/depth edits.
    main.propertyFields["width"].setValue(80)
    assert fireplace.depth == 800
    v.Undo()
    assert abs(fireplace.depth - 500) < .001
    v.Redo()
    assert fireplace.depth == 800
    main.propertyFields["length"].setValue(1.5)
    assert fireplace.width == 1500
    v.Undo()
    assert abs(fireplace.width - 1200) < .001
    fireplace.depth = 1
    assert fireplace.depth == wall.width
    fireplace.depth = 800
    fireplace.depthOffset = -100
    assert v.FindFireplacePlacement(v.WorldToViewport(QtCore.QPointF(10000, 10000)),
                                   QtCore.Qt.KeyboardModifier.NoModifier) is None
    start = v.WorldToViewport((fireplace.firstVertex + fireplace.secondVertex) / 2 + QtCore.QPointF(-200, 200))
    end = start + QtCore.QPointF(70, -20)
    for eventType, position, buttons in (
            (QtCore.QEvent.Type.MouseButtonPress, start, QtCore.Qt.MouseButton.LeftButton),
            (QtCore.QEvent.Type.MouseMove, end, QtCore.Qt.MouseButton.LeftButton),
            (QtCore.QEvent.Type.MouseButtonRelease, end, QtCore.Qt.MouseButton.NoButton)):
        event = QtGui.QMouseEvent(eventType, position, QtCore.QPointF(v.mapToGlobal(position.toPoint())),
            QtCore.Qt.MouseButton.NoButton if eventType == QtCore.QEvent.Type.MouseMove else QtCore.Qt.MouseButton.LeftButton,
            buttons, QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(v, event)
    assert fireplace.centerFraction > .5 and fireplace.depthOffset > -100
    v.Undo()
    assert abs(fireplace.centerFraction - .5) < .001 and abs(fireplace.depthOffset + 100) < .001
    v.snapEnabled = True
    limit = (fireplace.depth - wall.width) / 2
    for value in (-limit, 0, limit):
        placement = v.FindFireplacePlacement(v.WorldToViewport(QtCore.QPointF(0, value + 2)),
                                             QtCore.Qt.KeyboardModifier.NoModifier, fireplace)
        assert placement is not None and abs(placement.depthOffset - value) < .001
    placement = v.FindFireplacePlacement(v.WorldToViewport(QtCore.QPointF(0, 20)),
                                         QtCore.Qt.KeyboardModifier.AltModifier, fireplace)
    assert abs(placement.depthOffset - 20) < .001
    v.snapEnabled = False
    for field in ("width", "length"):
        handle = next(handle for handle in v.FurnishingHandles(fireplace) if handle[:3] == ("resize", field, 1))
        axis = QtCore.QPointF(0, -1) if field == "width" else QtCore.QPointF(1, 0)
        originalSize = fireplace.depth if field == "width" else fireplace.length
        end = v.WorldToViewport(v.ViewportToWorld(handle[3]) + axis * 200)
        v.BeginFurnishingHandleDrag(fireplace, handle, handle[3])
        v.UpdateFurnishingHandleDrag(end, QtCore.Qt.KeyboardModifier.NoModifier)
        assert abs((fireplace.depth if field == "width" else fireplace.length) - originalSize - 200) < .001
        release = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonRelease, end,
            QtCore.QPointF(v.mapToGlobal(end.toPoint())), QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier)
        v.mouseReleaseEvent(release)
        v.Undo()
        assert abs((fireplace.depth if field == "width" else fireplace.length) - originalSize) < .001
    before = v.CaptureState()
    wall.firstVertex += QtCore.QPointF(100, 200)
    wall.secondVertex += QtCore.QPointF(100, 200)
    wall.width = 1000
    v.RecordEdit(before)
    assert fireplace.depth == 1000 and fireplace.depthOffset == 0
    v.Undo()
    assert fireplace.depth == 800 and wall.width == 240
    before = v.CaptureState()
    wall.firstVertex = QtCore.QPointF(0, -2500)
    wall.secondVertex = QtCore.QPointF(0, 2500)
    v.RecordEdit(before)
    assert abs(fireplace.HandleBox().angle) < .001
    v.Undo()
    v.SetSelection([(wall, None)])
    assert v.CopySelection() and v.PasteSelection(v.DrawingRect().center() + QtCore.QPointF(0, 180))
    assert len(v.windows) == 2 and v.windows[1].parentWall is v.walls[1]
    assert v.windows[1].depth == fireplace.depth and v.windows[1].depthOffset == fireplace.depthOffset
    v.Undo()
    v.SetSelection([(v.walls[0], None)])
    v.DeleteSelected()
    assert not v.walls and not v.windows
    v.Undo()
    assert len(v.walls) == len(v.windows) == 1
    before = v.CaptureState()
    wall.width = 1200
    v.RecordEdit(before)
    before = v.CaptureState()
    wall.width = 240
    v.RecordEdit(before)
    saved = main.BuildProjectData()
    main.ApplyProject(DecodeProject(saved, v.furnishingDefinitions), None)
    assert isinstance(v.windows[0], Fireplace) and v.windows[0].parentWall is v.walls[0]
    v.Undo()
    assert v.walls[0].width == 1200 and v.windows[0].depth == 1200
    v.Redo()
    assert v.walls[0].width == 240 and v.windows[0].depth == 800
    v.verifyRenderRevisions = True
    v.SceneRenderKey(("fireplace",))
    v.windows[0].depthOffset = 50
    v.SceneRenderKey(("fireplace",))
    main.sidebarTabs.setCurrentWidget(main.exportPanel)
    panel = main.exportPanel
    panel.borderField.setCurrentText("None")
    panel.showGridField.setChecked(False)
    panel.SetOverride("measurementVisibility", {key: False for key in v.measurementVisibility})
    png = panel.Render("png")
    assert not png.isNull() and SvgPreviewRenderer(panel.Render("svg")).isValid()
    v.windows[0].material = "Brick"
    patterned = panel.Render("png")
    assert patterned != png, "Fireplace material did not affect the render"
    assert SvgPreviewRenderer(panel.Render("svg")).isValid()
    v.windows[0].material = v.walls[0].material
    png.save(str(Path(__file__).resolve().parent.parent / "diagnostics" / "fireplace-export-preview.png"))
    panel.showGridField.setChecked(True)
    opaque = panel.Render("png")
    panel.solidObjectsField.setChecked(False)
    assert panel.Render("png") == opaque, "Fireplace should only draw its solid U-shaped body"
    assert SvgPreviewRenderer(panel.Render("svg")).isValid()
    v.visibility["Fireplaces"] = False
    hidden = panel.Render("png")
    v.visibility["Fireplaces"] = True
    assert panel.Render("png") != hidden
    fireplace = v.windows[0]
    direction, normal = fireplace.Axes()
    center = (fireplace.firstVertex + fireplace.secondVertex) / 2 + normal * fireplace.depthOffset
    cavity = center - normal * (fireplace.depth * .4)
    x, y, width, length = v.exportOverlay.bounds
    pixel = QtCore.QPoint(round((cavity.x() - x) * panel.ScalePerMeter() / 1000),
                         round((y + length - cavity.y()) * panel.ScalePerMeter() / 1000))
    assert opaque.pixelColor(pixel) == hidden.pixelColor(pixel), "Fireplace background hid the grid in its cavity"
    image = QtGui.QImage(600, 300, QtGui.QImage.Format.Format_ARGB32)
    image.fill("#ffffff")
    fixtureWall = Wall(QtCore.QPointF(-2500, 0), QtCore.QPointF(2500, 0), 240)
    fixture = Fireplace(fixtureWall, .4, .6)
    with QtGui.QPainter(image) as painter:
        painter.translate(300, 160)
        painter.scale(.35, -.35)
        painter.fillRect(QtCore.QRectF(-900, -120, 1800, 240), QtGui.QColor("#aaaaaa"))
        painter.fillRect(QtCore.QRectF(-500, -fixture.depth / 2, 1000, fixture.depth), QtGui.QColor("#ffffff"))
        painter.fillPath(FireplacePath(fixture), QtGui.QColor("#333333"))
    image.save(str(Path(__file__).resolve().parent.parent / "diagnostics" / "fireplace-preview.png"))
    # A closed wall loop must retain its empty interior at fractional positions
    # and export densities; fireplace outlines must cross the wall's fill.
    point = QtCore.QPointF
    top = Wall(point(-2500, 0), point(2500, 0), 240)
    v.walls = [top, Wall(point(2500, 0), point(2500, -3000), 240),
               Wall(point(2500, -3000), point(-2500, -3000), 240),
               Wall(point(-2500, -3000), point(-2500, 0), 240)]
    fireplace = Fireplace(top, .38, .62)
    v.windows = [fireplace]
    v.exportOverlay.bounds = (-3000, -3500, 6000, 4500)
    panel.showGridField.setChecked(False)
    for density, fraction, offset in ((50, .5, 0), (123, .4371, 130), (200, .61, -130)):
        panel.scaleField.setValue(density)
        fireplace.centerFraction = fraction
        fireplace.depthOffset = offset
        visible = panel.Render("png")
        v.visibility["Fireplaces"] = False
        hidden = panel.Render("png")
        v.visibility["Fireplaces"] = True
        centerPixel = QtCore.QPoint(round(3000 * density / 1000), round(2500 * density / 1000))
        assert visible.pixelColor(centerPixel) == hidden.pixelColor(centerPixel), "Fireplace filled the enclosed room"
        edgePixel = QtCore.QPoint(round((fireplace.firstVertex.x() + 3000) * density / 1000), density)
        assert visible.pixelColor(edgePixel) != hidden.pixelColor(edgePixel), "Fireplace outline disappeared inside its wall"
        assert SvgPreviewRenderer(panel.Render("svg")).isValid()
    v.walls = [top]
    for mode in (0, 1, 2):
        v.measurementSettings["windows"] = mode
        dimensions = v.WallDimensions([top], v.ConnectedWallPath([top]))
        horizontal = [(first, second) for first, second, owners in dimensions if abs(first.y() - second.y()) < .001]
        assert len(horizontal) == 6, "Fireplace did not split measurements on both wall faces"
        widths = [(first, second) for first, second in horizontal
                  if abs(QtCore.QLineF(first, second).length() - fireplace.width) < .01]
        assert len(widths) == 2
        expectedEdges = sorted((fireplace.depthOffset - fireplace.depth / 2, fireplace.depthOffset + fireplace.depth / 2))
        assert all(abs(actual - expected) < .01 for actual, expected in
                   zip(sorted(first.y() for first, second in widths), expectedEdges)), "Width measurements crossed the fireplace body"
    fireplace.depthOffset = 70
    shifted = v.WallDimensions([top], v.ConnectedWallPath([top]))
    widths = [(first, second) for first, second, owners in shifted
              if abs(first.y() - second.y()) < .001 and abs(QtCore.QLineF(first, second).length() - fireplace.width) < .01]
    assert sorted(round(first.y()) for first, second in widths) == [-180, 320], "Fireplace measurement cache ignored depth movement"
    app.clipboard().clear()
    main.close()
    print("PASS: fireplace placement, wall attachment, depth snaps, handles, undo, clipboard and PNG/SVG")


if __name__ == "__main__":
    Main()
