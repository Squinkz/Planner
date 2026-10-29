"""Title block controls for the export panel."""
import base64
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from planner_app.graphics.icons import UiIcon
from planner_app.export_settings import TitleBlockLogoMode
from .widgets import DownwardComboBox


class TitleBlockControlsMixin:
    def CreateTitleBlockControls(self, layout):
        self.titleBlockEnabled = QtWidgets.QCheckBox()
        self.titleBlockEnabled.setAccessibleName("Draw Title Block")
        self.titleBlockEnableForm = QtWidgets.QGridLayout()
        self.titleBlockEnableForm.addWidget(QtWidgets.QLabel("Draw Title Block"), 0, 0)
        self.titleBlockEnableForm.addWidget(self.titleBlockEnabled, 0, 1, QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(self.titleBlockEnableForm)
        self.titleBlockOptions = QtWidgets.QWidget()
        optionsLayout = QtWidgets.QVBoxLayout(self.titleBlockOptions)
        optionsLayout.setContentsMargins(0, 0, 0, 0)
        optionsLayout.setSpacing(12)
        layout.addWidget(self.titleBlockOptions)

        positionLabel = QtWidgets.QLabel("Position")
        self.titleBlockPosition = QtWidgets.QWidget()
        self.titleBlockPosition.setAccessibleName("Title block position")
        positionLayout = QtWidgets.QHBoxLayout(self.titleBlockPosition)
        positionLayout.setContentsMargins(0, 0, 0, 0)
        positionLayout.setSpacing(8)
        self.titleBlockPositionGroup = QtWidgets.QButtonGroup(self)
        self.titleBlockPositionButtons = {}
        for position, icon in (("Right", "flip_v"), ("Bottom", "flip_h")):
            button = QtWidgets.QPushButton()
            button.setObjectName("propertyIconButton")
            button.setIcon(UiIcon(icon))
            button.setIconSize(QtCore.QSize(24, 24))
            button.setFixedHeight(32)
            button.setCheckable(True)
            button.setAccessibleName("Title block position " + position.lower())
            button.setToolTip("Title block on the " + position.lower())
            button.clicked.connect(lambda checked = False, position = position: self.SetTitleBlockOption("position", position))
            self.titleBlockPositionGroup.addButton(button)
            self.titleBlockPositionButtons[position] = button
            positionLayout.addWidget(button, 1)
        positionLabel.setBuddy(self.titleBlockPositionButtons["Right"])

        logoLabel = QtWidgets.QLabel("Logo")
        self.titleBlockLogoMode = DownwardComboBox()
        self.titleBlockLogoMode.addItems(("None", "Planner", "Custom"))
        self.titleBlockLogoMode.setAccessibleName("Title block logo")
        logoLabel.setBuddy(self.titleBlockLogoMode)
        inlineLabelWidth = max(positionLabel.sizeHint().width(), logoLabel.sizeHint().width())
        for label, field in ((positionLabel, self.titleBlockPosition), (logoLabel, self.titleBlockLogoMode)):
            label.setFixedWidth(inlineLabelWidth)
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(24)
            row.addWidget(label)
            row.addWidget(field, 1)
            optionsLayout.addLayout(row)
        self.titleBlockLogoOptions = QtWidgets.QWidget()
        logoRow = QtWidgets.QHBoxLayout(self.titleBlockLogoOptions)
        logoRow.setContentsMargins(0, 0, 0, 0)
        logoRow.setSpacing(8)
        self.titleBlockLogoButton = QtWidgets.QToolButton()
        self.titleBlockLogoButton.setObjectName("exportBrowseButton")
        self.titleBlockLogoButton.setIcon(UiIcon("folder_open"))
        self.titleBlockLogoButton.setIconSize(QtCore.QSize(26, 26))
        self.titleBlockLogoButton.setFixedSize(44, 32)
        self.titleBlockLogoButton.setToolTip("Choose logo")
        self.titleBlockLogoButton.setAccessibleName("Choose title block logo")
        self.titleBlockLogoName = QtWidgets.QLineEdit()
        self.titleBlockLogoName.setReadOnly(True)
        self.titleBlockLogoName.setPlaceholderText("No logo selected")
        self.titleBlockLogoName.setAccessibleName("Title block logo filename")
        self.titleBlockLogoName.setMinimumWidth(0)
        self.titleBlockLogoName.setFixedHeight(32)
        logoRow.addWidget(self.titleBlockLogoName, 1)
        logoRow.addWidget(self.titleBlockLogoButton)
        optionsLayout.addWidget(self.titleBlockLogoOptions)

        self.titleBlockFields = {}
        for name, text, multiline in (
                ("projectName", "Project name", False),
                ("drawingTitle", "Drawing title", False),
                ("address", "Project address", True),
                ("date", "Date", False),
                ("preparedBy", "Prepared by", False),
                ("comments", "Comments", True),
                ("sheetNumber", "Sheet number", False),
                ("revision", "Revision", False)):
            label = QtWidgets.QLabel(text)
            label.setObjectName("exportControlLabel")
            field = (QtWidgets.QDateEdit() if name == "date" else
                     QtWidgets.QPlainTextEdit() if multiline else QtWidgets.QLineEdit())
            field.setAccessibleName("Title block " + text.lower())
            field.setMinimumWidth(0)
            if name == "date":
                field.setFixedHeight(32)
                field.setCalendarPopup(True)
                field.setDisplayFormat("yyyy-MM-dd")
                field.setDate(QtCore.QDate.currentDate())
                field.setKeyboardTracking(False)
                field.dateChanged.connect(lambda date: self.SetTitleBlockOption("date", date.toString(QtCore.Qt.DateFormat.ISODate)))
            elif multiline:
                field.setFixedHeight(96)
                field.setTabChangesFocus(True)
                field.textChanged.connect(lambda name = name, field = field:
                                          self.SetTitleBlockOption(name, field.toPlainText()))
            else:
                field.setFixedHeight(32)
                field.setMaxLength(10000)
                field.textEdited.connect(lambda value, name = name: self.SetTitleBlockOption(name, value))
            label.setBuddy(field)
            if name == "date":
                dateRow = QtWidgets.QHBoxLayout()
                dateRow.setSpacing(8)
                self.titleBlockDateReset = QtWidgets.QPushButton()
                self.titleBlockDateReset.setIcon(UiIcon("refresh"))
                self.titleBlockDateReset.setFixedWidth(32)
                self.titleBlockDateReset.setAccessibleName("Reset title block date to today")
                self.titleBlockDateReset.setToolTip("Reset date to today")
                self.titleBlockDateReset.clicked.connect(lambda: self.SetTitleBlockOption(
                    "date", QtCore.QDate.currentDate().toString(QtCore.Qt.DateFormat.ISODate)))
                dateRow.addWidget(field, 1)
                dateRow.addWidget(self.titleBlockDateReset)
                label.setFixedWidth(inlineLabelWidth)
                dateForm = QtWidgets.QHBoxLayout()
                dateForm.setSpacing(24)
                dateForm.addWidget(label)
                dateForm.addLayout(dateRow, 1)
                optionsLayout.addLayout(dateForm)
            else:
                optionsLayout.addWidget(label)
                optionsLayout.addWidget(field)
            self.titleBlockFields[name] = field

        self.titleBlockEnabled.toggled.connect(lambda enabled: self.SetTitleBlockOption("enabled", enabled))
        self.titleBlockLogoButton.clicked.connect(self.ChooseTitleBlockLogo)
        self.titleBlockLogoMode.currentTextChanged.connect(self.SetTitleBlockLogoMode)

    def SetTitleBlockLogoMode(self, mode):
        if self.applying:
            return
        if mode == "Custom":
            self.titleBlockLogoOptions.show()
            self.ChooseTitleBlockLogo()
        else:
            self.SetTitleBlockOption("logoMode", mode)

    def TitleBlockOptions(self):
        options = dict(self.overrides.get("titleBlock", {}))
        path = self.mainWindow.projectPath
        options.setdefault("projectName", Path(path).stem if path else "New Project")
        options["logoMode"] = TitleBlockLogoMode(options)
        if options["logoMode"] == "Custom" and not options.get("logo"):
            options["logoMode"] = "Planner"
        return options

    def TitleBlockDpi(self):
        if self.overrides.get("scaleMode") == "Architectural":
            return self.overrides.get("dpi", 300)
        return 300

    def SetTitleBlockOption(self, name, value):
        if self.applying:
            return
        options = dict(self.overrides.get("titleBlock", {}))
        options[name] = value
        self.SetOverride("titleBlock", options)

    def RefreshTitleBlockControls(self):
        options = self.TitleBlockOptions()
        overlay = self.mainWindow.viewport.exportOverlay
        overlay.titleBlockDpi = self.TitleBlockDpi()
        if overlay.titleBlock != options:
            overlay.titleBlock = dict(options)
            self.mainWindow.viewport.update()
        if overlay.active:
            bounds = overlay.ConstrainTitleBlockBounds(overlay.bounds)
            if bounds != overlay.bounds:
                overlay.bounds = bounds
                overlay.boundsChanged.emit(bounds)
                self.mainWindow.viewport.update()
        widgets = [self.titleBlockEnabled, *self.titleBlockPositionButtons.values(), self.titleBlockLogoMode, *self.titleBlockFields.values()]
        blockers = [QtCore.QSignalBlocker(widget) for widget in widgets]
        self.titleBlockEnabled.setChecked(options.get("enabled", False))
        self.titleBlockOptions.setEnabled(self.titleBlockEnabled.isChecked())
        self.titleBlockPositionButtons[options.get("position", "Right")].setChecked(True)
        self.titleBlockLogoName.setText(options.get("logoName") or ("Embedded logo" if options.get("logo") else ""))
        self.titleBlockLogoMode.setCurrentText(options["logoMode"])
        self.titleBlockLogoOptions.setVisible(options["logoMode"] == "Custom")
        for name, field in self.titleBlockFields.items():
            value = options.get(name, "0001" if name == "sheetNumber" else "")
            if isinstance(field, QtWidgets.QDateEdit):
                date = QtCore.QDate.fromString(value, QtCore.Qt.DateFormat.ISODate)
                field.setDate(date if date.isValid() else QtCore.QDate.currentDate())
            elif isinstance(field, QtWidgets.QPlainTextEdit):
                if field.toPlainText() != value:
                    field.setPlainText(value)
            elif field.text() != value:
                field.setText(value)
        del blockers

    def ChooseTitleBlockLogo(self):
        path, selectedFilter = QtWidgets.QFileDialog.getOpenFileName(
            self, "Choose Title Block Logo", str(self.mainWindow.BrowseDirectory()),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.svg)")
        if not path:
            self.SetTitleBlockOption("logoMode", "Planner")
            return
        reader = QtGui.QImageReader(path)
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid() and max(size.width(), size.height()) > 1600:
            size.scale(1600, 1600, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
            reader.setScaledSize(size)
        image = reader.read()
        if image.isNull():
            self.SetTitleBlockOption("logoMode", "Planner")
            self.mainWindow.ShowAppMessage("Title Block Logo", "Could not open this image.", "warning")
            return
        if max(image.width(), image.height()) > 1600:
            image = image.scaled(1600, 1600, QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                                 QtCore.Qt.TransformationMode.SmoothTransformation)
        buffer = QtCore.QBuffer()
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buffer, "PNG") or buffer.size() > 6_000_000:
            self.SetTitleBlockOption("logoMode", "Planner")
            self.mainWindow.ShowAppMessage("Title Block Logo", "Choose a smaller logo image.", "warning")
            return
        options = dict(self.overrides.get("titleBlock", {}))
        options.update(logo = base64.b64encode(bytes(buffer.data())).decode("ascii"), logoName = Path(path).name,
                       logoMode = "Custom")
        self.SetOverride("titleBlock", options)
        self.mainWindow.RememberBrowseFolder(path)

