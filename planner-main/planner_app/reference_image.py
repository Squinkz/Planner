"""Embedded reference-image records, independent of scene objects and visibility."""
import base64
from PySide6 import QtCore, QtGui

from .reference_state import ValidateReferenceState, imageByteLimit


def ReadReferenceImage(payload):
    if len(payload) > imageByteLimit:
        raise ValueError("The reference image exceeds 40 MiB.")
    buffer = QtCore.QBuffer()
    buffer.setData(payload)
    buffer.open(QtCore.QIODevice.OpenModeFlag.ReadOnly)
    reader = QtGui.QImageReader(buffer)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.width() <= 0 or size.height() <= 0:
        raise ValueError("Cannot read the reference image's dimensions. The file may be damaged or use an unsupported format.\n\n" + reader.errorString())
    if max(size.width(), size.height()) > 32767:
        raise ValueError(f"The reference image is {size.width():,} × {size.height():,} pixels. "
                         "The maximum width or height is 32,767 pixels.\n\nResize the image before loading it.")
    if size.width() * size.height() > 100000000:
        raise ValueError(f"The reference image is {size.width():,} × {size.height():,} pixels "
                         f"({size.width() * size.height() / 1000000:,.1f} million pixels). "
                         "The maximum is 100 million pixels.\n\nResize the image before loading it.")
    image = reader.read()
    if image.isNull():
        error = reader.errorString()
        allocationLimit = reader.allocationLimit()
        if "allocat" in error.lower() or (allocationLimit > 0 and size.width() * size.height() * 4 > allocationLimit * 1024 * 1024):
            limitText = f" The image decoder's memory limit is {allocationLimit:,} MiB." if allocationLimit > 0 else ""
            raise ValueError(f"The reference image is {size.width():,} × {size.height():,} pixels "
                             "and could not be loaded into memory." + limitText +
                             "\n\nResize the image before loading it. A small file on disk can still require substantial memory when opened.")
        raise ValueError("Cannot read reference image: " + error)
    return image


def ValidateReferenceImage(record, validatedImages = None):
    candidate = ValidateReferenceState(record)
    encoded = candidate["data"]
    try:
        if validatedImages is None or encoded not in validatedImages:
            ReadReferenceImage(base64.b64decode(encoded, validate = True))
            if validatedImages is not None:
                validatedImages.add(encoded)
    except (ValueError, TypeError) as error:
        raise ValueError("Invalid embedded reference image: " + str(error)) from error
    return candidate
