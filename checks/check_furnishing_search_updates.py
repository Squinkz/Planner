"""Search retains shared cards and refreshes layout metrics and units correctly."""
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
    originals = dict(main.furnishingCards)
    categoryCards = dict(main.furnishingCategoryCards)
    field, grid = main.furnishingSearchField, main.furnishingResultsLayout
    field.setFocus()
    with patch.object(furnishing_search, "FormatLength", wraps = furnishing_search.FormatLength) as formatting:
        for cycle in range(3):
            for query in ("chair", "chair office", "*", "no matching fixture", ""):
                before = {grid.itemAt(index).widget(): grid.itemAt(index) for index in range(grid.count())}
                field.setText(query)
                main.furnishingSearchTimer.stop()
                main.UpdateFurnishingSearch()
                app.processEvents()
                assert field.hasFocus(), "Search rebuilding stole keyboard focus"
                assert main.furnishingCards == originals
                if query:
                    expected = FindFurnishings(definitions, query, main.viewport.unitsMode)
                    cards = [grid.itemAt(index).widget() for index in range(grid.count())]
                    assert cards == [originals[definition["key"]] for definition in expected]
                    assert all(card.isVisible() == (card in cards) for card in originals.values())
                    assert all(not widget.isVisible() for widget in main.furnishingCategoryWidgets.values())
                    assert main.furnishingNoResults.isVisible() == (not expected)
                    for index, card in enumerate(cards):
                        if card in before:
                            assert grid.itemAt(index) is before[card], "Shared result lost its layout item"
                else:
                    assert grid.count() == 0
                    for category, categoryGrid in main.furnishingCategoryLayouts.items():
                        cards = [card for (key, name), card in categoryCards.items() if name == category]
                        assert [categoryGrid.itemAt(index).widget() for index in range(categoryGrid.count())] == cards
                        assert all(card.isVisible() for card in cards)
        assert formatting.call_count == 0, "Typing reformatted every dimension"
        main.viewport.unitsMode = "Inches"
        main.UpdateFurnishingSearch()
        assert formatting.call_count == 2 * (len(definitions) - 1)
    field.setText("chair")
    main.UpdateFurnishingSearch()
    with patch.object(grid, "SetWidgets", wraps = grid.SetWidgets) as replacement:
        field.setText("CHAIR")
        main.UpdateFurnishingSearch()
        assert not replacement.called, "Identical results rebuilt the layout"
    app.processEvents()
    width = 250
    oldHeight = grid.heightForWidth(width)
    card = grid.itemAt(0).widget()
    caption = next(label for label in card.findChildren(QtWidgets.QLabel) if label.objectName() == "openingIconCaption")
    caption.setText("A much longer furnishing caption that occupies several additional lines")
    app.processEvents()
    assert grid.heightForWidth(width) > oldHeight, "Caption change left stale grid metrics"
    assert grid.heightForWidth(130) >= grid.heightForWidth(400)
    main.BuildFurnishTab(refresh = True)
    assert main.furnishingSearchField.text() == "CHAIR"
    assert main.furnishingResultsLayout.count() == len(FindFurnishings(definitions, "chair", "Inches"))
    main.close()
    print("PASS: shared items, identical results, focus, category ordering, unit refresh, caption/width changes and rebuild")


if __name__ == "__main__":
    Main()
