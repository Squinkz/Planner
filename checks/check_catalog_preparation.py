"""Frozen search ordering, lazy thumbnail requests and exact catalog pixels."""
import gc
import os
from pathlib import Path
import sys
import weakref
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from fixtures.parity_examples import ExampleWindow
from fixtures.catalog_search_reference_20261030 import FindFurnishings as ReferenceFind
from fixtures.catalog_popup_reference_20261030 import FurnishingQuickSearch as ReferencePopup
from fixtures.catalog_list_reference_20261030 import FurnishingCatalogList as ReferenceList
from planner_app.furnishing_search import FindFurnishings, FurnishingSearchFields
from planner_app.graphics.furnishing_thumbnails import FurnishingThumbnailCache
from planner_app.ui.furnishing_quick_search import FurnishingQuickSearch
from planner_app.ui.furnishing_list import FurnishingCatalogList


def Pixels(widget):
    widget.ensurePolished()
    ratio = widget.devicePixelRatioF()
    image = QtGui.QImage(round(widget.width() * ratio), round(widget.height() * ratio), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(ratio)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    widget.render(image)
    return image


def Main():
    matrices, images = 0, 0
    with ExampleWindow() as (main, folder):
        definitions = list(main.viewport.furnishingDefinitions.values())
        queries = ("", "*", "chair", "ChAiR", "ch", "office chair", "couch", "six chairs", "dinnng", "washr",
                   "noexistent", "w:60 l:60", "400 600", "w:400mm l:.6m", '2\' 6"', "w:", "L: 40", "4×6", "shelves", "123456789" * 40)
        for mode in ("Millimeters", "Centimeters", "Meters", "Adaptive Metric", "Inches", "Feet and Inches"):
            for source in (definitions, [*definitions[20:45], definitions[21], *reversed(definitions[:8])]):
                for query in queries:
                    assert [id(item) for item in FindFurnishings(source, query, mode)] == [id(item) for item in ReferenceFind(source, query, mode)], (mode, query)
                    matrices += 1
        mutable = dict(key = "fixture", name = "Sofa Shelf", keywords = ["seating", "two"], categories = ["Office"], width = 400, length = 600)
        for change in range(9):
            if change == 1:
                mutable["keywords"].append("cupboard")
            elif change == 2:
                mutable["categories"][:] = ["Kitchen", "Laundry"]
            elif change == 3:
                mutable["name"] = "Refrigerator’s Children"
            elif change == 4:
                mutable["keywords"] = "wide couch"
            elif change == 5:
                mutable.pop("categories")
                mutable["category"] = ["Living", "Storage"]
            elif change == 6:
                mutable["width"], mutable["length"] = 600, 400
            elif change == 7:
                mutable["categories"] = []
            elif change == 8:
                mutable["key"] = "null"
            for query in (*queries, "cupboard", "kitchen", "child", "fridge"):
                assert FindFurnishings([mutable], query, "Inches") == ReferenceFind([mutable], query, "Inches"), (change, query)
                matrices += 1
        class Definition(dict):
            pass
        record = Definition(key = "weak", name = "Unused fixture", keywords = [], categories = [], width = 1, length = 2)
        retained = weakref.ref(record)
        FindFurnishings([record], "fixture", "Millimeters")
        del record
        gc.collect()
        assert retained() is None, "Search preparation retained a mutable catalog record"
        for index in range(4100):
            FurnishingSearchFields("Unique " + str(index), ("bounded",), ("Fixture",))
        assert FurnishingSearchFields.cache_info().currsize <= 4096

        for ui, canvas in (("Dark UI", "Dark Canvas"), ("Light UI", "Blueprint Canvas")):
            main.SetThemes(ui, canvas, notify = False)
            for mode in ("Centimeters", "Feet and Inches"):
                main.viewport.unitsMode = mode
                main.UpdateFurnishingSearch()
                for query in ("", "chair", "no matching fixture"):
                    popups = []
                    for cls in (ReferencePopup, FurnishingQuickSearch):
                        popup = cls(main)
                        popup.worldPosition = QtCore.QPointF(200000, 200000)
                        popup.visibleRows = 8
                        popup.setFixedWidth(420)
                        popup.searchField.blockSignals(True)
                        popup.searchField.setText(query)
                        popup.searchField.blockSignals(False)
                        popup.UpdateResults()
                        popup.adjustSize()
                        popups.append(popup)
                    assert Pixels(popups[0]) == Pixels(popups[1]), (ui, mode, query, "popup pixels")
                    images += 1
                    for popup in popups:
                        popup.results.setCurrentRow(max(0, popup.results.count() - 1))
                        popup.results.scrollToBottom()
                    assert Pixels(popups[0]) == Pixels(popups[1]), (ui, mode, query, "scrolled popup")
                    images += 1
                    matches = FindFurnishings(definitions, query, mode)
                    lists = [ReferenceList(main), FurnishingCatalogList(main)]
                    for view in lists:
                        view.resize(420, 380)
                        view.UpdateItems(matches, query)
                    assert Pixels(lists[0]) == Pixels(lists[1]), (ui, mode, query, "list pixels")
                    images += 1
                    for view in lists:
                        view.scrollToBottom()
                    assert Pixels(lists[0]) == Pixels(lists[1]), (ui, mode, query, "scrolled list")
                    images += 1
                    for widget in (*popups, *lists):
                        widget.hide()
                        widget.deleteLater()
                    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        # Hidden rows perform no I/O or SVG rendering. Painting requests only
        # viewport rows; repeated painting retains those same QIcons.
        popup = FurnishingQuickSearch(main)
        popup.worldPosition, popup.visibleRows = QtCore.QPointF(200000, 200000), 8
        popup.setFixedWidth(420)
        main.furnishingThumbnails = FurnishingThumbnailCache()
        with patch.object(main.furnishingThumbnails, "Icon", wraps = main.furnishingThumbnails.Icon) as icons:
            popup.UpdateResults()
            popup.adjustSize()
            assert icons.call_count == 0, "Hidden results eagerly loaded icons"
            Pixels(popup)
            first = icons.call_count
            assert 0 < first <= 10, ("Too many visible thumbnails", first)
            Pixels(popup)
            assert icons.call_count == first, "Repaint reread unchanged icons"
            last = popup.results.item(popup.results.count() - 1)
            assert not last.icon().isNull(), "Direct item icon access did not realize the thumbnail"
            popup.RefreshIcons()
            Pixels(popup)
            assert icons.call_count <= first * 2 + 1, "Theme refresh loaded offscreen icons"
        popup.hide()
        popup.deleteLater()
    print(f"PASS: {matrices} frozen search matrices, {images} exact popup/list images, live metadata edits, bounded record-free caching and visible-only thumbnail loading.")


if __name__ == "__main__":
    Main()
