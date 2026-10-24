"""Furnishing SVG selection colors and viewport painting."""

import math
import re
from collections import OrderedDict
from copy import deepcopy
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from PySide6 import QtCore, QtGui, QtSvg
from .linework import defaultLineWidths
from .palette import themeColors, svgBackgroundPaints, svgOutlinePaints
from .furnishing_mask import FurnishingBackgroundPath
from .object_composite import ObjectPaintDevice
from . import palette as canvasPalette
from planner_app.scene_changes import SceneDict
from planner_app.svg_safety import ValidateFurnishingSvg


# Qt's SVG image handler expects the standard xlink prefix when reading href.
ElementTree.register_namespace("xlink", "http://www.w3.org/1999/xlink")
preparedFurnishingCache = OrderedDict()


def ApplyFurnishingBounds(root):
    """Use an editor-authored rectangle or path's extent as hidden dimension bounds."""
    markers = [element for element in root.iter() if element.get("id") == "planner-bounds"]
    if not markers:
        return None
    # A marker is metadata, never visible furnishing artwork.
    for marker in markers:
        marker.set("display", "none")
        marker.set("style", marker.get("style", "") + ";display:none;fill:none;stroke:none")
    if len(markers) != 1:
        return None
    marker = markers[0]
    markerTag = marker.tag.rsplit("}", 1)[-1]
    if markerTag not in ("rect", "path"):
        return None
    parents = {child: parent for parent in root.iter() for child in parent}
    ancestors = [marker]
    while ancestors[-1] in parents:
        ancestors.append(parents[ancestors[-1]])
    # Let Qt interpret SVG units and transform lists. The isolated geometry
    # probe omits paint, CSS and visibility, including hidden Inkscape layers.
    probeRoot = probeParent = None
    for element in reversed(ancestors):
        attributes = {key: value for key, value in element.attrib.items()
                      if key in ("x", "y", "width", "height", "viewBox", "transform", "preserveAspectRatio")
                      or element is marker and key == "d"}
        probe = ElementTree.Element(element.tag, attributes)
        if probeRoot is None:
            probeRoot = probe
        else:
            probeParent.append(probe)
        probeParent = probe
    probeParent.set("id", "planner-bounds")
    probeParent.set("style", "fill:black;stroke:none")
    probeRenderer = QtSvg.QSvgRenderer(ElementTree.tostring(probeRoot))
    bounds = probeRenderer.transformForElement("planner-bounds").mapRect(probeRenderer.boundsOnElement("planner-bounds"))
    if bounds.isEmpty() or not all(math.isfinite(value) for value in (bounds.x(), bounds.y(), bounds.width(), bounds.height())):
        return None
    root.set("viewBox", f"{bounds.x()} {bounds.y()} {bounds.width()} {bounds.height()}")
    root.set("preserveAspectRatio", "none")
    root.set("data-planner-bounds", "true")
    return bounds


def FurnishingArtworkBounds(furnishing, renderer):
    """World-space paint bounds, separate from the model's physical footprint."""
    viewBox = renderer.viewBoxF()
    artworkBounds = getattr(renderer, "artworkBounds", viewBox)
    if viewBox.isEmpty():
        return QtCore.QRectF()
    center = (furnishing.firstVertex + furnishing.secondVertex) / 2
    transform = QtGui.QTransform().translate(center.x(), center.y()).rotate(furnishing.angle)
    transform.scale(furnishing.width / viewBox.width(), -furnishing.length / viewBox.height())
    transform.scale(-1 if furnishing.flipHorizontal else 1, -1 if furnishing.flipVertical else 1)
    transform.translate(-viewBox.center().x(), -viewBox.center().y())
    return transform.mapRect(artworkBounds)


def FurnishingContainsPoint(furnishing, renderer, worldPosition, tolerance):
    """Test cached SVG coverage after the viewport's cheap footprint rejection."""
    renderer = getattr(renderer, "solidRenderer", renderer)
    direction = furnishing.secondVertex - furnishing.firstVertex
    length = math.hypot(direction.x(), direction.y())
    if length <= 0 or furnishing.width <= 0:
        return False
    offset = worldPosition - (furnishing.firstVertex + furnishing.secondVertex) / 2
    localX = (offset.x() * direction.y() - offset.y() * direction.x()) / length
    localY = -(offset.x() * direction.x() + offset.y() * direction.y()) / length
    viewBox = renderer.viewBoxF()
    if not renderer.isValid() or viewBox.isEmpty():
        return abs(localX) <= furnishing.width / 2 + tolerance and abs(localY) <= length / 2 + tolerance
    coverage = getattr(renderer, "hitCoverage", None)
    fixedSize = (furnishing.width, length) if getattr(renderer, "fixedElements", None) else None
    if fixedSize != getattr(renderer, "hitCoverageSize", None):
        coverage = None
    if coverage is None:
        # Keep one small mask per shared renderer, never per placed instance.
        # Alpha captures SVG fills, strokes, holes, clips and embedded images.
        bounds = getattr(renderer, "artworkBounds", viewBox).united(viewBox)
        pixelScale = 512 / max(bounds.width(), bounds.height())
        width = max(1, math.ceil(bounds.width() * pixelScale))
        height = max(1, math.ceil(bounds.height() * pixelScale))
        image = QtGui.QImage(width, height, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        with QtGui.QPainter(image) as painter:
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            painter.scale(width / bounds.width(), height / bounds.height())
            painter.translate(-bounds.left(), -bounds.top())
            if fixedSize is not None:
                renderer.render(painter, viewBox, worldSize = fixedSize)
            else:
                renderer.render(painter, viewBox)
        image = image.convertToFormat(QtGui.QImage.Format.Format_Alpha8)
        pixels = image.constBits()
        stride = image.bytesPerLine()
        # Packed rows make a small tolerance rectangle an integer AND query,
        # avoiding per-pixel Python loops or raster copies during mouse moves.
        rows = tuple(int.from_bytes(pixels[y * stride:y * stride + width], "little") for y in range(height))
        coverage = renderer.hitCoverage = (bounds, width, height, rows)
        renderer.hitCoverageSize = fixedSize
    bounds, width, height, rows = coverage
    if furnishing.flipHorizontal:
        localX = -localX
    if furnishing.flipVertical:
        localY = -localY
    x = viewBox.center().x() + localX * viewBox.width() / furnishing.width
    y = viewBox.center().y() + localY * viewBox.height() / length
    marginX = tolerance * viewBox.width() / furnishing.width
    marginY = tolerance * viewBox.height() / length
    left = max(0, math.floor((x - marginX - bounds.left()) * width / bounds.width()))
    right = min(width - 1, math.floor((x + marginX - bounds.left()) * width / bounds.width()))
    top = max(0, math.floor((y - marginY - bounds.top()) * height / bounds.height()))
    bottom = min(height - 1, math.floor((y + marginY - bounds.top()) * height / bounds.height()))
    if left > right or top > bottom:
        return False
    mask = ((1 << ((right - left + 1) * 8)) - 1) << (left * 8)
    return any(rows[index] & mask for index in range(top, bottom + 1))


def CompoundFurnishingSvg(components):
    from planner_app.furnishing_limits import FurnishingExpansionSizes
    FurnishingExpansionSizes([{"components": components}])
    corners = []
    for child in components:
        angle = math.radians(child["angle"])
        cosine, sine = math.cos(angle), math.sin(angle)
        for x in (-child["width"] / 2, child["width"] / 2):
            for y in (-child["length"] / 2, child["length"] / 2):
                corners.append((child["x"] + x * cosine - y * sine,
                                child["y"] + x * sine + y * cosine))
    left, right = min(x for x, y in corners), max(x for x, y in corners)
    bottom, top = min(y for x, y in corners), max(y for x, y in corners)
    width, length = right - left, top - bottom
    namespace = "{http://www.w3.org/2000/svg}"
    root = ElementTree.Element(namespace + "svg", {"viewBox": f"{left} {-top} {width} {length}",
                                                   "preserveAspectRatio": "none"})
    sourceBytes = elementCount = 0
    for index, child in sorted(enumerate(components), key = lambda entry: (entry[1]["zIndex"], entry[0])):
        definition = child["definition"]
        source = definition.get("graphicData") or Path(definition["imagePath"]).read_bytes()
        sourceBytes += len(source)
        if sourceBytes > 8 * 1024 * 1024:
            raise ValueError("Compound SVG source exceeds 8 MiB.")
        graphic = ValidateFurnishingSvg(source)
        elementCount += sum(1 for element in graphic.iter())
        if elementCount > 50000:
            raise ValueError("Compound SVG exceeds 50,000 elements.")
        ApplyFurnishingBounds(graphic)
        for element in graphic.iter():
            if element.get("id") == "planner-fixed" or element.get("id", "").startswith("planner-fixed-"):
                element.set("data-planner-fixed", "true")
        # Repeated SVGs must not share gradient, clip or symbol identifiers.
        identifiers = {element.get("id"): f"child{index}_{element.get('id')}"
                       for element in graphic.iter() if element.get("id")}
        classes = {name: f"child{index}_{name}" for element in graphic.iter()
                   for name in element.get("class", "").split()}
        for element in graphic.iter():
            for attribute, value in list(element.attrib.items()):
                if attribute == "id":
                    element.set(attribute, identifiers[value])
                elif attribute == "class":
                    element.set(attribute, " ".join(classes[name] for name in value.split()))
                else:
                    for original, replacement in identifiers.items():
                        value = value.replace(f"url(#{original})", f"url(#{replacement})")
                        if attribute.rsplit("}", 1)[-1] == "href" and value == "#" + original:
                            value = "#" + replacement
                    element.set(attribute, value)
            if element.tag.rsplit("}", 1)[-1] == "style" and element.text:
                for original, replacement in identifiers.items():
                    element.text = re.sub(r"#" + re.escape(original) + r"(?![\w-])", "#" + replacement, element.text)
                for original, replacement in classes.items():
                    element.text = re.sub(r"\." + re.escape(original) + r"(?![\w-])", "." + replacement, element.text)
        viewBox = [float(value) for value in graphic.get("viewBox", "").replace(",", " ").split()]
        if len(viewBox) != 4:
            viewBox = [0, 0, float(graphic.get("width", child["width"])),
                       float(graphic.get("height", child["length"]))]
        if viewBox[2] <= 0 or viewBox[3] <= 0:
            raise ValueError("A furnishing SVG needs a positive viewBox")
        group = ElementTree.SubElement(root, namespace + "g", {
            "transform": f"translate({child['x']} {-child['y']}) rotate({-child['angle']})"})
        if child.get("flipHorizontal") or child.get("flipVertical"):
            group = ElementTree.SubElement(group, namespace + "g", {"transform":
                f"scale({-1 if child.get('flipHorizontal') else 1} {-1 if child.get('flipVertical') else 1})"})
        if child.get("fixedSize", False):
            group = ElementTree.SubElement(group, namespace + "g", {
                "data-planner-fixed": "true", "data-planner-fixed-anchor": "0 0"})
        mapped = ElementTree.SubElement(group, namespace + "g", {"transform":
            f"translate({-child['width'] / 2} {-child['length'] / 2}) "
            f"scale({child['width'] / viewBox[2]} {child['length'] / viewBox[3]}) "
            f"translate({-viewBox[0]} {-viewBox[1]})"})
        # Qt SVG does not render nested SVG viewports reliably. Flatten each
        # viewport into a transformed group while retaining its vector strokes.
        graphic.tag = namespace + "g"
        graphic.set("data-furnishing-viewbox", " ".join(str(value) for value in viewBox))
        if definition.get("width") and definition.get("length"):
            graphic.set("data-furnishing-size", f"{definition['width']} {definition['length']}")
        for attribute in ("viewBox", "x", "y", "width", "height", "preserveAspectRatio"):
            graphic.attrib.pop(attribute, None)
        mapped.append(graphic)
    source = ElementTree.tostring(root)
    # Flattening adds transforms, IDs and wrapper elements. The combined result
    # must obey the same limits as an imported asset before it can be saved.
    ValidateFurnishingSvg(source)
    return source, width, length, ((left + right) / 2, (bottom + top) / 2)


class FurnishingSvgRenderer(QtSvg.QSvgRenderer):
    """Preserve lettering anchors and physical sizes of marked SVG details."""
    def __init__(self, root, prepared = None):
        if prepared is not None:
            lettering, self.letteringFont, customBounds, fixedElements = prepared
            self.lettering = list(lettering)
            self.fixedElements = list(fixedElements)
            self.letteringRoot = root if lettering or fixedElements else None
            self.letteringVariants = OrderedDict()
            super().__init__(ElementTree.tostring(root))
            self.artworkBounds = self.boundsOnElement("").united(self.viewBoxF()) if customBounds else self.viewBoxF()
            return
        # Qt resolves image links even in hidden Inkscape tracing layers. Omit
        # those images from the in-memory graphic; keep the editable source intact.
        stack = [(None, root, False)]
        while stack:
            parent, element, hidden = stack.pop()
            hidden = (hidden or element.get("display", "").strip().lower() == "none"
                      or bool(re.search(r"(?:^|;)\s*display\s*:\s*none\s*(?:;|$)", element.get("style", ""), re.IGNORECASE)))
            if hidden and element.tag.rsplit("}", 1)[-1] == "image" and parent is not None:
                parent.remove(element)
            else:
                stack.extend((element, child, hidden) for child in element)
        ApplyFurnishingBounds(root)
        customBounds = any(element.get("data-planner-bounds") == "true" for element in root.iter())
        self.letteringRoot = None
        self.letteringVariants = OrderedDict()
        self.lettering = []
        self.fixedElements = []
        if not any(element.tag.rsplit("}", 1)[-1] == "text" for element in root.iter()):
            super().__init__(ElementTree.tostring(root))
            self.artworkBounds = self.boundsOnElement("").united(self.viewBoxF()) if customBounds else self.viewBoxF()
            self.PrepareFixedElements(root)
            return
        self.letteringRoot = root
        namespace = "{http://www.w3.org/2000/svg}"
        textElements = []
        identifiers = {element.get("id") for element in root.iter()}
        viewBox = [float(value) for value in root.get("viewBox", "").replace(",", " ").split()]
        if len(viewBox) != 4:
            sourceRenderer = QtSvg.QSvgRenderer(ElementTree.tostring(root))
            sourceBounds = sourceRenderer.viewBoxF()
            viewBox = [sourceBounds.x(), sourceBounds.y(), sourceBounds.width(), sourceBounds.height()]
        rootScope = QtCore.QRectF(*viewBox)
        parents = {child: parent for parent in root.iter() for child in parent}
        rootSize = root.get("data-furnishing-size")
        stack = [(root, None, rootScope, rootSize)]
        while stack:
            element, scopeId, scopeBounds, scopeSize = stack.pop()
            tag = element.tag.rsplit("}", 1)[-1]
            if tag in ("defs", "metadata", "namedview"):
                continue
            if element.get("id") == "planner-fixed" or element.get("id", "").startswith("planner-fixed-") or element.get("data-planner-fixed") == "true":
                continue
            if element.get("data-furnishing-viewbox"):
                scopeBounds = QtCore.QRectF(*[float(value) for value in element.get("data-furnishing-viewbox").split()])
                scopeSize = element.get("data-furnishing-size")
                scopeId = "plannerLetterScope"
                while scopeId in identifiers:
                    scopeId += "_"
                identifiers.add(scopeId)
                # An invisible anchor exposes all ancestor transforms through Qt.
                ElementTree.SubElement(element, namespace + "rect", {
                    "id": scopeId, "x": str(scopeBounds.x()), "y": str(scopeBounds.y()),
                    "width": str(scopeBounds.width()), "height": str(scopeBounds.height()),
                    "style": "fill:none;stroke:none;opacity:0"})
            if tag == "text":
                textId = element.get("id")
                if not textId:
                    textId = "plannerLettering"
                    while textId in identifiers:
                        textId += "_"
                    identifiers.add(textId)
                    element.set("id", textId)
                transformId = None
                if element.get("transform"):
                    transformId = "plannerLetterTransform"
                    while transformId in identifiers:
                        transformId += "_"
                    identifiers.add(transformId)
                    probe = ElementTree.SubElement(parents[element], namespace + "g", {"transform": element.get("transform")})
                    ElementTree.SubElement(probe, namespace + "rect", {
                        "id": transformId, "width": "1", "height": "1", "style": "fill:none;stroke:none;opacity:0"})
                textElements.append((textId, scopeId, scopeBounds, scopeSize, transformId))
            else:
                stack.extend((child, scopeId, scopeBounds, scopeSize) for child in reversed(list(element)))
        super().__init__(ElementTree.tostring(root))
        self.artworkBounds = self.boundsOnElement("").united(self.viewBoxF()) if customBounds else self.viewBoxF()
        for textId, scopeId, scopeBounds, scopeSize, transformId in textElements:
            textBounds = self.boundsOnElement(textId)
            if not textBounds.isEmpty():
                parentTransform = self.transformForElement(textId)
                parentInverse, parentValid = parentTransform.inverted()
                ownTransform = self.transformForElement(transformId) * parentInverse if transformId and parentValid else QtGui.QTransform()
                ownInverse, ownValid = ownTransform.inverted()
                if not ownValid:
                    continue
                scopeTransform = self.transformForElement(scopeId) if scopeId else QtGui.QTransform()
                scopeInverse, scopeValid = scopeTransform.inverted()
                if not scopeValid:
                    continue
                authored = ownTransform * parentTransform * scopeInverse
                largestScale = (math.hypot(authored.m11() + authored.m22(), authored.m12() - authored.m21())
                                + math.hypot(authored.m11() - authored.m22(), authored.m12() + authored.m21())) / 2
                ownScale = abs(authored.determinant()) / max(largestScale, 1e-12)
                # Preserve the existing screen cap for a 600-mm appliance drawn
                # in 100 units. Convert every component's coordinates to that
                # convention once, including transforms inside its SVG scope.
                if scopeSize:
                    nominalWidth, nominalLength = [float(value) for value in scopeSize.split()]
                    ownScale *= min(nominalWidth / scopeBounds.width(), nominalLength / scopeBounds.height()) / 6
                else:
                    ownScale *= 100 / min(scopeBounds.width(), scopeBounds.height())
                textBounds = self.LetteringBounds(textId, ownInverse)
                self.lettering.append((textId, textBounds, parentTransform,
                    scopeTransform, scopeBounds, ownTransform, ownScale, textBounds.center()))
        # Measure the authored anchors before replacing the font. A different
        # family's glyph metrics must not move lettering out of its feature.
        self.letteringFont = canvasPalette.labelFont
        family = self.letteringFont.replace("\\", "\\\\").replace('"', '\\"')
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] in ("text", "tspan"):
                element.set("font-family", self.letteringFont)
                style = re.sub(r"(?:^|;)\s*(?:font-family|-inkscape-font-specification)\s*:[^;]*", "", element.get("style", ""))
                element.set("style", style.rstrip(";") + f';font-family:"{family}"')
        self.load(ElementTree.tostring(root))
        self.lettering = [(textId, self.LetteringBounds(textId, ownTransform.inverted()[0]), parentTransform,
                          scopeTransform, scopeBounds, ownTransform, ownScale, anchor)
                         for textId, textBounds, parentTransform, scopeTransform, scopeBounds, ownTransform, ownScale, anchor in self.lettering]
        self.PrepareFixedElements(root)

    def PrepareFixedElements(self, root):
        """Measure midpoint anchors and component scopes once per SVG template."""
        if not any(element.get("id") == "planner-fixed" or element.get("id", "").startswith("planner-fixed-") or element.get("data-planner-fixed") == "true"
                   for element in root.iter()):
            return
        namespace = "{http://www.w3.org/2000/svg}"
        identifiers = {element.get("id") for element in root.iter()}
        parents = {child: parent for parent in root.iter() for child in parent}
        pending = [(root, None, self.viewBoxF(), root.get("data-furnishing-size"))]
        targets = []
        while pending:
            element, scopeId, scopeBounds, scopeSize = pending.pop()
            if element.tag.rsplit("}", 1)[-1] in ("defs", "metadata", "namedview"):
                continue
            if element.get("data-furnishing-viewbox"):
                scopeBounds = QtCore.QRectF(*[float(value) for value in element.get("data-furnishing-viewbox").split()])
                scopeSize = element.get("data-furnishing-size")
                scopeId = "plannerFixedScope"
                while scopeId in identifiers:
                    scopeId += "_"
                identifiers.add(scopeId)
                ElementTree.SubElement(element, namespace + "rect", {
                    "id": scopeId, "x": str(scopeBounds.x()), "y": str(scopeBounds.y()),
                    "width": str(scopeBounds.width()), "height": str(scopeBounds.height()),
                    "style": "fill:none;stroke:none;opacity:0"})
            if element in parents and (element.get("id") == "planner-fixed" or element.get("id", "").startswith("planner-fixed-") or element.get("data-planner-fixed") == "true"):
                wrapperId = "plannerFixedTransform"
                while wrapperId in identifiers:
                    wrapperId += "_"
                identifiers.add(wrapperId)
                parent = parents[element]
                wrapper = ElementTree.Element(namespace + "g", {"id": wrapperId})
                parent.insert(list(parent).index(element), wrapper)
                parent.remove(element)
                wrapper.append(element)
                targets.append((wrapperId, scopeId, scopeBounds, scopeSize, element.get("data-planner-fixed-anchor")))
            else:
                pending.extend((child, scopeId, scopeBounds, scopeSize) for child in reversed(list(element)))
        self.load(ElementTree.tostring(root))
        for wrapperId, scopeId, scopeBounds, scopeSize, fixedAnchor in targets:
            bounds = self.boundsOnElement(wrapperId)
            if bounds.isEmpty() or not scopeSize:
                continue
            nominalWidth, nominalLength = [float(value) for value in scopeSize.split()]
            anchor = QtCore.QPointF(*[float(value) for value in fixedAnchor.split()]) if fixedAnchor else bounds.center()
            self.fixedElements.append((wrapperId, anchor, self.transformForElement(wrapperId),
                                       self.transformForElement(scopeId) if scopeId else QtGui.QTransform(),
                                       nominalWidth / scopeBounds.width(), nominalLength / scopeBounds.height()))
        if self.fixedElements:
            self.letteringRoot = root

    def LetteringBounds(self, textId, ownInverse):
        """Measure visible glyphs independently of a font's ascent/descent box."""
        textBounds = self.boundsOnElement(textId)
        device = ObjectPaintDevice(self.defaultSize(), "#ffffff")
        with QtGui.QPainter(device) as painter:
            QtSvg.QSvgRenderer.render(self, painter, textId, textBounds)
        inkBounds = QtCore.QRectF()
        for path, pen, brush, transform, opacity, clip, mask, hints, brushOrigin in device.engine.commands:
            if not isinstance(path, tuple) and opacity > 0:
                inkBounds = inkBounds.united((transform * ownInverse).map(path).boundingRect())
        return inkBounds if not inkBounds.isEmpty() else ownInverse.mapRect(textBounds)

    def render(self, painter, *arguments, worldSize = None):
        if isinstance(painter.device(), QtSvg.QSvgGenerator):
            # Keep fixed stroke widths while rendering at the chosen export scale,
            # then bake those widths into ordinary vector geometry.
            size = painter.device().size()
            device = ObjectPaintDevice(size, themeColors["canvas"])
            device.engine.captureBackground = False
            with QtGui.QPainter(device) as recorder:
                recorder.setWorldTransform(painter.worldTransform())
                recorder.setFont(painter.font())
                recorder.setRenderHints(painter.renderHints())
                recorder.setOpacity(painter.opacity())
                self.render(recorder, *arguments, worldSize = worldSize)
            painter.save()
            try:
                painter.resetTransform()
                device.engine.Replay(painter, QtCore.QRectF(0, 0, size.width(), size.height()))
            finally:
                painter.restore()
            return
        if not (self.lettering or self.fixedElements and worldSize) or len(arguments) != 1 or not isinstance(arguments[0], QtCore.QRectF):
            return super().render(painter, *arguments)
        bounds = arguments[0]
        viewBox = self.viewBoxF()
        if bounds.isEmpty() or viewBox.isEmpty():
            return super().render(painter, *arguments)
        world = painter.worldTransform()
        worldLinear = QtGui.QTransform(world.m11(), world.m12(), world.m21(), world.m22(), 0, 0)
        rotation, worldValid = worldLinear.inverted()
        if not worldValid:
            return super().render(painter, *arguments)
        key = (bounds.width(), bounds.height(), world.m11(), world.m12(), world.m21(), world.m22(),
               tuple(worldSize) if worldSize is not None else None)
        variant = self.letteringVariants.get(key)
        if variant is None:
            root = deepcopy(self.letteringRoot)
            elements = {element.get("id"): element for element in root.iter() if element.get("id")}
            scale = QtGui.QTransform.fromScale(bounds.width() / viewBox.width(), bounds.height() / viewBox.height())
            if worldSize is not None:
                physicalScale = QtGui.QTransform.fromScale(worldSize[0] / viewBox.width(), worldSize[1] / viewBox.height())
                for wrapperId, anchor, parentTransform, scopeTransform, nominalX, nominalY in self.fixedElements:
                    parentPhysical = parentTransform * physicalScale
                    parentInverse, parentValid = parentPhysical.inverted()
                    scopeInverse, scopeValid = scopeTransform.inverted()
                    scopePhysical = scopeTransform * physicalScale
                    xLength = math.hypot(scopePhysical.m11(), scopePhysical.m12())
                    yLength = math.hypot(scopePhysical.m21(), scopePhysical.m22())
                    if not parentValid or not scopeValid or min(xLength, yLength) <= 0:
                        continue
                    relative = QtGui.QTransform.fromScale(1 / nominalX, 1 / nominalY) * scopePhysical
                    largestScale = (math.hypot(relative.m11() + relative.m22(), relative.m12() - relative.m21())
                                    + math.hypot(relative.m11() - relative.m22(), relative.m12() + relative.m21())) / 2
                    shrink = min(1.0, abs(relative.determinant()) / max(largestScale, 1e-12))
                    cosine, sine = scopePhysical.m11() / xLength, scopePhysical.m12() / xLength
                    facing = -1 if scopePhysical.determinant() < 0 else 1
                    desiredScope = QtGui.QTransform(cosine * nominalX * shrink, sine * nominalX * shrink,
                        -sine * nominalY * shrink * facing, cosine * nominalY * shrink * facing, 0, 0)
                    desired = parentTransform * scopeInverse * desiredScope
                    offset = parentPhysical.map(anchor) - desired.map(anchor)
                    desired = QtGui.QTransform(desired.m11(), desired.m12(), desired.m21(), desired.m22(),
                                              desired.dx() + offset.x(), desired.dy() + offset.y())
                    correction = desired * parentInverse
                    elements[wrapperId].set("transform",
                        f"matrix({correction.m11()} {correction.m12()} {correction.m21()} {correction.m22()} {correction.dx()} {correction.dy()})")
            for textId, textBounds, parentTransform, scopeTransform, scopeBounds, ownTransform, ownScale, anchor in self.lettering:
                parentTotal = parentTransform * scale
                scopeTotal = scopeTransform * scale
                parentInverse, parentValid = parentTotal.inverted()
                scopeInverse, scopeValid = scopeTotal.inverted()
                if not parentValid or not scopeValid:
                    continue
                # Cancel the painter's orientation as well as SVG component
                # transforms, keeping lettering horizontal in the final drawing.
                intoScope = rotation * scopeInverse
                extentX = extentY = 0
                for x in (-textBounds.width() / 2, textBounds.width() / 2):
                    for y in (-textBounds.height() / 2, textBounds.height() / 2):
                        corner = intoScope.map(QtCore.QPointF(x, y)) - intoScope.map(QtCore.QPointF())
                        extentX = max(extentX, abs(corner.x()))
                        extentY = max(extentY, abs(corner.y()))
                # Limit the text to its authored proportion along the least-scaled
                # direction. This also shrinks it with zoom before it fills the object.
                authoredTotal = ownTransform * parentTotal * worldLinear
                largestScale = (math.hypot(authoredTotal.m11() + authoredTotal.m22(), authoredTotal.m12() - authoredTotal.m21())
                                + math.hypot(authoredTotal.m11() - authoredTotal.m22(), authoredTotal.m12() + authoredTotal.m21())) / 2
                authoredScale = abs(authoredTotal.determinant()) / max(largestScale, 1e-12)
                # Five-percent padding keeps glyphs clear of the object's outline.
                textScale = min(ownScale, authoredScale, scopeBounds.width() * .45 / max(extentX, 1e-12),
                                   scopeBounds.height() * .45 / max(extentY, 1e-12))
                uniform = QtGui.QTransform(rotation.m11() * textScale, rotation.m12() * textScale,
                    rotation.m21() * textScale, rotation.m22() * textScale, 0, 0)
                # Keep the authored glyph anchor (e.g. a washer drum center),
                # even when zoom compensation changes text size/orientation.
                targetCenter = (ownTransform * parentTotal).map(anchor)
                offset = targetCenter - uniform.map(textBounds.center())
                uniform = QtGui.QTransform(uniform.m11(), uniform.m12(), uniform.m21(), uniform.m22(), offset.x(), offset.y())
                correction = uniform * parentInverse
                element = elements[textId]
                element.set("transform",
                    f"matrix({correction.m11()} {correction.m12()} {correction.m21()} {correction.m22()} {correction.dx()} {correction.dy()})")
            variant = QtSvg.QSvgRenderer(ElementTree.tostring(root))
            self.letteringVariants[key] = variant
            while len(self.letteringVariants) > 16:
                self.letteringVariants.popitem(last = False)
        else:
            self.letteringVariants.move_to_end(key)
        return variant.render(painter, bounds)


def NormalizeFurnishingDashes(root, lineWidth):
    """Keep dash/width ratios when replacing authored widths with cosmetic ink."""
    if lineWidth == 0:
        return
    numberPattern = re.compile(r"([-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?)([a-zA-Z%]*)")
    unitScales = {"": 1, "px": 1, "mm": 96 / 25.4, "cm": 96 / 2.54, "in": 96,
                  "pt": 96 / 72, "pc": 16, "q": 96 / 101.6}
    pending = [(root, {"stroke-width": "1", "stroke-dasharray": "none", "stroke-dashoffset": "0"})]
    while pending:
        element, inherited = pending.pop()
        authored = dict(inherited)
        authored.update((name, element.get(name)) for name in inherited if element.get(name) not in (None, "inherit"))
        style = element.get("style", "")
        declarations = dict((name.strip().lower(), value.strip()) for name, value in
                            re.findall(r"([\w-]+)\s*:\s*([^;]+)", style))
        authored.update((name, declarations[name]) for name in inherited
                        if name in declarations and declarations[name] != "inherit")
        pending.extend((child, authored) for child in element)
        # CSS blocks keep declarations together so their authored width is read
        # before the existing width replacement below changes it.
        styles = [(style, False)]
        if element.tag.rsplit("}", 1)[-1] == "style" and element.text:
            styles = [(match.group(0), True) for match in re.finditer(r"\{[^{}]*\}", element.text)]
        for sourceStyle, cssBlock in styles:
            values = dict(authored)
            if cssBlock:
                values.update((name.strip().lower(), value.strip()) for name, value in
                              re.findall(r"([\w-]+)\s*:\s*([^;}]+)", sourceStyle))
            widthMatch = numberPattern.fullmatch(values["stroke-width"].strip())
            if widthMatch is None or widthMatch.group(2).lower() not in unitScales:
                continue
            width = float(widthMatch.group(1)) * unitScales[widthMatch.group(2).lower()]
            if not math.isfinite(width) or width <= 0:
                continue
            ratio = lineWidth / width
            for name in ("stroke-dasharray", "stroke-dashoffset"):
                value = values[name]
                if value in ("none", "inherit"):
                    continue
                matches = list(numberPattern.finditer(value))
                if not matches or numberPattern.sub("", value).strip(" ,\t\r\n"):
                    continue
                scaled = numberPattern.sub(lambda match: f"{float(match.group(1)) * ratio:.12g}" + match.group(2), value)
                if cssBlock:
                    updated = re.sub(r"(\b" + name + r"\s*:\s*)[^;}]+", lambda match: match.group(1) + scaled, sourceStyle)
                    element.text = element.text.replace(sourceStyle, updated)
                    sourceStyle = updated
                elif values["stroke-dasharray"] != "none":
                    # Materialize inherited patterns on children, since a child
                    # may override width without redeclaring its dash pattern.
                    element.set(name, scaled)
                    style = re.sub(r"(\b" + name + r"\s*:\s*)[^;]+", lambda match: match.group(1) + scaled, style)
            if not cssBlock and style:
                element.set("style", style)


def FurnishingRenderer(imagePath, selectionColor = None, palette = None, lineWidth = None, solidBackground = True, nominalSize = None, excludeErrors = False):
    """Map neutral SVG paints once, retaining geometry, transparency and strokes."""
    if palette is None:
        palette = {"outline": themeColors["objectOutline"], "background": themeColors["canvas"], "missing": themeColors["missing"]}
    try:
        source = imagePath if isinstance(imagePath, bytes) else Path(imagePath).read_bytes()
    except OSError:
        return QtSvg.QSvgRenderer(b"")
    lineWidth = defaultLineWidths["furnishings"] if lineWidth is None else lineWidth
    cacheKey = (source, canvasPalette.labelFont, tuple(nominalSize) if nominalSize is not None else None, lineWidth)
    cached = preparedFurnishingCache.pop(cacheKey, None)
    if cached is None:
        try:
            root = ValidateFurnishingSvg(source)
        except ValueError:
            return QtSvg.QSvgRenderer(b"")
        # Older saved Null graphics marked only their text. Promote that
        # semantic role to the whole placeholder, without tinting its siblings
        # when the graphic has been flattened into a compound.
        if (any(element.get("data-theme-outline") == "missing" for element in root.iter())
                and not any(element.get("data-furnishing-viewbox") for element in root.iter())):
            root.set("data-theme-outline", "missing")
        for element in root.iter():
            if element.get("data-furnishing-viewbox"):
                descendants = list(element.iter())[1:]
                if (any(child.get("data-theme-outline") == "missing" for child in descendants)
                        and not any(child.get("data-furnishing-viewbox") for child in descendants)):
                    element.set("data-theme-outline", "missing")
        if nominalSize is not None:
            root.set("data-furnishing-size", f"{nominalSize[0]} {nominalSize[1]}")
        NormalizeFurnishingDashes(root, lineWidth)
        template = FurnishingSvgRenderer(root)
        prepared = (tuple(template.lettering), template.letteringFont if template.lettering else canvasPalette.labelFont,
                    any(element.get("data-planner-bounds") == "true" for element in root.iter()), tuple(template.fixedElements))
        cached = (root, prepared)
    preparedFurnishingCache[cacheKey] = cached
    # Retain parsed artwork and font measurements, never unbounded color variants.
    while len(preparedFurnishingCache) > 128 or sum(len(key[0]) for key in preparedFurnishingCache) > 8 * 1024 * 1024:
        preparedFurnishingCache.popitem(last = False)
    root = deepcopy(cached[0])
    prepared = cached[1]
    if excludeErrors:
        for element in root.iter():
            if element.get("data-theme-outline") == "missing":
                # Qt SVG can let a child's display:inline defeat a hidden
                # flattened group. Suppress each descendant explicitly.
                for child in element.iter():
                    child.set("display", "none")
                    child.set("style", child.get("style", "") + ";display:none")
    transparentColors = {"none", "transparent", "inherit"}
    paintPattern = re.compile(r"(\b(?:fill|stroke|color|stop-color)\s*:\s*)([^;}]+)", re.IGNORECASE)
    widthPattern = re.compile(r"(\bstroke-width\s*:\s*)([^;}]+)", re.IGNORECASE)
    strokeWidth = str(lineWidth)

    def Recolor(paint, missing = False):
        color = paint.strip().lower().replace(" ", "")
        if color in transparentColors or color.startswith("url("):
            return paint
        if color in svgBackgroundPaints:
            return palette["background"] if solidBackground else "none"
        if missing and color in svgOutlinePaints:
            return palette["missing"]
        if selectionColor is not None:
            return selectionColor
        if color in svgOutlinePaints:
            return palette["missing"] if missing else palette["outline"]
        return paint

    pending = [(root, False)]
    while pending:
        element, missing = pending.pop()
        missing = missing or element.get("data-theme-outline") == "missing"
        pending.extend((child, missing) for child in reversed(list(element)))
        if element.get("stroke-width") is not None:
            element.set("stroke-width", strokeWidth)
        if element.tag.rsplit("}", 1)[-1] in ("path", "rect", "circle", "ellipse", "polygon", "polyline", "line", "use"):
            element.set("vector-effect", "non-scaling-stroke")
        for attribute in ("fill", "stroke", "color", "stop-color"):
            paint = element.get(attribute)
            if paint is not None:
                element.set(attribute, "none" if attribute == "stroke" and lineWidth == 0 else Recolor(paint, missing))
        # Editors may put paint declarations in inline styles or CSS classes.
        styleElement = element.tag.rsplit("}", 1)[-1] == "style"
        style = element.text if styleElement else element.get("style")
        if style:
            style = widthPattern.sub(lambda match: match.group(1) + strokeWidth, style)
            style = paintPattern.sub(
                lambda match: match.group(1) + ("none" if match.group(1).strip().lower().startswith("stroke:") and lineWidth == 0 else Recolor(match.group(2), missing)), style)
            if styleElement:
                element.text = style
            else:
                element.set("style", style)
    # SVG's implicit black fill/currentColor also represent foreground ink.
    foreground = palette["missing"] if root.get("data-theme-outline") == "missing" else selectionColor or palette["outline"]
    root.set("fill", root.get("fill", foreground))
    root.set("color", root.get("color", foreground))
    root.set("stroke-width", strokeWidth)
    renderer = FurnishingSvgRenderer(root, prepared = prepared)
    if not solidBackground:
        # Capture the original background shapes, including curves and SVG
        # transforms. Bounding rectangles would incorrectly hide nearby ink.
        renderer.solidRenderer = FurnishingRenderer(imagePath, selectionColor = selectionColor, palette = palette, lineWidth = lineWidth, nominalSize = nominalSize, excludeErrors = excludeErrors)
        maskPalette = {"outline": "#000000", "background": "#ffffff", "missing": "#000000"}
        maskRenderer = FurnishingRenderer(imagePath, palette = maskPalette, lineWidth = 0, nominalSize = nominalSize, excludeErrors = excludeErrors)
        renderer.backgroundPath = FurnishingBackgroundPath(maskRenderer)
    return renderer


class FurnishingRendererMap(SceneDict):
    """Realize scene artwork on demand, without parsing the unused catalog."""
    def __init__(self, definitions, selected = False, lineWidth = None, solidBackground = True, colors = None, selectionColor = None, excludeErrors = False):
        super().__init__({}, lambda: None)
        self.definitions = definitions
        self.selected = selected
        self.lineWidth = lineWidth
        self.solidBackground = solidBackground
        self.excludeErrors = excludeErrors
        self.colors = dict(colors) if colors is not None else {
            "outline": themeColors["objectOutline"], "background": themeColors["canvas"], "missing": themeColors["missing"]}
        self.selectionColor = selectionColor if selectionColor is not None else themeColors["selectionOutline"] if selected else None

    def __missing__(self, key):
        definition = self.definitions[key]
        renderer = FurnishingRenderer(definition.get("graphicData") or definition["imagePath"],
            selectionColor = self.selectionColor, palette = self.colors, lineWidth = self.lineWidth,
            solidBackground = self.solidBackground, nominalSize = (definition["width"], definition["length"]), excludeErrors = self.excludeErrors)
        # Populating a render cache does not change scene appearance or revisions.
        dict.__setitem__(self, key, renderer)
        return renderer

    def get(self, key, default = None):
        try:
            return self[key]
        except KeyError:
            return default

    def Copy(self, changed = None, solidBackground = None, excludeErrors = None):
        solid = self.solidBackground if solidBackground is None else solidBackground
        exclude = self.excludeErrors if excludeErrors is None else excludeErrors
        result = FurnishingRendererMap(self.definitions, selected = self.selected, lineWidth = self.lineWidth,
            solidBackground = solid, colors = self.colors, selectionColor = self.selectionColor, excludeErrors = exclude)
        if changed is not None:
            result.changed = changed
        for key, renderer in self.items():
            if exclude != self.excludeErrors:
                continue
            if solid == self.solidBackground:
                dict.__setitem__(result, key, renderer)
            elif solid:
                dict.__setitem__(result, key, getattr(renderer, "solidRenderer", renderer))
        return result


def SelectedFurnishingRenderer(imagePath, selectionColor = None, lineWidth = None, solidBackground = True, nominalSize = None):
    """Retain the existing selection API using the shared theme mapping."""
    return FurnishingRenderer(imagePath, selectionColor = themeColors["selectionOutline"] if selectionColor is None else selectionColor, lineWidth = lineWidth, solidBackground = solidBackground, nominalSize = nominalSize)


def DrawFurnishing(painter, furnishing, first, second, pixelsPerMillimeter, renderer, selected = False, invalid = False,
                   selectionColor = None, drawBounds = True):
    selectionColor = themeColors["selectionOutline"] if selectionColor is None else selectionColor
    length = QtCore.QLineF(first, second).length()
    direction = first - second
    if length <= 0:
        return
    painter.save()
    center = (first + second) / 2
    painter.translate(center)
    painter.rotate(math.degrees(math.atan2(direction.y(), direction.x())) - 90)
    bounds = QtCore.QRectF(-furnishing.width * pixelsPerMillimeter / 2, -length / 2,
                          furnishing.width * pixelsPerMillimeter, length)
    if invalid:
        painter.setOpacity(.4)
    painter.save()
    painter.scale(-1 if getattr(furnishing, "flipHorizontal", False) else 1,
                  -1 if getattr(furnishing, "flipVertical", False) else 1)
    if getattr(renderer, "fixedElements", None):
        renderer.render(painter, bounds, worldSize = (furnishing.width, furnishing.length))
    else:
        renderer.render(painter, bounds)
    painter.restore()
    if drawBounds and (selected or invalid):
        painter.setPen(QtGui.QPen(QtGui.QColor(themeColors["invalidOutline"] if invalid else selectionColor), 1.5))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawRect(bounds)
    painter.restore()
