"""Cached glyph outlines keep imperial fractions independent of SVG viewer fonts."""
import re
from functools import lru_cache
from PySide6 import QtCore, QtGui
from planner_app.graphics.fonts import fontFamily
from planner_app.graphics.text import OutlineFont


def ShapedTextPath(text, font):
    layout = QtGui.QTextLayout(text, font)
    layout.beginLayout()
    line = layout.createLine()
    line.setLineWidth(1e9)
    layout.endLayout()
    path = QtGui.QPainterPath()
    path.setFillRule(QtCore.Qt.FillRule.WindingFill)
    glyphs = []
    selectedFont = QtGui.QRawFont.fromFont(font)
    for run in layout.glyphRuns():
        rawFont = run.rawFont()
        # Whitespace-only runs may carry no font; retain their layout advance
        # without asking an invalid native font for glyph metadata or outlines.
        if not rawFont.isValid():
            continue
        outlineFont = OutlineFont(font.family(), int(font.weight()), font.pixelSize())
        if outlineFont is not None and rawFont == selectedFont:
            pathFont = outlineFont
        else:
            pathFont = rawFont
        for glyph, position in zip(run.glyphIndexes(), run.positions()):
            glyphs.append((rawFont == selectedFont, glyph))
            path.addPath(QtGui.QTransform().translate(position.x(), position.y() - line.ascent()).map(pathFont.pathForGlyph(glyph)))
    return path, line.horizontalAdvance(), glyphs


@lru_cache(maxsize = 256)
def FractionTextPath(text, fontKey, dpi):
    font = QtGui.QFont()
    font.fromString(fontKey)
    if font.pointSizeF() > 0:
        font.setPixelSize(max(1, round(font.pointSizeF() * dpi / 72)))
    fractionFont = QtGui.QFont(font)
    fractionFont.setPixelSize(max(1, round(font.pixelSize() * 1.2)))
    fractionFont.setFeature(QtGui.QFont.Tag.fromString("frac"), 1)
    path, advance, glyphs = ShapedTextPath(text, fractionFont)
    rawFont = QtGui.QRawFont.fromFont(fractionFont)
    ordinaryGlyphs = rawFont.glyphIndexesForString(text)
    native = bool(glyphs) and all(selected and glyph != 0 for selected, glyph in glyphs)
    # A feature tag alone is insufficient: some fonts only shape a few common
    # fractions. Require a whole-token ligature or substituted numerator/denominator digits.
    native = native and (len(glyphs) == 1 or len(glyphs) == len(text) and
        all(glyphs[index][1] != ordinaryGlyphs[index] for index, character in enumerate(text) if character.isdigit()))
    if native:
        return path, advance, "native"
    numerator, denominator = text.split("/")
    rawFont = QtGui.QRawFont.fromFont(font)
    slash = "\u2044" if rawFont.supportsCharacter(0x2044) else "/"
    if all(rawFont.supportsCharacter(ord(character)) for character in numerator + denominator + slash):
        digitFont = QtGui.QFont(font)
        digitFont.setPixelSize(max(1, round(font.pixelSize() * .6)))
        digitFont.setFeature(QtGui.QFont.Tag.fromString("frac"), 0)
        numeratorPath, numeratorAdvance, unused = ShapedTextPath(numerator, digitFont)
        denominatorPath, denominatorAdvance, unused = ShapedTextPath(denominator, digitFont)
        slashFont = QtGui.QFont(font)
        slashFont.setFeature(QtGui.QFont.Tag.fromString("frac"), 0)
        slashPath, slashAdvance, unused = ShapedTextPath(slash, slashFont)
        slashX = max(0, numeratorAdvance - slashAdvance * .15)
        denominatorX = slashX + slashAdvance * .8
        path = QtGui.QPainterPath()
        path.setFillRule(QtCore.Qt.FillRule.WindingFill)
        path.addPath(QtGui.QTransform().translate(0, -QtGui.QFontMetricsF(font).capHeight() * .42).map(numeratorPath))
        path.addPath(QtGui.QTransform().translate(slashX, 0).map(slashPath))
        path.addPath(QtGui.QTransform().translate(denominatorX, 0).map(denominatorPath))
        return path, denominatorX + denominatorAdvance, "built"
    fractionFont.setFamily(fontFamily)
    path, advance, unused = ShapedTextPath(text, fractionFont)
    return path, advance, "fallback"


@lru_cache(maxsize = 256)
def MeasurementTextPath(text, fontKey, dpi):
    font = QtGui.QFont()
    font.fromString(fontKey)
    if font.pointSizeF() > 0:
        font.setPixelSize(max(1, round(font.pointSizeF() * dpi / 72)))
    path = QtGui.QPainterPath()
    path.setFillRule(QtCore.Qt.FillRule.WindingFill)
    x = 0.0
    for piece in re.split(r"(\d+/\d+)", text):
        if not piece:
            continue
        if re.fullmatch(r"\d+/\d+", piece):
            piecePath, advance, unused = FractionTextPath(piece, fontKey, dpi)
        else:
            piecePath, advance, unused = ShapedTextPath(piece, font)
        path.addPath(QtGui.QTransform().translate(x, 0).map(piecePath))
        x += advance
    return path
