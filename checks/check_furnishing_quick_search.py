"""Space search, keyboard/mouse placement, focus, cancellation and export guards."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Wall
from planner_app.furnishing_search import FindFurnishings
from planner_app.graphics import palette
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.viewport.rendering import toolTipRows


def OpenSearch(main, position):
    main.activateWindow()
    main.viewport.setFocus()
    QtGui.QCursor.setPos(main.viewport.mapToGlobal(position.toPoint()))
    QtWidgets.QApplication.processEvents()
    QtTest.QTest.keyClick(main.viewport, QtCore.Qt.Key.Key_Space)
    QtWidgets.QApplication.processEvents()
    popup = main.furnishingQuickSearch
    assert popup.isVisible() and popup.searchField.hasFocus()
    return popup


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    main = MainWindow()
    main.show()
    main.activateWindow()
    app.processEvents()
    v = main.viewport
    v.snapEnabled = False
    v.unitsMode = "Centimeters"
    position = v.DrawingRect().center()
    originalWorld = v.ViewportToWorld(position)
    assert toolTipRows["searchFurnishings"] == ("Space", "Search furnishings")
    popup = OpenSearch(main, position)
    assert popup.results.count() == len(v.furnishingDefinitions) - 1
    assert not v.furnishings and not v.undoHistory
    for query in ("dinn", "dinne", "dinner"):
        popup.searchField.setText(query)
        keys = {popup.results.item(index).data(QtCore.Qt.ItemDataRole.UserRole) for index in range(popup.results.count())}
        expectedDinner = {item["key"] for item in FindFurnishings(v.furnishingDefinitions.values(), "dinner", v.unitsMode)}
        assert expectedDinner and expectedDinner <= keys, query
        assert popup.status.isHidden()
    popup.searchField.clear()
    QtTest.QTest.keyClicks(popup.searchField, "sofa")
    expected = FindFurnishings(v.furnishingDefinitions.values(), "sofa", v.unitsMode)
    assert [popup.results.item(index).data(QtCore.Qt.ItemDataRole.UserRole) for index in range(popup.results.count())] == [item["key"] for item in expected]
    assert popup.results.currentRow() == 0
    assert popup.status.isHidden()
    main.UpdateFurnishingSearch()
    for index in range(popup.results.count()):
        item = popup.results.item(index)
        key = item.data(QtCore.Qt.ItemDataRole.UserRole)
        assert item.data(QtCore.Qt.ItemDataRole.UserRole + 1) == main.furnishingDimensions[key]
    assert popup.resultDelegate.dimensionStyle.font().pointSizeF() < popup.results.font().pointSizeF()
    searchPanel = popup.findChild(QtWidgets.QFrame, "furnishingQuickSearchField")
    pixels = popup.grab().toImage()
    assert pixels.pixelColor(searchPanel.x() + 5, searchPanel.y() + 5).name() == palette.themeColors["fieldBackground"]
    assert pixels.pixelColor(2, 2).name() == palette.themeColors["windowBackground"]
    QtTest.QTest.keyClick(popup.searchField, QtCore.Qt.Key.Key_Up)
    assert popup.results.currentRow() == popup.results.count() - 1 and popup.searchField.hasFocus(), (popup.results.currentRow(), popup.results.count(), popup.searchField.hasFocus())
    lastItem = popup.results.currentItem()
    assert v.furnishingPreview.definition["key"] == lastItem.data(QtCore.Qt.ItemDataRole.UserRole)
    assert popup.results.viewport().rect().intersects(popup.results.visualItemRect(lastItem))
    QtTest.QTest.keyClick(popup.searchField, QtCore.Qt.Key.Key_Down)
    assert popup.results.currentRow() == 0 and popup.searchField.hasFocus()
    firstItem = popup.results.currentItem()
    assert v.furnishingPreview.definition["key"] == firstItem.data(QtCore.Qt.ItemDataRole.UserRole)
    assert popup.results.viewport().rect().intersects(popup.results.visualItemRect(firstItem))
    QtTest.QTest.keyClick(popup.searchField, QtCore.Qt.Key.Key_Down)
    assert popup.results.currentRow() == 1 and popup.searchField.hasFocus()
    chosen = popup.results.currentItem().data(QtCore.Qt.ItemDataRole.UserRole)
    assert v.furnishingPreview.definition["key"] == chosen
    QtTest.QTest.keyClick(popup.searchField, QtCore.Qt.Key.Key_Return)
    assert not popup.isVisible() and v.furnishingPreview is None
    assert len(v.furnishings) == 1 and len(v.undoHistory) == 1
    assert v.furnishings[0].definition["key"] == chosen
    assert QtCore.QLineF((v.furnishings[0].firstVertex + v.furnishings[0].secondVertex) / 2, originalWorld).length() < 1e-6
    v.Undo()
    assert not v.furnishings
    v.Redo()
    assert len(v.furnishings) == 1

    popup = OpenSearch(main, position)
    assert popup.searchField.text() == ""
    QtTest.QTest.keyClicks(popup.searchField, "desk")
    assert v.openingPlacementMode is None, "Typing invoked viewport tool shortcuts"
    assert popup.results.count() > 0
    chosen = popup.results.item(0).data(QtCore.Qt.ItemDataRole.UserRole)
    rowRect = popup.results.visualItemRect(popup.results.item(0))
    QtGui.QCursor.setPos(popup.results.viewport().mapToGlobal(rowRect.center()))
    QtTest.QTest.mouseClick(popup.results.viewport(), QtCore.Qt.MouseButton.LeftButton, pos = rowRect.center())
    assert not popup.isVisible() and len(v.furnishings) == 2
    assert v.furnishings[-1].definition["key"] == chosen
    assert QtCore.QLineF((v.furnishings[-1].firstVertex + v.furnishings[-1].secondVertex) / 2, originalWorld).length() < 1e-6

    popup = OpenSearch(main, position)
    popup.searchField.setText("w:40 l:60")
    assert popup.results.count() == len(FindFurnishings(v.furnishingDefinitions.values(), "w:40 l:60", v.unitsMode))
    popup.searchField.setText("no-such-furnishing-123")
    assert popup.results.count() == 0 and popup.status.text() == "No results" and v.furnishingPreview is None
    QtTest.QTest.keyClick(popup.searchField, QtCore.Qt.Key.Key_Down)
    QtTest.QTest.keyClick(popup.searchField, QtCore.Qt.Key.Key_Up)
    assert popup.results.currentRow() == -1 and v.furnishingPreview is None
    QtTest.QTest.keyClick(popup.searchField, QtCore.Qt.Key.Key_Enter)
    assert popup.isVisible() and len(v.furnishings) == 2
    QtTest.QTest.keyClick(popup.searchField, QtCore.Qt.Key.Key_Escape)
    assert not popup.isVisible() and v.furnishingPreview is None and not v.alignmentGuides

    # Existing text fields retain spaces, even while the pointer is over the canvas.
    main.sidebarTabs.setCurrentWidget(main.furnishPage)
    main.furnishingSearchField.setFocus()
    main.furnishingSearchField.setText("desk")
    QtGui.QCursor.setPos(v.mapToGlobal(position.toPoint()))
    QtTest.QTest.keyClick(main.furnishingSearchField, QtCore.Qt.Key.Key_Space)
    assert main.furnishingSearchField.text() == "desk " and not popup.isVisible()
    main.furnishingSearchField.clear()
    v.setFocus()
    QtGui.QCursor.setPos(main.sidebarPanel.mapToGlobal(QtCore.QPoint(10, 10)))
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Space)
    assert not popup.isVisible()

    main.sidebarTabs.setCurrentWidget(main.exportPanel)
    app.processEvents()
    assert v.exportOverlay.active
    v.setFocus()
    QtGui.QCursor.setPos(v.mapToGlobal(position.toPoint()))
    QtTest.QTest.keyClick(v, QtCore.Qt.Key.Key_Space)
    assert not popup.isVisible() and not main.ShowFurnishingSearch(position)
    main.sidebarTabs.setCurrentIndex(0)

    # Failed placement stays in the search, with feedback and no history edit.
    center = v.ViewportToWorld(position)
    v.walls = [Wall(center - QtCore.QPointF(10000, 0), center + QtCore.QPointF(10000, 0), 20000)]
    count = len(v.undoHistory)
    popup = OpenSearch(main, position)
    popup.searchField.setText("desk")
    assert "Not enough space" in popup.status.text()
    QtTest.QTest.keyClick(popup.searchField, QtCore.Qt.Key.Key_Return)
    assert popup.isVisible() and len(v.undoHistory) == count and len(v.furnishings) == 2
    popup.hide()
    assert v.furnishingPreview is None
    v.walls = []

    edge = v.DrawingRect().bottomRight() - QtCore.QPointF(2, 2)
    popup = OpenSearch(main, edge)
    available = QtCore.QRect(v.mapToGlobal(v.DrawingRect().topLeft().toPoint()), v.DrawingRect().size().toSize())
    assert available.contains(popup.geometry()), (available, popup.geometry())
    popup.searchField.setText("sofa")
    app.processEvents()
    popup.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots/furnishing-quick-search.png"))
    main.sidebarTabs.setCurrentWidget(main.exportPanel)
    assert not popup.isVisible() and v.furnishingPreview is None
    main.sidebarTabs.setCurrentIndex(0)
    themes = palette.activeUITheme, palette.activeCanvasTheme
    main.SetThemes("Light UI", "Blueprint Canvas", notify = False)
    popup = OpenSearch(main, position)
    popup.searchField.setText("desk")
    app.processEvents()
    popup.grab().save(str(Path(__file__).resolve().parent.parent / "screenshots/furnishing-quick-search-light.png"))
    popup.hide()
    main.SetThemes(*themes, notify = False)
    main.close()
    print("PASS: Space search, shared matching, arrows/Enter/click, original placement point, undo, cancellation, focus, bounds and export guards.")


if __name__ == "__main__":
    Main()
