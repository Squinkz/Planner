"""Bounded, shared catalog thumbnails keyed by artwork and paint dependencies."""
from collections import OrderedDict
from pathlib import Path
from PySide6 import QtCore, QtGui
from . import palette
from .furnishings import FurnishingRenderer
from .linework import defaultLineWidths
from planner_app.svg_safety import ValidateFurnishingSvg


class FurnishingThumbnailCache:
    def __init__(self, limit = 512, byteLimit = 24 * 1024 * 1024):
        self.icons = OrderedDict()
        self.limit = limit
        self.byteLimit = byteLimit
        self.byteCount = 0
        self.sources = OrderedDict()
        self.sourceBytes = 0

    def Icon(self, definition, size = 80):
        compoundIcon = bool(definition.get("graphicData") and not definition.get("icon"))
        if compoundIcon:
            source = definition["graphicData"]
        else:
            try:
                source = Path(definition["iconPath"]).read_bytes()
            except OSError:
                source = b""
        # Content keys also detect edits made in place, including same-size files
        # with unchanged timestamps, and share identical artwork across categories.
        colors = tuple(palette.themeColors[role] for role in ("icon", "fieldBackground", "missing"))
        dependencies = self.sources.get(source)
        if dependencies is None:
            try:
                root = ValidateFurnishingSvg(source)
                dependencies = (any(element.get("data-theme-outline") == "missing" for element in root.iter()),
                                any(element.tag.rsplit("}", 1)[-1] == "text" for element in root.iter()))
            except ValueError:
                dependencies = (False, False)
            if len(source) <= self.byteLimit // 3:
                self.sources[source] = dependencies
                self.sourceBytes += len(source)
                while len(self.sources) > self.limit or self.sourceBytes > self.byteLimit // 3:
                    retiredSource, _ = self.sources.popitem(last = False)
                    self.sourceBytes -= len(retiredSource)
        else:
            self.sources.move_to_end(source)
        hasMissing, hasText = dependencies
        cacheColors = (colors[0], colors[1], colors[2] if hasMissing else None)
        key = (source, definition["width"], definition["length"], compoundIcon, size,
               cacheColors, palette.labelFont if hasText else None, defaultLineWidths["furnishings"])
        cached = self.icons.get(key)
        if cached is not None:
            self.icons.move_to_end(key)
            return cached[0]
        renderer = FurnishingRenderer(source, nominalSize = (definition["width"], definition["length"]),
                                     palette = dict(zip(("outline", "background", "missing"), colors)))
        pixmap = QtGui.QPixmap(size, size)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        with QtGui.QPainter(pixmap) as painter:
            if compoundIcon:
                width, length = definition["width"], definition["length"]
            else:
                width, length = max(1, renderer.defaultSize().width()), max(1, renderer.defaultSize().height())
            scale = (size * .9 if compoundIcon else size) / max(width, length)
            viewBox = renderer.viewBoxF()
            artwork = getattr(renderer, "artworkBounds", viewBox)
            if not viewBox.isEmpty() and artwork != viewBox:
                scale = size * .9 / max(artwork.width(), artwork.height())
                target = QtCore.QRectF(size / 2 + (viewBox.x() - artwork.center().x()) * scale,
                                      size / 2 + (viewBox.y() - artwork.center().y()) * scale,
                                      viewBox.width() * scale, viewBox.height() * scale)
            else:
                target = QtCore.QRectF((size - width * scale) / 2, (size - length * scale) / 2,
                                      width * scale, length * scale)
            renderer.render(painter, target)
        icon = QtGui.QIcon(pixmap)
        cost = size * size * 4 + len(source)
        if cost <= self.byteLimit:
            self.icons[key] = (icon, cost)
            self.byteCount += cost
            while len(self.icons) > self.limit or self.byteCount > self.byteLimit:
                _, (_, retiredCost) = self.icons.popitem(last = False)
                self.byteCount -= retiredCost
        return icon
