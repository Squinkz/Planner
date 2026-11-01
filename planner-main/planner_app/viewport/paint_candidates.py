"""Current-scene world ink bounds for ordered editor paint culling."""
import math
from PySide6 import QtCore, QtGui
from planner_app.models import Furnishing, Label
from planner_app.graphics import palette
from planner_app.graphics.furnishings import FurnishingArtworkBounds
from .spatial_index import BoundsIndex


class PaintCandidatesMixin:
    def PaintObjectBounds(self, obj):
        if type(obj) is Label:
            font, width, height, ink, lines = obj.TextLayout()
            center = (obj.firstVertex + obj.secondVertex) / 2
            transform = QtGui.QTransform().translate(center.x(), center.y()).rotate(obj.angle)
            transform.scale(obj.width / width, -obj.length / height)
            return transform.mapRect(ink).united(self.ObjectFootprint(obj)[0])
        renderers = self.furnishingRenderers
        artwork = (renderers.ArtworkGeometry(obj.definition["key"]) if hasattr(renderers, "ArtworkGeometry")
                   else renderers[obj.definition["key"]])
        return self.ObjectFootprint(obj)[0].united(FurnishingArtworkBounds(obj, artwork))

    def PaintObjectCandidates(self, drawingRect, pixelsPerMillimeter, dirtyRects = None):
        # Exports and derived/custom annotation models keep their original path.
        # Room-label area text can change without a model geometry notification.
        if getattr(self, "exportRender", False) or pixelsPerMillimeter != self.basePixelsPerMillimeter * self.zoom:
            return self.furnishings, self.labels
        changes = self.renderChanges
        definitions = []
        for identity, members in changes.definitions.items():
            member = next(iter(members.values()), None)
            if member is not None:
                definition = member.definition
                definitions.append((identity, definition["key"], definition["width"], definition["length"]))
        policy = (changes.topology, changes.visibility, tuple(self.visibility.items()), palette.labelFont,
                  tuple(definitions), id(self.furnishingRenderers), self.logicalDpiX(), self.logicalDpiY(), self.devicePixelRatioF())
        revision = changes.geometry + changes.appearance
        prepared = getattr(self, "paintObjectIndex", None)
        journal = changes.paintChanges
        rebuild = (prepared is None or prepared["policy"] != policy or journal is None
                   or revision - prepared["revision"] != journal["events"])
        if not rebuild:
            edits = {identity: obj for identity, obj in journal["objects"].items() if identity in prepared["objects"]}
            rebuild = len(prepared["overlay"].keys() | edits.keys()) > 256
        if rebuild:
            objects = self.furnishings + self.labels
            index = BoundsIndex(2000)
            prepared = dict(policy = policy, revision = revision, index = index, overlay = {},
                            objects = {}, positions = {}, fallback = set(), ordered = objects, split = len(self.furnishings))
            for position, obj in enumerate(objects):
                identity = id(obj)
                prepared["positions"].setdefault(identity, []).append(position)
                if identity in prepared["objects"]:
                    continue
                prepared["objects"][identity] = obj
                if not self.IsObjectVisible(obj):
                    continue
                if type(obj) not in (Furnishing, Label):
                    prepared["fallback"].add(identity)
                    continue
                bounds = self.PaintObjectBounds(obj)
                if all(math.isfinite(value) for value in bounds.getCoords()):
                    index.Insert(bounds.normalized().adjusted(-1e-5, -1e-5, 1e-5, 1e-5), identity)
                else:
                    prepared["fallback"].add(identity)
        else:
            # Calculate all edits before publishing; a failed artwork/layout load
            # must leave both the previous index and pending notifications intact.
            overlay = dict(prepared["overlay"])
            for identity, obj in edits.items():
                if type(obj) in (Furnishing, Label) and self.IsObjectVisible(obj):
                    overlay[identity] = self.PaintObjectBounds(obj)
            prepared = dict(prepared, overlay = overlay, revision = revision)
        self.paintObjectIndex = prepared
        changes.paintChanges = {"objects": {}, "events": 0}
        padding = max(2, self.lineWidths["furnishings"] + 2)
        queryKey = (revision, drawingRect.getRect(), pixelsPerMillimeter, self.width(), self.height(),
                    self.panOffset.x(), self.panOffset.y(), padding,
                    None if dirtyRects is None else tuple(rect.getRect() for rect in dirtyRects))
        cached = prepared.get("query")
        if cached is not None and cached[0] == queryKey:
            return cached[1]
        regions = [drawingRect] if dirtyRects is None else [drawingRect.intersected(rect) for rect in dirtyRects]
        overlay = prepared["overlay"]
        candidates = prepared["fallback"] - overlay.keys()
        for region in regions:
            if region.isEmpty():
                continue
            region = region.adjusted(-padding, -padding, padding, padding)
            bounds = QtCore.QRectF(self.ViewportToWorld(region.topLeft()), self.ViewportToWorld(region.bottomRight())).normalized()
            candidates.update(identity for identity in prepared["index"].Query(bounds) if identity not in overlay)
            candidates.update(identity for identity, ink in overlay.items()
                              if not all(math.isfinite(value) for value in ink.getCoords())
                              or ink.normalized().adjusted(-1e-5, -1e-5, 1e-5, 1e-5).intersects(bounds))
        if len(candidates) * 4 >= len(prepared["objects"]) * 3:
            result = self.furnishings, self.labels
        else:
            positions = sorted(position for identity in candidates for position in prepared["positions"][identity])
            ordered, split = prepared["ordered"], prepared["split"]
            result = ([ordered[position] for position in positions if position < split],
                      [ordered[position] for position in positions if position >= split])
        prepared["query"] = queryKey, result
        return result
