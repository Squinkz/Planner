"""Frozen palette and pixel parity for binary transfer and native PNG compression."""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
from unittest.mock import patch
import zlib

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtGui, QtWidgets
from PySide6.QtQml import QJSEngine
from planner_app.optimized_png import EncodeOptimizedPng


def SeededEngine():
    engine = QJSEngine()
    engine.evaluate("var plannerTestSeed = 123; Math.random = function() { plannerTestSeed = (1664525 * plannerTestSeed + 1013904223) >>> 0; return plannerTestSeed / 4294967296; };")
    return engine


def TestImage(case):
    image = QtGui.QImage(case["width"], case["height"], QtGui.QImage.Format.Format_RGBA8888)
    for y in range(image.height()):
        for x in range(image.width()):
            if case["mode"] == "flat":
                index = (x // 11 + y // 13) % 7
                color = QtGui.QColor(index * 31, index * 17, index * 37, (0, 30, 60, 120, 180, 220, 255)[index])
            else:
                color = QtGui.QColor((x * 37 + y * 13) % 256, (x * 7 + y * 29) % 256,
                                     (x * 17 + y * 3) % 256, 255 if case["mode"] == "opaque" else (x * 11 + y * 19) % 256)
            image.setPixelColor(x, y, color)
    image.setDotsPerMeterX(11811)
    image.setDotsPerMeterY(11811)
    return image


def PngFingerprint(encoded):
    chunks = {}
    position = 8
    assert encoded[:8] == b"\x89PNG\r\n\x1a\n"
    while position < len(encoded):
        length = struct.unpack(">I", encoded[position:position + 4])[0]
        kind = encoded[position + 4:position + 8]
        chunks[kind] = chunks.get(kind, b"") + encoded[position + 8:position + 8 + length]
        position += length + 12
    chunks[b"IDAT"] = zlib.decompress(chunks[b"IDAT"])
    decoded = QtGui.QImage.fromData(encoded, "PNG").convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
    assert not decoded.isNull()
    return {"chunks": {kind.decode("ascii"): hashlib.sha256(value).hexdigest() for kind, value in chunks.items()},
            "pixels": hashlib.sha256(decoded.constBits()).hexdigest(), "dpi": [decoded.dotsPerMeterX(), decoded.dotsPerMeterY()]}


def Main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    fixture = json.loads((root / "checks/fixtures/optimized_png_parity.json").read_text(encoding = "utf-8"))
    for case in fixture["cases"]:
        image = TestImage(case)
        with patch("planner_app.optimized_png.QJSEngine", SeededEngine):
            encoded = EncodeOptimizedPng(image)
        assert PngFingerprint(encoded) == case["expected"], case["name"]
    print("PASS: exact palette, transparency, filtered pixels, decoded pixels and DPI against frozen UPNG/pako reference")


if __name__ == "__main__":
    Main()
