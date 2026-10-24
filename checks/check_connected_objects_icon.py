"""Connected Objects artwork renders its hatch without unsupported SVG patterns."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from planner_app.graphics.icons import UiIconPath, uiIconColors


def Main():
    app = QtWidgets.QApplication([])
    messages = []
    previousHandler = QtCore.qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    try:
        for color in (None, uiIconColors["iconDisabled"]):
            renderer = QtSvg.QSvgRenderer(str(UiIconPath("con_obj", color)))
            assert renderer.isValid()
            image = QtGui.QImage(96, 96, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(QtCore.Qt.GlobalColor.transparent)
            painter = QtGui.QPainter(image)
            renderer.render(painter)
            painter.end()
            pixels = [image.pixelColor(x, 48) for x in range(12, 84)]
            assert any(pixel.alpha() == 255 for pixel in pixels), "Hatch is missing"
            assert any(pixel.alpha() == 0 for pixel in pixels), "Hatch became a solid fill"
            assert {pixel.name() for pixel in pixels if pixel.alpha() == 255} == {color or uiIconColors["icon"]}
            if color is None:
                image.save(str(root / "diagnostics/connected-objects-icon.png"))
    finally:
        QtCore.qInstallMessageHandler(previousHandler)
    assert not messages, messages


if __name__ == "__main__":
    Main()
