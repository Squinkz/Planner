"""Reject external SVG images; hide tracing images and retain visible embedded PNGs."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from planner_app.graphics.furnishings import FurnishingRenderer, SelectedFurnishingRenderer
from planner_app.paths import furnishingsDirectory


def Main():
    app = QtWidgets.QApplication([])
    messages = []
    previousHandler = QtCore.qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    try:
        pixel = QtGui.QImage(1, 1, QtGui.QImage.Format.Format_ARGB32)
        pixel.fill(QtGui.QColor("red"))
        data = QtCore.QByteArray()
        buffer = QtCore.QBuffer(data)
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        assert pixel.save(buffer, "PNG")
        encoded = bytes(data.toBase64()).decode("ascii")
        source = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 100 100">
          <image style="display:none" width="100" height="100" xlink:href="missing-tracing.jpg"/>
          <g style="display: none;"><image width="100" height="100" xlink:href="missing-layer.jpg"/></g>
          <g display="none"><g><image width="100" height="100" xlink:href="missing-nested.jpg"/></g></g>
          <image width="100" height="100" xlink:href="data:image/png;base64,{encoded}"/>
        </svg>'''.encode()
        assert not FurnishingRenderer(source).isValid(), "Hidden external resources must be rejected too"
        source = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 100 100">
          <image style="display:none" width="100" height="100" xlink:href="data:image/png;base64,{encoded}"/>
          <g style="display: none;"><image width="100" height="100" xlink:href="data:image/png;base64,{encoded}"/></g>
          <g display="none"><g><image width="100" height="100" xlink:href="data:image/png;base64,{encoded}"/></g></g>
          <image width="20" height="20" xlink:href="data:image/png;base64,{encoded}"/>
        </svg>'''.encode()
        renderer = FurnishingRenderer(source)
        assert renderer.isValid()
        image = QtGui.QImage(100, 100, QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        with QtGui.QPainter(image) as painter:
            renderer.render(painter, QtCore.QRectF(0, 0, 100, 100))
        assert image.pixelColor(10, 10) == QtGui.QColor("red")
        assert image.pixelColor(50, 50).alpha() == 0, "A hidden embedded tracing image became visible"
        sedanPath = furnishingsDirectory / "images/sedan.svg"
        original = sedanPath.read_bytes()
        for renderer in (FurnishingRenderer(sedanPath), SelectedFurnishingRenderer(sedanPath),
                         FurnishingRenderer(sedanPath, solidBackground = False)):
            assert renderer.isValid()
        main = MainWindow()
        main.show()
        app.processEvents()
        main.close()
        assert sedanPath.read_bytes() == original
        assert not any("Image filename is empty" in message for message in messages), messages
    finally:
        QtCore.qInstallMessageHandler(previousHandler)
    print("PASS: external references rejected, hidden embedded images omitted, visible PNG preserved, clean startup and unchanged SVG sources")


if __name__ == "__main__":
    Main()
