"""Export controls for automatically sized scale bars."""
from PySide6 import QtCore, QtWidgets
from planner_app.export_settings import scaleBarDivisions, scaleBarStyles, scaleBarDefaultDivisions, scaleBarDefaultStyle
from planner_app.graphics.icons import UiIcon
from .widgets import DownwardComboBox


class ScaleBarControlsMixin:
    def CreateScaleBarControls(self, layout):
        self.scaleBarEnabled = QtWidgets.QCheckBox()
        self.scaleBarEnabled.setAccessibleName("Draw Scale Bar")
        self.scaleBarEnableForm = QtWidgets.QGridLayout()
        self.scaleBarEnableForm.addWidget(QtWidgets.QLabel("Draw Scale Bar"), 0, 0)
        self.scaleBarEnableForm.addWidget(self.scaleBarEnabled, 0, 1, QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(self.scaleBarEnableForm)
        self.scaleBarOptions = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(self.scaleBarOptions)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(12)
        self.scaleBarPosition = QtWidgets.QWidget()
        self.scaleBarPosition.setAccessibleName("Scale bar position")
        positionLayout = QtWidgets.QHBoxLayout(self.scaleBarPosition)
        positionLayout.setContentsMargins(0, 0, 0, 0)
        positionLayout.setSpacing(8)
        self.scaleBarPositionGroup = QtWidgets.QButtonGroup(self)
        self.scaleBarPositionButtons = {}
        for position, rotation in (("Bottom left", 0), ("Bottom right", 270), ("Top left", 90), ("Top right", 180)):
            button = QtWidgets.QPushButton()
            button.setObjectName("propertyIconButton")
            button.setIcon(UiIcon("align_corner_bl", rotation = rotation))
            button.setIconSize(QtCore.QSize(24, 24))
            button.setFixedHeight(32)
            button.setCheckable(True)
            button.setAccessibleName("Scale bar position " + position.lower())
            button.setToolTip(position)
            button.clicked.connect(lambda checked = False, position = position: self.SetScaleBarOption("position", position))
            self.scaleBarPositionGroup.addButton(button)
            self.scaleBarPositionButtons[position] = button
            positionLayout.addWidget(button, 1)
        positionLabel = QtWidgets.QLabel("Position")
        positionLabel.setBuddy(self.scaleBarPositionButtons["Bottom left"])
        form.addRow(positionLabel, self.scaleBarPosition)
        self.scaleBarDivisionMode = DownwardComboBox()
        self.scaleBarDivisionMode.addItems(scaleBarDivisions)
        self.scaleBarDivisionMode.setAccessibleName("Scale bar divisions")
        self.scaleBarDivisionMode.setMinimumHeight(32)
        form.addRow("Divisions", self.scaleBarDivisionMode)
        self.scaleBarStyle = DownwardComboBox()
        self.scaleBarStyle.addItems(scaleBarStyles)
        self.scaleBarStyle.setAccessibleName("Scale bar style")
        self.scaleBarStyle.setMinimumHeight(32)
        form.addRow("Style", self.scaleBarStyle)
        layout.addWidget(self.scaleBarOptions)
        self.scaleBarEnabled.toggled.connect(lambda enabled: self.SetScaleBarOption("enabled", enabled))
        self.scaleBarDivisionMode.currentTextChanged.connect(lambda value: self.SetScaleBarOption("divisionMode", value))
        self.scaleBarStyle.currentTextChanged.connect(lambda value: self.SetScaleBarOption("style", value))

    def SetScaleBarOption(self, name, value):
        if self.applying:
            return
        options = dict(self.overrides.get("scaleBar", {}))
        options[name] = value
        self.SetOverride("scaleBar", options)

    def RefreshScaleBarControls(self):
        options = self.overrides.get("scaleBar", {})
        overlay = self.mainWindow.viewport.exportOverlay
        overlay.scaleBar = dict(options)
        if overlay.active and not overlay.printMode and options.get("enabled", False):
            bounds = overlay.ConstrainTitleBlockBounds(overlay.bounds)
            if bounds != overlay.bounds:
                overlay.bounds = bounds
                overlay.boundsChanged.emit(bounds)
                self.mainWindow.viewport.update()
        blockers = [QtCore.QSignalBlocker(control) for control in
                    (self.scaleBarEnabled, *self.scaleBarPositionButtons.values(), self.scaleBarDivisionMode, self.scaleBarStyle)]
        self.scaleBarEnabled.setChecked(options.get("enabled", False))
        self.scaleBarOptions.setEnabled(self.scaleBarEnabled.isChecked())
        self.scaleBarPositionButtons[options.get("position", "Bottom left")].setChecked(True)
        self.scaleBarDivisionMode.setCurrentText(options.get("divisionMode", scaleBarDefaultDivisions))
        self.scaleBarStyle.setCurrentText(options.get("style", scaleBarDefaultStyle))
        del blockers
