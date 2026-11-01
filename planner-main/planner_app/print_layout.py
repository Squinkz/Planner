"""Fixed paper sizing and selection of complete drawing-area tiles."""
import math


# Portrait dimensions in millimetres. US sizes retain exact inch conversions.
printPaperSizes = {
    "A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420),
    "A4": (210, 297),
    "ARCH A": (228.6, 304.8), "ARCH B": (304.8, 457.2), "ARCH C": (457.2, 609.6),
    "ARCH D": (609.6, 914.4), "ARCH E": (914.4, 1219.2),
    "Letter": (215.9, 279.4), "Legal": (215.9, 355.6), "Tabloid": (279.4, 431.8),
}


def PrintPaperSize(options):
    size = options.get("pageSize", "A4")
    if size not in printPaperSizes:
        raise ValueError("Unsupported print page size.")
    width, height = printPaperSizes[size]
    return (height, width) if options.get("pageOrientation", "Landscape") == "Landscape" else (width, height)


def PrintPaperGeometry(options):
    extent = tuple(size * options.get("architecturalScale", 100) for size in PrintPaperSize(options))
    return extent, extent


def PrintOverlapOffset(options, overlap, bounds):
    """Change source coverage about the current crop centre, leaving sheets fixed."""
    extent, stride = PrintPaperGeometry(options)
    origin = options.get("pageOrigin", (0, 0))
    previous = options.get("pageOverlap", (0, 0))
    offset = options.get("pageOverlapOffset", (0, 0))
    result = []
    for axis in range(2):
        centre = (bounds[axis] + bounds[axis + 2] / 2 - origin[axis]) / extent[axis] - .5
        value = offset[axis] + (overlap[axis] - previous[axis]) * centre
        result.append(0.0 if abs(value) < 1e-8 else value)
    return result


def UpgradePrintOverlap(options):
    """Keep saved page counts and source cuts from the old overlapping-sheet layout."""
    overlap = options.get("pageOverlap", (0, 0))
    if options.get("scaleMode") != "Print" or "pageOverlapOffset" in options or not any(overlap):
        return options
    updated = dict(options, pageOverlapOffset = [0, 0])
    bounds = options.get("bounds")
    if bounds is None:
        return updated
    extent, stride = PrintPaperGeometry(options)
    legacy = tuple(size - amount for size, amount in zip(extent, overlap))
    if min(legacy) <= 0:
        return updated
    origin = options.get("pageOrigin", (0, 0))
    try:
        pages = SelectedPrintPages(bounds, extent, origin, stride = legacy)
    except ValueError:
        return updated
    if not pages:
        return updated
    first = [round((min(page[axis] for page in pages) - origin[axis]) / legacy[axis]) for axis in range(2)]
    last = [round((max(page[axis] for page in pages) - origin[axis]) / legacy[axis]) for axis in range(2)]
    size = [(end - start + 1) * dimension for start, end, dimension in zip(first, last, extent)]
    start = [bounds[axis] + (bounds[axis + 2] - size[axis]) / 2 for axis in range(2)]
    newOrigin = [start[axis] - first[axis] * extent[axis] for axis in range(2)]
    updated.update(bounds = [*start, *size], pageOrigin = newOrigin,
                   pageOverlapOffset = [origin[axis] - newOrigin[axis] for axis in range(2)])
    return updated


def ConstrainPrintBounds(bounds, options, origin = (0, 0), edge = None):
    """Retain a complete paper cell, keeping the opposite crop edge fixed on drag."""
    if bounds is None:
        return bounds
    paper, strides = PrintPaperGeometry(options)
    starts, ends = list(bounds[:2]), [bounds[0] + bounds[2], bounds[1] + bounds[3]]
    for axis, (dimension, step) in enumerate(zip(paper, strides)):
        first = math.ceil((starts[axis] - origin[axis]) / step - 1e-9)
        last = math.floor((ends[axis] - origin[axis] - dimension) / step + 1e-9)
        if last >= first:
            continue
        if edge == axis * 2:
            starts[axis] = origin[axis] + last * step
        elif edge == axis * 2 + 1:
            ends[axis] = origin[axis] + first * step + dimension
        else:
            page = math.floor(((starts[axis] + ends[axis] - dimension) / 2 - origin[axis]) / step + .5)
            starts[axis] = min(starts[axis], origin[axis] + page * step)
            ends[axis] = max(ends[axis], origin[axis] + page * step + dimension)
    return starts[0], starts[1], ends[0] - starts[0], ends[1] - starts[1]


def ResizePrintSelection(bounds, options, name, value, updates = None):
    """Resize selected paper cells around their centre, discarding partial margins."""
    origin = options.get("pageOrigin", (0, 0))
    tile, stride = PrintPaperGeometry(options)
    bounds = ConstrainPrintBounds(bounds, options, origin)
    pages = SelectedPrintPages(bounds, tile, origin, stride = stride)
    left, bottom = min(page[0] for page in pages), min(page[1] for page in pages)
    right = max(page[0] + page[2] for page in pages)
    top = max(page[1] + page[3] for page in pages)
    columns, rows = round((right - left - tile[0]) / stride[0]) + 1, round((top - bottom - tile[1]) / stride[1]) + 1
    column, row = round((left - origin[0]) / stride[0]), round((bottom - origin[1]) / stride[1])
    updated = dict(options)
    updated[name] = value
    updated.update(updates or {})
    newTile, newStride = PrintPaperGeometry(updated)
    width, height = newTile[0] + (columns - 1) * newStride[0], newTile[1] + (rows - 1) * newStride[1]
    centreX, centreY = (left + right) / 2, (bottom + top) / 2
    if name == "pageOverlap":
        centreX, centreY = bounds[0] + bounds[2] / 2, bounds[1] + bounds[3] / 2
    x, y = centreX - width / 2, centreY - height / 2
    return (x, y, width, height), (x - column * newStride[0], y - row * newStride[1])


def PrintPageLayout(options, border, titleBlock, outputFormat = "png"):
    from planner_app.graphics.title_block import TitleBlockLayout
    paper = PrintPaperSize(options)
    dpi = options.get("dpi", 300)
    width, height = (max(1, round(value * dpi / 25.4)) for value in paper)
    baselineWidth, baselineHeight = (max(1, round(value * 300 / 25.4)) for value in paper)
    baselineScale = 300 * 1000 / (25.4 * options.get("architecturalScale", 100))
    drawingWidth, drawingHeight = baselineWidth, baselineHeight
    if titleBlock.get("enabled", False):
        vertical = titleBlock.get("position", "Right") == "Right"
        minimumWidth, minimumHeight, block = TitleBlockLayout(baselineWidth if not vertical else 1, 1, titleBlock,
            baselineScale, options.get("architecturalScale", 100), outputFormat, 300, fitWidth = not vertical, pageSize = paper)
        if vertical:
            drawingWidth -= block[2]
            if minimumHeight > baselineHeight:
                raise ValueError("The title block is taller than this page. Shorten its text or choose portrait orientation.")
        else:
            drawingHeight -= block[3]
    drawingWidth -= 2 * border
    drawingHeight -= 2 * border
    if drawingWidth < 1 or drawingHeight < 1:
        raise ValueError("The border and title block leave no drawing area on this page.")
    tile = (drawingWidth * 1000 / baselineScale, drawingHeight * 1000 / baselineScale)
    overlap = options.get("pageOverlap", (0, 0))
    stride = tuple(size - amount for size, amount in zip(tile, overlap))
    if any(not math.isfinite(value) or value <= 0 for value in stride):
        raise ValueError("Page overlap must be smaller than the page's drawing area.")
    paperTile, paperStride = PrintPaperGeometry(options)
    return dict(paper = paper, pixels = (width, height), drawingPixels = (drawingWidth, drawingHeight),
                baselinePixels = (baselineWidth, baselineHeight),
                tile = tile, stride = stride, offset = tuple(options.get("pageOverlapOffset", (0, 0))),
                paperTile = paperTile, paperStride = paperStride)


def PrintDrawingBounds(page, layout, origin = (0, 0)):
    paperStride = layout.get("paperStride", layout["paperTile"])
    column = round((page[0] - origin[0]) / paperStride[0])
    row = round((page[1] - origin[1]) / paperStride[1])
    width, height = layout["tile"]
    stepX, stepY = layout.get("stride", layout["tile"])
    offsetX, offsetY = layout.get("offset", (0, 0))
    return origin[0] + offsetX + column * stepX, origin[1] + offsetY + row * stepY, width, height


def SelectedPrintPages(bounds, tile, origin = (0, 0), maximum = 256, fullyEnclosed = True, stride = None):
    x, y, width, height = bounds
    tileWidth, tileHeight = tile
    stepX, stepY = stride or tile
    if fullyEnclosed:
        firstColumn = math.ceil((x - origin[0]) / stepX - 1e-9)
        lastColumn = math.floor((x + width - origin[0] - tileWidth) / stepX + 1e-9)
        firstRow = math.ceil((y - origin[1]) / stepY - 1e-9)
        lastRow = math.floor((y + height - origin[1] - tileHeight) / stepY + 1e-9)
    else:
        firstColumn = math.floor((x - origin[0] - tileWidth) / stepX + 1e-9) + 1
        lastColumn = math.ceil((x + width - origin[0]) / stepX - 1e-9) - 1
        firstRow = math.floor((y - origin[1] - tileHeight) / stepY + 1e-9) + 1
        lastRow = math.ceil((y + height - origin[1]) / stepY - 1e-9) - 1
    if lastColumn < firstColumn or lastRow < firstRow:
        return []
    count = (lastColumn - firstColumn + 1) * (lastRow - firstRow + 1)
    if count > maximum:
        raise ValueError(f"The crop selects {count} pages. Select at most {maximum} pages per export.")
    return [(origin[0] + column * stepX, origin[1] + row * stepY, tileWidth, tileHeight)
            for row in range(lastRow, firstRow - 1, -1) for column in range(firstColumn, lastColumn + 1)]
