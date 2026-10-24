"""Render Planner SVG layers with native clipping instead of bitmap masks."""
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
        clipSources = {}
        definitions = ElementTree.Element(namespace + "defs")
        for group in root.findall(namespace + "defs"):
            for element in group:
                if element.tag == namespace + "clipPath":
                    sourceKey = tuple((shape.tag, tuple(sorted(shape.attrib.items()))) for shape in element)
                    if sourceKey in clipSources:
                        clips[element.get("id")] = clipSources[sourceKey]
                        continue
                    clip = QtGui.QPainterPath()
                    for shape in element:
                        if shape.tag != namespace + "path":
                            raise ValueError("Unsupported SVG preview clip shape.")
                        shapePath = SvgClipPath(shape)
                        clip = Paths.Union(clip, shapePath) if not clip.isEmpty() else shapePath
                    clips[element.get("id")] = clip
                    clipSources[sourceKey] = clip
                else:
                    definitions.append(element)

        layers = []
        mappedClips = {}
        clipGeometry = {}

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
                sourceKey = (clipId, transform.m11(), transform.m12(), transform.m21(), transform.m22(), transform.dx(), transform.dy())
                mapped = mappedClips.get(sourceKey)
                if mapped is None:
                    path = transform.map(clips[clipId])
                    # Native serialization retains exact coordinates, curves and
                    # fill rules. Equal masks can have different exported IDs.
                    encoded = QtCore.QByteArray()
                    stream = QtCore.QDataStream(encoded, QtCore.QIODevice.OpenModeFlag.WriteOnly)
                    stream << path
                    geometryKey = bytes(encoded)
                    mapped = (geometryKey, clipGeometry.setdefault(geometryKey, path))
                    mappedClips[sourceKey] = mapped
                clipKeys += (mapped[0],)
                clipPaths += (mapped[1],)
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
        referencePattern = re.compile(r"url\(\s*['\"]?#([^)'\"\s]+)['\"]?\s*\)", re.IGNORECASE)
        definitionsById = {element.get("id"): element for element in definitions.iter() if element.get("id")}
        definitionOwners = {element.get("id"): owner for owner in definitions for element in owner.iter() if element.get("id")}
        globalStyles = [element for element in definitions if element.tag == namespace + "style"]
        for clipKeys, clipPaths, layer in layers:
            # Each Qt renderer needs only definitions referenced by its layer.
            # Repeating every material tile in thousands of independent XML
            # documents otherwise dominates preview construction and recoloring.
            if not globalStyles:
                pending = [child for child in layer if child is not definitions]
                visited = set()
                required = set()
                while pending:
                    element = pending.pop()
                    if id(element) in visited:
                        continue
                    visited.add(id(element))
                    pending.extend(element)
                    for attribute, value in element.attrib.items():
                        references = referencePattern.findall(value) if "url(" in value.lower() else []
                        if attribute.rsplit("}", 1)[-1] == "href" and value.startswith("#"):
                            references.append(value[1:])
                        for reference in references:
                            if reference in definitionsById:
                                required.add(definitionOwners[reference])
                                pending.append(definitionsById[reference])
                localDefinitions = ElementTree.Element(definitions.tag, definitions.attrib)
                localDefinitions.extend(owner for owner in definitions if owner in required)
                layer.remove(definitions)
                layer.insert(0, localDefinitions)
            renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(ElementTree.tostring(layer)), self)
            if not renderer.isValid():
                raise ValueError("Could not display the SVG preview.")
            self.layers.append((clipPaths, renderer))
            self.layerSources.append(layer)
        # Bind each named paint once, including paints inherited from groups or
        # referenced through shared gradient/pattern definitions. Shared XML
        # nodes are mutated once, but every dependent layer must reload.
        self.paintBindings = {}
        self.paintLayers = {}
        self.paintValues = {}
        seenBindings = set()
        for layerIndex, source in enumerate([self.root] + self.layerSources):
            pending = [source]
            visited = set()
            while pending:
                element = pending.pop()
                if layerIndex and element is definitions:
                    pending.extend(globalStyles)
                    continue
                if id(element) in visited:
                    continue
                visited.add(id(element))
                pending.extend(element)
                for attribute in ("fill", "stroke", "stop-color"):
                    role = element.get("data-planner-" + attribute)
                    if role is None:
                        continue
                    bindingKey = (id(element), attribute)
                    if bindingKey not in seenBindings:
                        seenBindings.add(bindingKey)
                        self.paintBindings.setdefault(role, []).append((element, attribute))
                        self.paintValues[role] = QtGui.QColor(element.get(attribute)).name()
                    if layerIndex:
                        self.paintLayers.setdefault(role, set()).add(layerIndex - 1)
                if layerIndex:
                    # A shared definition affects only layers that actually use
                    # it, including indirect gradient/pattern href references.
                    for attribute, value in element.attrib.items():
                        references = referencePattern.findall(value) if "url(" in value.lower() else []
                        if attribute.rsplit("}", 1)[-1] == "href" and value.startswith("#"):
                            references.append(value[1:])
                        pending.extend(definitionsById[reference] for reference in references if reference in definitionsById)
                    if element.tag == namespace + "style" and element.text:
                        pending.extend(definitionsById[reference] for reference in referencePattern.findall(element.text)
                                       if reference in definitionsById)

    def Recolor(self, colors):
        """Reuse parsed clip geometry and layer structure for palette edits."""
        paints = {role: QtGui.QColor(colors[role]).name() for role in self.paintBindings}
        changedRoles = {role for role, paint in paints.items() if paint != self.paintValues[role]}
        affectedLayers = set()
        for role in changedRoles:
            for element, attribute in self.paintBindings[role]:
                element.set(attribute, paints[role])
            affectedLayers.update(self.paintLayers.get(role, ()))
        for layerIndex in sorted(affectedLayers):
            root = self.layerSources[layerIndex]
            clipPaths, renderer = self.layers[layerIndex]
            if not renderer.load(QtCore.QByteArray(ElementTree.tostring(root))):
                raise ValueError("Could not recolor the SVG preview.")
        self.paintValues.update(paints)
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
