"""Record/replay inherited Qt control behavior that a browser port must make explicit."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

workspace = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(workspace / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtGui, QtTest, QtWidgets
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.ui.main_window import MainWindow
from planner_app.ui.settings import SettingsWindow
from planner_app.ui.widgets import DownwardComboBox, DragSlider, DragSpinBox, VisibilityItemDelegate


def Main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setStyle("Fusion")
    LoadApplicationFonts(app)
    ApplyApplicationTheme(app)
    host = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(host)
    spin = DragSpinBox()
    spin.setDecimals(2)
    spin.setRange(-100, 100)
    spin.setSingleStep(.5)
    spin.setKeyboardTracking(False)
    spin.setValue(10.25)
    layout.addWidget(spin)
    other = QtWidgets.QLineEdit()
    layout.addWidget(other)
    combo = DownwardComboBox()
    combo.addItems(("Alpha", "Beta", "Gamma"))
    layout.addWidget(combo)
    slider = DragSlider(QtCore.Qt.Orientation.Horizontal)
    slider.setRange(0, 100)
    slider.setSingleStep(1)
    slider.setPageStep(10)
    layout.addWidget(slider)
    tabs = QtWidgets.QTabBar()
    for name in ("First", "Second", "Third"):
        tabs.addTab(name)
    layout.addWidget(tabs)
    tree = QtWidgets.QTreeWidget()
    tree.setHeaderHidden(True)
    tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
    tree.setItemDelegate(VisibilityItemDelegate(tree))
    item = QtWidgets.QTreeWidgetItem(tree, ["A category"])
    item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
    item.setCheckState(0, QtCore.Qt.CheckState.PartiallyChecked)
    layout.addWidget(tree)
    host.resize(420, 450)
    host.show()
    app.processEvents()
    observations = {}
    spin.setFocus()
    spin.selectAll()
    QtTest.QTest.keyClicks(spin.lineEdit(), "12.")
    observations["numeric-draft"] = {"text": spin.lineEdit().text(), "value": spin.value()}
    QtTest.QTest.keyClick(spin, QtCore.Qt.Key.Key_Return)
    observations["numeric-enter"] = {"text": spin.lineEdit().text(), "value": spin.value()}
    QtTest.QTest.keyClick(spin, QtCore.Qt.Key.Key_Up)
    observations["numeric-up"] = spin.value()
    other.setFocus()
    center = QtCore.QPointF(spin.rect().center())
    wheel = QtGui.QWheelEvent(center, QtCore.QPointF(spin.mapToGlobal(center.toPoint())),
                             QtCore.QPoint(), QtCore.QPoint(0, 120), QtCore.Qt.MouseButton.NoButton,
                             QtCore.Qt.KeyboardModifier.NoModifier, QtCore.Qt.ScrollPhase.NoScrollPhase, False)
    app.sendEvent(spin, wheel)
    observations["numeric-wheel-without-focus"] = {"value": spin.value(), "focus": spin.hasFocus()}
    spin.setValue(10.25)
    spin.setFocus()
    spin.selectAll()
    QtTest.QTest.keyClicks(spin.lineEdit(), "14.75")
    QtTest.QTest.keyClick(spin.lineEdit(), QtCore.Qt.Key.Key_Escape)
    observations["numeric-escape-without-drag"] = {"text": spin.lineEdit().text(), "value": spin.value()}
    other.setFocus()
    app.processEvents()
    observations["numeric-focus-loss-after-escape"] = spin.value()
    spin.setValue(10.25)
    spin.setFocus()
    spin.lineEdit().setText("-")
    QtTest.QTest.keyClick(spin, QtCore.Qt.Key.Key_Return)
    observations["numeric-incomplete-commit"] = {"text": spin.lineEdit().text(), "value": spin.value()}
    spin.setValue(10.25)
    spin.selectAll()
    QtTest.QTest.keyClicks(spin.lineEdit(), "22")
    QtTest.QTest.keyClick(spin.lineEdit(), QtCore.Qt.Key.Key_Z, QtCore.Qt.KeyboardModifier.ControlModifier)
    observations["numeric-local-text-undo"] = {"text": spin.lineEdit().text(), "value": spin.value()}
    combo.setCurrentIndex(1)
    combo.setFocus()
    QtTest.QTest.keyClick(combo, QtCore.Qt.Key.Key_Down)
    observations["combo-closed-down"] = combo.currentIndex()
    combo.showPopup()
    app.processEvents()
    observations["combo-popup-initial-highlight"] = combo.view().currentIndex().row()
    QtTest.QTest.keyClick(combo.view(), QtCore.Qt.Key.Key_Up)
    observations["combo-popup-up"] = {"value": combo.currentIndex(), "highlight": combo.view().currentIndex().row()}
    QtTest.QTest.keyClick(combo.view(), QtCore.Qt.Key.Key_Escape)
    observations["combo-popup-escape"] = {"value": combo.currentIndex(), "visible": combo.view().isVisible()}
    combo.showPopup()
    app.processEvents()
    observations["combo-popup-reopen-highlight"] = combo.view().currentIndex().row()
    QtTest.QTest.keyClick(combo.view(), QtCore.Qt.Key.Key_Up)
    QtTest.QTest.keyClick(combo.view(), QtCore.Qt.Key.Key_Return)
    observations["combo-popup-enter"] = {"value": combo.currentIndex(), "visible": combo.view().isVisible()}
    slider.setFocus()
    slider.setValue(50)
    QtTest.QTest.keyClick(slider, QtCore.Qt.Key.Key_Right)
    values = [slider.value()]
    QtTest.QTest.keyClick(slider, QtCore.Qt.Key.Key_PageUp)
    values.append(slider.value())
    QtTest.QTest.keyClick(slider, QtCore.Qt.Key.Key_Home)
    values.append(slider.value())
    QtTest.QTest.keyClick(slider, QtCore.Qt.Key.Key_End)
    values.append(slider.value())
    observations["slider-right-pageup-home-end"] = values
    tabs.setCurrentIndex(0)
    tabs.setFocus()
    QtTest.QTest.keyClick(tabs, QtCore.Qt.Key.Key_Right)
    observations["tab-right-activates"] = tabs.currentIndex()
    tabs.setCurrentIndex(2)
    QtTest.QTest.keyClick(tabs, QtCore.Qt.Key.Key_Right)
    observations["tab-right-at-last"] = tabs.currentIndex()
    index = tree.model().index(0, 0)
    option = QtWidgets.QStyleOptionViewItem()
    tree.itemDelegate().initStyleOption(option, index)
    option.rect = tree.visualRect(index)
    option.widget = tree
    check = tree.style().subElementRect(QtWidgets.QStyle.SubElement.SE_ItemViewItemCheckIndicator, option, tree)
    QtTest.QTest.mouseClick(tree.viewport(), QtCore.Qt.MouseButton.LeftButton,
                            pos = QtCore.QPoint(check.right() + 25, check.center().y()))
    observations["tree-caption-click"] = item.checkState(0).name
    QtTest.QTest.mouseClick(tree.viewport(), QtCore.Qt.MouseButton.LeftButton, pos = check.center())
    observations["tree-mixed-checkbox-click"] = item.checkState(0).name
    host.close()
    with tempfile.TemporaryDirectory(prefix = "implicit-ui-", dir = workspace / "tmp") as folder:
        os.environ["PLANNER_SESSION_PATH"] = str(Path(folder) / "session.json")
        os.environ["PLANNER_STARTUP_PATH"] = str(Path(folder) / "startup.plan")
        main = MainWindow()
        main.show()
        settings = SettingsWindow(main)
        settings.show()
        settings.tabs.setCurrentIndex(2)
        app.processEvents()
        field = settings.lineworkFields["walls"]
        field.setFocus()
        field.selectAll()
        QtTest.QTest.keyClicks(field.lineEdit(), "0.37")
        QtTest.QTest.keyClick(field, QtCore.Qt.Key.Key_Return)
        observations["settings-enter-commits-keeps-dialog"] = {"value": field.value(), "visible": settings.isVisible()}
        mode = settings.measurementSliders["doors"]
        observations["measurement-selector-configuration"] = {
            "orientation": mode.orientation().name, "singleStep": mode.singleStep(), "pageStep": mode.pageStep(),
            "invertedAppearance": mode.invertedAppearance(), "invertedControls": mode.invertedControls()}
        settings.close()
        with patch.object(QtWidgets.QMessageBox, "exec", return_value = QtWidgets.QMessageBox.StandardButton.Discard):
            main.close()
    target = workspace / "docs" / "parity" / "reference" / "qt-widget-defaults.json"
    if "--record" in sys.argv:
        data = {"format": "Planner inherited Qt UI behavior", "version": 1,
                "qt": QtCore.qVersion(), "baseStyle": "Fusion", "styleClass": app.style().metaObject().className(),
                "startDragDistance": app.startDragDistance(), "doubleClickInterval": app.doubleClickInterval(),
                "observations": observations}
        target.write_text(json.dumps(data, indent = 2), encoding = "utf-8", newline = "\n")
        print(json.dumps(data, indent = 2))
    else:
        expected = json.loads(target.read_text(encoding = "utf-8"))["observations"]
        assert observations == expected, {key: {"expected": expected.get(key), "actual": value}
                                          for key, value in observations.items() if expected.get(key) != value}
        print(f"PASS: {len(observations)} inherited Qt control observations")


if __name__ == "__main__":
    Main()
