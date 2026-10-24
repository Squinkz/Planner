"""All app dropdowns fit text/icons beside arrows and within scrollable panel contents."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Wall
from planner_app.models import Furnishing
from planner_app.ui.settings import SettingsWindow
from planner_app.graphics.theme import ApplyApplicationTheme


def Main():
    with tempfile.TemporaryDirectory(dir = Path(__file__).parent) as folder:
        os.environ["PLANNER_SESSION_PATH"] = str(Path(folder) / "session.json")
        os.environ["PLANNER_STARTUP_PATH"] = str(Path(folder) / "startup.plan")
        app = QtWidgets.QApplication([])
        ApplyApplicationTheme(app)
        main = MainWindow()
        main.show()
        panel = main.exportPanel
        main.sidebarTabs.setCurrentWidget(panel)
        for button in panel.sectionButtons.values():
            button.setChecked(True)
        app.processEvents()
        main.mainSplitter.setSizes([main.width() - 320, 320])
        report, failures = [], []
        def CheckControls(root, scope):
            for combo in root.findChildren(QtWidgets.QComboBox):
                if not combo.isVisible():
                    continue
                option = QtWidgets.QStyleOptionComboBox()
                combo.initStyleOption(option)
                rect = combo.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_ComboBox, option,
                                                   QtWidgets.QStyle.SubControl.SC_ComboBoxEditField, combo)
                textWidth = max((combo.fontMetrics().horizontalAdvance(combo.itemText(index))
                                 + (combo.iconSize().width() + 4 if not combo.itemIcon(index).isNull() else 0)
                                 for index in range(combo.count())), default = 0)
                textWidth = max(textWidth, combo.fontMetrics().horizontalAdvance(combo.currentText()))
                report.append({"scope": scope, "text": combo.currentText(),
                               "width": combo.width(), "textArea": rect.width(), "textWidth": textWidth,
                               "hint": combo.sizeHint().width(), "minimumHint": combo.minimumSizeHint().width(),
                               "minimum": combo.minimumWidth(), "class": type(combo).__name__})
                if textWidth > rect.width():
                    failures.append(report[-1])
                ancestor = combo.parentWidget()
                while ancestor is not None and not isinstance(ancestor, QtWidgets.QScrollArea):
                    ancestor = ancestor.parentWidget()
                if ancestor is not None:
                    left = combo.mapTo(ancestor.viewport(), QtCore.QPoint()).x()
                    scroll = ancestor.horizontalScrollBar()
                    if left + scroll.value() < 0 or left + combo.width() > ancestor.viewport().width() + scroll.maximum() - scroll.value():
                        failures.append({"outsideScrollablePanel": combo.currentText(), "left": left,
                                         "right": left + combo.width(), "panelWidth": ancestor.viewport().width(),
                                         "scrollMaximum": scroll.maximum()})

        for formatName in ("PNG", "SVG"):
            panel.typeField.setCurrentIndex(panel.typeField.findData(formatName))
            for mode in range(2):
                panel.scaleModeTabs.setCurrentIndex(mode)
                app.processEvents()
                CheckControls(panel, f"Export {formatName} mode {mode}")
                scroll = panel.scrollArea.horizontalScrollBar()
                scroll.setValue(scroll.maximum())
                CheckControls(panel, f"Export {formatName} mode {mode} scrolled right")
                scroll.setValue(0)
        for index in range(main.sidebarTabs.count() - 1):
            main.sidebarTabs.setCurrentIndex(index)
            app.processEvents()
            CheckControls(main, f"Sidebar {main.sidebarTabs.tabText(index)}")
        main.sidebarTabs.setCurrentIndex(0)
        wall = Wall(QtCore.QPointF(), QtCore.QPointF(2000, 0))
        main.viewport.walls = [wall]
        main.viewport.EnsureObjectIds()
        main.viewport.SetSelection([(wall, None)])
        app.processEvents()
        CheckControls(main.propertiesPanel, "Object Properties")
        settings = SettingsWindow(main)
        settings.show()
        for index in range(settings.tabs.count()):
            settings.tabs.setCurrentIndex(index)
            app.processEvents()
            CheckControls(settings, f"Settings {settings.tabs.tabText(index)}")
        settings.close()

        def InspectCatalog(dialog):
            dialog.show()
            app.processEvents()
            CheckControls(dialog, "Create Furnishing")
            dialog.reject()
            return QtWidgets.QDialog.DialogCode.Rejected

        main.viewport.furnishings = [Furnishing(main.viewport.furnishingDefinitions["desk"], QtCore.QPointF(index * 2000, -2000))
                                    for index in range(2)]
        with patch.object(QtWidgets.QDialog, "exec", InspectCatalog):
            main.CreateFurnishingFromSelection(main.viewport.furnishings)
        main.sidebarTabs.setCurrentWidget(panel)
        directory = Path(__file__).resolve().parent.parent / "diagnostics"
        (directory / "export-dropdown-sizes.json").write_text(json.dumps(report, indent = 2), encoding = "utf-8")
        panel.scaleModeTabs.setCurrentIndex(0)
        app.processEvents()
        panel.grab().save(str(directory / "export-dropdown-preview.png"))
        main.close()
        assert not failures, failures
        print("PASS: All dropdowns fit text/icons beside arrows and within export, sidebar, properties, settings and furnishing dialogs")


if __name__ == "__main__":
    Main()
