"""Modeless application preferences, styled like Stacker's slider/reset fields."""
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.theme import HeaderIcon, gridIntensityDefaults
from planner_app.graphics.icons import UiIcon
from planner_app.preferences import lineworkDefaults, wallPresetNames, wallPresetWidths, openingDefaultSizes, miscDefaultSizes, measurementDefaults, stairStepSizeDefaults, railingSpacingDefaults
from planner_app.units import MetricUnit, FormatLength, unitModes, measurementPrecisions, imperialModes
from planner_app.ui.widgets import DownwardComboBox, VisibilityItemDelegate, DragSlider, UnitSpinBox
from planner_app.graphics.palette import themeColors, themeDefinitions
from planner_app.graphics import palette
from planner_app.placement_sizing import NominalPlacementSize


class SettingsWindow(QtWidgets.QDialog):
    def __init__(self, mainWindow):
        super().__init__(mainWindow)
        self.mainWindow = mainWindow
        self.setWindowTitle("Settings")
        self.setWindowIcon(HeaderIcon("Settings"))
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setIconSize(QtCore.QSize(24, 24))
        self.tabs.tabBar().setDrawBase(False)
        layout.addWidget(self.tabs)
        self.BuildSizeTab()
        page = QtWidgets.QWidget()
        self.viewportPage = page
        pageLayout = QtWidgets.QVBoxLayout(page)
        pageLayout.setContentsMargins(16, 20, 16, 16)
        form = QtWidgets.QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        columns = QtWidgets.QHBoxLayout()
        columns.setSpacing(24)
        leftColumn = QtWidgets.QVBoxLayout()
        rightColumn = QtWidgets.QVBoxLayout()
        for column, text in ((leftColumn, "Grid"), (rightColumn, "Line Weight")):
            heading = QtWidgets.QLabel(text)
            heading.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            font = heading.font()
            font.setBold(True)
            heading.setFont(font)
            column.addWidget(heading)
        self.sliders = {}
        self.valueFields = {}
        self.resetButtons = {}
        for key, text in (("overall", "Grid Intensity"), ("major", "Major Gridlines"),
                          ("minor", "Minor Gridlines"), ("origin", "Origin")):
            label = QtWidgets.QLabel(text)
            label.setFixedWidth(120)
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            field = QtWidgets.QWidget()
            row = QtWidgets.QHBoxLayout(field)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            slider = DragSlider(QtCore.Qt.Orientation.Horizontal)
            maximum = 2 if key == "overall" else 1
            slider.setRange(0, maximum * 1000)
            slider.setMinimumHeight(26)
            slider.setAccessibleName(text)
            valueField = UnitSpinBox()
            valueField.setObjectName("settingsValue")
            valueField.setRange(0, maximum)
            valueField.setDecimals(3)
            valueField.setSingleStep(.01)
            valueField.setFixedWidth(96)
            valueField.setAccessibleName(f"{text} value")
            value = mainWindow.viewport.gridIntensities[key]
            slider.setValue(round(value * 1000))
            valueField.setValue(value)
            reset = QtWidgets.QPushButton()
            reset.setObjectName("settingsIconButton")
            reset.setIcon(UiIcon("refresh"))
            reset.setIconSize(QtCore.QSize(24, 24))
            reset.setFixedWidth(34)
            reset.setMaximumHeight(32)
            default = gridIntensityDefaults[key]
            reset.setToolTip(f"Reset {text.lower()} to {default:.3f}")
            reset.setAccessibleName(f"Reset {text}")
            reset.setEnabled(value != default)
            slider.valueChanged.connect(lambda value, key = key: self.SetGridIntensity(key, value / 1000))
            valueField.valueChanged.connect(lambda value, key = key: self.SetGridIntensity(key, value))
            reset.clicked.connect(lambda checked = False, key = key: self.SetGridIntensity(key, gridIntensityDefaults[key]))
            row.addWidget(slider, 1)
            row.addWidget(valueField)
            row.addWidget(reset)
            form.addRow(label, field)
            self.sliders[key], self.valueFields[key], self.resetButtons[key] = slider, valueField, reset
            if key == "overall":
                spacer = QtWidgets.QWidget()
                spacer.setFixedHeight(8)
                form.addRow(spacer)
        leftColumn.addLayout(form)
        leftColumn.addStretch(1)
        weightForm = QtWidgets.QFormLayout()
        weightForm.setHorizontalSpacing(16)
        weightForm.setVerticalSpacing(12)
        self.lineworkSliders = {}
        self.lineworkFields = {}
        self.lineworkResetButtons = {}
        for key, text in (("baseWidth", "Base width"), ("walls", "Walls"), ("architectural", "Architectural objects"),
                          ("furnishings", "Furnishings"), ("dimensions", "Dimensions")):
            minimum, maximum = (1, 4) if key == "baseWidth" else (0, 2)
            slider = DragSlider(QtCore.Qt.Orientation.Horizontal)
            slider.setRange(minimum * 1000, maximum * 1000)
            slider.setMinimumHeight(26)
            slider.setAccessibleName(text)
            field = UnitSpinBox()
            field.setObjectName("settingsValue")
            field.setRange(minimum, maximum)
            field.setDecimals(3)
            field.setSingleStep(.01)
            field.setSuffix(" px" if key == "baseWidth" else "×")
            field.setKeyboardTracking(False)
            field.setFixedWidth(112)
            field.setAccessibleName(f"{text} value")
            reset = QtWidgets.QPushButton()
            reset.setObjectName("settingsIconButton")
            reset.setIcon(UiIcon("refresh"))
            reset.setIconSize(QtCore.QSize(24, 24))
            reset.setFixedWidth(34)
            reset.setMaximumHeight(32)
            reset.setToolTip(f"Reset {text.lower()} to {lineworkDefaults[key]:g}")
            reset.setAccessibleName(f"Reset {text}")
            value = mainWindow.viewport.lineworkSettings[key]
            slider.setValue(round(value * 1000))
            field.setValue(value)
            reset.setEnabled(value != lineworkDefaults[key])
            slider.valueChanged.connect(lambda value, key = key: self.SetLineWeight(key, value / 1000))
            field.valueChanged.connect(lambda value, key = key: self.SetLineWeight(key, value))
            reset.clicked.connect(lambda checked = False, key = key: self.SetLineWeight(key, lineworkDefaults[key]))
            container = QtWidgets.QWidget()
            row = QtWidgets.QHBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            row.addWidget(slider, 1)
            row.addWidget(field)
            row.addWidget(reset)
            weightForm.addRow(text, container)
            self.lineworkSliders[key], self.lineworkFields[key], self.lineworkResetButtons[key] = slider, field, reset
        rightColumn.addLayout(weightForm)
        rightColumn.addStretch(1)
        columns.addLayout(leftColumn, 1)
        columns.addLayout(rightColumn, 1)
        heading = QtWidgets.QLabel("Theme")
        heading.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        heading.setFont(font)
        pageLayout.addWidget(heading)
        pageLayout.addSpacing(18)
        themeChoices = QtWidgets.QHBoxLayout()
        themeChoices.setSpacing(24)
        self.uiThemeField = DownwardComboBox()
        self.uiThemeField.setAccessibleName("UI Theme")
        self.uiThemeField.addItems(sorted((name for name, theme in themeDefinitions.items() if theme["type"] == "ui"),
                                         key = lambda name: (name != "Dark UI", name.casefold())))
        self.uiThemeField.setCurrentText(palette.activeUITheme)
        self.uiThemeField.currentTextChanged.connect(lambda name: mainWindow.SetThemes(uiTheme = name))
        self.canvasThemeField = DownwardComboBox()
        self.canvasThemeField.setAccessibleName("Canvas Theme")
        self.canvasThemeField.addItems(sorted((name for name, theme in themeDefinitions.items() if theme["type"] == "canvas"),
                                             key = lambda name: (name != "Dark Canvas", name.casefold())))
        self.canvasThemeField.setCurrentText(palette.activeCanvasTheme)
        self.canvasThemeField.currentTextChanged.connect(lambda name: mainWindow.SetThemes(canvasTheme = name))
        for text, field in (("UI Theme", self.uiThemeField), ("Canvas Theme", self.canvasThemeField)):
            label = QtWidgets.QLabel(text)
            label.setFixedWidth(120)
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(label)
            row.addWidget(field, 1)
            themeChoices.addLayout(row, 1)
        pageLayout.addLayout(themeChoices)
        pageLayout.addSpacing(12)
        pageLayout.addLayout(columns)
        pageLayout.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        self.sliders["overall"].setToolTip("Multiplies the intensity of major, minor and origin gridlines")
        self.BuildMeasurementTab()
        self.tabs.addTab(scroll, HeaderIcon("Appearance"), "Appearance")
        self.RefreshSizeUnits()
        self.confirmButtons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        self.confirmButtons.accepted.connect(self.accept)
        layout.addWidget(self.confirmButtons)
        for field in self.findChildren(QtWidgets.QAbstractSpinBox) + self.findChildren(QtWidgets.QLineEdit):
            field.installEventFilter(self)

    def showEvent(self, event):
        super().showEvent(event)
        self.FitToContents()

    def FitToContents(self):
        self.ensurePolished()
        self.layout().activate()
        available = self.screen().availableGeometry()
        margins = self.layout().contentsMargins()
        contentHeight = max(page.sizeHint().height() for page in (self.buildPage, self.viewportPage, self.measurementPage))
        height = (contentHeight + self.tabs.tabBar().sizeHint().height() + margins.top() + margins.bottom()
                  + self.confirmButtons.sizeHint().height() + self.layout().spacing() + 4)
        frameHeight = max(0, self.frameGeometry().height() - self.height())
        maximumHeight = max(1, available.height() - frameHeight - 24)
        maximumWidth = max(1, available.width() - 24)
        contentWidth = max(page.minimumSizeHint().width() for page in (self.buildPage, self.viewportPage, self.measurementPage))
        width = max(900, contentWidth + margins.left() + margins.right() + 4)
        self.setMinimumSize(min(width, maximumWidth), min(height, maximumHeight))
        self.resize(min(width, maximumWidth), min(height, maximumHeight))
        frame = self.frameGeometry()
        self.move(max(available.left(), min(frame.left(), available.right() - frame.width() + 1)),
                  max(available.top(), min(frame.top(), available.bottom() - frame.height() + 1)))

    def BuildSizeTab(self):
        page = QtWidgets.QWidget()
        self.buildPage = page
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(16, 20, 16, 16)
        self.buildTabs = QtWidgets.QTabWidget()
        self.buildTabs.tabBar().setDrawBase(False)
        layout.addWidget(self.buildTabs)
        generalPage = QtWidgets.QWidget()
        generalLayout = QtWidgets.QVBoxLayout(generalPage)
        generalLayout.setContentsMargins(16, 20, 16, 16)
        self.buildTabs.addTab(generalPage, "General")
        columns = QtWidgets.QHBoxLayout()
        columns.setSpacing(24)
        leftColumn = QtWidgets.QVBoxLayout()
        rightColumn = QtWidgets.QVBoxLayout()
        leftColumn.setSpacing(8)
        rightColumn.setSpacing(8)
        columns.addLayout(leftColumn, 1)
        columns.addLayout(rightColumn, 1)
        generalLayout.addLayout(columns)
        font = page.font()
        font.setBold(True)
        sizeForms = {}
        for name in ("Walls", "Doors", "Windows", "Misc"):
            sizePage = QtWidgets.QWidget()
            sizeLayout = QtWidgets.QVBoxLayout(sizePage)
            sizeLayout.setContentsMargins(16, 20, 16, 16)
            section = QtWidgets.QWidget()
            section.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
            form = QtWidgets.QFormLayout(section)
            form.setContentsMargins(0, 0, 0, 0)
            form.setHorizontalSpacing(16)
            form.setVerticalSpacing(12)
            sizeLayout.addWidget(section)
            sizeLayout.addStretch(1)
            sizeForms[name] = form
            self.buildTabs.addTab(sizePage, name)
        self.sizeFields = {}
        self.buildResetButtons = {}
        entries = list(enumerate(wallPresetNames)) + [("Door", "Standard Door"), ("SlidingDoor", "Sliding Door"),
                   ("PocketDoor", "Pocket Door"), ("BarnDoor", "Barn Door"), ("BifoldDoor", "Bifold Door"), ("OpenDoorway", "Open Doorway"),
                   ("Window", "Standard Window"), ("SilledWindow", "Silled Window"), ("CasementWindow", "Casement Window"),
                   ("Stair", "Stair"), ("Counter", "Counter"), ("Railing", "Railing"), ("Pillar", "Pillar"), ("Column", "Column"), ("Fireplace", "Fireplace"), ("Elevator", "Elevator")]
        objectButtons = {"Door": self.mainWindow.doorButton, "SlidingDoor": self.mainWindow.slidingDoorButton,
                          "PocketDoor": self.mainWindow.pocketDoorButton, "BarnDoor": self.mainWindow.barnDoorButton, "BifoldDoor": self.mainWindow.bifoldDoorButton, "OpenDoorway": self.mainWindow.openDoorwayButton,
                          "Window": self.mainWindow.windowButton, "SilledWindow": self.mainWindow.silledWindowButton,
                          "CasementWindow": self.mainWindow.casementWindowButton,
                          "Stair": self.mainWindow.stairButton, "Counter": self.mainWindow.counterButton,
                          "Railing": self.mainWindow.railingButton, "Pillar": self.mainWindow.pillarButton, "Column": self.mainWindow.columnButton,
                          "Fireplace": self.mainWindow.fireplaceButton, "Elevator": self.mainWindow.elevatorButton}
        for key, text in entries:
            form = sizeForms["Walls" if isinstance(key, int) else
                             "Misc" if key in miscDefaultSizes else
                             "Windows" if key in ("Window", "SilledWindow", "CasementWindow") else "Doors"]
            label = QtWidgets.QWidget()
            row = QtWidgets.QHBoxLayout(label)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(10)
            icon = QtWidgets.QLabel()
            icon.setFixedSize(28, 28)
            if isinstance(key, int):
                icon.setPixmap(self.mainWindow.wallWidthSelector.icons[key].pixmap(28, 28))
                value = self.mainWindow.viewport.wallPresetWidths[key]
            else:
                icon.setPixmap(objectButtons[key].icon().pixmap(28, 28))
                sizes = self.mainWindow.viewport.miscDefaultSizes if key in miscDefaultSizes else self.mainWindow.viewport.openingDefaultSizes
                value = sizes[key]
            row.addWidget(icon)
            row.addWidget(QtWidgets.QLabel(text))
            row.addStretch(1)
            field = UnitSpinBox()
            field.setObjectName("settingsValue")
            field.setRange(.1, 10000)
            field.setDecimals(1)
            field.setSingleStep(1)
            field.setSuffix(" cm")
            field.setAccessibleName(f"{text} default size")
            field.setValue(value)
            if key in ("SlidingDoor", "PocketDoor", "BarnDoor"):
                field.setToolTip("Sets the door panel size. The complete opening occupies twice this length.")
            elif key in miscDefaultSizes:
                field.setToolTip("Sets the diameter for new columns" if key == "Column" else "Sets both width and height for new pillars" if key == "Pillar" else
                                 "Sets both width and length for new elevators" if key == "Elevator" else
                                 "Sets the length along the wall for new fireplaces. Width follows a 12:5 ratio, with wall thickness as the minimum." if key == "Fireplace" else
                                 f"Sets the width for new {text.lower()} objects")
            field.valueChanged.connect(lambda value, key = key: self.SetDefaultSize(key, value))
            default = wallPresetWidths[key] if isinstance(key, int) else (openingDefaultSizes | miscDefaultSizes)[key]
            reset = QtWidgets.QPushButton()
            reset.setObjectName("settingsIconButton")
            reset.setIcon(UiIcon("refresh"))
            reset.setIconSize(QtCore.QSize(24, 24))
            reset.setFixedWidth(34)
            reset.setMaximumHeight(32)
            reset.setAccessibleName(f"Reset {text} default size")
            reset.setEnabled(value != default)
            reset.clicked.connect(lambda checked = False, key = key, default = default: self.SetDefaultSize(key, default, canonical = True))
            container = QtWidgets.QWidget()
            row = QtWidgets.QHBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            row.addWidget(field, 1)
            row.addWidget(reset)
            form.addRow(label, container)
            self.sizeFields[key] = field
            self.buildResetButtons[key] = reset
        heading = QtWidgets.QLabel("Auto Tread Depth")
        heading.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        heading.setFont(font)
        leftColumn.addWidget(heading)
        stepSection = QtWidgets.QWidget()
        stepSection.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        stepForm = QtWidgets.QFormLayout(stepSection)
        stepForm.setContentsMargins(0, 0, 0, 0)
        stepForm.setHorizontalSpacing(16)
        stepForm.setVerticalSpacing(12)
        self.stepSizingFields = {}
        self.stepSizingResetButtons = {}
        for key, text in (("minimum", "Minimum Tread Depth"), ("maximum", "Maximum Tread Depth")):
            field = UnitSpinBox()
            field.setObjectName("settingsValue")
            field.setRange(.1, 10000)
            field.setDecimals(1)
            field.setSingleStep(1)
            field.setSuffix(" cm")
            field.setAccessibleName(text)
            field.setValue(self.mainWindow.viewport.stairStepSizes[key])
            field.valueChanged.connect(lambda value, key = key: self.SetStepSizing(key, value))
            reset = QtWidgets.QPushButton()
            reset.setObjectName("settingsIconButton")
            reset.setIcon(UiIcon("refresh"))
            reset.setIconSize(QtCore.QSize(24, 24))
            reset.setFixedWidth(34)
            reset.setMaximumHeight(32)
            reset.clicked.connect(lambda checked = False, key = key: self.SetStepSizing(key, stairStepSizeDefaults[key], canonical = True))
            container = QtWidgets.QWidget()
            row = QtWidgets.QHBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            row.addWidget(field, 1)
            row.addWidget(reset)
            stepForm.addRow(text, container)
            self.stepSizingFields[key] = field
            self.stepSizingResetButtons[key] = reset
        leftColumn.addWidget(stepSection)
        leftColumn.addSpacing(16)
        heading = QtWidgets.QLabel("Collisions")
        heading.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        heading.setFont(font)
        leftColumn.addWidget(heading)
        collisionSection = QtWidgets.QWidget()
        collisionLayout = QtWidgets.QGridLayout(collisionSection)
        collisionLayout.setContentsMargins(0, 0, 0, 0)
        collisionLayout.setHorizontalSpacing(12)
        collisionLayout.setVerticalSpacing(12)
        collisionLayout.setColumnStretch(0, 1)
        collisionLayout.setColumnStretch(1, 1)
        self.collisionFields = {}
        for key, text, iconName in (("walls", "Walls", "Walls"), ("architectural", "Architectural objects", "Objects"),
                                    ("furnishings", "Furnishings", "Chair")):
            field = QtWidgets.QCheckBox()
            field.setAccessibleName(text + " collisions")
            field.setChecked(self.mainWindow.viewport.collisionSettings[key])
            field.toggled.connect(lambda enabled, key = key: self.SetCollision(key, enabled))
            label = QtWidgets.QToolButton()
            label.setText(text)
            label.setIcon(HeaderIcon(iconName))
            label.setIconSize(QtCore.QSize(24, 24))
            label.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            label.setStyleSheet("QToolButton { border: none; background: transparent; padding: 0; }")
            label.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
            label.clicked.connect(field.toggle)
            rowIndex = len(self.collisionFields)
            collisionLayout.addWidget(field, rowIndex, 0, QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            collisionLayout.addWidget(label, rowIndex, 1, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
            self.collisionFields[key] = field
        labelWidth = max(collisionLayout.itemAtPosition(rowIndex, 1).widget().sizeHint().width()
                         for rowIndex in range(len(self.collisionFields)))
        collisionLayout.setColumnMinimumWidth(0, labelWidth)
        collisionLayout.setColumnMinimumWidth(1, labelWidth)
        leftColumn.addWidget(collisionSection)
        heading = QtWidgets.QLabel("Auto Railing Sizing")
        heading.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        heading.setFont(font)
        rightColumn.addWidget(heading)
        railingSection = QtWidgets.QWidget()
        railingSection.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        railingForm = QtWidgets.QFormLayout(railingSection)
        railingForm.setContentsMargins(0, 0, 0, 0)
        railingForm.setHorizontalSpacing(16)
        railingForm.setVerticalSpacing(12)
        self.railingSizingFields = {}
        self.railingSizingResetButtons = {}
        for key, text in (("minimum", "Minimum Spacing"), ("maximum", "Maximum Spacing"), ("target", "Preferred Spacing")):
            field = UnitSpinBox()
            field.setObjectName("settingsValue")
            field.setAccessibleName(text)
            field.valueChanged.connect(lambda value, key = key: self.SetRailingSizing(key, value))
            reset = QtWidgets.QPushButton()
            reset.setObjectName("settingsIconButton")
            reset.setIcon(UiIcon("refresh"))
            reset.setIconSize(QtCore.QSize(24, 24))
            reset.setFixedWidth(34)
            reset.setMaximumHeight(32)
            reset.clicked.connect(lambda checked = False, key = key: self.SetRailingSizing(key, railingSpacingDefaults[key], canonical = True))
            container = QtWidgets.QWidget()
            row = QtWidgets.QHBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            row.addWidget(field, 1)
            row.addWidget(reset)
            railingForm.addRow(text, container)
            self.railingSizingFields[key] = field
            self.railingSizingResetButtons[key] = reset
        rightColumn.addWidget(railingSection)
        leftColumn.addStretch(1)
        rightColumn.addStretch(1)
        self.RefreshStepSizing()
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.buildScrollArea = scroll
        self.tabs.addTab(scroll, HeaderIcon("Construction"), "Build")

    def RefreshCollisions(self):
        for key, field in self.collisionFields.items():
            blocker = QtCore.QSignalBlocker(field)
            field.setChecked(self.mainWindow.viewport.collisionSettings[key])
            del blocker

    def SetCollision(self, key, enabled):
        viewport = self.mainWindow.viewport
        viewport.collisionSettings[key] = enabled
        viewport.collisionResults = {}
        viewport.furnishingValidationCache = {}
        viewport.viewportSceneKey = None
        self.mainWindow.RefreshProperties()
        viewport.update()
        viewport.settingsChanged.emit()

    def RefreshStepSizing(self):
        self.RefreshRailingSizing()
        viewport = self.mainWindow.viewport
        divisor, unit = MetricUnit(viewport.unitsMode, "cm")
        limits = viewport.AutoSizingLimits("stairs")
        for key, field in self.stepSizingFields.items():
            value = limits[key]
            default = NominalPlacementSize(stairStepSizeDefaults[key] * 10, viewport.unitsMode)
            blocker = QtCore.QSignalBlocker(field)
            field.setDecimals(0 if unit == "mm" else 3 if unit in ("m", "ft", "in") else 1)
            field.setRange(1 / divisor, max(100000, NominalPlacementSize(100000, viewport.unitsMode)) / divisor)
            field.setSingleStep((25.4 if viewport.unitsMode in imperialModes else 10) / divisor)
            field.setSuffix(" " + unit)
            field.setValue(value / divisor)
            del blocker
            self.stepSizingResetButtons[key].setEnabled(not QtCore.qFuzzyCompare(value, default))
            self.stepSizingResetButtons[key].setToolTip(f"Reset to {FormatLength(default, viewport.unitsMode, 'cm')}")

    def RefreshRailingSizing(self):
        viewport = self.mainWindow.viewport
        divisor, unit = MetricUnit(viewport.unitsMode, "cm")
        limits = viewport.AutoSizingLimits("railings")
        for key, field in self.railingSizingFields.items():
            default = NominalPlacementSize(railingSpacingDefaults[key] * 10, viewport.unitsMode)
            blocker = QtCore.QSignalBlocker(field)
            field.setDecimals(0 if unit == "mm" else 3 if unit in ("m", "ft", "in") else 1)
            field.setRange(1 / divisor, max(100000, NominalPlacementSize(100000, viewport.unitsMode)) / divisor)
            field.setSingleStep((25.4 if viewport.unitsMode in imperialModes else 10) / divisor)
            field.setSuffix(" " + unit)
            field.setValue(limits[key] / divisor)
            del blocker
            self.railingSizingResetButtons[key].setEnabled(not QtCore.qFuzzyCompare(limits[key], default))
            self.railingSizingResetButtons[key].setToolTip(f"Reset to {FormatLength(default, viewport.unitsMode, 'cm')}")

    def SetRailingSizing(self, key, value, canonical = False):
        panel = self.mainWindow.exportPanel
        if panel.projectView is not None and not panel.applying:
            panel.EditProjectSettings(lambda: self.SetRailingSizing(key, value, canonical))
            return
        viewport = self.mainWindow.viewport
        imperial = viewport.unitsMode in imperialModes
        if imperial:
            divisor, unused = MetricUnit(viewport.unitsMode, "cm")
            value = NominalPlacementSize(value * 10, viewport.unitsMode) if canonical else round(value * divisor, 6)
        elif not canonical:
            divisor, unused = MetricUnit(viewport.unitsMode, "cm")
            value = round(value * divisor / 10, 6)
        limits = viewport.AutoSizingLimits("railings") if imperial else viewport.railingSpacings
        limits[key] = value
        if key == "target":
            limits["minimum"] = min(limits["minimum"], value)
            limits["maximum"] = max(limits["maximum"], value)
        else:
            if limits["minimum"] > limits["maximum"]:
                limits["maximum" if key == "minimum" else "minimum"] = value
            limits["target"] = max(limits["minimum"], min(limits["maximum"], limits["target"]))
        if imperial:
            viewport.imperialAutoSizes["railings"] = limits
        else:
            viewport.imperialAutoSizes.pop("railings", None)
        self.RefreshRailingSizing()
        viewport.EnsureObjectIds()
        self.mainWindow.RefreshProperties()
        viewport.update()
        self.mainWindow.ProjectSettingsChanged()

    def SetStepSizing(self, key, value, canonical = False):
        panel = self.mainWindow.exportPanel
        if panel.projectView is not None and not panel.applying:
            panel.EditProjectSettings(lambda: self.SetStepSizing(key, value, canonical))
            return
        v = self.mainWindow.viewport
        imperial = v.unitsMode in imperialModes
        if imperial:
            divisor, unused = MetricUnit(v.unitsMode, "cm")
            value = NominalPlacementSize(value * 10, v.unitsMode) if canonical else round(value * divisor, 6)
        elif not canonical:
            divisor, unused = MetricUnit(v.unitsMode, "cm")
            value = round(value * divisor / 10, 6)
        limits = v.AutoSizingLimits("stairs") if imperial else v.stairStepSizes
        limits[key] = value
        if limits["minimum"] > limits["maximum"]:
            limits["maximum" if key == "minimum" else "minimum"] = value
        if imperial:
            v.imperialAutoSizes["stairs"] = limits
        else:
            v.imperialAutoSizes.pop("stairs", None)
        self.RefreshStepSizing()
        v.EnsureObjectIds()
        self.mainWindow.RefreshProperties()
        v.update()
        self.mainWindow.ProjectSettingsChanged()

    def BuildMeasurementTab(self):
        page = QtWidgets.QWidget()
        self.measurementPage = page
        pageLayout = QtWidgets.QVBoxLayout(page)
        pageLayout.setContentsMargins(16, 20, 16, 16)
        columns = QtWidgets.QHBoxLayout()
        columns.setSpacing(48)
        layout = QtWidgets.QVBoxLayout()
        columns.addLayout(layout, 1)
        rightColumn = QtWidgets.QVBoxLayout()
        rightColumn.setSpacing(0)
        unitsRow = QtWidgets.QWidget()
        unitsRow.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        unitsForm = QtWidgets.QFormLayout(unitsRow)
        unitsForm.setContentsMargins(0, 0, 0, 0)
        unitsForm.setHorizontalSpacing(16)
        self.unitsField = DownwardComboBox()
        self.unitsField.addItems(unitModes)
        self.unitsField.setCurrentText(self.mainWindow.viewport.unitsMode)
        self.unitsField.currentTextChanged.connect(self.SetUnitsMode)
        unitsForm.addRow("Units", self.unitsField)
        self.precisionField = DownwardComboBox()
        self.precisionField.addItems(list(measurementPrecisions))
        self.precisionField.setCurrentText(self.mainWindow.viewport.measurementPrecision)
        self.precisionField.currentTextChanged.connect(self.SetMeasurementPrecision)
        unitsForm.addRow("Precision", self.precisionField)
        rightColumn.addWidget(unitsRow)
        rightColumn.addSpacing(10)
        self.measurementVisibilityTree = QtWidgets.QTreeWidget()
        self.measurementVisibilityTree.setObjectName("visibilityTree")
        self.measurementVisibilityTree.setHeaderHidden(True)
        self.measurementVisibilityTree.setRootIsDecorated(False)
        self.measurementVisibilityTree.setItemsExpandable(False)
        self.measurementVisibilityTree.setExpandsOnDoubleClick(False)
        self.measurementVisibilityTree.setIndentation(24)
        self.measurementVisibilityTree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.measurementVisibilityTree.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.measurementVisibilityTree.setItemDelegate(VisibilityItemDelegate(self.measurementVisibilityTree))
        self.measurementVisibilityItems = {}
        for key, title in (("all", "Show all measurements"), ("walls", "Show wall measurements"),
                           ("stairs", "Show stair measurements"), ("counters", "Show counter measurements"),
                           ("railings", "Show railing measurements"), ("elevators", "Show elevator measurements")):
            parent = self.measurementVisibilityTree if key == "all" else self.measurementVisibilityItems["all"]
            item = QtWidgets.QTreeWidgetItem(parent, [title])
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, key)
            self.measurementVisibilityItems[key] = item
        self.measurementVisibilityTree.expandAll()
        self.measurementVisibilityTree.itemChanged.connect(lambda item, column:
            self.SetMeasurementVisibility(item.data(0, QtCore.Qt.ItemDataRole.UserRole),
                                          item.checkState(0) != QtCore.Qt.CheckState.Unchecked))
        self.measurementVisibilityTree.ensurePolished()
        rowHeight = self.measurementVisibilityTree.sizeHintForRow(0)
        self.measurementVisibilityTree.setFixedHeight(rowHeight * len(self.measurementVisibilityItems) +
                                                    self.measurementVisibilityTree.frameWidth() * 2)
        rightColumn.addWidget(self.measurementVisibilityTree)
        rightColumn.addSpacing(16)
        self.showGridField = QtWidgets.QCheckBox("Show Grid")
        self.showGridField.setAccessibleName("Show Grid")
        self.showGridField.toggled.connect(lambda checked: self.mainWindow.SetViewOption("showGrid"))
        rightColumn.addWidget(self.showGridField)
        rightColumn.addStretch(1)
        self.mainWindow.viewport.settingsChanged.connect(self.RefreshMeasurementVisibility)
        self.RefreshMeasurementVisibility()
        columns.addLayout(rightColumn, 1)
        pageLayout.addLayout(columns)
        layout.setSpacing(24)
        self.measurementSliders = {}
        self.measurementResetButtons = {}
        self.measurementDragging = None
        self.measurementWheelDeltas = {key: 0 for key in measurementDefaults}
        self.measurementModes = {"doors": (0, 1, 2), "windows": (0, 1, 2), "stairs": (0, 2), "counters": (0, 2)}
        for key, title in (("doors", "Doors"), ("windows", "Windows"), ("stairs", "Stairs"), ("counters", "Counters")):
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(16)
            heading = QtWidgets.QLabel(title)
            font = heading.font()
            font.setBold(True)
            heading.setFont(font)
            heading.setFixedWidth(70)
            row.addWidget(heading)
            slider = DragSlider(QtCore.Qt.Orientation.Vertical)
            slider.setObjectName("measurementMode")
            slider.setRange(0, len(self.measurementModes[key]) - 1)
            slider.setInvertedAppearance(True)
            slider.setInvertedControls(True)
            slider.setSingleStep(1)
            slider.setPageStep(1)
            slider.setFixedHeight(49 if key in ("stairs", "counters") else 112)
            slider.setAccessibleName(f"{title} wall measurement splits")
            value = self.mainWindow.viewport.measurementSettings[key]
            slider.setValue(self.measurementModes[key].index(value))
            row.addWidget(slider)
            labelArea = QtWidgets.QWidget()
            labels = QtWidgets.QVBoxLayout(labelArea)
            labels.setContentsMargins(0, 0, 0, 0)
            labels.setSpacing(0)
            texts = ("Split wall measurements", "Do not split wall measurements") if key in ("stairs", "counters") else (
                "Split all wall measurements", "Split on facing side only", "Do not split wall measurements")
            for index, text in enumerate(texts):
                label = QtWidgets.QLabel(text)
                label.setProperty("measurementKey", key)
                label.installEventFilter(self)
                alignment = QtCore.Qt.AlignmentFlag.AlignTop if index == 0 else (
                    QtCore.Qt.AlignmentFlag.AlignBottom if index == len(texts) - 1 else QtCore.Qt.AlignmentFlag.AlignVCenter)
                labels.addWidget(label, 1, alignment)
            for control in (slider, labelArea):
                control.setProperty("measurementKey", key)
                control.installEventFilter(self)
            row.addWidget(labelArea, 1)
            reset = QtWidgets.QPushButton()
            reset.setObjectName("settingsIconButton")
            reset.setIcon(UiIcon("refresh"))
            reset.setIconSize(QtCore.QSize(24, 24))
            reset.setFixedWidth(34)
            reset.setMaximumHeight(32)
            reset.setToolTip(f"Reset wall measurement splits for {title.lower()}")
            reset.setEnabled(value != measurementDefaults[key])
            reset.clicked.connect(lambda checked = False, key = key: self.SetMeasurementMode(key, measurementDefaults[key]))
            row.addWidget(reset)
            slider.valueChanged.connect(lambda value, key = key: self.SetMeasurementMode(key, self.measurementModes[key][value]))
            self.measurementSliders[key] = slider
            self.measurementResetButtons[key] = reset
            layout.addLayout(row)
        layout.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, HeaderIcon("Measurements"), "Measurements")

    def SetMeasurementPrecision(self, precision):
        if precision not in measurementPrecisions:
            return
        panel = self.mainWindow.exportPanel
        if panel.projectView is not None and not panel.applying:
            panel.EditProjectSettings(lambda: self.SetMeasurementPrecision(precision))
            return
        self.mainWindow.viewport.measurementPrecision = precision
        self.mainWindow.viewport.update()
        self.mainWindow.ProjectSettingsChanged()

    def SetUnitsMode(self, mode):
        if mode not in unitModes:
            return
        panel = self.mainWindow.exportPanel
        if panel.projectView is not None and not panel.applying:
            panel.EditProjectSettings(lambda: self.SetUnitsMode(mode))
            return
        self.mainWindow.viewport.unitsMode = mode
        self.mainWindow.UpdateFurnishingSearch()
        self.mainWindow.wallWidthSelector.unitsMode = mode
        self.mainWindow.wallWidthSelector.widths = tuple(self.mainWindow.viewport.DefaultPlacementSize(index) / 10 for index in range(4))
        self.mainWindow.SetWallWidth(self.mainWindow.wallWidthSelector.slider.value())
        self.mainWindow.wallWidthSelector.update()
        self.RefreshSizeUnits()
        self.RefreshStepSizing()
        self.mainWindow.RefreshProperties()
        self.RefreshMeasurementVisibility()
        self.mainWindow.viewport.update()
        self.mainWindow.ProjectSettingsChanged()

    def RefreshSizeUnits(self):
        v = self.mainWindow.viewport
        divisor, unit = MetricUnit(v.unitsMode, "cm")
        for key, field in self.sizeFields.items():
            value = v.DefaultPlacementSize(key)
            default = wallPresetWidths[key] if isinstance(key, int) else (openingDefaultSizes | miscDefaultSizes)[key]
            default = NominalPlacementSize(default * 10, v.unitsMode)
            blocker = QtCore.QSignalBlocker(field)
            field.setDecimals(0 if unit == "mm" else 3 if unit in ("m", "ft", "in") else 1)
            field.setRange(1 / divisor, max(100000, NominalPlacementSize(100000, v.unitsMode)) / divisor)
            field.setSingleStep((25.4 if v.unitsMode in imperialModes else 10) / divisor)
            field.setSuffix(" " + unit)
            field.setValue(value / divisor)
            del blocker
            self.buildResetButtons[key].setEnabled(value != default)
            self.buildResetButtons[key].setToolTip(f"Reset to {FormatLength(default, v.unitsMode, 'cm')}")

    def eventFilter(self, watched, event):
        if (event.type() == QtCore.QEvent.Type.KeyPress and
                event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter) and
                isinstance(watched, (QtWidgets.QAbstractSpinBox, QtWidgets.QLineEdit))):
            # Moving focus commits the editor without activating the dialog's default OK button.
            self.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
            event.accept()
            return True
        key = watched.property("measurementKey")
        if key in self.measurementSliders:
            slider = self.measurementSliders[key]
            eventType = event.type()
            if eventType == QtCore.QEvent.Type.Wheel:
                delta = event.angleDelta().y()
                if delta:
                    self.measurementWheelDeltas[key] += delta
                    steps = int(self.measurementWheelDeltas[key] / 120)
                    self.measurementWheelDeltas[key] -= steps * 120
                    slider.setValue(max(0, min(slider.maximum(), slider.value() - steps)))
                elif event.pixelDelta().y():
                    slider.setValue(max(0, min(slider.maximum(), slider.value() - (1 if event.pixelDelta().y() > 0 else -1))))
                event.accept()
                return True
            if watched is slider:
                return super().eventFilter(watched, event)
            pressed = eventType == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.LeftButton
            moved = eventType == QtCore.QEvent.Type.MouseMove and self.measurementDragging == key
            released = (eventType == QtCore.QEvent.Type.MouseButtonRelease and
                        event.button() == QtCore.Qt.MouseButton.LeftButton and self.measurementDragging == key)
            if pressed or moved or released:
                if pressed:
                    self.measurementDragging = key
                    slider.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
                    slider.setSliderDown(True)
                slider.SetValueAt(slider.mapFromGlobal(event.globalPosition().toPoint()))
                if released:
                    self.measurementDragging = None
                    slider.setSliderDown(False)
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def SetMeasurementMode(self, key, value):
        blocker = QtCore.QSignalBlocker(self.measurementSliders[key])
        self.measurementSliders[key].setValue(self.measurementModes[key].index(value))
        del blocker
        self.measurementResetButtons[key].setEnabled(value != measurementDefaults[key])
        self.mainWindow.viewport.measurementSettings[key] = value
        self.mainWindow.RefreshProperties()
        self.mainWindow.viewport.update()
        self.mainWindow.ProjectSettingsChanged()

    def RefreshMeasurementVisibility(self):
        v = self.mainWindow.viewport
        view = self.mainWindow.exportPanel.projectView
        unitsBlocker = QtCore.QSignalBlocker(self.unitsField)
        self.unitsField.setCurrentText(view["unitsMode"] if view is not None else v.unitsMode)
        del unitsBlocker
        precisionBlocker = QtCore.QSignalBlocker(self.precisionField)
        self.precisionField.setCurrentText(view["measurementPrecision"] if view is not None else v.measurementPrecision)
        del precisionBlocker
        mode = view["unitsMode"] if view is not None else v.unitsMode
        for index, step in enumerate(measurementPrecisions.values()):
            label = ("1/16 inch", "1/4 inch", "1 inch")[index] if mode in imperialModes else FormatLength(step, mode, "mm")
            self.precisionField.setItemData(index, f"Round canvas measurements to the nearest {label}", QtCore.Qt.ItemDataRole.ToolTipRole)
        showGrid = view["showGrid"] if view is not None else v.showGrid
        showMeasurements = view["showMeasurements"] if view is not None else v.showMeasurements
        measurementVisibility = view["measurementVisibility"] if view is not None else v.measurementVisibility
        gridBlocker = QtCore.QSignalBlocker(self.showGridField)
        self.showGridField.setChecked(showGrid)
        del gridBlocker
        blocker = QtCore.QSignalBlocker(self.measurementVisibilityTree)
        states = []
        for key, item in self.measurementVisibilityItems.items():
            if key == "all":
                continue
            enabled = showMeasurements and measurementVisibility[key]
            state = QtCore.Qt.CheckState.Checked if enabled else QtCore.Qt.CheckState.Unchecked
            states.append(state)
            item.setCheckState(0, state)
            item.setForeground(0, QtGui.QBrush(QtGui.QColor(themeColors["text" if enabled else "treeDisabledText"])))
        state = (QtCore.Qt.CheckState.Checked if all(value == QtCore.Qt.CheckState.Checked for value in states)
                 else QtCore.Qt.CheckState.Unchecked if all(value == QtCore.Qt.CheckState.Unchecked for value in states)
                 else QtCore.Qt.CheckState.PartiallyChecked)
        item = self.measurementVisibilityItems["all"]
        item.setCheckState(0, state)
        item.setForeground(0, QtGui.QBrush(QtGui.QColor(themeColors["treeDisabledText" if state == QtCore.Qt.CheckState.Unchecked else "text"])))
        del blocker

    def SetMeasurementVisibility(self, key, checked):
        panel = self.mainWindow.exportPanel
        if panel.projectView is not None and not panel.applying:
            panel.EditProjectSettings(lambda: self.SetMeasurementVisibility(key, checked))
            return
        v = self.mainWindow.viewport
        if key == "all":
            v.showMeasurements = checked
            v.measurementVisibility = dict.fromkeys(v.measurementVisibility, checked)
        else:
            if not v.showMeasurements:
                v.measurementVisibility = dict.fromkeys(v.measurementVisibility, False)
            v.measurementVisibility[key] = checked
            v.showMeasurements = any(v.measurementVisibility.values())
        self.RefreshMeasurementVisibility()
        v.update()
        self.mainWindow.RefreshProperties()
        self.mainWindow.ProjectSettingsChanged()

    def SetDefaultSize(self, key, value, canonical = False):
        v = self.mainWindow.viewport
        if v.unitsMode in imperialModes and not canonical:
            divisor, unused = MetricUnit(v.unitsMode, "cm")
            v.imperialDefaultSizes[str(key)] = round(value * divisor, 6)
        else:
            v.imperialDefaultSizes.pop(str(key), None)
            if not canonical:
                divisor, unused = MetricUnit(v.unitsMode, "cm")
                value = round(value * divisor / 10, 6)
            if isinstance(key, int):
                v.wallPresetWidths[key] = value
            elif key in miscDefaultSizes:
                v.miscDefaultSizes[key] = value
            else:
                v.openingDefaultSizes[key] = value
        if isinstance(key, int):
            selector = self.mainWindow.wallWidthSelector
            selector.widths = tuple(v.DefaultPlacementSize(index) / 10 for index in range(4))
            selector.update()
            if selector.slider.value() == key:
                self.mainWindow.SetWallWidth(key)
        self.RefreshSizeUnits()
        self.mainWindow.ProjectSettingsChanged()
        if not self.mainWindow.sessionTimer.isActive():
            self.mainWindow.sessionTimer.start(500)

    def SetGridIntensity(self, key, value):
        panel = self.mainWindow.exportPanel
        if panel.projectView is not None and not panel.applying:
            panel.EditProjectSettings(lambda: self.SetGridIntensity(key, value))
            return
        value = round(max(0.0, min(2.0 if key == "overall" else 1.0, value)), 3)
        sliderBlocker = QtCore.QSignalBlocker(self.sliders[key])
        fieldBlocker = QtCore.QSignalBlocker(self.valueFields[key])
        self.sliders[key].setValue(round(value * 1000))
        self.valueFields[key].setValue(value)
        del sliderBlocker, fieldBlocker
        self.resetButtons[key].setEnabled(value != gridIntensityDefaults[key])
        self.mainWindow.viewport.gridIntensities[key] = value
        self.mainWindow.viewport.update()
        self.mainWindow.ProjectSettingsChanged()
        if not self.mainWindow.sessionTimer.isActive():
            self.mainWindow.sessionTimer.start(500)

    def RefreshLinework(self):
        view = self.mainWindow.exportPanel.projectView
        settings = view["lineworkSettings"] if view is not None else self.mainWindow.viewport.lineworkSettings
        for key, value in settings.items():
            blockers = [QtCore.QSignalBlocker(self.lineworkSliders[key]), QtCore.QSignalBlocker(self.lineworkFields[key])]
            self.lineworkSliders[key].setValue(round(value * 1000))
            if self.lineworkFields[key].value() != value:
                self.lineworkFields[key].setValue(value)
            self.lineworkResetButtons[key].setEnabled(value != lineworkDefaults[key])
            del blockers

    def SetLineWeight(self, key, value):
        panel = self.mainWindow.exportPanel
        if panel.projectView is not None and not panel.applying:
            panel.EditProjectSettings(lambda: self.SetLineWeight(key, value))
            return
        minimum, maximum = (1, 4) if key == "baseWidth" else (0, 2)
        settings = dict(self.mainWindow.viewport.lineworkSettings)
        settings[key] = round(max(minimum, min(maximum, value)), 3)
        self.mainWindow.SetLinework(settings)
