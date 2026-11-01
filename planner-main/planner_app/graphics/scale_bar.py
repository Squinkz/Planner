"""Export-only scale bars in shared preview/file drawing coordinates."""
import math
from PySide6 import QtCore, QtGui
from planner_app.graphics.palette import themeColors
from planner_app.graphics.text import TextPath
from planner_app.graphics.measurement_text import MeasurementFontStyle
from planner_app.measurement_units import FormatLength, MetricUnit
from planner_app.geometry.snapping import GridIntervals
from planner_app.units import imperialModes
from planner_app.export_settings import scaleBarDefaultDivisions, scaleBarDefaultStyle, measurementDefaultTextSize, measurementTextSizes


def ScaleBarLayout(plot, options, scale, unitsMode, font, bounds = None, gridOrigin = (0, 0), measurementTextSize = measurementDefaultTextSize):
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("Scale bar requires a positive export scale.")
    # Like the title block, every mode uses a 300-PPI design space. Physical
    # exports scale the painter for output PPI; Digital uses this baseline as-is.
    factor = 300 / 25.4
    if measurementTextSize == 0:
        measurementTextSize = measurementTextSizes["Small"]
    targetWidth = 100 * factor
    divisionMode = options.get("divisionMode", scaleBarDefaultDivisions)
    unit, unitName = MetricUnit(unitsMode)
    targetDistance = targetWidth * 1000 / scale / unit
    if unitName == "ft" and targetDistance < 10:
        # Short imperial bars use inch increments instead of decimal feet.
        unit = 25.4
        targetDistance = targetWidth * 1000 / scale / unit
    step = 5 * 10.0 ** math.floor(math.log10(targetDistance / 5))
    candidates = sorted((step * index for index in range(1, 11)),
                        key = lambda value: (round(abs(value / targetDistance - 1), 12), value))
    margin, padding = 5 * factor, 1.5 * factor
    height, gap = 1.5 * factor, factor
    if options.get("style") == "Checker":
        height *= 2
    labelPadding = .3 * factor
    font = QtGui.QFont(font)
    font.setFamily("D-DIN Condensed")
    font.setPixelSize(QtGui.QFontInfo(font).pixelSize())
    fontKey, unused = MeasurementFontStyle(font.toString(), 96, measurementTextSize * factor, "D-DIN Condensed")
    font.fromString(fontKey)
    font.setHintingPreference(QtGui.QFont.HintingPreference.PreferNoHinting)
    metrics = QtGui.QFontMetricsF(font)
    chosen = None
    for candidate in candidates:
        distance = candidate * unit
        width = distance * scale / 1000
        tickDecade = math.floor(math.log10(candidate))
        ticks = [value * 10.0 ** exponent for exponent in (tickDecade - 2, tickDecade - 1, tickDecade)
                 for value in (1, 2, 5) if value * 10.0 ** exponent < candidate * (1 - 1e-12)]
        marks = (0, *ticks[-3:], candidate)
        if divisionMode != "Progressive":
            # Aim for five equal major divisions, using clean increments that
            # divide the total exactly. Other totals can need fewer or more.
            majorSteps = [value for value in ticks if 2 <= round(candidate / value) <= 10
                          and math.isclose(candidate / value, round(candidate / value), rel_tol = 1e-10)]
            major = min(majorSteps, key = lambda value: (abs(candidate / value - 5), -value))
            marks = tuple(index * major for index in range(round(candidate / major) + 1))
            if divisionMode == "Subdivided":
                minor = next(value for value in reversed(ticks) if value < major * (1 - 1e-12)
                             and math.isclose(major / value, round(major / value), rel_tol = 1e-10))
                marks = (0, *(index * minor for index in range(1, round(major / minor))), *marks[1:])
        fractions = tuple(mark / candidate for mark in marks)
        distances = tuple(mark * unit for mark in marks)
        adaptive = "m" if distance >= 1000 else "cm" if distance >= 10 else "mm"
        labels = [FormatLength(value, unitsMode, adaptive = adaptive, decimals = 6,
                               includeUnit = index == len(distances) - 1, preserveDecimals = True)
                  for index, value in enumerate(distances)]
        leading = metrics.horizontalAdvance(labels[0]) / 2
        trailing = metrics.horizontalAdvance(labels[-1]) / 2
        geometry = distance, width, labels, leading, trailing, fractions, distances
        if chosen is None:
            chosen = geometry
        # Prefer the closest clean total that fits a narrow page's drawing area.
        if width + leading + trailing + 2 * padding + 2 * margin <= plot.width() + .01:
            chosen = geometry
            break
    distance, width, labels, leading, trailing, fractions, distances = chosen
    last = len(labels) - 1
    visibleLabels = [0, last]
    labelSpacing = 4 + 2 * labelPadding
    if leading + trailing + labelSpacing <= width:
        previousRight = leading
        finalLeft = width - trailing
        for index in range(1, last):
            halfWidth = metrics.horizontalAdvance(labels[index]) / 2
            center = width * fractions[index]
            if center - halfWidth >= previousRight + labelSpacing and center + halfWidth <= finalLeft - labelSpacing:
                visibleLabels.insert(-1, index)
                previousRight = center + halfWidth
    else:
        visibleLabels = [last]
        leading = max(0, trailing - width)
    size = QtCore.QSizeF(width + leading + trailing + 2 * padding, metrics.height() + gap + height + 2 * padding)
    position = options.get("position", "Bottom left")
    left = plot.right() - margin - size.width() if position.endswith("right") else plot.left() + margin
    top = plot.top() + margin if position.startswith("Top") else plot.bottom() - margin - size.height()
    rect = QtCore.QRectF(QtCore.QPointF(left, top), size)
    bar = QtCore.QRectF(left + padding + leading, top + padding + metrics.height() + gap, width, height)
    if bounds is not None:
        # Use the export grid, independent of viewport zoom or raster density.
        # Move horizontally inward only when the complete decoration still fits
        # inside its existing inset, including the end labels. Keep height fixed.
        pixelsPerMillimeter = scale / 1000
        spacing = GridIntervals(pixelsPerMillimeter, unitsMode in imperialModes)[0] * pixelsPerMillimeter
        origin = plot.left() + (gridOrigin[0] - bounds[0]) * pixelsPerMillimeter
        allowed = plot.adjusted(margin - .01, margin - .01, -margin + .01, -margin + .01)
        index = (math.floor((bar.left() - origin) / spacing + 1e-9) if position.endswith("right")
                 else math.ceil((bar.left() - origin) / spacing - 1e-9))
        offset = QtCore.QPointF(origin + index * spacing - bar.left(), 0)
        if allowed.contains(rect.translated(offset)):
            rect.translate(offset)
            bar.translate(offset)
    return dict(rect = rect, bar = bar, labels = labels, visibleLabels = visibleLabels, font = font, padding = padding,
                minimum = QtCore.QSizeF(size.width() + 2 * margin, size.height() + 2 * margin), distance = distance,
                fractions = fractions, distances = distances, labelPadding = labelPadding)


def DrawScaleBar(painter, plot, options, scale, unitsMode, bounds = None, gridOrigin = (0, 0), measurementTextSize = measurementDefaultTextSize):
    if not options.get("enabled", False):
        return
    layout = ScaleBarLayout(plot, options, scale, unitsMode, painter.font(), bounds, gridOrigin, measurementTextSize)
    if layout["minimum"].width() > plot.width() + .01 or layout["minimum"].height() > plot.height() + .01:
        raise ValueError("The scale bar does not fit the drawing area. Use a larger drawing area.")
    bar = layout["bar"]
    ink, background = QtGui.QColor(themeColors["objectOutline"]), QtGui.QColor(themeColors["canvas"])
    ink.setAlpha(255)
    background.setAlpha(255)
    fractions = layout["fractions"]
    painter.save()
    try:
        painter.setClipRect(plot, QtCore.Qt.ClipOperation.IntersectClip)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setOpacity(1)
        painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setPen(QtGui.QPen(ink, .25 * 300 / 25.4))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        style = options.get("style", scaleBarDefaultStyle)
        if style == "Stepped":
            path = QtGui.QPainterPath(QtCore.QPointF(bar.left(), bar.top()))
            for index, (start, end) in enumerate(zip(fractions, fractions[1:])):
                y = bar.bottom() if index % 2 == 0 else bar.top()
                path.lineTo(bar.left() + start * bar.width(), y)
                path.lineTo(bar.left() + end * bar.width(), y)
            path.lineTo(bar.right(), bar.top() if y == bar.bottom() else bar.bottom())
            pen = painter.pen()
            pen.setJoinStyle(QtCore.Qt.PenJoinStyle.MiterJoin)
            pen.setCapStyle(QtCore.Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            painter.drawPath(path)
        else:
            rows = 2 if style == "Checker" else 1
            for row in range(rows):
                for index, (start, end) in enumerate(zip(fractions, fractions[1:])):
                    painter.fillRect(QtCore.QRectF(bar.left() + start * bar.width(), bar.top() + row * bar.height() / rows,
                                                  (end - start) * bar.width(), bar.height() / rows),
                                     ink if (index + row) % 2 == 0 else background)
            painter.drawRect(bar)
            if rows == 2:
                painter.drawLine(QtCore.QPointF(bar.left(), bar.center().y()), QtCore.QPointF(bar.right(), bar.center().y()))
        painter.setFont(layout["font"])
        metrics = QtGui.QFontMetricsF(layout["font"])
        for index in layout["visibleLabels"]:
            text = layout["labels"][index]
            path, advance, height, ascent = TextPath(text, layout["font"].toString(), painter.device().logicalDpiY())
            painter.save()
            painter.translate(bar.left() + fractions[index] * bar.width() - advance / 2,
                              layout["rect"].top() + layout["padding"] + metrics.ascent())
            labelPadding = layout["labelPadding"]
            painter.fillRect(path.boundingRect().adjusted(-labelPadding, -labelPadding, labelPadding, labelPadding), background)
            painter.fillPath(path, ink)
            painter.restore()
    finally:
        painter.restore()
