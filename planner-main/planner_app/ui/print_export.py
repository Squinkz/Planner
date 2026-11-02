"""Print-mode controls and complete-page export jobs."""
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics import palette
from planner_app.graphics.icons import UiIcon
from planner_app.print_layout import PrintPageLayout, PrintDrawingBounds, PrintPaperGeometry, PrintOverlapOffset, UpgradePrintOverlap, SelectedPrintPages, printPaperSizes
from planner_app.export_settings import ExportBorderSize, exportRenderFormats
from planner_app.measurement_units import MetricUnit
from .widgets import DownwardComboBox, DragSpinBox, SectionComboDelegate


class PaperSizeDelegate(SectionComboDelegate):
    def paint(self, painter, option, index):
        if index.flags() != QtCore.Qt.ItemFlag.NoItemFlags:
            styled = QtWidgets.QStyleOptionViewItem(option)
            self.initStyleOption(styled, index)
            styled.text = ""
            style = option.widget.style() if option.widget is not None else QtWidgets.QApplication.style()
            style.drawControl(QtWidgets.QStyle.ControlElement.CE_ItemViewItem, styled, painter, option.widget)
            painter.save()
            try:
                painter.setClipRect(option.rect)
                selected = bool(styled.state & QtWidgets.QStyle.StateFlag.State_Selected)
                detailsFont = QtGui.QFont(styled.font)
                if detailsFont.pointSizeF() > 0:
                    detailsFont.setPointSizeF(detailsFont.pointSizeF() * .85)
                else:
                    detailsFont.setPixelSize(max(8, round(detailsFont.pixelSize() * .85)))
                details = index.data(QtCore.Qt.ItemDataRole.UserRole + 1) or ""
                detailsWidth = QtGui.QFontMetrics(detailsFont).horizontalAdvance(details)
                rect = option.rect.adjusted(14, 0, -14, 0)
                painter.setFont(styled.font)
                painter.setPen(QtGui.QColor(palette.themeColors["activeText" if selected else "text"]))
                painter.drawText(rect.adjusted(0, 0, -detailsWidth - 24, 0), QtCore.Qt.AlignmentFlag.AlignVCenter,
                                 index.data(QtCore.Qt.ItemDataRole.UserRole))
                painter.setFont(detailsFont)
                painter.setPen(QtGui.QColor(palette.themeColors["activeText" if selected else "mutedText"]))
                painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignRight, details)
            finally:
                painter.restore()
            return
        super().paint(painter, option, index)


class PrintExportMixin:
    def InitializePrintSelection(self):
        overlay = self.mainWindow.viewport.exportOverlay
        if (self.overrides.get("scaleMode") != "Print" or "bounds" in self.overrides
                or "pageOrigin" in self.overrides or overlay.autoBounds is None):
            return False
        # Start with one complete sheet over the model, at the chosen scale.
        # Explicit crops and even a reset-to-zero page offset retain precedence.
        x, y, width, height = overlay.autoBounds
        paper = PrintPaperGeometry(self.overrides)[0]
        origin = (x + (width - paper[0]) / 2, y + (height - paper[1]) / 2)
        bounds = (*origin, *paper)
        self.overrides.update(bounds = list(bounds), pageOrigin = list(origin))
        overlay.bounds = bounds
        overlay.pageOrigin = origin
        overlay.printSettings = dict(self.overrides)
        return True

    def UpdatePhysicalScaleView(self, previousScale):
        scale = self.overrides.get("architecturalScale", 100)
        if scale == previousScale:
            return
        v = self.mainWindow.viewport
        bounds = v.exportOverlay.bounds
        if bounds is None:
            return
        x, y, width, height = bounds
        centre = QtCore.QPointF(x + width / 2, y + height / 2)
        if self.overrides.get("scaleMode") == "Print":
            paper, stride = PrintPaperGeometry(self.overrides)
            pages = SelectedPrintPages(bounds, paper, self.overrides.get("pageOrigin", (0, 0)), stride = stride)
            if not pages:
                return
            centre = QtCore.QPointF((min(page[0] for page in pages) + max(page[0] + page[2] for page in pages)) / 2,
                                   (min(page[1] for page in pages) + max(page[1] + page[3] for page in pages)) / 2)
        position = v.WorldToViewport(centre)
        v.zoom *= previousScale / scale
        v.panOffset += position - v.WorldToViewport(centre)

    def PreviewScalePerMeter(self):
        if self.overrides.get("scaleMode") in ("Architectural", "Print"):
            return 300 * 1000 / (25.4 * self.overrides.get("architecturalScale", 100))
        return self.ScalePerMeter()

    def CreatePrintControls(self, pageLayout, architecturalLayout):
        self.printPageLayout = pageLayout
        self.architecturalPageLayout = architecturalLayout
        self.printOptions = QtWidgets.QWidget()
        form = QtWidgets.QGridLayout(self.printOptions)
        form.setContentsMargins(14, 0, 14, 6)
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(8)
        self.pageSizeField = DownwardComboBox()
        self.pageSizeField.setItemDelegate(PaperSizeDelegate(self.pageSizeField))
        self.pageSizeHeadings = []
        groups = (("A Series", [name for name in printPaperSizes if name.startswith("A") and not name.startswith("ARCH")]),
                  ("ARCH Series", [name for name in printPaperSizes if name.startswith("ARCH")]),
                  ("US Sizes", [name for name in printPaperSizes if not name.startswith("A")]))
        for heading, names in groups:
            self.pageSizeField.addItem(heading)
            item = self.pageSizeField.model().item(self.pageSizeField.count() - 1)
            item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
            font = self.pageSizeField.font()
            font.setBold(True)
            item.setFont(font)
            self.pageSizeHeadings.append(item)
            for name in names:
                width, height = printPaperSizes[name]
                units = "mm" if heading == "A Series" else "in"
                if units == "in":
                    width, height = width / 25.4, height / 25.4
                self.pageSizeField.addItem(f"{name} ({width:g} × {height:g} {units})", name)
        self.pageSizeField.setCurrentIndex(self.pageSizeField.findData("A4"))
        self.pageSizeField.setAccessibleName("Print page size")
        sizeLabel = QtWidgets.QLabel("Page size")
        sizeLabel.setBuddy(self.pageSizeField)
        form.addWidget(sizeLabel, 0, 0)
        form.addWidget(self.pageSizeField, 0, 1)
        orientation = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(orientation)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.pageOrientationGroup = QtWidgets.QButtonGroup(self)
        self.pageOrientationButtons = {}
        for name in ("Landscape", "Portrait"):
            button = QtWidgets.QPushButton()
            button.setObjectName("propertyIconButton")
            button.setIcon(UiIcon(name.lower()))
            button.setIconSize(QtCore.QSize(24, 24))
            button.setFixedHeight(32)
            button.setCheckable(True)
            button.setAccessibleName("Print " + name.lower())
            button.setToolTip(name)
            button.clicked.connect(lambda checked = False, name = name: self.SetScaleOption("pageOrientation", name))
            self.pageOrientationGroup.addButton(button)
            self.pageOrientationButtons[name] = button
            row.addWidget(button, 1)
        label = QtWidgets.QLabel("Orientation")
        label.setBuddy(self.pageOrientationButtons["Landscape"])
        form.addWidget(label, 1, 0)
        form.addWidget(orientation, 1, 1)
        self.pageOverlapRow = QtWidgets.QWidget()
        overlapLayout = QtWidgets.QHBoxLayout(self.pageOverlapRow)
        overlapLayout.setContentsMargins(0, 0, 0, 0)
        overlapLayout.setSpacing(6)
        self.pageOverlapFields = []
        for axis, name in enumerate(("X", "Y")):
            field = DragSpinBox()
            field.setAccessibleName("Page overlap " + name)
            field.setToolTip(name + " overlap in project units. Positive repeats content; negative skips content. Drag to adjust or click to type.")
            field.setKeyboardTracking(False)
            field.setMinimumHeight(32)
            field.dragStarted.connect(self.BeginExportGesture)
            field.dragFinished.connect(self.FinishPageOverlapDrag)
            field.valueChanged.connect(lambda value, axis = axis: self.SetPageOverlap(axis, value))
            self.pageOverlapFields.append(field)
            overlapLayout.addWidget(field, 1)
        self.pageOverlapReset = QtWidgets.QPushButton()
        self.pageOverlapReset.setIcon(UiIcon("refresh"))
        self.pageOverlapReset.setFixedSize(32, 32)
        self.pageOverlapReset.setAccessibleName("Reset page overlap")
        self.pageOverlapReset.setToolTip("Reset X and Y overlap to zero")
        self.pageOverlapReset.clicked.connect(lambda: self.SetScaleOption("pageOverlap", [0, 0]))
        overlapLayout.addWidget(self.pageOverlapReset)
        self.pageOverlapLabel = QtWidgets.QLabel("Overlap")
        self.pageOverlapLabel.setBuddy(self.pageOverlapFields[0])
        form.addWidget(self.pageOverlapLabel, 2, 0)
        form.addWidget(self.pageOverlapRow, 2, 1)
        form.setColumnStretch(1, 1)
        self.printNote = QtWidgets.QLabel()
        self.printNote.setWordWrap(True)
        self.printNote.setObjectName("exportFormatNote")
        self.printNote.setMinimumHeight(self.printNote.fontMetrics().lineSpacing() * 2)
        form.addWidget(self.printNote, 3, 0, 1, 2)
        pageLayout.addWidget(self.printOptions)
        self.pageSizeField.currentIndexChanged.connect(lambda index: self.SetScaleOption("pageSize", self.pageSizeField.itemData(index)))
        overlay = self.mainWindow.viewport.exportOverlay
        overlay.renderPrintPage = self.RenderPrintPage
        overlay.renderPrintScene = self.RenderPrintScene
        overlay.pageOriginChanged.connect(self.MovePrintPages)
        overlay.pageDragStarted.connect(self.BeginExportGesture)
        overlay.pageDragFinished.connect(self.EndExportGesture)

    def SetPageOverlap(self, axis, value):
        mode = (self.projectView if self.projectView is not None else self.CaptureView())["unitsMode"]
        divisor, unit = MetricUnit(mode)
        overlap = list(self.overrides.get("pageOverlap", (0, 0)))
        overlap[axis] = value * divisor
        self.SetScaleOption("pageOverlap", overlap)

    def FinishPageOverlapDrag(self, cancelled):
        if cancelled and self.exportGestureBefore is not None:
            state = self.exportGestureBefore
            self.exportGestureBefore = None
            self.mainWindow.viewport.exportOverlay.previewGesture = False
            self.RestoreExportHistory(state)
        else:
            self.EndExportGesture()

    def MovePrintPages(self, origin):
        overlay = self.mainWindow.viewport.exportOverlay
        previous = self.overrides.get("pageOrigin", (0, 0))
        dx, dy = origin[0] - previous[0], origin[1] - previous[1]
        if overlay.bounds is not None and (dx or dy):
            x, y, width, height = overlay.bounds
            overlay.bounds = (x + dx, y + dy, width, height)
            if overlay.bounds == overlay.autoBounds:
                self.overrides.pop("bounds", None)
            else:
                self.overrides["bounds"] = list(overlay.bounds)
        # Commit both changes together so one drag has one undo/redo entry.
        self.SetScaleOption("pageOrigin", list(origin))

    def RefreshPrintControls(self):
        printing = self.overrides.get("scaleMode") == "Print"
        upgraded = UpgradePrintOverlap(self.overrides)
        if upgraded is not self.overrides:
            self.overrides.update(upgraded)
            if "bounds" in upgraded:
                self.mainWindow.viewport.exportOverlay.bounds = tuple(upgraded["bounds"])
        target = self.printPageLayout if printing else self.architecturalPageLayout
        if target.indexOf(self.architecturalRow) < 0:
            target.insertWidget(0, self.architecturalRow)
        blockers = [QtCore.QSignalBlocker(self.pageSizeField),
                    *(QtCore.QSignalBlocker(button) for button in self.pageOrientationButtons.values()),
                    *(QtCore.QSignalBlocker(field) for field in self.pageOverlapFields)]
        landscape = self.overrides.get("pageOrientation", "Landscape") == "Landscape"
        for index in range(self.pageSizeField.count()):
            name = self.pageSizeField.itemData(index)
            if name not in printPaperSizes:
                continue
            width, height = printPaperSizes[name]
            units = "mm" if name.startswith("A") and not name.startswith("ARCH") else "in"
            if units == "in":
                width, height = width / 25.4, height / 25.4
            if landscape:
                width, height = height, width
            self.pageSizeField.setItemText(index, f"{name} ({width:g} × {height:g} {units})")
            self.pageSizeField.setItemData(index, f"{width:g} × {height:g} {units}", QtCore.Qt.ItemDataRole.UserRole + 1)
        self.pageSizeField.setCurrentIndex(self.pageSizeField.findData(self.overrides.get("pageSize", "A4")))
        backgroundRole = "windowBackground" if QtGui.QColor(palette.themeColors["controlBackground"]).lightnessF() < .5 else "pressedBackground"
        for heading in self.pageSizeHeadings:
            heading.setForeground(QtGui.QColor(palette.themeColors["mutedText"]))
            heading.setBackground(QtGui.QColor(palette.themeColors[backgroundRole]))
        self.pageOrientationButtons[self.overrides.get("pageOrientation", "Landscape")].setChecked(True)
        overlap = list(self.overrides.get("pageOverlap", (0, 0)))
        maximum = [1e12, 1e12]
        try:
            kind = exportRenderFormats[self.typeField.currentData()]
            border = ExportBorderSize(self.overrides, self.borderField.currentText())
            layout = PrintPageLayout(dict(self.overrides, pageOverlap = [0, 0]), border, self.TitleBlockOptions(), kind)
            maximum = [max(0, size - 1) for size in layout["tile"]]
        except ValueError:
            pass
        clamped = [min(value, limit) for value, limit in zip(overlap, maximum)]
        if printing and clamped != overlap:
            if self.mainWindow.viewport.exportOverlay.bounds is not None:
                self.overrides["pageOverlapOffset"] = PrintOverlapOffset(self.overrides, clamped, self.mainWindow.viewport.exportOverlay.bounds)
            self.overrides["pageOverlap"] = clamped
        mode = (self.projectView if self.projectView is not None else self.CaptureView())["unitsMode"]
        divisor, unit = MetricUnit(mode)
        for field, value, limit in zip(self.pageOverlapFields, clamped, maximum):
            field.setDecimals(0 if unit == "mm" else 3)
            field.setRange(-1e12 / divisor, limit / divisor)
            field.setSingleStep(100 / divisor)
            field.setSuffix(" " + unit)
            field.setValue(value / divisor)
        del blockers
        overlay = self.mainWindow.viewport.exportOverlay
        overlay.printMode = printing
        overlay.rasterDensity = self.overrides.get("dpi", 300) / 300 if self.overrides.get("scaleMode") == "Architectural" and overlay.outputFormat == "png" else 1
        overlay.printSettings = dict(self.overrides)
        overlay.pageOrigin = tuple(self.overrides.get("pageOrigin", (0, 0)))
        if printing and overlay.active and not self.exportHistoryRestoring:
            bounds = overlay.ConstrainTitleBlockBounds(overlay.bounds)
            if bounds != overlay.bounds:
                overlay.bounds = bounds
                overlay.boundsChanged.emit(bounds)
        self.mainWindow.viewport.update()
        multiplePages = False
        if printing:
            try:
                layout = self.PrintLayout()
                bounds = overlay.bounds or self.overrides.get("bounds") or overlay.autoBounds
                pages = SelectedPrintPages(bounds, layout["paperTile"], overlay.pageOrigin, stride = layout["paperStride"]) if bounds is not None else []
                multiplePages = len(pages) > 1
                pageLabel = "page" if len(pages) == 1 else "pages"
                width, height = layout["pixels"]
                resolution = f"Page resolution: {width} × {height} px\n" if exportRenderFormats[self.typeField.currentData()] == "png" else ""
                self.printNote.setText(f"{resolution}{len(pages)} {pageLabel} selected.")
            except ValueError as error:
                self.printNote.setText(str(error))
            self.printPageLayout.invalidate()
            self.printOptions.updateGeometry()
            self.scaleModeTabs.updateGeometry()
        self.pageOverlapLabel.setEnabled(multiplePages)
        self.pageOverlapRow.setEnabled(printing)
        for field in self.pageOverlapFields:
            field.setEnabled(multiplePages)
        self.pageOverlapReset.setEnabled(printing and any(value != 0 for value in clamped))
        self.FitScaleModeTabs()

    def PrintLayout(self):
        kind = exportRenderFormats[self.typeField.currentData()]
        border = ExportBorderSize(self.overrides, self.borderField.currentText())
        return PrintPageLayout(self.overrides, border, self.TitleBlockOptions(), kind)

    def ExportJobs(self, path, outputFormat):
        pdf = outputFormat in ("pdf_raster", "pdf_vector")
        if pdf and self.overrides.get("scaleMode") != "Print":
            raise ValueError("PDF export requires Print mode.")
        renderFormat = "png" if outputFormat == "pdf_raster" else "svg" if outputFormat == "pdf_vector" else outputFormat
        render = self.RenderArguments(renderFormat)
        if self.overrides.get("scaleMode") != "Print":
            return [(path, render)]
        layout = self.PrintLayout()
        pages = SelectedPrintPages(self.mainWindow.viewport.exportOverlay.bounds, layout["paperTile"],
                                   self.overrides.get("pageOrigin", (0, 0)), stride = layout["paperStride"])
        if not pages:
            raise ValueError("Enclose at least one complete page with the crop guides.")
        return [(path if pdf else path.with_name(f"{path.stem}_{index:03d}{path.suffix}"),
                 dict(render, bounds = PrintDrawingBounds(bounds, layout, self.overrides.get("pageOrigin", (0, 0))),
                      pageSize = layout["paper"], sheetIndex = index)) for index, bounds in enumerate(pages, 1)]

    def RenderPrintScene(self, bounds):
        from planner_app.export_plan import ExportSceneCache, RenderPlan
        overlay = self.mainWindow.viewport.exportOverlay
        if overlay.printRenderArguments is None:
            overlay.printRenderArguments = self.RenderArguments("svg", preview = True)
            overlay.printRenderArguments["projectData"]["settings"].pop("referenceImage", None)
        render = dict(overlay.printRenderArguments)
        from planner_app.export_preview import PreviewProcess
        worker = PreviewProcess(overlay)
        if worker is not None:
            render.update(bounds = bounds, pageSize = None, border = "None", ruler = False, titleBlock = {},
                          outputFormat = "svg", previewScene = True, transparentScene = True)
            return worker.Request("model", (overlay.printRenderKey, tuple(bounds)), lambda: render, "svg")
        if overlay.printSceneCache is None:
            overlay.printSceneCache = ExportSceneCache()
            self.mainWindow.viewport.destroyed.connect(overlay.printSceneCache.Clear)
        render.update(bounds = bounds, pageSize = None, border = "None", ruler = False, titleBlock = {},
                      outputFormat = "svg", previewScene = True, transparentScene = True, clipCache = overlay.svgClipCache,
                      sceneCache = overlay.printSceneCache, previewDocument = True)
        return RenderPlan(**render)

    def RenderPrintPage(self, bounds, sampling = 1, decorationsOnly = False):
        from planner_app.export_plan import ExportSceneCache, RenderPlan
        outputFormat = exportRenderFormats[self.typeField.currentData()]
        overlay = self.mainWindow.viewport.exportOverlay
        if overlay.printRenderArguments is None:
            overlay.printRenderArguments = self.RenderArguments(outputFormat, preview = True)
            overlay.printRenderArguments["projectData"]["settings"].pop("referenceImage", None)
        render = dict(overlay.printRenderArguments)
        layout = overlay.PrintLayout()
        pages = SelectedPrintPages(overlay.bounds, layout["paperTile"], overlay.pageOrigin, stride = layout["paperStride"])
        sheetIndex = pages.index(bounds) + 1
        render.update(bounds = PrintDrawingBounds(bounds, layout, self.overrides.get("pageOrigin", (0, 0))),
                      pageSize = layout["paper"], rasterSampling = sampling, sheetIndex = sheetIndex)
        if not decorationsOnly:
            from planner_app.export_preview import PreviewProcess
            worker = PreviewProcess(overlay)
            if worker is not None:
                key = (overlay.printRenderKey, tuple(bounds), sampling, tuple(self.overrides.get("pageOrigin", (0, 0))), sheetIndex)
                return worker.Request(("page", tuple(bounds)), key, lambda: render, outputFormat)
        if decorationsOnly:
            data = dict(render["projectData"])
            data["scene"] = dict(objects = [], groups = [], hidden = [])
            # Interactive effects are painted over the complete page in the
            # viewport, so cached borders/title blocks do not bake old values in.
            render.update(projectData = data, outputFormat = "png", texture = None, vignetteStrength = 0)
        elif outputFormat == "png":
            if overlay.printSceneCache is None:
                overlay.printSceneCache = ExportSceneCache()
                self.mainWindow.viewport.destroyed.connect(overlay.printSceneCache.Clear)
            render["sceneCache"] = overlay.printSceneCache
        return RenderPlan(**render)
