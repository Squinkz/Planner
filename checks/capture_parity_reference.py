"""Explicitly regenerate reviewed porting examples; never run as a regression check."""
import hashlib
import json
import os
import platform
import re
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

workspace = Path(__file__).resolve().parent.parent
appDirectory = workspace / "planner-main"
sys.path.insert(0, str(appDirectory))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6 import QtCore, QtGui, QtWidgets, __version__ as pysideVersion
from planner_app.graphics import palette
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.models import Door, Furnishing, Wall
from planner_app.project_codec import DecodeProject, EncodeScene
from planner_app.ui.color_picker import ColorPickerDialog
from planner_app.ui.dialogs import AppMessageBox
from planner_app.ui.main_window import MainWindow
from planner_app.ui.settings import SettingsWindow
from planner_app.ui.widgets import DownwardComboBox, DragSlider, DragSpinBox, SectionHeading


def Main():
    reference = appDirectory.parent / "docs" / "parity" / "reference"
    reference.mkdir(parents = True, exist_ok = True)
    app = QtWidgets.QApplication([])
    app.setStyle("Fusion")
    LoadApplicationFonts(app)
    ApplyApplicationTheme(app)
    captures = []
    with tempfile.TemporaryDirectory(prefix = "parity-", dir = workspace / "tmp") as folder:
        os.environ["PLANNER_SESSION_PATH"] = str(Path(folder) / "session.json")
        os.environ["PLANNER_STARTUP_PATH"] = str(Path(folder) / "startup.plan")
        main = MainWindow()
        main.resize(1440, 900)
        main.show()
        app.processEvents()
        main.mainSplitter.setSizes([960, 440])
        v = main.viewport
        wall = Wall(QtCore.QPointF(-2200, 1000), QtCore.QPointF(2200, 1000), 240)
        side = Wall(QtCore.QPointF(-2200, 1000), QtCore.QPointF(-2200, -1400), 240)
        v.walls = [wall, side]
        v.windows = [Door(wall, .5, .7)]
        v.furnishings = [Furnishing(v.furnishingDefinitions["desk"], QtCore.QPointF(100, -500))]
        v.EnsureObjectIds()
        v.SetSelection([(wall, None)])
        v.sceneChanged.emit()
        app.processEvents()

        def Capture(name, root, description):
            root.ensurePolished()
            app.processEvents()
            root.grab().save(str(reference / (name + ".png")))
            controls = []
            types = (QtWidgets.QAbstractButton, QtWidgets.QAbstractSpinBox, QtWidgets.QComboBox,
                     QtWidgets.QLineEdit, QtWidgets.QLabel, QtWidgets.QSlider, QtWidgets.QTabBar,
                     QtWidgets.QScrollArea, QtWidgets.QSplitter, QtWidgets.QTreeWidget)
            for widget in [root, *root.findChildren(QtWidgets.QWidget)]:
                if not widget.isVisibleTo(root) or not isinstance(widget, types):
                    continue
                position = widget.mapTo(root, QtCore.QPoint())
                record = {"class": type(widget).__name__, "name": widget.objectName(),
                          "accessibleName": widget.accessibleName(), "enabled": widget.isEnabled(),
                          "bounds": [position.x(), position.y(), widget.width(), widget.height()],
                          "cursor": widget.cursor().shape().name, "tooltip": widget.toolTip(),
                          "font": {"family": widget.font().family(), "pointSize": widget.font().pointSizeF(),
                                   "pixelSize": widget.font().pixelSize(), "weight": int(widget.font().weight())}}
                if isinstance(widget, (QtWidgets.QLabel, QtWidgets.QAbstractButton, QtWidgets.QLineEdit)):
                    record["text"] = widget.text()
                if isinstance(widget, QtWidgets.QAbstractButton):
                    record.update(checkable = widget.isCheckable(), checked = widget.isChecked())
                if isinstance(widget, QtWidgets.QComboBox):
                    record.update(editable = widget.isEditable(), currentIndex = widget.currentIndex(),
                                  items = [{"text": widget.itemText(index), "data": widget.itemData(index),
                                            "tooltip": widget.itemData(index, QtCore.Qt.ItemDataRole.ToolTipRole)}
                                           for index in range(widget.count())])
                if isinstance(widget, (QtWidgets.QDoubleSpinBox, QtWidgets.QSpinBox, QtWidgets.QSlider)):
                    record.update(minimum = widget.minimum(), maximum = widget.maximum(),
                                  step = widget.singleStep(), value = widget.value())
                if isinstance(widget, QtWidgets.QAbstractSpinBox):
                    record.update(keyboardTracking = widget.keyboardTracking(), buttons = widget.buttonSymbols().name)
                if isinstance(widget, QtWidgets.QDoubleSpinBox):
                    record.update(decimals = widget.decimals(), suffix = widget.suffix())
                if isinstance(widget, QtWidgets.QTabBar):
                    record.update(currentIndex = widget.currentIndex(),
                                  tabs = [{"text": widget.tabText(index), "tooltip": widget.tabToolTip(index)}
                                          for index in range(widget.count())])
                controls.append(record)
            layouts = []
            for layout in root.findChildren(QtWidgets.QLayout):
                margins = layout.contentsMargins()
                parent = layout.parentWidget()
                layouts.append({"class": type(layout).__name__,
                                "parent": parent.objectName() or type(parent).__name__ if parent else None,
                                "margins": [margins.left(), margins.top(), margins.right(), margins.bottom()],
                                "spacing": layout.spacing()})
            payload = {"description": description, "logicalSize": [root.width(), root.height()],
                       "devicePixelRatio": root.devicePixelRatioF(), "controls": controls, "layouts": layouts}
            (reference / (name + ".json")).write_text(json.dumps(payload, indent = 2, ensure_ascii = False), encoding = "utf-8", newline = "\n")
            captures.append({"name": name, "description": description,
                             "image": name + ".png", "metrics": name + ".json"})

        Capture("build", main, "Build, selected wall, properties and toolbar")
        Capture("build-tools-full", main.buildScrollArea.widget(), "Complete Build palette including Misc and Annotations below the fold")
        project = main.BuildProjectData(includeHistory = False)
        decoded = DecodeProject(project, v.furnishingDefinitions)
        restored = SimpleNamespace(walls = decoded[0], windows = decoded[1], furnishings = decoded[2],
                                   objectGroups = decoded[3], hiddenObjects = decoded[4], labels = decoded[7])
        assert EncodeScene(restored) == project["scene"], "Reference project did not round-trip"
        (reference / "example.plan").write_text(json.dumps(project, indent = 2, ensure_ascii = False), encoding = "utf-8", newline = "\n")
        main.sidebarTabs.setCurrentIndex(1)
        Capture("furnish", main, "Furnishing palette, captions, categories and search")
        main.sidebarTabs.setCurrentIndex(2)
        Capture("visibility", main, "Visibility hierarchy and properties layout")
        panel = main.exportPanel
        main.sidebarTabs.setCurrentWidget(panel)
        panel.fileNameField.setText("example.png")
        for name in ("Canvas", "Border", "Grid"):
            panel.sectionButtons[name].setChecked(True)
        for formatName, mode, name in (("PNG", 0, "export-png-digital"),
                                       ("PNG", 1, "export-png-architectural"),
                                       ("SVG", 0, "export-svg-digital"),
                                       ("SVG", 1, "export-svg-architectural")):
            panel.typeField.setCurrentIndex(panel.typeField.findData(formatName))
            panel.scaleModeTabs.setCurrentIndex(mode)
            Capture(name, main, f"{formatName}, {'Architectural' if mode else 'Digital'}; Canvas/Border/Grid expanded")
        panel.typeField.setCurrentIndex(panel.typeField.findData("PNG"))
        for name, button in panel.sectionButtons.items():
            button.setChecked(name == "Composite")
        Capture("composite-disabled", panel.sectionContents["Composite"].parentWidget(), "Vignette off and texture None: labels and controls disabled")
        panel.enableVignetteField.setChecked(True)
        if panel.textureField.count() > 1:
            panel.textureField.setCurrentIndex(1)
        Capture("composite-enabled", panel.sectionContents["Composite"].parentWidget(), "Vignette enabled and first available texture; control ranges/defaults")
        for name, button in panel.sectionButtons.items():
            button.setChecked(True)
        for name, contents in panel.sectionContents.items():
            Capture("export-section-" + name.lower().replace(" ", "-"), contents.parentWidget(), "Complete Export " + name + " section")
        main.sidebarTabs.setCurrentIndex(0)
        picker = ColorPickerDialog(QtGui.QColor("#46a8d2"), main)
        picker.setWindowFlags(QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.FramelessWindowHint)
        picker.adjustSize()
        picker.show()
        Capture("color-picker", picker, "HSV/RGB/hex content; popup positioning and dismissal are tested separately")
        picker.reject()
        main.newWallMaterialField.showPopup()
        Capture("dropdown", main.newWallMaterialField.view().window(), "Styled material dropdown, initial top scroll")
        main.newWallMaterialField.hidePopup()
        main.fileMenu.popup(main.mapToGlobal(QtCore.QPoint(800, 40)))
        Capture("file-menu", main.fileMenu, "Menu row spacing, separators, shortcut alignment and disabled Revert")
        main.fileMenu.hide()
        settings = SettingsWindow(main)
        settings.show()
        for index in range(settings.tabs.count()):
            settings.tabs.setCurrentIndex(index)
            Capture(f"settings-{index}", settings, "Settings: " + settings.tabs.tabText(index))
        settings.tabs.setCurrentIndex(0)
        for index in range(1, settings.buildTabs.count()):
            settings.buildTabs.setCurrentIndex(index)
            Capture(f"settings-build-{index}", settings, "Settings Build: " + settings.buildTabs.tabText(index))
        settings.close()
        board = QtWidgets.QWidget()
        board.setWindowTitle("Control states")
        boardLayout = QtWidgets.QVBoxLayout(board)
        boardLayout.addWidget(SectionHeading("Control states"))
        for label, checked, enabled in (("Idle button", False, True), ("Checked button", True, True),
                                        ("Disabled button", False, False)):
            button = QtWidgets.QPushButton(label)
            button.setCheckable(True)
            button.setChecked(checked)
            button.setEnabled(enabled)
            boardLayout.addWidget(button)
        combo = DownwardComboBox()
        combo.addItems(("Dropdown", "Longer option with room for arrow"))
        boardLayout.addWidget(combo)
        scrub = DragSpinBox()
        scrub.setValue(12.5)
        scrub.setAccessibleName("Scrub field: no arrows")
        boardLayout.addWidget(scrub)
        stepper = QtWidgets.QDoubleSpinBox()
        stepper.setObjectName("settingsValue")
        stepper.setValue(12.5)
        boardLayout.addWidget(stepper)
        slider = DragSlider(QtCore.Qt.Orientation.Horizontal)
        slider.setValue(50)
        boardLayout.addWidget(slider)
        disabledSlider = DragSlider(QtCore.Qt.Orientation.Horizontal)
        disabledSlider.setEnabled(False)
        boardLayout.addWidget(disabledSlider)
        main.RefreshControlCursors(board)
        board.resize(430, board.sizeHint().height())
        board.show()
        Capture("controls", board, "Shared buttons, fields, arrow treatment and sliders")
        app.sendEvent(board.findChildren(QtWidgets.QPushButton)[0], QtCore.QEvent(QtCore.QEvent.Type.Enter))
        board.findChildren(QtWidgets.QPushButton)[0].setAttribute(QtCore.Qt.WidgetAttribute.WA_UnderMouse, True)
        Capture("controls-hover", board, "First button hovered; checked and disabled siblings unchanged")
        board.findChildren(QtWidgets.QPushButton)[0].setDown(True)
        Capture("controls-pressed", board, "First button pressed; checked and disabled siblings unchanged")
        board.close()
        message = AppMessageBox(main)
        message.setWindowTitle("Replace Export")
        message.setText("Replace the existing file?")
        message.setInformativeText("example.png")
        message.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
        message.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)
        message.show()
        Capture("dialog-sizing", message, "Message minimum size and button placement; status icons covered by popup check")
        message.hide()
        message.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        v.SetSelection([(v.walls[0], None)])
        main.SetThemes(uiTheme = "Light UI", canvasTheme = "Light Canvas", notify = False)
        Capture("build-light", main, "Same layout with independent light UI/canvas palettes")
        manifest = {"baseline": "2026-10-17", "python": platform.python_version(), "pyside": pysideVersion,
                    "qt": QtCore.qVersion(), "platform": app.platformName(), "baseStyle": "Fusion",
                    "styleClass": app.style().metaObject().className(),
                    "screen": [app.primaryScreen().size().width(), app.primaryScreen().size().height()],
                    "logicalDpi": app.primaryScreen().logicalDotsPerInch(), "font": app.font().family(),
                    "captures": captures, "sources": {}}
        for name in ("ui/widgets.py", "ui/sidebar.py", "ui/header.py", "ui/export_panel.py", "ui/color_picker.py",
                     "ui/context_submenu.py", "ui/dialogs.py", "ui/main_window.py", "graphics/theme.py",
                     "graphics/palette.py", "viewport/interaction.py", "viewport/furnishing_handles.py", "project_codec.py"):
            path = appDirectory / "planner_app" / name
            manifest["sources"]["planner_app/" + name] = hashlib.sha256(path.read_bytes()).hexdigest()
        (reference / "manifest.json").write_text(json.dumps(manifest, indent = 2), encoding = "utf-8", newline = "\n")
        (reference / "palette.json").write_text(json.dumps(palette.themeDefinitions, indent = 2, ensure_ascii = False), encoding = "utf-8", newline = "\n")
        def StoreStyle(name):
            assets = reference / "style-assets"
            assets.mkdir(exist_ok = True)

            def ArchiveIcon(match):
                source = Path(match.group(1))
                data = source.read_bytes()
                filename = hashlib.sha256(data).hexdigest()[:16] + source.suffix
                (assets / filename).write_bytes(data)
                return 'url("style-assets/' + filename + '")'

            style = re.sub(r'url\("([^\"]+)"\)', ArchiveIcon, app.styleSheet())
            (reference / name).write_text(style, encoding = "utf-8", newline = "\n")

        StoreStyle("resolved-style-light.qss")
        # Save both stylesheet resolutions, avoiding dependence on the final capture's theme.
        main.SetThemes(uiTheme = "Dark UI", canvasTheme = "Dark Canvas", notify = False)
        StoreStyle("resolved-style-dark.qss")
        text = "# Desktop reference gallery\n\nGenerated explicitly by `checks/capture_parity_reference.py`.\n"
        text += "\nOffscreen content captures omit OS frames and do not capture the mouse cursor.\n"
        text += "See `manifest.json` for environment/source hashes, and each JSON for measured control/layout properties.\n\n"
        for capture in captures:
            text += f"## {capture['name']}\n\n{capture['description']}\n\n![{capture['description']}]({capture['image']})\n\n[Metrics]({capture['metrics']})\n\n"
        (reference / "GALLERY.md").write_text(text, encoding = "utf-8", newline = "\n")
        with patch.object(QtWidgets.QMessageBox, "exec", return_value = QtWidgets.QMessageBox.StandardButton.Discard):
            main.close()
    print(f"Captured {len(captures)} parity examples in {reference}")


if __name__ == "__main__":
    Main()
