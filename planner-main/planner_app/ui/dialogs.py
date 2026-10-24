"""Stacker's themed message boxes, using its status icons and tint colors."""
from PySide6 import QtCore, QtWidgets
from planner_app.graphics.icons import UiIcon, uiIconColors


class AppMessageBox(QtWidgets.QMessageBox):
    def showEvent(self, event):
        super().showEvent(event)
        available = self.screen().availableGeometry()
        self.setMinimumSize(min(440, available.width()), min(180, available.height()))
        self.resize(max(self.width(), self.minimumWidth()), max(self.height(), self.minimumHeight()))


class RecoveryMessageBox(AppMessageBox):
    @QtCore.Slot()
    def QueueRefresh(self):
        self.refreshTimer.start(0)

    @QtCore.Slot()
    def RefreshObjects(self):
        tree = self.recoveryTree
        expanded = {tree.topLevelItem(index).text(0).rsplit(" — ", 1)[0]: tree.topLevelItem(index).isExpanded()
                    for index in range(tree.topLevelItemCount())}
        current = tree.currentItem()
        selectedIds = {id(obj) for obj in current.data(0, QtCore.Qt.ItemDataRole.UserRole)} if current else set()
        tree.clear()
        entries = self.parentWidget().RecoveryObjectEntries()
        tree.setHeaderLabel("Click an entry to select it and zoom to it" if entries else "No missing objects remain")
        for key, objects in sorted(entries.items()):
            count = len(objects)
            parent = QtWidgets.QTreeWidgetItem(tree, [f"{key} — {count} object{'s' if count != 1 else ''}"])
            parent.setData(0, QtCore.Qt.ItemDataRole.UserRole, objects)
            parent.setExpanded(expanded.get(key, True))
            for obj in objects:
                child = QtWidgets.QTreeWidgetItem(parent, [f"Object {obj.objectId}"])
                child.setData(0, QtCore.Qt.ItemDataRole.UserRole, [obj])
                if selectedIds == {id(obj)}:
                    tree.setCurrentItem(child)

    @QtCore.Slot(int)
    def StopUpdates(self, result):
        self.refreshTimer.stop()
        self.parentWidget().viewport.sceneChanged.disconnect(self.QueueRefresh)
        if getattr(self.parentWidget(), "recoveryWindow", None) is self:
            self.parentWidget().recoveryWindow = None


class DialogsMixin:
    def ShowProblems(self):
        if self.problemsWindow is not None:
            self.problemsWindow.Recheck()
            self.problemsWindow.showNormal()
            self.problemsWindow.raise_()
            self.problemsWindow.activateWindow()
            return
        self.exportPanel.SetActive(False)
        if self.referenceImage.active:
            self.referenceImage.Hide()
        self.viewport.CancelInteraction()
        from .problems import ProblemsWindow
        self.problemsWindow = ProblemsWindow(self)
        self.RefreshControlCursors(self.problemsWindow)
        self.problemsWindow.show()

    def ShowGeometryIssue(self, issue):
        message = AppMessageBox(self)
        message.setOption(QtWidgets.QMessageBox.Option.DontUseNativeDialog, True)
        message.setWindowTitle("Project Geometry Issue")
        message.setWindowIcon(UiIcon("warning", uiIconColors["warningTitle"]))
        message.setIconPixmap(UiIcon("warning", uiIconColors["warning"]).pixmap(48, 48))
        message.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        message.setText(issue["object"])
        message.setInformativeText(issue["description"] + "\n\n" + issue["repairText"] + "\n\n" + issue["removeText"])
        buttons = {}
        selection = {"choice": None}
        # QMessageBox needs an escape button to support closing a box with
        # multiple ActionRole buttons. Keep cancellation on Escape/window close.
        cancel = message.addButton(QtWidgets.QMessageBox.StandardButton.Cancel)
        cancel.hide()
        message.setEscapeButton(cancel)
        for action, label, enabled in (("remove", "Remove", True), ("highlight", "Highlight", issue["highlight"]),
                                       ("repair", "Repair", issue["repair"] is not None)):
            button = message.addButton(label, QtWidgets.QMessageBox.ButtonRole.ActionRole)
            button.setEnabled(enabled)
            button.clicked.connect(lambda checked = False, action = action: selection.update(choice = action))
            buttons[action] = button
        message.setDefaultButton(buttons["highlight"] if issue["highlight"] else buttons["repair"] if issue["repair"] is not None else buttons["remove"])
        message.exec()
        return selection["choice"]

    def ShowMoveSpecial(self):
        if self.viewport.exportOverlay.active:
            return
        v = self.viewport
        if not v.SelectionEntries() or v.dragStart is not None or v.pendingWall is not None or v.guiDragActive:
            return
        dialog = getattr(self, "moveSpecialWindow", None)
        if dialog is not None and dialog.isVisible():
            dialog.raise_()
            dialog.activateWindow()
            return
        if dialog is not None:
            dialog.deleteLater()
        from .move_special import MoveSpecialWindow
        self.moveSpecialWindow = MoveSpecialWindow(self)
        self.RefreshControlCursors(self.moveSpecialWindow)
        self.moveSpecialWindow.show()
        self.moveSpecialWindow.xField.setFocus()
        self.moveSpecialWindow.xField.selectAll()

    def ShowAppMessage(self, title, text, kind = "info", informativeText = None, standardButtons = None, defaultButton = None,
                       buttonLabels = None, wrapInformativeText = True, detailedText = None, locateEntries = None):
        message = RecoveryMessageBox(self) if locateEntries is not None else AppMessageBox(self)
        message.setOption(QtWidgets.QMessageBox.Option.DontUseNativeDialog, True)
        message.setWindowTitle(title)
        message.setWindowIcon(UiIcon(kind, uiIconColors[kind + "Title"]))
        message.setIconPixmap(UiIcon(kind, uiIconColors[kind]).pixmap(48, 48))
        message.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        message.setText(text)
        if informativeText:
            message.setInformativeText(informativeText)
        if detailedText:
            message.setDetailedText(detailedText)
        message.setStandardButtons(standardButtons or QtWidgets.QMessageBox.StandardButton.Ok)
        for standardButton, label in (buttonLabels or {}).items():
            message.button(standardButton).setText(label)
        if defaultButton is not None:
            message.setDefaultButton(defaultButton)
        if locateEntries is not None:
            tree = QtWidgets.QTreeWidget(message)
            tree.setObjectName("recoveryObjects")
            tree.setHeaderLabel("Click an entry to select it and zoom to it")
            tree.setMinimumWidth(360)
            tree.setFixedHeight(180)
            message.recoveryTree = tree
            message.RefreshObjects()

            def Locate(item, column = 0):
                objects = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                self.LocateRecoveryObjects(objects)

            tree.itemClicked.connect(Locate)
            tree.itemActivated.connect(Locate)
            layout = message.layout()
            buttonBox = message.findChild(QtWidgets.QDialogButtonBox)
            buttonRow = layout.getItemPosition(layout.indexOf(buttonBox))[0]
            for index in reversed(range(layout.count())):
                row, column, rowSpan, columnSpan = layout.getItemPosition(index)
                if row >= buttonRow:
                    item = layout.takeAt(index)
                    layout.addItem(item, row + 1, column, rowSpan, columnSpan)
            layout.addWidget(tree, buttonRow, 0, 1, layout.columnCount())
        if informativeText and not wrapInformativeText:
            label = message.findChild(QtWidgets.QLabel, "qt_msgbox_informativelabel")
            label.ensurePolished()
            textWidth = label.fontMetrics().horizontalAdvance(informativeText) + 4
            availableWidth = max(200, self.screen().availableGeometry().width() - 200)
            # Let the file path determine the dialog width, wrapping only when
            # a single line would exceed the available screen space.
            label.setMinimumWidth(min(textWidth, availableWidth))
            label.setWordWrap(textWidth > availableWidth)
        if locateEntries is not None:
            previous = getattr(self, "recoveryWindow", None)
            if previous is not None:
                previous.close()
            self.recoveryWindow = message
            message.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
            message.setWindowModality(QtCore.Qt.WindowModality.NonModal)
            message.refreshTimer = QtCore.QTimer(message)
            message.refreshTimer.setSingleShot(True)
            message.refreshTimer.timeout.connect(message.RefreshObjects)
            self.viewport.sceneChanged.connect(message.QueueRefresh)
            message.finished.connect(message.StopUpdates)
            message.show()
            return message
        return message.exec()
