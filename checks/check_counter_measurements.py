"""Counter end caps, covered spans, rotation and measurement cache invalidation."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Wall, Counter, Stair
from planner_app.models import Furnishing


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    viewport = main.viewport
    point = QtCore.QPointF
    counter = Counter(point(0, 0), point(2000, 0), 600)
    viewport.walls = [counter]
    viewport.furnishings = []
    dimensions = viewport.ConnectedCounterPath([counter])[1]
    assert sorted(round(QtCore.QLineF(first, second).length()) for first, second, owners in dimensions) == [600, 600, 2000, 2000]
    assert all(owners == [counter] for first, second, owners in dimensions)
    for blocker in (Wall(point(0, 420), point(2000, 420), 240),
                    Stair(point(0, 600), point(2000, 600), 600)):
        viewport.walls = [counter] + ([blocker] if isinstance(blocker, Wall) else [])
        viewport.furnishings = [] if isinstance(blocker, Wall) else [blocker]
        dimensions = viewport.ConnectedCounterPath([counter])[1]
        assert len(dimensions) == 3
        assert all(not (abs(first.y() - 300) < .1 and abs(second.y() - 300) < .1)
                   for first, second, owners in dimensions)
        # Moving a blocker must invalidate the cached measurements.
        blocker.firstVertex += point(0, 1000)
        blocker.secondVertex += point(0, 1000)
        assert len(viewport.ConnectedCounterPath([counter])[1]) == 4
    # Stools, plants, sinks and other furnishings never cut counter dimensions.
    viewport.walls = [counter]
    baseline = viewport.ConnectedCounterPath([counter])[1]
    for origin in (point(1000, 600), point(1000, 0), point(0, 0)):
        viewport.furnishings = [Furnishing({"width": 2000, "length": 600}, origin)]
        assert viewport.ConnectedCounterPath([counter])[1] == baseline
    viewport.furnishings = []
    blocker = Wall(point(-120, -1000), point(-120, 1000), 240)
    viewport.walls = [counter, blocker]
    assert len(viewport.ConnectedCounterPath([counter])[1]) == 3  # Flush end cap.
    blocker.firstVertex, blocker.secondVertex = point(500, 420), point(1500, 420)
    dimensions = viewport.ConnectedCounterPath([counter])[1]
    topSpans = [QtCore.QLineF(first, second).length() for first, second, owners in dimensions
                if abs(first.y() - 300) < .1 and abs(second.y() - 300) < .1]
    assert len(topSpans) == 2 and all(abs(length - 500) < .1 for length in topSpans)
    viewport.hiddenObjects = [blocker]
    viewport.hiddenObjectIds = {id(blocker)}
    assert len(viewport.ConnectedCounterPath([counter])[1]) == 4
    viewport.walls = [counter]
    counter.secondVertex = point(1200, 1600)
    dimensions = viewport.ConnectedCounterPath([counter])[1]
    assert sorted(round(QtCore.QLineF(first, second).length()) for first, second, owners in dimensions) == [600, 600, 2000, 2000]
    main.close()


if __name__ == "__main__":
    Main()
