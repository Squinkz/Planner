"""Aggregate admission for the viewport's retained raster surfaces."""
from PySide6 import QtGui
from time import perf_counter


class RasterCacheBudget:
    def __init__(self, viewport):
        self.viewport = viewport
        self.peakBytes = 0
        self.evictions = 0

    def Entries(self):
        v = self.viewport
        entries = {"background": v.viewportBackground, "scene": v.viewportScene, "pan": v.viewportPanRaster,
                   "edit": v.viewportEditRaster, "referenceFocus": v.referenceFocusBackground}
        overlay = getattr(v, "exportOverlay", None)
        if overlay is not None:
            entries.update(snapshot = overlay.snapshot, navigation = overlay.svgNavigationImage,
                           vectorView = overlay.svgViewImage, detail = overlay.detailImage,
                           rulers = [strip[2] for strip in overlay.rulerStrips])
        return entries

    def RetainedBytes(self):
        seen = set()
        total = 0
        for entry in self.Entries().values():
            for image in entry if isinstance(entry, list) else (entry,):
                if image is None or image.isNull():
                    continue
                key = (type(image), image.cacheKey())
                if key in seen:
                    continue
                seen.add(key)
                total += image.sizeInBytes() if isinstance(image, QtGui.QImage) else image.width() * image.height() * max(4, image.depth() // 8)
        return total

    def Clear(self, name, reason = "budget"):
        v = self.viewport
        entry = self.Entries()[name]
        if entry is None or isinstance(entry, list) and not entry:
            return
        if name == "background":
            v.viewportBackground = v.viewportBackgroundKey = None
        elif name == "scene":
            v.viewportScene = v.viewportSceneKey = v.viewportSceneState = None
        elif name == "pan":
            v.viewportPanRaster = v.viewportPanKey = v.viewportPanState = v.viewportPanOrigin = None
        elif name == "edit":
            v.viewportEditRaster = v.viewportEditKey = v.viewportEditState = v.viewportEditSnapshot = None
            v.viewportEditFrameKey = v.viewportEditBackgroundKey = None
            v.viewportEditDirtyRects = []
        elif name == "referenceFocus":
            v.referenceFocusBackground = v.referenceFocusKey = None
        else:
            overlay = v.exportOverlay
            if name == "snapshot":
                overlay.snapshot = overlay.snapshotKey = None
            elif name == "navigation":
                overlay.svgNavigationImage = None
            elif name == "vectorView":
                overlay.svgViewImage = overlay.svgViewKey = None
            elif name == "detail":
                overlay.detailImage = overlay.detailBounds = overlay.detailKey = None
            elif name == "rulers":
                overlay.rulerStrips = []
                overlay.rulerKey = None
        self.evictions += 1
        self.Record("evicted", name, reason)

    def Prepare(self, name, requestedBytes, preserve = ()):
        """Release replacements before allocation; never evict a caller's live source."""
        self.Clear(name, "replacement")
        limit = self.viewport.viewportRasterByteLimit
        for candidate in self.Entries():
            if self.RetainedBytes() + requestedBytes <= limit:
                break
            if candidate != name and candidate not in preserve:
                self.Clear(candidate)
        admitted = self.RetainedBytes() + requestedBytes <= limit
        if admitted:
            self.peakBytes = max(self.peakBytes, self.RetainedBytes() + requestedBytes)
        self.Record("allocation" if admitted else "refused", name, "admission", requestedBytes)
        return admitted

    def Enforce(self):
        for name in self.Entries():
            if self.RetainedBytes() <= self.viewport.viewportRasterByteLimit:
                break
            self.Clear(name, "limit-change")

    def Record(self, action, name, reason, requestedBytes = 0):
        diagnostics = self.viewport.renderDiagnostics
        if diagnostics is not None and diagnostics.enabled:
            diagnostics.RecordEvent({"kind": "rasterCache", "action": action, "name": name, "reason": reason,
                                     "at": perf_counter(),
                                     "requestedBytes": requestedBytes, "retainedBytes": self.RetainedBytes(),
                                     "limitBytes": self.viewport.viewportRasterByteLimit})
