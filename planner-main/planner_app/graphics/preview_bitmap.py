"""Rasterize export decorations on the export pixel grid, including low-memory draws."""
import math
from PySide6 import QtCore, QtGui
from .text import PathTextPainter


def PictureBitmap(picture, rect, density):
    left, top = (math.floor(round(value * density, 8)) for value in (rect.left(), rect.top()))
    right, bottom = (math.ceil(round(value * density, 8)) for value in (rect.right(), rect.bottom()))
    image = QtGui.QImage(max(1, right - left), max(1, bottom - top), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    if image.isNull():
        raise ValueError("Could not allocate the export decoration preview.")
    image.fill(QtCore.Qt.GlobalColor.transparent)
    capture = QtCore.QRectF(left / density, top / density, image.width() / density, image.height() / density)
    with PathTextPainter(image) as painter:
        painter.scale(density, density)
        painter.translate(-capture.left(), -capture.top())
        painter.drawPicture(QtCore.QPointF(), picture)
    return capture, image


def DrawPictureTiles(painter, picture, rect, density):
    # Cache refusal must not turn a raster preview into vector artwork. Keep
    # temporary storage below 300 KiB and visit only the visible native pixels.
    visible = rect.intersected(painter.clipBoundingRect()) if painter.hasClipping() else rect
    if visible.isEmpty():
        return
    left, top = (math.floor(round(value * density, 8)) for value in (visible.left(), visible.top()))
    right, bottom = (math.ceil(round(value * density, 8)) for value in (visible.right(), visible.bottom()))
    painter.save()
    try:
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
        for y in range(top, bottom, 256):
            for x in range(left, right, 256):
                tile = QtCore.QRectF(x / density, y / density, min(256, right - x) / density, min(256, bottom - y) / density)
                # One native pixel of neighbours keeps filtered tile edges
                # identical to a single bitmap during fractional pan and zoom.
                capture, image = PictureBitmap(picture, tile.adjusted(-1 / density, -1 / density, 1 / density, 1 / density), density)
                painter.save()
                painter.setClipRect(tile.intersected(rect), QtCore.Qt.ClipOperation.IntersectClip)
                painter.drawImage(capture, image)
                painter.restore()
    finally:
        painter.restore()
