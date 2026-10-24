"""Grid fallback snaps control vertices exactly, independently of cap width."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Wall, Stair, Counter, Railing, Arrow, MeasurementGuide
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v, point = main.viewport, QtCore.QPointF
    v.snapEnabled = v.gridSnapEnabled = True
    v.vertexSnapEnabled = v.midpointSnapEnabled = v.alignmentSnapEnabled = False
    for cls in (Wall, Stair, Counter, Railing, Arrow, MeasurementGuide):
        for width in ((0,) if cls is MeasurementGuide else (80, 240, 1100)):
            for zoom in (.5, 1, 3.2):
                v.zoom = zoom
                source = cls(point(-1600, -1300), point(400, 300), width)
                v.walls = [source]
                v.SetSelection([(source, 1)])
                unused, spacing = v.GridSteps()
                for position in (point(-2, 98), point(173, 367), point(-241, -193)):
                    expected = point(round(position.x() / spacing) * spacing, round(position.y() / spacing) * spacing)
                    snapped = v.SnapStairVertex(position, source.firstVertex, source, QtCore.Qt.KeyboardModifier.NoModifier)
                    assert snapped == expected, (cls.__name__, width, zoom, snapped, expected)
                    assert v.snapPriority == 2 and not v.alignmentGuides
    # Exercise the complete vertex gesture, including integer screen coordinates.
    v.zoom = 1
    for cls in (Wall, Stair, Counter, Railing):
        source = cls(point(-1000, 0), point(500, 0))
        v.walls = [source]
        v.SetSelection([(source, 1)])
        Drag(v, v.WorldToViewport(source.secondVertex).toPoint(), v.WorldToViewport(point(173, 367)).toPoint())
        unused, spacing = v.GridSteps()
        vertex = source.secondVertex
        assert abs(vertex.x() / spacing - round(vertex.x() / spacing)) < 1e-9
        assert abs(vertex.y() / spacing - round(vertex.y() / spacing)) < 1e-9
    main.close()


if __name__ == "__main__":
    Main()
