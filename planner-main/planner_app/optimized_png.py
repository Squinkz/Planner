"""UPNG palette encoding through Qt's bundled JavaScript engine."""
import zlib
from PySide6 import QtCore, QtGui
from PySide6.QtQml import QJSEngine, QJSValue

from planner_app.paths import appDirectory


class PngCompressionBridge(QtCore.QObject):
    @QtCore.Slot(QtCore.QByteArray, int, result = QtCore.QByteArray)
    def Deflate(self, data, level):
        return QtCore.QByteArray(zlib.compress(bytes(data), level))


def CreatePngEngine():
    engine = QJSEngine()
    compression = PngCompressionBridge()
    engine.globalObject().setProperty("plannerCompression", engine.newQObject(compression))
    vendorPath = appDirectory / "vendor/upng"
    for filename in ("pako.js", "UPNG.js", "encode.js"):
        result = engine.evaluate((vendorPath / filename).read_text(encoding = "utf-8"), filename)
        if result.isError():
            raise RuntimeError(f"Could not initialize optimized PNG export: {result.toString()}")
    return engine, compression


class OptimizedPngEncoder:
    """One engine per export job; release each image's pixels before the next."""
    def __init__(self):
        self.engine, self.compression = CreatePngEngine()

    def Encode(self, image):
        if image.isNull():
            raise ValueError("Cannot encode an empty image.")
        engine = self.engine
        if engine is None:
            raise RuntimeError("The optimized PNG encoder is closed.")
        if QtCore.QThread.currentThread() != engine.thread():
            raise RuntimeError("Optimized PNG encoding must run on its owning thread.")
        try:
            return EncodeOptimizedPng(image, preparedEngine = engine)
        finally:
            engine.globalObject().setProperty("plannerRgba", QJSValue(QJSValue.SpecialValue.NullValue))
            engine.collectGarbage()

    def Close(self):
        if self.engine is not None and QtCore.QThread.currentThread() != self.engine.thread():
            raise RuntimeError("Optimized PNG cleanup must run on its owning thread.")
        self.engine = None
        self.compression = None


def EncodeOptimizedPng(image, preparedEngine = None):
    if image.isNull():
        raise ValueError("Cannot encode an empty image.")
    # RGBA8888 has byte-ordered channels, independent of the host's endianness.
    rgba = image.convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
    if preparedEngine is None:
        engine, compression = CreatePngEngine()
    else:
        engine = preparedEngine
    result = engine.globalObject().property("BeginPngPixels").call([rgba.sizeInBytes()])
    if result.isError():
        raise RuntimeError(f"Could not initialize optimized PNG pixels: {result.toString()}")
    # Qt maps QByteArray directly to JavaScript ArrayBuffer. Bound temporary
    # buffers and avoid encoding/decoding the raster as base64 strings.
    pixels = rgba.constBits()
    chunkSize = 192 * 1024
    append = engine.globalObject().property("AppendPngPixels")
    for offset in range(0, len(pixels), chunkSize):
        chunk = QtCore.QByteArray(bytes(pixels[offset:offset + chunkSize]))
        result = append.call([engine.toScriptValue(chunk), offset])
        if result.isError():
            raise RuntimeError(f"Could not transfer optimized PNG pixels: {result.toString()}")
        engine.collectGarbage()
    result = engine.globalObject().property("EncodePng").call(
        [rgba.width(), rgba.height(), image.dotsPerMeterX(), image.dotsPerMeterY()])
    if result.isError():
        raise RuntimeError(f"Could not encode optimized PNG: {result.toString()}")
    encoded = result.toVariant()
    if not isinstance(encoded, QtCore.QByteArray):
        raise RuntimeError("The optimized PNG encoder returned invalid binary data.")
    return bytes(encoded)
