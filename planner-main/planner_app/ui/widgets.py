"""Reusable sidebar controls, menus, drag buttons and wrapping icon layout."""

from PySide6 import QtCore, QtGui, QtWidgets
import math
import re

from planner_app.graphics.palette import themeColors
from planner_app.graphics.theme import HeaderIcon, WallPresetIcon, BuildCanvasStyle
from planner_app.graphics.furnishings import FurnishingRenderer
from planner_app.preferences import wallPresetWidths
from planner_app.graphics.icons import UiIcon
from planner_app.units import FormatLength, ParseImperialLength
from planner_app.number_expressions import EvaluateNumberExpression


class SizeLinkButton(QtWidgets.QPushButton):
    def __init__(self, checked = True):
        super().__init__()
        self.setObjectName("propertyIconButton")
        self.setIcon(UiIcon("link"))
        self.setIconSize(QtCore.QSize(24, 24))
        self.setFixedSize(32, 32)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setAccessibleName("Link width and length")
        self.setToolTip("Link width and length for proportional property edits. Canvas handles are unaffected.")
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)


class VisibilityItemDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, tree, rowHeight = None):
        super().__init__(tree)
        self.rowHeight = rowHeight
        tree.setStyleSheet(BuildCanvasStyle())
        tree.viewport().setMouseTracking(True)
        tree.viewport().installEventFilter(self)

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        if self.rowHeight is not None:
            size.setHeight(self.rowHeight)
        return size

    def eventFilter(self, watched, event):
        if event.type() not in (QtCore.QEvent.Type.MouseMove, QtCore.QEvent.Type.Leave):
            return super().eventFilter(watched, event)
        tree = self.parent()
        # During teardown Qt can expose the parent only as its base QWidget.
        if not isinstance(tree, QtWidgets.QTreeWidget):
            return False
        if watched is tree.viewport():
            shape = QtCore.Qt.CursorShape.ArrowCursor
            if event.type() == QtCore.QEvent.Type.MouseMove and tree.isEnabled():
                index = tree.indexAt(event.position().toPoint())
                if index.isValid() and index.flags() & QtCore.Qt.ItemFlag.ItemIsEnabled and index.flags() & QtCore.Qt.ItemFlag.ItemIsUserCheckable:
                    option = QtWidgets.QStyleOptionViewItem()
                    self.initStyleOption(option, index)
                    option.rect = tree.visualRect(index)
                    option.widget = tree
                    checkRect = tree.style().subElementRect(QtWidgets.QStyle.SubElement.SE_ItemViewItemCheckIndicator, option, tree)
                    if checkRect.contains(event.position().toPoint()):
                        shape = QtCore.Qt.CursorShape.PointingHandCursor
            watched.setCursor(shape)
        return super().eventFilter(watched, event)

    def editorEvent(self, event, model, option, index):
        if index.data(QtCore.Qt.ItemDataRole.CheckStateRole) == QtCore.Qt.CheckState.PartiallyChecked.value:
            toggle = False
            if event.type() == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.LeftButton:
                checkOption = QtWidgets.QStyleOptionViewItem(option)
                self.initStyleOption(checkOption, index)
                style = option.widget.style() if option.widget else QtWidgets.QApplication.style()
                checkRect = style.subElementRect(QtWidgets.QStyle.SubElement.SE_ItemViewItemCheckIndicator,
                                                checkOption, option.widget)
                toggle = checkRect.contains(event.position().toPoint())
            elif event.type() == QtCore.QEvent.Type.KeyPress:
                toggle = event.key() in (QtCore.Qt.Key.Key_Space, QtCore.Qt.Key.Key_Select)
            if toggle:
                return model.setData(index, QtCore.Qt.CheckState.Unchecked, QtCore.Qt.ItemDataRole.CheckStateRole)
        return super().editorEvent(event, model, option, index)


class SidebarTabBar(QtWidgets.QTabBar):
    def paintEvent(self, event):
        painter = QtWidgets.QStylePainter(self)
        for tabIndex in range(self.count()):
            option = QtWidgets.QStyleOptionTab()
            self.initStyleOption(option, tabIndex)
            painter.drawControl(QtWidgets.QStyle.ControlElement.CE_TabBarTabShape, option)
            # Draw only the icon; retained tab names still determine the original widths.
            iconRect = QtCore.QRect(option.rect.x() + (option.rect.width() - option.iconSize.width()) // 2,
                                    option.rect.y() + (option.rect.height() - option.iconSize.height()) // 2,
                                    option.iconSize.width(), option.iconSize.height())
            mode = QtGui.QIcon.Mode.Normal if option.state & QtWidgets.QStyle.StateFlag.State_Enabled else QtGui.QIcon.Mode.Disabled
            state = QtGui.QIcon.State.On if option.state & QtWidgets.QStyle.StateFlag.State_Selected else QtGui.QIcon.State.Off
            option.icon.paint(painter, iconRect, QtCore.Qt.AlignmentFlag.AlignCenter, mode, state)

    def tabSizeHint(self, index):
        size = super().tabSizeHint(index)
        compactWidth = max((super(SidebarTabBar, self).tabSizeHint(tabIndex).height()
                            for tabIndex in range(self.count())), default = size.height())
        compactCount = sum(not self.tabText(tabIndex) for tabIndex in range(self.count()))
        if not self.tabText(index):
            size.setWidth(compactWidth)
        else:
            availableWidth = self.parentWidget().contentsRect().width() - compactWidth * compactCount
            size.setWidth(max(1, availableWidth // max(1, self.count() - compactCount)))
        return size

    def sizeHint(self):
        size = super().sizeHint()
        size.setWidth(self.parentWidget().contentsRect().width())
        return size


class SectionHeading(QtWidgets.QWidget):
    def __init__(self, text, iconName = None):
        super().__init__()
        self.setObjectName("sectionHeading")
        self.setAccessibleName(text)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        leadingLine = QtWidgets.QFrame()
        leadingLine.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        leadingLine.setObjectName("sectionHeadingLine")
        layout.addWidget(leadingLine, 1)
        caption = QtWidgets.QWidget()
        caption.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Preferred)
        captionLayout = QtWidgets.QHBoxLayout(caption)
        captionLayout.setContentsMargins(0, 0, 0, 0)
        captionLayout.setSpacing(6)
        self.iconLabel = None
        if iconName is not None:
            iconLabel = QtWidgets.QLabel()
            self.iconLabel = iconLabel
            iconLabel.setFixedSize(18, 18)
            iconLabel.setPixmap(HeaderIcon(iconName).pixmap(18, 18))
            captionLayout.addWidget(iconLabel, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
        label = QtWidgets.QLabel(text)
        self.titleLabel = label
        label.setStyleSheet("font-size: 11pt; font-weight: 700; padding: 4px 0; margin: 0;")
        captionLayout.addWidget(label)
        layout.addWidget(caption)
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        line.setObjectName("sectionHeadingLine")
        layout.addWidget(line, 1)

    def SetContent(self, text, iconName):
        self.titleLabel.setText(text)
        self.setAccessibleName(text)
        if self.iconLabel is not None:
            self.iconLabel.setPixmap(HeaderIcon(iconName).pixmap(18, 18))


class CollapsibleSectionHeading(SectionHeading):
    clicked = QtCore.Signal()

    def __init__(self, text, iconName):
        super().__init__(text, iconName)
        self.arrowLabel = QtWidgets.QLabel()
        self.arrowLabel.setFixedSize(18, 18)
        self.layout().addWidget(self.arrowLabel)
        for child in self.findChildren(QtWidgets.QWidget):
            child.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.SetCollapsed(False)

    def SetCollapsed(self, collapsed):
        self.arrowLabel.setPixmap(UiIcon("arrow_drop_up" if collapsed else "arrow_drop_down").pixmap(18, 18))
        self.setToolTip(("Restore " if collapsed else "Minimize ") + self.titleLabel.text().lower())

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key.Key_Space, QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class DragSlider(QtWidgets.QSlider):
    """Jump on track clicks and track the pointer without Qt's page-repeat timer."""
    def __init__(self, orientation, parent = None):
        super().__init__(orientation, parent)
        self.dragOffset = None
        self.dragAnchor = None

    def SetValueAt(self, position):
        option = QtWidgets.QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_Slider, option,
                                             QtWidgets.QStyle.SubControl.SC_SliderGroove, self)
        handle = self.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_Slider, option,
                                             QtWidgets.QStyle.SubControl.SC_SliderHandle, self)
        if self.orientation() == QtCore.Qt.Orientation.Horizontal:
            dragOffset = handle.width() / 2 if self.dragOffset is None else self.dragOffset
            offset = position.x() - groove.left() - dragOffset
            span = groove.width() - handle.width()
        else:
            dragOffset = handle.height() / 2 if self.dragOffset is None else self.dragOffset
            offset = position.y() - groove.top() - dragOffset
            span = groove.height() - handle.height()
        if self.dragAnchor is not None:
            coordinate = position.x() if self.orientation() == QtCore.Qt.Orientation.Horizontal else position.y()
            delta = (coordinate - self.dragAnchor[0]) * (-1 if option.upsideDown else 1)
            value = self.dragAnchor[1] + round(delta * (self.maximum() - self.minimum()) / max(1, span))
            value = max(self.minimum(), min(self.maximum(), value))
        else:
            value = QtWidgets.QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), round(offset), max(1, span), option.upsideDown)
        self.setSliderPosition(value)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self.isEnabled():
            option = QtWidgets.QStyleOptionSlider()
            self.initStyleOption(option)
            handle = self.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_Slider, option,
                                                 QtWidgets.QStyle.SubControl.SC_SliderHandle, self)
            horizontal = self.orientation() == QtCore.Qt.Orientation.Horizontal
            coordinate = event.position().x() if horizontal else event.position().y()
            start = handle.left() if horizontal else handle.top()
            size = handle.width() if horizontal else handle.height()
            onHandle = handle.contains(event.position().toPoint())
            self.dragOffset = coordinate - start if onHandle else size / 2
            self.dragAnchor = (coordinate, self.sliderPosition()) if onHandle else None
            self.dragStartValue = self.value()
            self.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
            self.setSliderDown(True)
            self.SetValueAt(event.position())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragOffset is not None:
            self.SetValueAt(event.position())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self.dragOffset is not None:
            self.SetValueAt(event.position())
            self.setValue(self.sliderPosition())
            self.dragOffset = None
            self.dragAnchor = None
            self.setSliderDown(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key.Key_Escape and self.dragOffset is not None:
            self.dragOffset = None
            self.dragAnchor = None
            self.setValue(self.dragStartValue)
            self.setSliderDown(False)
            event.accept()
            return
        super().keyPressEvent(event)

    def event(self, event):
        if (event.type() in (QtCore.QEvent.Type.Hide, QtCore.QEvent.Type.UngrabMouse)
                or event.type() == QtCore.QEvent.Type.EnabledChange and not self.isEnabled()):
            if getattr(self, "dragOffset", None) is not None:
                self.dragOffset = None
                self.dragAnchor = None
                self.setSliderDown(False)
        return super().event(event)


class WallWidthSelector(QtWidgets.QWidget):
    def __init__(self, parent = None):
        super().__init__(parent)
        self.widths = wallPresetWidths
        self.unitsMode = "Millimeters"
        self.icons = [WallPresetIcon(index) for index in range(4)]
        self.pressX = None
        self.dragging = False
        self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
        self.setMinimumWidth(164)
        self.slider = DragSlider(QtCore.Qt.Orientation.Horizontal)
        self.slider.setRange(0, len(self.widths) - 1)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(1)
        self.slider.setValue(2)
        self.slider.setAccessibleName("Wall width preset")
        self.slider.setToolTip("Drag to choose a wall width. Press Q to decrease the width or W to increase it.")
        self.slider.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
        self.slider.installEventFilter(self)
        self.slider.valueChanged.connect(self.update)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 52, 12, 0)
        layout.addWidget(self.slider)

    def PresetCenters(self):
        option = QtWidgets.QStyleOptionSlider()
        self.slider.initStyleOption(option)
        centers = []
        for index in range(len(self.widths)):
            option.sliderPosition = index
            option.sliderValue = index
            handle = self.slider.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_Slider,
                                                       option, QtWidgets.QStyle.SubControl.SC_SliderHandle, self.slider)
            centers.append(self.slider.x() + handle.center().x())
        return centers

    def paintEvent(self, event):
        with QtGui.QPainter(self) as painter:
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            font = painter.font()
            font.setPointSize(8)
            painter.setFont(font)
            for index, (width, center) in enumerate(zip(self.widths, self.PresetCenters())):
                selected = index == self.slider.value()
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.setBrush(QtGui.QColor(themeColors["activeBackground"] if selected else themeColors["controlBackground"]))
                painter.drawRoundedRect(QtCore.QRectF(center - 12, 0, 24, 28), 4, 4)
                painter.drawPixmap(round(center - 12), 0, self.icons[index].pixmap(24, 28))
                painter.setPen(QtGui.QColor(themeColors["activeText"] if selected else themeColors["mutedText"]))
                painter.drawText(QtCore.QRectF(center - 22, 30, 44, 18), QtCore.Qt.AlignmentFlag.AlignCenter, FormatLength(width * 10, self.unitsMode, "cm"))

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.pressX = event.globalPosition().x()
            self.startValue = self.slider.value()
            self.dragging = True
            self.slider.setFocus()
            centers = self.PresetCenters()
            localX = self.mapFromGlobal(event.globalPosition().toPoint()).x()
            self.slider.setValue(min(range(len(centers)), key = lambda index: abs(centers[index] - localX)))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.pressX is not None:
            if self.dragging:
                centers = self.PresetCenters()
                localX = self.mapFromGlobal(event.globalPosition().toPoint()).x()
                self.slider.setValue(min(range(len(centers)), key = lambda index: abs(centers[index] - localX)))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self.pressX is not None:
            if not self.dragging:
                centers = self.PresetCenters()
                localX = self.mapFromGlobal(event.globalPosition().toPoint()).x()
                self.slider.setValue(min(range(len(centers)), key = lambda index: abs(centers[index] - localX)))
            self.pressX = None
            self.dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        self.slider.wheelEvent(event)
        event.accept()

    def eventFilter(self, watched, event):
        if watched is self.slider:
            if event.type() == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.LeftButton:
                self.mousePressEvent(event)
                return True
            if event.type() == QtCore.QEvent.Type.MouseMove and self.pressX is not None:
                self.mouseMoveEvent(event)
                return True
            if event.type() == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.LeftButton and self.pressX is not None:
                self.mouseReleaseEvent(event)
                return True
            if event.type() == QtCore.QEvent.Type.KeyPress and event.key() == QtCore.Qt.Key.Key_Escape and self.pressX is not None:
                self.slider.setValue(self.startValue)
                self.pressX = None
                self.dragging = False
                return True
        return super().eventFilter(watched, event)


class RightAlignedMenuToolButton(QtWidgets.QToolButton):
    def showMenu(self):
        menu = self.menu()
        if menu is None:
            return
        menuSize = menu.sizeHint()
        position = (QtCore.QPoint(self.width() + 6, 0) if self.property("menuToRight") else
                    QtCore.QPoint(self.width() - menuSize.width(), self.height()))
        menu.popup(self.mapToGlobal(position))

    def mousePressEvent(self, event):
        option = QtWidgets.QStyleOptionToolButton()
        self.initStyleOption(option)
        menuRect = self.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_ToolButton,
                                              option, QtWidgets.QStyle.SubControl.SC_ToolButtonMenu, self)
        if self.menu() is not None and (event.button() == QtCore.Qt.MouseButton.RightButton or
                (event.button() == QtCore.Qt.MouseButton.LeftButton and menuRect.contains(event.position().toPoint()))):
            self.showMenu()
            event.accept()
            return
        super().mousePressEvent(event)


class DownwardComboBox(QtWidgets.QComboBox):

    def __init__(self, parent = None):
        super().__init__(parent)
        # Qt's menu delegate bypasses styled item padding and selection shapes.
        self.setItemDelegate(QtWidgets.QStyledItemDelegate(self))
        self.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.currentTextChanged.connect(self.UpdateContentWidth)
        for signal in (self.model().rowsInserted, self.model().rowsRemoved, self.model().dataChanged, self.model().modelReset):
            signal.connect(self.UpdateContentWidth)

    def sizeHint(self):
        size = super().sizeHint()
        option = QtWidgets.QStyleOptionComboBox()
        self.initStyleOption(option)
        option.rect = QtCore.QRect(QtCore.QPoint(), size)
        textRect = self.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_ComboBox, option,
                                              QtWidgets.QStyle.SubControl.SC_ComboBoxEditField, self)
        textWidth = max((self.fontMetrics().horizontalAdvance(text)
                         for text in [self.currentText(), *(self.itemText(index) for index in range(self.count()))]), default = 0)
        if any(not self.itemIcon(index).isNull() for index in range(self.count())):
            textWidth += self.iconSize().width() + 4
        # Qt's styled size hint can omit part of the arrow/padding allocation.
        # Use the actual edit-field geometry, leaving a little text clearance.
        size.setWidth(max(size.width(), textWidth + 4 + size.width() - textRect.width()))
        return size

    def minimumSizeHint(self):
        return self.sizeHint()

    def UpdateContentWidth(self):
        if self.isVisible():
            self.setMinimumWidth(self.sizeHint().width())
            self.updateGeometry()

    def showEvent(self, event):
        super().showEvent(event)
        self.UpdateContentWidth()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QtCore.QEvent.Type.StyleChange, QtCore.QEvent.Type.FontChange):
            self.UpdateContentWidth()

    def showPopup(self):
        super().showPopup()
        view = self.view()
        popup = view.window() if view is not None else None
        if popup is None:
            return

        # Stacker anchors the popup below the field, independently of selection.
        globalPosition = self.mapToGlobal(QtCore.QPoint(0, self.height()))
        fieldTop = self.mapToGlobal(QtCore.QPoint()).y()
        available = self.screen().availableGeometry()
        below = available.bottom() + 1 - globalPosition.y()
        above = fieldTop - available.top()
        if popup.height() > below and above > below:
            popup.resize(popup.width(), min(popup.height(), max(1, above)))
            globalPosition.setY(fieldTop - popup.height())
        else:
            popup.resize(popup.width(), min(popup.height(), max(1, below)))
        globalPosition.setX(max(available.left(), min(globalPosition.x(), available.right() + 1 - popup.width())))
        popup.move(globalPosition)
        view.scrollToTop()


class NumberExpressionMixin:
    def IsExpression(self, text):
        # A leading minus remains an absolute negative value for position fields.
        return text.lstrip().startswith(("+", "*", "/", "(")) or bool(re.search(r"(?<![eE])[+*/()-]", text.strip()[1:]))

    def NormalizeExpressionText(self, text):
        if self.prefix():
            text = text.replace(self.prefix(), "")
        suffix = self.suffix().strip()
        if suffix:
            text = text.replace(suffix, "")
        locale = self.locale()
        separator = locale.groupSeparator()
        if separator and not (getattr(self, "feetAndInches", False) and separator == "."):
            text = text.replace(separator, "")
        return text.replace(locale.decimalPoint(), ".").strip()

    def ExpressionValue(self, text):
        if len(text) > 256:
            raise ValueError("Expression is too long.")
        text = self.NormalizeExpressionText(text)
        if getattr(self, "mixedValue", False) and text.startswith(("+", "*", "/")):
            raise ValueError("A mixed field has no single starting value.")
        currentText = self.NormalizeExpressionText(self.textFromValue(self.value()))
        if not getattr(self, "mixedValue", False) and currentText and text.startswith(currentText):
            remainder = text[len(currentText):].lstrip()
            if remainder.startswith(("+", "-", "*", "/")):
                # Appending to a rounded readout must use the stored dimension.
                text = "(" + repr(float(self.value())) + ")" + remainder
        parseLiteral = (lambda value: ParseImperialLength(value, "Feet and Inches") / 304.8) if getattr(self, "feetAndInches", False) else float
        result = EvaluateNumberExpression(text, self.value(), parseLiteral = parseLiteral)
        if isinstance(self, QtWidgets.QSpinBox):
            result = math.copysign(math.floor(abs(result) + .5), result)
            result = int(result)
        if not self.minimum() <= result <= self.maximum():
            raise ValueError("Result is outside the field's limits.")
        return result

    def valueFromText(self, text):
        if self.IsExpression(text):
            try:
                return self.ExpressionValue(text)
            except (ValueError, OverflowError):
                if getattr(self, "mixedValue", False):
                    self.mixedEdited = False
                return self.value()
        return super().valueFromText(text)

    def validate(self, text, position):
        if len(text) > 256:
            return QtGui.QValidator.State.Invalid, text, position
        if self.IsExpression(text):
            # Defer arithmetic until commit, including fields with live numeric previews.
            return QtGui.QValidator.State.Intermediate, text, position
        return super().validate(text, position)

    def fixup(self, text):
        if self.IsExpression(text):
            value = self.valueFromText(text)
            # Feed native commit the full numeric precision, then let the field
            # format its readout. Imperial readouts may display fewer decimals.
            if getattr(self, "feetAndInches", False):
                return f"{value:.{self.decimals()}f} ft"
            number = str(value) if isinstance(self, QtWidgets.QSpinBox) else self.locale().toString(value, "f", self.decimals())
            return self.prefix() + number + self.suffix()
        return super().fixup(text)

    def interpretText(self):
        if self.IsExpression(self.text()):
            self.lineEdit().setText(self.fixup(self.text()))
        super().interpretText()


class ExpressionSpinBox(NumberExpressionMixin, QtWidgets.QSpinBox):
    """Integer editor with the same arithmetic grammar as dimensional fields."""


class UnitSpinBox(NumberExpressionMixin, QtWidgets.QDoubleSpinBox):
    """Decimal imperial editors retain the same numeric signal contract as metric."""
    def setSuffix(self, suffix):
        displayUnit = suffix or (getattr(self, "commonSuffix", "") if getattr(self, "mixedValue", False) else "")
        self.feetAndInches = displayUnit.strip() == "ft"
        self.inchesOnly = displayUnit.strip() == "in"
        if self.feetAndInches:
            self.setDecimals(6)
        elif self.inchesOnly:
            self.setDecimals(5)
        super().setSuffix("" if self.feetAndInches else suffix)

    def textFromValue(self, value):
        if getattr(self, "feetAndInches", False):
            return FormatLength(value * 304.8, "Feet and Inches", decimals = 3)
        if getattr(self, "inchesOnly", False):
            return self.locale().toString(value, "f", 3)
        return super().textFromValue(value)

    def valueFromText(self, text):
        if self.IsExpression(text):
            return super().valueFromText(text)
        if getattr(self, "feetAndInches", False) or getattr(self, "inchesOnly", False):
            currentText = self.textFromValue(self.value())
            # Committing an unchanged rounded readout must retain its stored precision.
            if text.strip() in (currentText, (currentText + self.suffix()).strip()):
                return self.value()
        if getattr(self, "feetAndInches", False):
            try:
                return ParseImperialLength(text, "Feet and Inches") / 304.8
            except ValueError:
                return self.value()
        return super().valueFromText(text)

    def validate(self, text, position):
        if self.IsExpression(text):
            return super().validate(text, position)
        if not getattr(self, "feetAndInches", False):
            return super().validate(text, position)
        try:
            value = ParseImperialLength(text, "Feet and Inches") / 304.8
        except ValueError:
            return QtGui.QValidator.State.Intermediate, text, position
        state = QtGui.QValidator.State.Acceptable if self.minimum() <= value <= self.maximum() else QtGui.QValidator.State.Intermediate
        return state, text, position


class DragSpinBox(UnitSpinBox):
    dragStarted = QtCore.Signal()
    dragFinished = QtCore.Signal(bool)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setToolTip("Drag left or right to adjust. Hold Alt for finer control. Click to type a value.")
        self.pressPosition = None
        self.dragging = False
        self.dragValue = 0.0
        self.mixedEdited = False
        self.lineEdit().textEdited.connect(lambda text: setattr(self, "mixedEdited", True))
        self.lineEdit().installEventFilter(self)

    def textFromValue(self, value):
        if getattr(self, "mixedValue", False) and not self.mixedEdited:
            return ""
        return super().textFromValue(value)

    def eventFilter(self, watched, event):
        if watched is self.lineEdit() and not self.isReadOnly():
            if event.type() == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.LeftButton:
                self.pressPosition = event.globalPosition()
                self.lastDragX = event.globalPosition().x()
            elif event.type() == QtCore.QEvent.Type.MouseMove and self.pressPosition is not None:
                if not self.dragging and abs(event.globalPosition().x() - self.pressPosition.x()) >= QtWidgets.QApplication.startDragDistance():
                    self.interpretText()
                    self.dragValue = self.value()
                    self.dragging = True
                    self.lineEdit().setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
                    self.dragStarted.emit()
                if self.dragging:
                    delta = event.globalPosition().x() - self.lastDragX
                    speed = self.singleStep() / 10
                    if event.modifiers() & QtCore.Qt.KeyboardModifier.AltModifier:
                        speed /= 10
                    self.dragValue = max(self.minimum(), min(self.maximum(), self.dragValue + delta * speed))
                    self.lastDragX = event.globalPosition().x()
                    self.setValue(self.dragValue)
                    return True
            elif event.type() == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.LeftButton:
                self.pressPosition = None
                if self.dragging:
                    self.dragging = False
                    self.lineEdit().unsetCursor()
                    self.dragFinished.emit(False)
                    return True
            elif event.type() == QtCore.QEvent.Type.KeyPress and event.key() == QtCore.Qt.Key.Key_Escape and self.dragging:
                self.dragging = False
                self.pressPosition = None
                self.lineEdit().unsetCursor()
                self.dragFinished.emit(True)
                return True
        return super().eventFilter(watched, event)


class WindowButton(QtWidgets.QPushButton):
    def __init__(self, parent = None, objectType = "window"):
        super().__init__(parent)
        label = objectType.replace("-", " ").title()
        self.setAccessibleName(label)
        self.setObjectName("openingIconButton")
        self.setStyleSheet(BuildCanvasStyle())
        self.setFixedSize(48, 48)
        self.setIconSize(QtCore.QSize(40, 40))
        self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        self.setIcon(UiIcon("objects/" + objectType))
        self.objectType = objectType
        self.pressPosition = None
        self.setToolTip(label.capitalize())

    def mousePressEvent(self, event):
        self.pressPosition = event.position().toPoint() if event.button() == QtCore.Qt.MouseButton.LeftButton else None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self.pressPosition is not None and event.buttons() & QtCore.Qt.MouseButton.LeftButton
                and (event.position().toPoint() - self.pressPosition).manhattanLength() >= QtWidgets.QApplication.startDragDistance()):
            mime = QtCore.QMimeData()
            mime.setData(f"application/x-planner-{self.objectType}", self.objectType.encode())
            drag = QtGui.QDrag(self)
            drag.setMimeData(mime)
            # Paint the symbol only in the canvas. Native drag images can remain
            # cached by Windows even after setPixmap, producing a second symbol.
            dragImage = QtGui.QPixmap(1, 1)
            dragImage.fill(QtCore.Qt.GlobalColor.transparent)
            drag.setPixmap(dragImage)
            drag.setHotSpot(QtCore.QPoint(0, 0))
            self.pressPosition = None
            self.setDown(False)
            viewport = self.window().viewport
            viewport.guiDragActive = True
            viewport.guiDragCancelled = False
            viewport.guiDragKind = self.objectType
            viewport.update()
            try:
                drag.exec(QtCore.Qt.DropAction.CopyAction)
            finally:
                viewport.guiDragActive = False
                viewport.guiDragKind = None
            viewport.doorOrientationLocked = False
            viewport.alignmentGuides = []
            viewport.counterPreview = None
            viewport.arrowPreview = None
            viewport.labelPreview = None
            viewport.windowDropPreview = None
            viewport.inactiveOpeningPreview = None
            viewport.update()
            return
        super().mouseMoveEvent(event)


class FurnishingIconLayout(QtWidgets.QLayout):
    def __init__(self):
        super().__init__()
        self.items = []
        self.cellSize = self.itemMinimumSize = None
        self.setContentsMargins(0, 0, 0, 0)

    def invalidate(self):
        self.cellSize = self.itemMinimumSize = None
        super().invalidate()

    def addItem(self, item):
        self.items.append(item)
        if item.widget() is not None:
            item.widget().installEventFilter(self)
        self.invalidate()

    def eventFilter(self, watched, event):
        if event.type() in (QtCore.QEvent.Type.LayoutRequest, QtCore.QEvent.Type.FontChange,
                            QtCore.QEvent.Type.StyleChange, QtCore.QEvent.Type.ContentsRectChange):
            self.invalidate()
        return False

    def SetWidgets(self, widgets):
        """Retain items shared by consecutive searches, including their parent."""
        remaining = {item.widget(): item for item in self.items}
        self.items = []
        for widget in widgets:
            item = remaining.pop(widget, None)
            if item is None:
                self.addWidget(widget)
                widget.show()
            else:
                self.items.append(item)
        for widget in remaining:
            widget.removeEventFilter(self)
            widget.hide()
        self.invalidate()

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        return self.items[index] if 0 <= index < len(self.items) else None

    def takeAt(self, index):
        if 0 <= index < len(self.items):
            item = self.items.pop(index)
            if item.widget() is not None:
                item.widget().removeEventFilter(self)
            self.invalidate()
            return item
        return None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.ArrangeItems(QtCore.QRect(0, 0, width, 0), apply = False)

    def minimumSize(self):
        if self.itemMinimumSize is None:
            size = QtCore.QSize()
            for item in self.items:
                size = size.expandedTo(item.minimumSize())
            self.itemMinimumSize = size
        return QtCore.QSize(self.itemMinimumSize)

    def sizeHint(self):
        return self.minimumSize()

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.ArrangeItems(rect, apply = True)

    def ArrangeItems(self, rect, apply):
        if not self.items:
            return 0
        if self.cellSize is None:
            size = QtCore.QSize()
            for item in self.items:
                size = size.expandedTo(item.sizeHint())
            self.cellSize = size
        cellWidth, cellHeight = self.cellSize.width(), self.cellSize.height()
        columns = max(1, (rect.width() + 8) // (cellWidth + 8))
        for index, item in enumerate(self.items):
            if apply:
                item.setGeometry(QtCore.QRect(rect.x() + (index % columns) * (cellWidth + 8),
                                              rect.y() + (index // columns) * (cellHeight + 12),
                                              cellWidth, cellHeight))
        rows = (len(self.items) + columns - 1) // columns
        return rows * cellHeight + (rows - 1) * 12


class FurnishingButton(QtWidgets.QPushButton):
    def __init__(self, definition):
        super().__init__()
        self.definition = definition
        self.setObjectName("openingIconButton")
        self.setStyleSheet(BuildCanvasStyle())
        self.setAccessibleName(definition["name"])
        self.setToolTip(definition["name"])
        self.setFixedSize(48, 48)
        self.setIconSize(QtCore.QSize(40, 40))
        self.RefreshIcon()
        self.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        self.pressPosition = None

    def RefreshIcon(self):
        definition = self.definition
        compoundIcon = bool(definition.get("graphicData") and not definition.get("icon"))
        renderer = FurnishingRenderer(definition["graphicData"] if compoundIcon else definition["iconPath"],
            nominalSize = (definition["width"], definition["length"]),
            palette = {"outline": themeColors["icon"], "background": themeColors["fieldBackground"], "missing": themeColors["missing"]})
        pixmap = QtGui.QPixmap(80, 80)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        with QtGui.QPainter(pixmap) as painter:
            if compoundIcon:
                width, length = definition["width"], definition["length"]
            else:
                width, length = max(1, renderer.defaultSize().width()), max(1, renderer.defaultSize().height())
            scale = (72 if compoundIcon else 80) / max(width, length)
            viewBox = renderer.viewBoxF()
            artwork = getattr(renderer, "artworkBounds", viewBox)
            if not viewBox.isEmpty() and artwork != viewBox:
                scale = 72 / max(artwork.width(), artwork.height())
                target = QtCore.QRectF(40 + (viewBox.x() - artwork.center().x()) * scale,
                                      40 + (viewBox.y() - artwork.center().y()) * scale,
                                      viewBox.width() * scale, viewBox.height() * scale)
            else:
                target = QtCore.QRectF((80 - width * scale) / 2, (80 - length * scale) / 2,
                                      width * scale, length * scale)
            renderer.render(painter, target)
        self.setIcon(QtGui.QIcon(pixmap))

    def mousePressEvent(self, event):
        self.pressPosition = event.position().toPoint() if event.button() == QtCore.Qt.MouseButton.LeftButton else None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self.pressPosition is not None and event.buttons() & QtCore.Qt.MouseButton.LeftButton
                and (event.position().toPoint() - self.pressPosition).manhattanLength() >= QtWidgets.QApplication.startDragDistance()):
            self.StartDrag()
            return
        super().mouseMoveEvent(event)

    def StartDrag(self):
        mime = QtCore.QMimeData()
        mime.setData("application/x-planner-furnishing", self.definition["key"].encode())
        drag = QtGui.QDrag(self)
        drag.setMimeData(mime)
        pixmap = QtGui.QPixmap(1, 1)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        drag.setPixmap(pixmap)
        self.pressPosition = None
        self.setDown(False)
        viewport = self.window().viewport
        viewport.guiDragActive = True
        viewport.guiDragCancelled = False
        viewport.guiDragKind = "furnishing"
        viewport.update()
        try:
            drag.exec(QtCore.Qt.DropAction.CopyAction)
        finally:
            viewport.guiDragActive = False
            viewport.guiDragKind = None
            viewport.furnishingPreview = None
            viewport.alignmentGuides = []
            viewport.update()
