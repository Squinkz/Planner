"""HSV mouse controls and synchronized RGB/HSV/hex color entry."""
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.palette import themeColors
from .widgets import DragSpinBox


class ColorPlane(QtWidgets.QWidget):
    changed = QtCore.Signal(float, float)

    def __init__(self, hueOnly = False, parent = None):
        super().__init__(parent)
        self.hueOnly = hueOnly
        self.hue, self.saturation, self.value = 0.0, 0.0, 1.0
        self.setMinimumSize(32 if hueOnly else 250, 220)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setCursor(QtCore.Qt.CursorShape.CrossCursor)
        self.setAccessibleName("Hue" if hueOnly else "Saturation and value")

    def paintEvent(self, event):
        with QtGui.QPainter(self) as painter:
            rect = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)
            if self.hueOnly:
                gradient = QtGui.QLinearGradient(rect.topLeft(), rect.bottomLeft())
                for index in range(7):
                    gradient.setColorAt(index / 6, QtGui.QColor.fromHsvF((index / 6) % 1, 1, 1))
                painter.fillRect(rect, gradient)
                y = rect.top() + self.hue * rect.height()
                marker = QtCore.QRectF(rect.left(), y - 3, rect.width(), 6)
                painter.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.black, 3))
                painter.drawRect(marker)
                painter.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.white, 1))
                painter.drawRect(marker)
            else:
                saturation = QtGui.QLinearGradient(rect.topLeft(), rect.topRight())
                saturation.setColorAt(0, QtGui.QColor("white"))
                saturation.setColorAt(1, QtGui.QColor.fromHsvF(self.hue, 1, 1))
                painter.fillRect(rect, saturation)
                value = QtGui.QLinearGradient(rect.topLeft(), rect.bottomLeft())
                value.setColorAt(0, QtGui.QColor(QtCore.Qt.GlobalColor.transparent))
                value.setColorAt(1, QtGui.QColor("black"))
                painter.fillRect(rect, value)
                point = QtCore.QPointF(rect.left() + self.saturation * rect.width(),
                                      rect.top() + (1 - self.value) * rect.height())
                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.black, 3))
                painter.drawEllipse(point, 5, 5)
                painter.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.white, 1))
                painter.drawEllipse(point, 5, 5)
            painter.setPen(QtGui.QColor(themeColors["activeBackground"] if self.hasFocus() else themeColors["border"]))
            painter.drawRect(rect)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.setFocus()
            self.mouseMoveEvent(event)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            x = max(0.0, min(1.0, (event.position().x() - 1) / max(1, self.width() - 2)))
            y = max(0.0, min(1.0, (event.position().y() - 1) / max(1, self.height() - 2)))
            self.changed.emit(min(y, .999999) if self.hueOnly else x, 1 - y)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        if key not in (QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Right, QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Down):
            return super().keyPressEvent(event)
        if self.hueOnly:
            delta = -1 if key in (QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Up) else 1
            self.changed.emit((self.hue + delta / 360) % 1, 0)
        else:
            saturation = self.saturation + (.01 if key == QtCore.Qt.Key.Key_Right else -.01 if key == QtCore.Qt.Key.Key_Left else 0)
            value = self.value + (.01 if key == QtCore.Qt.Key.Key_Up else -.01 if key == QtCore.Qt.Key.Key_Down else 0)
            self.changed.emit(max(0, min(1, saturation)), max(0, min(1, value)))
        event.accept()


class ColorPickerDialog(QtWidgets.QDialog):
    colorChanged = QtCore.Signal(QtGui.QColor)

    def __init__(self, initial, parent = None):
        super().__init__(parent)
        self.setWindowTitle("Canvas Color")
        self.color = QtGui.QColor(initial)
        self.hue, self.saturation, self.value = 0.0, 0.0, 1.0
        self.popupAnchor = None
        self.popupArmed = False
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)
        planes = QtWidgets.QHBoxLayout()
        self.svPlane = ColorPlane(parent = self)
        self.huePlane = ColorPlane(hueOnly = True, parent = self)
        self.huePlane.setFixedWidth(32)
        planes.addWidget(self.svPlane, 1)
        planes.addWidget(self.huePlane)
        layout.addLayout(planes)
        fields = QtWidgets.QGridLayout()
        self.rgbFields, self.hsvFields = [], []
        for row, names in enumerate((("Red", "Green", "Blue"), ("Hue", "Sat", "Value"))):
            for column, name in enumerate(names):
                field = DragSpinBox()
                field.setDecimals(0 if row == 0 else 1)
                field.setRange(0, 255 if row == 0 else 360 if column == 0 else 100)
                if row == 1:
                    field.setDecimals(1)
                    field.setSuffix("°" if column == 0 else "%")
                field.setAccessibleName("Saturation" if name == "Sat" else name)
                field.setKeyboardTracking(True)
                label = QtWidgets.QLabel(name)
                label.setBuddy(field)
                fields.addWidget(label, column, row * 2)
                fields.addWidget(field, column, row * 2 + 1)
                (self.rgbFields if row == 0 else self.hsvFields).append(field)
                field.valueChanged.connect(self.SetRgb if row == 0 else self.SetHsv)
        layout.addLayout(fields)
        hexRow = QtWidgets.QHBoxLayout()
        self.swatch = QtWidgets.QLabel()
        self.swatch.setFixedSize(32, 32)
        hexRow.addWidget(self.swatch)
        hexLabel = QtWidgets.QLabel("Hex")
        self.hexField = QtWidgets.QLineEdit()
        self.hexField.setAccessibleName("Hex color")
        self.hexField.setPlaceholderText("#RRGGBB")
        self.hexField.setValidator(QtGui.QRegularExpressionValidator(QtCore.QRegularExpression("#?(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})"), self))
        hexLabel.setBuddy(self.hexField)
        hexRow.addWidget(hexLabel)
        hexRow.addWidget(self.hexField, 1)
        layout.addLayout(hexRow)
        self.setToolTip("Leave the picker to confirm. Right-click or press Escape to cancel.")
        self.hexField.textEdited.connect(self.SetHex)
        self.svPlane.changed.connect(self.SetSv)
        self.huePlane.changed.connect(self.SetHue)
        self.SetColor(self.color)

    def SetColor(self, color):
        self.color = QtGui.QColor(color)
        hue, saturation, value, alpha = self.color.getHsvF()
        if hue >= 0:
            self.hue = hue
        self.saturation, self.value = saturation, value
        self.RefreshFields()

    def RefreshFields(self, updateHex = True):
        blockers = [QtCore.QSignalBlocker(field) for field in self.rgbFields + self.hsvFields]
        for field, value in zip(self.rgbFields, (self.color.red(), self.color.green(), self.color.blue())):
            field.setValue(value)
        for field, value in zip(self.hsvFields, (self.hue * 360, self.saturation * 100, self.value * 100)):
            field.setValue(value)
        if updateHex:
            self.hexField.setText(self.color.name())
        for plane in (self.svPlane, self.huePlane):
            plane.hue, plane.saturation, plane.value = self.hue, self.saturation, self.value
            plane.update()
        swatch = QtGui.QPixmap(32, 32)
        swatch.fill(self.color)
        self.swatch.setPixmap(swatch)
        self.colorChanged.emit(QtGui.QColor(self.color))

    def SetRgb(self):
        self.SetColor(QtGui.QColor(*(round(field.value()) for field in self.rgbFields)))

    def SetHsv(self):
        hue, saturation, value = (field.value() for field in self.hsvFields)
        self.hue = (hue % 360) / 360
        self.saturation, self.value = saturation / 100, value / 100
        self.color = QtGui.QColor.fromHsvF(self.hue, self.saturation, self.value)
        self.RefreshFields()

    def SetHue(self, hue, unused):
        self.hue = hue
        self.color = QtGui.QColor.fromHsvF(self.hue, self.saturation, self.value)
        self.RefreshFields()

    def SetSv(self, saturation, value):
        self.saturation, self.value = saturation, value
        self.color = QtGui.QColor.fromHsvF(self.hue, saturation, value)
        self.RefreshFields()

    def SetHex(self, text):
        valid = self.hexField.hasAcceptableInput()
        if valid:
            digits = text.lstrip("#")
            if len(digits) == 3:
                digits = "".join(character * 2 for character in digits)
            self.color = QtGui.QColor("#" + digits)
            hue, self.saturation, self.value, alpha = self.color.getHsvF()
            if hue >= 0:
                self.hue = hue
            self.RefreshFields(updateHex = False)

    def accept(self):
        # Incomplete text retains the last valid color when dismissing.
        self.hexField.setText(self.color.name())
        super().accept()

    def closeEvent(self, event):
        self.accept()
        event.accept()

    def showEvent(self, event):
        super().showEvent(event)
        if self.popupAnchor is not None:
            self.popupArmed = False
            self.adjustSize()
            anchor = self.popupAnchor
            position = anchor.mapToGlobal(QtCore.QPoint(-self.width() - 4, 0))
            available = anchor.screen().availableGeometry()
            x = max(available.left(), min(position.x(), available.right() - self.width() + 1))
            y = max(available.top(), min(position.y(), available.bottom() - self.height() + 1))
            self.move(x, y)
            for widget in [self, *self.findChildren(QtWidgets.QWidget)]:
                widget.setMouseTracking(True)
            QtWidgets.QApplication.instance().installEventFilter(self)

    def hideEvent(self, event):
        if self.popupAnchor is not None:
            QtWidgets.QApplication.instance().removeEventFilter(self)
        super().hideEvent(event)

    def eventFilter(self, watched, event):
        if self.popupAnchor is not None and self.isVisible():
            if event.type() in (QtCore.QEvent.Type.MouseMove, QtCore.QEvent.Type.MouseButtonPress,
                                QtCore.QEvent.Type.MouseButtonRelease):
                rect = QtCore.QRect(self.mapToGlobal(QtCore.QPoint()), self.size())
                inside = rect.contains(event.globalPosition().toPoint())
                if (inside and event.type() == QtCore.QEvent.Type.MouseButtonPress
                        and event.button() == QtCore.Qt.MouseButton.RightButton):
                    self.reject()
                    return True
                if event.type() == QtCore.QEvent.Type.MouseMove and inside:
                    self.popupArmed = True
                elif not inside and event.type() == QtCore.QEvent.Type.MouseButtonRelease:
                    if self.popupArmed and event.buttons() == QtCore.Qt.MouseButton.NoButton:
                        # A drag ending outside must re-enter before leaving can confirm.
                        self.popupArmed = False
                elif not inside and (event.type() == QtCore.QEvent.Type.MouseButtonPress
                                     or (self.popupArmed and event.buttons() == QtCore.Qt.MouseButton.NoButton)):
                    self.accept()
                    return True
            elif (watched is self and event.type() == QtCore.QEvent.Type.Leave and self.popupArmed
                  and QtWidgets.QApplication.mouseButtons() == QtCore.Qt.MouseButton.NoButton):
                self.accept()
        return super().eventFilter(watched, event)

    @classmethod
    def GetColor(cls, initial, parent = None, preview = None, anchor = None):
        dialog = cls(initial, parent)
        if anchor is not None:
            dialog.popupAnchor = anchor
            dialog.setWindowFlags(QtCore.Qt.WindowType.Popup | QtCore.Qt.WindowType.FramelessWindowHint)
        if preview is not None:
            dialog.colorChanged.connect(preview)
        return QtGui.QColor(dialog.color) if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted else QtGui.QColor()
