"""Canvas stroke defaults and zero-width strokes that render no line."""
from PySide6 import QtCore, QtGui
from planner_app.preferences import lineworkDefaults

defaultLineWidths = {key: lineworkDefaults["baseWidth"] * value
                     for key, value in lineworkDefaults.items() if key != "baseWidth"}


def LinePen(color, width, *args):
    # QPen width zero means a one-pixel cosmetic stroke, rather than no ink.
    if width == 0:
        return QtGui.QPen(QtCore.Qt.PenStyle.NoPen)
    return QtGui.QPen(QtGui.QColor(color), width, *args)
