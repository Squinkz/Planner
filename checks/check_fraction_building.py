"""Native, constructed and last-resort fraction paths share canvas typography."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.measurement_text import FractionTextPath, MeasurementTextPath


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    font = QtGui.QFont("D-DIN Condensed", 24)
    samples = ("1/4", "1/2", "3/4", "1/8", "3/8", "7/8", "1/16", "15/16")
    for text in samples:
        path, advance, strategy = FractionTextPath(text, font.toString(), 96)
        assert strategy == ("native" if text in ("1/4", "1/2", "3/4") else "built")
        assert not path.isEmpty() and advance >= path.boundingRect().width() - 2
        assert FractionTextPath(text, QtGui.QFont("Noto Sans", 24).toString(), 96)[2] == "native"
    FractionTextPath.cache_clear()
    with patch.object(QtGui.QRawFont, "supportsCharacter", return_value = False):
        path, advance, strategy = FractionTextPath("15/16", font.toString(), 96)
        assert strategy == "fallback" and not path.isEmpty()
    FractionTextPath.cache_clear()
    image = QtGui.QImage(840, 180, QtGui.QImage.Format.Format_RGB32)
    image.fill("#f0f0f0")
    with QtGui.QPainter(image) as painter:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.GlobalColor.black)
        for index, text in enumerate(samples):
            path = MeasurementTextPath('2\' 3 ' + text + '"', font.toString(), 96)
            painter.save()
            painter.translate(15 + index % 4 * 210, 55 + index // 4 * 85)
            painter.fillPath(path, QtCore.Qt.GlobalColor.black)
            painter.restore()
    image.save(str(Path(__file__).resolve().parent.parent / "screenshots/fraction-building.png"))
    print("PASS: native common fractions, constructed arbitrary fractions, missing-glyph fallback and mixed labels.")


if __name__ == "__main__":
    Main()
