"""Exact translation and rotation of the current selection."""
from PySide6 import QtCore, QtWidgets
from planner_app.units import MetricUnit
from planner_app.graphics.icons import UiIcon
from .widgets import UnitSpinBox


class MoveSpecialWindow(QtWidgets.QDialog):
    def __init__(self, mainWindow):
        super().__init__(mainWindow)
        self.mainWindow = mainWindow
        self.setWindowTitle("Transform")
        self.setWindowIcon(UiIcon("translate"))
        self.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        self.divisor, unit = MetricUnit(mainWindow.viewport.unitsMode, "cm")
        for name, label in (("xField", "X"), ("yField", "Y"), ("angleField", "Angle")):
            if name == "angleField":
                spacer = QtWidgets.QWidget()
                spacer.setFixedHeight(8)
                form.addRow(spacer)
            field = UnitSpinBox()
            field.setObjectName("settingsValue")
            field.setKeyboardTracking(False)
            field.setDecimals(3)
            field.setRange(-100000000 / self.divisor, 100000000 / self.divisor)
            field.setSuffix(" " + unit)
            if name == "angleField":
                field.setRange(-360000, 360000)
                field.setSuffix("°")
            field.setAccessibleName(label)
            setattr(self, name, field)
            form.addRow(label, field)
        self.localOriginsField = QtWidgets.QCheckBox()
        self.localOriginsField.setAccessibleName("Use local origins")
        self.localOriginsField.setToolTip("Rotate around each object's center instead of the chosen pivot or selection center")
        form.addRow("Use local origins", self.localOriginsField)
        self.ensurePolished()
        fields = (self.xField, self.yField, self.angleField, self.localOriginsField)
        rowHeight = max(field.sizeHint().height() for field in fields)
        form.setVerticalSpacing(6)
        for field in fields:
            field.setFixedHeight(rowHeight)
            label = form.labelForField(field)
            label.setFixedHeight(rowHeight)
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(form)
        self.buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok |
                                                QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.resize(340, self.sizeHint().height())

    def accept(self):
        for field in (self.xField, self.yField, self.angleField):
            field.interpretText()
        error = self.mainWindow.viewport.MoveSpecial(self.xField.value() * self.divisor,
                                                     self.yField.value() * self.divisor,
                                                     self.angleField.value(), self.localOriginsField.isChecked())
        if error:
            self.mainWindow.viewport.clipboardMessage.emit(error)
            return
        self.mainWindow.viewport.ShowClipboardError("")
        super().accept()
