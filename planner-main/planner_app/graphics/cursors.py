"""Replaceable bitmap cursors for canvas actions."""
from PySide6 import QtGui
from planner_app.paths import assetsDirectory

rotationCursorCache = None


def RotationCursor():
    global rotationCursorCache
    if rotationCursorCache is None:
        pixmap = QtGui.QPixmap(str(assetsDirectory / "cursors" / "rotate.png"))
        rotationCursorCache = QtGui.QCursor(pixmap, 16, 16)
    return rotationCursorCache
