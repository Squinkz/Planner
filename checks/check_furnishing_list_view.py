"""Pinned catalog view controls, categorized rows, search, units and shared drags."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.graphics.palette import themeColors
from planner_app.furnishing_search import FindFurnishings, FurnishingDimensionText


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    main = MainWindow()
    main.show()
    main.sidebarTabs.setCurrentIndex(1)
    app.processEvents()
    button, catalog = main.furnishingViewButton, main.furnishingList
    searchRect = main.furnishingSearchField.rect()
    searchRight = main.furnishingSearchField.mapToGlobal(searchRect.topRight()).x()
    sortPosition = main.furnishingSortButton.mapToGlobal(QtCore.QPoint())
    viewPosition = button.mapToGlobal(QtCore.QPoint())
    assert searchRight < sortPosition.x() < viewPosition.x()
    assert sortPosition.y() == viewPosition.y()
    assert main.furnishingSearchPanel.isAncestorOf(button)
    assert not button.isChecked() and not main.furnishingListView and catalog.isHidden()
    assert main.furnishScrollArea.isVisible() and not button.icon().isNull()
    grid = next(grid for grid in main.furnishingCategoryLayouts.values() if grid.count() >= 6)
    firstRow = [grid.itemAt(index).geometry() for index in range(6)]
    assert len({rect.y() for rect in firstRow[:5]}) == 1, "Default sidebar should fit five tiles per row"
    assert firstRow[5].y() > firstRow[0].y(), "Default sidebar should wrap after five tiles"
    availableWidth = sum(main.mainSplitter.sizes())
    main.mainSplitter.setSizes([availableWidth - 600, 600])
    QtTest.QTest.mouseDClick(main.mainSplitter.handle(1), QtCore.Qt.MouseButton.LeftButton)
    app.processEvents()
    assert main.mainSplitter.sizes()[1] == 460, "Double-click should restore the default sidebar width"
    for selector in (button, main.transformOrientationButton):
        assert selector.property("modeSelector") is True
        selector.setAttribute(QtCore.Qt.WidgetAttribute.WA_UnderMouse, False)
        assert selector.grab().toImage().pixelColor(5, 5).name() == QtGui.QColor(themeColors["activeBackground"]).name()
    cards = dict(main.furnishingCategoryCards)
    headerPositions = [widget.mapToGlobal(QtCore.QPoint()) for widget in (main.furnishingSearchPanel, main.furnishingViewPanel)]
    main.furnishScrollArea.verticalScrollBar().setValue(main.furnishScrollArea.verticalScrollBar().maximum())
    app.processEvents()
    assert headerPositions == [widget.mapToGlobal(QtCore.QPoint()) for widget in (main.furnishingSearchPanel, main.furnishingViewPanel)]
    QtTest.QTest.mouseClick(button, QtCore.Qt.MouseButton.LeftButton)
    app.processEvents()
    assert button.isChecked() and main.furnishingListView and catalog.isVisible()
    assert button.grab().toImage().pixelColor(5, 5).name() == QtGui.QColor(themeColors["activeBackground"]).name()
    assert main.furnishScrollArea.isHidden() and main.furnishingCategoryCards == cards
    headings = [catalog.item(row).text() for row in range(catalog.count())
                if catalog.item(row).data(QtCore.Qt.ItemDataRole.UserRole + 2)]
    assert headings == list(main.furnishingCategoryWidgets)
    assert catalog.count() == len(main.furnishingCategoryCards) + len(headings)
    for row in range(catalog.count()):
        item = catalog.item(row)
        key = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if key is None:
            assert not item.flags() & QtCore.Qt.ItemFlag.ItemIsSelectable
        else:
            assert item.data(QtCore.Qt.ItemDataRole.UserRole + 1) == main.furnishingDimensionLabels[key].text()
    catalog.verticalScrollBar().setValue(catalog.verticalScrollBar().maximum())
    app.processEvents()
    assert headerPositions == [widget.mapToGlobal(QtCore.QPoint()) for widget in (main.furnishingSearchPanel, main.furnishingViewPanel)]
    for query in ("chair", "CHAIR", "*", "no matching fixture", ""):
        oldItem = catalog.item(1) if query == "CHAIR" else None
        main.furnishingSearchField.setText(query)
        main.furnishingSearchTimer.stop()
        main.UpdateFurnishingSearch()
        expected = FindFurnishings(main.viewport.furnishingDefinitions.values(), query, main.viewport.unitsMode)
        keys = [catalog.item(row).data(QtCore.Qt.ItemDataRole.UserRole) for row in range(catalog.count())]
        if query:
            assert [key for key in keys if key is not None] == [definition["key"] for definition in expected]
        if query == "CHAIR":
            assert catalog.item(1) is oldItem, "Identical results rebuilt list rows"
        if query == "no matching fixture":
            assert catalog.item(1).text() == "No results"
    main.viewport.unitsMode = "Inches"
    main.UpdateFurnishingSearch()
    item = catalog.item(1)
    key = item.data(QtCore.Qt.ItemDataRole.UserRole)
    assert item.data(QtCore.Qt.ItemDataRole.UserRole + 1) == FurnishingDimensionText(main.viewport.furnishingDefinitions[key], "Inches")
    catalog.setCurrentItem(item)
    payloads = []

    def CaptureDrag(drag, actions):
        assert main.viewport.guiDragActive and main.viewport.guiDragKind == "furnishing"
        payloads.append(bytes(drag.mimeData().data("application/x-planner-furnishing")).decode())
        return QtCore.Qt.DropAction.IgnoreAction

    with patch.object(QtGui.QDrag, "exec", CaptureDrag):
        catalog.startDrag(QtCore.Qt.DropAction.CopyAction)
    assert payloads == [key] and not main.viewport.guiDragActive and main.viewport.furnishingPreview is None
    catalog.setCurrentItem(catalog.item(0))
    with patch.object(QtGui.QDrag, "exec", side_effect = AssertionError("Category heading started a drag")):
        catalog.startDrag(QtCore.Qt.DropAction.CopyAction)
    main.furnishingSearchField.setText("chair")
    main.furnishingSearchTimer.stop()
    main.UpdateFurnishingSearch()
    main.BuildFurnishTab(refresh = True)
    app.processEvents()
    assert main.furnishingViewButton is button and button.isChecked() and main.furnishingList is catalog
    assert main.furnishingSearchField.text() == "chair" and main.furnishScrollArea.isHidden()
    QtTest.QTest.mouseClick(button, QtCore.Qt.MouseButton.LeftButton)
    app.processEvents()
    assert main.furnishScrollArea.isVisible() and catalog.isHidden()
    assert main.furnishingResultsLayout.count() == len(FindFurnishings(main.viewport.furnishingDefinitions.values(), "chair", "Inches"))
    QtTest.QTest.mouseClick(button, QtCore.Qt.MouseButton.LeftButton)
    main.furnishingSearchField.clear()
    main.furnishingSearchTimer.stop()
    main.UpdateFurnishingSearch()
    app.processEvents()
    main.grab().save(str(root / "diagnostics/furnishing-list-view.png"))
    main.SetThemes(uiTheme = "Light UI")
    app.processEvents()
    assert main.furnishingListView and button.isChecked()
    item = catalog.item(1)
    key = item.data(QtCore.Qt.ItemDataRole.UserRole)
    assert item.icon().cacheKey() == main.furnishingButtons[key].icon().cacheKey(), "List retained an old theme icon"
    main.resize(1000, 720)
    app.processEvents()
    assert not catalog.horizontalScrollBar().isVisible()
    assert main.furnishingViewPanel.isVisible() and main.furnishingSearchPanel.isVisible()
    main.grab().save(str(root / "diagnostics/furnishing-list-view-light.png"))
    main.MarkProjectClean()
    main.close()
    restored = MainWindow()
    assert restored.furnishingListView and restored.furnishingViewButton.isChecked()
    assert restored.furnishScrollArea.isHidden() and not restored.furnishingList.isHidden()
    restored.furnishingViewButton.click()
    restored.MarkProjectClean()
    restored.close()
    restoredGrid = MainWindow()
    assert not restoredGrid.furnishingListView and not restoredGrid.furnishingViewButton.isChecked()
    restoredGrid.MarkProjectClean()
    restoredGrid.close()


if __name__ == "__main__":
    Main()
