"""Shaped glyph outlines shared by canvas, raster exports and SVG exports."""
from functools import lru_cache
from PySide6 import QtCore, QtGui
from .fonts import fontSources


@lru_cache(maxsize = 64)
def OutlineFont(family, weight, pixelSize):
    candidates = [QtGui.QRawFont(str(path), pixelSize, QtGui.QFont.HintingPreference.PreferNoHinting)
                  for path in fontSources.get(family, ())]
    candidates = [font for font in candidates if font.isValid()]
    return min(candidates, key = lambda font: abs(font.weight() - weight)) if candidates else None


@lru_cache(maxsize = 256)
def TextPath(text, fontKey, dpi, width = 0, wrap = False):
    font = QtGui.QFont()
    font.fromString(fontKey)
    if font.pointSizeF() > 0:
        font.setPixelSize(max(1, round(font.pointSizeF() * dpi / 72)))
    layout = QtGui.QTextLayout(text.replace("\n", "\u2028"), font)
    options = QtGui.QTextOption()
    options.setUseDesignMetrics(True)
    options.setWrapMode(QtGui.QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere if wrap else QtGui.QTextOption.WrapMode.NoWrap)
    layout.setTextOption(options)
    height = advance = ascent = 0.0
    layout.beginLayout()
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(width if width > 0 else 1e9)
        line.setPosition(QtCore.QPointF(0, height))
        if height == 0:
            ascent = line.ascent()
        height += line.height()
        advance = max(advance, line.horizontalAdvance())
    layout.endLayout()
    path = QtGui.QPainterPath()
    path.setFillRule(QtCore.Qt.FillRule.WindingFill)
    outlineFont = OutlineFont(font.family(), int(font.weight()), font.pixelSize())
    selectedFont = QtGui.QRawFont.fromFont(font)
    for run in layout.glyphRuns():
        rawFont = run.rawFont()
        if not rawFont.isValid():
            continue
        if outlineFont is not None and rawFont == selectedFont:
            rawFont = outlineFont
        for glyph, position in zip(run.glyphIndexes(), run.positions()):
            glyphPath = rawFont.pathForGlyph(glyph)
            glyphPath.translate(position.x(), position.y() - ascent)
            path.addPath(glyphPath)
    return path, advance, height, ascent


class PathTextPainter(QtGui.QPainter):
    def drawText(self, *args):
        dpi = self.device().logicalDpiY()
        if len(args) == 2 and isinstance(args[0], (QtCore.QPointF, QtCore.QPoint)):
            position, text = args
            path, advance, height, ascent = TextPath(text, self.font().toString(), dpi)
        elif len(args) == 3 and isinstance(args[0], (QtCore.QRect, QtCore.QRectF)):
            rect, flags, text = args
            wrap = bool(int(flags) & int(QtCore.Qt.TextFlag.TextWordWrap))
            path, advance, height, ascent = TextPath(text, self.font().toString(), dpi, rect.width(), wrap)
            x, y = rect.left(), rect.top() + ascent
            if flags & QtCore.Qt.AlignmentFlag.AlignHCenter:
                x += (rect.width() - advance) / 2
            elif flags & QtCore.Qt.AlignmentFlag.AlignRight:
                x += rect.width() - advance
            if flags & QtCore.Qt.AlignmentFlag.AlignVCenter:
                y += (rect.height() - height) / 2
            elif flags & QtCore.Qt.AlignmentFlag.AlignBottom:
                y += rect.height() - height
            position = QtCore.QPointF(x, y)
        else:
            raise TypeError("Unsupported canvas text drawing arguments.")
        self.save()
        try:
            self.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            self.translate(position)
            self.fillPath(path, self.pen().brush())
        finally:
            self.restore()
