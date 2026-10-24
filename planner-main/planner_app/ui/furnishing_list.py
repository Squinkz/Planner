"""Categorized furnishing rows sharing quick-search painting and catalog drags."""
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.palette import themeColors
from .furnishing_quick_search import FurnishingResultDelegate


class FurnishingListDelegate(FurnishingResultDelegate):
    def __init__(self, parent):
        super().__init__(parent)
        self.headingStyle = QtWidgets.QLabel(parent)
        self.headingStyle.setObjectName("objectSubheading")
        self.headingStyle.hide()

    def paint(self, painter, option, index):
        if index.data(QtCore.Qt.ItemDataRole.UserRole) is not None:
            return super().paint(painter, option, index)
        painter.save()
        heading = index.data(QtCore.Qt.ItemDataRole.UserRole + 2)
        painter.setFont(self.headingStyle.font() if heading else option.font)
        painter.setPen(QtGui.QColor(themeColors["text" if heading else "mutedText"]))
        painter.drawText(option.rect.adjusted(10, 0, -10, 0),
                         QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter, index.data())
        painter.restore()


class FurnishingCatalogList(QtWidgets.QListWidget):
    def __init__(self, mainWindow):
        super().__init__(mainWindow.furnishPage)
        self.mainWindow = mainWindow
        self.resultKey = None
        self.setObjectName("furnishingCatalogList")
        self.setAccessibleName("Furnishings list")
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setViewportMargins(4, 0, 4, 0)
        self.setIconSize(QtCore.QSize(28, 28))
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setDragEnabled(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DragOnly)
        self.setMouseTracking(True)
        self.resultDelegate = FurnishingListDelegate(self)
        self.setItemDelegate(self.resultDelegate)

    def UpdateItems(self, results, query):
        main = self.mainWindow
        if main.furnishingSortMode != "Category":
            sections = [("Search Results" if query else None, [definition["key"] for definition in results])]
        elif query:
            sections = [("Search Results", [definition["key"] for definition in results if definition["key"] != "null"])]
        else:
            sections = [(category, [key for key, cardCategory in main.furnishingCategoryCards if cardCategory == category])
                        for category in main.furnishingCategoryWidgets]
            if main.furnishingSortDescending:
                sections = [(category, keys[::-1]) for category, keys in reversed(sections)]
        key = (tuple((category, tuple(keys)) for category, keys in sections), main.viewport.unitsMode)
        if key == self.resultKey:
            return
        self.resultKey = key
        self.setUpdatesEnabled(False)
        try:
            self.clear()
            for category, keys in sections:
                if category is not None:
                    heading = QtWidgets.QListWidgetItem(category)
                    heading.setData(QtCore.Qt.ItemDataRole.UserRole + 2, True)
                    heading.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
                    heading.setSizeHint(QtCore.QSize(0, 32))
                    self.addItem(heading)
                for key in keys:
                    definition = main.viewport.furnishingDefinitions[key]
                    dimensions = main.furnishingDimensionLabels[key].text()
                    item = QtWidgets.QListWidgetItem(main.furnishingButtons[key].icon(), definition["name"].strip())
                    item.setData(QtCore.Qt.ItemDataRole.UserRole, key)
                    item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, dimensions)
                    item.setSizeHint(QtCore.QSize(0, 40))
                    item.setToolTip(definition["name"].strip() + "\n" + dimensions + "\n" +
                                    ", ".join(definition.get("categories", [definition["category"]])))
                    self.addItem(item)
            if query and not sections[0][1]:
                empty = QtWidgets.QListWidgetItem("No results")
                empty.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
                empty.setSizeHint(QtCore.QSize(0, 40))
                self.addItem(empty)
            self.RefreshIcons()
            self.verticalScrollBar().setValue(0)
        finally:
            self.setUpdatesEnabled(True)

    def RefreshIcons(self):
        self.resultDelegate.dimensionStyle.ensurePolished()
        self.resultDelegate.headingStyle.ensurePolished()
        metrics = self.resultDelegate.dimensionStyle.fontMetrics()
        dimensionWidth = 64
        for row in range(self.count()):
            item = self.item(row)
            key = item.data(QtCore.Qt.ItemDataRole.UserRole)
            button = self.mainWindow.furnishingButtons.get(key)
            if button is not None:
                item.setIcon(button.icon())
                dimensionWidth = max(dimensionWidth, metrics.horizontalAdvance(item.data(QtCore.Qt.ItemDataRole.UserRole + 1)))
        self.resultDelegate.dimensionWidth = min(144, dimensionWidth)
        self.viewport().update()

    def mouseMoveEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        furnishing = item is not None and item.data(QtCore.Qt.ItemDataRole.UserRole) is not None
        self.viewport().setCursor(QtCore.Qt.CursorShape.OpenHandCursor if furnishing else QtCore.Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        key = item.data(QtCore.Qt.ItemDataRole.UserRole) if item is not None else None
        button = self.mainWindow.furnishingButtons.get(key)
        if button is not None:
            button.StartDrag()
