"""Modeless, virtualized activity browser using the application's dialog widgets."""
from datetime import datetime
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.icons import UiIcon


class ActivityTableModel(QtCore.QAbstractTableModel):
    def __init__(self, log, parent):
        super().__init__(parent)
        self.log = log
        self.rows = len(log.entries)
        self.generation = log.generation

    def rowCount(self, parent = QtCore.QModelIndex()):
        return 0 if parent.isValid() else self.rows

    def columnCount(self, parent = QtCore.QModelIndex()):
        return 4

    def headerData(self, section, orientation, role = QtCore.Qt.ItemDataRole.DisplayRole):
        if role == QtCore.Qt.ItemDataRole.DisplayRole and orientation == QtCore.Qt.Orientation.Horizontal:
            return ("Time", "Type", "Activity", "State")[section]
        return None

    def data(self, index, role = QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.log.entries):
            return None
        entry = self.log.entries[index.row()]
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            return entry["details"] or entry["summary"]
        if role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None
        if index.column() == 0:
            return datetime.fromisoformat(entry["time"]).astimezone().strftime("%Y-%m-%d %H:%M:%S") if entry["time"] else "Earlier edit"
        if index.column() == 1:
            return entry["kind"]
        if index.column() == 2:
            return entry["summary"]
        position = self.log.Position(entry)
        if position is not None:
            return position[0] + (" · Current" if position[1] == position[2] else " · Restore available")
        return "History unavailable" if entry["anchor"] else "Read-only"

    def Refresh(self):
        count = len(self.log.entries)
        if self.generation != self.log.generation or count < self.rows:
            self.beginResetModel()
            self.rows, self.generation = count, self.log.generation
            self.endResetModel()
        elif count > self.rows:
            self.beginInsertRows(QtCore.QModelIndex(), self.rows, count - 1)
            self.rows = count
            self.endInsertRows()
        if self.rows:
            self.dataChanged.emit(self.index(0, 0), self.index(self.rows - 1, 3))


class ActivityLogWindow(QtWidgets.QDialog):
    def __init__(self, main):
        super().__init__(main)
        self.log = main.activityLog
        self.setWindowTitle("Activity Log")
        self.setWindowIcon(UiIcon("view_list"))
        self.setModal(False)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QtWidgets.QVBoxLayout(self)
        self.searchField = QtWidgets.QLineEdit()
        self.searchField.setPlaceholderText("Search activity…")
        self.searchField.setAccessibleName("Search activity")
        layout.addWidget(self.searchField)
        self.model = ActivityTableModel(self.log, self)
        self.proxy = QtCore.QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterKeyColumn(-1)
        self.proxy.setFilterCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        self.table = QtWidgets.QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 160)
        self.table.setColumnWidth(1, 115)
        self.table.setColumnWidth(3, 190)
        layout.addWidget(self.table, 1)
        self.details = QtWidgets.QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(110)
        self.details.setAccessibleName("Activity details")
        layout.addWidget(self.details)
        row = QtWidgets.QHBoxLayout()
        self.restoreButton = QtWidgets.QPushButton("Restore to Here")
        self.clearButton = QtWidgets.QPushButton("Clear Log")
        self.closeButton = QtWidgets.QPushButton("Close")
        for button in (self.restoreButton, self.clearButton, self.closeButton):
            button.setAutoDefault(False)
        row.addWidget(self.restoreButton)
        row.addStretch(1)
        row.addWidget(self.clearButton)
        row.addWidget(self.closeButton)
        layout.addLayout(row)
        self.restoreButton.clicked.connect(self.RestoreCurrent)
        self.clearButton.clicked.connect(self.Clear)
        self.closeButton.clicked.connect(self.close)
        self.searchField.textChanged.connect(self.proxy.setFilterFixedString)
        self.table.selectionModel().selectionChanged.connect(self.RefreshActions)
        self.log.changed.connect(self.Refresh)
        self.finished.connect(self.Detach)
        self.resize(950, 560)
        self.Refresh()
        self.table.scrollToBottom()

    def CurrentEntry(self):
        index = self.proxy.mapToSource(self.table.currentIndex())
        return self.log.entries[index.row()] if index.isValid() and index.row() < len(self.log.entries) else None

    def Refresh(self):
        scrollbar = self.table.verticalScrollBar()
        follow = scrollbar.value() == scrollbar.maximum()
        self.model.Refresh()
        self.RefreshActions()
        if follow:
            self.table.scrollToBottom()

    def RefreshActions(self, *unused):
        entry = self.CurrentEntry()
        position = self.log.Position(entry) if entry else None
        self.restoreButton.setEnabled(position is not None and position[1] != position[2])
        self.clearButton.setEnabled(bool(self.log.entries))
        details = ""
        if entry:
            details = entry["summary"] + ("\n\n" + entry["details"] if entry["details"] != entry["summary"] else "")
            if position:
                details += f"\n\nRestores only the {position[0].lower()} state recorded by this entry."
            elif entry["anchor"]:
                details += "\n\nThe undo history for this state is no longer available."
        self.details.setPlainText(details)

    def RestoreCurrent(self):
        entry = self.CurrentEntry()
        if entry is None:
            return
        try:
            self.log.Restore(entry)
        except (ValueError, RuntimeError) as error:
            self.parentWidget().ShowAppMessage("Cannot Restore Activity", "This history state could not be restored.", "error",
                                              informativeText = str(error))
        self.Refresh()

    def Clear(self):
        answer = self.parentWidget().ShowAppMessage("Clear Activity Log", "Clear this project's activity log?", "warning",
            informativeText = "Undo history will remain available. Cleared log entries cannot be restored.",
            standardButtons = QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            defaultButton = QtWidgets.QMessageBox.StandardButton.No)
        if answer == QtWidgets.QMessageBox.StandardButton.Yes:
            self.log.Clear()

    def Detach(self, result):
        self.log.changed.disconnect(self.Refresh)
        self.log.window = None
