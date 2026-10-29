"""Export-only title block painting, shared by PNG and SVG."""
import base64
import math
from datetime import date

from PySide6 import QtCore, QtGui, QtSvg
from planner_app.graphics import palette
from planner_app.graphics.text import TextPath
from planner_app.export_settings import TitleBlockLogoMode
from planner_app.paths import assetsDirectory


def TitleBlockLogo(options):
    mode = TitleBlockLogoMode(options)
    if mode == "None":
        return None, QtCore.QSizeF()
    if mode == "Planner" or not options.get("logo"):
        logo = QtSvg.QSvgRenderer(str(assetsDirectory / "planner.svg"))
        if not logo.isValid():
            raise ValueError("Could not load Planner's logo.")
        return logo, logo.viewBoxF().size()
    logo = QtGui.QImage.fromData(base64.b64decode(options["logo"]))
    if logo.isNull():
        raise ValueError("Could not read the title block logo. Choose the logo again.")
    return logo, QtCore.QSizeF(logo.size())


def TitleBlockFont(name, heading = False):
    # Body text is 3.2 mm nominal; headings are 20% smaller.
    # This is the em size, rather than the smaller capital-letter ink height.
    font = QtGui.QFont("Noto Sans" if heading else "D-DIN Condensed")
    font.setPixelSize(8 if heading else 7 if name in ("comments", "date", "scale") else 10)
    font.setBold(heading or name in ("sheetNumber", "projectName", "drawingTitle"))
    font.setHintingPreference(QtGui.QFont.HintingPreference.PreferNoHinting)
    return font


def TitleBlockUnitScale(scale, architecturalScale = None, outputFormat = "png", dpi = None):
    if outputFormat == "svg" and architecturalScale is not None:
        unitsPerMillimeter = scale * architecturalScale / 1000
    else:
        unitsPerMillimeter = (300 if dpi is None else dpi) / 25.4
    return .32 * unitsPerMillimeter


def DrawTitleBlockText(painter, position, text):
    path, advance, height, ascent = TextPath(text, painter.font().toString(), painter.device().logicalDpiY())
    painter.save()
    try:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.translate(position)
        painter.fillPath(path, painter.pen().brush())
    finally:
        painter.restore()


def RenderTitleBlockBitmap(block, options, scale, architecturalScale = None, pixelSize = None, dpi = None):
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
        DrawTitleBlock(painter, (0, 0, block[2], block[3]), options, scale, architecturalScale, "png", dpi)
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


def TitleBlockGroups(fields):
    groups = []
    for field in fields:
        if field[0] == "scale" and groups and groups[-1][0][0] == "date":
            groups[-1].append(field)
        else:
            groups.append([field])
    return groups


def TitleBlockFields(options, scale, architecturalScale = None, outputFormat = "png"):
    """Measure the same content and title-block fonts used for preview and export."""
    scaleText = (f"1:{architecturalScale:g}" if architecturalScale is not None else
                 f"{scale:g} {'px/m' if outputFormat == 'png' else 'units/m'}")
    fields = []
    for name, label, value, preferredWidth in (
            ("projectName", "PROJECT NAME", options.get("projectName", ""), 115),
            ("drawingTitle", "DRAWING TITLE", options.get("drawingTitle", ""), 110),
            ("address", "PROJECT ADDRESS", options.get("address", ""), 125),
            ("date", "DATE", options.get("date", "").strip() or date.today().isoformat(), 85),
            ("scale", "SCALE", scaleText, 85),
            ("preparedBy", "PREPARED BY", options.get("preparedBy", ""), 110),
            ("revision", "REVISION", options.get("revision", ""), 65),
            ("comments", "COMMENTS", options.get("comments", ""), 120),
            ("sheetNumber", "SHEET NUMBER", options.get("sheetNumber", "0001"), 130)):
        if not value.strip() and (name == "revision" or
                                  (name == "comments" and options.get("position", "Right") != "Right")):
            continue
        metrics = QtGui.QFontMetricsF(TitleBlockFont(name))
        labelWidth = QtGui.QFontMetricsF(TitleBlockFont(name, heading = True)).horizontalAdvance(label) + 12
        if name == "comments":
            preferredWidth = min(200, max(preferredWidth, max(metrics.horizontalAdvance(line) for line in value.split("\n")) + 12))
        columnWidth = math.ceil(max(labelWidth, preferredWidth))
        heights = []
        for width in (68 if name in ("date", "scale") else 148, columnWidth - 12):
            lines = TitleBlockTextLines(value, TitleBlockFont(name), width)
            heights.append(math.ceil(24 + (sum(lineHeight for text, lineHeight, ascent in lines) if value.strip() else 0)))
        if name == "comments":
            heights[0] = max(heights[0], math.ceil(24 + 4 * lines[0][1]))
        fields.append((name, label, value, heights[0], columnWidth, heights[1]))
    logo, size = TitleBlockLogo(options)
    if logo is not None:
        aspectRatio = size.width() / size.height()
        rowHeight = math.ceil((min(200, max(24, 148 / aspectRatio + 12)) - 12) * .6 + 12)
        columnHeight = max(50, max(sum(field[5] for field in group) for group in TitleBlockGroups(fields)))
        columnWidth = math.ceil(min(200, max(24, (columnHeight - 12) * aspectRatio + 12)))
        fields.insert(0, ("logo", "", "", rowHeight, columnWidth, 0))
    return fields


def TitleBlockLayout(width, height, options, scale = 100, architecturalScale = None, outputFormat = "png", dpi = None):
    if not options or not options.get("enabled", False):
        return width, height, None
    fields = TitleBlockFields(options, scale, architecturalScale, outputFormat)
    groups = TitleBlockGroups(fields)
    factor = TitleBlockUnitScale(scale, architecturalScale, outputFormat, dpi)
    if options.get("position", "Right") == "Right":
        height = max(height, math.ceil(sum(max(field[3] for field in group) for group in groups) * factor))
        blockWidth = math.ceil(160 * factor)
        return width + blockWidth, height, (width, 0, blockWidth, height)
    width = max(width, math.ceil(sum(max(field[4] for field in group) for group in groups) * factor))
    blockHeight = math.ceil(max(50, max(sum(field[5] for field in group) for group in groups)) * factor)
    return width, height + blockHeight, (0, height, width, blockHeight)


def TitleBlockCells(block, options, scale, architecturalScale = None, outputFormat = "png", dpi = None):
    factor = TitleBlockUnitScale(scale, architecturalScale, outputFormat, dpi)
    rect = QtCore.QRectF(*(value / factor for value in block))
    vertical = options.get("position", "Right") == "Right"
    fields = TitleBlockFields(options, scale, architecturalScale, outputFormat)
    groups = TitleBlockGroups(fields)
    available = rect.height() if vertical else rect.width()
    extra = max(0, available - sum(max(field[3 if vertical else 4] for field in group) for group in groups))
    cells = []
    offset = rect.top() if vertical else rect.left()
    for group in groups:
        name = group[0][0]
        if name == "sheetNumber" and (vertical or not any(field[0] == "comments" for field in fields)):
            if extra > 0:
                spacer = (QtCore.QRectF(rect.left(), offset, rect.width(), extra) if vertical else
                          QtCore.QRectF(offset, rect.top(), extra, rect.height()))
                cells.append(("spacer", "", "", QtCore.QRectF(spacer.x() * factor, spacer.y() * factor,
                                                             spacer.width() * factor, spacer.height() * factor)))
                offset += extra
        extent = max(field[3 if vertical else 4] for field in group) + (extra if not vertical and name == "comments" else 0)
        for index, (name, label, value, rowHeight, columnWidth, columnHeight) in enumerate(group):
            cell = (QtCore.QRectF(rect.left() + index * rect.width() / len(group), offset, rect.width() / len(group), extent) if vertical else
                    QtCore.QRectF(offset, rect.top() + index * rect.height() / len(group), extent, rect.height() / len(group)))
            cells.append((name, label, value, QtCore.QRectF(cell.x() * factor, cell.y() * factor, cell.width() * factor, cell.height() * factor)))
        offset += extent
    return cells


def DrawTitleBlock(painter, block, options, scale, architecturalScale = None, outputFormat = "png", dpi = None):
    factor = TitleBlockUnitScale(scale, architecturalScale, outputFormat, dpi)
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
    painter.save()
    try:
        painter.scale(factor, factor)
        painter.setClipRect(rect, QtCore.Qt.ClipOperation.IntersectClip)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.fillRect(rect, QtGui.QColor(palette.themeColors["canvas"]))
        for name, label, value, cell in TitleBlockCells(block, options, scale, architecturalScale, outputFormat, dpi):
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
                DrawTitleBlockText(painter, QtCore.QPointF(cell.left() + 6, cell.top() + 12), label)
                painter.setPen(textColor)
                font = TitleBlockFont(name)
                painter.setFont(font)
                lines = TitleBlockTextLines(value, font, cell.width() - 12, painter.device())
                textY = cell.top() + 18
                if name == "sheetNumber" and not vertical:
                    textY = cell.bottom() - 6 - sum(lineHeight for text, lineHeight, ascent in lines)
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
            # Design units are 0.32 mm: keep printed rules light at every PPI.
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
