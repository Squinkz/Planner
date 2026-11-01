"""CPU command batching, formatted length reuse and conservative symbol culling."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Door, SilledWindow, SlidingDoor
from planner_app.viewport import rendering
from planner_app.graphics.text import PathTextPainter
from check_editor_zoom_measurements import FreshFrame


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        p = QtCore.QPointF
        near = Wall(p(-3000, 0), p(3000, 0), 200)
        far = Wall(p(50000, 50000), p(56000, 50000), 200)
        door, window = Door(near, .2, .35), SilledWindow(near, .6, .8)
        window.sillDepth = 700
        window.windowWell = True
        window.wellDepth = 1100
        InstallScene(main, [near, far, door, window, SlidingDoor(far, .2, .5)])
        v.setFixedSize(1000, 700)
        v.zoom = .5
        v.showMeasurements = v.showTips = False
        v.grab()
        v.viewportSceneKey = None
        with patch.object(rendering, "DrawOpeningSymbol", wraps = rendering.DrawOpeningSymbol) as symbols:
            actual = v.grab().toImage()
            assert symbols.call_count == 2, "Offscreen opening symbol was submitted"
        # The same valid scene without the editor-only culling gives a direct
        # all-symbol reference, including deep sills and window wells.
        v.exportRender = True
        v.viewportSceneKey = None
        with patch.object(rendering, "DrawOpeningSymbol", wraps = rendering.DrawOpeningSymbol) as symbols:
            expected = v.grab().toImage()
            assert symbols.call_count == 3
        # Export uses its own ruler typography. Compare the scene interior,
        # leaving that deliberately different frame out of the culling oracle.
        sceneRect = v.DrawingRect().toAlignedRect().adjusted(1, 1, -1, -1)
        assert actual.copy(sceneRect) == expected.copy(sceneRect), "Opening culling removed visible ink"
        v.exportRender = False
        v.showMeasurements = True
        FreshFrame(v)
        batches = []
        inMeasurements = [False]
        original = v.DrawSceneMeasurements
        def Measure(*arguments, **keywords):
            inMeasurements[0] = True
            try:
                return original(*arguments, **keywords)
            finally:
                inMeasurements[0] = False
        def Lines(painter, lines):
            if inMeasurements[0] and isinstance(painter.device(), QtGui.QPicture):
                batches.append(len(lines))
            return QtGui.QPainter.drawLines(painter, lines)
        # The retained editor no longer records these strokes every zoom. Keep
        # checking the original batched recorder used by export and fallback.
        with patch.object(v, "DrawRetainedMeasurements", return_value = False), \
                patch.object(rendering, "StackedDimensionLengths", side_effect = AssertionError("Zoom rebuilt formatted world lengths")), \
                patch.object(v, "DrawSceneMeasurements", Measure), patch.object(PathTextPainter, "drawLines", Lines):
            for factor in (1.1, .8, 1.2):
                v.ZoomBy(factor, v.DrawingRect().center())
                v.grab()
        assert any(count >= 3 for count in batches), "Dimension segments were not batched"
        old = v.measurementLabelRecords
        v.measurementPrecision = "Low" if v.measurementPrecision != "Low" else "High"
        v.viewportSceneKey = None
        actual = v.grab().toImage()
        assert v.measurementLabelRecords is not old, "Precision retained stale formatted labels"
        v.measurementLabelRecords = None
        assert actual == FreshFrame(v)
        assert len(v.measurementLabelRecords[-1]) <= 4096
        font = QtGui.QFont(v.font())
        font.setPointSizeF(max(1, font.pointSizeF()) + 3)
        v.setFont(font)
        v.viewportSceneKey = None
        actual = v.grab().toImage()
        assert actual == FreshFrame(v), "Cached label width ignored a font change"
        v.unitsMode = "Feet and Inches"
        v.viewportSceneKey = None
        actual = v.grab().toImage()
        assert actual == FreshFrame(v), "Cached labels ignored imperial formatting"
    print("CPU dimension batching and preparation reuse passed; culled opening pixels match all-symbol rendering")


if __name__ == "__main__":
    Main()
