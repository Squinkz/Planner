"""Global/local movement axes, original-relative vertex angles and persistence."""
import math
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtTest import QTest
from planner import MainWindow
from planner_app.models import Wall, Counter, Railing, Stair, Arrow, MeasurementGuide, Pillar, Furnishing, Label
from planner_app.project_codec import DecodeProject
from planner_app.graphics.theme import BuildStyle
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    point = QtCore.QPointF
    ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
    button = main.transformOrientationButton
    assert not button.isCheckable() and not v.localTransforms
    assert "Global" in button.toolTip() and not button.icon().pixmap(24, 24).isNull()
    button.click()
    assert v.localTransforms and "Local" in button.toolTip()
    v.setFocus()
    QTest.keyClick(v, QtCore.Qt.Key.Key_Tab)
    assert not v.localTransforms and app.focusWidget() is v
    QTest.keyClick(v, QtCore.Qt.Key.Key_Tab)
    assert v.localTransforms and app.focusWidget() is v
    editor = QtWidgets.QLineEdit(main)
    editor.show()
    editor.setFocus()
    QTest.keyClick(editor, QtCore.Qt.Key.Key_Tab)
    assert v.localTransforms
    editor.hide()
    v.setFocus()
    v.snapEnabled = False
    v.connectedVerticesEnabled = v.connectedObjectsEnabled = False
    angle = math.radians(37)
    along = point(math.cos(angle), math.sin(angle))
    normal = point(-along.y(), along.x())
    for cls in (Wall, Counter, Railing, Stair, Arrow, MeasurementGuide, Pillar, Furnishing, Label):
        if cls is Furnishing:
            obj = Furnishing(v.furnishingDefinitions["desk"])
            obj.angle = 37
        elif cls is Label:
            obj = Label(point(), "Local label")
            obj.angle = 37
        else:
            obj = cls(-along * 500, along * 500)
        v.walls = [obj] if isinstance(obj, Wall) else []
        v.furnishings = [obj] if type(obj) is Furnishing else []
        v.labels = [obj] if isinstance(obj, Label) else []
        v.windows = []
        v.SetSelection([(obj, None)])
        original = (point(obj.firstVertex), point(obj.secondVertex))
        center = (original[0] + original[1]) / 2
        for local in (False, True):
            main.SetTransformOrientation(local)
            v.SetSelection([(obj, None)])
            delta = along * 180 + normal * 25
            # The guide midpoint now edits its label offset; use the line body.
            dragOrigin = center + along * 250 if isinstance(obj, MeasurementGuide) else center
            start = v.WorldToViewport(dragOrigin).toPoint()
            end = (point(start) + point(delta.x(), -delta.y()) * v.basePixelsPerMillimeter * v.zoom).toPoint()
            Drag(v, start, end, ctrl)
            moved = obj.firstVertex - original[0]
            assert QtCore.QLineF(obj.secondVertex - obj.firstVertex, original[1] - original[0]).length() < .01
            if local:
                assert min(abs(moved.x() * axis.y() - moved.y() * axis.x()) for axis in (along, normal)) < .01, cls
            else:
                assert abs(moved.y()) < .01 and moved.x() > 0, (cls, moved, center, v.size(), v.selectedWall, v.furnishingHandleDrag)
            if isinstance(obj, Stair):
                assert not obj.directionReversed
            assert v.undoHistory
            v.Undo()
            assert QtCore.QLineF(obj.firstVertex, original[0]).length() < .01
    # Ctrl vertex angles are relative to the captured geometry, not geometry
    # from the previous mouse move. Global mode remains a world 15-degree grid.
    wall = Wall(point(), along * 1000)
    v.walls, v.furnishings, v.labels = [wall], [], []
    v.SetSelection([(wall, 1)])
    v.dragStart = v.WorldToViewport(wall.secondVertex)
    v.dragVertices = v.dragSourceVertices = (point(wall.firstVertex), point(wall.secondVertex))
    for local, expected in ((False, 60), (True, 52)):
        main.SetTransformOrientation(local)
        target = point(math.cos(math.radians(54)), math.sin(math.radians(54))) * 1200
        for snapped in (v.SnapWallEndpoint(target, point(), ctrl), v.SnapStairVertex(target, point(), wall, ctrl)):
            assert v.axisConstraintOrigin == point()
            assert abs(math.degrees(math.atan2(v.axisConstraintDirection.y(), v.axisConstraintDirection.x())) - expected) < 1e-6
            assert abs(math.degrees(math.atan2(snapped.y(), snapped.x())) - expected) < 1e-6
        wall.secondVertex = point(1000, 0)
        assert abs(math.degrees(v.ConstrainedVertexAngle(target)) - expected) < 1e-6
    v.CancelInteraction()
    assert v.axisConstraintOrigin is None and v.axisConstraintDirection is None
    # One active frame moves a mixed selection rigidly; it never gives each
    # member a different delta when they have different rotations.
    first = Wall(-along * 500, along * 500)
    second = Wall(point(-500, 1500), point(500, 1500))
    v.walls = [first, second]
    main.SetTransformOrientation(True)
    v.SetSelection([(second, None), (first, None)])
    original = (point(first.firstVertex), point(second.firstVertex))
    start = v.WorldToViewport(point()).toPoint()
    Drag(v, start, start + QtCore.QPoint(100, -60), ctrl)
    delta = first.firstVertex - original[0]
    assert abs(delta.x() * along.y() - delta.y() * along.x()) < .01
    assert QtCore.QLineF(second.firstVertex - original[1], delta).length() < .01
    v.Undo()
    # Snapping may change distance along a local axis, never the axis itself.
    v.snapEnabled = True
    v.SetSelection([(first, None)])
    v.dragStart = v.WorldToViewport(point())
    v.dragVertices = v.dragSourceVertices = (point(first.firstVertex), point(first.secondVertex))
    snapped = v.SnapObjectMovement(list(v.dragVertices), along * 190 + normal * 35, ctrl)
    assert abs(snapped.x() * along.y() - snapped.y() * along.x()) < .01
    v.CancelInteraction()
    v.snapEnabled = False
    # A shared selected vertex uses the active segment's captured frame and
    # remains coincident after local 15-degree snapping, with working undo.
    first = Wall(point(), along * 1000)
    second = Wall(along * 1000, along * 1000 + normal * 500)
    v.walls = [first, second]
    v.SetSelection([(second, 0), (first, 1)])
    start = v.WorldToViewport(first.secondVertex).toPoint()
    end = v.WorldToViewport(point(math.cos(math.radians(54)), math.sin(math.radians(54))) * 1000).toPoint()
    Drag(v, start, end, ctrl)
    assert abs(math.degrees(math.atan2(first.secondVertex.y(), first.secondVertex.x())) - 52) < .01
    assert QtCore.QLineF(first.secondVertex, second.firstVertex).length() < .01
    v.Undo()
    assert QtCore.QLineF(first.secondVertex, along * 1000).length() < .01
    data = main.BuildProjectData()
    assert DecodeProject(data, v.furnishingDefinitions)[5]["localTransforms"]
    del data["settings"]["localTransforms"]
    assert not DecodeProject(data, v.furnishingDefinitions)[5]["localTransforms"]
    main.WriteSession(wait = True)
    main.viewportToolbar.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots/local-transform-toolbar.png"))
    main.close()
    recovered = MainWindow()
    assert recovered.viewport.localTransforms and "Local" in recovered.transformOrientationButton.toolTip()
    recovered.close()


if __name__ == "__main__":
    Main()
