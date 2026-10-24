"""Automatic stair density, corner landing tread limits and plain step-size labels."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Stair
from theme import BuildStyle


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyle("Fusion")
    app.setStyleSheet(BuildStyle())
    window = MainWindow()
    window.SetThemes(uiTheme = "Dark UI", canvasTheme = "Dark Canvas")  # Fixed palette for pixel assertions.
    window.show()
    app.processEvents()
    viewport = window.viewport
    viewport.unitsMode = "Adaptive Metric"  # Label and property expectations use meters/centimeters.
    point = QtCore.QPointF
    horizontal = Stair(point(-2500, 0), point())
    vertical = Stair(point(), point(0, 2500))
    assert horizontal.stepCount == vertical.stepCount == 9
    assert abs(horizontal.stepSize - 2500 / 9) < 1e-8
    viewport.walls = [horizontal, vertical]
    viewport.EnsureObjectIds()
    viewport.showGrid = False
    viewport.panOffset = point(120, 140)
    viewport.grab()
    assert horizontal.stepCount == vertical.stepCount == 8
    assert 250 <= horizontal.stepSize <= 300 and 250 <= vertical.stepSize <= 300
    assert viewport.StairLandingTrims(horizontal, viewport.walls) == (0, 500)
    assert viewport.StairLandingTrims(vertical, viewport.walls) == (500, 0)
    image = viewport.grab().toImage()
    # Old tread positions inside the landing are blank; the inner corner
    # limits have tread lines across the whole width of each adjoining run.
    for sample in (point(-250, 200), point(200, 250)):
        assert image.pixelColor(viewport.WorldToViewport(sample).toPoint()).name() == "#0e0e0e"
    for sample in (point(-500, 200), point(200, 500)):
        assert image.pixelColor(viewport.WorldToViewport(sample).toPoint()).name() != "#0e0e0e"
    viewport.selectedWall = vertical
    window.RefreshProperties()
    assert isinstance(window.stepSizeLabel, QtWidgets.QLabel) and window.stepSizeLabel.text() == "28.57 cm"
    assert window.stepCountLabel.text() == "8"
    # Usable run excludes the 500 mm landing; total count includes it once.
    window.propertyFields["length"].setValue(3)
    assert vertical.stepCount == 10 and abs(vertical.stepSize - 2500 / 9) < 1e-8
    window.EditProperty("stepCount", 3)
    assert vertical.stepCount == 10
    viewport.Undo()
    assert vertical.stepCount == 8
    # Width changes invalidate the landing cache and move the inner corner.
    horizontal.width = 600
    viewport.ConnectedStairPath(viewport.walls)
    assert viewport.StairLandingTrims(vertical, viewport.walls) == (300, 0)
    horizontal.width = 1000
    # A landing at each end contributes one step per landing, not tread depth.
    lastRun = Stair(point(0, 2500), point(1500, 2500))
    vertical.sceneStairs = [horizontal, vertical, lastRun]
    treadCount, stepSize, landingCount = vertical.StepLayout()
    assert landingCount == 2 and vertical.stepCount == treadCount + 2
    assert 250 <= stepSize <= 300
    # Short solo runs choose the closest achievable size when no whole-number
    # count fits the range; ordinary lengths always remain within it.
    short = Stair(point(), point(200, 0))
    assert short.stepCount == 1 and short.stepSize == 200
    for length in (1000, 1500, 2000, 2750, 4000):
        solo = Stair(point(), point(length, 0))
        assert 250 <= solo.stepSize <= 300
        assert abs(solo.stepCount * solo.stepSize - length) < 1e-8
    # Reversing endpoint order simply swaps which endpoint is trimmed.
    reversedRun = Stair(horizontal.secondVertex, horizontal.firstVertex)
    viewport.ConnectedStairPath([reversedRun, vertical])
    assert viewport.StairLandingTrims(reversedRun, [reversedRun, vertical]) == (500, 0)
    viewport.selectedWall, viewport.selectedVertex = vertical, None
    window.RefreshProperties()
    app.processEvents()
    window.buildScrollArea.ensureWidgetVisible(window.stepSizeLabel)
    app.processEvents()
    window.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots" / "stair-landings.png"))
    window.close()
    print("PASS: 25-30 cm derived treads, landing counts and undo, plain labels, landing tread limits, width changes and reversed endpoints.")


if __name__ == "__main__":
    Main()
