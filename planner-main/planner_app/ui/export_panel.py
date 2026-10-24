"""Per-option export overrides and their temporary viewport preview."""



import copy

import math

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from planner_app.graphics import palette
from planner_app.graphics.compositing import TextureMapping, CompactTextureName

from planner_app.graphics.icons import UiIcon

from planner_app.graphics.theme import gridIntensityDefaults

from planner_app.preferences import lineworkDefaults

from planner_app.export_bounds import AutomaticBounds, BorderSize

from planner_app.units import unitModes

from planner_app.paths import appDirectory

from .widgets import DownwardComboBox, DragSlider, VisibilityItemDelegate, SectionHeading, UnitSpinBox, ExpressionSpinBox

from .color_picker import ColorPickerDialog
from .export_history import ExportHistoryMixin





class ExportPanel(ExportHistoryMixin, QtWidgets.QWidget):

    def __init__(self, mainWindow):

        super().__init__()

        self.mainWindow = mainWindow

        mainWindow.viewport.exportOverlay.renderVector = lambda outputFormat: self.Render(outputFormat, preview = True, previewScene = True)
        mainWindow.viewport.exportOverlay.vectorSceneOnly = True
        self.colorPreviewTimer = QtCore.QTimer(self)
        self.colorPreviewTimer.setSingleShot(True)
        self.colorPreviewTimer.setInterval(33)
        self.colorPreviewTimer.timeout.connect(mainWindow.viewport.update)

        self.overrides = {}

        self.projectView = None

        self.projectZoom = None

        self.projectPanOffset = None

        self.exportZoom = None

        self.exportPanOffset = None

        self.effectiveView = None

        self.applying = False

        self.pathProject = None

        self.automaticPath = None

        rowHeight = 32

        headingHeight = 40

        panelLayout = QtWidgets.QVBoxLayout(self)

        panelLayout.setContentsMargins(0, 0, 0, 0)

        panelLayout.setSpacing(0)

        headingRow = QtWidgets.QVBoxLayout()

        headingRow.setContentsMargins(14, 14, 14, 0)

        exportHeading = SectionHeading("Export", "Export")

        headingRow.addWidget(exportHeading)

        panelLayout.addLayout(headingRow)

        pathRow = QtWidgets.QHBoxLayout()

        pathRow.setContentsMargins(14, 14, 14, 6)

        pathRow.setSpacing(6)

        self.pathField = QtWidgets.QLineEdit()

        self.pathField.setPlaceholderText("Export file path")

        self.pathField.setAccessibleName("Export file path")

        self.browseButton = QtWidgets.QToolButton()

        self.browseButton.setObjectName("exportBrowseButton")

        self.browseButton.setIcon(UiIcon("folder_open"))

        self.browseButton.setIconSize(QtCore.QSize(26, 26))

        self.browseButton.setFixedSize(44, 32)

        self.browseButton.setToolTip("Browse")

        self.browseButton.setAccessibleName("Browse export file path")

        self.browseButton.clicked.connect(self.BrowsePath)

        pathRow.addWidget(self.pathField, 1)

        pathRow.addWidget(self.browseButton)

        panelLayout.addLayout(pathRow)

        typeRow = QtWidgets.QHBoxLayout()

        typeRow.setContentsMargins(14, 8, 14, 6)

        typeRow.setSpacing(8)

        typeLabel = QtWidgets.QLabel("Type")

        self.typeField = DownwardComboBox()

        self.typeField.addItem("PNG (raster)", "PNG")
        self.typeField.addItem("SVG (vector)", "SVG")
        self.typeField.addItem("Optimized PNG (raster)", "PNG_OPTIMIZED")

        self.typeField.setAccessibleName("Export type")

        typeLabel.setBuddy(self.typeField)

        typeRow.addWidget(typeLabel)

        typeRow.addWidget(self.typeField, 1)

        panelLayout.addLayout(typeRow)

        separatorRow = QtWidgets.QHBoxLayout()
        separatorRow.setContentsMargins(14, 4, 14, 4)
        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        separator.setObjectName("sectionHeadingLine")
        separatorRow.addWidget(separator)
        panelLayout.addLayout(separatorRow)

        modeLayout = QtWidgets.QVBoxLayout()

        modeLayout.setContentsMargins(14, 8, 14, 6)

        self.scaleModeTabs = QtWidgets.QTabWidget()

        self.scaleModeTabs.setAccessibleName("Export scale mode")

        self.scaleModeTabs.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Maximum)

        digitalPage = QtWidgets.QWidget()

        architecturalPage = QtWidgets.QWidget()

        digitalLayout = QtWidgets.QVBoxLayout(digitalPage)

        architecturalPageLayout = QtWidgets.QVBoxLayout(architecturalPage)

        for pageLayout in (digitalLayout, architecturalPageLayout):

            pageLayout.setContentsMargins(0, 0, 0, 0)

            pageLayout.setSpacing(0)

        self.scaleModeTabs.addTab(digitalPage, "Digital")

        self.scaleModeTabs.addTab(architecturalPage, "Architectural")

        modeLayout.addWidget(self.scaleModeTabs)

        panelLayout.addLayout(modeLayout)

        self.digitalScaleRow = QtWidgets.QWidget()

        scaleRow = QtWidgets.QHBoxLayout(self.digitalScaleRow)

        scaleRow.setContentsMargins(14, 8, 14, 6)

        scaleRow.setSpacing(8)

        scaleLabel = QtWidgets.QLabel("Scale")

        scaleLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)

        self.scaleField = UnitSpinBox()

        self.scaleField.setObjectName("settingsValue")

        self.scaleField.setDecimals(2)

        self.scaleField.setRange(.01, 1000000)

        self.scaleField.setValue(100)

        self.scaleField.setFixedWidth(120)

        self.scaleField.setKeyboardTracking(False)

        self.scaleField.setAccessibleName("Export scale")

        self.scaleField.setToolTip("Pixels per meter")

        scaleLabel.setBuddy(self.scaleField)

        scaleRow.addWidget(scaleLabel)

        scaleRow.addWidget(self.scaleField)

        self.scaleUnitsField = DownwardComboBox()

        self.scaleUnitsField.addItems(("px/m", "px/cm"))

        self.scaleUnitsField.setItemData(0, "Pixels per meter", QtCore.Qt.ItemDataRole.ToolTipRole)

        self.scaleUnitsField.setItemData(1, "Pixels per centimeter", QtCore.Qt.ItemDataRole.ToolTipRole)

        self.scaleUnitsField.setToolTip("Pixels per meter")

        self.scaleUnitsField.setAccessibleName("Export scale units")

        scaleRow.addWidget(self.scaleUnitsField, 1)

        digitalLayout.addWidget(self.digitalScaleRow)

        self.resolutionRow = QtWidgets.QWidget()

        resolutionRow = QtWidgets.QHBoxLayout(self.resolutionRow)

        resolutionRow.setContentsMargins(14, 0, 14, 6)

        resolutionRow.addWidget(QtWidgets.QLabel("Resolution"))

        self.resolutionFields = []

        for name in ("Width", "Height"):

            field = ExpressionSpinBox()

            field.setObjectName("settingsValue")

            field.setRange(1, 32767)

            field.setAccessibleName(f"Export pixel {name.lower()}")

            field.setToolTip(f"{name} in pixels, including the border")

            field.setKeyboardTracking(False)

            resolutionRow.addWidget(field, 1)

            self.resolutionFields.append(field)

            if name == "Width":

                resolutionRow.addWidget(QtWidgets.QLabel("×"))

        digitalLayout.addWidget(self.resolutionRow)

        self.architecturalRow = QtWidgets.QWidget()

        architecturalLayout = QtWidgets.QHBoxLayout(self.architecturalRow)

        architecturalLayout.setContentsMargins(14, 8, 14, 6)

        architecturalLayout.addWidget(QtWidgets.QLabel("Scale"))

        self.architecturalScaleField = DownwardComboBox()

        self.architecturalScaleField.setEditable(True)

        self.architecturalScaleField.addItems([f"1:{value}" for value in (1, 5, 10, 20, 25, 50, 100, 200, 500, 1000)])

        self.architecturalScaleField.setCurrentText("1:100")

        self.architecturalScaleField.setAccessibleName("Architectural scale")

        architecturalLayout.addWidget(self.architecturalScaleField, 1)

        architecturalPageLayout.addWidget(self.architecturalRow)

        self.dpiRow = QtWidgets.QWidget()

        dpiLayout = QtWidgets.QHBoxLayout(self.dpiRow)

        dpiLayout.setContentsMargins(0, 0, 0, 0)

        ppiLabel = QtWidgets.QLabel("PPI")
        ppiLabel.setToolTip("Pixels per inch at the selected architectural scale. Often referred to as DPI.")
        dpiLayout.addWidget(ppiLabel)

        self.dpiField = DownwardComboBox()

        self.dpiField.setEditable(True)

        self.dpiField.addItems(("96", "150", "300", "600"))

        self.dpiField.setCurrentText("300")

        self.dpiField.lineEdit().setValidator(QtGui.QIntValidator(1, 2400, self))

        self.dpiField.setAccessibleName("Export pixels per inch")
        self.dpiField.setToolTip("Pixels per inch at the selected architectural scale. Often referred to as DPI.")
        ppiLabel.setBuddy(self.dpiField)

        dpiLayout.addWidget(self.dpiField, 1)

        architecturalLayout.addWidget(self.dpiRow, 1)

        self.architecturalResolutionRow = QtWidgets.QWidget()

        architecturalResolutionLayout = QtWidgets.QHBoxLayout(self.architecturalResolutionRow)

        architecturalResolutionLayout.setContentsMargins(14, 0, 14, 6)

        self.resolutionLabel = QtWidgets.QLabel("Resolution: —")

        self.resolutionLabel.setObjectName("exportResolution")

        self.resolutionLabel.setAccessibleName("Export resolution")

        architecturalResolutionLayout.addWidget(self.resolutionLabel)

        architecturalPageLayout.addWidget(self.architecturalResolutionRow)

        self.scrollArea = QtWidgets.QScrollArea()

        self.scrollArea.setWidgetResizable(True)

        self.scrollArea.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        self.scrollArea.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        panelLayout.addWidget(self.scrollArea, 1)

        page = QtWidgets.QWidget()

        self.scrollArea.setWidget(page)

        layout = QtWidgets.QVBoxLayout(page)

        layout.setContentsMargins(14, 14, 14, 14)

        layout.setSpacing(20)

        sections = {}

        self.sectionButtons, self.sectionContents = {}, {}

        for name in ("Canvas", "Border", "Grid", "Line Weight", "Measurements", "Composite", "Visibility"):

            section = QtWidgets.QWidget()

            sectionLayout = QtWidgets.QVBoxLayout(section)

            sectionLayout.setContentsMargins(0, 0, 0, 0)

            sectionLayout.setSpacing(12)

            heading = QtWidgets.QPushButton(name)

            heading.setObjectName("exportSectionHeading")

            heading.setCheckable(True)

            heading.setChecked(False)

            heading.setIcon(UiIcon("arrow_drop_up"))

            heading.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

            heading.setAccessibleName(f"{name} section")

            heading.setToolTip(f"Expand {name}")

            sectionLayout.addWidget(heading)

            contents = QtWidgets.QWidget()

            contentsLayout = QtWidgets.QVBoxLayout(contents)

            contentsLayout.setContentsMargins(0, 0, 0, 0)

            contentsLayout.setSpacing(12)

            sectionLayout.addWidget(contents)

            contents.hide()

            self.sectionButtons[name], self.sectionContents[name] = heading, contents
            if name == "Composite":
                self.compositeSection = section

            heading.toggled.connect(lambda expanded, name = name: self.SetSectionExpanded(name, expanded))

            sections[name] = contentsLayout

            layout.addWidget(section)

        layout.addStretch(1)



        canvasForm = QtWidgets.QGridLayout()

        canvasForm.setHorizontalSpacing(8)

        canvasForm.setVerticalSpacing(12)

        canvasForm.setColumnStretch(1, 1)

        label = QtWidgets.QLabel("Theme")

        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)

        self.canvasThemeField = DownwardComboBox()

        self.canvasThemeField.setAccessibleName("Export Canvas Theme")

        self.canvasThemeField.addItems(sorted((name for name, definition in palette.themeDefinitions.items()

                                              if definition["type"] == "canvas"),

                                             key = lambda name: (name != "Dark Canvas", name.casefold())))

        self.canvasThemeField.setCurrentText(palette.activeCanvasTheme)

        label.setBuddy(self.canvasThemeField)

        canvasForm.addWidget(label, 0, 0)

        canvasForm.addWidget(self.canvasThemeField, 0, 1)

        sections["Canvas"].addLayout(canvasForm)

        borderForm = QtWidgets.QGridLayout()

        borderForm.setHorizontalSpacing(8)

        borderForm.setVerticalSpacing(12)

        borderForm.setColumnStretch(1, 1)

        sections["Border"].addLayout(borderForm)

        self.borderField = DownwardComboBox()

        self.borderField.addItems(("None", "Plain", "Frame", "Corner Marks", "Reference Zones", "Marked", "Ruler", "Ruler + Reference Zones"))

        self.borderField.setAccessibleName("Export border")

        borderForm.addWidget(self.borderField, 0, 0, 1, 2)

        self.borderSizeOptions = QtWidgets.QWidget()

        self.borderSizeOptions.setObjectName("exportBorderSizeOptions")

        borderSizeLayout = QtWidgets.QVBoxLayout(self.borderSizeOptions)

        borderSizeLayout.setContentsMargins(0, 0, 0, 0)

        borderSizeLayout.setSpacing(4)

        borderSizeLayout.addWidget(QtWidgets.QLabel("Border Size"))

        borderSizeRow = QtWidgets.QHBoxLayout()

        self.borderSizeSlider = DragSlider(QtCore.Qt.Orientation.Horizontal)

        self.borderSizeSlider.setRange(1, 128)

        self.borderSizeSlider.setValue(28)

        self.borderSizeSlider.setAccessibleName("Export border size")

        self.borderSizeField = ExpressionSpinBox()

        self.borderSizeField.setObjectName("settingsValue")

        self.borderSizeField.setRange(1, 128)

        self.borderSizeField.setValue(28)

        self.borderSizeField.setSuffix(" px")

        self.borderSizeField.setFixedWidth(72)

        self.borderSizeField.setAccessibleName("Export border size in pixels or SVG units")

        borderSizeRow.addWidget(self.borderSizeSlider, 1)

        borderSizeRow.addWidget(self.borderSizeField)

        borderSizeLayout.addLayout(borderSizeRow)

        borderForm.addWidget(self.borderSizeOptions, 2, 0, 1, 2)



        self.gridColorOptions = QtWidgets.QWidget()

        gridColorForm = QtWidgets.QGridLayout(self.gridColorOptions)

        gridColorForm.setContentsMargins(0, 0, 0, 0)

        gridColorForm.setHorizontalSpacing(8)

        gridColorForm.setColumnStretch(1, 1)

        for form, name, text, row in ((canvasForm, "canvas", "Background", 1), (canvasForm, "lines", "Lines", 3), (borderForm, "border", "Color", 1),

                                 (gridColorForm, "grid", "Color", 1)):

            colorRow = QtWidgets.QHBoxLayout()

            colorRow.setSpacing(8)

            colorLabel = QtWidgets.QLabel(text)

            colorLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)

            button = QtWidgets.QPushButton(" Theme")

            button.setAccessibleName(f"Export {name} color")

            button.setToolTip(f"Choose a {name} color for export")

            colorLabel.setBuddy(button)

            reset = QtWidgets.QPushButton()

            reset.setIcon(UiIcon("refresh"))

            reset.setFixedWidth(32)

            reset.setToolTip(f"Use the theme's {name} color")

            reset.setAccessibleName(f"Reset export {name} color to theme")

            setattr(self, name + "ColorLabel", colorLabel)

            setattr(self, name + "ColorButton", button)

            setattr(self, name + "ColorReset", reset)

            colorRow.addWidget(button, 1)

            colorRow.addWidget(reset)

            form.addWidget(colorLabel, row, 0)

            form.addLayout(colorRow, row, 1)



        wallsLabel = QtWidgets.QLabel("Walls")
        wallsLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.wallStyleField = DownwardComboBox()
        self.wallStyleField.addItems(("Material", "Solid", "Outline"))
        self.wallStyleField.setAccessibleName("Export wall fill")
        wallsLabel.setBuddy(self.wallStyleField)
        canvasForm.addWidget(wallsLabel, 2, 0)
        canvasForm.addWidget(self.wallStyleField, 2, 1)
        self.solidObjectsField = QtWidgets.QCheckBox("Solid Objects")
        self.solidObjectsField.setChecked(True)
        self.solidObjectsField.setToolTip("Fill objects to hide the canvas and grid behind them")
        canvasForm.addWidget(self.solidObjectsField, 4, 0, 1, 2, QtCore.Qt.AlignmentFlag.AlignHCenter)

        viewport = mainWindow.viewport

        self.showGridField = QtWidgets.QCheckBox("Show Grid")

        self.showGridField.setChecked(viewport.showGrid)

        sections["Grid"].addWidget(self.showGridField, alignment = QtCore.Qt.AlignmentFlag.AlignHCenter)

        sections["Grid"].addWidget(self.gridColorOptions)

        self.gridOptions = QtWidgets.QWidget()

        self.gridOptions.setObjectName("exportGridOptions")

        gridForm = QtWidgets.QFormLayout(self.gridOptions)

        gridForm.setContentsMargins(0, 0, 0, 0)

        gridForm.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapAllRows)

        gridForm.setHorizontalSpacing(16)

        gridForm.setVerticalSpacing(12)

        self.gridSliders, self.gridValueFields, self.gridResetButtons = {}, {}, {}

        for key, text in (("overall", "Grid Intensity"), ("major", "Major Gridlines"),

                          ("minor", "Minor Gridlines"), ("origin", "Origin")):

            label = QtWidgets.QLabel(text)

            field = QtWidgets.QWidget()

            row = QtWidgets.QHBoxLayout(field)

            row.setContentsMargins(0, 0, 0, 0)

            row.setSpacing(8)

            maximum = 2 if key == "overall" else 1

            slider = DragSlider(QtCore.Qt.Orientation.Horizontal)

            slider.setRange(0, maximum * 1000)

            slider.setMinimumHeight(26)

            slider.setAccessibleName(f"Export {text}")

            slider.setValue(round(viewport.gridIntensities[key] * 1000))

            valueField = UnitSpinBox()

            valueField.setObjectName("settingsValue")

            valueField.setRange(0, maximum)

            valueField.setDecimals(3)

            valueField.setSingleStep(.01)

            valueField.setFixedWidth(80)

            valueField.setAccessibleName(f"Export {text} value")

            valueField.setValue(viewport.gridIntensities[key])

            reset = QtWidgets.QPushButton()

            reset.setIcon(UiIcon("refresh"))

            reset.setFixedWidth(34)

            reset.setMaximumHeight(32)

            reset.setToolTip(f"Reset {text.lower()} to {gridIntensityDefaults[key]:.3f}")

            reset.setAccessibleName(f"Reset export {text}")

            reset.setEnabled(viewport.gridIntensities[key] != gridIntensityDefaults[key])

            row.addWidget(slider, 1)

            row.addWidget(valueField)

            row.addWidget(reset)

            gridForm.addRow(label, field)

            self.gridSliders[key], self.gridValueFields[key], self.gridResetButtons[key] = slider, valueField, reset

            if key == "overall":

                spacer = QtWidgets.QWidget()

                spacer.setFixedHeight(8)

                gridForm.addRow(spacer)

        self.gridOptions.setEnabled(viewport.showGrid)

        sections["Grid"].addWidget(self.gridOptions)



        weightForm = QtWidgets.QFormLayout()

        weightForm.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapAllRows)

        weightForm.setHorizontalSpacing(16)

        weightForm.setVerticalSpacing(12)

        self.lineworkSliders, self.lineworkFields, self.lineworkResetButtons = {}, {}, {}

        for key, text in (("baseWidth", "Base width"), ("walls", "Walls"), ("architectural", "Architectural objects"),

                          ("furnishings", "Furnishings"), ("dimensions", "Dimensions")):

            minimum, maximum = (1, 4) if key == "baseWidth" else (0, 2)

            slider = DragSlider(QtCore.Qt.Orientation.Horizontal)

            slider.setRange(minimum * 1000, maximum * 1000)

            slider.setMinimumHeight(26)

            slider.setAccessibleName(f"Export {text}")

            field = UnitSpinBox()

            field.setObjectName("settingsValue")

            field.setRange(minimum, maximum)

            field.setDecimals(3)

            field.setSingleStep(.01)

            field.setSuffix(" px" if key == "baseWidth" else "×")

            field.setKeyboardTracking(False)

            field.setFixedWidth(104 if key == "baseWidth" else 88)

            field.setAccessibleName(f"Export {text} value")

            value = viewport.lineworkSettings[key]

            slider.setValue(round(value * 1000))

            field.setValue(value)

            reset = QtWidgets.QPushButton()

            reset.setIcon(UiIcon("refresh"))

            reset.setFixedWidth(34)

            reset.setMaximumHeight(32)

            reset.setToolTip(f"Reset {text.lower()} to {lineworkDefaults[key]:g}")

            reset.setAccessibleName(f"Reset export {text}")

            reset.setEnabled(value != lineworkDefaults[key])

            container = QtWidgets.QWidget()

            row = QtWidgets.QHBoxLayout(container)

            row.setContentsMargins(0, 0, 0, 0)

            row.setSpacing(8)

            row.addWidget(slider, 1)

            row.addWidget(field)

            row.addWidget(reset)

            weightForm.addRow(text, container)

            self.lineworkSliders[key], self.lineworkFields[key], self.lineworkResetButtons[key] = slider, field, reset

        sections["Line Weight"].addLayout(weightForm)



        unitsRow = QtWidgets.QHBoxLayout()

        unitsRow.setSpacing(16)

        unitsLabel = QtWidgets.QLabel("Units")

        unitsLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)

        unitsLabel.setFixedHeight(32)

        self.unitsField = DownwardComboBox()

        self.unitsField.addItems(unitModes)

        self.unitsField.setFixedHeight(32)

        self.unitsField.setCurrentText("Millimeters")

        self.unitsField.currentTextChanged.connect(lambda mode: self.SetOverride("unitsMode", mode))

        unitsRow.addWidget(unitsLabel)

        unitsRow.addWidget(self.unitsField, 1)

        sections["Measurements"].addLayout(unitsRow)

        self.measurementVisibilityTree = QtWidgets.QTreeWidget()

        self.measurementVisibilityItems = {}

        states = []

        for key, text in (("all", "Show all measurements"), ("walls", "Show wall measurements"),

                          ("stairs", "Show stair measurements"), ("counters", "Show counter measurements"),

                          ("railings", "Show railing measurements"), ("elevators", "Show elevator measurements")):

            parent = self.measurementVisibilityTree if key == "all" else self.measurementVisibilityItems["all"]

            item = QtWidgets.QTreeWidgetItem(parent, [text])

            item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsUserCheckable)

            enabled = viewport.showMeasurements and viewport.measurementVisibility.get(key, False)

            state = QtCore.Qt.CheckState.Checked if enabled else QtCore.Qt.CheckState.Unchecked

            item.setCheckState(0, state)

            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, key)

            self.measurementVisibilityItems[key] = item

            if key != "all":

                states.append(state)

        state = (QtCore.Qt.CheckState.Checked if all(state == QtCore.Qt.CheckState.Checked for state in states)

                 else QtCore.Qt.CheckState.Unchecked if all(state == QtCore.Qt.CheckState.Unchecked for state in states)

                 else QtCore.Qt.CheckState.PartiallyChecked)

        self.measurementVisibilityItems["all"].setCheckState(0, state)

        self.measurementVisibilityTree.setRootIsDecorated(False)

        self.measurementVisibilityTree.setItemsExpandable(False)

        self.measurementVisibilityTree.setExpandsOnDoubleClick(False)



        vignetteHeading = SectionHeading("Vignette")
        vignetteHeader = QtWidgets.QVBoxLayout()
        vignetteHeader.setSpacing(6)
        vignetteHeader.addWidget(vignetteHeading)
        self.enableVignetteField = QtWidgets.QCheckBox("Enable Vignette")
        vignetteHeader.addWidget(self.enableVignetteField, alignment = QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.vignetteStrengthOptions = QtWidgets.QWidget()
        strengthLayout = QtWidgets.QVBoxLayout(self.vignetteStrengthOptions)
        strengthLayout.setContentsMargins(0, 0, 0, 0)
        strengthLayout.setSpacing(4)
        strengthLabel = QtWidgets.QLabel("Strength")
        strengthLabel.setObjectName("exportControlLabel")
        strengthLayout.addWidget(strengthLabel)
        strengthRow = QtWidgets.QHBoxLayout()
        strengthRow.setSpacing(8)
        self.vignetteStrengthSlider = DragSlider(QtCore.Qt.Orientation.Horizontal)
        self.vignetteStrengthSlider.setRange(0, 2000)
        self.vignetteStrengthSlider.setValue(250)
        self.vignetteStrengthSlider.setAccessibleName("Vignette strength from 0 to 2")
        strengthRow.addWidget(self.vignetteStrengthSlider, 1)
        self.vignetteStrengthField = UnitSpinBox()
        self.vignetteStrengthField.setObjectName("settingsValue")
        self.vignetteStrengthField.setKeyboardTracking(False)
        self.vignetteStrengthField.setRange(0, 2)
        self.vignetteStrengthField.setDecimals(3)
        self.vignetteStrengthField.setSingleStep(.01)
        self.vignetteStrengthField.setFixedWidth(80)
        self.vignetteStrengthField.setAccessibleName("Vignette strength value")
        self.vignetteStrengthReset = QtWidgets.QPushButton()
        self.vignetteStrengthReset.setIcon(UiIcon("refresh"))
        self.vignetteStrengthReset.setFixedWidth(32)
        self.vignetteStrengthReset.setAccessibleName("Reset vignette strength")
        self.vignetteStrengthReset.setToolTip("Reset vignette strength to default")
        strengthRow.addWidget(self.vignetteStrengthField)
        strengthRow.addWidget(self.vignetteStrengthReset)
        strengthLayout.addLayout(strengthRow)
        vignetteHeader.addWidget(self.vignetteStrengthOptions)
        sections["Composite"].addLayout(vignetteHeader)
        sections["Composite"].addSpacing(8)
        textureHeading = SectionHeading("Texture")
        textureHeader = QtWidgets.QVBoxLayout()
        textureHeader.setSpacing(6)
        textureHeader.addWidget(textureHeading)
        self.textureField = DownwardComboBox()
        self.textureField.setAccessibleName("Export normal-map texture")
        self.textureField.addItem("None", None)
        formats = {"." + bytes(value).decode().lower() for value in QtGui.QImageReader.supportedImageFormats()}
        for path in sorted((appDirectory / "textures").glob("*"), key = lambda path: path.name.casefold()):
            if path.is_file() and path.suffix.lower() in formats:
                try:
                    label, mode, scale = TextureMapping(path.name)
                except ValueError:
                    continue
                self.textureField.addItem(label, path.name)
        textureHeader.addWidget(self.textureField)
        sections["Composite"].addLayout(textureHeader)
        self.textureSliders, self.textureControls, self.textureFields, self.textureResetButtons = {}, {}, {}, {}
        for name, maximum, initial in (("Scale", 4000, 1000), ("Angle", 360, 0), ("Strength", 1000, 500),
                                        ("Highlights", 1000, 1000), ("Midtones", 1000, 1000), ("Shadows", 1000, 1000)):
            options = QtWidgets.QWidget()
            optionLayout = QtWidgets.QVBoxLayout(options)
            optionLayout.setContentsMargins(0, 0, 0, 0)
            optionLayout.setSpacing(4)
            optionLabel = QtWidgets.QLabel(name)
            optionLabel.setObjectName("exportControlLabel")
            optionLayout.addWidget(optionLabel)
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(8)
            slider = DragSlider(QtCore.Qt.Orientation.Horizontal)
            slider.setRange(0, maximum)
            slider.setValue(initial)
            slider.setAccessibleName(f"Texture {name.lower()}")
            row.addWidget(slider, 1)
            field = ExpressionSpinBox() if name == "Angle" else UnitSpinBox()
            field.setObjectName("settingsValue")
            field.setKeyboardTracking(False)
            field.setRange(0, maximum if name == "Angle" else maximum / 1000)
            if name != "Angle":
                field.setDecimals(3)
                field.setSingleStep(.01)
            field.setFixedWidth(80)
            field.setAccessibleName(f"Texture {name.lower()} value")
            reset = QtWidgets.QPushButton()
            reset.setIcon(UiIcon("refresh"))
            reset.setFixedWidth(32)
            reset.setAccessibleName(f"Reset texture {name.lower()}")
            row.addWidget(field)
            row.addWidget(reset)
            self.textureFields[name], self.textureResetButtons[name] = field, reset
            setattr(self, "texture" + name + "Field", field)
            setattr(self, "texture" + name + "Reset", reset)
            optionLayout.addLayout(row)
            self.textureSliders[name], self.textureControls[name] = slider, options
            setattr(self, "texture" + name + "Slider", slider)
            setattr(self, "texture" + name + "Options", options)
            sections["Composite"].addWidget(options)

        self.visibilityTree = QtWidgets.QTreeWidget()

        visibilityRoots = [mainWindow.visibilityTree.topLevelItem(index) for index in range(mainWindow.visibilityTree.topLevelItemCount())
                           if mainWindow.visibilityTree.topLevelItem(index) is not mainWindow.referenceImageItem]
        for source in visibilityRoots:
            self.visibilityTree.addTopLevelItem(source.clone())

        for tree, section, rowCount in ((self.measurementVisibilityTree, "Measurements", len(self.measurementVisibilityItems)),

                                        (self.visibilityTree, "Visibility", len(mainWindow.visibilityItems))):

            tree.setObjectName("visibilityTree")

            tree.setAccessibleName(f"Export {section}")

            tree.setHeaderHidden(True)

            tree.setIndentation(24)

            tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)

            tree.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

            tree.setItemDelegate(VisibilityItemDelegate(tree, rowHeight = rowHeight))

            tree.expandAll()

            tree.ensurePolished()

            tree.setFixedHeight(rowHeight * rowCount)

            sections[section].addWidget(tree)



        # Keep label-only rows, checkboxes and multi-control rows on the same

        # rhythm. Embedded spinbox editors retain their normal internal layout.

        for widget in self.findChildren(QtWidgets.QWidget):

            if any(heading is widget or heading.isAncestorOf(widget) for heading in (exportHeading, vignetteHeading, textureHeading)):

                continue

            if widget.objectName() == "exportControlLabel":
                widget.ensurePolished()
                widget.setFixedHeight(widget.sizeHint().height())
                continue
            if isinstance(widget, (QtWidgets.QLabel, QtWidgets.QCheckBox, QtWidgets.QRadioButton, QtWidgets.QPushButton,

                                   QtWidgets.QToolButton, QtWidgets.QSlider, QtWidgets.QComboBox,

                                   QtWidgets.QAbstractSpinBox)) or widget is self.pathField:

                widget.setFixedHeight(headingHeight if widget.objectName() == "exportSectionHeading" else rowHeight)



        self.visibilityItems = {}

        def MapVisibility(source, target):

            name = next(name for name, item in mainWindow.visibilityItems.items() if item is source)

            self.visibilityItems[name] = target

            for index in range(source.childCount()):

                MapVisibility(source.child(index), target.child(index))

        for index, source in enumerate(visibilityRoots):
            MapVisibility(source, self.visibilityTree.topLevelItem(index))

        self.solidObjectsField.toggled.connect(lambda checked: self.SetOverride("solidObjects", checked))

        self.wallStyleField.currentTextChanged.connect(lambda style: self.SetOverride("wallStyle", style))

        self.canvasThemeField.currentTextChanged.connect(lambda name: self.SetOverride("canvasTheme", name))

        self.showGridField.toggled.connect(lambda checked: self.SetOverride("showGrid", checked))

        self.textureField.currentIndexChanged.connect(lambda index: self.SetOverride("texture", self.textureField.itemData(index)))

        for name, slider in self.textureSliders.items():
            slider.valueChanged.connect(lambda value, name = name: self.SetOverride("texture" + name, value if name == "Angle" else value / 1000))
            self.textureFields[name].valueChanged.connect(lambda value, name = name: self.SetOverride("texture" + name, value))
            self.textureResetButtons[name].clicked.connect(lambda checked = False, name = name: self.ResetOverride("texture" + name))

        self.enableVignetteField.toggled.connect(lambda checked: self.SetOverride("vignetteEnabled", checked))

        self.vignetteStrengthSlider.valueChanged.connect(lambda value: self.SetOverride("vignetteStrength", value / 1000))
        self.vignetteStrengthField.valueChanged.connect(lambda value: self.SetOverride("vignetteStrength", value))
        self.vignetteStrengthReset.clicked.connect(lambda: self.ResetOverride("vignetteStrength"))

        self.borderField.currentTextChanged.connect(self.SetBorder)

        self.borderSizeSlider.valueChanged.connect(lambda size: self.SetOverride("borderSize", size))

        self.borderSizeField.valueChanged.connect(lambda size: self.SetOverride("borderSize", size))

        for name in ("canvas", "lines", "border", "grid"):

            getattr(self, name + "ColorButton").clicked.connect(lambda checked = False, name = name: self.ChooseColor(name))

            getattr(self, name + "ColorReset").clicked.connect(lambda checked = False, name = name: self.ResetOverride(name + "Color"))

        self.scaleField.valueChanged.connect(self.SetScale)

        self.scaleUnitsField.currentTextChanged.connect(self.SetScaleUnits)

        self.scaleModeTabs.currentChanged.connect(lambda index: self.SetScaleOption("scaleMode", self.scaleModeTabs.tabText(index)))

        self.architecturalScaleField.activated.connect(lambda: self.SetArchitecturalScale())

        self.architecturalScaleField.lineEdit().editingFinished.connect(self.SetArchitecturalScale)

        self.dpiField.activated.connect(lambda: self.SetDpi())

        self.dpiField.lineEdit().editingFinished.connect(self.SetDpi)

        for axis, field in enumerate(self.resolutionFields):

            field.valueChanged.connect(lambda value, axis = axis: self.SetResolution(axis, value))

        self.typeField.currentIndexChanged.connect(lambda index: self.SetPathType(self.typeField.itemData(index)))

        for group, sliders, fields, buttons, defaults in (

                ("viewportSettings", self.gridSliders, self.gridValueFields, self.gridResetButtons, gridIntensityDefaults),

                ("lineworkSettings", self.lineworkSliders, self.lineworkFields, self.lineworkResetButtons, lineworkDefaults)):

            for key in sliders:

                sliders[key].valueChanged.connect(lambda value, group = group, key = key: self.SetOverride(group, value / 1000, key))

                fields[key].valueChanged.connect(lambda value, group = group, key = key: self.SetOverride(group, value, key))

                buttons[key].clicked.connect(lambda checked = False, group = group, key = key, defaults = defaults:

                                             self.SetOverride(group, defaults[key], key))

        self.measurementVisibilityTree.itemChanged.connect(self.SetMeasurementVisibility)

        self.visibilityTree.itemChanged.connect(self.SetVisibility)

        mainWindow.viewport.sceneChanged.connect(self.RefreshControls)

        mainWindow.viewport.exportOverlay.boundsChanged.connect(self.SetBounds)
        mainWindow.viewport.exportOverlay.originChanged.connect(lambda origin: self.SetOverride("gridOrigin", list(origin)))
        self.InitializeExportHistory()



    def CaptureView(self):

        v = self.mainWindow.viewport

        return {"canvasTheme": palette.activeCanvasTheme, "showGrid": v.showGrid,

                "viewportSettings": dict(v.gridIntensities), "lineworkSettings": dict(v.lineworkSettings),

                "showMeasurements": v.showMeasurements, "measurementVisibility": dict(v.measurementVisibility),

                "visibility": dict(v.visibility), "unitsMode": v.unitsMode, "measurementPrecision": v.measurementPrecision}



    def ResolvedView(self):

        view = copy.deepcopy(self.projectView if self.projectView is not None else self.CaptureView())

        view["autoSizingUnitsMode"] = view["unitsMode"]
        view["unitsMode"] = "Millimeters"

        for name, value in self.overrides.items():

            if isinstance(value, dict):

                if name == "measurementVisibility":

                    view[name] = {key: enabled and view["showMeasurements"] for key, enabled in view[name].items()}

                view[name].update(value)

            else:

                view[name] = value

        if "measurementVisibility" in self.overrides:

            view["showMeasurements"] = any(view["measurementVisibility"].values())

        if "visibility" in self.overrides:

            view["visibility"]["World"] = any(value for key, value in view["visibility"].items() if key != "World")

        return view



    def ApplyView(self, view):

        self.applying = True

        try:

            main = self.mainWindow

            v = main.viewport
            v.autoSizingUnitsMode = view.get("autoSizingUnitsMode")

            previousCanvasColor = palette.themeColors["canvas"]
            previousOutlineColor = palette.themeColors["objectOutline"]
            previousSolidObjects = v.solidObjects

            main.SetThemes(canvasTheme = view["canvasTheme"], notify = False)

            if "canvasColor" in view:

                palette.themeColors["canvas"] = view["canvasColor"]

            for name, role in (("borderColor", "rulerBackground"), ("gridColor", "grid")):

                if name in view:

                    palette.themeColors[role] = view[name]

            if "linesColor" in view:
                palette.themeColors["objectOutline"] = view["linesColor"]
                palette.themeColors["wallOutline"] = view["linesColor"]

            main.SetLinework(view["lineworkSettings"], notify = False)

            v.solidObjects = view.get("solidObjects", True)

            if (previousCanvasColor != palette.themeColors["canvas"] or previousSolidObjects != v.solidObjects
                    or previousOutlineColor != palette.themeColors["objectOutline"]):
                previousRevision = v.renderChanges.appearance
                main.RefreshFurnishingRenderers()
                # Palette and solid-fill state are explicit preview-key inputs.
                # Renderer replacement alone must not make a prior state stale.
                v.exportOverlay.colorAppearanceRevisions += v.renderChanges.appearance - previousRevision

            v.wallStyle = view.get("wallStyle", "Material")

            v.gridIntensities = dict(view["viewportSettings"])

            v.showGrid, v.showMeasurements = view["showGrid"], view["showMeasurements"]

            v.unitsMode = view["unitsMode"]
            main.UpdateFurnishingSearch()
            v.measurementPrecision = view["measurementPrecision"]
            v.gridOrigin = tuple(view.get("gridOrigin", (0.0, 0.0)))

            v.measurementVisibility, v.visibility = dict(view["measurementVisibility"]), dict(view["visibility"])

            v.exportOverlay.borderStyle = self.overrides.get("border", "Ruler + Reference Zones" if "ruler" not in self.overrides else "Ruler" if self.overrides["ruler"] else "None")

            v.exportOverlay.drawRuler = v.exportOverlay.borderStyle != "None"

            v.exportOverlay.texture = self.overrides.get("texture")

            v.exportOverlay.textureAngle = self.overrides.get("textureAngle", 0)
            v.exportOverlay.textureSettings = self.TextureSettings()

            v.exportOverlay.vignetteStrength = self.overrides.get("vignetteStrength", .25) if self.overrides.get("vignetteEnabled", False) else 0

            v.exportOverlay.borderSize = BorderSize(v.exportOverlay.borderStyle, self.overrides.get("borderSize", 28))

            v.viewportSceneKey = None

            v.update()

            if main.settingsWindow is not None:

                panel = main.settingsWindow

                normal = self.projectView if self.projectView is not None else view

                for key, value in normal["viewportSettings"].items():

                    blockers = [QtCore.QSignalBlocker(panel.sliders[key]), QtCore.QSignalBlocker(panel.valueFields[key])]

                    panel.sliders[key].setValue(round(value * 1000))

                    panel.valueFields[key].setValue(value)

                    panel.resetButtons[key].setEnabled(value != gridIntensityDefaults[key])

                    del blockers

                main.settingsWindow.RefreshMeasurementVisibility()

            self.effectiveView = self.CaptureView()

        finally:

            self.applying = False



    def SetActive(self, active):
        self.colorPreviewTimer.stop()

        if active and self.projectView is None:

            self.PopulatePath()
            self.exportHistoryState = self.ExportHistoryState()

            self.projectView = self.CaptureView()

            self.projectZoom = self.mainWindow.viewport.zoom

            self.projectPanOffset = QtCore.QPointF(self.mainWindow.viewport.panOffset)

            self.ApplyView(self.ResolvedView())

            self.mainWindow.viewport.exportOverlay.scale = self.ScalePerMeter()

            self.mainWindow.viewport.exportOverlay.outputFormat = "svg" if self.typeField.currentData() == "SVG" else "png"

            self.mainWindow.viewport.exportOverlay.SetActive(True, self.overrides.get("bounds"))

            v = self.mainWindow.viewport

            v.zoom = (self.exportZoom if self.exportZoom is not None else

                      self.ScalePerMeter() / (1000 * v.basePixelsPerMillimeter))

            x, y, width, height = v.exportOverlay.bounds

            scale = v.basePixelsPerMillimeter * v.zoom

            if self.exportPanOffset is not None:

                v.panOffset = QtCore.QPointF(self.exportPanOffset)

            topLeft = v.WorldToViewport(QtCore.QPointF(x, y + height))

            bottomRight = v.WorldToViewport(QtCore.QPointF(x + width, y))

            midpoint = v.DrawingRect().center()

            if (self.exportPanOffset is None or bottomRight.x() < midpoint.x()

                    or topLeft.x() > midpoint.x() or topLeft.y() > midpoint.y()

                    or bottomRight.y() < midpoint.y()):

                v.panOffset = QtCore.QPointF(-(x + width / 2) * scale, (y + height / 2) * scale)

            self.mainWindow.viewport.update()

        elif not active and self.projectView is not None:
            self.EndExportGesture()

            self.exportZoom = self.mainWindow.viewport.zoom

            self.exportPanOffset = QtCore.QPointF(self.mainWindow.viewport.panOffset)

            self.mainWindow.viewport.exportOverlay.SetActive(False)

            self.ApplyView(self.projectView)

            self.mainWindow.viewport.zoom = self.projectZoom

            self.mainWindow.viewport.panOffset = self.projectPanOffset

            self.projectZoom = None

            self.projectPanOffset = None

            self.projectView = None

            self.effectiveView = None

        for control in (*self.mainWindow.connectedOptions.values(), self.mainWindow.groupModeButton,
                        self.mainWindow.transformOrientationButton, self.mainWindow.snapOptionsButton):
            control.setEnabled(not active)
        self.mainWindow.RefreshGroupActions()
        self.RefreshControls()



    def SetScale(self, value):

        value *= 100 if self.scaleUnitsField.currentText() == "px/cm" else 1

        self.overrides["scale"] = value

        if self.projectView is not None:

            v = self.mainWindow.viewport

            v.exportOverlay.scale = value

            v.update()

        self.mainWindow.ProjectSettingsChanged()



    def ScalePerMeter(self):

        if self.overrides.get("scaleMode", "Digital") == "Architectural":

            dpi = self.overrides.get("dpi", 300) if self.typeField.currentData() != "SVG" else 96

            return dpi * 1000 / (25.4 * self.overrides.get("architecturalScale", 100))

        return self.overrides.get("scale", 100)



    def SetScaleUnits(self, units):

        if units not in ("px/m", "px/cm"):

            return

        self.overrides["scaleUnits"] = units

        self.RefreshControls()

        self.mainWindow.ProjectSettingsChanged()



    def SetScaleOption(self, name, value):

        if self.overrides.get(name) == value:

            self.RefreshControls()

            return

        self.overrides[name] = value

        if self.projectView is not None:

            self.mainWindow.viewport.exportOverlay.scale = self.ScalePerMeter()

            if name in ("scaleMode", "architecturalScale"):

                self.mainWindow.viewport.exportOverlay.svgKey = None

            self.mainWindow.viewport.update()

        self.RefreshControls()

        self.mainWindow.ProjectSettingsChanged()



    def SetArchitecturalScale(self):

        text = self.architecturalScaleField.currentText().replace(" ", "")

        try:

            value = float(text[2:] if text.startswith("1:") else text)

            if not math.isfinite(value) or not 1 <= value <= 100000:

                raise ValueError

        except ValueError:

            self.RefreshControls()

            return

        self.SetScaleOption("architecturalScale", value)



    def SetDpi(self):

        try:

            value = int(self.dpiField.currentText())

            if not 1 <= value <= 2400:

                raise ValueError

        except ValueError:

            self.RefreshControls()

            return

        self.SetScaleOption("dpi", value)



    def SetResolution(self, axis, value):

        overlay = self.mainWindow.viewport.exportOverlay

        if not overlay.active:

            return

        border = 2 * BorderSize(self.borderField.currentText(), self.overrides.get("borderSize", 28))

        value = max(border + 1, value)

        # Keep full precision internally so a pixel dimension remains exact,

        # even though the scale control displays only two decimal places.

        scale = (value - border) * 1000 / overlay.bounds[axis + 2]

        self.SetScaleOption("scale", min(1000000, max(.001, scale)))



    def CaptureProjectChanges(self):

        # Normal controls and shortcuts may change the viewport during an export preview.

        # Remember their changes as project settings, then reapply the export overrides.

        if self.applying or self.projectView is None:

            return

        current = self.CaptureView()

        changed = False

        for name, value in current.items():

            previous = self.effectiveView[name]

            if isinstance(value, dict):

                for key, entry in value.items():

                    if entry != previous[key]:

                        self.projectView[name][key] = entry

                        changed = True

            elif value != previous:

                self.projectView[name] = value

                changed = True

        if changed:

            self.ApplyView(self.ResolvedView())

        self.RefreshControls()



    def EditProjectSettings(self, callback):

        self.ApplyView(self.projectView)

        self.applying = True

        try:

            callback()

            self.projectView = self.CaptureView()

        finally:

            self.applying = False

            self.ApplyView(self.ResolvedView())

            self.RefreshControls()

        self.mainWindow.ProjectSettingsChanged()



    def SetOverride(self, name, value, key = None):

        if self.applying:

            return

        if name == "texture" and value != self.overrides.get("texture"):
            # A newly selected map starts with its own filename defaults.
            # Clear all adjustments together so preview and controls refresh once.
            for setting in self.textureSliders:
                self.overrides.pop("texture" + setting, None)

        if key is None:

            self.overrides[name] = value

        else:

            self.overrides.setdefault(name, {})[key] = round(value, 3) if type(value) is not bool else value

        if self.projectView is not None:

            self.ApplyView(self.ResolvedView())

        self.RefreshControls()

        self.mainWindow.ProjectSettingsChanged()



    def ChooseColor(self, name):

        view = self.ResolvedView()

        role = {"canvas": "canvas", "lines": "objectOutline", "border": "rulerBackground", "grid": "grid"}[name]

        option = name + "Color"

        themeColor = QtGui.QColor(palette.themeDefinitions[view["canvasTheme"]]["colors"][role])

        initial = self.overrides.get(option, themeColor.name())

        try:

            color = ColorPickerDialog.GetColor(QtGui.QColor(initial), self,

                                               preview = lambda color: self.PreviewColor(name, color),

                                               anchor = getattr(self, name + "ColorButton"))

        finally:
            self.colorPreviewTimer.stop()
            if self.projectView is not None:

                self.ApplyView(self.ResolvedView())

        if color.isValid():

            matchesTheme = color.rgb() == themeColor.rgb()
            if name == "lines":
                wallColor = QtGui.QColor(palette.themeDefinitions[view["canvasTheme"]]["colors"]["wallOutline"])
                matchesTheme = matchesTheme and color.rgb() == wallColor.rgb()
            if matchesTheme:

                if option in self.overrides:

                    self.ResetOverride(name + "Color")

            else:

                self.SetOverride(option, color.name())



    def PreviewColor(self, name, color):

        if self.projectView is not None:

            role = {"canvas": "canvas", "lines": "objectOutline", "border": "rulerBackground", "grid": "grid"}[name]

            if (palette.themeColors[role] != color.name()
                    or name == "lines" and palette.themeColors["wallOutline"] != color.name()):

                palette.themeColors[role] = color.name()
                if name == "lines":
                    palette.themeColors["wallOutline"] = color.name()

                if name in ("canvas", "lines"):
                    previousRevision = self.mainWindow.viewport.renderChanges.appearance
                    self.mainWindow.RefreshFurnishingRenderers()
                    self.mainWindow.viewport.exportOverlay.colorAppearanceRevisions += self.mainWindow.viewport.renderChanges.appearance - previousRevision

            # Palette state stays current for accept/cancel and explicit renders;
            # rapid picker events request at most one queued scene repaint.
            if not self.colorPreviewTimer.isActive():
                self.colorPreviewTimer.start()



    def SetBorder(self, border):

        if self.applying:

            return

        self.overrides.pop("ruler", None)

        self.SetOverride("border", border)



    def ResetOverride(self, name):

        self.overrides.pop(name, None)

        if self.projectView is not None:

            self.ApplyView(self.ResolvedView())

        self.RefreshControls()

        self.mainWindow.ProjectSettingsChanged()



    def SetBounds(self, bounds):

        if tuple(bounds) == self.mainWindow.viewport.exportOverlay.autoBounds:

            self.overrides.pop("bounds", None)

        else:

            self.overrides["bounds"] = list(bounds)

        self.mainWindow.ProjectSettingsChanged()



    def SetMeasurementVisibility(self, item, column):

        if self.applying:

            return

        key = item.data(0, QtCore.Qt.ItemDataRole.UserRole)

        checked = item.checkState(0) != QtCore.Qt.CheckState.Unchecked

        keys = self.mainWindow.viewport.measurementVisibility if key == "all" else (key,)

        for name in keys:

            self.overrides.setdefault("measurementVisibility", {})[name] = checked

        if self.projectView is not None:

            self.ApplyView(self.ResolvedView())

        self.RefreshControls()

        self.mainWindow.ProjectSettingsChanged()



    def SetVisibility(self, item, column):

        if self.applying:

            return

        enabled = item.checkState(0) != QtCore.Qt.CheckState.Unchecked

        descendants = [item]

        while descendants:

            node = descendants.pop()

            name = next(name for name, candidate in self.visibilityItems.items() if candidate is node)

            self.overrides.setdefault("visibility", {})[name] = enabled

            descendants.extend(node.child(index) for index in range(node.childCount()))

        if self.projectView is not None:

            self.ApplyView(self.ResolvedView())

        self.RefreshControls()

        self.mainWindow.ProjectSettingsChanged()



    def RefreshControls(self):

        if self.applying:

            return

        view = self.ResolvedView()

        widgets = [self.solidObjectsField, self.wallStyleField, self.textureField, *self.textureSliders.values(), *self.textureFields.values(), self.vignetteStrengthField, self.enableVignetteField, self.vignetteStrengthSlider, self.canvasThemeField, self.showGridField, self.borderField, self.borderSizeSlider, self.borderSizeField,

                   self.scaleField, self.scaleUnitsField,

                   self.scaleModeTabs, self.architecturalScaleField, self.dpiField, *self.resolutionFields,

                   self.unitsField, self.measurementVisibilityTree, self.visibilityTree]

        widgets += list(self.gridSliders.values()) + list(self.gridValueFields.values())

        widgets += list(self.lineworkSliders.values()) + list(self.lineworkFields.values())

        blockers = [QtCore.QSignalBlocker(widget) for widget in widgets]

        self.solidObjectsField.setChecked(view.get("solidObjects", True))

        self.wallStyleField.setCurrentText(view.get("wallStyle", "Material"))

        self.canvasThemeField.setCurrentText(view["canvasTheme"])

        for name, role in (("canvas", "canvas"), ("lines", "objectOutline"), ("border", "rulerBackground"), ("grid", "grid")):

            color = self.overrides.get(name + "Color")

            button = getattr(self, name + "ColorButton")

            button.setText(" " + (color if color is not None else "Theme"))

            swatch = QtGui.QPixmap(16, 16)

            swatch.fill(QtGui.QColor(color or palette.themeDefinitions[view["canvasTheme"]]["colors"][role]))

            button.setIcon(QtGui.QIcon(swatch))

            getattr(self, name + "ColorReset").setEnabled(color is not None)

        self.unitsField.setCurrentText(view["unitsMode"])

        png = self.typeField.currentData() != "SVG"
        self.compositeSection.setVisible(png)

        self.sectionContents["Composite"].setEnabled(png)

        self.sectionButtons["Composite"].setToolTip("Expand or collapse Composite" if png else "Compositing effects are available for raster export only")

        self.enableVignetteField.setChecked(self.overrides.get("vignetteEnabled", False))

        self.vignetteStrengthSlider.setValue(round(self.overrides.get("vignetteStrength", .25) * 1000))
        self.vignetteStrengthField.setValue(self.overrides.get("vignetteStrength", .25))
        self.vignetteStrengthReset.setEnabled("vignetteStrength" in self.overrides)

        self.vignetteStrengthOptions.setEnabled(self.enableVignetteField.isChecked())

        texture = self.overrides.get("texture")

        index = self.textureField.findData(texture)
        if index < 0 and texture is not None:
            compactName = CompactTextureName(texture)
            index = self.textureField.findData(compactName)
            if index >= 0:
                texture = self.overrides["texture"] = compactName

        if index < 0:

            try:
                label = TextureMapping(texture)[0]
            except ValueError:
                label = Path(texture).stem
            self.textureField.addItem(label + " (missing)", texture)

            index = self.textureField.count() - 1

        self.textureField.setCurrentIndex(index)
        self.textureField.setToolTip(texture or "No texture")

        mode, filenameScale = "tile", 1
        defaults = {"strength": .5, "highlights": 1, "midtones": 1, "shadows": 1}
        if texture is not None:
            try:
                label, mode, filenameScale, defaults = TextureMapping(texture, includeDefaults = True)
            except ValueError:
                pass
        defaults.update({"scale": filenameScale, "angle": 0})
        for name, slider in self.textureSliders.items():
            default = defaults[name.lower()]
            value = self.overrides.get("texture" + name, default)
            slider.setValue(round(value if name == "Angle" else value * 1000))
            self.textureFields[name].setValue(round(value) if name == "Angle" else value)
            self.textureResetButtons[name].setEnabled("texture" + name in self.overrides)
            self.textureResetButtons[name].setToolTip(f"Reset {name.lower()} to {default:g}" + (" (texture default)" if name != "Angle" else ""))
            self.textureControls[name].setEnabled(texture is not None and (name != "Scale" or mode == "tile"))
            slider.setToolTip(f"{name}: {value:g}" + (" normal-map pixels per canvas pixel" if name == "Scale" else " degrees" if name == "Angle" else ""))
        self.textureScaleReset.setEnabled("textureScale" in self.overrides)
        self.textureScaleReset.setToolTip(f"Use filename scale ({filenameScale:g} normal-map pixels per canvas pixel)")

        architectural = self.overrides.get("scaleMode", "Digital") == "Architectural"

        self.scaleModeTabs.setCurrentIndex(1 if architectural else 0)

        self.digitalScaleRow.setVisible(not architectural)

        self.resolutionRow.setVisible(png and not architectural)

        self.architecturalRow.setVisible(architectural)

        self.dpiRow.setVisible(png and architectural)

        self.architecturalResolutionRow.setVisible(png and architectural)

        self.architecturalScaleField.setCurrentText(f'1:{self.overrides.get("architecturalScale", 100):g}')

        self.dpiField.setCurrentText(str(self.overrides.get("dpi", 300)))

        units = self.overrides.get("scaleUnits", "px/m") if png else "units/m"

        choices = ["px/m", "px/cm"] if png else ["units/m"]

        if [self.scaleUnitsField.itemText(index) for index in range(self.scaleUnitsField.count())] != choices:

            self.scaleUnitsField.clear()

            self.scaleUnitsField.addItems(choices)

        self.scaleUnitsField.setCurrentText(units)

        descriptions = {"px/m": "Pixels per meter", "px/cm": "Pixels per centimeter", "units/m": "SVG units per meter"}

        for index in range(self.scaleUnitsField.count()):

            self.scaleUnitsField.setItemData(index, descriptions[self.scaleUnitsField.itemText(index)], QtCore.Qt.ItemDataRole.ToolTipRole)

        self.scaleUnitsField.setToolTip(descriptions[units])

        factor = 100 if units == "px/cm" else 1

        self.scaleField.setDecimals(2)

        self.scaleField.setRange(.01, 1000000 / factor)

        self.scaleField.setToolTip("Pixels per centimeter" if units == "px/cm" else "Pixels per meter" if png else "SVG units per meter")

        self.scaleField.setValue(self.overrides.get("scale", 100) / factor)

        overlay = self.mainWindow.viewport.exportOverlay

        bounds = overlay.bounds if overlay.active else self.overrides.get("bounds")

        if bounds is None:

            try:

                bounds = AutomaticBounds(self.mainWindow.viewport)

            except ValueError:

                bounds = (-1000, -1000, 2000, 2000)

        pixelsPerMillimeter = self.ScalePerMeter() / 1000

        width = max(1, math.ceil(round(bounds[2] * pixelsPerMillimeter, 8)))

        height = max(1, math.ceil(round(bounds[3] * pixelsPerMillimeter, 8)))

        self.borderField.setCurrentText(self.overrides.get("border", "Ruler + Reference Zones" if "ruler" not in self.overrides else "Ruler" if self.overrides["ruler"] else "None"))

        style = self.borderField.currentText()

        size = BorderSize(style, self.overrides.get("borderSize", 28))

        minimum = BorderSize(style, 1)

        self.borderSizeOptions.setEnabled(style != "None")

        self.borderColorLabel.setEnabled(style != "None")

        self.borderColorButton.setEnabled(style != "None")

        self.borderColorReset.setEnabled(style != "None" and "borderColor" in self.overrides)

        for control in (self.borderSizeSlider, self.borderSizeField):

            control.setMinimum(max(1, minimum))

            control.setValue(size if size else self.overrides.get("borderSize", 28))

            control.setToolTip(f"Border width at export scale; minimum {minimum} {'pixels' if png else 'SVG units'}")

        self.borderSizeField.setSuffix(" px" if png else " u")

        width += 2 * size

        height += 2 * size

        for field, value in zip(self.resolutionFields, (width, height)):

            field.setValue(value)

            field.setToolTip(f"{value} pixels, including the border")

        self.resolutionLabel.setText(f"Resolution: {width} × {height} pixels")

        self.showGridField.setChecked(view["showGrid"])

        self.gridOptions.setEnabled(view["showGrid"])

        self.gridColorOptions.setEnabled(view["showGrid"])

        for name, sliders, fields, buttons, defaults in (

                ("viewportSettings", self.gridSliders, self.gridValueFields, self.gridResetButtons, gridIntensityDefaults),

                ("lineworkSettings", self.lineworkSliders, self.lineworkFields, self.lineworkResetButtons, lineworkDefaults)):

            for key, value in view[name].items():

                sliders[key].setValue(round(value * 1000))

                fields[key].setValue(value)

                buttons[key].setEnabled(value != defaults[key])

        for key, item in self.measurementVisibilityItems.items():

            if key == "all":

                continue

            enabled = view["showMeasurements"] and view["measurementVisibility"][key]

            item.setCheckState(0, QtCore.Qt.CheckState.Checked if enabled else QtCore.Qt.CheckState.Unchecked)

            item.setForeground(0, QtGui.QBrush(QtGui.QColor(palette.themeColors["text" if enabled else "treeDisabledText"])))

        for key, item in self.visibilityItems.items():

            item.setText(0, self.mainWindow.visibilityItems[key].text(0))

            item.setCheckState(0, QtCore.Qt.CheckState.Checked if view["visibility"][key] else QtCore.Qt.CheckState.Unchecked)

            role = "treeEmptyText" if "(0 objects)" in item.text(0) else "text"

            item.setForeground(0, QtGui.QBrush(QtGui.QColor(palette.themeColors[role if view["visibility"][key] else "treeDisabledText"])))

        for item, includeSelf in ((self.measurementVisibilityItems["all"], False),

                                  (self.visibilityItems["Walls"], True), (self.visibilityItems["World"], False)):

            states = [item.child(index).checkState(0) for index in range(item.childCount())]

            if includeSelf:

                states.append(item.checkState(0))

            state = (QtCore.Qt.CheckState.Checked if all(value == QtCore.Qt.CheckState.Checked for value in states)

                     else QtCore.Qt.CheckState.Unchecked if all(value == QtCore.Qt.CheckState.Unchecked for value in states)

                     else QtCore.Qt.CheckState.PartiallyChecked)

            item.setCheckState(0, state)

            if item is self.measurementVisibilityItems["all"]:

                role = "treeDisabledText" if state == QtCore.Qt.CheckState.Unchecked else "text"

                item.setForeground(0, QtGui.QBrush(QtGui.QColor(palette.themeColors[role])))

        del blockers



    def SetSectionExpanded(self, name, expanded):

        self.sectionContents[name].setVisible(expanded)

        heading = self.sectionButtons[name]

        heading.setIcon(UiIcon("arrow_drop_down" if expanded else "arrow_drop_up"))

        heading.setToolTip(f"{'Collapse' if expanded else 'Expand'} {name}")

        if hasattr(self.mainWindow, "sessionTimer") and not self.mainWindow.projectLoading:

            self.mainWindow.sessionTimer.start(500)



    def RestoreSectionStates(self, states):

        for name, button in self.sectionButtons.items():

            expanded = states.get(name, states.get("Vignette", False) if name == "Composite" else False)

            blocker = QtCore.QSignalBlocker(button)

            button.setChecked(expanded)

            self.SetSectionExpanded(name, expanded)

            del blocker



    def PopulatePath(self, force = False):

        project = self.mainWindow.projectPath

        current = self.pathField.text().strip()

        if not force and project == self.pathProject and current and current != self.automaticPath:

            return

        folder = self.mainWindow.BrowseDirectory(forExport = True)

        name = project.stem if project is not None else "plan"

        extension = "svg" if self.typeField.currentData() == "SVG" else "png"

        path = folder / f"{name}.{extension}"

        number = 1

        while path.exists():

            path = folder / f"{name}_{number}.{extension}"

            number += 1

        self.pathProject = project

        self.automaticPath = str(path)

        self.pathField.setText(self.automaticPath)



    def SetPathType(self, kind):
        ownGesture = self.exportGestureBefore is None
        if ownGesture:
            self.exportGestureBefore = self.exportHistoryState

        self.RefreshControls()

        if self.projectView is not None:

            self.mainWindow.viewport.exportOverlay.scale = self.ScalePerMeter()

        self.mainWindow.viewport.exportOverlay.outputFormat = "svg" if kind == "SVG" else "png"

        self.mainWindow.viewport.exportOverlay.previewError = ""

        self.mainWindow.viewport.exportOverlay.svgKey = None

        self.mainWindow.viewport.exportOverlay.navigationTimer.stop()

        self.mainWindow.viewport.update()

        current = self.pathField.text().strip()

        if not current or current == self.automaticPath:

            self.PopulatePath()

        else:

            self.pathField.setText(str(Path(current).with_suffix(".svg" if kind == "SVG" else ".png")))

        self.RecordExportHistory()
        if ownGesture:
            self.EndExportGesture()



    def TextureSettings(self):
        defaults = {"strength": .5, "highlights": 1, "midtones": 1, "shadows": 1}
        texture = self.overrides.get("texture")
        if texture is not None:
            try:
                label, mode, scale, defaults = TextureMapping(texture, includeDefaults = True)
            except ValueError:
                pass
        settings = {name.lower(): self.overrides.get("texture" + name, defaults[name.lower()])
                    for name in ("Strength", "Highlights", "Midtones", "Shadows")}
        settings["scaleOverride"] = self.overrides.get("textureScale")
        return settings

    def Render(self, outputFormat, preview = False, previewScene = False):

        from planner_app.export_plan import RenderPlan



        main = self.mainWindow

        # Use the unsaved scene and the effective export view, without changing

        # the application's theme. Preview and file output share this path.

        data = main.BuildProjectData(includeHistory = False)

        data["settings"].update(self.CaptureView())
        data["settings"]["autoSizingUnitsMode"] = main.viewport.autoSizingUnitsMode or main.viewport.unitsMode

        return RenderPlan(main.projectPath or Path("plan.plan"), self.ScalePerMeter(),

                          main.viewport.exportOverlay.bounds, ruler = self.borderField.currentText() == "Ruler",

                          outputFormat = outputFormat, projectData = data, applyTheme = False, preview = preview, previewScene = previewScene,
                          furnishingDefinitions = main.viewport.furnishingDefinitions,
                          clipCache = main.viewport.exportOverlay.svgClipCache if previewScene else None,

                          border = self.borderField.currentText(), wallStyle = self.wallStyleField.currentText(),
                          solidObjects = self.solidObjectsField.isChecked(),
                          gridOrigin = main.viewport.gridOrigin,

                          borderSize = self.overrides.get("borderSize", 28),

                          texture = self.overrides.get("texture"), textureAngle = self.overrides.get("textureAngle", 0), textureSettings = self.TextureSettings(),

                          vignetteStrength = self.overrides.get("vignetteStrength", .25) if self.overrides.get("vignetteEnabled", False) else 0,

                          dpi = self.overrides.get("dpi", 300) if self.overrides.get("scaleMode") == "Architectural" and outputFormat == "png" else None,

                          architecturalScale = self.overrides.get("architecturalScale", 100) if self.overrides.get("scaleMode") == "Architectural" else None)



    def Export(self):



        main = self.mainWindow

        if self.projectView is None:

            return

        self.PopulatePath()

        optimized = self.typeField.currentData() == "PNG_OPTIMIZED"
        outputFormat = "svg" if self.typeField.currentData() == "SVG" else "png"

        path = Path(self.pathField.text().strip()).with_suffix("." + outputFormat)

        self.pathField.setText(str(path))

        if path.exists():

            answer = main.ShowAppMessage(
                "Replace Export", "Replace the existing file?", "warning", informativeText = str(path),
                standardButtons = QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                defaultButton = QtWidgets.QMessageBox.StandardButton.No, wrapInformativeText = False)

            if answer != QtWidgets.QMessageBox.StandardButton.Yes:

                return



        main.exportButton.setEnabled(False)

        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)

        output = None

        try:

            result = self.Render(outputFormat)
            if optimized:
                from planner_app.optimized_png import EncodeOptimizedPng
                result = EncodeOptimizedPng(result)

            path.parent.mkdir(parents = True, exist_ok = True)

            output = QtCore.QSaveFile(str(path))

            if not output.open(QtCore.QIODevice.OpenModeFlag.WriteOnly):

                raise OSError(output.errorString())

            if outputFormat == "png" and not optimized:

                if not result.save(output, "PNG"):

                    raise OSError("Could not encode the PNG image.")

            elif output.write(result) != len(result):

                raise OSError(output.errorString())

            if not output.commit():

                raise OSError(output.errorString())

        except Exception as error:

            if output is not None:

                output.cancelWriting()

            QtWidgets.QApplication.restoreOverrideCursor()

            main.ShowAppMessage("Export Failed", str(error), "error")

        else:

            QtWidgets.QApplication.restoreOverrideCursor()

            main.exportButton.setText("Exported")

            main.exportButton.setToolTip(f"Saved {path}")

            QtCore.QTimer.singleShot(2000, lambda: main.exportButton.setText("Export"))

            self.PopulatePath()

        finally:

            main.exportButton.setEnabled(True)



    def BrowsePath(self):

        kind = self.typeField.currentData()

        current = self.pathField.text().strip()

        if not current:

            self.PopulatePath()

            current = self.pathField.text()

        filters = "PNG images (*.png);;SVG images (*.svg);;Optimized PNG images (*.png)"
        selectedType = "Optimized PNG" if kind == "PNG_OPTIMIZED" else kind
        extension = "svg" if kind == "SVG" else "png"

        path, selectedFilter = QtWidgets.QFileDialog.getSaveFileName(

            self, "Export File", str(self.mainWindow.BrowseDirectory(forExport = True) / Path(current).name), filters, f"{selectedType} images (*.{extension})")

        if path:

            self.mainWindow.RememberBrowseFolder(path, forExport = True)

            self.pathField.setText(path)
            self.RecordExportHistory()

            selectedType = "SVG" if selectedFilter.startswith("SVG") else "PNG_OPTIMIZED" if selectedFilter.startswith("Optimized") else "PNG"
            self.typeField.setCurrentIndex(self.typeField.findData(selectedType))

