"""Selected objects win overlap hits; exposed, deselected and hidden objects retain normal picking."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from planner_app.models import Furnishing, Label, Wall, Pillar, Counter, MeasurementGuide, Arrow


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    v.snapEnabled = False
    point = QtCore.QPointF
    back = Furnishing(v.furnishingDefinitions["null"])
    front = Furnishing(v.furnishingDefinitions["null"])
    back.width = 600
    back.firstVertex, back.secondVertex = point(0, -300), point(0, 300)
    front.width = 1600
    front.firstVertex, front.secondVertex = point(0, -800), point(0, 800)
    v.furnishings = [back, front]
    overlap = v.WorldToViewport(point())
    exposed = v.WorldToViewport(point(650, 0))
    assert v.HitTest(overlap) == (front, None)
    v.SetSelection([(back, None)])
    assert v.HitTest(overlap) == (back, None)
    assert v.HitTest(exposed) == (front, None)
    originalFront = (point(front.firstVertex), point(front.secondVertex))
    left = QtCore.Qt.MouseButton.LeftButton
    for eventType, position in ((QtCore.QEvent.Type.MouseButtonPress, overlap),
                                (QtCore.QEvent.Type.MouseMove, overlap + point(30, 20)),
                                (QtCore.QEvent.Type.MouseButtonRelease, overlap + point(30, 20))):
        button = QtCore.Qt.MouseButton.NoButton if eventType == QtCore.QEvent.Type.MouseMove else left
        buttons = QtCore.Qt.MouseButton.NoButton if eventType == QtCore.QEvent.Type.MouseButtonRelease else left
        event = QtGui.QMouseEvent(eventType, position, point(v.mapToGlobal(position.toPoint())), button, buttons,
                                 QtCore.Qt.KeyboardModifier.NoModifier)
        QtWidgets.QApplication.sendEvent(v, event)
    assert (front.firstVertex, front.secondVertex) == originalFront
    assert (back.firstVertex + back.secondVertex) / 2 != point()
    v.Undo()
    v.SetSelection([])
    assert v.HitTest(overlap) == (front, None)
    v.SetSelection([(back, None)])
    v.hiddenObjects = [back]
    v.hiddenObjectIds = {id(back)}
    assert v.HitTest(overlap) == (front, None)
    v.hiddenObjects, v.hiddenObjectIds = [], set()
    # An unselected object's nearby resize handle cannot intercept the selected body.
    front.width = 200
    front.firstVertex, front.secondVertex = point(0, -100), point(0, 100)
    handle = next(handle for handle in v.FurnishingHandles(front) if handle[:3] == ("resize", "width", 1))
    v.hoverPosition = handle[3]
    assert v.HitTest(handle[3]) == (back, None)
    assert v.HitFurnishingHandle(handle[3]) == (None, None)
    front.width = 1600
    front.firstVertex, front.secondVertex = originalFront

    # Priority applies across object types, including objects above furnishings in scene painting.
    wall = Wall(point(-700, 0), point(700, 0), 240)
    pillar = Pillar(point(0, -300), point(0, 300), 600)
    counter = Counter(point(-700, 0), point(700, 0), 300)
    guide = MeasurementGuide(point(-700, 0), point(700, 0))
    arrow = Arrow(point(-700, 0), point(700, 0), 40)
    label = Label(point(), "Selected")
    label.firstVertex, label.secondVertex, label.width = point(0, -300), point(0, 300), 600
    v.walls = [wall, pillar, counter, guide, arrow]
    v.labels = [label]
    for obj in (back, wall, pillar, counter, guide, arrow, label):
        v.SetSelection([(obj, None)])
        assert v.HitTest(overlap) == (obj, 3 if obj is guide else None), type(obj).__name__
        if obj is guide:
            assert v.HitTest(v.WorldToViewport(point(300, 0))) == (guide, None)
    v.SetSelection([(wall, 0)])
    assert v.HitTest(v.WorldToViewport(wall.firstVertex)) == (wall, 0)
    main.close()


if __name__ == "__main__":
    Main()
