"""Header menu construction, themed actions and view commands."""

from PySide6 import QtCore, QtGui, QtWidgets
from pathlib import Path
from planner_app.graphics.theme import HeaderIcon
from planner_app.graphics.icons import UiIcon
from planner_app.graphics.palette import themeColors
from .menus import AddMenuButton, AddSubmenuButton
from .settings import SettingsWindow
from .help_viewer import HelpWindow
from .about import AboutDialog, LicensesDialog


class HeaderMixin:
    def PopulateRecentProjects(self, menu):
        paths = [Path(value) for value in self.appPreferences["recentProjects"]]
        for path in paths:
            duplicates = [other for other in paths if other.name.casefold() == path.name.casefold()]
            label = path.name
            if len(duplicates) > 1:
                depth = 1
                while depth < len(path.parent.parts) and any(
                        other != path and other.parent.parts[-depth:] == path.parent.parts[-depth:] for other in duplicates):
                    depth += 1
                label += " — " + str(Path(*path.parent.parts[-depth:]))
            label = QtGui.QFontMetrics(self.font()).elidedText(label, QtCore.Qt.TextElideMode.ElideMiddle, 420)
            button = AddMenuButton(menu, label, iconName = "Open Project")
            button.setToolTip(str(path))
            button.setEnabled(path.is_file())
            button.clicked.connect(self.fileMenu.hide)
            button.clicked.connect(lambda checked = False, path = path: self.OpenProject(path))

    def BuildHeader(self, sidebarLayout):
        self.editorShortcuts = []
        self.deselectShortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+A"), self)
        self.deselectShortcut.setAutoRepeat(False)
        self.deselectShortcut.activated.connect(self.viewport.DeselectAll)
        self.editorShortcuts.append(self.deselectShortcut)
        sidebarHeader = QtWidgets.QWidget()
        headerLayout = QtWidgets.QHBoxLayout(sidebarHeader)
        headerLayout.setContentsMargins(0, 0, 0, 0)
        headerLayout.setSpacing(6)
        headerLayout.addStretch(1)
        self.headerButtons = {}
        for buttonName in ("File", "Edit", "View", "Settings", "Help"):
            button = QtWidgets.QPushButton()
            button.setObjectName("headerButton")
            button.setAccessibleName(buttonName)
            button.setIcon(HeaderIcon(buttonName))
            button.setIconSize(QtCore.QSize(28, 28))
            button.setFixedSize(34, 32)
            button.setToolTip(f"{buttonName} (coming later)")
            self.headerButtons[buttonName] = button
            headerLayout.addWidget(button)
        self.headerMenus = {}
        self.settingsWindow = None
        self.helpWindow = None
        self.aboutDialog = None
        self.licensesDialog = None
        self.problemsWindow = None
        self.problemsShortcut = QtGui.QShortcut(QtGui.QKeySequence("Alt+P"), self)
        self.problemsShortcut.setAutoRepeat(False)
        self.problemsShortcut.activated.connect(self.ShowProblems)
        self.helpShortcut = QtGui.QShortcut(QtGui.QKeySequence("F1"), self)
        self.helpShortcut.setAutoRepeat(False)
        self.helpShortcut.activated.connect(self.ShowHelp)
        self.headerButtons["Settings"].setToolTip("Settings")
        self.headerButtons["Settings"].clicked.connect(self.ShowSettings)
        self.menuButtons = {}
        fileCommands = {"New Project": self.NewProject, "Open Project": self.OpenProject,
                        "Revert": self.RevertProject,
                        "Save Project": self.SaveProject, "Save Project as": self.SaveProjectAs,
                        "Save startup file": self.SaveStartupFile,
                        "Close Project": self.CloseProject}
        menuIconNames = {"Save startup file": "Save Project", "Keyboard shortcuts": "Help", "Check for Problems…": UiIcon("report")}
        menuItems = {
            "File": (("New Project", "Ctrl + N"), ("Open Project", "Ctrl + O"), None,
                     ("Open Recent", ""), None,
                     ("Revert", ""), None,
                     ("Save Project", "Ctrl + S"), ("Save Project as", "Ctrl + Shift + S"), None,
                     ("Save startup file", ""), None,
                     ("Close Project", "Ctrl + W")),
            "Edit": (("Undo", "Ctrl + Z"), ("Redo", "Ctrl + Shift + Z"), None,
                     ("Cut", "Ctrl + X"), ("Copy", "Ctrl + C"), ("Paste", "Ctrl + V"), None,
                     ("Check for Problems…", "Alt + P")),
            "Help": (("Help", "F1"), ("Keyboard shortcuts", ""), None, ("About", "")),
        }
        for menuName, items in menuItems.items():
            headerButton = self.headerButtons[menuName]
            headerButton.setToolTip(menuName)
            headerButton.setCheckable(True)
            menu = QtWidgets.QMenu(headerButton)
            menu.setObjectName("viewportContextMenu")
            menu.setSeparatorsCollapsible(False)
            self.headerMenus[menuName] = menu
            for item in items:
                if item is None:
                    menu.addSeparator()
                else:
                    label, shortcutText = item
                    if label == "Open Recent":
                        button = AddSubmenuButton(self, menu, "Open Project", label, self.PopulateRecentProjects)
                        button.setMinimumWidth(300)
                        button.setEnabled(bool(self.appPreferences["recentProjects"]))
                        self.menuButtons[label] = button
                        continue
                    button = AddMenuButton(menu, label, shortcutText, iconName = menuIconNames.get(label))
                    self.menuButtons[label] = button
                    if label == "Revert":
                        button.setEnabled(False)
                    if label in fileCommands:
                        button.clicked.connect(lambda checked = False, command = fileCommands[label]: command())
                        if shortcutText:
                            shortcut = QtGui.QShortcut(QtGui.QKeySequence(shortcutText), self)
                            shortcut.setAutoRepeat(False)
                            shortcut.activated.connect(fileCommands[label])
                    elif label == "Undo":
                        button.clicked.connect(self.viewport.Undo)
                    elif label == "Redo":
                        button.clicked.connect(self.viewport.Redo)
                    elif label == "Cut":
                        button.clicked.connect(self.viewport.CutSelection)
                    elif label == "Copy":
                        button.clicked.connect(self.viewport.CopySelection)
                    elif label == "Paste":
                        button.clicked.connect(lambda checked = False: self.viewport.PasteSelection())
                    elif label == "Check for Problems…":
                        button.clicked.connect(self.ShowProblems)
                    elif label == "Help":
                        button.clicked.connect(lambda checked = False: self.ShowHelp())
                    elif label == "Keyboard shortcuts":
                        button.clicked.connect(lambda checked = False: self.ShowHelp("shortcuts.md"))
                    elif label == "About":
                        button.clicked.connect(lambda checked = False: self.ShowAbout())
            headerButton.clicked.connect(lambda checked = False, menuName = menuName: self.ShowHeaderMenu(menuName))
            menu.aboutToShow.connect(lambda headerButton = headerButton: headerButton.setChecked(True))
            menu.aboutToHide.connect(lambda headerButton = headerButton: headerButton.setChecked(False))
        self.fileMenu = self.headerMenus["File"]
        self.editMenu = self.headerMenus["Edit"]
        self.helpMenu = self.headerMenus["Help"]
        viewButton = self.headerButtons["View"]
        viewButton.setToolTip("View")
        viewButton.setCheckable(True)
        self.viewMenu = QtWidgets.QMenu(viewButton)
        self.viewMenu.setObjectName("viewportContextMenu")
        self.viewMenu.setSeparatorsCollapsible(False)
        self.viewOptions = {}
        for item in (("showMeasurements", "Toggle dimensions", "M"),
                     ("showGrid", "Draw Grid", "G"), None,
                     ("referenceImage", "Reference Image", "B"),
                     ("editReferenceImage", "Setup Reference Image", "Alt + B"), None,
                     ("viewportOnlyMode", "Maximize", "F"), None,
                     ("showTips", "Show tips", ""),
                     ("showFpsCounter", "Show FPS counter", "")):
            if item is None:
                self.viewMenu.addSeparator()
                continue
            option, label, shortcutText = item
            if option == "editReferenceImage":
                button = AddMenuButton(self.viewMenu, label, shortcutText, iconName = UiIcon("image"))
                button.clicked.connect(lambda checked = False: self.SetViewOption("editReferenceImage"))
                self.menuButtons[label] = button
                continue
            if option == "viewportOnlyMode":
                button = AddMenuButton(self.viewMenu, label, shortcutText, iconName = "Maximize")
                button.clicked.connect(lambda checked = False: self.SetViewOption("viewportOnlyMode"))
                self.menuButtons[label] = button
                continue
            action = QtWidgets.QWidgetAction(self.viewMenu)
            button = QtWidgets.QPushButton()
            button.setObjectName("viewportMenuItem")
            button.setAccessibleName(label)
            button.setFlat(True)
            button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            button.setMinimumWidth(320)
            row = QtWidgets.QHBoxLayout(button)
            row.setContentsMargins(12, 0, 14, 0)
            row.setSpacing(14)
            iconLabel = QtWidgets.QLabel()
            iconLabel.setFixedSize(18, 18)
            iconLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            iconLabel.setPixmap(HeaderIcon("Check").pixmap(18, 18))
            textLabel = QtWidgets.QLabel(label)
            textLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            row.addWidget(iconLabel)
            row.addWidget(textLabel)
            row.addStretch(1)
            shortcutLabel = QtWidgets.QLabel(shortcutText)
            shortcutLabel.setObjectName("menuShortcutLabel")
            shortcutLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            shortcutLabel.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            shortcutLabel.setMinimumWidth(24)
            row.addWidget(shortcutLabel)
            button.iconLabel = iconLabel
            button.textLabel = textLabel
            button.shortcutLabel = shortcutLabel
            button.clicked.connect(lambda checked = False, option = option: self.SetViewOption(option))
            action.setDefaultWidget(button)
            self.viewMenu.addAction(action)
            self.viewOptions[option] = button
            if not shortcutText:
                continue
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(shortcutText), self)
            shortcut.setAutoRepeat(False)
            shortcut.activated.connect(lambda option = option: self.SetViewOption(option))
            if option in ("showGrid", "showMeasurements", "referenceImage"):
                self.editorShortcuts.append(shortcut)
        self.viewMenu.addSeparator()
        self.activityLogButton = AddMenuButton(self.viewMenu, "Activity Log", iconName = UiIcon("view_list"))
        self.activityLogButton.clicked.connect(lambda checked = False: self.activityLog.Show())
        self.menuButtons["Activity Log"] = self.activityLogButton
        self.referenceImageEditShortcut = QtGui.QShortcut(QtGui.QKeySequence("Alt+B"), self)
        self.referenceImageEditShortcut.setAutoRepeat(False)
        self.referenceImageEditShortcut.activated.connect(lambda: self.SetViewOption("editReferenceImage"))
        self.editorShortcuts.append(self.referenceImageEditShortcut)
        viewButton.clicked.connect(self.ShowViewMenu)
        self.viewMenu.aboutToShow.connect(lambda: viewButton.setChecked(True))
        self.viewMenu.aboutToHide.connect(lambda: viewButton.setChecked(False))
        sidebarLayout.addWidget(sidebarHeader)



    def ShowHeaderMenu(self, menuName):
        if menuName == "File":
            button = self.menuButtons["Revert"]
            enabled = self.projectPath is not None
            button.setEnabled(enabled)
            button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor if enabled else QtCore.Qt.CursorShape.ArrowCursor)
            mode = QtGui.QIcon.Mode.Normal if enabled else QtGui.QIcon.Mode.Disabled
            button.iconLabel.setPixmap(HeaderIcon("Revert").pixmap(QtCore.QSize(18, 18), mode))
        if menuName == "Edit":
            exporting = self.viewport.exportOverlay.active
            for label in ("Cut", "Copy", "Paste"):
                enabled = self.viewport.ReadClipboardSelection() is not None if label == "Paste" else self.viewport.CanCopySelection()
                self.menuButtons[label].setEnabled(not exporting and enabled)
            undo = self.exportPanel.exportUndoHistory if exporting else self.viewport.undoHistory
            redo = self.exportPanel.exportRedoHistory if exporting else self.viewport.redoHistory
            for label, history in (("Undo", undo), ("Redo", redo)):
                button = self.menuButtons[label]
                enabled = bool(history)
                button.setEnabled(enabled)
                button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor if enabled else QtCore.Qt.CursorShape.ArrowCursor)
                mode = QtGui.QIcon.Mode.Normal if enabled else QtGui.QIcon.Mode.Disabled
                button.iconLabel.setPixmap(HeaderIcon(label).pixmap(QtCore.QSize(18, 18), mode))
        headerButton = self.headerButtons[menuName]
        self.headerMenus[menuName].popup(headerButton.mapToGlobal(QtCore.QPoint(0, headerButton.height())))

    def ShowAbout(self):
        if self.aboutDialog is None:
            dialog = AboutDialog(self)
            self.aboutDialog = dialog
            dialog.finished.connect(lambda result: setattr(self, "aboutDialog", None))
            dialog.finished.connect(dialog.deleteLater)
        self.aboutDialog.show()
        self.aboutDialog.raise_()
        self.aboutDialog.activateWindow()

    def ShowLicenses(self):
        if self.licensesDialog is None:
            self.licensesDialog = LicensesDialog(self)
        if self.licensesDialog.isMinimized():
            self.licensesDialog.showNormal()
        self.licensesDialog.show()
        self.licensesDialog.raise_()
        self.licensesDialog.activateWindow()

    def ShowHelp(self, page = "README.md"):
        if self.helpWindow is None:
            self.helpWindow = HelpWindow(self)
        wasClosed = not self.helpWindow.isVisible()
        self.helpWindow.ShowPage(page)
        if wasClosed:
            self.helpWindow.browser.clearHistory()
        if self.helpWindow.isMinimized():
            self.helpWindow.showMaximized()
        else:
            self.helpWindow.show()
        self.helpWindow.raise_()
        self.helpWindow.activateWindow()
        self.helpWindow.browser.setFocus()

    def ShowSettings(self):
        panel = self.exportPanel
        if panel.projectView is not None or self.sidebarTabs.currentWidget() is panel:
            self.sidebarTabs.setCurrentIndex(0)
        if self.settingsWindow is None:
            self.settingsWindow = SettingsWindow(self)
        self.settingsWindow.show()
        self.settingsWindow.raise_()
        self.settingsWindow.activateWindow()

    def RefreshExportActions(self):
        exporting = self.viewport.exportOverlay.active
        for shortcut in self.editorShortcuts:
            shortcut.setEnabled(not exporting)
        for option in ("showGrid", "showMeasurements", "referenceImage"):
            button = self.viewOptions[option]
            button.setEnabled(not exporting)
            button.setCursor(QtCore.Qt.CursorShape.ArrowCursor if exporting else QtCore.Qt.CursorShape.PointingHandCursor)
            button.setToolTip("Use the Export tab controls" if exporting and option != "referenceImage" else
                              "Reference images are unavailable in Export" if exporting else "")
        button = self.menuButtons["Setup Reference Image"]
        enabled = not exporting and bool(self.referenceImage.state and self.referenceImage.state["visible"])
        button.setEnabled(enabled)
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor if enabled else QtCore.Qt.CursorShape.ArrowCursor)
        mode = QtGui.QIcon.Mode.Normal if enabled else QtGui.QIcon.Mode.Disabled
        button.iconLabel.setPixmap(UiIcon("image").pixmap(QtCore.QSize(18, 18), mode))

    def ShowViewMenu(self):
        self.RefreshExportActions()
        view = self.exportPanel.ResolvedView() if self.exportPanel.projectView is not None else None
        for option, button in self.viewOptions.items():
            showMeasurements = view["showMeasurements"] if view is not None else self.viewport.showMeasurements
            measurements = view["measurementVisibility"] if view is not None else self.viewport.measurementVisibility
            enabled = (bool(self.referenceImage.state and self.referenceImage.state["visible"]) if option == "referenceImage" else
                       showMeasurements and any(measurements.values()) if option == "showMeasurements" else
                       (showMeasurements and measurements[option] if view is not None else measurements[option]) if option in measurements
                       else view[option] if view is not None and option in view else getattr(self.viewport, option))
            if option == "showMeasurements":
                label = "Toggle dimensions"
                button.textLabel.setText(label)
                button.setAccessibleName(label)
            if (view is not None and option == "showMeasurements" and enabled
                    and not all(measurements.values())):
                pixmap = QtGui.QPixmap(18, 18)
                pixmap.fill(QtCore.Qt.GlobalColor.transparent)
                painter = QtGui.QPainter(pixmap)
                painter.fillRect(5, 5, 8, 8, QtGui.QColor(themeColors["icon"]))
                painter.end()
                button.iconLabel.setPixmap(pixmap)
            elif enabled:
                button.iconLabel.setPixmap(HeaderIcon("Check").pixmap(18, 18))
            else:
                button.iconLabel.clear()
        viewButton = self.headerButtons["View"]
        self.viewMenu.popup(viewButton.mapToGlobal(QtCore.QPoint(0, viewButton.height())))

    def SetViewOption(self, option):
        if (self.viewport.exportOverlay.active and not self.exportPanel.applying
                and (option in ("referenceImage", "editReferenceImage", "showGrid", "showMeasurements")
                     or option in self.viewport.measurementVisibility)):
            self.viewMenu.hide()
            return
        if option in ("referenceImage", "editReferenceImage"):
            if option == "editReferenceImage" and not (self.referenceImage.state and self.referenceImage.state["visible"]):
                return
            self.viewMenu.hide()
            if option == "referenceImage":
                enabled = not bool(self.referenceImage.state and self.referenceImage.state["visible"])
                self.referenceImage.ToggleVisibility(enabled)
            if option == "editReferenceImage":
                self.sidebarTabs.setCurrentWidget(self.visibilityPage)
                self.referenceImage.Show()
            return
        if option == "viewportOnlyMode":
            self.viewMenu.hide()
            self.ToggleViewportOnlyMode()
            return
        if option in self.viewport.measurementVisibility:
            self.viewport.measurementVisibility[option] = not self.viewport.measurementVisibility[option]
            if self.viewport.measurementVisibility[option]:
                self.viewport.showMeasurements = True
            elif not any(self.viewport.measurementVisibility.values()):
                self.viewport.showMeasurements = False
        elif option == "showMeasurements":
            self.viewport.showMeasurements = not (self.viewport.showMeasurements and any(self.viewport.measurementVisibility.values()))
            if self.viewport.showMeasurements and not any(self.viewport.measurementVisibility.values()):
                self.viewport.measurementVisibility["walls"] = True
        elif option == "showFpsCounter":
            self.viewport.SetFpsCounterVisible(not self.viewport.showFpsCounter)
        else:
            setattr(self.viewport, option, not getattr(self.viewport, option))
        if option == "showMeasurements" or option in self.viewport.measurementVisibility:
            self.RefreshProperties()
        self.viewMenu.hide()
        self.viewport.update()
        if option in ("showTips", "showFpsCounter"):
            self.appPreferences[option] = getattr(self.viewport, option)
            self.SaveAppPreferences()
        else:
            self.viewport.settingsChanged.emit()
        if self.settingsWindow is not None:
            self.settingsWindow.RefreshMeasurementVisibility()
