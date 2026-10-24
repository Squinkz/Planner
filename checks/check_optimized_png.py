"""Optimized PNG encoding, print density and third-option export integration."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall
from planner_app.optimized_png import EncodeOptimizedPng
from planner_app.graphics.theme import ApplyApplicationTheme


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    # Exercise odd dimensions, intermediate alpha and print-density metadata.
    image = QtGui.QImage(71, 43, QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(image)
    painter.fillRect(1, 1, 30, 30, QtGui.QColor(30, 70, 120, 128))
    painter.fillRect(35, 1, 30, 30, QtGui.QColor(220, 190, 160))
    painter.end()
    image.setDotsPerMeterX(11811)
    image.setDotsPerMeterY(11811)
    messages = []
    previousHandler = QtCore.qInstallMessageHandler(lambda kind, context, message: messages.append((context.category, message)))
    try:
        encoded = EncodeOptimizedPng(image)
    finally:
        QtCore.qInstallMessageHandler(previousHandler)
    assert not [message for category, message in messages if category == "qt.qml.usedbeforedeclared"], messages
    with patch.object(Path, "read_text", return_value = "function {"):
        try:
            EncodeOptimizedPng(image)
        except RuntimeError as error:
            assert "initialize optimized PNG" in str(error)
        else:
            raise AssertionError("JavaScript initialization errors must remain visible")
    assert encoded[:8] == b"\x89PNG\r\n\x1a\n"
    decoded = QtGui.QImage.fromData(encoded, "PNG")
    assert decoded.size() == image.size()
    assert decoded.pixelColor(0, 0).alpha() == 0
    assert decoded.pixelColor(5, 5).alpha() == 128
    assert decoded.pixelColor(40, 5) == image.pixelColor(40, 5)
    assert decoded.dotsPerMeterX() == 11811 and decoded.dotsPerMeterY() == 11811

    with tempfile.TemporaryDirectory() as directory:
        main = MainWindow()
        main.show()
        main.viewport.walls = [Wall(QtCore.QPointF(0, 0), QtCore.QPointF(2000, 0), 160)]
        main.projectPath = Path(directory) / "example.plan"
        panel = main.exportPanel
        main.sidebarTabs.setCurrentWidget(panel)
        panel.scaleField.setValue(60)
        assert panel.typeField.itemData(2) == "PNG_OPTIMIZED"
        panel.typeField.setCurrentIndex(2)
        assert panel.compositeSection.isVisible() and panel.resolutionRow.isVisible()
        assert main.viewport.exportOverlay.outputFormat == "png"
        assert Path(panel.pathField.text()).suffix == ".png"
        assert panel.scaleUnitsField.currentText() == "px/m"
        panel.SetScaleOption("scaleMode", "Architectural")
        assert abs(panel.ScalePerMeter() - 300 * 1000 / (25.4 * 100)) < .001
        panel.SetScaleOption("scaleMode", "Digital")
        panel.SetOverride("vignetteEnabled", True)
        image = panel.Render("png")
        path = Path(directory) / "optimized.png"
        panel.pathField.setText(str(path))
        with patch.object(main, "ShowAppMessage") as message:
            panel.Export()
            assert not message.called, message.call_args
        data = path.read_bytes()
        assert data[25] == 3, "Expected an indexed PNG"
        assert QtGui.QImage(str(path)).size() == image.size()
        assert main.exportButton.isEnabled() and app.overrideCursor() is None
        # Selecting the optimized file filter keeps the third option and .png suffix.
        with patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value = (str(path), "Optimized PNG images (*.png)")):
            panel.BrowsePath()
        assert panel.typeField.currentData() == "PNG_OPTIMIZED"
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        assert Path(panel.pathField.text()).suffix == ".svg"
        panel.UndoExport()
        assert panel.typeField.currentData() == "PNG_OPTIMIZED"
        assert main.viewport.exportOverlay.outputFormat == "png"
        # Encoding failure must leave the existing destination intact.
        panel.pathField.setText(str(path))
        with patch("planner_app.optimized_png.EncodeOptimizedPng", side_effect = RuntimeError("Encoding failed")):
            with patch.object(main, "ShowAppMessage", return_value = QtWidgets.QMessageBox.StandardButton.Yes) as message:
                panel.Export()
                assert message.call_args.args[:2] == ("Export Failed", "Encoding failed")
        assert path.read_bytes() == data
        main.MarkProjectClean()
        main.close()
    print("PASS: optimized PNG palette, transparency, DPI, raster controls, file filter, undo and atomic errors")


if __name__ == "__main__":
    Main()
