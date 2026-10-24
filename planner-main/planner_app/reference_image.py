"""Embedded reference-image records, independent of scene objects and visibility."""
import base64
import math
from PySide6 import QtCore, QtGui

imageByteLimit = 40 * 1024 * 1024


def ReadReferenceImage(payload):
    if len(payload) > imageByteLimit:
        raise ValueError("The reference image exceeds 40 MiB.")
    buffer = QtCore.QBuffer()
    buffer.setData(payload)
    buffer.open(QtCore.QIODevice.OpenModeFlag.ReadOnly)
    reader = QtGui.QImageReader(buffer)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.width() <= 0 or size.height() <= 0 or max(size.width(), size.height()) > 32767 or size.width() * size.height() > 100000000:
        raise ValueError("The reference image is invalid or exceeds the supported image dimensions.")
    image = reader.read()
    if image.isNull():
        raise ValueError("Cannot read reference image: " + reader.errorString())
    return image


def ValidateReferenceImage(record):
    if not isinstance(record, dict):
        raise ValueError("Invalid reference image settings.")
    if not isinstance(record.get("path"), str) or "\0" in record["path"]:
        raise ValueError("Invalid reference image path.")
    encoded = record.get("data")
    if not isinstance(encoded, str) or len(encoded) > (imageByteLimit + 2) // 3 * 4:
        raise ValueError("Invalid embedded reference image.")
    try:
        ReadReferenceImage(base64.b64decode(encoded, validate = True))
    except (ValueError, TypeError) as error:
        raise ValueError("Invalid embedded reference image: " + str(error)) from error
    if type(record.get("visible")) is not bool:
        raise ValueError("Invalid reference image visibility.")
    center = record.get("center")
    if not isinstance(center, list) or len(center) != 2:
        raise ValueError("Invalid reference image position.")
    values = center + [record.get(name) for name in ("width", "height", "angle", "opacity")]
    if any(type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e12 for value in values):
        raise ValueError("Invalid reference image dimensions or position.")
    if record["width"] < 1 or record["height"] < 1 or not 0 <= record["opacity"] <= 1:
        raise ValueError("Invalid reference image dimensions or opacity.")
    return {name: list(record[name]) if name == "center" else record[name] for name in
            ("path", "data", "visible", "center", "width", "height", "angle", "opacity")}
