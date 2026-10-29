"""Search retains grid models and refreshes layout metrics and units correctly."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner_app.ui.main_window import MainWindow
from planner_app.furnishing_search import FindFurnishings
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app import furnishing_search


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    main = MainWindow()
    main.show()
    main.sidebarTabs.setCurrentIndex(1)
    app.processEvents()
    definitions = list(main.viewport.furnishingDefinitions.values())
    grids = dict(main.furnishingCategoryGrids)
    field, grid = main.furnishingSearchField, main.furnishingResultsGrid
    field.setFocus()
    with patch.object(furnishing_search, "FormatLength", wraps = furnishing_search.FormatLength) as formatting:
        for cycle in range(3):
            for query in ("chair", "chair office", "*", "no matching fixture", ""):
                field.setText(query)
                main.furnishingSearchTimer.stop()
                main.UpdateFurnishingSearch()
                app.processEvents()
                assert field.hasFocus(), "Search rebuilding stole keyboard focus"
                assert main.furnishingCategoryGrids == grids
                if query:
                    expected = FindFurnishings(definitions, query, main.viewport.unitsMode)
                    assert grid.model().keys == tuple(definition["key"] for definition in expected)
                    assert all(not widget.isVisible() for widget in main.furnishingCategoryWidgets.values())
                    assert main.furnishingNoResults.isVisible() == (not expected)
                else:
                    for category, categoryGrid in grids.items():
                        assert categoryGrid.model().keys == main.furnishingCategoryKeys[category]
                        assert categoryGrid.isVisible()
        assert formatting.call_count == 0, "Typing reformatted every dimension"
        main.viewport.unitsMode = "Inches"
        main.UpdateFurnishingSearch()
        assert formatting.call_count == 2 * (len(definitions) - 1)
    field.setText("chair")
    main.UpdateFurnishingSearch()
    with patch.object(grid.model(), "beginResetModel", wraps = grid.model().beginResetModel) as replacement:
        field.setText("CHAIR")
        main.UpdateFurnishingSearch()
        assert not replacement.called, "Identical results rebuilt the model"
    app.processEvents()
    firstKey = grid.model().keys[0]
    originalName = main.viewport.furnishingDefinitions[firstKey]["name"]
    oldHeight = grid.cellHeight
    main.viewport.furnishingDefinitions[firstKey]["name"] = "A much longer furnishing caption that occupies several additional lines"
    grid.RefreshMetrics()
    assert grid.cellHeight > oldHeight, "Caption change left stale grid metrics"
    main.viewport.furnishingDefinitions[firstKey]["name"] = originalName
    main.BuildFurnishTab(refresh = True)
    assert main.furnishingSearchField.text() == "CHAIR"
    assert main.furnishingResultsGrid.model().rowCount() == len(FindFurnishings(definitions, "chair", "Inches"))
    main.close()
    print("PASS: shared items, identical results, focus, category ordering, unit refresh, caption/width changes and rebuild")


if __name__ == "__main__":
    Main()
