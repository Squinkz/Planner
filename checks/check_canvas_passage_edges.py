"""Canvas passage edges match native thin-line antialiasing, without wall fringes."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
os.environ["QT_QPA_PLATFORM"] = "offscreen"


def Child():
    from PySide6 import QtCore, QtGui, QtWidgets
    from planner_app.models import Wall, Door, OpenDoorway
    from planner_app.viewport.widget import DrawingViewport
    from planner_app.graphics.palette import themeColors
    from planner_app.graphics.linework import LinePen
    from check_room_detection import Rectangle
    app = QtWidgets.QApplication([])
    view = DrawingViewport()
    view.resize(1001, 701)
    view.performanceTimer.stop()
    view.showGrid = view.showMeasurements = view.showTips = view.floors = False
    view.show()
    app.processEvents()
    view.performanceLabel.hide()
    point = QtCore.QPointF
    ratio = view.devicePixelRatioF()
    comparisons = 0
    for angle in (0, 37, 90):
        transform = QtGui.QTransform().rotate(angle)
        divider = Wall(point(-2000, 0), point(2000, 0), 200)
        walls = Rectangle(-2000, -2000, 4000, 4000) + [divider]
        for wall in walls:
            wall.firstVertex = transform.map(wall.firstVertex)
            wall.secondVertex = transform.map(wall.secondVertex)
        view.walls = walls
        for kind in (Door, OpenDoorway):
            view.windows = [kind(divider, .35, .65)]
            for zoom in (.4, 1, 2.3, 5):
                view.zoom = zoom
                for phase in (0, .31, .77):
                    view.solidRooms = phase == .31
                    view.panOffset = point(phase, .43)
                    actual = view.grab().toImage()
                    expected = QtGui.QImage(actual.size(), QtGui.QImage.Format.Format_ARGB32)
                    expected.setDevicePixelRatio(ratio)
                    expected.fill(QtGui.QColor(themeColors["canvas"]))
                    with QtGui.QPainter(expected) as painter:
                        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                        edgeColor = QtGui.QColor(themeColors["objectOutline"])
                        edgeColor.setAlphaF(edgeColor.alphaF() * .2)
                        painter.setPen(LinePen(edgeColor, view.lineWidths["architectural"]))
                        firstPoint = view.WorldToViewport(view.windows[0].firstVertex)
                        secondPoint = view.WorldToViewport(view.windows[0].secondVertex)
                        direction = secondPoint - firstPoint
                        normal = QtCore.QPointF(-direction.y(), direction.x()) * (
                            divider.width * view.basePixelsPerMillimeter * zoom / (2 * QtCore.QLineF(firstPoint, secondPoint).length()))
                        for side in (-1, 1):
                            painter.drawLine(QtCore.QLineF(firstPoint + normal * side, secondPoint + normal * side))
                    for side in (-1, 1):
                        sample = (view.WorldToViewport(transform.map(point(0, side * 100))) * ratio).toPoint()
                        area = QtCore.QRect(sample.x() - 3, sample.y() - 3, 7, 7)
                        difference = max(abs(a - b) for y in range(area.top(), area.bottom() + 1)
                                         for x in range(area.left(), area.right() + 1)
                                         for a, b in zip(actual.pixelColor(x, y).getRgb(), expected.pixelColor(x, y).getRgb()))
                        # Equivalent rotated coordinates can differ by a native
                        # coverage rounding step. No displaced or extra ink fits.
                        assert difference <= 3, (ratio, angle, kind.__name__, zoom, phase, side, difference)
                        comparisons += 1
    view.close()
    print("PASS: DPR", ratio, comparisons, "native thin-line pixel comparisons across angles, zooms and camera phases")


def Exports():
    from PySide6 import QtCore, QtGui, QtSvg
    from fixtures.parity_examples import ExampleWindow, InstallScene
    from planner_app.models import Wall, Door
    from planner_app.graphics.palette import themeColors
    from planner_app.graphics.linework import LinePen
    from check_room_detection import Rectangle
    with ExampleWindow() as (main, folder):
        view, panel = main.viewport, main.exportPanel
        point = QtCore.QPointF
        divider = Wall(point(-2000, 0), point(2000, 0), 200)
        InstallScene(main, Rectangle(-2000, -2000, 4000, 4000) + [divider, Door(divider, .35, .65)])
        view.showGrid = view.showMeasurements = view.showTips = view.floors = False
        main.sidebarTabs.setCurrentWidget(panel)
        panel.roomStyleField.setCurrentText("Canvas")
        panel.borderField.setCurrentText("None")
        panel.scaleField.setValue(200)
        view.exportOverlay.bounds = (-2500, -2500, 5000, 5000)
        panel.SetBounds(list(view.exportOverlay.bounds))
        for scale in (60, 100, 150, 199, 200):
            panel.scaleField.setValue(scale)
            ppm = scale / 1000
            expected = QtGui.QImage(round(5000 * ppm), round(5000 * ppm), QtGui.QImage.Format.Format_ARGB32)
            expected.fill(QtGui.QColor(themeColors["canvas"]))
            with QtGui.QPainter(expected) as painter:
                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                edgeColor = QtGui.QColor(themeColors["objectOutline"])
                edgeColor.setAlphaF(edgeColor.alphaF() * .2)
                painter.setPen(LinePen(edgeColor, view.lineWidths["architectural"]))
                for y in (2400 * ppm, 2600 * ppm):
                    painter.drawLine(QtCore.QLineF(1900 * ppm, y, 3100 * ppm, y))
            for solid in (False, True):
                panel.solidRoomsField.setChecked(solid)
                for kind in ("png", "svg"):
                    result = panel.Render(kind)
                    if kind == "svg":
                        image = QtGui.QImage(expected.size(), expected.format())
                        image.fill(0)
                        with QtGui.QPainter(image) as painter:
                            QtSvg.QSvgRenderer(result).render(painter)
                    else:
                        image = result
                    for center in (round(2400 * ppm), round(2600 * ppm)):
                        difference = max(abs(a - b) for y in range(center - 3, center + 4)
                                         for a, b in zip(image.pixelColor(round(2500 * ppm), y).getRgb(), expected.pixelColor(round(2500 * ppm), y).getRgb()))
                        assert difference <= 3, (solid, kind, center, difference)
    print("PASS: Canvas PNG/SVG passage edges match native thin lines with Solid Rooms on/off")


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
