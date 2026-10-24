"""UPNG palette encoding through Qt's bundled JavaScript engine."""
import base64

from PySide6 import QtGui
from PySide6.QtQml import QJSEngine

from planner_app.paths import appDirectory


def EncodeOptimizedPng(image):
    if image.isNull():
        raise ValueError("Cannot encode an empty image.")
    # RGBA8888 has byte-ordered channels, independent of the host's endianness.
    rgba = image.convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
    pixels = base64.b64encode(rgba.constBits()).decode("ascii")
    engine = QJSEngine()
    vendorPath = appDirectory / "vendor/upng"
    for filename in ("pako.js", "UPNG.js", "encode.js"):
        result = engine.evaluate((vendorPath / filename).read_text(encoding = "utf-8"), filename)
        if result.isError():
            raise RuntimeError(f"Could not initialize optimized PNG export: {result.toString()}")
    result = engine.globalObject().property("EncodePng").call(
        [pixels, rgba.width(), rgba.height(), image.dotsPerMeterX(), image.dotsPerMeterY()])
    if result.isError():
        raise RuntimeError(f"Could not encode optimized PNG: {result.toString()}")
    return base64.b64decode(result.toString(), validate = True)
