"""Export-only title block painting, shared by PNG and SVG."""
import base64
import math
from datetime import date

from PySide6 import QtCore, QtGui, QtSvg
from planner_app.graphics import palette
from planner_app.graphics.text import TextPath
from planner_app.export_settings import TitleBlockLogoMode
from planner_app.paths import assetsDirectory


titleBlockLogoCache = {}
# Match the original compact date/scale column: two 32-unit rows.
titleBlockBottomHeight = 64


def TitleBlockLogo(options):
    mode = TitleBlockLogoMode(options)
    if mode == "None":
        return None, QtCore.QSizeF()
    if mode == "Planner" or not options.get("logo"):
        path = assetsDirectory / "planner.svg"
        key = path.stat().st_mtime_ns
        cached = titleBlockLogoCache.get("Planner")
        if cached is not None and cached[0] == key:
            return cached[1:]
        logo = QtSvg.QSvgRenderer(str(path))
        if not logo.isValid():
            raise ValueError("Could not load Planner's logo.")
        size = logo.viewBoxF().size()
        titleBlockLogoCache["Planner"] = (key, logo, size)
        return logo, size
    key = options["logo"]
    cached = titleBlockLogoCache.get("Custom")
    if cached is not None and cached[0] == key:
        return cached[1:]
    logo = QtGui.QImage.fromData(base64.b64decode(key))
    if logo.isNull():
        raise ValueError("Could not read the title block logo. Choose the logo again.")
    size = QtCore.QSizeF(logo.size())
    titleBlockLogoCache["Custom"] = (key, logo, size)
    return logo, size


def TitleBlockFont(name, heading = False):
    # Base body text is 3.2 mm nominal; sheet numbers are twice that size.
    # Print scales these together with the block for its selected paper size.
    # Headings are 20% smaller than ordinary body text.
    # This is the em size, rather than the smaller capital-letter ink height.
    font = QtGui.QFont("Noto Sans" if heading else "D-DIN Condensed")
    bodySize = 20 if name == "sheetNumber" else 7 if name in ("comments", "date", "scale") else 10
    font.setPixelSize(8 if heading else bodySize)
    font.setBold(heading or name in ("sheetNumber", "projectName", "drawingTitle"))
    font.setHintingPreference(QtGui.QFont.HintingPreference.PreferNoHinting)
    return font


def TitleBlockUnitScale(scale, architecturalScale = None, outputFormat = "png", dpi = None, pageSize = None, position = "Right"):
    if outputFormat == "svg" and architecturalScale is not None:
        unitsPerMillimeter = scale * architecturalScale / 1000
    else:
        unitsPerMillimeter = (300 if dpi is None else dpi) / 25.4
    factor = .32 * unitsPerMillimeter
    if pageSize is not None:
        shortEdge = min(pageSize)
        # A4 -> A3 grows from 40 to 50 mm. Larger sheets grow more gently
        # toward a 60 mm cap at A0; orientation never changes the block scale.
        if shortEdge <= 297:
            sideWidth = 40 + 10 * max(0, (shortEdge - 210) / (297 - 210))
        else:
            sideWidth = 50 + 10 * min(1, (shortEdge - 297) / (841 - 297))
        # Bottom keeps its existing A4 height; both layouts scale uniformly.
        factor *= sideWidth / (40 if position == "Bottom" else 51.2)
    return factor


def DrawTitleBlockText(painter, position, text):
    path, advance, height, ascent = TextPath(text, painter.font().toString(), painter.device().logicalDpiY())
    painter.save()
    try:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.translate(position)
        painter.fillPath(path, painter.pen().brush())
    finally:
        painter.restore()


def RenderTitleBlockBitmap(block, options, scale, architecturalScale = None, pixelSize = None, dpi = None, fitWidth = False, pageSize = None):
    width, height = pixelSize or (math.ceil(block[2]), math.ceil(block[3]))
    image = QtGui.QImage(width, height, QtGui.QImage.Format.Format_ARGB32)
    if image.isNull():
        raise ValueError("Could not allocate the title block bitmap.")
    image.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(image)
    try:
        painter.scale(width / block[2], height / block[3])
        # Use the same local pixel origin in the preview and exported bitmap;
        # translated glyph rasterization can otherwise round coverage differently.
        DrawTitleBlock(painter, (0, 0, block[2], block[3]), options, scale, architecturalScale, "png", dpi, fitWidth, pageSize)
    finally:
        painter.end()
    return image


def TitleBlockTextLines(value, font, width, device = None):
    """Use identical wrapping and newline spacing when measuring and painting."""
    lines = []
    textOptions = QtGui.QTextOption()
    textOptions.setWrapMode(QtGui.QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    textOptions.setUseDesignMetrics(True)
    for paragraph in value.split("\n"):
        text = paragraph or " "
        encoded = text.encode("utf-16-le")
        textLayout = QtGui.QTextLayout(text, font, device)
        textLayout.setTextOption(textOptions)
        textLayout.beginLayout()
        while True:
            line = textLayout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(width)
            # Qt's offsets count UTF-16 units; Python indexes Unicode characters.
            start = line.textStart() * 2
            end = start + line.textLength() * 2
            lines.append((encoded[start:end].decode("utf-16-le"), line.height(), line.ascent()))
        textLayout.endLayout()
    return lines


def TitleBlockGroups(fields, position):
    groups = []
    for field in fields:
        if groups and ((field[0] == "scale" and groups[-1][0][0] == "date") or
                       (position == "Bottom" and field[0] == "sheetNumber" and groups[-1][0][0] == "revision")):
            groups[-1].append(field)
        else:
            groups.append([field])
    return groups


def TitleBlockFields(options, scale, architecturalScale = None, outputFormat = "png", fitWidth = None):
    """Measure the same content and title-block fonts used for preview and export."""
    scaleText = (f"1:{architecturalScale:g}" if architecturalScale is not None else
                 f"{scale:g} {'px/m' if outputFormat == 'png' else 'units/m'}")
    fields = []
    vertical = options.get("position", "Right") == "Right"
    for name, label, value, preferredWidth in (
            ("projectName", "PROJECT NAME", options.get("projectName", ""), 115),
            ("drawingTitle", "SHEET TITLE", options.get("drawingTitle", "Ground Floor Plan"), 110),
            ("address", "PROJECT ADDRESS", options.get("address", ""), 125),
            ("date", "DATE", options.get("date", "").strip() or date.today().isoformat(), 85),
            ("scale", "SCALE", scaleText, 85),
            ("preparedBy", "PREPARED BY", options.get("preparedBy", ""), 110),
            ("comments", "NOTES", options.get("comments", ""), 120),
            ("revision", "REVISION", options.get("revision", ""), 65),
            ("sheetNumber", "SHEET NUMBER", options.get("sheetNumber", "A-101"), 130)):
        minimumLines = {"address": 3, "comments": 4}.get(name, 1)
        metrics = QtGui.QFontMetricsF(TitleBlockFont(name))
        labelWidth = QtGui.QFontMetricsF(TitleBlockFont(name, heading = True)).horizontalAdvance(label) + 12
        if name == "comments":
            preferredWidth = min(200, max(preferredWidth, max(metrics.horizontalAdvance(line) for line in value.split("\n")) + 12))
        columnWidth = math.ceil(max(labelWidth, preferredWidth))
        heights = []
        for index, width in enumerate((68 if name in ("date", "scale") else 148, columnWidth - 12)):
            lines = TitleBlockTextLines(value, TitleBlockFont(name), width)
            textHeight = sum(lineHeight for text, lineHeight, ascent in lines) if value.strip() and (vertical or index == 0) else 0
            padding = {"revision": 18, "sheetNumber": 13}.get(name, 24) if not vertical and index == 1 else 24
            heights.append(math.ceil(padding + max(textHeight, minimumLines * lines[0][1])))
        fields.append((name, label, value, heights[0], columnWidth, heights[1]))
    logo, size = TitleBlockLogo(options)
    if logo is not None:
        aspectRatio = size.width() / size.height()
        rowHeight = math.ceil((min(200, max(24, 148 / aspectRatio + 12)) - 12) * .6 + 12)
        columnHeight = titleBlockBottomHeight
        columnWidth = math.ceil(min(200, max(24, (columnHeight - 12) * aspectRatio + 12)))
        fields.insert(0, ("logo", "", "", rowHeight, columnWidth, 0))
    if fitWidth is not None:
        groups = TitleBlockGroups(fields, options.get("position", "Right"))
        totalWidth = sum(max(field[4] for field in group) for group in groups)
        if totalWidth > fitWidth:
            fitted = []
            for group in groups:
                columnWidth = max(field[4] for field in group) * fitWidth / totalWidth
                if columnWidth <= 16:
                    raise ValueError("The title block is too wide for this page.")
                for name, label, value, rowHeight, originalWidth, columnHeight in group:
                    if name != "logo":
                        headings = TitleBlockTextLines(label, TitleBlockFont(name, heading = True), columnWidth - 12)
                        lines = TitleBlockTextLines(value, TitleBlockFont(name), columnWidth - 12)
                        minimumLines = {"address": 3, "comments": 4}.get(name, 1)
                        textHeight = sum(line[1] for line in lines) if value.strip() and vertical else 0
                        padding = {"revision": 18, "sheetNumber": 13}.get(name, 24) if not vertical else 24
                        columnHeight = math.ceil(padding + (sum(line[1] for line in headings[1:]) if vertical else 0) +
                                                  max(textHeight, minimumLines * lines[0][1]))
                    fitted.append((name, label, value, rowHeight, columnWidth, columnHeight))
            fields = fitted
    return fields


def TitleBlockLayout(width, height, options, scale = 100, architecturalScale = None, outputFormat = "png", dpi = None, fitWidth = False, pageSize = None):
    if not options or not options.get("enabled", False):
        return width, height, None
    factor = TitleBlockUnitScale(scale, architecturalScale, outputFormat, dpi, pageSize, options.get("position", "Right"))
    fields = TitleBlockFields(options, scale, architecturalScale, outputFormat, width / factor if fitWidth else None)
    groups = TitleBlockGroups(fields, options.get("position", "Right"))
    if options.get("position", "Right") == "Right":
        height = max(height, math.ceil(sum(max(field[3] for field in group) for group in groups) * factor))
        blockWidth = math.ceil(160 * factor)
        return width + blockWidth, height, (width, 0, blockWidth, height)
    width = max(width, math.ceil(round(sum(max(field[4] for field in group) for group in groups) * factor, 8)))
    blockHeight = math.ceil(titleBlockBottomHeight * factor)
    return width, height + blockHeight, (0, height, width, blockHeight)


def TitleBlockCells(block, options, scale, architecturalScale = None, outputFormat = "png", dpi = None, fitWidth = False, pageSize = None):
    factor = TitleBlockUnitScale(scale, architecturalScale, outputFormat, dpi, pageSize, options.get("position", "Right"))
    rect = QtCore.QRectF(*(value / factor for value in block))
    vertical = options.get("position", "Right") == "Right"
    fields = TitleBlockFields(options, scale, architecturalScale, outputFormat, rect.width() if fitWidth else None)
    groups = TitleBlockGroups(fields, options.get("position", "Right"))
    available = rect.height() if vertical else rect.width()
    extra = max(0, available - sum(max(field[3 if vertical else 4] for field in group) for group in groups))
    cells = []
    offset = rect.top() if vertical else rect.left()
    for group in groups:
        name = group[0][0]
        extent = max(field[3 if vertical else 4] for field in group) + (extra if name == "comments" else 0)
        top = rect.top()
        groupHeight = sum(field[5] for field in group)
        for index, (name, label, value, rowHeight, columnWidth, columnHeight) in enumerate(group):
            cellHeight = (columnHeight * rect.height() / groupHeight if groupHeight > rect.height() else
                          columnHeight + (rect.height() - groupHeight if index == len(group) - 1 else 0))
            if group[0][0] == "date":
                cellHeight = rect.height() / len(group)
            cell = (QtCore.QRectF(rect.left() + index * rect.width() / len(group), offset, rect.width() / len(group), extent) if vertical else
                    QtCore.QRectF(offset, top, extent, cellHeight))
            cells.append((name, label, value, QtCore.QRectF(cell.x() * factor, cell.y() * factor, cell.width() * factor, cell.height() * factor)))
            top += cellHeight
        offset += extent
    return cells


def DrawTitleBlock(painter, block, options, scale, architecturalScale = None, outputFormat = "png", dpi = None, fitWidth = False, pageSize = None):
    factor = TitleBlockUnitScale(scale, architecturalScale, outputFormat, dpi, pageSize, options.get("position", "Right"))
    textColor = QtGui.QColor(palette.themeColors["objectOutline"])
    canvasColor = QtGui.QColor(palette.themeColors["canvas"])
    # Soften headings toward the canvas colour for both light and dark themes.
    headingColor = QtGui.QColor.fromRgbF(
        textColor.redF() * .8 + canvasColor.redF() * .2,
        textColor.greenF() * .8 + canvasColor.greenF() * .2,
        textColor.blueF() * .8 + canvasColor.blueF() * .2,
        textColor.alphaF())
    rect = QtCore.QRectF(*(value / factor for value in block))
    vertical = options.get("position", "Right") == "Right"
    logo, logoSize = TitleBlockLogo(options)
    # Fitting must not mutate the cached intrinsic dimensions: accumulated
    # rounding can change subsequent column widths and preview/export pixels.
    logoSize = QtCore.QSizeF(logoSize)
    painter.save()
    try:
        painter.scale(factor, factor)
        painter.setClipRect(rect, QtCore.Qt.ClipOperation.IntersectClip)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.fillRect(rect, QtGui.QColor(palette.themeColors["canvas"]))
        for name, label, value, cell in TitleBlockCells(block, options, scale, architecturalScale, outputFormat, dpi, fitWidth, pageSize):
            cell = QtCore.QRectF(cell.x() / factor, cell.y() / factor, cell.width() / factor, cell.height() / factor)
            painter.save()
            painter.setClipRect(cell.adjusted(2, 2, -2, -2), QtCore.Qt.ClipOperation.IntersectClip)
            if name == "logo":
                if logo is not None:
                    logoRect = cell.adjusted(6, 6, -6, -6)
                    logoSize.scale(logoRect.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)
                    target = QtCore.QRectF(QtCore.QPointF(), logoSize)
                    target.moveCenter(logoRect.center())
                    painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
                    if isinstance(logo, QtSvg.QSvgRenderer):
                        logo.render(painter, target)
                    else:
                        painter.drawImage(target, logo)
            elif name != "spacer":
                painter.setPen(headingColor)
                font = TitleBlockFont(name, heading = True)
                painter.setFont(font)
                headings = TitleBlockTextLines(label, font, cell.width() - 12, painter.device())
                if not vertical:
                    heading = QtGui.QFontMetricsF(font).elidedText(label, QtCore.Qt.TextElideMode.ElideRight, cell.width() - 12)
                    headings = [(heading, headings[0][1], headings[0][2])]
                compact = not vertical and name in ("revision", "sheetNumber")
                headingY = cell.top() + (8 if compact and name == "sheetNumber" else 12)
                for text, lineHeight, ascent in headings:
                    DrawTitleBlockText(painter, QtCore.QPointF(cell.left() + 6, headingY), text)
                    headingY += lineHeight
                painter.setPen(textColor)
                font = TitleBlockFont(name)
                painter.setFont(font)
                lines = TitleBlockTextLines(value, font, cell.width() - 12, painter.device())
                textY = cell.top() + ({"revision": 14, "sheetNumber": 9}[name] if compact else 18) + sum(line[1] for line in headings[1:])
                bottomPadding = 4 if compact else 6
                if not vertical:
                    availableHeight = max(0, cell.bottom() - bottomPadding - textY)
                    visible = []
                    for line in lines:
                        if line[1] > availableHeight + .001:
                            break
                        visible.append(line)
                        availableHeight -= line[1]
                    if visible and len(visible) < len(lines):
                        text, lineHeight, ascent = visible[-1]
                        text = QtGui.QFontMetricsF(font).elidedText(text.rstrip() + "…", QtCore.Qt.TextElideMode.ElideRight, cell.width() - 12)
                        visible[-1] = (text, lineHeight, ascent)
                    lines = visible
                if name == "sheetNumber" and not vertical:
                    textY = cell.bottom() - bottomPadding - sum(lineHeight for text, lineHeight, ascent in lines)
                # Paint wrapped lines individually so the SVG export can outline
                # text through its existing painter without losing line breaks.
                for text, lineHeight, ascent in lines:
                    textX = cell.left() + 6
                    if name in ("sheetNumber", "date", "scale", "revision"):
                        path, advance, height, textAscent = TextPath(text, font.toString(), painter.device().logicalDpiY())
                        textX = cell.right() - 6 - advance
                    DrawTitleBlockText(painter, QtCore.QPointF(textX, textY + ascent), text)
                    textY += lineHeight
            painter.restore()
            # Base design units are 0.32 mm; rules scale with the block at every PPI.
            painter.setPen(QtGui.QPen(QtGui.QColor(palette.themeColors["rulerMinorTick"]), .18 / .32))
            if cell.bottom() < rect.bottom() - .1:
                painter.drawLine(cell.bottomLeft(), cell.bottomRight())
            if cell.right() < rect.right() - .1:
                painter.drawLine(cell.topRight(), cell.bottomRight())
        borderPen = QtGui.QPen(QtGui.QColor(palette.themeColors["rulerMajorTick"]), .35 / .32)
        borderPen.setJoinStyle(QtCore.Qt.PenJoinStyle.MiterJoin)
        painter.setPen(borderPen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        inset = borderPen.widthF() / 2
        painter.drawRect(rect.adjusted(inset, inset, -inset, -inset))
    finally:
        painter.restore()
