"""Alternating frozen/current catalog search and first-paint workloads."""
import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import sys
from time import perf_counter
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow
from fixtures.catalog_search_reference_20261030 import FindFurnishings as ReferenceFind
from fixtures.catalog_popup_reference_20261030 import FurnishingQuickSearch as ReferencePopup
from fixtures.catalog_list_reference_20261030 import FurnishingCatalogList as ReferenceList
from planner_app.furnishing_search import FindFurnishings, FurnishingSearchFields
from planner_app.graphics.furnishing_thumbnails import FurnishingThumbnailCache
from planner_app.ui.furnishing_quick_search import FurnishingQuickSearch
from planner_app.ui.furnishing_list import FurnishingCatalogList


def Paint(widget):
    ratio = widget.devicePixelRatioF()
    image = QtGui.QImage(round(widget.width() * ratio), round(widget.height() * ratio), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(ratio)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    widget.render(image)


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--samples", type = int, default = 7)
    parser.add_argument("--output", type = Path, default = root / "diagnostics/performance-catalog-20261030/benchmark-final.json")
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("Samples must be positive")
    results = dict(python = platform.python_version(), qt = QtCore.qVersion(), platform = platform.platform(), samples = args.samples,
        methodology = "Alternate frozen/current variants, discard one warmup, median batch means. Search excludes UI. "
            "UI timings include result preparation, thumbnail requests, row construction/layout and synchronous first QWidget paint. "
            "Cold means a fresh thumbnail cache; shared SVG/font caches retain normal application limits between samples. "
            "The full catalog can exceed the SVG preparation cache. Popup shows eight rows, list is 420x380. "
            "Excludes application startup, window positioning, input dispatch and display latency. Counts use separate untimed calls.",
        search = [], ui = [], counts = [])
    with ExampleWindow() as (main, folder):
        base = list(main.viewport.furnishingDefinitions.values())
        main.viewport.unitsMode = "Centimeters"
        main.UpdateFurnishingSearch()
        for count in (len(base), 1000, 4096):
            definitions = base if count == len(base) else [dict(base[index % len(base)], key = "fixture" + str(index),
                name = base[index % len(base)]["name"] + " variant " + str(index)) for index in range(count)]
            for group, queries in (("text", ("ch", "chai", "chair", "office chair", "sofa", "fridge")),
                                   ("fuzzy/no match", ("dinnng", "washr", "noexistent")),
                                   ("dimensions", ("w:60 l:60", "400 600", "w:400mm l:.6m"))):
                samples = [[], []]
                for repeat in range(args.samples + 1):
                    for variant in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                        find = ReferenceFind if variant == 0 else FindFurnishings
                        start = perf_counter()
                        for query in queries:
                            find(definitions, query, "Centimeters")
                        elapsed = (perf_counter() - start) * 1000 / len(queries)
                        if repeat:
                            samples[variant].append(elapsed)
                row = dict(entries = count, group = group, beforeMs = statistics.median(samples[0]), afterMs = statistics.median(samples[1]), samplesMs = samples)
                results["search"].append(row)
                print("search", count, group, round(row["beforeMs"], 3), round(row["afterMs"], 3), flush = True)
        for kind in ("popup", "list"):
            for state in ("cold", "warm"):
                views, caches = [], []
                for cls in ((ReferencePopup, FurnishingQuickSearch) if kind == "popup" else (ReferenceList, FurnishingCatalogList)):
                    view = cls(main)
                    if kind == "popup":
                        view.worldPosition = QtCore.QPointF(200000, 200000)
                        view.visibleRows = 8
                        view.setFixedWidth(420)
                    else:
                        view.resize(420, 380)
                    views.append(view)
                    caches.append(FurnishingThumbnailCache())
                samples = [[], []]
                for repeat in range(args.samples + 1):
                    for variant in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                        if state == "cold":
                            caches[variant] = FurnishingThumbnailCache()
                        main.furnishingThumbnails = caches[variant]
                        view = views[variant]
                        start = perf_counter()
                        if kind == "popup":
                            view.UpdateResults()
                            view.adjustSize()
                        else:
                            # Emulate a real result/units rebuild, not the early
                            # return used for identical categorized list keys.
                            view.resultKey = None
                            view.UpdateItems(base, "*")
                        Paint(view)
                        elapsed = (perf_counter() - start) * 1000
                        if repeat:
                            samples[variant].append(elapsed)
                row = dict(view = kind, state = state, entries = len(base) - 1,
                    beforeMs = statistics.median(samples[0]), afterMs = statistics.median(samples[1]), samplesMs = samples)
                results["ui"].append(row)
                print(kind, state, round(row["beforeMs"], 3), round(row["afterMs"], 3), flush = True)
                for variant, view in enumerate(views):
                    cache = FurnishingThumbnailCache()
                    main.furnishingThumbnails = cache
                    reads = []
                    readBytes = Path.read_bytes
                    def ReadSource(path):
                        reads.append(str(path))
                        return readBytes(path)
                    with patch.object(cache, "Icon", wraps = cache.Icon) as icons, patch.object(Path, "read_bytes", ReadSource):
                        if kind == "popup":
                            view.UpdateResults()
                            view.adjustSize()
                        else:
                            view.resultKey = None
                            view.UpdateItems(base, "*")
                        Paint(view)
                        firstCalls, firstReads = icons.call_count, len(reads)
                        Paint(view)
                    results["counts"].append(dict(view = kind, state = state, variant = "before" if variant == 0 else "after",
                        firstPaintIconCalls = firstCalls, firstPaintFileReads = firstReads,
                        repaintAdditionalIconCalls = icons.call_count - firstCalls, repaintAdditionalFileReads = len(reads) - firstReads,
                        retainedIcons = len(cache.icons), accountedThumbnailBytes = cache.byteCount))
                    view.hide()
                    view.deleteLater()
                QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        results["fieldCache"] = FurnishingSearchFields.cache_info()._asdict()
    args.output.parent.mkdir(parents = True, exist_ok = True)
    args.output.write_text(json.dumps(results, indent = 2) + "\n", encoding = "utf-8")


if __name__ == "__main__":
    Main()
