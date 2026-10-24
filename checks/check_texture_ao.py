"""AO companion discovery, ordering, shared strength, placement and missing maps."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow
from planner_app.graphics import compositing
from planner_app.ui import export_panel


def Main():
    app = QtWidgets.QApplication([])
    with tempfile.TemporaryDirectory() as folder:
        directory = Path(folder)
        textures = directory / "textures"
        textures.mkdir()
        normal = QtGui.QImage(2, 2, QtGui.QImage.Format.Format_RGB32)
        normal.fill(QtGui.QColor(255, 128, 255))
        names = ("leather_1_t1_5_5_5_10.png", "paper_s.png", "plain.png", "missing_t1.png")
        for name in names:
            normal.save(str(textures / name))
        ao = QtGui.QImage(2, 2, QtGui.QImage.Format.Format_RGBA8888)
        ao.fill(QtGui.QColor(128, 128, 128, 0))
        for name in ("leather_1", "paper", "plain"):
            ao.save(str(textures / (name + "_ao.png")))
        with patch.object(compositing, "texturesDirectory", directory / "textures"), patch.object(export_panel, "texturesDirectory", directory / "textures"):
            for name in names:
                for strength in (0, .5, 1):
                    image = QtGui.QImage(12, 12, QtGui.QImage.Format.Format_RGB32)
                    image.fill(QtGui.QColor(200, 200, 200))
                    with QtGui.QPainter(image) as painter:
                        compositing.DrawNormalTexture(painter, QtCore.QRectF(2, 2, 8, 8), name, 0, (8, 8), strength = strength)
                    expected = 200 * (1 - .5 * strength)
                    if not name.startswith("missing"):
                        expected *= 1 - strength * (1 - 128 / 255)
                    assert abs(image.pixelColor(5, 5).red() - expected) <= 2, (name, strength, image.pixelColor(5, 5))
                    assert image.pixelColor(0, 0).red() == 200
            main = MainWindow()
            assert main.exportPanel.textureField.count() == len(names) + 1
            assert all(not str(main.exportPanel.textureField.itemData(index)).endswith("_ao.png")
                       for index in range(main.exportPanel.textureField.count()))
            main.close()
            # Resolution changes must preserve corresponding left/right regions
            # and the normal map's eight-pixel tile period.
            normal = QtGui.QImage(8, 8, QtGui.QImage.Format.Format_RGB32)
            for y in range(8):
                for x in range(8):
                    normal.setPixelColor(x, y, QtGui.QColor(255 if x < 4 else 128, 128, 255))
            for size in (4, 16):
                ao = QtGui.QImage(size, size, QtGui.QImage.Format.Format_RGB32)
                for y in range(size):
                    for x in range(size):
                        value = 128 if x < size / 2 else 255
                        ao.setPixelColor(x, y, QtGui.QColor(value, value, value))
                for mapping in ("t1", "s"):
                    name = f"aligned{size}_{mapping}.png"
                    normal.save(str(textures / name))
                    ao.save(str(textures / f"aligned{size}_ao.png"))
                    image = QtGui.QImage(20, 12, QtGui.QImage.Format.Format_RGB32)
                    image.fill(QtGui.QColor(200, 200, 200))
                    with QtGui.QPainter(image) as painter:
                        compositing.DrawNormalTexture(painter, QtCore.QRectF(2, 2, 16, 8), name, 0, (16, 8))
                    positions = ((3, 50), (8, 198), (11, 50), (16, 198)) if mapping == "t1" else ((4, 50), (15, 198))
                    for x, expected in positions:
                        assert abs(image.pixelColor(x, 5).red() - expected) <= 2, (size, mapping, x, image.pixelColor(x, 5))
    print("PASS: AO naming, multiply after normal lighting, shared overall strength, alpha ignored and missing companions.")


if __name__ == "__main__":
    Main()
