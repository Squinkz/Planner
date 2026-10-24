"""Control vertices remain snap anchors when translating complete objects."""
import os
import sys
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Wall, Counter, Railing, Stair, Arrow, MeasurementGuide
from check_history import Drag


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    point = QtCore.QPointF
    v.ResetView()
    v.connectedEnabled = False
    v.snapEnabled = v.vertexSnapEnabled = True
    v.gridSnapEnabled = v.alignmentSnapEnabled = v.midpointSnapEnabled = False
    v.windows, v.furnishings, v.labels = [], [], []
    target = Wall(point(2000, 500), point(4000, 500), 600)
    for cls in (Wall, Counter, Railing, Stair, Arrow, MeasurementGuide):
        for grouped in (False, True):
            source = cls(point(-1000, 0), point(1000, 0), 200 if cls is not MeasurementGuide else 0)
            other = Arrow(point(-2000, -2000), point(-1000, -2000))
            v.walls = [source, target] + ([other] if grouped else [])
            entries = [(source, None)] + ([(other, None)] if grouped else [])
            v.SetSelection(entries)
            # Grab the measurement line away from its independently draggable label.
            grabPoint = point(-500, 0) if cls is MeasurementGuide else point()
            start = v.WorldToViewport(grabPoint).toPoint()
            # Stop 20 mm short of the target centerline vertex; corners are 100+
            # mm away so only the control vertex can supply the exact correction.
            end = v.WorldToViewport(grabPoint + point(980, 480)).toPoint()
            Drag(v, start, end)
            assert QtCore.QLineF(source.secondVertex, target.firstVertex).length() < .01, (cls.__name__, grouped, source.secondVertex)
            assert QtCore.QLineF(source.firstVertex, point(0, 500)).length() < .01
            v.Undo()
            assert source.firstVertex == point(-1000, 0) and source.secondVertex == point(1000, 0)
    main.close()
    print("PASS: whole-object and group translation snap control vertices while retaining object dimensions and undo.")


if __name__ == "__main__":
    Main()
