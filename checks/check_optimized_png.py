"""Optimized PNG encoding, print density and third-option export integration."""
import os
import json
import io
from contextlib import redirect_stdout
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtQml import QJSEngine
from planner import MainWindow, Wall
from planner_app.optimized_png import EncodeOptimizedPng
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.graphics import palette
from planner_app.export_worker import ExportJobEncoder, RunExportWorker


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

    # Cover multiple binary transfer chunks and a partial final chunk.
    # Pixels on both sides of the boundary and at the tail must remain intact.
    chunked = QtGui.QImage(257, 257, QtGui.QImage.Format.Format_RGBA8888)
    chunked.fill(QtGui.QColor("#123456"))
    chunked.setPixelColor(64, 191, QtGui.QColor("#654321"))
    chunked.setPixelColor(65, 191, QtGui.QColor("#654321"))
    chunked.setPixelColor(256, 256, QtGui.QColor("#abcdef"))
    lengths = []
    class TransferEngine(QJSEngine):
        def toScriptValue(self, value):
            if isinstance(value, QtCore.QByteArray):
                lengths.append(value.size())
            return super().toScriptValue(value)
    with patch("planner_app.optimized_png.QJSEngine", TransferEngine):
        chunkedBytes = EncodeOptimizedPng(chunked)
    assert len(lengths) > 1 and max(lengths) <= 192 * 1024
    assert sum(lengths) == chunked.sizeInBytes()
    chunkedDecoded = QtGui.QImage.fromData(chunkedBytes, "PNG").convertToFormat(chunked.format())
    assert chunkedDecoded == chunked

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
        assert panel.OutputPath().suffix == ".png"
        assert panel.scaleUnitsField.currentText() == "px/m"
        panel.SetScaleOption("scaleMode", "Architectural")
        assert abs(panel.ScalePerMeter() - 300 * 1000 / (25.4 * 100)) < .001
        panel.SetScaleOption("scaleMode", "Digital")
        panel.SetOverride("vignetteEnabled", True)
        image = panel.Render("png")
        path = Path(directory) / "optimized.png"
        panel.folderField.setText(str(path.parent))
        panel.fileNameField.setText(path.name)
        with patch.object(main, "ShowAppMessage") as message:
            panel.Export()
            assert not message.called, message.call_args
        data = path.read_bytes()
        assert data[25] == 3, "Expected an indexed PNG"
        assert QtGui.QImage(str(path)).size() == image.size()
        assert main.exportButton.isEnabled() and app.overrideCursor() is None
        # Choosing a folder keeps the selected type and filename.
        with patch.object(QtWidgets.QFileDialog, "getExistingDirectory", return_value = str(path.parent)):
            panel.BrowsePath()
        assert panel.typeField.currentData() == "PNG_OPTIMIZED"
        panel.typeField.setCurrentIndex(panel.typeField.findData("SVG"))
        assert panel.OutputPath().suffix == ".svg"
        panel.UndoExport()
        assert panel.typeField.currentData() == "PNG_OPTIMIZED"
        assert main.viewport.exportOverlay.outputFormat == "png"
        # Encoding failure must leave the existing destination intact.
        panel.folderField.setText(str(path.parent))
        panel.fileNameField.setText(path.name)
        failedPath = Path(directory) / "failed.tmp"
        job = {"render": panel.RenderArguments("png"), "optimized": True, "stagingPath": str(failedPath),
               "style": app.style().objectName(), "uiTheme": palette.activeUITheme,
               "canvasTheme": palette.activeCanvasTheme, "colors": dict(palette.themeColors), "labelFont": palette.labelFont}
        jobPath = Path(directory) / "failed-job.json"
        jobPath.write_text(json.dumps(job, cls = ExportJobEncoder), encoding = "utf-8")
        output = io.StringIO()
        with patch("planner_app.optimized_png.EncodeOptimizedPng", side_effect = RuntimeError("Encoding failed")):
            with redirect_stdout(output):
                assert RunExportWorker(jobPath) == 1
        assert '"error": "Encoding failed"' in output.getvalue()
        assert not failedPath.exists()
        assert path.read_bytes() == data
        main.MarkProjectClean()
        main.close()
    print("PASS: optimized PNG palette, transparency, DPI, raster controls, folder selection, undo and atomic errors")


if __name__ == "__main__":
    Main()
