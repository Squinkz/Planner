"""Render Planner SVG layers with native clipping instead of bitmap masks."""
import copy
import math
import re
from threading import Lock
from collections import OrderedDict
from xml.etree import ElementTree
from planner_app.graphics.path_operations import Paths
from planner_app.geometry.spatial_index import BoundsIndex
from PySide6 import QtCore, QtGui, QtSvg

clipPathCache = OrderedDict()
clipPathCacheElements = clipPathCacheBytes = 0
clipPathCacheLock = Lock()


class SvgPreviewDocument:
    """Owned, already parsed worker output with a conservative size budget."""
    def __init__(self, root, size):
        self.root, self.size = root, size
        self.renderer = None
        self.prepared = None

    def __len__(self):
        return self.size


class SvgPreviewLayer:
    """Address one native group without reparsing a document per clip layer."""
    def __init__(self, renderer, name, viewBox):
        self.renderer, self.name, self.viewBox = renderer, name, viewBox
        self.bounds = renderer.boundsOnElement(name)
        self.inkBounds = renderer.boundsOnElement(name + "Ink")

    def render(self, painter, target):
        painter.save()
        try:
            painter.translate(target.topLeft())
            painter.scale(target.width() / self.viewBox.width(), target.height() / self.viewBox.height())
            painter.translate(-self.viewBox.x(), -self.viewBox.y())
            self.renderer.render(painter, self.name, self.bounds)
        finally:
            painter.restore()


def SvgClipPath(element, useCache = True):
    """Read the path commands emitted by QSvgGenerator."""
    global clipPathCacheElements, clipPathCacheBytes
    rule = element.get("clip-rule", element.get("fill-rule"))
    source = element.get("d", "")
    key = (source, rule)
    if useCache:
        with clipPathCacheLock:
            cached = clipPathCache.get(key)
            if cached is not None:
                clipPathCache.move_to_end(key)
                return QtGui.QPainterPath(cached)
    path = QtGui.QPainterPath()
    path.setFillRule(QtCore.Qt.FillRule.OddEvenFill if rule == "evenodd"
                     else QtCore.Qt.FillRule.WindingFill)
    tokens = re.findall(r"[A-Za-z]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", source)
    argumentCounts = {"M": 2, "L": 2, "H": 1, "V": 1, "Q": 4, "C": 6}
    index, command, count, relative = 0, None, None, False
    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index].upper()
            relative = tokens[index].islower()
            count = argumentCounts.get(command)
            index += 1
            if command == "Z":
                path.closeSubpath()
                continue
        if count is None or index + count > len(tokens):
            raise ValueError("Unsupported SVG preview clip path.")
        values = [float(value) for value in tokens[index:index + count]]
        index += count
        # QSvgGenerator emits mostly absolute coordinates. Those segments do
        # not need a native position query or relative-coordinate adjustment.
        if relative or command in ("H", "V"):
            current = path.currentPosition()
        if relative:
            x, y = current.x(), current.y()
            for coordinate in range(count):
                vertical = command == "V" or command != "H" and coordinate % 2 == 1
                values[coordinate] += y if vertical else x
        if command == "M":
            path.moveTo(*values)
            command = "L"
        elif command == "L":
            path.lineTo(*values)
        elif command == "H":
            path.lineTo(values[0], current.y())
        elif command == "V":
            path.lineTo(current.x(), values[0])
        elif command == "Q":
            path.quadTo(*values)
        elif command == "C":
            path.cubicTo(*values)
    # Appearance changes often retain identical passage masks. Bound both
    # native geometry and source text; a large one-off export cannot fill RAM.
    elements, sourceBytes = path.elementCount(), len(source) * 2
    if useCache and elements <= 262144 and sourceBytes <= 4 * 1024 * 1024:
        with clipPathCacheLock:
            # Another thread may have parsed this same source outside the lock.
            previous = clipPathCache.pop(key, None)
            if previous is not None:
                clipPathCacheElements -= previous.elementCount()
                clipPathCacheBytes -= sourceBytes
            while clipPathCache and (len(clipPathCache) >= 256 or clipPathCacheElements + elements > 262144
                                    or clipPathCacheBytes + sourceBytes > 4 * 1024 * 1024):
                oldKey, oldPath = clipPathCache.popitem(last = False)
                clipPathCacheElements -= oldPath.elementCount()
                clipPathCacheBytes -= len(oldKey[0]) * 2
            clipPathCache[key] = QtGui.QPainterPath(path)
            clipPathCacheElements += elements
            clipPathCacheBytes += sourceBytes
    return path


def LoadSvgData(renderer, source, nativeDispatch):
    if nativeDispatch:
        # Dispatch the native slot directly on this same owning thread, allowing
        # other Python threads to run during Qt's background SVG load.
        return QtCore.QMetaObject.invokeMethod(renderer, "load", QtCore.Qt.ConnectionType.DirectConnection,
            QtCore.Q_RETURN_ARG(bool), QtCore.Q_ARG(QtCore.QByteArray, QtCore.QByteArray(source)))
    return renderer.load(source)


class SvgPreviewRenderer(QtCore.QObject):
    @classmethod
    def FromDocument(cls, svgData, parent = None):
        if isinstance(svgData, SvgPreviewDocument) and svgData.renderer is not None:
            renderer, svgData.renderer = svgData.renderer, None
            renderer.setParent(parent)
            return renderer
        return cls(svgData, parent)

    def __init__(self, svgData, parent = None, useClipCache = True, cancelled = None, prepareOnly = False):
        super().__init__(parent)
        if isinstance(svgData, SvgPreviewDocument) and svgData.prepared is not None:
            self.LoadPrepared(svgData.prepared, cancelled)
            svgData.prepared = None
            return
        root = (svgData.root if isinstance(svgData, SvgPreviewDocument) else svgData if isinstance(svgData, ElementTree.Element)
                else ElementTree.fromstring(svgData))
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
                        shapePath = SvgClipPath(shape, useCache = useClipCache)
                        clip = Paths.Union(clip, shapePath) if not clip.isEmpty() else shapePath
                    clips[element.get("id")] = clip
                    clipSources[sourceKey] = clip
                else:
                    definitions.append(element)

        layers = []
        mappedClips = {}
        clipGeometry = {}

        # Compute descendant clip flags once. Repeated subtree scans become
        # quadratic for deeply nested groups and allocate a list at each visit.
        clippedChildren = {}
        for element in reversed(list(root.iter())):
            clippedChildren[element] = any("clip-path" in child.attrib or clippedChildren[child] for child in element)

        def Visit(element, ancestors, clipKeys, clipPaths, transform):
            if cancelled is not None and cancelled():
                raise RuntimeError("Preview result preparation cancelled.")
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
            if clippedChildren[element]:
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

        try:
            for element in root:
                if element.tag not in (namespace + "defs", namespace + "title", namespace + "desc"):
                    Visit(element, (), (), (), QtGui.QTransform())
        finally:
            # Break the recursive function's closure cycle, including its XML
            # temporaries and optional bound worker-cancellation callback.
            Visit = None
        self.layers = []
        self.layerSources = []
        layerBounds = []
        # Include cosmetic stroke fringes when querying in device pixels. Qt's
        # SVG geometry bounds alone can underestimate non-scaling strokes.
        self.devicePadding = 2
        for element in root.iter():
            width = element.get("stroke-width")
            if width is not None:
                self.devicePadding = max(self.devicePadding, float(width) * max(1, float(element.get("stroke-miterlimit", 4))) / 2 + 2)
        referencePattern = re.compile(r"url\(\s*['\"]?#([^)'\"\s]+)['\"]?\s*\)", re.IGNORECASE)
        definitionsById = {element.get("id"): element for element in definitions.iter() if element.get("id")}
        definitionOwners = {element.get("id"): owner for owner in definitions for element in owner.iter() if element.get("id")}
        globalStyles = [element for element in definitions if element.tag == namespace + "style"]
        self.sharedSource = self.sharedRenderer = None
        # Generated SVGs have unique artwork IDs and no root transparency.
        # Retain the independent-document path for inputs where grouping could
        # change ID references, CSS scope or root opacity semantics.
        identifiers = [element.get("id") for keys, paths, layer in layers for child in layer if child is not definitions
                       for element in child.iter() if element.get("id")]
        shared = (not globalStyles and len(identifiers) == len(set(identifiers))
                  and root.get("opacity", "1") in ("1", "1.0") and "opacity" not in root.get("style", ""))
        layerNames = []
        if shared:
            self.sharedSource = ElementTree.Element(root.tag, root.attrib)
            self.sharedSource.append(definitions)
            usedNames = set(identifiers) | set(definitionsById)
            if root.get("id"):
                usedNames.add(root.get("id"))
            for index, (clipKeys, clipPaths, layer) in enumerate(layers):
                name = f"plannerPreviewLayer{index}"
                while name in usedNames or name + "Ink" in usedNames:
                    name += "_"
                usedNames.update((name, name + "Ink"))
                layerNames.append(name)
                group = ElementTree.SubElement(self.sharedSource, namespace + "g", {"id": name})
                ElementTree.SubElement(group, namespace + "rect", {
                    "x": str(self.viewBox.x()), "y": str(self.viewBox.y()), "width": str(self.viewBox.width()),
                    "height": str(self.viewBox.height()), "fill": "none", "stroke": "none"})
                ink = ElementTree.SubElement(group, namespace + "g", {"id": name + "Ink"})
                ink.extend(child for child in layer if child is not definitions)
            if not prepareOnly:
                self.sharedRenderer = QtSvg.QSvgRenderer(self)
                if not LoadSvgData(self.sharedRenderer, ElementTree.tostring(self.sharedSource, encoding = "unicode").encode("utf-8"), cancelled is not None):
                    raise ValueError("Could not display the SVG preview.")
        for clipKeys, clipPaths, layer in layers:
            if cancelled is not None and cancelled():
                raise RuntimeError("Preview result preparation cancelled.")
            # Each Qt renderer needs only definitions referenced by its layer.
            # Repeating every material tile in thousands of independent XML
            # documents otherwise dominates preview construction and recoloring.
            if not shared and not globalStyles:
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
            # Build text in memory before encoding once. ElementTree's byte
            # writer otherwise encodes every small XML fragment separately for
            # each clipped layer in a detailed drawing.
            if prepareOnly:
                renderer, bounds = None, self.viewBox
            elif shared:
                renderer = SvgPreviewLayer(self.sharedRenderer, layerNames[len(self.layers)], self.viewBox)
                bounds = renderer.inkBounds
            else:
                renderer = QtSvg.QSvgRenderer(self)
                if not LoadSvgData(renderer, ElementTree.tostring(layer, encoding = "unicode").encode("utf-8"), cancelled is not None):
                    raise ValueError("Could not display the SVG preview.")
                bounds = renderer.boundsOnElement("")
            self.layers.append((clipPaths, renderer))
            self.layerSources.append(layer)
            for clip in clipPaths:
                bounds = bounds.intersected(clip.boundingRect())
            layerBounds.append(bounds.adjusted(-1e-5, -1e-5, 1e-5, 1e-5))
        self.layerNames = layerNames
        if not prepareOnly:
            self.BuildLayerIndex(layerBounds)
        # Bind each named paint once, including paints inherited from groups or
        # referenced through shared gradient/pattern definitions. Shared XML
        # nodes are mutated once, but every dependent layer must reload.
        self.paintBindings = {}
        self.paintLayers = {}
        self.paintValues = {}
        seenBindings = set()
        for layerIndex, source in enumerate([self.root] + self.layerSources):
            if cancelled is not None and cancelled():
                raise RuntimeError("Preview result preparation cancelled.")
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

    def BuildLayerIndex(self, bounds):
        sizes = sorted(max(rect.width(), rect.height()) for rect in bounds)
        self.layerIndex = BoundsIndex(sizes[len(sizes) // 2] if sizes else 1)
        for index, rect in enumerate(bounds):
            self.layerIndex.Insert((rect.left(), rect.top(), rect.right(), rect.bottom()), index)

    def PreparedData(self):
        """Private process transport: XML/bindings plus exact native path bytes."""
        paths = {}
        clips = []
        for clipPaths, renderer in self.layers:
            layer = []
            for path in clipPaths:
                identity = id(path)
                if identity not in paths:
                    encoded = QtCore.QByteArray()
                    stream = QtCore.QDataStream(encoded, QtCore.QIODevice.OpenModeFlag.WriteOnly)
                    stream << path
                    paths[identity] = bytes(encoded)
                layer.append(paths[identity])
            clips.append(tuple(layer))
        data = {name: getattr(self, name) for name in ("root", "devicePadding", "sharedSource", "layerNames",
                "layerSources", "paintBindings", "paintLayers", "paintValues")}
        data.update(viewBox = self.viewBox.getRect(), clips = clips,
                    sharedXml = ElementTree.tostring(self.sharedSource, encoding = "unicode").encode("utf-8")
                    if self.sharedSource is not None else None,
                    layerXml = [ElementTree.tostring(source, encoding = "unicode").encode("utf-8")
                                for source in self.layerSources] if self.sharedSource is None else None)
        return data

    def LoadPrepared(self, data, cancelled):
        if cancelled is not None and cancelled():
            raise RuntimeError("Preview result preparation cancelled.")
        for name in ("root", "devicePadding", "sharedSource", "layerNames", "layerSources",
                     "paintBindings", "paintLayers", "paintValues"):
            setattr(self, name, data[name])
        self.viewBox = QtCore.QRectF(*data["viewBox"])
        self.size = QtCore.QSize(math.ceil(self.viewBox.width()), math.ceil(self.viewBox.height()))
        self.sharedRenderer = None
        if data["sharedXml"] is not None:
            self.sharedRenderer = QtSvg.QSvgRenderer(self)
            if not LoadSvgData(self.sharedRenderer, data["sharedXml"], cancelled is not None):
                raise ValueError("Could not display the SVG preview.")
        self.layers, bounds, paths = [], [], {}
        for index, encodedPaths in enumerate(data["clips"]):
            if cancelled is not None and cancelled():
                raise RuntimeError("Preview result preparation cancelled.")
            clips = []
            for encoded in encodedPaths:
                if encoded not in paths:
                    path = QtGui.QPainterPath()
                    stream = QtCore.QDataStream(QtCore.QByteArray(encoded))
                    stream >> path
                    paths[encoded] = path
                clips.append(paths[encoded])
            if self.sharedRenderer is not None:
                renderer = SvgPreviewLayer(self.sharedRenderer, self.layerNames[index], self.viewBox)
                ink = renderer.inkBounds
            else:
                renderer = QtSvg.QSvgRenderer(self)
                if not LoadSvgData(renderer, data["layerXml"][index], cancelled is not None):
                    raise ValueError("Could not display the SVG preview.")
                ink = renderer.boundsOnElement("")
            self.layers.append((tuple(clips), renderer))
            for clip in clips:
                ink = ink.intersected(clip.boundingRect())
            bounds.append(ink.adjusted(-1e-5, -1e-5, 1e-5, 1e-5))
        self.BuildLayerIndex(bounds)

    def Recolor(self, colors):
        """Reuse parsed clip geometry and layer structure for palette edits."""
        paints = {role: QtGui.QColor(colors[role]).name() for role in self.paintBindings}
        changedRoles = {role for role, paint in paints.items() if paint != self.paintValues[role]}
        affectedLayers = set()
        for role in changedRoles:
            for element, attribute in self.paintBindings[role]:
                element.set(attribute, paints[role])
            affectedLayers.update(self.paintLayers.get(role, ()))
        if affectedLayers and self.sharedRenderer is not None:
            if not self.sharedRenderer.load(ElementTree.tostring(self.sharedSource, encoding = "unicode").encode("utf-8")):
                raise ValueError("Could not recolor the SVG preview.")
        elif affectedLayers:
            for layerIndex in sorted(affectedLayers):
                root = self.layerSources[layerIndex]
                clipPaths, renderer = self.layers[layerIndex]
                if not renderer.load(QtCore.QByteArray(ElementTree.tostring(root, encoding = "unicode").encode("utf-8"))):
                    raise ValueError("Could not recolor the SVG preview.")
        self.paintValues.update(paints)
        return ElementTree.tostring(self.root, encoding = "unicode", xml_declaration = True).encode("utf-8")

    def defaultSize(self):
        return self.size

    def isValid(self):
        return bool(self.layers)

    def render(self, painter, target = None):
        target = target if target is not None else QtCore.QRectF(0, 0, painter.device().width(), painter.device().height())
        transform = QtGui.QTransform().translate(target.x(), target.y()).scale(
            target.width() / self.viewBox.width(), target.height() / self.viewBox.height()).translate(
                -self.viewBox.x(), -self.viewBox.y())
        device = painter.device()
        indices = range(len(self.layers))
        inverse, invertible = (transform * painter.deviceTransform()).inverted()
        if invertible and device.width() > 0 and device.height() > 0:
            visible = QtCore.QRectF(0, 0, device.width(), device.height())
            if painter.hasClipping():
                visible = visible.intersected(painter.deviceTransform().mapRect(painter.clipBoundingRect()))
            if visible.isEmpty():
                return
            padding = self.devicePadding
            visible = inverse.mapRect(visible.adjusted(-padding, -padding, padding, padding))
            indices = self.layerIndex.Query((visible.left(), visible.top(), visible.right(), visible.bottom()))
        for index in indices:
            clipPaths, renderer = self.layers[index]
            painter.save()
            try:
                for path in clipPaths:
                    painter.setClipPath(transform.map(path), QtCore.Qt.ClipOperation.IntersectClip)
                renderer.render(painter, target)
            finally:
                painter.restore()
