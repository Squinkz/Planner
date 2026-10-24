"""Fireplace faces align to wall outlines during placement and live movement."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall, Fireplace


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    point = QtCore.QPointF
    none = QtCore.Qt.KeyboardModifier.NoModifier
    alt = QtCore.Qt.KeyboardModifier.AltModifier
    v.snapEnabled = v.alignmentSnapEnabled = True
    v.gridSnapEnabled = v.vertexSnapEnabled = v.midpointSnapEnabled = False
    fixtures = [
        (point(720, 1200), point(720, 2400), 200, point(5, 0), point(20, 0)),
        (point(-720, 1200), point(-720, 2400), 200, point(-5, 0), point(-20, 0)),
        (point(1500, 500), point(2200, 500), 160, point(0, 105), point(0, 120)),
        (point(1500, -500), point(2200, -500), 160, point(0, -105), point(0, -120)),
    ]
    for rotated in (False, True):
        rotation = QtGui.QTransform().rotate(90 if rotated else 0)
        parent = Wall(rotation.map(point(-2500, 0)), rotation.map(point(2500, 0)), 240)
        fireplace = Fireplace(parent, .38, .62)
        fireplace.depth = 600
        v.windows = [fireplace]
        v.SetSelection([(fireplace, None)])
        for first, second, width, raw, expected in fixtures:
            v.walls = [parent, Wall(rotation.map(first), rotation.map(second), width)]
            raw, expected = rotation.map(raw), rotation.map(expected)
            placement = v.FindFireplacePlacement(v.WorldToViewport(raw), none, fireplace)
            assert placement is not None
            direction, normal = placement.Axes()
            center = (placement.firstVertex + placement.secondVertex) / 2 + normal * placement.depthOffset
            assert QtCore.QLineF(center, expected).length() < .001, (rotated, raw, center, expected)
            assert v.alignmentGuides
            assert abs(placement.width - 1200) < .001 and placement.depth == 600
            for modifiers in (alt, none):
                v.alignmentSnapEnabled = modifiers == alt
                placement = v.FindFireplacePlacement(v.WorldToViewport(raw), modifiers, fireplace)
                center = (placement.firstVertex + placement.secondVertex) / 2 + normal * placement.depthOffset
                assert QtCore.QLineF(center, raw).length() < .001
            v.alignmentSnapEnabled = True
    # Exercise the actual drag path, including release and undo.
    parent = Wall(point(-2500, 0), point(2500, 0), 240)
    fireplace = Fireplace(parent, .38, .62)
    fireplace.depth = 600
    v.walls = [parent, Wall(point(720, 1200), point(720, 2400), 200)]
    v.windows = [fireplace]
    v.SetSelection([(fireplace, None)])
    start = v.WorldToViewport(point(0, 150))
    end = start + point(QtWidgets.QApplication.startDragDistance() + 1, 0)
    for eventType, position, buttons in (
            (QtCore.QEvent.Type.MouseButtonPress, start, QtCore.Qt.MouseButton.LeftButton),
            (QtCore.QEvent.Type.MouseMove, end, QtCore.Qt.MouseButton.LeftButton),
            (QtCore.QEvent.Type.MouseButtonRelease, end, QtCore.Qt.MouseButton.NoButton)):
        event = QtGui.QMouseEvent(eventType, position, point(v.mapToGlobal(position.toPoint())),
            QtCore.Qt.MouseButton.NoButton if eventType == QtCore.QEvent.Type.MouseMove else QtCore.Qt.MouseButton.LeftButton,
            buttons, none)
        app.sendEvent(v, event)
        if eventType == QtCore.QEvent.Type.MouseButtonPress:
            assert v.selectedWall is fireplace and v.dragStart is not None
    assert abs(fireplace.secondVertex.x() - 620) < .001, (fireplace.secondVertex, v.selectedWall, v.inactiveOpeningPreview)
    v.Undo()
    assert abs(fireplace.secondVertex.x() - 600) < .001
    # Center/flush depth alignment obeys the same enabled target types as the
    # general snapping path; Alignment alone must not retain hidden targets.
    v.walls = [parent]
    v.gridSnapEnabled = v.vertexSnapEnabled = v.cornerSnapEnabled = v.midpointSnapEnabled = False
    v.alignmentSnapEnabled = v.snapEnabled = True
    placement = v.FindFireplacePlacement(v.WorldToViewport(point(0, 15)), none, fireplace)
    assert placement is not None and abs(placement.depthOffset - 15) < .001 and not v.snapApplied
    v.midpointSnapEnabled = True
    placement = v.FindFireplacePlacement(v.WorldToViewport(point(0, 15)), none, fireplace)
    assert placement is not None and abs(placement.depthOffset) < .001 and v.snapApplied
    v.midpointSnapEnabled = False
    for enabled in (False, True):
        v.cornerSnapEnabled = enabled
        placement = v.FindFireplacePlacement(v.WorldToViewport(point(0, 170)), none, fireplace)
        assert placement is not None and abs(placement.depthOffset - (180 if enabled else 170)) < .001
    main.close()
    print("PASS: all four faces, rotated parents, wall edges, snap toggles, live drag and undo.")


if __name__ == "__main__":
    Main()
