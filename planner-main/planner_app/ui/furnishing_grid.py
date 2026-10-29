"""Wrapping furnishing tiles painted by delegates instead of per-item widgets."""
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.palette import themeColors
from .widgets import StartFurnishingDrag


class FurnishingGridModel(QtCore.QAbstractListModel):
    def __init__(self, mainWindow, parent):
        super().__init__(parent)
        self.mainWindow = mainWindow
        self.keys = ()

    def rowCount(self, parent = QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.keys)

    def data(self, index, role = QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.keys):
            return None
        key = self.keys[index.row()]
        definition = self.mainWindow.viewport.furnishingDefinitions[key]
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return definition["name"]
        if role == QtCore.Qt.ItemDataRole.UserRole:
            return key
        if role == QtCore.Qt.ItemDataRole.UserRole + 1:
            return self.mainWindow.furnishingDimensions[key]
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            return (definition["name"].strip() + "\n" + self.mainWindow.furnishingDimensions[key] + "\n" +
                    ", ".join(definition.get("categories", [definition["category"]])))

    def flags(self, index):
        return (QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable |
                QtCore.Qt.ItemFlag.ItemIsDragEnabled) if index.isValid() else QtCore.Qt.ItemFlag.NoItemFlags

    def SetKeys(self, keys):
        keys = tuple(keys)
        if keys != self.keys:
            self.beginResetModel()
            self.keys = keys
            self.endResetModel()


class FurnishingTileDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, view):
        super().__init__(view)
        self.view = view
        # A few hidden style probes preserve QSS fonts and button states without
        # creating controls, captions or dimension labels for each catalog item.
        self.buttonStyle = QtWidgets.QPushButton(view)
        self.buttonStyle.setObjectName("openingIconButton")
        self.buttonStyle.hide()
        self.dimensionStyle = QtWidgets.QLabel(view)
        self.dimensionStyle.setObjectName("furnishingDimensions")
        self.dimensionStyle.hide()
        self.captionStyle = QtWidgets.QLabel(view)
        self.captionStyle.setObjectName("openingIconCaption")
        self.captionStyle.hide()

    def sizeHint(self, option, index):
        return QtCore.QSize(64, self.view.cellHeight - 12)

    def paint(self, painter, option, index):
        main = self.view.mainWindow
        definition = main.viewport.furnishingDefinitions[index.data(QtCore.Qt.ItemDataRole.UserRole)]
        left, top = option.rect.x(), option.rect.y()
        button = QtWidgets.QStyleOptionButton()
        button.initFrom(self.buttonStyle)
        button.rect = QtCore.QRect(left + 8, top, 48, 48)
        if option.state & QtWidgets.QStyle.StateFlag.State_MouseOver:
            button.state |= QtWidgets.QStyle.StateFlag.State_MouseOver
        if option.state & QtWidgets.QStyle.StateFlag.State_Selected:
            button.state |= QtWidgets.QStyle.StateFlag.State_HasFocus
        painter.save()
        self.buttonStyle.style().drawControl(QtWidgets.QStyle.ControlElement.CE_PushButton, button, painter, self.buttonStyle)
        mode = QtGui.QIcon.Mode.Normal if option.state & QtWidgets.QStyle.StateFlag.State_Enabled else QtGui.QIcon.Mode.Disabled
        main.furnishingThumbnails.Icon(definition).paint(painter, QtCore.QRect(left + 12, top + 4, 40, 40), mode = mode)
        y = top + 52
        for probe, text, color in ((self.dimensionStyle, index.data(QtCore.Qt.ItemDataRole.UserRole + 1), "mutedText"),
                                   (self.captionStyle, definition["name"], "text")):
            painter.setFont(probe.font())
            painter.setPen(QtGui.QColor(themeColors[color]))
            flags = QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.TextFlag.TextWordWrap
            bounds = painter.fontMetrics().boundingRect(QtCore.QRect(0, 0, 64, 10000), flags, text)
            painter.drawText(QtCore.QRect(left, y, 64, bounds.height()), flags, text)
            y += bounds.height() + 4
        painter.restore()


class FurnishingGridView(QtWidgets.QListView):
    def __init__(self, mainWindow):
        super().__init__()
        self.mainWindow = mainWindow
        self.setObjectName("furnishingGrid")
        self.setAccessibleName("Furnishing tiles")
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        self.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.setMovement(QtWidgets.QListView.Movement.Static)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.viewport().setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        self.setDragEnabled(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DragOnly)
        self.catalogModel = FurnishingGridModel(mainWindow, self)
        self.setModel(self.catalogModel)
        self.tileDelegate = FurnishingTileDelegate(self)
        self.setItemDelegate(self.tileDelegate)
        self.setUniformItemSizes(True)
        self.cellHeight = 100

    def SetKeys(self, keys):
        self.catalogModel.SetKeys(keys)
        self.RefreshMetrics()

    def RefreshMetrics(self):
        delegate = self.tileDelegate
        for probe in (delegate.buttonStyle, delegate.dimensionStyle, delegate.captionStyle):
            probe.ensurePolished()
        dimensionMetrics = delegate.dimensionStyle.fontMetrics()
        captionMetrics = delegate.captionStyle.fontMetrics()
        flags = QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.TextFlag.TextWordWrap
        bounds = QtCore.QRect(0, 0, 64, 10000)
        height = 48
        for key in self.catalogModel.keys:
            definition = self.mainWindow.viewport.furnishingDefinitions[key]
            height = max(height, 56 + dimensionMetrics.boundingRect(bounds, flags, self.mainWindow.furnishingDimensions[key]).height() +
                         captionMetrics.boundingRect(bounds, flags, definition["name"]).height())
        self.cellHeight = height + 12
        self.setGridSize(QtCore.QSize(72, self.cellHeight))
        self.UpdateHeight()
        self.viewport().update()

    def UpdateHeight(self):
        columns = max(1, self.viewport().width() // 72)
        rows = (len(self.catalogModel.keys) + columns - 1) // columns
        height = max(1, rows * self.cellHeight)
        if self.height() != height:
            self.setFixedHeight(height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.UpdateHeight()

    def wheelEvent(self, event):
        # Category views expand to their full height; the outer catalog owns
        # scrolling, including smooth pixel deltas from precision touchpads.
        self.mainWindow.furnishScrollArea.wheelEvent(event)

    def scrollTo(self, index, hint = QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible):
        super().scrollTo(index, hint)
        scrollArea = getattr(self.mainWindow, "furnishScrollArea", None)
        if scrollArea is None or not index.isValid() or not self.isVisible() or not scrollArea.isVisible():
            return
        rect = self.visualRect(index)
        if rect.isEmpty():
            return
        rect.moveTopLeft(self.viewport().mapTo(scrollArea.widget(), rect.topLeft()))
        scrollbar = scrollArea.verticalScrollBar()
        height = scrollArea.viewport().height()
        if hint == QtWidgets.QAbstractItemView.ScrollHint.PositionAtTop:
            scrollbar.setValue(rect.top())
        elif hint == QtWidgets.QAbstractItemView.ScrollHint.PositionAtBottom:
            scrollbar.setValue(rect.bottom() - height + 1)
        elif hint == QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter:
            scrollbar.setValue(rect.center().y() - height // 2)
        elif rect.top() < scrollbar.value():
            scrollbar.setValue(rect.top())
        elif rect.bottom() >= scrollbar.value() + height:
            scrollbar.setValue(max(rect.top(), rect.bottom() - height + 1))

    def currentChanged(self, current, previous):
        super().currentChanged(current, previous)
        # Qt can skip scrollTo when a tile fits the expanded inner viewport.
        # Selection changes must also account for the smaller outer viewport.
        self.scrollTo(current)

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        if event.key() in (QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Right, QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Down,
                           QtCore.Qt.Key.Key_Home, QtCore.Qt.Key.Key_End, QtCore.Qt.Key.Key_PageUp, QtCore.Qt.Key.Key_PageDown):
            # At a category edge Qt may ignore navigation, letting QScrollArea
            # scroll independently and move the current tile out of sight.
            self.scrollTo(self.currentIndex())
            event.accept()

    def startDrag(self, supportedActions):
        index = self.currentIndex()
        if index.isValid():
            StartFurnishingDrag(self, self.mainWindow.viewport, index.data(QtCore.Qt.ItemDataRole.UserRole))
