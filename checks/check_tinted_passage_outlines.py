"""Room tint alone controls passage outlines in complete editor/export paints."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
os.environ["QT_QPA_PLATFORM"] = "offscreen"


def AssertNoOutline(image, x, y, radius, fill, canvas, context):
    # Background transitions may blend canvas and room tint. Wall ink must not
    # introduce colors outside that range, including resampled export previews.
    for offset in range(-radius, radius + 1):
        color = image.pixelColor(x, y + offset)
        assert all(min(a, b) <= value <= max(a, b)
                   for a, b, value in zip(fill.getRgb(), canvas.getRgb(), color.getRgb())), (context, offset, color.name())


def Child():
    from PySide6 import QtCore, QtGui, QtWidgets
    from planner_app.models import Wall, Door, OpenDoorway
    from planner_app.viewport.widget import DrawingViewport
    from planner_app.graphics.palette import themeColors
    from check_room_detection import Rectangle
    from check_pan_dpi import CompareDirect
    app = QtWidgets.QApplication([])
    view = DrawingViewport()
    view.resize(1001, 701)
    view.performanceTimer.stop()
    view.showGrid = view.showMeasurements = view.showTips = False
    view.floors = view.solidRooms = True
    point = QtCore.QPointF
    divider = Wall(point(-2000, 0), point(2000, 0), 200)
    view.walls = Rectangle(-2000, -2000, 4000, 4000) + [divider]
    view.show()
    app.processEvents()
    view.performanceLabel.hide()
    ratio = view.devicePixelRatioF()
    fill = QtGui.QColor(themeColors["roomFill"])
    canvas = QtGui.QColor(themeColors["canvas"])
    count = 0
    for solidRooms in (False, True):
        view.solidRooms = solidRooms
        for kind in (Door, OpenDoorway):
            view.windows = [kind(divider, .35, .65)]
            for zoom in (.4, .75, 1, 1.25, 2.3, 5):
                view.zoom = zoom
                for phase in (0, .31, .77):
                    view.panOffset = point(phase, .43)
                    image = view.grab().toImage()
                    for side in (-1, 1):
                        sample = (view.WorldToViewport(point(0, side * 100)) * ratio).toPoint()
                        AssertNoOutline(image, sample.x(), sample.y(), 3, fill, canvas,
                                        (ratio, kind.__name__, zoom, phase, side, solidRooms))
                    count += 1
            view.isPanning = True
            for delta in (point(3, 1) / ratio, point(.31, .43) / ratio):
                view.panOffset += delta
                CompareDirect(view)
            view.isPanning = False
    # Untinted rooms retain the existing threshold lines, with either grid policy.
    view.floors = False
    view.windows = [OpenDoorway(divider, .35, .65)]
    view.zoom = 1
    view.panOffset = point(.31, .43)
    for solidRooms in (False, True):
        view.solidRooms = solidRooms
        image = view.grab().toImage()
        sample = (view.WorldToViewport(point(0, 100)) * ratio).toPoint()
        assert any(image.pixelColor(sample.x(), sample.y() + offset) != canvas for offset in range(-3, 4)), (ratio, solidRooms)
    view.close()
    print("PASS: DPR", ratio, count, "complete editor images across zoom/phase, native and cached pan parity")


def Exports():
    from PySide6 import QtCore, QtGui, QtSvg
    from fixtures.parity_examples import ExampleWindow, InstallScene
    from planner_app.models import Wall, Door
    from planner_app.graphics.palette import themeColors
    from check_room_detection import Rectangle
    with ExampleWindow() as (main, folder):
        view, panel = main.viewport, main.exportPanel
        point = QtCore.QPointF
        divider = Wall(point(-2000, 0), point(2000, 0), 200)
        InstallScene(main, Rectangle(-2000, -2000, 4000, 4000) + [divider, Door(divider, .35, .65)])
        view.showGrid = view.showMeasurements = view.showTips = False
        view.floors = view.solidRooms = True
        main.sidebarTabs.setCurrentWidget(panel)
        panel.borderField.setCurrentText("None")
        panel.scaleField.setValue(200)
        view.exportOverlay.bounds = (-2500, -2500, 5000, 5000)
        panel.SetBounds([-2500, -2500, 5000, 5000])
        fill = QtGui.QColor(themeColors["roomFill"])
        canvas = QtGui.QColor(themeColors["canvas"])
        for solidRooms in (False, True):
            panel.solidRoomsField.setChecked(solidRooms)
            for solidObjects in (True, False):
                panel.solidObjectsField.setChecked(solidObjects)
                # PNG and SVG output share the complete wall/door rendering path.
                for kind in ("png", "svg"):
                    result = panel.Render(kind)
                    if kind == "svg":
                        image = QtGui.QImage(1000, 1000, QtGui.QImage.Format.Format_ARGB32)
                        image.fill(0)
                        with QtGui.QPainter(image) as painter:
                            QtSvg.QSvgRenderer(result).render(painter)
                    else:
                        image = result
                    for y in (480, 520):
                        AssertNoOutline(image, 500, y, 3, fill, canvas, (kind, y, solidRooms, solidObjects))
                # Check the actual Export tab at several camera zooms, then the same
                # snapshot renderer with reduced overview sampling and detail scales.
                overlay = view.exportOverlay
                for outputType in ("PNG", "SVG"):
                    panel.typeField.setCurrentIndex(panel.typeField.findData(outputType))
                    for zoom in (.5, 1, 2.3, 5):
                        view.zoom = zoom
                        view.panOffset = point(.31, .43)
                        image = view.grab().toImage()
                        ratio = view.devicePixelRatioF()
                        for side in (-1, 1):
                            sample = (view.WorldToViewport(point(0, side * 100)) * ratio).toPoint()
                            AssertNoOutline(image, sample.x(), sample.y(), 2, fill, canvas, ("preview", outputType, zoom, side, solidRooms, solidObjects))
                        assert not overlay.previewError
                for sampling in (.2, .55, 1):
                    image = overlay.CaptureRaster(QtCore.QRectF(-2500, -2500, 5000, 5000), sampling, "detail")
                    for side in (-1, 1):
                        y = round((2500 - side * 100) * .2 * sampling)
                        x = image.width() // 2
                        AssertNoOutline(image, x, y, 2, fill, canvas, ("sampling", sampling, side, solidRooms, solidObjects))
    print("PASS: full PNG/SVG, live Export preview zooms and reduced overview sampling")


if __name__ == "__main__":
    if "--child" in sys.argv:
        Child()
    else:
        for ratio in (1, 1.25, 2):
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child"],
                env = dict(os.environ, QT_SCALE_FACTOR = str(ratio)), capture_output = True, text = True, timeout = 20)
            assert result.returncode == 0, result.stdout + result.stderr
            print(result.stdout.strip())
        Exports()
