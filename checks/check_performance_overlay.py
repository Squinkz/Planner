"""Actual paint sampling and an independent, noninteractive metrics overlay."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets, QtTest
from planner import MainWindow
from theme import BuildStyle
from planner_app.graphics.palette import themeColors


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    assert not v.showFpsCounter and not v.performanceLabel.isVisible() and not v.performanceTimer.isActive()
    main.SetViewOption("showFpsCounter")
    app.processEvents()
    assert v.showFpsCounter and v.performanceLabel.isVisible() and v.performanceTimer.isActive()
    assert v.performanceLabel.testAttribute(QtCore.Qt.WidgetAttribute.WA_OpaquePaintEvent), "Label opacity was reset during styling."
    assert v.renderSamples and all(duration > 0 for timestamp, duration in v.renderSamples)
    v.performanceTimer.stop()
    v.renderSamples.clear()
    v.renderSamples.extend([(99.5 + index * .01, 2.0) for index in range(51)])
    with patch("planner_app.viewport.widget.perf_counter", return_value = 100.0):
        v.RefreshPerformance()
    assert v.performanceLabel.text() == "FPS: 100.0 | Render: 2.0 ms"
    app.processEvents()
    main.grab().save("screenshots/performance-overlay.png")
    v.renderSamples.clear()
    with patch("planner_app.viewport.widget.perf_counter", return_value = 102.0):
        v.RefreshPerformance()
    app.processEvents()
    assert v.performanceLabel.text() == "FPS: Idle | Render: 2.0 ms"
    assert not v.renderSamples, "Updating the label must not redraw the scene."
    # Repaint into the same pixels: shorter text must erase every old glyph.
    image = QtGui.QImage(v.performanceLabel.size(), QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    v.performanceLabel.setText("FPS: 123456.7 | Render: 987.6 ms")
    v.performanceLabel.render(image, QtCore.QPoint(), QtGui.QRegion(), QtWidgets.QWidget.RenderFlag(0))
    v.performanceLabel.setText("FPS: Idle")
    v.performanceLabel.render(image, QtCore.QPoint(), QtGui.QRegion(), QtWidgets.QWidget.RenderFlag(0))
    cleanImage = QtGui.QImage(image.size(), image.format())
    cleanImage.fill(QtGui.QColor(themeColors["canvas"]))
    v.performanceLabel.render(cleanImage, QtCore.QPoint(), QtGui.QRegion(), QtWidgets.QWidget.RenderFlag(0))
    assert image == cleanImage, "Shorter text must completely clear the previous frame."
    app.processEvents()
    v.renderSamples.clear()
    v.performanceTimer.start()
    QtTest.QTest.qWait(600)
    assert not v.renderSamples, "The metrics timer must not manufacture frames at rest."
    assert v.performanceLabel.testAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    main.SetViewportOnlyMode(True)
    app.processEvents()
    assert v.performanceLabel.isVisible()
    assert v.performanceLabel.x() == v.rulerSize + 12
    assert v.performanceLabel.geometry().bottom() == v.height() - 13
    main.close()
    print("PASS: FPS/render timings, idle behavior, no timer-induced scene paints, and fullscreen position.")


if __name__ == "__main__":
    Main()
