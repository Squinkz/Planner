"""Write complete Print pages to one PDF without changing their renderer."""
import math
import copy
import re
from xml.etree import ElementTree
from PySide6 import QtCore, QtGui, QtSvg


def SvgPathData(path):
    parts = []
    index = 0
    while index < path.elementCount():
        point = path.elementAt(index)
        if point.type == QtGui.QPainterPath.ElementType.MoveToElement:
            parts.append(f"M{point.x:.12g},{point.y:.12g}")
        elif point.type == QtGui.QPainterPath.ElementType.LineToElement:
            parts.append(f"L{point.x:.12g},{point.y:.12g}")
        else:
            middle, end = path.elementAt(index + 1), path.elementAt(index + 2)
            parts.append(f"C{point.x:.12g},{point.y:.12g} {middle.x:.12g},{middle.y:.12g} {end.x:.12g},{end.y:.12g}")
            index += 2
        index += 1
    return " ".join(parts)


def SvgTransform(element):
    transform = element.get("transform")
    if transform is None:
        return QtGui.QTransform()
    match = re.fullmatch(r"matrix\(([^)]+)\)", transform)
    if match is None:
        raise ValueError("Unsupported PDF material transform.")
    return QtGui.QTransform(*map(float, re.split(r"[\s,]+", match.group(1).strip())))


def SvgFillPath(element, clips, rule = "nonzero", includeTransform = True):
    from planner_app.graphics.svg_preview import SvgClipPath
    rule = element.get("fill-rule", rule)
    path = QtGui.QPainterPath()
    if element.tag.endswith("}path"):
        path = SvgClipPath(element)
    elif element.tag.endswith("}g"):
        for child in element:
            path.addPath(SvgFillPath(child, clips, rule))
    else:
        raise ValueError("Unsupported PDF material shape.")
    path.setFillRule(QtCore.Qt.FillRule.OddEvenFill if rule == "evenodd" else QtCore.Qt.FillRule.WindingFill)
    clip = element.get("clip-path")
    if clip is not None and includeTransform:
        path = path.intersected(clips[clip.removeprefix("url(#").removesuffix(")")])
    return SvgTransform(element).map(path) if includeTransform else path


def VectorPdfSvg(content):
    """Replace Planner's pattern brushes with clipped, reusable vector tiles.

    Qt's SVG reader otherwise paints patterns through bitmap texture brushes.
    Bake a tiny tile's stroke outlines once, then repeat only tiles touching the
    visible wall fill. Other SVG content keeps the existing preview renderer.
    """
    from planner_app.graphics.object_composite import ObjectPaintDevice
    from planner_app.graphics.path_operations import Paths
    from planner_app.graphics.svg_preview import SvgClipPath
    namespace = "{http://www.w3.org/2000/svg}"
    root = ElementTree.fromstring(content)
    # Qt SVG represents stroke="none" as a solid-style pen with NoBrush.
    # The PDF engine can still expand that pen around filled glyphs. Use an
    # explicitly transparent stroke on drawing leaves to avoid thickened ink.
    pending = [(root, "none")]
    drawingTags = {namespace + name for name in ("path", "rect", "ellipse", "circle", "line", "polyline", "polygon")}
    while pending:
        element, inherited = pending.pop()
        stroke = element.get("stroke", inherited)
        if stroke == "none" and element.tag in drawingTags:
            element.set("stroke", "#000000")
            element.set("stroke-opacity", "0")
        pending.extend((child, stroke) for child in element)
    definitions = root.find(namespace + "defs")
    patterns = {element.get("id"): element for element in (() if definitions is None else definitions)
                if element.tag == namespace + "pattern" and element.get("id", "").startswith("plannerMaterial")}
    if not patterns:
        return root
    clips = {}
    for element in definitions:
        if element.tag == namespace + "clipPath":
            clip = QtGui.QPainterPath()
            for shape in element:
                clip.addPath(SvgClipPath(shape))
            clips[element.get("id")] = clip
    tiles = {}
    for index, (name, pattern) in enumerate(patterns.items()):
        width, height = float(pattern.get("width")), float(pattern.get("height"))
        tileRect = QtCore.QRectF(0, 0, width, height)
        tileClip = QtGui.QPainterPath()
        tileClip.addRect(tileRect)
        tile = ElementTree.Element(namespace + "svg", dict(viewBox = f"0 0 {width} {height}"))
        tile.extend(copy.deepcopy(list(pattern)))
        renderer = QtSvg.QSvgRenderer(ElementTree.tostring(tile))
        device = ObjectPaintDevice(QtCore.QSize(math.ceil(width), math.ceil(height)), "transparent")
        device.engine.captureBackground = False
        with QtGui.QPainter(device) as painter:
            renderer.render(painter, tileRect)
        tileId = f"plannerPdfTile{index}"
        group = ElementTree.SubElement(definitions, namespace + "g", dict(id = tileId))
        for path, pen, brush, transform, opacity, clip, mask, hints, origin in device.engine.commands:
            fills = []
            if brush.style() != QtCore.Qt.BrushStyle.NoBrush and brush.color().alpha() > 0:
                fills.append((path, brush.color()))
            if pen.style() != QtCore.Qt.PenStyle.NoPen and pen.brush().style() != QtCore.Qt.BrushStyle.NoBrush and pen.color().alpha() > 0:
                fills.append((Paths.PreparePenStroke(pen)(path), pen.color()))
            for ink, color in fills:
                ink = transform.map(ink).intersected(tileClip)
                if clip is not None:
                    ink = ink.intersected(clip)
                if not ink.isEmpty():
                    ElementTree.SubElement(group, namespace + "path", {
                        "d": SvgPathData(ink), "fill": color.name(), "fill-opacity": str(color.alphaF() * opacity),
                        "stroke": "#000000", "stroke-opacity": "0",
                        "fill-rule": "evenodd" if ink.fillRule() == QtCore.Qt.FillRule.OddEvenFill else "nonzero"})
        tiles[name] = (tileId, width, height)
    view = QtCore.QRectF(*map(float, root.get("viewBox").split()))
    pending = [(element, QtGui.QTransform()) for element in root if element is not definitions]
    serial = 0
    while pending:
        element, parent = pending.pop()
        transform = SvgTransform(element) * parent
        name = element.get("fill", "").removeprefix("url(#").removesuffix(")")
        if name not in tiles:
            pending.extend((child, transform) for child in element)
            continue
        path = SvgFillPath(element, clips, includeTransform = False)
        inverse, valid = transform.inverted()
        if not valid:
            raise ValueError("Invalid PDF material transform.")
        bounds = path.boundingRect().intersected(inverse.mapRect(view))
        clipId = f"plannerPdfHatch{serial}"
        serial += 1
        clip = ElementTree.SubElement(definitions, namespace + "clipPath", {"id": clipId, "clipPathUnits": "userSpaceOnUse"})
        ElementTree.SubElement(clip, namespace + "path", {"d": SvgPathData(path),
            "fill-rule": "evenodd" if path.fillRule() == QtCore.Qt.FillRule.OddEvenFill else "nonzero"})
        attributes = dict(element.attrib)
        element.clear()
        element.tag = namespace + "g"
        element.attrib.update(attributes)
        element.set("fill", "none")
        element.set("stroke", "none")
        group = ElementTree.SubElement(element, namespace + "g", {"clip-path": f"url(#{clipId})"})
        tileId, width, height = tiles[name]
        for row in range(math.floor(bounds.top() / height), math.ceil(bounds.bottom() / height)):
            for column in range(math.floor(bounds.left() / width), math.ceil(bounds.right() / width)):
                x, y = column * width, row * height
                if path.intersects(QtCore.QRectF(x, y, width, height)):
                    ElementTree.SubElement(group, namespace + "use", {
                        "{http://www.w3.org/1999/xlink}href": "#" + tileId, "transform": f"matrix(1,0,0,1,{x},{y})"})
    return root


class PdfExporter:
    def __init__(self, path, title = ""):
        self.writer = QtGui.QPdfWriter(str(path))
        self.writer.setCreator("Planner")
        self.writer.setTitle(title)
        # This is the vector coordinate grid. Raster pages retain their own
        # image resolution when placed over the exact physical sheet rectangle.
        self.writer.setResolution(300)
        self.painter = None
        self.pageCount = 0

    def AddPage(self, content, paper):
        if len(paper) != 2 or not all(type(value) in (int, float) and math.isfinite(value) and value > 0 for value in paper):
            raise ValueError("Invalid PDF page size.")
        page = QtGui.QPageSize(QtCore.QSizeF(*paper), QtGui.QPageSize.Unit.Millimeter,
                               "Planner sheet", QtGui.QPageSize.SizeMatchPolicy.ExactMatch)
        layout = QtGui.QPageLayout(page, QtGui.QPageLayout.Orientation.Portrait, QtCore.QMarginsF(), QtGui.QPageLayout.Unit.Millimeter)
        layout.setMode(QtGui.QPageLayout.Mode.FullPageMode)
        if not self.writer.setPageLayout(layout):
            raise ValueError("Could not configure the PDF page.")
        if self.painter is None:
            self.painter = QtGui.QPainter()
            if not self.painter.begin(self.writer):
                self.painter = None
                raise OSError("Could not start writing the PDF.")
            self.painter.setRenderHint(QtGui.QPainter.RenderHint.LosslessImageRendering, True)
        elif not self.writer.newPage():
            raise OSError("Could not add the next PDF page.")
        target = QtCore.QRectF(0, 0, self.writer.width(), self.writer.height())
        if isinstance(content, QtGui.QImage):
            if content.isNull():
                raise ValueError("The PDF page image is empty.")
            self.painter.drawImage(target, content)
        else:
            from planner_app.graphics.svg_preview import SvgPreviewRenderer
            self.painter.setPen(QtCore.Qt.PenStyle.NoPen)
            self.painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            renderer = SvgPreviewRenderer(VectorPdfSvg(content))
            try:
                if not renderer.isValid():
                    raise ValueError("Could not read the vector PDF page.")
                renderer.render(self.painter, target)
            finally:
                renderer.deleteLater()
        self.pageCount += 1

    def Close(self):
        painter, self.painter = self.painter, None
        if painter is not None and not painter.end():
            raise OSError("Could not finish writing the PDF.")
        self.writer = None
