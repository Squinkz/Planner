"""Cursor-anchored furnishing search using the catalog's matching and placement."""
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.furnishing_search import FindFurnishings, FurnishingDimensionText
from planner_app.graphics.icons import UiIcon
from planner_app.graphics.palette import themeColors


class FurnishingResultDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent):
        super().__init__(parent)
        self.dimensionStyle = QtWidgets.QLabel(parent)
        self.dimensionStyle.setObjectName("furnishingDimensions")
        self.dimensionStyle.hide()
        self.dimensionWidth = 64

    def paint(self, painter, option, index):
        row = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(row, index)
        name, icon = row.text, QtGui.QIcon(row.icon)
        row.text, row.icon = "", QtGui.QIcon()
        style = row.widget.style() if row.widget is not None else QtWidgets.QApplication.style()
        painter.save()
        style.drawControl(QtWidgets.QStyle.ControlElement.CE_ItemViewItem, row, painter, row.widget)
        painter.restore()
        active = row.state & (QtWidgets.QStyle.StateFlag.State_Selected | QtWidgets.QStyle.StateFlag.State_MouseOver)
        iconRect = QtCore.QRect(row.rect.left() + 10, row.rect.center().y() - 14, 28, 28)
        dimensionsRect = QtCore.QRect(iconRect.right() + 15, row.rect.top(), self.dimensionWidth, row.rect.height())
        nameLeft = dimensionsRect.right() + 15
        nameRect = QtCore.QRect(nameLeft, row.rect.top(), max(0, row.rect.right() - nameLeft - 10), row.rect.height())
        painter.save()
        icon.paint(painter, iconRect)
        painter.setFont(self.dimensionStyle.font())
        painter.setPen(QtGui.QColor(themeColors["activeText" if active else "mutedText"]))
        dimensions = painter.fontMetrics().elidedText(index.data(QtCore.Qt.ItemDataRole.UserRole + 1),
                                                       QtCore.Qt.TextElideMode.ElideRight, dimensionsRect.width())
        painter.drawText(dimensionsRect, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter, dimensions)
        painter.setFont(option.font)
        painter.setPen(QtGui.QColor(themeColors["activeText" if active else "text"]))
        painter.drawText(nameRect, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
                         painter.fontMetrics().elidedText(name, QtCore.Qt.TextElideMode.ElideRight, nameRect.width()))
        painter.restore()


class FurnishingQuickSearch(QtWidgets.QFrame):
    def __init__(self, mainWindow):
        super().__init__(mainWindow, QtCore.Qt.WindowType.Popup)
        self.mainWindow = mainWindow
        self.viewport = mainWindow.viewport
        self.setObjectName("furnishingQuickSearch")
        self.setAccessibleName("Search furnishings")
        self.preview = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(8)
        searchPanel = QtWidgets.QFrame()
        searchPanel.setObjectName("furnishingQuickSearchField")
        searchLayout = QtWidgets.QHBoxLayout(searchPanel)
        searchLayout.setContentsMargins(8, 4, 8, 4)
        searchLayout.setSpacing(10)
        icon = QtWidgets.QLabel()
        icon.setPixmap(UiIcon("search").pixmap(24, 24))
        icon.setFixedSize(24, 24)
        searchLayout.addWidget(icon)
        self.searchField = QtWidgets.QLineEdit()
        self.searchField.setObjectName("furnishingSearch")
        self.searchField.setAccessibleName("Search furnishings")
        self.searchField.setPlaceholderText("Search...")
        self.searchField.setToolTip(mainWindow.furnishingSearchField.toolTip())
        self.searchField.installEventFilter(self)
        self.searchField.textChanged.connect(self.UpdateResults)
        searchLayout.addWidget(self.searchField, 1)
        layout.addWidget(searchPanel)
        self.results = QtWidgets.QListWidget()
        self.results.setObjectName("furnishingQuickResults")
        self.results.setAccessibleName("Matching furnishings")
        self.results.setIconSize(QtCore.QSize(28, 28))
        self.results.setUniformItemSizes(True)
        self.resultDelegate = FurnishingResultDelegate(self.results)
        self.results.setItemDelegate(self.resultDelegate)
        self.results.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.results.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.results.setMouseTracking(True)
        self.results.currentRowChanged.connect(self.UpdatePreview)
        self.results.itemEntered.connect(self.results.setCurrentItem)
        self.results.itemClicked.connect(self.PlaceCurrent)
        layout.addWidget(self.results)
        self.status = QtWidgets.QLabel()
        self.status.setObjectName("menuShortcutLabel")
        self.status.setMinimumHeight(self.status.fontMetrics().height())
        layout.addWidget(self.status)
        mainWindow.sidebarTabs.currentChanged.connect(self.hide)

    def OpenAt(self, position):
        self.worldPosition = self.viewport.ViewportToWorld(position)
        blocker = QtCore.QSignalBlocker(self.searchField)
        self.searchField.clear()
        del blocker
        drawingRect = self.viewport.DrawingRect()
        self.setFixedWidth(min(420, int(drawingRect.width()) - 16))
        self.visibleRows = max(1, min(8, int((drawingRect.height() - 100) / 40)))
        self.UpdateResults()
        self.adjustSize()
        available = QtCore.QRect(self.viewport.mapToGlobal(drawingRect.topLeft().toPoint()), drawingRect.size().toSize())
        screen = QtGui.QGuiApplication.screenAt(self.viewport.mapToGlobal(position.toPoint()))
        if screen is not None:
            available = available.intersected(screen.availableGeometry())
        origin = self.viewport.mapToGlobal(position.toPoint())
        self.move(max(available.left(), min(origin.x(), available.right() - self.width() + 1)),
                  max(available.top(), min(origin.y(), available.bottom() - self.height() + 1)))
        self.show()
        self.searchField.setFocus(QtCore.Qt.FocusReason.PopupFocusReason)

    def UpdateResults(self):
        matches = FindFurnishings(self.viewport.furnishingDefinitions.values(), self.searchField.text(), self.viewport.unitsMode)
        blocker = QtCore.QSignalBlocker(self.results)
        self.results.clear()
        self.resultDelegate.dimensionStyle.ensurePolished()
        dimensionMetrics = self.resultDelegate.dimensionStyle.fontMetrics()
        dimensionWidth = 64
        for definition in matches:
            item = QtWidgets.QListWidgetItem(self.mainWindow.furnishingThumbnails.Icon(definition), definition["name"].strip())
            item.setData(QtCore.Qt.ItemDataRole.UserRole, definition["key"])
            dimensions = FurnishingDimensionText(definition, self.viewport.unitsMode)
            item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, dimensions)
            dimensionWidth = max(dimensionWidth, dimensionMetrics.horizontalAdvance(dimensions))
            item.setSizeHint(QtCore.QSize(0, 40))
            categories = definition.get("categories", [definition["category"]])
            item.setToolTip(definition["name"].strip() + "\n" + dimensions + "\n" + ", ".join(categories))
            self.results.addItem(item)
        self.resultDelegate.dimensionWidth = min(144, dimensionWidth)
        self.results.setFixedHeight(40 * min(self.visibleRows, max(1, len(matches))) + 2)
        self.results.setCurrentRow(0 if matches else -1)
        del blocker
        self.UpdatePreview()

    def UpdatePreview(self, row = None):
        v = self.viewport
        item = self.results.currentItem()
        definition = v.furnishingDefinitions.get(item.data(QtCore.Qt.ItemDataRole.UserRole)) if item is not None else None
        self.preview = (v.FindFurnishingPlacement(v.WorldToViewport(self.worldPosition), definition,
                                                QtWidgets.QApplication.keyboardModifiers()) if definition is not None else None)
        v.furnishingPreview = self.preview
        if self.preview is None:
            v.alignmentGuides = []
            self.status.setText("No results")
        elif not v.FurnishingFits(self.preview):
            self.status.setText("Not enough space here.")
        else:
            self.status.clear()
        self.status.setVisible(bool(self.status.text()))
        if self.isVisible():
            self.adjustSize()
        v.update()

    def PlaceCurrent(self, item = None):
        if not self.isVisible() or self.viewport.exportOverlay.active:
            return
        self.UpdatePreview()
        obj = self.preview
        v = self.viewport
        if obj is None or not v.FurnishingFits(obj):
            return
        before = v.CaptureState()
        self.hide()
        v.furnishings.append(obj)
        v.SetSelection([(obj, None)])
        v.RecordEdit(before)
        v.setFocus()
        v.update()

    def eventFilter(self, watched, event):
        if watched is self.searchField and event.type() == QtCore.QEvent.Type.KeyPress:
            key = event.key()
            if key in (QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Down):
                count = self.results.count()
                if count:
                    step = 1 if key == QtCore.Qt.Key.Key_Down else -1
                    # Scrolling can emit itemEntered under a stationary pointer.
                    # Keep keyboard selection stable while updating its preview.
                    blocker = QtCore.QSignalBlocker(self.results)
                    self.results.setCurrentRow((self.results.currentRow() + step) % count)
                    self.UpdatePreview()
                    self.results.scrollToItem(self.results.currentItem())
                    del blocker
                return True
            if key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                if not event.isAutoRepeat():
                    self.PlaceCurrent()
                return True
            if key == QtCore.Qt.Key.Key_Escape:
                self.hide()
                self.viewport.setFocus()
                return True
        return super().eventFilter(watched, event)

    def hideEvent(self, event):
        if self.viewport.furnishingPreview is self.preview:
            self.viewport.furnishingPreview = None
            self.viewport.alignmentGuides = []
        self.preview = None
        self.viewport.update()
        super().hideEvent(event)
