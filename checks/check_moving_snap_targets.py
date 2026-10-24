"""Moving footprints are excluded without losing stationary or fixed-end targets."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from planner_app.models import Furnishing, Pillar, Wall
from planner_app.viewport.widget import DrawingViewport


def Main():
    app = QtWidgets.QApplication([])
    viewport = DrawingViewport()
    viewport.resize(1200, 900)
    viewport.performanceTimer.stop()
    point = QtCore.QPointF
    none = QtCore.Qt.KeyboardModifier.NoModifier
    source = Wall(point(), point(1000, 0))
    pillar = Pillar(point(1100, -100), point(1100, 100), 200)
    desk = Furnishing(viewport.furnishingDefinitions["desk"], point(-1800, 1200))
    stationary = Furnishing(desk.definition, point(2200, 1600))
    viewport.walls = [source, pillar]
    viewport.furnishings = [desk, stationary]
    viewport.gridSnapEnabled = viewport.alignmentSnapEnabled = viewport.midpointSnapEnabled = False
    viewport.snapEnabled = viewport.vertexSnapEnabled = True
    viewport.connectedEnabled = viewport.connectedObjectsEnabled = True
    viewport.show()
    app.processEvents()

    # Begin an actual connected wall gesture: the touching pillar is captured
    # by AttachedVertices/ActiveAttachments, rather than a mocked attachment list.
    viewport.SetSelection([(source, None)])
    start = viewport.WorldToViewport(point(500, 0)).toPoint()
    QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos = start)
    assert viewport.selectedWall is source and viewport.selectedVertex is None
    assert any(obj is pillar for obj, index, vertex in viewport.ActiveAttachments())
    corners = viewport.ObjectCorners(pillar)
    targets = list(viewport.SnapVertices())
    assert not any(corner in targets for corner in corners), "Moving pillar corners leaked into snap targets"
    assert all(corner in targets for corner in viewport.ObjectCorners(stationary))
    corner = corners[0]
    delta = point(10, 10)
    assert viewport.SnapPosition(corner + delta, none) == corner + delta
    assert viewport.SnapObjectMovement([corner], delta, none) == delta
    viewport.CancelInteraction()

    # Group capture includes both furnishing and pillar footprint objects while
    # the primary selection remains a wall. Connection settings do not disable
    # exclusion of objects explicitly moved by the selection.
    viewport.connectedEnabled = False
    viewport.SetSelection([(desk, None), (pillar, None), (source, None)])
    viewport.dragStart = point(start)
    viewport.StartGroupDrag()
    for obj in (desk, pillar):
        targets = list(viewport.SnapVertices())
        assert not any(corner in targets for corner in viewport.ObjectCorners(obj))
        corner = viewport.ObjectCorners(obj)[0]
        assert viewport.SnapObjectMovement([corner], delta, none) == delta
    assert all(corner in targets for corner in viewport.ObjectCorners(stationary))
    target = viewport.ObjectCorners(stationary)[0]
    assert viewport.SnapPosition(target + delta, none) == target
    viewport.CancelInteraction()

    # Endpoint editing still offers the opposite, fixed endpoint as a target.
    viewport.SetSelection([(source, 0)])
    viewport.dragStart = point(start)
    targets = list(viewport.SnapVertices())
    assert source.firstVertex not in targets and source.secondVertex in targets
    viewport.CancelInteraction()
    # Stationary objects remain targets after the connected gesture ends.
    assert all(corner in list(viewport.SnapVertices()) for corner in corners)
    viewport.close()
    print("PASS: connected/group footprint exclusions, default snap callers, stationary targets and fixed endpoints.")


if __name__ == "__main__":
    Main()
