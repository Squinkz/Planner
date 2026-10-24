"""Properties stay outside the tabs with a user-adjustable one-third split."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner import MainWindow, Stair
from furnishings import Furnishing
from theme import BuildStyle

app = QtWidgets.QApplication([])
QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
app.setStyle("Fusion")
app.setStyleSheet(BuildStyle())
main = MainWindow()
main.show()
app.processEvents()
splitter = main.sidebarContentSplitter
sizes = splitter.sizes()
assert abs(sizes[1] / sum(sizes) - 1 / 3) < .02
assert splitter.widget(0) is main.sidebarTabs and splitter.widget(1) is main.propertiesPanel
assert not main.sidebarTabs.isAncestorOf(main.propertiesPanel)
assert main.propertiesPanel.isAncestorOf(main.propertyFields["length"])
for index in range(main.sidebarTabs.count()):
    main.sidebarTabs.setCurrentIndex(index)
    app.processEvents()
    if main.sidebarTabs.currentWidget() is main.exportPanel:
        assert not main.propertiesPanel.isVisible()
        assert main.ProjectUiState()["propertiesSplitter"] == sizes
    else:
        assert main.propertiesPanel.isVisible() and main.selectionLabel.isVisible()
        assert splitter.sizes() == sizes
main.sidebarTabs.setCurrentIndex(0)
app.processEvents()
assert splitter.sizes() == sizes

# Drag the actual divider, keeping the panel visible and preserving the chosen split.
handle = splitter.handle(1)
position = QtCore.QPointF(handle.rect().center())
globalStart = QtCore.QPointF(handle.mapToGlobal(position.toPoint()))
globalEnd = globalStart + QtCore.QPointF(0, -100)
left = QtCore.Qt.MouseButton.LeftButton
QtTest.QTest.mousePress(handle, left, pos = position.toPoint())
event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(handle.mapFromGlobal(globalEnd.toPoint())),
                         globalEnd, QtCore.Qt.MouseButton.NoButton, left, QtCore.Qt.KeyboardModifier.NoModifier)
QtWidgets.QApplication.sendEvent(handle, event)
event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseButtonRelease, QtCore.QPointF(handle.mapFromGlobal(globalEnd.toPoint())),
                         globalEnd, left, QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier)
QtWidgets.QApplication.sendEvent(handle, event)
adjusted = splitter.sizes()
assert adjusted[1] > sizes[1] + 70
main.sidebarTabs.setCurrentIndex(1)
app.processEvents()
assert splitter.sizes() == adjusted

# Double-click restores the default third, including from the collapsed state.
for collapsed in (False, True):
    main.SetPropertiesCollapsed(collapsed)
    QtTest.QTest.mouseDClick(handle, left)
    QtTest.QTest.mouseRelease(handle, left)
    app.processEvents()
    restored = splitter.sizes()
    assert abs(restored[1] / sum(restored) - 1 / 3) < .02
    assert not main.propertiesCollapsed and main.propertiesScrollArea.isVisible()
    assert not main.propertiesDividerDragging

# Furnishing properties are usable while the Furnish tab stays active.
desk = Furnishing(main.viewport.furnishingDefinitions["desk"])
main.viewport.furnishings = [desk]
main.viewport.SetSelection([(desk, None)])
assert main.propertyFields["width"].isVisible()
assert main.viewport.unitsMode == "Millimeters"
assert main.propertyFields["length"].suffix() == " mm"
main.propertyFields["length"].setValue(800)
assert desk.length == 800 and main.sidebarTabs.currentIndex() == 1
main.viewport.Undo()
assert desk.length == 600

# Compact properties scroll, rather than forcing the divider upward.
stair = Stair(QtCore.QPointF(), QtCore.QPointF(0, 3000))
main.viewport.walls = [stair]
main.viewport.SetSelection([(stair, None)])
splitter.setSizes([700, 140])
app.processEvents()
assert main.propertiesScrollArea.verticalScrollBar().maximum() > 0
assert main.propertiesPanel.isVisible()
main.sidebarPanel.grab().save("screenshots/sidebar-properties-panel.png")
main.close()
print("PASS: persistent tab-independent properties, default third, native divider dragging, Furnish editing and independent scrolling")
