"""Wheel-selected Ctrl vertex origins, tooltip feedback and gesture reset."""
import os
import math
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner_app.models import Wall, Stair, Counter, Railing, Arrow, MeasurementGuide
from planner_app.viewport.widget import DrawingViewport
from planner_app.graphics.text import PathTextPainter


def Main():
    app = QtWidgets.QApplication([])
    viewport = DrawingViewport()
    viewport.resize(1200, 900)
    viewport.show()
    app.processEvents()
    point = QtCore.QPointF
    ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
    none = QtCore.Qt.KeyboardModifier.NoModifier
    left = QtCore.Qt.MouseButton.LeftButton
    texts = []
    originalDrawText = PathTextPainter.drawText

    def CaptureText(painter, *arguments):
        texts.extend(argument for argument in arguments if isinstance(argument, str))
        return originalDrawText(painter, *arguments)

    for objectType in (Wall, Stair, Counter, Railing, Arrow, MeasurementGuide):
        for index in (0, 1):
            for snapEnabled in (False, True):
                obj = objectType(point(-1000, -400), point(1000, 400), 200)
                viewport.walls = [obj]
                viewport.snapEnabled = snapEnabled
                viewport.SetSelection([(obj, index)])
                start = viewport.WorldToViewport(obj.firstVertex if index == 0 else obj.secondVertex)
                QtTest.QTest.mousePress(viewport, left, pos = start.toPoint())
                assert viewport.selectedVertex == index
                originals = tuple(point(vertex) for vertex in viewport.dragVertices)
                cursor = start + point(100, -40)
                viewport.UpdateInteraction(cursor, ctrl)
                assert viewport.axisConstraintOrigin == originals[1 - index]
                originalAxes = viewport.VertexConstraintAxes()
                zoom = viewport.zoom
                for delta, fromDragged in ((60, False), (60, True), (-120, False), (120, True)):
                    wheel = QtGui.QWheelEvent(cursor, point(viewport.mapToGlobal(cursor.toPoint())),
                        QtCore.QPoint(), QtCore.QPoint(0, delta), left, ctrl,
                        QtCore.Qt.ScrollPhase.NoScrollPhase, False)
                    app.sendEvent(viewport, wheel)
                    assert wheel.isAccepted() and viewport.zoom == zoom
                    assert viewport.vertexAxisFromDragged == fromDragged
                    origin = originals[index if fromDragged else 1 - index]
                    assert viewport.axisConstraintOrigin == origin
                    assert viewport.VertexConstraintAxes() == originalAxes
                    cursorOffset = viewport.ViewportToWorld(cursor) - origin
                    cursorAngle = math.atan2(cursorOffset.y(), cursorOffset.x())
                    expectedAngle = round(cursorAngle / (math.pi / 12)) * (math.pi / 12)
                    expectedDirection = point(math.cos(expectedAngle), math.sin(expectedAngle))
                    assert QtCore.QLineF(viewport.axisConstraintDirection, expectedDirection).length() < .000001
                    vertex = obj.firstVertex if index == 0 else obj.secondVertex
                    direction = viewport.axisConstraintDirection
                    offset = vertex - origin
                    assert abs(offset.x() * direction.y() - offset.y() * direction.x()) < .01
                if objectType is Wall and index == 0 and not snapEnabled:
                    with patch.object(PathTextPainter, "drawText", CaptureText):
                        viewport.grab()
                    assert "Switch axis origin" in texts
                    texts.clear()
                    viewport.UpdateInteraction(cursor, none)
                    with patch.object(PathTextPainter, "drawText", CaptureText):
                        viewport.grab()
                    assert not any("Switch axis origin" in text for text in texts)
                    viewport.UpdateInteraction(cursor, ctrl)
                    assert viewport.axisConstraintOrigin == originals[index]
                if index == 0:
                    viewport.CancelInteraction()
                    assert obj.firstVertex == originals[0] and obj.secondVertex == originals[1]
                QtTest.QTest.mouseRelease(viewport, left, pos = cursor.toPoint())
                assert not viewport.vertexAxisFromDragged and viewport.vertexAxisWheelDelta == 0
    # Only the active axis is painted, for both endpoints in both frames.
    lines = []
    originalDrawLine = QtGui.QPainter.drawLine

    def CaptureLine(painter, *arguments):
        if (len(arguments) == 1 and isinstance(arguments[0], QtCore.QLineF)
                and arguments[0].length() > 2 * math.hypot(viewport.width(), viewport.height())
                and painter.pen().style() == QtCore.Qt.PenStyle.DashLine):
            lines.append(QtCore.QLineF(arguments[0]))
        return originalDrawLine(painter, *arguments)

    for local in (False, True):
        for index in (0, 1):
            obj = Wall(point(-900, -350), point(900, 350), 200)
            viewport.walls = [obj]
            viewport.snapEnabled = False
            viewport.localTransforms = local
            viewport.SetSelection([(obj, index)])
            start = viewport.WorldToViewport(obj.firstVertex if index == 0 else obj.secondVertex)
            QtTest.QTest.mousePress(viewport, left, pos = start.toPoint())
            originals = tuple(point(vertex) for vertex in viewport.dragVertices)
            cursor = start + point(100, -150)
            viewport.UpdateInteraction(cursor, ctrl)
            run = originals[index] - originals[1 - index]
            reference = math.atan2(run.y(), run.x()) if local else 0
            for fromDragged in (False, True):
                if fromDragged:
                    wheel = QtGui.QWheelEvent(cursor, point(viewport.mapToGlobal(cursor.toPoint())),
                        QtCore.QPoint(), QtCore.QPoint(0, 120), left, ctrl,
                        QtCore.Qt.ScrollPhase.NoScrollPhase, False)
                    app.sendEvent(viewport, wheel)
                origin = originals[index if fromDragged else 1 - index]
                offset = viewport.ViewportToWorld(cursor) - origin
                cursorAngle = math.atan2(offset.y(), offset.x())
                angle = reference + round((cursorAngle - reference) / (math.pi / 12)) * (math.pi / 12)
                assert QtCore.QLineF(viewport.axisConstraintDirection, point(math.cos(angle), math.sin(angle))).length() < .000001
                lines.clear()
                with patch.object(QtGui.QPainter, "drawLine", CaptureLine):
                    preview = viewport.grab()
                assert len(lines) == 1, len(lines)
                for line in lines:
                    assert QtCore.QLineF(line.center(), viewport.WorldToViewport(origin)).length() < .000001
                    direction = line.p2() - line.p1()
                    direction /= line.length()
                    expected = point(math.cos(angle), -math.sin(angle))
                    assert abs(abs(QtCore.QPointF.dotProduct(direction, expected)) - 1) < .000001
                if local and index == 1 and fromDragged:
                    preview.save(str(Path(__file__).resolve().parent.parent / "diagnostics/vertex-axis-active-preview.png"))
            viewport.CancelInteraction()
            QtTest.QTest.mouseRelease(viewport, left, pos = cursor.toPoint())
    # Explicitly selected endpoints in a group share one movement delta and
    # constrain around the selected object's chosen origin in local mode too.
    first = Wall(point(-1000, 0), point(1000, 300), 200)
    second = Wall(point(-1000, -1000), point(1000, -700), 200)
    viewport.walls = [first, second]
    viewport.snapEnabled = False
    viewport.localTransforms = True
    viewport.SetSelection([(first, 1), (second, 1)])
    start = viewport.WorldToViewport(first.secondVertex)
    originals = (point(first.secondVertex), point(second.secondVertex))
    QtTest.QTest.mousePress(viewport, left, pos = start.toPoint())
    cursor = start + point(100, -40)
    viewport.UpdateInteraction(cursor, ctrl)
    assert viewport.groupDrag
    wheel = QtGui.QWheelEvent(cursor, point(viewport.mapToGlobal(cursor.toPoint())),
        QtCore.QPoint(0, 20), QtCore.QPoint(), left, ctrl,
        QtCore.Qt.ScrollPhase.NoScrollPhase, False)
    app.sendEvent(viewport, wheel)
    assert viewport.axisConstraintOrigin == originals[0]
    assert QtCore.QLineF(first.secondVertex - originals[0], second.secondVertex - originals[1]).length() < .01
    QtTest.QTest.mouseRelease(viewport, left, ctrl, cursor.toPoint())
    assert not viewport.vertexAxisFromDragged
    viewport.close()
    print("PASS: both origins, wheel accumulation, unchanged zoom, constraints, tooltip, release and cancellation")


if __name__ == "__main__":
    Main()
