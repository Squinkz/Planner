"""Vector pixel diagnostics match an independent stored-byte oracle."""
import os
from pathlib import Path
import random
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtGui
from image_comparison import ChangedPixels, ImageChannels


def Main():
    randomizer = random.Random(20261030)
    comparisons = 0
    for imageFormat in (QtGui.QImage.Format.Format_RGB32, QtGui.QImage.Format.Format_ARGB32,
                        QtGui.QImage.Format.Format_ARGB32_Premultiplied, QtGui.QImage.Format.Format_RGBA8888):
        for width, height in ((1, 1), (3, 7), (17, 19)):
            for padding in (0, 12):
                stride = width * 4 + padding
                first = bytearray(randomizer.randbytes(stride * height))
                for mode in ("identical", "padding", "sparse", "all"):
                    second = first.copy()
                    for y in range(height):
                        if mode == "padding":
                            for offset in range(y * stride + width * 4, (y + 1) * stride):
                                second[offset] ^= 255
                        elif mode == "sparse":
                            second[y * stride + (y % width) * 4 + y % 4] ^= 255
                        elif mode == "all":
                            for offset in range(y * stride, y * stride + width * 4):
                                second[offset] ^= 255
                    left = QtGui.QImage(first, width, height, stride, imageFormat)
                    right = QtGui.QImage(second, width, height, stride, imageFormat)
                    left.setDevicePixelRatio(1.5)
                    right.setDevicePixelRatio(1.5)
                    expectedIndices, expectedErrors = [], []
                    for y in range(height):
                        for x in range(width):
                            offset = y * stride + x * 4
                            errors = [abs(a - b) for a, b in zip(first[offset:offset + 4], second[offset:offset + 4])]
                            if any(errors):
                                expectedIndices.append(y * width + x)
                                expectedErrors.append(max(errors))
                    indices, errors = ChangedPixels(left, right)
                    assert indices.tolist() == expectedIndices, (imageFormat, width, padding, mode)
                    assert errors.tolist() == expectedErrors, (imageFormat, width, padding, mode)
                    assert ImageChannels(left).shape == (height, width, 4)
                    assert first == bytearray(left.constBits()), "Comparison modified its source"
                    assert second == bytearray(right.constBits()), "Comparison modified its source"
                    comparisons += 1
    for first, second in ((QtGui.QImage(3, 2, QtGui.QImage.Format.Format_RGB32),
                           QtGui.QImage(2, 3, QtGui.QImage.Format.Format_RGB32)),
                          (QtGui.QImage(3, 2, QtGui.QImage.Format.Format_RGB32),
                           QtGui.QImage(3, 2, QtGui.QImage.Format.Format_RGBA8888)),
                          (QtGui.QImage(3, 2, QtGui.QImage.Format.Format_Grayscale8),
                           QtGui.QImage(3, 2, QtGui.QImage.Format.Format_Grayscale8))):
        try:
            ChangedPixels(first, second)
        except ValueError:
            pass
        else:
            raise AssertionError("Incompatible image comparison was accepted")
    print(f"{comparisons} comparisons preserve channel errors, pixel order, padding, alpha and source bytes")


if __name__ == "__main__":
    Main()
