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
from planner_app.export_settings import ResolveExportView, ExportScalePerMeter, ExportPixelSize, ExportBorderSize, measurementTextSizes, measurementDefaultTextSize, exportRenderFormats, exportFileExtensions, pdfFileTypes
from planner_app.view_settings import CaptureViewportView, ApplyViewportView
from planner_app.print_layout import ResizePrintSelection, PrintPageLayout, PrintPaperGeometry, PrintOverlapOffset
from planner_app.graphics.title_block import TitleBlockLayout

from planner_app.units import unitModes, measurementPrecisions, FormatLength, imperialModes
from planner_app.measurement_units import MetricUnit

from planner_app.paths import appDirectory, texturesDirectory

from .widgets import DownwardComboBox, DragSlider, VisibilityItemDelegate, SectionHeading, UnitSpinBox, ExpressionSpinBox, SectionComboDelegate

from .color_picker import ColorPickerDialog
from .export_history import ExportHistoryMixin
from .wall_dimensions import WallDimensionControlsMixin
from .title_block import TitleBlockControlsMixin
from .scale_bar import ScaleBarControlsMixin
from .print_export import PrintExportMixin





class ExportPanel(ExportHistoryMixin, WallDimensionControlsMixin, TitleBlockControlsMixin, ScaleBarControlsMixin, PrintExportMixin, QtWidgets.QWidget):

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
        self.exportFolder = None
        self.exportFileName = None

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

        destinationLayout = QtWidgets.QVBoxLayout()
        destinationLayout.setContentsMargins(14, 14, 14, 6)
        destinationLayout.setSpacing(8)
        folderRow = QtWidgets.QHBoxLayout()
        folderRow.setContentsMargins(0, 0, 0, 0)
        folderRow.setSpacing(6)
        self.folderField = QtWidgets.QLineEdit()
        self.folderField.setPlaceholderText("Output folder")
        self.folderField.setAccessibleName("Export folder")
        self.browseButton = QtWidgets.QToolButton()
        self.browseButton.setObjectName("exportBrowseButton")
        self.browseButton.setIcon(UiIcon("folder_open"))
        self.browseButton.setIconSize(QtCore.QSize(26, 26))
        self.browseButton.setFixedSize(44, 32)
        self.browseButton.setToolTip("Browse")
        self.browseButton.setAccessibleName("Browse export folder")
        self.browseButton.clicked.connect(self.BrowsePath)
        folderRow.addWidget(self.folderField, 1)
        folderRow.addWidget(self.browseButton)
        destinationLayout.addLayout(folderRow)
        self.fileNameField = QtWidgets.QLineEdit()
        self.fileNameField.setPlaceholderText("Filename")
        self.fileNameField.setAccessibleName("Export filename")
        fileForm = QtWidgets.QFormLayout()
        fileForm.setContentsMargins(0, 0, 0, 0)
        fileForm.setHorizontalSpacing(8)
        fileForm.setVerticalSpacing(8)
        fileForm.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        fileForm.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        fileNameLabel = QtWidgets.QLabel("Filename")
        fileNameLabel.setBuddy(self.fileNameField)
        fileForm.addRow(fileNameLabel, self.fileNameField)
        destinationLayout.addLayout(fileForm)
        panelLayout.addLayout(destinationLayout)

        typeLabel = QtWidgets.QLabel("Type")

        self.typeField = DownwardComboBox()

        self.typeField.setItemDelegate(SectionComboDelegate(self.typeField))
        self.typeHeadings = []
        for heading, formats in (("Raster", (("PNG (raster)", "PNG"), ("Optimized PNG (raster)", "PNG_OPTIMIZED"), ("PDF (raster)", "PDF_RASTER"))),
                                 ("Vector", (("SVG (vector)", "SVG"), ("PDF (vector)", "PDF_VECTOR")))):
            self.typeField.addItem(heading)
            item = self.typeField.model().item(self.typeField.count() - 1)
            item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
            font = self.typeField.font()
            font.setBold(True)
            item.setFont(font)
            self.typeHeadings.append(item)
            for label, value in formats:
                self.typeField.addItem(label, value)
        self.typeField.setCurrentIndex(self.typeField.findData("PNG"))

        self.typeField.setAccessibleName("Export type")

        typeLabel.setBuddy(self.typeField)

        fileForm.addRow(typeLabel, self.typeField)

        self.optimizedPngNote = QtWidgets.QLabel(
            "Note: Optimized PNG may take a while at high resolutions or with detailed plans, "
            "especially when compositing effects are enabled.")
        self.optimizedPngNote.setObjectName("exportFormatNote")
        self.optimizedPngNote.setWordWrap(True)
        self.optimizedPngNote.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Minimum)
        self.optimizedPngNote.hide()
        destinationLayout.addWidget(self.optimizedPngNote)

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
            pageLayout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        printPage = QtWidgets.QWidget()
        printLayout = QtWidgets.QVBoxLayout(printPage)
        printLayout.setContentsMargins(0, 0, 0, 0)
        printLayout.setSpacing(0)
        printLayout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self.scaleModeTabs.addTab(printPage, "Print")
        self.scaleModeTabs.addTab(architecturalPage, "Architectural")
        self.scaleModeTabs.addTab(digitalPage, "Digital")

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
        self.CreatePrintControls(printLayout, architecturalPageLayout)

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

        for name in ("Canvas", "Border", "Grid", "Line Weight", "Measurements", "Scale Bar", "Title Block", "Composite", "Visibility"):

            section = QtWidgets.QWidget()

            sectionLayout = QtWidgets.QVBoxLayout(section)

            sectionLayout.setContentsMargins(0, 0, 0, 0)

            sectionLayout.setSpacing(12)

            displayName = "Dimensions" if name == "Measurements" else name
            heading = QtWidgets.QPushButton(displayName)

            heading.setObjectName("exportSectionHeading")

            heading.setCheckable(True)

            heading.setChecked(False)

            heading.setIcon(UiIcon("arrow_drop_up"))

            heading.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

            heading.setAccessibleName(f"{displayName} section")

            heading.setToolTip(f"Expand {displayName}")

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

        self.CreateScaleBarControls(sections["Scale Bar"])
        self.CreateTitleBlockControls(sections["Title Block"])



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

                                             key = str.casefold))

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

        self.borderSizeLabel = QtWidgets.QLabel("Border")
        borderSizeLayout.addWidget(self.borderSizeLabel)

        borderSizeRow = QtWidgets.QHBoxLayout()

        self.borderSizeSlider = DragSlider(QtCore.Qt.Orientation.Horizontal)

        self.borderSizeSlider.setRange(1, 128)

        self.borderSizeSlider.setValue(28)

        self.borderSizeSlider.setAccessibleName("Export border size")

        self.borderSizeField = UnitSpinBox()
        self.borderSizeField.displayDecimals = 0
        self.borderSizeUnitFactor = 1.0

        self.borderSizeField.setObjectName("settingsValue")

        self.borderSizeField.setRange(1, 128)

        self.borderSizeField.setValue(28)

        self.borderSizeField.setSuffix(" px")

        self.borderSizeField.setFixedWidth(120)

        self.borderSizeField.setAccessibleName("Export border in pixels")

        borderSizeRow.addWidget(self.borderSizeSlider, 1)

        borderSizeRow.addWidget(self.borderSizeField)

        borderSizeLayout.addLayout(borderSizeRow)

        borderForm.addWidget(self.borderSizeOptions, 2, 0, 1, 2)
        self.borderTextLabel = QtWidgets.QLabel("Text")
        self.borderTextSizeField = DownwardComboBox()
        self.borderTextSizeField.setAccessibleName("Export border text size")
        for label, size in measurementTextSizes.items():
            self.borderTextSizeField.addItem(label, size)
        self.borderTextSizeField.setCurrentText("Medium")
        self.borderTextLabel.setBuddy(self.borderTextSizeField)
        borderForm.addWidget(self.borderTextLabel, 3, 0)
        borderForm.addWidget(self.borderTextSizeField, 3, 1)



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



        wallsLabel = QtWidgets.QLabel("Wall Style")
        wallsLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.wallStyleField = DownwardComboBox()
        self.wallStyleField.addItems(("Material", "Solid", "Outline"))
        self.wallStyleField.setAccessibleName("Export wall fill")
        wallsLabel.setBuddy(self.wallStyleField)
        canvasForm.addWidget(wallsLabel, 2, 0)
        canvasForm.addWidget(self.wallStyleField, 2, 1)
        canvasChecks = QtWidgets.QGridLayout()
        canvasChecks.setVerticalSpacing(12)
        canvasForm.addLayout(canvasChecks, 5, 0, 1, 2)
        self.roomStyleField = DownwardComboBox()
        self.roomStyleField.setAccessibleName("Room Style")
        self.roomStyleField.addItems(("Canvas", "Tinted"))
        self.roomStyleField.setCurrentText("Tinted" if mainWindow.viewport.floors else "Canvas")
        self.roomStyleField.setToolTip("Use the canvas color or the theme's tinted room color")
        roomStyleLabel = QtWidgets.QLabel("Room Style")
        roomStyleLabel.setBuddy(self.roomStyleField)
        canvasForm.addWidget(roomStyleLabel, 4, 0)
        canvasForm.addWidget(self.roomStyleField, 4, 1)
        self.solidRoomsField = QtWidgets.QCheckBox()
        self.solidRoomsField.setAccessibleName("Solid Rooms")
        self.solidRoomsField.setChecked(mainWindow.viewport.solidRooms)
        self.solidRoomsField.setToolTip("Hide the grid inside detected rooms")
        canvasChecks.addWidget(QtWidgets.QLabel("Solid Rooms"), 0, 0)
        canvasChecks.addWidget(self.solidRoomsField, 0, 1, QtCore.Qt.AlignmentFlag.AlignLeft)
        self.solidObjectsField = QtWidgets.QCheckBox()
        self.solidObjectsField.setAccessibleName("Solid Objects")
        self.solidObjectsField.setChecked(True)
        self.solidObjectsField.setToolTip("Fill objects to hide the canvas and grid behind them")
        canvasChecks.addWidget(QtWidgets.QLabel("Solid Objects"), 1, 0)
        canvasChecks.addWidget(self.solidObjectsField, 1, 1, QtCore.Qt.AlignmentFlag.AlignLeft)
        self.drawOpeningOutlinesField = QtWidgets.QCheckBox()
        self.drawOpeningOutlinesField.setAccessibleName("Openings")
        self.drawOpeningOutlinesField.setChecked(True)
        self.drawOpeningOutlinesField.setToolTip("Draw thin lines across door openings")
        canvasChecks.addWidget(QtWidgets.QLabel("Openings"), 2, 0)
        canvasChecks.addWidget(self.drawOpeningOutlinesField, 2, 1, QtCore.Qt.AlignmentFlag.AlignLeft)

        viewport = mainWindow.viewport

        self.showGridField = QtWidgets.QCheckBox()
        self.showGridField.setAccessibleName("Draw Grid")

        self.showGridField.setChecked(viewport.showGrid)

        gridVisibilityForm = QtWidgets.QGridLayout()
        gridVisibilityForm.addWidget(QtWidgets.QLabel("Draw Grid"), 0, 0)
        gridVisibilityForm.addWidget(self.showGridField, 0, 1, QtCore.Qt.AlignmentFlag.AlignLeft)
        sections["Grid"].addLayout(gridVisibilityForm)

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



        unitsForm = QtWidgets.QFormLayout()
        unitsForm.setHorizontalSpacing(16)
        unitsForm.setVerticalSpacing(12)
        self.unitsField = DownwardComboBox()
        self.unitsField.addItems(unitModes)
        self.unitsField.setAccessibleName("Export dimension units")
        self.unitsField.currentTextChanged.connect(lambda mode: self.SetOverride("unitsMode", mode))
        unitsForm.addRow("Units", self.unitsField)
        self.precisionField = DownwardComboBox()
        self.precisionField.addItems(list(measurementPrecisions))
        self.precisionField.setAccessibleName("Export dimension precision")
        self.precisionField.currentTextChanged.connect(lambda precision: self.SetOverride("measurementPrecision", precision))
        unitsForm.addRow("Precision", self.precisionField)
        self.measurementSizeField = DownwardComboBox()
        for label, size in measurementTextSizes.items():
            self.measurementSizeField.addItem(label, size)
        self.measurementSizeField.setAccessibleName("Export dimension text size")
        self.measurementSizeField.currentIndexChanged.connect(
            lambda index: self.SetOverride("measurementTextSize", self.measurementSizeField.itemData(index)))
        unitsForm.addRow("Size", self.measurementSizeField)
        sections["Measurements"].addLayout(unitsForm)
        sections["Measurements"].addWidget(SectionHeading("Measure", "Measurements"))

        self.measurementVisibilityTree = QtWidgets.QTreeWidget()
        self.measurementVisibilityItems = {}
        states = []
        for key, title in (("all", "Draw dimensions"), ("walls", "Walls"),
                           ("stairs", "Stairs"), ("counters", "Counters"),
                           ("railings", "Railings")):
            parent = self.measurementVisibilityTree if key == "all" else self.measurementVisibilityItems["all"]
            item = QtWidgets.QTreeWidgetItem(parent, [title])
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            enabled = viewport.showMeasurements and viewport.measurementVisibility.get(key, False)
            state = QtCore.Qt.CheckState.Checked if enabled else QtCore.Qt.CheckState.Unchecked
            item.setCheckState(0, state)
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, key)
            self.measurementVisibilityItems[key] = item
            if key != "all":
                states.append(state)
        state = (QtCore.Qt.CheckState.Checked if all(value == QtCore.Qt.CheckState.Checked for value in states)
                 else QtCore.Qt.CheckState.Unchecked if all(value == QtCore.Qt.CheckState.Unchecked for value in states)
                 else QtCore.Qt.CheckState.PartiallyChecked)
        self.measurementVisibilityItems["all"].setCheckState(0, state)

        vignetteHeading = SectionHeading("Vignette", "Vignette")
        vignetteHeader = QtWidgets.QVBoxLayout()
        vignetteHeader.setSpacing(6)
        vignetteHeader.addWidget(vignetteHeading)
        self.enableVignetteField = QtWidgets.QCheckBox()
        self.enableVignetteField.setAccessibleName("Enable Vignette")
        vignetteForm = QtWidgets.QGridLayout()
        vignetteForm.addWidget(QtWidgets.QLabel("Enable Vignette"), 0, 0)
        vignetteForm.addWidget(self.enableVignetteField, 0, 1, QtCore.Qt.AlignmentFlag.AlignLeft)
        checkboxForms = (canvasChecks, gridVisibilityForm, self.scaleBarEnableForm, self.titleBlockEnableForm, vignetteForm)
        checkboxLabelWidth = max(form.itemAtPosition(0, 0).widget().sizeHint().width() for form in checkboxForms)
        for form in checkboxForms:
            form.setContentsMargins(0, 0, 0, 0)
            form.setHorizontalSpacing(24)
            form.setColumnMinimumWidth(0, checkboxLabelWidth)
            form.setColumnStretch(1, 1)
        vignetteHeader.addLayout(vignetteForm)
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
        self.vignetteStrengthSlider.setValue(125)
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
        textureHeading = SectionHeading("Texture", "Texture")
        textureHeader = QtWidgets.QVBoxLayout()
        textureHeader.setSpacing(6)
        textureHeader.addWidget(textureHeading)
        self.textureField = DownwardComboBox()
        self.textureField.setAccessibleName("Export normal-map texture")
        self.textureField.addItem("None", None)
        formats = {"." + bytes(value).decode().lower() for value in QtGui.QImageReader.supportedImageFormats()}
        for path in sorted(texturesDirectory.glob("*"), key = lambda path: path.name.casefold()):
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
                                        (self.visibilityTree, "Visibility", len(mainWindow.visibilityItems) + len(mainWindow.visibilityGroups))):

            tree.setObjectName("visibilityTree")

            tree.setAccessibleName("Export Dimensions" if section == "Measurements" else f"Export {section}")

            tree.setHeaderHidden(True)

            tree.setIndentation(24)

            tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)

            tree.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

            tree.setItemDelegate(VisibilityItemDelegate(tree, rowHeight = rowHeight))

            tree.expandAll()

            tree.ensurePolished()

            tree.setFixedHeight(rowHeight * rowCount)

            sections[section].addWidget(tree)

        tree = self.measurementVisibilityTree
        for signal in (tree.itemExpanded, tree.itemCollapsed):
            signal.connect(lambda item: self.measurementVisibilityTree.setFixedHeight(rowHeight * (
                len(self.measurementVisibilityItems) if self.measurementVisibilityItems["all"].isExpanded() else 1)))
        self.BuildWallDimensionControls(sections["Measurements"], viewport.wallMeasurementMode, viewport.measurementSettings,
            lambda mode: self.SetOverride("wallMeasurementMode", mode),
            lambda reference: self.SetOverride("wallMeasurementReference", reference),
            lambda key, value: self.SetOverride("measurementSettings", value, key))
        self.wallMeasurementModeField.setAccessibleName("Export wall dimension mode")
        self.wallReferenceField.setAccessibleName("Export wall reference")

        # Keep label-only rows, checkboxes and multi-control rows on the same

        # rhythm. Embedded spinbox editors retain their normal internal layout.

        for widget in self.findChildren(QtWidgets.QWidget):

            if widget in (self.optimizedPngNote, self.printNote):
                continue  # Wrapped notes need their natural height, rather than a single control row.

            if any(heading is widget or heading.isAncestorOf(widget) for heading in (exportHeading, vignetteHeading, textureHeading, self.wallDimensionWidget)):

                continue

            if widget.objectName() == "exportControlLabel":
                widget.ensurePolished()
                widget.setFixedHeight(widget.sizeHint().height())
                continue
            if isinstance(widget, (QtWidgets.QLabel, QtWidgets.QCheckBox, QtWidgets.QRadioButton, QtWidgets.QPushButton,

                                   QtWidgets.QToolButton, QtWidgets.QSlider, QtWidgets.QComboBox,

                                   QtWidgets.QAbstractSpinBox)) or widget in (self.folderField, self.fileNameField):

                widget.setFixedHeight(headingHeight if widget.objectName() == "exportSectionHeading" else rowHeight)



        self.visibilityItems = {}
        self.visibilityGroups = {}

        def MapVisibility(source, target):

            name = next((name for name, item in mainWindow.visibilityItems.items() if item is source), None)
            if name is not None:
                self.visibilityItems[name] = target
            else:
                name = next(name for name, item in mainWindow.visibilityGroups.items() if item is source)
                self.visibilityGroups[name] = target

            for index in range(source.childCount()):

                MapVisibility(source.child(index), target.child(index))

        for index, source in enumerate(visibilityRoots):
            MapVisibility(source, self.visibilityTree.topLevelItem(index))

        def ResizeVisibilityTree(item = None):
            count = 0
            pending = [self.visibilityTree.topLevelItem(index) for index in range(self.visibilityTree.topLevelItemCount())]
            while pending:
                node = pending.pop()
                count += 1
                if node.isExpanded():
                    pending.extend(node.child(index) for index in range(node.childCount()))
            self.visibilityTree.setFixedHeight(rowHeight * count)

        self.visibilityTree.itemExpanded.connect(ResizeVisibilityTree)
        self.visibilityTree.itemCollapsed.connect(ResizeVisibilityTree)
        ResizeVisibilityTree()

        self.solidObjectsField.toggled.connect(lambda checked: self.SetOverride("solidObjects", checked))
        self.roomStyleField.currentTextChanged.connect(lambda style: self.SetOverride("roomStyle", style))
        self.solidRoomsField.toggled.connect(lambda checked: self.SetOverride("solidRooms", checked))
        self.drawOpeningOutlinesField.toggled.connect(lambda checked: self.SetOverride("drawOpeningOutlines", checked))

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

        self.borderSizeSlider.valueChanged.connect(lambda size: self.SetBorderWidth(size, fromSlider = True))

        self.borderSizeField.valueChanged.connect(self.SetBorderWidth)
        self.borderTextSizeField.currentIndexChanged.connect(
            lambda index: self.SetOverride("borderTextSize", self.borderTextSizeField.itemData(index)))

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
        # Keep wheel scrolling for the panel, including while an input has focus.
        # Popup lists/calendars retain their own scrolling when opened explicitly.
        for controlType in (QtWidgets.QSlider, QtWidgets.QComboBox, QtWidgets.QAbstractSpinBox):
            for control in self.findChildren(controlType):
                if control.window() is not self.window():
                    continue
                control.installEventFilter(self)
                if isinstance(control, QtWidgets.QAbstractSpinBox) or isinstance(control, QtWidgets.QComboBox) and control.isEditable():
                    control.lineEdit().installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Type.Wheel:
            viewport = self.scrollArea.viewport()
            position = viewport.mapFromGlobal(event.globalPosition().toPoint())
            forwarded = QtGui.QWheelEvent(QtCore.QPointF(position), event.globalPosition(), event.pixelDelta(), event.angleDelta(),
                                         event.buttons(), event.modifiers(), event.phase(), event.inverted(), event.source(), event.pointingDevice())
            QtWidgets.QApplication.sendEvent(viewport, forwarded)
            event.accept()
            return True
        return super().eventFilter(watched, event)



    def CaptureView(self):
        return CaptureViewportView(self.mainWindow.viewport, palette.activeCanvasTheme)

    def ResolvedView(self):
        baseView = self.projectView if self.projectView is not None else self.CaptureView()
        view = ResolveExportView(baseView, self.overrides)
        # Saved projects can name a removed or renamed custom theme. Resolve it
        # before controls index its colours, including while restoring Build.
        if palette.themeDefinitions.get(view["canvasTheme"], {}).get("type") != "canvas":
            inheritedTheme = baseView["canvasTheme"]
            view["canvasTheme"] = (inheritedTheme if palette.themeDefinitions.get(inheritedTheme, {}).get("type") == "canvas"
                                   else palette.activeCanvasTheme)
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

            if view.get("canvasColor") is not None:

                palette.themeColors["canvas"] = view["canvasColor"]

            for name, role in (("borderColor", "rulerBackground"), ("gridColor", "grid")):

                if view.get(name) is not None:

                    palette.themeColors[role] = view[name]

            if view.get("linesColor") is not None:
                palette.themeColors["objectOutline"] = view["linesColor"]
                palette.themeColors["wallOutline"] = view["linesColor"]

            ApplyViewportView(v, view)
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



            main.UpdateFurnishingSearch()
            v.gridOrigin = tuple(view.get("gridOrigin", (0.0, 0.0)))


            v.exportOverlay.borderStyle = self.overrides.get("border", "Ruler + Reference Zones" if "ruler" not in self.overrides else "Ruler" if self.overrides["ruler"] else "None")

            v.exportOverlay.drawRuler = v.exportOverlay.borderStyle != "None"

            v.exportOverlay.texture = self.overrides.get("texture")

            v.exportOverlay.textureAngle = self.overrides.get("textureAngle", 0)
            v.exportOverlay.textureSettings = self.TextureSettings()

            v.exportOverlay.vignetteStrength = self.overrides.get("vignetteStrength", .125) if self.overrides.get("vignetteEnabled", False) else 0

            v.exportOverlay.borderSize = ExportBorderSize(self.overrides, v.exportOverlay.borderStyle)

            v.exportOverlay.titleBlock = self.TitleBlockOptions()
            v.exportOverlay.scaleBar = dict(self.overrides.get("scaleBar", {}))
            v.exportOverlay.architecturalScale = (self.overrides.get("architecturalScale", 100)
                                                  if self.overrides.get("scaleMode") in ("Architectural", "Print") else None)

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

            if not self.overrides:
                self.overrides["scaleMode"] = "Print"

            self.RefreshControls()

            self.PopulatePath()
            self.exportHistoryState = self.ExportHistoryState()

            self.projectView = self.CaptureView()

            self.projectZoom = self.mainWindow.viewport.zoom

            self.projectPanOffset = QtCore.QPointF(self.mainWindow.viewport.panOffset)

            self.ApplyView(self.ResolvedView())

            self.mainWindow.viewport.exportOverlay.scale = self.PreviewScalePerMeter()

            self.mainWindow.viewport.exportOverlay.outputFormat = exportRenderFormats[self.typeField.currentData()]

            self.mainWindow.viewport.exportOverlay.SetActive(True, self.overrides.get("bounds"))

            if self.InitializePrintSelection():
                self.exportHistoryState = self.ExportHistoryState()

            v = self.mainWindow.viewport

            v.zoom = (self.exportZoom if self.exportZoom is not None else

                      self.PreviewScalePerMeter() / (1000 * v.basePixelsPerMillimeter))

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
        self.mainWindow.RefreshExportActions()
        self.RefreshControls()



    def SetScale(self, value):

        value *= 100 if self.scaleUnitsField.currentText() == "px/cm" else 1

        self.overrides["scale"] = value

        if self.projectView is not None:

            v = self.mainWindow.viewport

            v.exportOverlay.scale = self.PreviewScalePerMeter()

            v.update()

        self.mainWindow.ProjectSettingsChanged()



    def ScalePerMeter(self):
        return ExportScalePerMeter(self.overrides, self.typeField.currentData())

    def SetScaleUnits(self, units):

        if units not in ("px/m", "px/cm"):

            return

        self.overrides["scaleUnits"] = units

        self.RefreshControls()

        self.mainWindow.ProjectSettingsChanged()



    def SetScaleOption(self, name, value):
        if name == "scaleMode" and value != "Print" and self.typeField.currentData() in pdfFileTypes:
            self.RefreshControls()
            return

        if self.overrides.get(name) == value:

            self.RefreshControls()

            return

        previousMode = self.overrides.get("scaleMode", "Digital")
        if name == "scaleMode" and previousMode in ("Architectural", "Print"):
            # Commit edits to the mode that owns the field before moving its
            # shared controls into the destination tab.
            scaleText, dpiText = self.architecturalScaleField.currentText(), self.dpiField.currentText()
            if scaleText != f'1:{self.overrides.get("architecturalScale", 100):g}':
                self.SetArchitecturalScale(scaleText)
            if dpiText != str(self.overrides.get("dpi", 300)):
                self.SetDpi(dpiText)
        overlay = self.mainWindow.viewport.exportOverlay
        previousScale = self.overrides.get("architecturalScale", 100)
        printing = self.overrides.get("scaleMode") == "Print"
        if name == "scaleMode":
            # Active bounds stay in the existing field for renderers and legacy
            # projects. Park only inactive modes in the per-mode crop archive.
            scales = copy.deepcopy(self.overrides.get("modeScales", {}))
            defaults = {"architecturalScale": 100, "dpi": 300}
            legacy = not scales and previousMode == "Digital"
            if previousMode in ("Architectural", "Print"):
                scales[previousMode] = {key: self.overrides.get(key, default) for key, default in defaults.items()}
            if value in ("Architectural", "Print"):
                settings = scales.pop(value, None)
                for key, default in defaults.items():
                    self.overrides[key] = (settings.get(key, default) if settings is not None else
                                           self.overrides.get(key, default) if legacy else default)
            if scales:
                self.overrides["modeScales"] = scales
            else:
                self.overrides.pop("modeScales", None)
            regions = dict(self.overrides.get("cropRegions", {}))
            bounds = overlay.bounds if overlay.active else self.overrides.get("bounds")
            if bounds is not None:
                regions[previousMode] = list(bounds)
            bounds = regions.pop(value, None)
            if regions:
                self.overrides["cropRegions"] = regions
            else:
                self.overrides.pop("cropRegions", None)
            if bounds is None:
                self.overrides.pop("bounds", None)
            else:
                self.overrides["bounds"] = list(bounds)
            if overlay.active:
                overlay.bounds = tuple(bounds) if bounds is not None else overlay.autoBounds
        elif printing and overlay.active and name == "pageOverlap":
            overlay.printPreviewTimer.start()
            if overlay.bounds is not None:
                self.overrides["pageOverlapOffset"] = PrintOverlapOffset(self.overrides, value, overlay.bounds)
        if printing and overlay.active and overlay.bounds is not None and name in ("pageSize", "pageOrientation", "architecturalScale"):
            updated = dict(self.overrides)
            updated[name] = value
            overlap = list(updated.get("pageOverlap", (0, 0)))
            updated["pageOverlap"] = [0, 0]
            try:
                kind = exportRenderFormats[self.typeField.currentData()]
                border = ExportBorderSize(updated, self.borderField.currentText())
                maximum = PrintPageLayout(updated, border, self.TitleBlockOptions(), kind)["tile"]
            except ValueError:
                maximum = PrintPaperGeometry(updated)[0]
            overlap = [min(amount, max(0, size - 1)) for amount, size in zip(overlap, maximum)]
            updates = {"pageOverlap": overlap} if "pageOverlap" in self.overrides or name == "pageOverlap" else {}
            if overlap != self.overrides.get("pageOverlap", [0, 0]):
                updates["pageOverlapOffset"] = PrintOverlapOffset(self.overrides, overlap, overlay.bounds)
            value = updates.get(name, value)
            bounds, origin = ResizePrintSelection(overlay.bounds, self.overrides, name, value, updates)
            overlay.bounds = bounds
            self.overrides["bounds"] = list(bounds)
            self.overrides["pageOrigin"] = list(origin)
            self.overrides.update(updates)
        elif self.overrides.get("scaleMode") == "Architectural" and overlay.active and overlay.bounds is not None and name == "architecturalScale":
            x, y, width, height = overlay.bounds
            ratio = value / previousScale
            bounds = (x + width * (1 - ratio) / 2, y + height * (1 - ratio) / 2, width * ratio, height * ratio)
            overlay.bounds = bounds
            self.overrides["bounds"] = list(bounds)
        self.overrides[name] = value
        if self.overrides.get("scaleMode") in ("Architectural", "Print") and overlay.active and name == "architecturalScale":
            self.UpdatePhysicalScaleView(previousScale)

        if self.projectView is not None:

            self.mainWindow.viewport.exportOverlay.scale = self.PreviewScalePerMeter()

            if name in ("scaleMode", "architecturalScale"):

                self.mainWindow.viewport.exportOverlay.svgKey = None
                self.mainWindow.viewport.exportOverlay.architecturalScale = (
                    self.overrides.get("architecturalScale", 100) if self.overrides.get("scaleMode") in ("Architectural", "Print") else None)

            if name == "scaleMode" and overlay.active:
                # Apply the destination's minimum before notifying history, so
                # switching modes remains one complete, reversible change.
                self.InitializePrintSelection()
                overlay.printMode = value == "Print"
                overlay.printSettings = dict(self.overrides)
                overlay.pageOrigin = tuple(self.overrides.get("pageOrigin", (0, 0)))
                overlay.bounds = overlay.ConstrainTitleBlockBounds(overlay.bounds)
                if "bounds" in self.overrides or overlay.bounds != overlay.autoBounds:
                    self.overrides["bounds"] = list(overlay.bounds)

            self.mainWindow.viewport.update()

        self.RefreshControls()

        self.mainWindow.ProjectSettingsChanged()



    def SetArchitecturalScale(self, text = None):

        text = (self.architecturalScaleField.currentText() if text is None else text).replace(" ", "")

        try:

            value = float(text[2:] if text.startswith("1:") else text)

            if not math.isfinite(value) or not 1 <= value <= 100000:

                raise ValueError

        except ValueError:

            self.RefreshControls()

            return

        self.SetScaleOption("architecturalScale", value)



    def SetDpi(self, text = None):

        try:

            value = int(self.dpiField.currentText() if text is None else text)

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

        border = 2 * ExportBorderSize(self.overrides, self.borderField.currentText())

        titleBlock = self.TitleBlockOptions()
        if titleBlock.get("enabled", False):
            vertical = titleBlock.get("position", "Right") == "Right"
            minimumWidth, minimumHeight, block = TitleBlockLayout(1, 1, titleBlock, self.ScalePerMeter(), dpi = self.TitleBlockDpi())
            if axis == (0 if vertical else 1):
                value -= block[2] if vertical else block[3]
            else:
                value = max(minimumHeight if vertical else minimumWidth, value)

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



    def SetBorderWidth(self, value, fromSlider = False):
        if self.applying:
            return
        if self.overrides.get("scaleMode") in ("Architectural", "Print"):
            mode = (self.projectView if self.projectView is not None else self.CaptureView())["unitsMode"]
            divisor, unit = MetricUnit(mode)
            width = value * 1000 / self.PreviewScalePerMeter() if fromSlider else value * divisor
            self.SetOverride("borderWidth", width)
        else:
            self.SetOverride("borderSize", max(1, min(128, round(value))))

    def SetOverride(self, name, value, key = None):

        if self.applying:

            return
        if self.overrides.get("scaleMode") == "Print" and self.mainWindow.viewport.exportOverlay.active and name in ("borderSize", "borderWidth", "borderTextSize", "border", "titleBlock", "scaleBar"):
            self.mainWindow.viewport.exportOverlay.printPreviewTimer.start()

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

        initial = self.overrides.get(option) or themeColor.name()

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

        if self.applying or not item.flags() & QtCore.Qt.ItemFlag.ItemIsUserCheckable:

            return

        enabled = item.checkState(0) != QtCore.Qt.CheckState.Unchecked

        descendants = [item]

        while descendants:

            node = descendants.pop()

            name = next((name for name, candidate in self.visibilityItems.items() if candidate is node), None)
            if name is not None:
                self.overrides.setdefault("visibility", {})[name] = enabled

            descendants.extend(node.child(index) for index in range(node.childCount()))

        if self.projectView is not None:

            self.ApplyView(self.ResolvedView())

        self.RefreshControls()

        self.mainWindow.ProjectSettingsChanged()



    def RefreshControls(self):

        if self.applying:

            return

        self.RefreshTitleBlockControls()
        self.RefreshScaleBarControls()

        view = self.ResolvedView()

        widgets = [self.typeField, self.solidObjectsField, self.roomStyleField, self.solidRoomsField, self.drawOpeningOutlinesField, self.wallStyleField, self.textureField, *self.textureSliders.values(), *self.textureFields.values(), self.vignetteStrengthField, self.enableVignetteField, self.vignetteStrengthSlider, self.canvasThemeField, self.showGridField, self.borderField, self.borderSizeSlider, self.borderSizeField, self.borderTextSizeField,

                   self.scaleField, self.scaleUnitsField,

                   self.scaleModeTabs, self.architecturalScaleField, self.dpiField, *self.resolutionFields,

                   self.unitsField, self.precisionField, self.measurementSizeField, self.measurementVisibilityTree, self.visibilityTree,
                   self.wallMeasurementModeField, self.wallReferenceField]

        widgets += list(self.gridSliders.values()) + list(self.gridValueFields.values())

        widgets += list(self.lineworkSliders.values()) + list(self.lineworkFields.values())
        # Blocking a combo does not block its editor's editingFinished signal.
        # Reparenting the shared physical controls must not commit to a new mode.
        widgets += [self.architecturalScaleField.lineEdit(), self.dpiField.lineEdit()]

        blockers = [QtCore.QSignalBlocker(widget) for widget in widgets]

        self.typeField.setCurrentIndex(self.typeField.findData(self.overrides.get("fileType", "PNG")))
        backgroundRole = "windowBackground" if QtGui.QColor(palette.themeColors["controlBackground"]).lightnessF() < .5 else "pressedBackground"
        for heading in self.typeHeadings:
            heading.setForeground(QtGui.QColor(palette.themeColors["mutedText"]))
            heading.setBackground(QtGui.QColor(palette.themeColors[backgroundRole]))

        self.solidObjectsField.setChecked(view.get("solidObjects", True))
        self.roomStyleField.setCurrentText(view.get("roomStyle", "Tinted"))
        self.solidRoomsField.setChecked(view.get("solidRooms", False))
        self.drawOpeningOutlinesField.setChecked(view["drawOpeningOutlines"])

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
        self.precisionField.setCurrentText(view["measurementPrecision"])
        self.measurementSizeField.setCurrentIndex(self.measurementSizeField.findData(view["measurementTextSize"]))
        for index, step in enumerate(measurementPrecisions.values()):
            label = ("1/16 inch", "1/4 inch", "1 inch")[index] if view["unitsMode"] in imperialModes else FormatLength(step, view["unitsMode"], "mm")
            self.precisionField.setItemData(index, f"Round export dimensions to the nearest {label}", QtCore.Qt.ItemDataRole.ToolTipRole)

        png = exportRenderFormats[self.typeField.currentData()] == "png"
        self.optimizedPngNote.setVisible(self.typeField.currentData() == "PNG_OPTIMIZED")
        self.compositeSection.setVisible(png)

        self.sectionContents["Composite"].setEnabled(png)

        self.sectionButtons["Composite"].setToolTip("Expand or collapse Composite" if png else "Compositing effects are available for raster export only")

        self.enableVignetteField.setChecked(self.overrides.get("vignetteEnabled", False))

        self.vignetteStrengthSlider.setValue(round(self.overrides.get("vignetteStrength", .125) * 1000))
        self.vignetteStrengthField.setValue(self.overrides.get("vignetteStrength", .125))
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
            if name == "Scale" and value is None:
                value = default
            slider.setValue(round(value if name == "Angle" else value * 1000))
            self.textureFields[name].setValue(round(value) if name == "Angle" else value)
            self.textureResetButtons[name].setEnabled("texture" + name in self.overrides)
            self.textureResetButtons[name].setToolTip(f"Reset {name.lower()} to {default:g}" + (" (texture default)" if name != "Angle" else ""))
            self.textureControls[name].setEnabled(texture is not None and (name != "Scale" or mode == "tile"))
            slider.setToolTip(f"{name}: {value:g}" + (" degrees" if name == "Angle" else ""))
        self.textureScaleReset.setEnabled("textureScale" in self.overrides)
        self.textureScaleReset.setToolTip(f"Reset texture scale to {filenameScale:g}")

        printing = self.overrides.get("scaleMode") == "Print"
        architectural = self.overrides.get("scaleMode", "Digital") in ("Architectural", "Print")

        self.scaleModeTabs.setCurrentIndex(0 if printing else 1 if architectural else 2)
        for index in (1, 2):
            self.scaleModeTabs.setTabVisible(index, self.typeField.currentData() not in pdfFileTypes)
        # Mode/scale changes can update controls without applying the view.
        # Resolve the border's project length before any preview page layout.
        self.mainWindow.viewport.exportOverlay.borderSize = ExportBorderSize(self.overrides)
        self.RefreshPrintControls()

        self.digitalScaleRow.setVisible(not architectural)

        self.resolutionRow.setVisible(png and not architectural)

        self.architecturalRow.setVisible(architectural)

        self.dpiRow.setVisible(architectural and png)

        self.architecturalResolutionRow.setVisible(png and architectural and not printing)

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

        self.borderField.setCurrentText(self.overrides.get("border", "Ruler + Reference Zones" if "ruler" not in self.overrides else "Ruler" if self.overrides["ruler"] else "None"))

        style = self.borderField.currentText()

        size = ExportBorderSize(self.overrides, style)

        minimum = BorderSize(style, 1, view["borderTextSize"])

        self.borderSizeOptions.setEnabled(style != "None")

        self.borderColorLabel.setEnabled(style != "None")

        self.borderColorButton.setEnabled(style != "None")

        self.borderColorReset.setEnabled(style != "None" and "borderColor" in self.overrides)

        requestedSize = self.overrides.get("borderSize", 28)
        if architectural:
            requestedSize = self.overrides.get("borderWidth", 200) * self.PreviewScalePerMeter() / 1000
        effectiveSize = max(1, minimum, requestedSize)
        maximum = min(2_147_483_647, max(128, math.ceil(effectiveSize))) if architectural else 128
        self.borderSizeSlider.setRange(max(1, minimum), maximum)
        self.borderSizeSlider.setValue(min(maximum, round(effectiveSize)))
        factor, unit = 1.0, "px"
        if architectural:
            mode = (self.projectView if self.projectView is not None else self.CaptureView())["unitsMode"]
            divisor, unit = MetricUnit(mode)
            factor = 1000 / (self.PreviewScalePerMeter() * divisor)
        self.borderSizeUnitFactor = factor
        self.borderSizeField.setDecimals(0 if not architectural else max(3, math.ceil(-math.log10(factor)) + 2))
        self.borderSizeField.setRange(max(1, minimum) * factor, maximum * factor)
        self.borderSizeField.setSingleStep(factor)
        self.borderSizeField.setSuffix(" " + unit)
        self.borderSizeField.setValue(effectiveSize * factor)
        self.borderSizeField.setFixedWidth(120)
        self.borderSizeField.setAccessibleName("Export border in project units" if architectural else "Export border in pixels")
        hasText = style in ("Ruler", "Reference Zones", "Ruler + Reference Zones")
        self.borderTextLabel.setVisible(hasText)
        self.borderTextSizeField.setVisible(hasText)
        self.borderTextSizeField.setCurrentIndex(self.borderTextSizeField.findData(view["borderTextSize"]))

        width, height = ExportPixelSize(bounds, self.PreviewScalePerMeter(), size)
        width, height, titleBlockRect = TitleBlockLayout(width, height, self.TitleBlockOptions(), self.PreviewScalePerMeter(),
                                                        self.overrides.get("architecturalScale", 100) if self.overrides.get("scaleMode") in ("Architectural", "Print") else None,
                                                        "png" if png else "svg", self.TitleBlockDpi())
        if png and architectural:
            density = self.overrides.get("dpi", 300) / 300
            width, height = max(1, round(width * density)), max(1, round(height * density))

        for field, value in zip(self.resolutionFields, (width, height)):

            field.setValue(value)

            field.setToolTip(f"{value} pixels, including the border and enabled title block")

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

        wallDimensionsEnabled = view["showMeasurements"] and view["measurementVisibility"]["walls"]
        self.RefreshWallDimensionControls(view["wallMeasurementMode"], view["wallMeasurementReference"],
                                          view["measurementSettings"], wallDimensionsEnabled)
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

        for groupName, group in self.visibilityGroups.items():
            group.setText(0, self.mainWindow.visibilityGroups[groupName].text(0))
            names = [name for name, node in self.visibilityItems.items() if node.parent() is group]
            states = [view["visibility"][name] for name in names]
            state = (QtCore.Qt.CheckState.Checked if all(states)
                     else QtCore.Qt.CheckState.Unchecked if not any(states)
                     else QtCore.Qt.CheckState.PartiallyChecked)
            group.setCheckState(0, state)
            visible = view["visibility"]["World"] and any(view["visibility"][name] for name in names)
            empty = all("(0 objects)" in self.visibilityItems[name].text(0) for name in names)
            role = "treeDisabledText" if not visible else "treeEmptyText" if empty else "text"
            group.setForeground(0, QtGui.QBrush(QtGui.QColor(palette.themeColors[role])))

        for item, includeSelf in ((self.measurementVisibilityItems["all"], False),
                                  (self.visibilityItems["Walls"], True), (self.visibilityItems["World"], False)):

            states = [item.child(index).checkState(0) for index in range(item.childCount())]
            if item is self.visibilityItems["World"]:
                states = [node.checkState(0) for name, node in self.visibilityItems.items() if name != "World"]

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
        self.FitScaleModeTabs()

    def FitScaleModeTabs(self):
        tabs = self.scaleModeTabs
        page = tabs.currentWidget()
        if page is None:
            return
        tabs.ensurePolished()
        page.layout().invalidate()
        page.layout().activate()
        frameHeight = tabs.tabBar().sizeHint().height() + 2 * tabs.style().pixelMetric(QtWidgets.QStyle.PixelMetric.PM_DefaultFrameWidth)
        tabs.setFixedHeight(page.layout().sizeHint().height() + frameHeight)

    def SetSectionExpanded(self, name, expanded):

        self.sectionContents[name].setVisible(expanded)

        heading = self.sectionButtons[name]

        heading.setIcon(UiIcon("arrow_drop_down" if expanded else "arrow_drop_up"))

        heading.setToolTip(f"{'Collapse' if expanded else 'Expand'} {heading.text()}")

        if hasattr(self.mainWindow, "sessionTimer") and not self.mainWindow.projectLoading:

            self.mainWindow.sessionTimer.start(500)



    def RestoreSectionStates(self, states):

        for name, button in self.sectionButtons.items():

            expanded = states.get(name, states.get("Vignette", False) if name == "Composite" else False)

            blocker = QtCore.QSignalBlocker(button)

            button.setChecked(expanded)

            self.SetSectionExpanded(name, expanded)

            del blocker



    def OutputPath(self):
        name = self.fileNameField.text().strip()
        if not name or name in (".", "..") or any(character in name for character in '<>:"/\\|?*\0'):
            raise ValueError("Enter a filename without folder separators or reserved characters.")
        folder = self.folderField.text().strip()
        if not folder:
            raise ValueError("Choose an output folder.")
        extension = exportFileExtensions[self.typeField.currentData()]
        if Path(name).suffix.lower() in (".png", ".svg", ".pdf"):
            name = Path(name).stem
        return Path(folder) / (name + extension)

    def FolderEdited(self):
        folder = self.folderField.text().strip()
        if self.exportFolder is not None or folder != str(self.mainWindow.BrowseDirectory(forExport = True)):
            self.exportFolder = folder or None
        self.PopulatePath()
        self.mainWindow.ProjectSettingsChanged()
        self.RecordExportHistory()

    def PopulatePath(self, force = False):
        project = self.mainWindow.projectPath
        folder = self.folderField.text().strip()
        if force or project != self.pathProject or not folder:
            folder = str(self.mainWindow.BrowseDirectory(forExport = True))
            self.folderField.setText(folder)
        if self.exportFileName and (force or project != self.pathProject or not self.fileNameField.text().strip()):
            name = self.exportFileName
            if Path(name).suffix.lower() in (".png", ".svg", ".pdf"):
                name = Path(name).stem
            self.fileNameField.setText(name)
            self.pathProject = project
            return
        name = self.fileNameField.text().strip()
        automaticName = Path(self.automaticPath).stem if self.automaticPath else None
        if not force and project == self.pathProject and name and name != automaticName:
            return
        folder = Path(folder)
        name = project.stem if project is not None else "plan"
        extension = exportFileExtensions[self.typeField.currentData()]
        path = folder / f"{name}{extension}"
        number = 1
        while path.exists():
            path = folder / f"{name}_{number}{extension}"
            number += 1
        self.pathProject = project
        self.automaticPath = str(path)
        self.fileNameField.setText(path.stem)

    def SetPathType(self, kind):
        if not self.exportHistoryRestoring:
            self.overrides["fileType"] = kind
        ownGesture = self.exportGestureBefore is None
        if ownGesture:
            self.exportGestureBefore = self.exportHistoryState

        if kind in pdfFileTypes and self.overrides.get("scaleMode") != "Print":
            self.SetScaleOption("scaleMode", "Print")
        self.RefreshControls()

        if self.projectView is not None:

            self.mainWindow.viewport.exportOverlay.scale = self.PreviewScalePerMeter()

        self.mainWindow.viewport.exportOverlay.outputFormat = exportRenderFormats[kind]

        self.mainWindow.viewport.exportOverlay.previewError = ""

        self.mainWindow.viewport.exportOverlay.svgKey = None

        self.mainWindow.viewport.exportOverlay.navigationTimer.stop()

        self.mainWindow.viewport.update()

        current = self.fileNameField.text().strip()

        if not current or current == (Path(self.automaticPath).stem if self.automaticPath else None):

            self.PopulatePath()

        else:

            self.FileNameEdited()

        self.mainWindow.ProjectSettingsChanged()
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
        if self.overrides.get("scaleMode") == "Print" and not preview:
            jobs = self.ExportJobs(Path("preview." + outputFormat), outputFormat)
            return RenderPlan(**jobs[0][1])
        return RenderPlan(**self.RenderArguments(outputFormat, preview, previewScene))

    def RenderArguments(self, outputFormat, preview = False, previewScene = False):
        main = self.mainWindow
        cachedVector = previewScene and outputFormat == "svg" and self.overrides.get("scaleMode") != "Print"

        # Use the unsaved scene and the effective export view, without changing

        # the application's theme. Preview and file output share this path.

        data = main.BuildProjectData(includeHistory = False, includeActivity = False, reuseScene = preview)

        data["settings"].update(self.CaptureView())
        data["settings"]["autoSizingUnitsMode"] = main.viewport.autoSizingUnitsMode or main.viewport.unitsMode

        return dict(planPath = main.projectPath or Path("plan.plan"), scale = self.ScalePerMeter(),

                          bounds = (main.viewport.exportOverlay.vectorBounds or main.viewport.exportOverlay.bounds) if cachedVector else
                                   main.viewport.exportOverlay.PreviewBounds() if previewScene and self.overrides.get("scaleMode") == "Print" else main.viewport.exportOverlay.bounds,
                          ruler = not cachedVector and self.borderField.currentText() == "Ruler",

                          outputFormat = outputFormat, projectData = data, applyTheme = False, preview = preview, previewScene = previewScene,
                          furnishingDefinitions = main.viewport.furnishingDefinitions,
                          clipCache = main.viewport.exportOverlay.svgClipCache if previewScene else None,

                          border = "None" if cachedVector else self.borderField.currentText(), wallStyle = self.wallStyleField.currentText(),
                          solidObjects = self.solidObjectsField.isChecked(),
                          roomStyle = self.roomStyleField.currentText(), solidRooms = self.solidRoomsField.isChecked(),
                          drawOpeningOutlines = self.drawOpeningOutlinesField.isChecked(),
                          gridOrigin = main.viewport.gridOrigin,
                          measurementTextSize = self.overrides.get("measurementTextSize", measurementDefaultTextSize),
                          borderTextSize = self.overrides.get("borderTextSize", measurementDefaultTextSize),

                          borderSize = self.overrides.get("borderSize", 28),
                          borderWidth = self.overrides.get("borderWidth", 200) if self.overrides.get("scaleMode") in ("Architectural", "Print") else None,

                          titleBlock = self.TitleBlockOptions(),
                          scaleBar = dict(self.overrides.get("scaleBar", {})),

                          texture = self.overrides.get("texture"), textureAngle = self.overrides.get("textureAngle", 0), textureSettings = self.TextureSettings(),

                          vignetteStrength = self.overrides.get("vignetteStrength", .125) if self.overrides.get("vignetteEnabled", False) else 0,

                          dpi = self.overrides.get("dpi", 300) if self.overrides.get("scaleMode") == "Print" or self.overrides.get("scaleMode") == "Architectural" and outputFormat == "png" else None,

                          architecturalScale = self.overrides.get("architecturalScale", 100) if self.overrides.get("scaleMode") in ("Architectural", "Print") else None)



    def CaptureExportOverrides(self):
        view = self.ResolvedView()
        settings = copy.deepcopy(self.overrides)
        for name in self.CaptureView():
            if name != "showMeasurements":
                settings[name] = copy.deepcopy(view[name])
        settings["measurementVisibility"] = {key: enabled and view["showMeasurements"]
                                             for key, enabled in view["measurementVisibility"].items()}
        settings["visibility"] = {key: enabled and view["visibility"]["World"]
                                  for key, enabled in view["visibility"].items()}
        settings.update(fileType = self.typeField.currentData(),
                        bounds = list(self.mainWindow.viewport.exportOverlay.bounds),
                        gridOrigin = list(self.mainWindow.viewport.gridOrigin),
                        solidObjects = self.solidObjectsField.isChecked(),
                        drawOpeningOutlines = self.drawOpeningOutlinesField.isChecked(),
                        wallStyle = self.wallStyleField.currentText(),
                        border = self.borderField.currentText(),
                        borderSize = self.overrides.get("borderSize", 28),
                        borderTextSize = self.borderTextSizeField.currentData())
        if self.overrides.get("scaleMode") in ("Architectural", "Print"):
            settings["borderWidth"] = self.overrides.get("borderWidth", 200)
        defaults = {"scale": 100, "scaleUnits": "px/m", "scaleMode": "Digital", "measurementTextSize": measurementDefaultTextSize,
                    "architecturalScale": 100, "dpi": 300,
                    "texture": None, "textureAngle": 0, "vignetteEnabled": False, "vignetteStrength": .125}
        for name, default in defaults.items():
            settings.setdefault(name, default)
        if settings["scaleMode"] == "Print":
            for name, default in (("pageSize", "A4"), ("pageOrientation", "Landscape"), ("pageOrigin", [0, 0]), ("pageOverlap", [0, 0]), ("pageOverlapOffset", [0, 0])):
                settings.setdefault(name, default)
        # Null represents the Theme choice, not a color sampled from the editor.
        # In particular, themes may use different wall and object outline colors.
        for name in ("canvasColor", "linesColor", "borderColor", "gridColor"):
            settings.setdefault(name, None)
        texture = self.TextureSettings()
        for name in ("Strength", "Highlights", "Midtones", "Shadows"):
            settings["texture" + name] = texture[name.lower()]
        filenameScale = 1
        if settings["texture"] is not None:
            try:
                filenameScale = TextureMapping(settings["texture"])[2]
            except ValueError:
                pass  # The export worker reports invalid/missing textures normally.
        # Filename tiling ratios may exceed the slider's range. Preserve their
        # existing mapping instead of clamping it or saving an invalid override.
        settings["textureScale"] = (texture["scaleOverride"] if texture["scaleOverride"] is not None else
                                    filenameScale if 0 <= filenameScale <= 4 else None)
        settings.pop("ruler", None)
        return settings

    def Export(self):



        main = self.mainWindow

        if self.projectView is None:

            return

        self.PopulatePath()

        optimized = self.typeField.currentData() == "PNG_OPTIMIZED"
        kind = self.typeField.currentData()
        outputFormat = kind.lower() if kind in pdfFileTypes else exportRenderFormats[kind]

        try:
            path = self.OutputPath()
            jobs = self.ExportJobs(path, outputFormat)
        except ValueError as error:
            main.ShowAppMessage("Export Failed", str(error), "error")
            return
        self.fileNameField.setText(path.stem)

        existing = list(dict.fromkeys(target for target, render in jobs if target.exists()))
        if existing:

            answer = main.ShowAppMessage(
                "Replace Export", "Replace the existing file(s)?", "warning", informativeText = "\n".join(str(target) for target in existing),
                standardButtons = QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                defaultButton = QtWidgets.QMessageBox.StandardButton.No, wrapInformativeText = False)

            if answer != QtWidgets.QMessageBox.StandardButton.Yes:

                return



        capturedOverrides = self.CaptureExportOverrides()
        main.exportButton.setEnabled(False)

        try:
            from .export_progress import ExportProgressDialog
            pageCount = len(jobs)
            dialog = ExportProgressDialog(self, path, outputFormat, optimized, jobs = jobs)
            jobs = None
            accepted = dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted
            error = dialog.error
            dialog.deleteLater()
            if error:
                main.ShowAppMessage("Export Failed", error, "error")
            if not accepted:
                return

            self.overrides = capturedOverrides
            self.mainWindow.ProjectSettingsChanged()
            self.RefreshControls()
            self.RecordExportHistory()
            main.exportButton.setText("Exported")

            main.exportButton.setToolTip(f"Saved {pageCount} page(s) in {path.parent}" if self.overrides.get("scaleMode") == "Print" else f"Saved {path}")

            QtCore.QTimer.singleShot(2000, lambda: main.exportButton.setText("Export"))

            self.PopulatePath()

        finally:

            main.exportButton.setEnabled(True)



    def FileNameEdited(self):
        try:
            path = self.OutputPath()
        except ValueError:
            pass
        else:
            self.fileNameField.setText(path.stem)
            self.exportFileName = path.stem
        self.mainWindow.ProjectSettingsChanged()
        self.RecordExportHistory()

    def BrowsePath(self):
        self.PopulatePath()
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose Export Folder", self.folderField.text().strip())
        if folder:
            self.BeginExportGesture()
            self.folderField.setText(folder)
            self.exportFolder = str(Path(folder).resolve())
            self.mainWindow.ProjectSettingsChanged()
            self.PopulatePath()
            self.EndExportGesture()
