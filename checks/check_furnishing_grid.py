"""Delegate tiles retain wrapping, native drags, cancellation and lazy artwork."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.ui.widgets import FurnishingButton


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    main = MainWindow()
    main.show()
    main.sidebarTabs.setCurrentIndex(1)
    app.processEvents()
    assert not main.findChildren(FurnishingButton), "The catalog still creates per-item buttons"
    assert len(app.allWidgets()) < 1800
    assert len(main.furnishingThumbnails.icons) < 100, "Opening the grid eagerly rendered the entire catalog"
    for grid in main.furnishingCategoryGrids.values():
        assert grid.model().rowCount() > 0
        assert grid.indexWidget(grid.model().index(0, 0)) is None
        last = grid.model().index(grid.model().rowCount() - 1, 0)
        assert grid.visualRect(last).bottom() < grid.viewport().height(), "Last row is clipped inside its view"
    grid = next(iter(main.furnishingCategoryGrids.values()))
    grid.setFocus()
    grid.setCurrentIndex(grid.model().index(0, 0))
    for key in (QtCore.Qt.Key.Key_End, QtCore.Qt.Key.Key_Home,
                *([QtCore.Qt.Key.Key_Down] * 10), QtCore.Qt.Key.Key_PageDown, QtCore.Qt.Key.Key_PageUp):
        QtTest.QTest.keyClick(grid, key)
        app.processEvents()
        selected = grid.visualRect(grid.currentIndex())
        selected.moveTopLeft(grid.viewport().mapTo(main.furnishScrollArea.viewport(), selected.topLeft()))
        assert selected.top() >= 0 and selected.bottom() < main.furnishScrollArea.viewport().height(), (key, selected, grid.currentIndex().row(), grid.verticalScrollBar().value(), main.furnishScrollArea.verticalScrollBar().value(), grid.height())
    grid.scrollTo(grid.model().index(0, 0))
    main.furnishScrollArea.verticalScrollBar().setValue(0)
    index = grid.model().index(0, 0)
    key = index.data(QtCore.Qt.ItemDataRole.UserRole)
    assert key and index.data(QtCore.Qt.ItemDataRole.ToolTipRole)
    position = grid.visualRect(index).center()
    payloads = []

    def ExecDrag(drag, actions):
        v = main.viewport
        assert v.guiDragActive and v.guiDragKind == "furnishing" and not v.guiDragCancelled
        payloads.append(bytes(drag.mimeData().data("application/x-planner-furnishing")).decode())
        event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonPress, QtCore.QPointF(50, 50),
                                 QtCore.QPointF(v.mapToGlobal(QtCore.QPoint(50, 50))), QtCore.Qt.MouseButton.RightButton,
                                 QtCore.Qt.MouseButton.LeftButton | QtCore.Qt.MouseButton.RightButton,
                                 QtCore.Qt.KeyboardModifier.NoModifier)
        app.sendEvent(v, event)
        assert v.guiDragCancelled
        return QtCore.Qt.DropAction.IgnoreAction

    # Exercise QListView's real press/move threshold rather than invoking startDrag directly.
    QtTest.QTest.mousePress(grid.viewport(), QtCore.Qt.MouseButton.LeftButton, pos = position)
    moved = QtCore.QPointF(position + QtCore.QPoint(30, 0))
    move = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, moved,
                            QtCore.QPointF(grid.viewport().mapToGlobal(moved.toPoint())), QtCore.Qt.MouseButton.NoButton,
                            QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
    with patch.object(QtGui.QDrag, "exec", ExecDrag), patch.object(QtGui.QDrag, "cancel") as cancelled:
        app.sendEvent(grid.viewport(), move)
        assert cancelled.call_count == 1
    QtTest.QTest.mouseRelease(grid.viewport(), QtCore.Qt.MouseButton.LeftButton, pos = position)
    assert payloads == [key] and not main.viewport.guiDragActive and main.viewport.guiDragKind is None
    assert main.viewport.furnishingPreview is None and not main.viewport.alignmentGuides
    # Nested category views must let the outer catalog handle wheel scrolling.
    wheel = QtGui.QWheelEvent(QtCore.QPointF(position), QtCore.QPointF(grid.viewport().mapToGlobal(position)),
                             QtCore.QPoint(), QtCore.QPoint(0, -120), QtCore.Qt.MouseButton.NoButton,
                             QtCore.Qt.KeyboardModifier.NoModifier, QtCore.Qt.ScrollPhase.NoScrollPhase, False)
    app.sendEvent(grid.viewport(), wheel)
    assert main.furnishScrollArea.verticalScrollBar().value() > 0
    main.furnishScrollArea.verticalScrollBar().setValue(0)
    main.mainSplitter.setSizes([1100, 300])
    app.processEvents()
    for grid in main.furnishingCategoryGrids.values():
        last = grid.model().index(grid.model().rowCount() - 1, 0)
        assert grid.visualRect(last).bottom() < grid.viewport().height()
        assert not grid.horizontalScrollBar().isVisible() and not grid.verticalScrollBar().isVisible()
    main.ShowFurnishingSearch(main.viewport.DrawingRect().center())
    popup = main.furnishingQuickSearch
    main.SetThemes(uiTheme = "Light UI")
    for row in range(popup.results.count()):
        item = popup.results.item(row)
        definition = main.viewport.furnishingDefinitions[item.data(QtCore.Qt.ItemDataRole.UserRole)]
        assert item.icon().cacheKey() == main.furnishingThumbnails.Icon(definition).cacheKey()
    popup.hide()
    main.MarkProjectClean()
    main.close()
    print("PASS: widget reduction, lazy tiles, wrapping, native drag/cancellation and quick-search theme refresh")


if __name__ == "__main__":
    Main()
