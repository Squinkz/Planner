"""Frozen preview before selective recoloring and adjacent-mask consolidation.

Used only for independent pixel comparisons; retain its original layer grouping
and all-layer recoloring behavior.
"""
import copy
import math
import re
from xml.etree import ElementTree
from planner_app.graphics.path_operations import Paths
from PySide6 import QtCore, QtGui, QtSvg


def SvgClipPath(element):
    """Read the path commands emitted by QSvgGenerator."""
    path = QtGui.QPainterPath()
    path.setFillRule(QtCore.Qt.FillRule.OddEvenFill if element.get("clip-rule", element.get("fill-rule")) == "evenodd"
                     else QtCore.Qt.FillRule.WindingFill)
    tokens = re.findall(r"[A-Za-z]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", element.get("d", ""))
    index, command = 0, None
    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index]
            index += 1
            if command.upper() == "Z":
                path.closeSubpath()
                continue
        count = {"M": 2, "L": 2, "H": 1, "V": 1, "Q": 4, "C": 6}.get(command.upper())
        if count is None or index + count > len(tokens):
            raise ValueError("Unsupported SVG preview clip path.")
        values = [float(value) for value in tokens[index:index + count]]
        index += count
        current = path.currentPosition()
        if command.islower():
            for coordinate in range(count):
                vertical = command.upper() == "V" or command.upper() != "H" and coordinate % 2 == 1
                values[coordinate] += current.y() if vertical else current.x()
        if command.upper() == "M":
            path.moveTo(*values)
            command = "l" if command.islower() else "L"
        elif command.upper() == "L":
            path.lineTo(*values)
        elif command.upper() == "H":
            path.lineTo(values[0], current.y())
        elif command.upper() == "V":
            path.lineTo(current.x(), values[0])
        elif command.upper() == "Q":
            path.quadTo(*values)
        elif command.upper() == "C":
            path.cubicTo(*values)
    return path


class SvgPreviewRenderer(QtCore.QObject):
    def __init__(self, svgData, parent = None):
        super().__init__(parent)
        root = ElementTree.fromstring(svgData)
        self.root = root
        namespace = "{http://www.w3.org/2000/svg}"
        self.viewBox = QtCore.QRectF(*map(float, root.get("viewBox").split()))
        # Architectural files express width/height in physical units (mm).
        # Preview buffers use the viewBox's renderer coordinate system instead.
        if (not all(math.isfinite(value) for value in (self.viewBox.x(), self.viewBox.y(), self.viewBox.width(), self.viewBox.height()))
                or self.viewBox.width() <= 0 or self.viewBox.height() <= 0):
            raise ValueError("Invalid SVG preview viewBox.")
        self.size = QtCore.QSize(math.ceil(self.viewBox.width()), math.ceil(self.viewBox.height()))
        clips = {}
        definitions = ElementTree.Element(namespace + "defs")
        for group in root.findall(namespace + "defs"):
            for element in group:
                if element.tag == namespace + "clipPath":
                    clip = QtGui.QPainterPath()
                    for shape in element:
                        if shape.tag != namespace + "path":
                            raise ValueError("Unsupported SVG preview clip shape.")
                        shapePath = SvgClipPath(shape)
                        clip = Paths.Union(clip, shapePath) if not clip.isEmpty() else shapePath
                    clips[element.get("id")] = clip
                else:
                    definitions.append(element)

        layers = []

        def Visit(element, ancestors, clipKeys, clipPaths, transform):
            localTransform = element.get("transform")
            if localTransform:
                # Qt emits affine transforms as matrix(a,b,c,d,e,f).
                match = re.fullmatch(r"matrix\(([^)]+)\)", localTransform)
                if match is None:
                    raise ValueError("Unsupported SVG preview transform.")
                values = [float(value) for value in re.split(r"[\s,]+", match.group(1).strip())]
                transform = QtGui.QTransform(*values) * transform
            reference = element.get("clip-path")
            if reference:
                clipId = reference.removeprefix("url(#").removesuffix(")")
                clipKeys += ((clipId, transform.m11(), transform.m12(), transform.m21(), transform.m22(), transform.dx(), transform.dy()),)
                clipPaths += (transform.map(clips[clipId]),)
            if any("clip-path" in child.attrib for child in list(element.iter())[1:]):
                wrapper = ElementTree.Element(element.tag, element.attrib)
                wrapper.attrib.pop("clip-path", None)
                for child in element:
                    Visit(child, ancestors + (wrapper,), clipKeys, clipPaths, transform)
                return
            content = copy.deepcopy(element)
            content.attrib.pop("clip-path", None)
            for ancestor in reversed(ancestors):
                wrapper = ElementTree.Element(ancestor.tag, ancestor.attrib)
                wrapper.append(content)
                content = wrapper
            if not layers or layers[-1][0] != clipKeys:
                layer = ElementTree.Element(root.tag, root.attrib)
                layer.append(definitions)
                layers.append((clipKeys, clipPaths, layer))
            layers[-1][2].append(content)

        for element in root:
            if element.tag not in (namespace + "defs", namespace + "title", namespace + "desc"):
                Visit(element, (), (), (), QtGui.QTransform())
        self.layers = []
        self.layerSources = []
        for clipKeys, clipPaths, layer in layers:
            renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(ElementTree.tostring(layer)), self)
            if not renderer.isValid():
                raise ValueError("Could not display the SVG preview.")
            self.layers.append((clipPaths, renderer))
            self.layerSources.append(layer)

    def Recolor(self, colors):
        """Reuse parsed clip geometry and layer structure for palette edits."""
        paints = {role: QtGui.QColor(color).name() for role, color in colors.items()}
        for root in [self.root] + self.layerSources:
            for element in root.iter():
                for attribute in ("fill", "stroke", "stop-color"):
                    role = element.get("data-planner-" + attribute)
                    if role is not None:
                        element.set(attribute, paints[role])
        for root, (clipPaths, renderer) in zip(self.layerSources, self.layers):
            if not renderer.load(QtCore.QByteArray(ElementTree.tostring(root))):
                raise ValueError("Could not recolor the SVG preview.")
        return ElementTree.tostring(self.root, encoding = "utf-8", xml_declaration = True)

    def defaultSize(self):
        return self.size

    def isValid(self):
        return bool(self.layers)

    def render(self, painter, target = None):
        target = target if target is not None else QtCore.QRectF(0, 0, painter.device().width(), painter.device().height())
        transform = QtGui.QTransform().translate(target.x(), target.y()).scale(
            target.width() / self.viewBox.width(), target.height() / self.viewBox.height()).translate(
                -self.viewBox.x(), -self.viewBox.y())
        for clipPaths, renderer in self.layers:
            painter.save()
            try:
                for path in clipPaths:
                    painter.setClipPath(transform.map(path), QtCore.Qt.ClipOperation.IntersectClip)
                renderer.render(painter, target)
            finally:
                painter.restore()
