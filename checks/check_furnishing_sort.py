"""Catalog sorting, reversal, shared cards, search and durable application state."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtTest, QtWidgets
from planner import MainWindow
from planner_app import furnishing_search
from planner_app.furnishing_search import FindFurnishings
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.placement_sizing import NominalPlacementSize


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    ApplyApplicationTheme(app)
    main = MainWindow()
    main.show()
    main.sidebarTabs.setCurrentIndex(1)
    app.processEvents()
    assert main.furnishingSortMode == "Category" and not main.furnishingSortDescending
    assert list(main.furnishingSortOptions) == ["Category", "Alphabetical", "Width", "Length", "Area"]
    assert not main.furnishingSortButton.icon().isNull()
    grids = dict(main.furnishingCategoryGrids)
    definitions = [definition for definition in main.viewport.furnishingDefinitions.values() if definition["key"] != "null"]
    with patch.object(furnishing_search, "FormatLength", wraps = furnishing_search.FormatLength) as formatting:
        for mode in ("Alphabetical", "Width", "Length", "Area"):
            for descending in (False, True):
                QtTest.QTest.mouseClick(main.furnishingSortButton, QtCore.Qt.MouseButton.LeftButton)
                assert main.furnishingSortMenu.isVisible()
                QtTest.QTest.mouseClick(main.furnishingSortOptions[mode], QtCore.Qt.MouseButton.LeftButton)
                app.processEvents()
                assert not main.furnishingSortMenu.isVisible()
                assert main.furnishingSortMode == mode and main.furnishingSortDescending == descending
                assert sum(button.isChecked() for button in main.furnishingSortOptions.values()) == 1
                assert main.furnishingSortOptions[mode].isChecked()
                if mode == "Alphabetical":
                    expected = sorted(definitions, key = lambda item: (item["name"].strip().casefold(), item["key"]), reverse = descending)
                elif mode == "Area":
                    expected = sorted(definitions, key = lambda item: (item["width"] * item["length"], item["name"].strip().casefold(), item["key"]), reverse = descending)
                else:
                    expected = sorted(definitions, key = lambda item: (item[mode.lower()], item["name"].strip().casefold(), item["key"]), reverse = descending)
                expectedKeys = [item["key"] for item in expected]
                grid = main.furnishingResultsGrid
                assert list(grid.model().keys) == expectedKeys
                assert all(widget.isHidden() for widget in main.furnishingCategoryWidgets.values())
                assert main.furnishingResultsHeading.isHidden()
                main.furnishingViewButton.click()
                assert main.furnishingListView
                catalog = main.furnishingList
                assert [catalog.item(index).data(QtCore.Qt.ItemDataRole.UserRole) for index in range(catalog.count())] == expectedKeys
                main.furnishingSearchField.setText("chair")
                assert not main.furnishingSortButton.isEnabled(), "Typing must immediately disable sorting"
                main.furnishingSearchTimer.stop()
                main.UpdateFurnishingSearch()
                matches = FindFurnishings(definitions, "chair", main.viewport.unitsMode)
                assert not main.furnishingSortButton.isEnabled()
                assert [catalog.item(index).data(QtCore.Qt.ItemDataRole.UserRole) for index in range(1, catalog.count())] == [item["key"] for item in matches]
                main.furnishingViewButton.click()
                assert list(grid.model().keys) == [item["key"] for item in matches]
                main.furnishingViewButton.click()
                main.furnishingSearchField.clear()
                main.furnishingSearchTimer.stop()
                main.UpdateFurnishingSearch()
                assert main.furnishingSortButton.isEnabled()
                main.furnishingViewButton.click()
                assert not main.furnishingListView and main.furnishingCategoryGrids == grids
        assert formatting.call_count == 0, "Sorting reformatted unchanged dimensions"
    # Grouped reversal changes both category order and the order within each category.
    main.SetFurnishingSort("Category")
    main.SetFurnishingSort("Category")
    categories = list(main.furnishingCategoryWidgets)[::-1]
    layout = main.furnishScrollArea.widget().layout()
    assert [layout.itemAt(index).widget() for index in range(len(categories))] == [main.furnishingCategoryWidgets[category] for category in categories]
    for category, grid in main.furnishingCategoryGrids.items():
        expected = list(main.furnishingCategoryKeys[category])[::-1]
        assert list(grid.model().keys) == expected
    main.furnishingViewButton.click()
    catalog = main.furnishingList
    headings = [catalog.item(index).text() for index in range(catalog.count())
                if catalog.item(index).data(QtCore.Qt.ItemDataRole.UserRole + 2)]
    assert headings == categories
    main.furnishingSearchField.setText("range")
    main.furnishingSearchTimer.stop()
    main.UpdateFurnishingSearch()
    matches = FindFurnishings(definitions, "range", main.viewport.unitsMode)
    assert [catalog.item(index).data(QtCore.Qt.ItemDataRole.UserRole) for index in range(1, catalog.count())] == [item["key"] for item in matches]
    assert main.furnishingSortMode == "Category" and main.furnishingSortDescending
    main.furnishingSearchField.clear()
    main.furnishingSearchTimer.stop()
    main.UpdateFurnishingSearch()
    assert main.furnishingSortButton.isEnabled() and main.furnishingSortDescending
    main.SetFurnishingSort("Width")
    main.SetFurnishingSort("Width")
    main.viewport.unitsMode = "Inches"
    main.UpdateFurnishingSearch()
    assert [main.furnishingList.item(index).data(QtCore.Qt.ItemDataRole.UserRole) for index in range(main.furnishingList.count())] == [
        item["key"] for item in sorted(definitions, key = lambda item: (NominalPlacementSize(item["width"], "Inches"), item["name"].strip().casefold(), item["key"]), reverse = True)]
    main.furnishingSearchField.setText("no matching fixture")
    main.furnishingSearchTimer.stop()
    main.UpdateFurnishingSearch()
    assert main.furnishingList.item(1).text() == "No results"
    main.furnishingViewButton.click()
    assert main.furnishingNoResults.isVisible() and main.furnishingResultsGrid.model().rowCount() == 0
    main.furnishingViewButton.click()
    main.furnishingSearchField.clear()
    main.furnishingSearchTimer.stop()
    main.UpdateFurnishingSearch()
    main.BuildFurnishTab(refresh = True)
    assert main.furnishingSortMode == "Width" and main.furnishingSortDescending
    assert main.furnishingSortOptions["Width"].isChecked()
    app.processEvents()
    main.furnishingSortButton.click()
    app.processEvents()
    main.grab().save(str(root / "diagnostics/furnishing-sort.png"))
    main.furnishingSortMenu.grab().save(str(root / "diagnostics/furnishing-sort-menu.png"))
    main.furnishingSortMenu.hide()
    main.MarkProjectClean()
    main.close()
    restored = MainWindow()
    assert restored.furnishingSortMode == "Width" and restored.furnishingSortDescending
    assert restored.furnishingListView and restored.furnishingSortOptions["Width"].isChecked()
    keys = [restored.furnishingList.item(index).data(QtCore.Qt.ItemDataRole.UserRole) for index in range(restored.furnishingList.count())]
    assert keys == [item["key"] for item in sorted(definitions, key = lambda item: (NominalPlacementSize(item["width"], restored.viewport.unitsMode), item["name"].strip().casefold(), item["key"]), reverse = True)]
    restored.SetFurnishingSort("Category")
    assert not restored.furnishingSortDescending
    restored.furnishingViewButton.click()
    assert all(not widget.isHidden() for widget in restored.furnishingCategoryWidgets.values())
    for descending in (False, True):
        restored.SetFurnishingSort("Area")
        assert restored.furnishingSortDescending == descending
        expected = sorted(definitions, key = lambda item: (
            NominalPlacementSize(item["width"], restored.viewport.unitsMode) * NominalPlacementSize(item["length"], restored.viewport.unitsMode),
            item["name"].strip().casefold(), item["key"]), reverse = descending)
        grid = restored.furnishingResultsGrid
        assert list(grid.model().keys) == [item["key"] for item in expected]
    restored.MarkProjectClean()
    restored.close()
    restoredArea = MainWindow()
    assert restoredArea.furnishingSortMode == "Area" and restoredArea.furnishingSortDescending
    assert restoredArea.furnishingSortOptions["Area"].isChecked()
    restoredArea.MarkProjectClean()
    restoredArea.close()


if __name__ == "__main__":
    Main()
