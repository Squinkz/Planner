"""Counter selection fills respect ownership, groups and warm scene caches."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.graphics.palette import themeColors
from planner_app.models import Counter


def Main():
    with ExampleWindow() as (main, folder):
        v, point = main.viewport, QtCore.QPointF
        first = Counter(point(-1500, 0), point(), 600, secondMiter = .5)
        second = Counter(point(), point(0, 1500), 400, firstMiter = .5)
        InstallScene(main, [first, second])
        v.showGrid = v.showMeasurements = False
        v.hoverPosition = None

        def CheckPixels(firstRole, secondRole):
            image = v.grab().toImage()
            for position, role in ((point(-900, 30), firstRole), (point(20, 900), secondRole), (point(-900, 600), "canvas")):
                pixel = v.WorldToViewport(position) * image.devicePixelRatio()
                actual = image.pixelColor(round(pixel.x()), round(pixel.y()))
                assert actual == QtGui.QColor(themeColors[role]), (position, role, actual.name(), themeColors[role])

        for zoom in (.5, 1, 1.25):
            v.zoom = zoom
            v.SetSelection([])
            CheckPixels("canvas", "canvas")
            v.SetSelection([(first, None)])
            CheckPixels("selectionFill", "canvas")
            CheckPixels("selectionFill", "canvas")  # Cached repeat.
            v.SetSelection([(first, None), (second, None)])
            CheckPixels("selectionFill", "selectionFill")
            v.objectGroups = [(first, second)]
            v.SetSelection([(first, None)])
            CheckPixels("groupSelectionFill", "groupSelectionFill")
            v.objectGroups = []
            v.SetSelection([])
            CheckPixels("canvas", "canvas")
    print("Counter highlights: selected/group fills, joined ownership, deselection, zoom and cached paints passed")


if __name__ == "__main__":
    Main()
