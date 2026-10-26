"""Selection property controls, mixed values and atomic bulk edits."""

from planner_app.models import Elevator, AngleGuide, ObjectControlPoints, SetControlPoint

import math
from PySide6 import QtCore, QtWidgets
from planner_app.graphics.theme import HeaderIcon, UiIcon, wallMaterials
from planner_app.models import OpenDoorway, Door, SwingingDoor, DoubleDoor, Furnishing, PocketDoor, BarnDoor, BifoldDoor, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, SlidingDoor, MeasurementGuide, NorthArrow, Arrow, Counter, Railing, Stair, Wall, Pillar, Column, Label, RoomLabel, Window, Fireplace
from planner_app.ui.widgets import DownwardComboBox, DragSpinBox, DragSlider, SizeLinkButton
from planner_app.units import PropertyUnit, FormatLength, FormatArea, imperialModes, unitModes
from planner_app.geometry.junctions import BuildWallJunction
from planner_app.furnishing_assets import FurnishingAssetProblems


from .arrow_properties import ArrowPropertiesMixin
from .angle_properties import AnglePropertiesMixin


class PropertiesMixin(AnglePropertiesMixin, ArrowPropertiesMixin):
    def BuildProperties(self, toolsLayout):
        toolsLayout.setSpacing(8)
        self.selectionLabel = QtWidgets.QLabel("No selection")
        self.selectionLabel.setObjectName("selectionHeading")
        self.selectionLabel.setWordWrap(True)
        toolsLayout.addWidget(self.selectionLabel)
        self.wallProperties = QtWidgets.QWidget()
        wallForm = QtWidgets.QFormLayout(self.wallProperties)
        wallForm.setContentsMargins(0, 16, 0, 0)
        wallForm.setVerticalSpacing(8)
        self.vertexProperties = QtWidgets.QGroupBox("Point 1")
        self.vertexProperties.setObjectName("vertexProperties")
        vertexForm = QtWidgets.QFormLayout(self.vertexProperties)
        vertexForm.setContentsMargins(10, 18, 10, 10)
        vertexForm.setVerticalSpacing(8)
        wallForm.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        vertexForm.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        self.propertyFields = {}
        self.propertyDragBefore = None
        self.bulkPropertyEdit = False
        self.objectPositionRow, self.objectPositionFields = self.BuildPositionFields(wallForm)
        controlPositionRow = QtWidgets.QWidget()
        controlPositionLayout = QtWidgets.QHBoxLayout(controlPositionRow)
        controlPositionLayout.setContentsMargins(0, 0, 0, 0)
        controlPositionLayout.setSpacing(6)
        vertexForm.addRow("Position", controlPositionRow)
        self.sizeRow = QtWidgets.QWidget()
        sizeLayout = QtWidgets.QHBoxLayout(self.sizeRow)
        sizeLayout.setContentsMargins(0, 0, 0, 0)
        sizeLayout.setSpacing(6)
        wallForm.addRow("Size", self.sizeRow)
        self.openingLengthRow = QtWidgets.QWidget()
        self.sizeLinkButton = SizeLinkButton()
        self.sizeLinkSelection = frozenset()
        openingLengthLayout = QtWidgets.QHBoxLayout(self.openingLengthRow)
        openingLengthLayout.setContentsMargins(0, 0, 0, 0)
        wallForm.addRow("Length", self.openingLengthRow)
        for fieldName, label, form in (("width", "Width", wallForm), ("length", "Length", wallForm),
                                       ("doorSize", "Door Size", wallForm), ("sillDepth", "Sill Depth", wallForm),
                                       ("wellDepth", "Well depth", wallForm),
                                       ("angle", "Angle", wallForm),
                                       ("x", "X", vertexForm), ("y", "Y", vertexForm), ("miter", "Chamfer", vertexForm)):
            spinBox = DragSpinBox()
            spinBox.setAccessibleName(label)
            spinBox.setRange((0.1 if fieldName == "width" else 0.001) if fieldName in ("width", "length", "doorSize") else -1e9, 1e9)
            if fieldName in ("sillDepth", "wellDepth"):
                spinBox.setRange(.1 if fieldName == "wellDepth" else 0.0, 1e9)
            spinBox.setDecimals(3)
            spinBox.setSuffix(" cm" if fieldName in ("width", "sillDepth", "wellDepth") else " m" if fieldName in ("length", "doorSize") else "")
            spinBox.setSingleStep(1.0 if fieldName in ("width", "sillDepth", "wellDepth") else 0.1)
            if fieldName == "angle":
                spinBox.setRange(0.0, 360.0)
                spinBox.setDecimals(1)
                spinBox.setSuffix("°")
                spinBox.setSingleStep(1.0)
            if fieldName == "miter":
                spinBox.setRange(0.0, 1.0)
                spinBox.setSuffix("")
                spinBox.setSingleStep(0.05)
                spinBox.setToolTip(spinBox.toolTip() + " Chamfer: 0 leaves a sharp corner; 1 makes the full flat cut.")
            spinBox.setKeyboardTracking(False)
            spinBox.dragStarted.connect(self.BeginPropertyDrag)
            spinBox.dragFinished.connect(self.FinishPropertyDrag)
            spinBox.valueChanged.connect(lambda value, fieldName = fieldName: self.EditProperty(fieldName, value))
            spinBox.mixedValue = False
            spinBox.editingFinished.connect(lambda fieldName = fieldName, spinBox = spinBox:
                                            self.EditProperty(fieldName, spinBox.value())
                                            if spinBox.mixedValue and spinBox.mixedEdited and spinBox.lineEdit().text().strip() else None)
            if fieldName in ("width", "length"):
                if fieldName == "length":
                    sizeLayout.addWidget(self.sizeLinkButton)
                sizeLayout.addWidget(spinBox, 1)
            elif fieldName in ("x", "y"):
                controlPositionLayout.addWidget(spinBox, 1)
            elif fieldName != "wellDepth":
                form.addRow(label, spinBox)
            self.propertyFields[fieldName] = spinBox
        self.windowWellFields = {}
        self.windowWellRows = {}
        for name, label in (("windowWell", "Window well"), ("wellDashed", "Dashed well outline")):
            checkbox = QtWidgets.QCheckBox()
            checkbox.ensurePolished()
            checkbox.setFixedWidth(checkbox.style().pixelMetric(QtWidgets.QStyle.PixelMetric.PM_IndicatorWidth, None, checkbox))
            checkbox.setAccessibleName(label)
            checkbox.clicked.connect(lambda checked, name = name: self.EditWindowWell(name, checked))
            row = QtWidgets.QWidget()
            rowLayout = QtWidgets.QHBoxLayout(row)
            rowLayout.setContentsMargins(0, 0, 0, 0)
            rowLayout.addWidget(checkbox, 0, QtCore.Qt.AlignmentFlag.AlignCenter)
            wallForm.addRow(label, row)
            if name == "windowWell":
                wallForm.addRow("Well depth", self.propertyFields["wellDepth"])
            self.windowWellFields[name] = checkbox
            self.windowWellRows[name] = row
        self.furnishingFlipFields = {}
        for fieldName, label in (("flipHorizontal", "Flip horizontal"), ("flipVertical", "Flip vertical")):
            button = QtWidgets.QPushButton()
            button.setIcon(UiIcon("flip_h" if fieldName == "flipHorizontal" else "flip_v"))
            button.setObjectName("propertyIconButton")
            button.setIconSize(QtCore.QSize(24, 24))
            button.setAccessibleName(label)
            axis = "vertical" if fieldName == "flipHorizontal" else "horizontal"
            button.setToolTip("Mirror across the selection's " + axis + " axis, or each object's local " + axis + " axis in Local mode")
            button.clicked.connect(lambda checked = False, fieldName = fieldName: self.EditFurnishingFlip(fieldName))
            wallForm.addRow(label, button)
            self.furnishingFlipFields[fieldName] = button
        self.materialField = DownwardComboBox()
        self.materialField.setIconSize(QtCore.QSize(32, 24))
        for material in wallMaterials:
            self.materialField.addItem(self.materialIcons[material], material)
        self.materialField.currentTextChanged.connect(self.EditMaterial)
        wallForm.addRow("Material", self.materialField)
        self.stairDirectionButton = QtWidgets.QPushButton()
        self.stairDirectionButton.setIcon(HeaderIcon("Redo"))
        self.stairDirectionButton.setObjectName("propertyIconButton")
        self.stairDirectionButton.setIconSize(QtCore.QSize(24, 24))
        self.stairDirectionButton.setAccessibleName("Flip stair direction")
        self.stairDirectionButton.setToolTip("Flip the stair direction")
        self.stairDirectionButton.clicked.connect(self.FlipStairDirection)
        wallForm.addRow("Direction", self.stairDirectionButton)
        self.autosizeField = QtWidgets.QCheckBox()
        self.autosizeField.stateChanged.connect(lambda state: self.EditStairAutosize(state == QtCore.Qt.CheckState.Checked.value))
        wallForm.addRow("Autosize", self.autosizeField)
        self.stepCountLabel = QtWidgets.QLabel()
        self.stepCountLabel.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.stepCountLabel.setToolTip("Includes calculated treads and one step for each landing")
        self.stepSizeLabel = QtWidgets.QLabel()
        self.stepSizeLabel.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.stairStepWidgets = {}
        for fieldName, text, label in (("stepCount", "Step count", self.stepCountLabel), ("stepSize", "Tread depth", self.stepSizeLabel)):
            spinBox = DragSpinBox()
            spinBox.setDecimals(0 if fieldName == "stepCount" else 2)
            spinBox.setRange(1 if fieldName == "stepCount" else .01, 100000)
            spinBox.setSuffix("" if fieldName == "stepCount" else " cm")
            spinBox.setSingleStep(1)
            spinBox.setKeyboardTracking(False)
            spinBox.dragStarted.connect(self.BeginPropertyDrag)
            spinBox.dragFinished.connect(self.FinishPropertyDrag)
            spinBox.valueChanged.connect(lambda value, fieldName = fieldName: self.EditProperty(fieldName, value))
            spinBox.editingFinished.connect(lambda fieldName = fieldName, spinBox = spinBox:
                                            self.EditProperty(fieldName, spinBox.value())
                                            if spinBox.mixedValue and spinBox.mixedEdited and spinBox.lineEdit().text().strip() else None)
            spinBox.mixedValue = False
            container = QtWidgets.QStackedWidget()
            container.addWidget(label)
            container.addWidget(spinBox)
            wallForm.addRow(text, container)
            self.propertyFields[fieldName] = spinBox
            self.stairStepWidgets[fieldName] = container
        toolsLayout.addWidget(self.wallProperties)
        self.doorProperties = QtWidgets.QWidget()
        doorForm = QtWidgets.QFormLayout(self.doorProperties)
        doorForm.setContentsMargins(0, 0, 0, 0)
        doorForm.setVerticalSpacing(8)
        doorForm.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        self.doorFields = {}
        for fieldName, label in (("swing", "Swing direction"), ("hinge", "Hinge side"),
                                 ("measurement", "Dimension side")):
            button = QtWidgets.QPushButton()
            button.setIcon(UiIcon("flip_h" if fieldName == "hinge" else "flip_v")
                           if fieldName != "measurement" else HeaderIcon("Measurements"))
            button.setObjectName("propertyIconButton")
            button.setIconSize(QtCore.QSize(24, 24))
            button.setAccessibleName("Flip " + label.lower())
            button.clicked.connect(lambda checked = False, fieldName = fieldName: self.EditDoorProperty(fieldName))
            doorForm.addRow(label, button)
            self.doorFields[fieldName] = button
        self.doorFields["swing"].setToolTip("Flip the door to the other side of its wall")
        self.doorFields["hinge"].setToolTip("Move the hinge to the opposite endpoint")
        self.doorFields["measurement"].setToolTip("Flip the side used to split dimensions for this opening")
        propertyWidgets = []
        propertyRowHeight = 32
        for form in (wallForm, vertexForm, doorForm):
            form.setHorizontalSpacing(16)
            form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
            for row in range(form.rowCount()):
                for role in (QtWidgets.QFormLayout.ItemRole.LabelRole, QtWidgets.QFormLayout.ItemRole.FieldRole):
                    item = form.itemAt(row, role)
                    if item is not None and item.widget() is not None:
                        widget = item.widget()
                        widget.ensurePolished()
                        propertyRowHeight = max(propertyRowHeight, widget.minimumSizeHint().height())
                        propertyWidgets.append(widget)
        for widget in propertyWidgets + [self.propertyFields[name] for name in ("width", "length", "x", "y")] + list(self.objectPositionFields.values()):
            widget.setFixedHeight(propertyRowHeight)
        for button in [self.stairDirectionButton] + list(self.doorFields.values()) + list(self.furnishingFlipFields.values()):
            button.setFixedWidth(propertyRowHeight)
        for row in self.windowWellRows.values():
            row.setFixedWidth(propertyRowHeight)
        toolsLayout.addWidget(self.doorProperties)
        self.BuildArrowProperties(toolsLayout, rowHeight = propertyRowHeight)
        self.BuildAngleProperties(toolsLayout)
        self.vertexSpacing = QtWidgets.QWidget()
        self.vertexSpacing.setFixedHeight(12)
        toolsLayout.addWidget(self.vertexSpacing)
        toolsLayout.addWidget(self.vertexProperties)
        self.labelProperties = QtWidgets.QWidget()
        labelForm = QtWidgets.QFormLayout(self.labelProperties)
        labelForm.setContentsMargins(0, 16, 0, 0)
        labelForm.setHorizontalSpacing(16)
        labelForm.setVerticalSpacing(8)
        labelForm.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        labelForm.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetMinimumSize)
        self.labelTextField = QtWidgets.QPlainTextEdit()
        self.labelTextField.setObjectName("labelTextField")
        self.labelTextField.setMaximumHeight(110)
        self.labelTextField.setMinimumHeight(80)
        self.labelTextField.setTabChangesFocus(True)
        self.labelTextField.textChanged.connect(self.EditLabelText)
        labelForm.addRow("Text", self.labelTextField)
        self.roomNameField = QtWidgets.QLineEdit()
        self.roomNameField.setAccessibleName("Room name")
        self.roomNameField.textChanged.connect(self.EditLabelText)
        labelForm.addRow("Name", self.roomNameField)
        self.roomAreaValue = QtWidgets.QLabel()
        self.roomAreaValue.setAccessibleName("Room area")
        self.roomAreaValue.setFixedHeight(propertyRowHeight)
        self.roomAreaValue.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        labelForm.addRow("Area", self.roomAreaValue)
        self.roomUnitsField = DownwardComboBox()
        self.roomUnitsField.setAccessibleName("Room area units")
        self.roomUnitsField.addItem("Project", None)
        for mode in unitModes:
            self.roomUnitsField.addItem(mode, mode)
        self.roomUnitsField.setFixedHeight(propertyRowHeight)
        self.roomUnitsField.currentIndexChanged.connect(self.EditRoomUnits)
        labelForm.addRow("Units", self.roomUnitsField)
        self.labelFields = {}
        self.labelPositionRow, self.labelPositionFields = self.BuildPositionFields(labelForm)
        labelSizeRow = QtWidgets.QHBoxLayout()
        labelSizeRow.setContentsMargins(0, 0, 0, 0)
        labelSizeRow.setSpacing(6)
        labelForm.addRow("Size", labelSizeRow)
        for name, title in (("width", "Width"), ("length", "Length"), ("pointSize", "Point size")):
            control = DragSpinBox()
            control.setAccessibleName(title)
            control.setKeyboardTracking(False)
            control.setRange(.01, 1e9)
            control.setDecimals(3)
            control.setFixedHeight(propertyRowHeight)
            control.dragStarted.connect(self.BeginPropertyDrag)
            control.dragFinished.connect(self.FinishPropertyDrag)
            control.valueChanged.connect(lambda value, name = name: self.EditLabelSize(name, value))
            control.editingFinished.connect(lambda name = name, control = control:
                                            self.EditLabelSize(name, control.value()) if control.mixedValue and control.mixedEdited else None)
            if name != "pointSize":
                control.setToolTip(title + ". Resizes the label proportionally.")
            else:
                control.setToolTip("")
            self.labelFields[name] = control
            if name in ("width", "length"):
                labelSizeRow.addWidget(control, 1)
            else:
                labelForm.addRow(title, control)
        intensityRow, self.labelIntensitySlider, self.labelIntensityValue = self.BuildObjectOpacityRow(propertyRowHeight, "Label")
        labelForm.addRow(intensityRow)
        toolsLayout.addWidget(self.labelProperties)
        self.labelProperties.hide()
        self.northArrowOpacityRow, self.northArrowIntensitySlider, self.northArrowIntensityValue = self.BuildObjectOpacityRow(propertyRowHeight, "North arrow")
        toolsLayout.addWidget(self.northArrowOpacityRow)
        self.northArrowOpacityRow.hide()
        # Polish before fixing heights, so stylesheet metrics cannot resize only
        # some controls when their form becomes visible for the first time.
        for panel in (self.wallProperties, self.vertexProperties, self.doorProperties,
                      self.arrowProperties, self.angleGuideProperties, self.labelProperties):
            form = panel.layout()
            form.setVerticalSpacing(8)
            form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
            for control in panel.findChildren(QtWidgets.QAbstractSpinBox):
                control.ensurePolished()
                control.setFixedHeight(propertyRowHeight)
            for row in range(form.rowCount()):
                for role in (QtWidgets.QFormLayout.ItemRole.LabelRole, QtWidgets.QFormLayout.ItemRole.FieldRole):
                    item = form.itemAt(row, role)
                    widget = item.widget() if item is not None else None
                    if widget is not None and widget is not self.labelTextField:
                        widget.ensurePolished()
                        widget.setFixedHeight(propertyRowHeight)

    def EditRoomUnits(self, index):
        labels = list({id(obj): obj for obj, point in self.viewport.SelectionEntries()}.values())
        if not labels or any(not isinstance(label, RoomLabel) for label in labels):
            return
        mode = self.roomUnitsField.itemData(index)
        if all(label.unitsOverride == mode for label in labels):
            return
        before = self.viewport.CaptureState()
        for label in labels:
            label.unitsOverride = mode
        self.viewport.roomDetection.UpdateLabels(force = True)
        self.viewport.RecordEdit(before)
        self.RefreshProperties()
        self.viewport.update()

    def BuildObjectOpacityRow(self, rowHeight, name):
        row = QtWidgets.QWidget()
        row.setMinimumHeight(rowHeight)
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        opacityIcon = QtWidgets.QLabel()
        opacityIcon.setPixmap(UiIcon("opacity").pixmap(24, 24))
        opacityIcon.setToolTip("Opacity")
        opacityIcon.setAccessibleName("Opacity")
        layout.addWidget(opacityIcon)
        slider = DragSlider(QtCore.Qt.Orientation.Horizontal)
        slider.setMinimumHeight(rowHeight)
        slider.setAccessibleName(name + " opacity")
        slider.setRange(0, 100)
        slider.setValue(100)
        slider.setToolTip("Controls opacity: 0 is invisible and 1 is fully opaque")
        slider.sliderPressed.connect(self.BeginPropertyDrag)
        slider.sliderReleased.connect(lambda: self.FinishPropertyDrag(False))
        slider.valueChanged.connect(self.EditObjectIntensity)
        value = QtWidgets.QLabel("1.00")
        layout.addWidget(slider, 1)
        layout.addWidget(value)
        return row, slider, value

    def BuildPositionFields(self, form):
        row = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        fields = {}
        for axis in ("x", "y"):
            field = DragSpinBox()
            field.setAccessibleName("Position " + axis.upper())
            field.setToolTip("Center " + axis.upper() + ". Drag to adjust or click to type.")
            field.setKeyboardTracking(False)
            field.setMinimumHeight(32)
            field.dragStarted.connect(self.BeginPropertyDrag)
            field.dragFinished.connect(self.FinishPropertyDrag)
            field.valueChanged.connect(lambda value, axis = axis: self.EditObjectPosition(axis, value))
            field.editingFinished.connect(lambda axis = axis, field = field:
                self.EditObjectPosition(axis, field.value()) if field.mixedValue and field.mixedEdited else None)
            fields[axis] = field
            layout.addWidget(field, 1)
        form.addRow("Position", row)
        return row, fields

    def RefreshPositionFields(self, fields, objects):
        divisor, unit = PropertyUnit("x", objects[0], self.viewport.unitsMode)
        pivot = self.ObjectPositionPivot(objects)
        for axis, field in fields.items():
            values = ([getattr(pivot, axis)()] if pivot is not None else
                      [getattr(obj.middleVertex if isinstance(obj, AngleGuide) else (obj.firstVertex + obj.secondVertex) / 2, axis)() for obj in objects])
            blocker = QtCore.QSignalBlocker(field)
            field.setToolTip(("Anchor " if isinstance(objects[0], AngleGuide) else "Rotation pivot " if pivot is not None else "Center ") + axis.upper() + ". Drag to adjust or click to type.")
            field.setDecimals(0 if unit == "mm" else 3)
            field.setRange(-1e12 / divisor, 1e12 / divisor)
            field.setSingleStep(100 / divisor)
            field.mixedValue = not all(math.isclose(value, values[0], abs_tol = 1e-6) for value in values)
            field.mixedEdited = False
            field.commonSuffix = " " + unit
            field.setSuffix("" if field.mixedValue else field.commonSuffix)
            field.setValue(values[0] / divisor)
            field.lineEdit().setPlaceholderText("(different)" if field.mixedValue else "")
            if field.mixedValue:
                field.lineEdit().clear()
            del blocker

    def ObjectPositionPivot(self, objects):
        v = self.viewport
        if not any(obj is v.furnishingRotationObject for obj in objects):
            return None
        if v.rotationPivot is not None:
            return QtCore.QPointF(v.rotationPivot)
        box = v.FurnishingSelectionBox() if len(objects) > 1 else None
        obj = box if box is not None else objects[0]
        return (obj.firstVertex + obj.secondVertex) / 2

    def EditObjectPosition(self, axis, value):
        v = self.viewport
        objects = list({id(obj): obj for obj, index in v.SelectionEntries()}.values())
        if not objects or any(not isinstance(obj, (Furnishing, Pillar, AngleGuide)) for obj in objects):
            return
        divisor, unused = PropertyUnit(axis, objects[0], v.unitsMode)
        target = value * divisor
        pivot = self.ObjectPositionPivot(objects)
        centers = ([pivot] * len(objects) if pivot is not None else
                   [obj.middleVertex if isinstance(obj, AngleGuide) else (obj.firstVertex + obj.secondVertex) / 2 for obj in objects])
        if all(math.isclose(getattr(center, axis)(), target, abs_tol = 1e-6) for center in centers):
            return
        before = v.CaptureState()
        for obj, center in zip(objects, centers):
            offset = target - getattr(center, axis)()
            delta = QtCore.QPointF(offset if axis == "x" else 0, offset if axis == "y" else 0)
            obj.firstVertex += delta
            obj.secondVertex += delta
            if isinstance(obj, AngleGuide):
                obj.middleVertex += delta
        if not v.FitWallOpenings(before):
            v.RestoreState(before)
        else:
            if pivot is not None and v.rotationPivot is not None:
                v.rotationPivot = pivot + delta
            if self.propertyDragBefore is None:
                v.RecordEdit(before)
        self.RefreshProperties()
        v.update()

    def EditLabelText(self):
        labels = [obj for obj, index in self.viewport.SelectionEntries()]
        if not labels or any(not isinstance(obj, Label) for obj in labels):
            return
        text = self.roomNameField.text() if all(isinstance(label, RoomLabel) for label in labels) else self.labelTextField.toPlainText()
        if all(obj.text == text for obj in labels):
            return
        before = self.viewport.CaptureState()
        for label in labels:
            label.SetText(text)
        self.viewport.RecordEdit(before, coalesceKey = ("labelText", tuple(id(label) for label in labels)))
        self.RefreshProperties()
        self.viewport.update()

    def EditLabelSize(self, name, value):
        labels = list({id(obj): obj for obj, index in self.viewport.SelectionEntries()}.values())
        if not labels or any(not isinstance(obj, Label) for obj in labels):
            return
        before = self.viewport.CaptureState()
        for label in labels:
            if name == "pointSize":
                label.SetPointSize(value)
            else:
                divisor, unit = PropertyUnit(name, label, self.viewport.unitsMode)
                factor = value * divisor / getattr(label, name)
                origin = label.origin
                direction = (label.secondVertex - label.firstVertex) / label.length
                width = label.width * factor
                length = label.length * factor
                east = QtCore.QPointF(direction.y(), -direction.x())
                label.width = width
                label.firstVertex = origin + east * (width / 2)
                label.secondVertex = label.firstVertex + direction * length
        if self.propertyDragBefore is None:
            self.viewport.RecordEdit(before)
        self.RefreshProperties()
        self.viewport.update()

    def EditObjectIntensity(self, value):
        objects = [obj for obj, index in self.viewport.SelectionEntries()]
        if not objects or type(objects[0]) not in (Label, RoomLabel, NorthArrow) or any(type(obj) is not type(objects[0]) for obj in objects):
            return
        intensity = value / 100
        readout = self.northArrowIntensityValue if isinstance(objects[0], NorthArrow) else self.labelIntensityValue
        readout.setText(f"{intensity:.2f}")
        if all(obj.intensity == intensity for obj in objects):
            return
        before = self.viewport.CaptureState()
        for obj in objects:
            obj.intensity = intensity
        if self.propertyDragBefore is None:
            self.viewport.RecordEdit(before)
        self.viewport.update()

    def RefreshProperties(self):
        if self.bulkPropertyEdit:
            return
        if self.referenceImage.active:
            self.referenceImage.SyncProperties()
            return
        self.selectionLabel.show()
        # Keep all property signals blocked until refresh returns. Intermediate
        # ranges/suffixes use metric units and must never edit the selected object.
        propertyBlockers = [QtCore.QSignalBlocker(field) for field in self.propertyFields.values()]
        entries = self.viewport.SelectionEntries()
        sizeSelection = frozenset(id(obj) for obj, index in entries)
        if sizeSelection != self.sizeLinkSelection:
            self.sizeLinkSelection = sizeSelection
            self.sizeLinkButton.setChecked(all(isinstance(obj, (Furnishing, Pillar, Fireplace)) for obj, index in entries))
        self.viewport.EnsureObjectIds()
        labelSelection = bool(entries) and all(isinstance(obj, Label) for obj, index in entries)
        northSelection = bool(entries) and all(isinstance(obj, NorthArrow) for obj, index in entries)
        self.northArrowOpacityRow.setVisible(northSelection)
        if northSelection:
            arrows = [obj for obj, index in entries]
            blocker = QtCore.QSignalBlocker(self.northArrowIntensitySlider)
            self.northArrowIntensitySlider.setValue(round(arrows[0].intensity * 100))
            self.northArrowIntensityValue.setText(f"{arrows[0].intensity:.2f}" if all(obj.intensity == arrows[0].intensity for obj in arrows) else "(different)")
            del blocker
        self.labelProperties.setVisible(labelSelection)
        if self.RefreshAngleProperties(entries):
            return
        if self.RefreshArrowProperties(entries):
            return
        if labelSelection:
            self.wallProperties.hide()
            self.doorProperties.hide()
            self.vertexProperties.hide()
            self.vertexSpacing.hide()
            self.labelProperties.show()
            labels = list({id(obj): obj for obj, index in entries}.values())
            self.RefreshPositionFields(self.labelPositionFields, labels)
            for name, control in self.labelFields.items():
                values = [getattr(label, name) for label in labels]
                divisor, unit = (1, "pt") if name == "pointSize" else PropertyUnit(name, labels[0], self.viewport.unitsMode)
                blocker = QtCore.QSignalBlocker(control)
                mixed = not all(math.isclose(value, values[0], abs_tol = 1e-6) for value in values)
                control.setDecimals(0 if unit == "mm" else 3)
                control.setRange(.001 / divisor, 1e9 / divisor)
                control.setSingleStep(1 if name == "pointSize" else 10 / divisor)
                control.mixedValue = mixed
                control.mixedEdited = False
                control.commonSuffix = " " + unit
                control.setSuffix("" if mixed else control.commonSuffix)
                control.setValue(values[0] / divisor)
                control.lineEdit().setPlaceholderText("(different)" if mixed else "")
                if mixed:
                    control.lineEdit().clear()
                del blocker
            rooms = all(isinstance(label, RoomLabel) for label in labels)
            form = self.labelProperties.layout()
            form.setRowVisible(self.labelTextField, not rooms)
            form.setRowVisible(self.roomNameField, rooms)
            form.setRowVisible(self.roomAreaValue, rooms)
            form.setRowVisible(self.roomUnitsField, rooms)
            if rooms:
                blocker = QtCore.QSignalBlocker(self.roomUnitsField)
                modes = [label.unitsOverride for label in labels]
                self.roomUnitsField.setCurrentIndex(self.roomUnitsField.findData(modes[0]) if all(mode == modes[0] for mode in modes) else -1)
                self.roomUnitsField.setPlaceholderText("(different)")
                del blocker
                self.viewport.roomDetection.UpdateLabels(force = True)
                areas = [FormatArea(label.areaSquareMillimeters, label.areaUnitsMode) for label in labels]
                self.roomAreaValue.setText(areas[0] if len(set(areas)) == 1 else "(different)")
            title = "Room Label" if rooms else "Label"
            self.selectionLabel.setText(f"{title} (#{labels[0].objectId:04d})" if len(labels) == 1 else f"{len(labels)} {title}s selected")
            text = labels[0].text if all(obj.text == labels[0].text for obj in labels) else ""
            blocker = QtCore.QSignalBlocker(self.roomNameField)
            name = text if rooms else ""
            if self.roomNameField.text() != name:
                self.roomNameField.setText(name)
            self.roomNameField.setPlaceholderText("(different)" if any(obj.text != labels[0].text for obj in labels) else "")
            del blocker
            blocker = QtCore.QSignalBlocker(self.labelTextField)
            if self.labelTextField.toPlainText() != text:
                self.labelTextField.setPlainText(text)
            self.labelTextField.setPlaceholderText("(different)" if any(obj.text != labels[0].text for obj in labels) else "")
            del blocker
            blocker = QtCore.QSignalBlocker(self.labelIntensitySlider)
            self.labelIntensitySlider.setValue(round(labels[0].intensity * 100))
            self.labelIntensityValue.setText(f"{labels[0].intensity:.2f}" if all(obj.intensity == labels[0].intensity for obj in labels) else "(different)")
            del blocker
            return
        for spinBox in self.propertyFields.values():
            if spinBox.mixedValue:
                blocker = QtCore.QSignalBlocker(spinBox)
                spinBox.mixedValue = False
                spinBox.setSuffix(spinBox.commonSuffix)
                del blocker
        wall = self.viewport.selectedWall
        for fieldName, field in self.propertyFields.items():
            if fieldName in ("angle", "miter", "stepCount"):
                continue
            blocker = QtCore.QSignalBlocker(field)
            field.setRange(.01 if fieldName == "stepSize" else .1 if fieldName == "wellDepth" else 0 if fieldName == "sillDepth" else .1 if fieldName == "width" else .001 if fieldName in ("length", "doorSize") else -1e9, 100000 if fieldName == "stepSize" else 1e9)
            # These metric values are staging values for the final unit conversion.
            # Rounding them to display precision loses exact imperial grid lengths.
            field.setDecimals(9 if self.viewport.unitsMode in imperialModes else 2 if fieldName == "stepSize" else 3)
            field.setSingleStep(1 if fieldName in ("width", "sillDepth", "wellDepth", "stepSize") else .1)
            field.setSuffix(" " + PropertyUnit(fieldName, wall, "Adaptive Metric")[1] if fieldName not in ("x", "y") else "")
            del blocker
        entries = self.viewport.SelectionEntries()
        if len({Wall if type(obj) in (Wall, Pillar, Column) else type(obj) for obj, index in entries}) > 1:
            objects = len({id(obj) for obj, index in entries})
            self.selectionLabel.setText(f"Multiple types ({objects} objects)")
            self.wallProperties.hide()
            self.doorProperties.hide()
            self.vertexProperties.hide()
            self.vertexSpacing.hide()
            return
        vertexIndex = self.viewport.selectedVertex
        if len({type(obj) for obj, index in entries}) > 1 and all(type(obj) in (Wall, Pillar, Column) for obj, index in entries):
            wall = next(obj for obj, index in entries if type(obj) is Wall)
        isWindow = isinstance(wall, Window)
        isDoor = isinstance(wall, Door)
        isSilledWindow = isinstance(wall, SilledWindow)
        isSlidingDoor = isinstance(wall, SlidingDoor)
        isPocketDoor = isinstance(wall, PocketDoor)
        isBarnDoor = isinstance(wall, BarnDoor)
        isBifoldDoor = isinstance(wall, BifoldDoor)
        isStair = isinstance(wall, Stair)
        isRailing = isinstance(wall, Railing)
        hasSizing = isStair or isRailing
        isFurnishing = isinstance(wall, Furnishing)
        isPillar = isinstance(wall, Pillar)
        self.wallProperties.layout().setRowVisible(self.objectPositionRow, isFurnishing or isPillar)
        if isFurnishing or isPillar:
            self.RefreshPositionFields(self.objectPositionFields, list({id(obj): obj for obj, index in entries}.values()) or [wall])
        self.viewport.EnsureObjectIds()
        self.doorProperties.setVisible(isWindow and not isinstance(wall, OpenDoorway))
        self.doorProperties.layout().setRowVisible(self.doorFields["swing"], isDoor or isinstance(wall, DoubleDoor) or isSlidingDoor or isBarnDoor or isBifoldDoor or type(wall) in (Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, Fireplace))
        self.doorProperties.layout().setRowVisible(self.doorFields["hinge"], isDoor or isSlidingDoor or isPocketDoor or isinstance(wall, (CasementWindow, SwingingDoor)))
        measurementClass = "windows" if type(wall) in (Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow) else "doors"
        self.doorProperties.layout().setRowVisible(self.doorFields["measurement"],
                                                   type(wall) in (Door, DoubleDoor, SlidingDoor, BarnDoor, Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow)
                                                   and self.viewport.showMeasurements and self.viewport.measurementVisibility["walls"]
                                                   and self.viewport.measurementSettings[measurementClass] == 1
                                                   and any(not obj.measurementHidden for obj, index in entries))
        sideLabel = self.doorProperties.layout().labelForField(self.doorFields["swing"])
        sideLabel.setText("Facing" if isBarnDoor or type(wall) in (Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, Fireplace) else "Panel side" if isSlidingDoor else "Swing direction")
        sideLabel.setMinimumWidth(sideLabel.sizeHint().width())
        self.doorFields["swing"].setToolTip("Flip the panel to the other side of its wall" if isBarnDoor else "Flip the window to the other side of its wall" if type(wall) in (Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow) else
                                          "Mirror the panels across the wall" if isSlidingDoor else
                                          "Flip the door to the other side of its wall")
        hingeLabel = self.doorProperties.layout().labelForField(self.doorFields["hinge"])
        hingeLabel.setText("Slide direction" if isBarnDoor else "Pocket side" if isPocketDoor else "Slide direction" if isSlidingDoor else "Hinge side")
        hingeLabel.setMinimumWidth(hingeLabel.sizeHint().width())
        self.doorFields["hinge"].setToolTip("Swap the opening and parking sides" if isBarnDoor else "Swap the opening and pocket sides" if isPocketDoor else
                                          "Reverse the sliding direction" if isSlidingDoor else "Move the hinge to the opposite endpoint")
        self.wallProperties.layout().setRowVisible(self.propertyFields["sillDepth"], isSilledWindow)
        hasWell = type(wall) in (Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow)
        for name, checkbox in self.windowWellFields.items():
            self.wallProperties.layout().setRowVisible(self.windowWellRows[name], hasWell and (name == "windowWell" or wall.windowWell))
            if hasWell:
                states = {getattr(obj, name) for obj, index in entries}
                blocker = QtCore.QSignalBlocker(checkbox)
                checkbox.setTristate(len(states) > 1)
                checkbox.setCheckState(QtCore.Qt.CheckState.PartiallyChecked if len(states) > 1 else
                                       QtCore.Qt.CheckState.Checked if getattr(wall, name) else QtCore.Qt.CheckState.Unchecked)
                del blocker
        self.wallProperties.layout().setRowVisible(self.propertyFields["wellDepth"], hasWell and wall.windowWell)
        self.wallProperties.layout().setRowVisible(self.propertyFields["angle"], isFurnishing or isPillar)
        for button in self.furnishingFlipFields.values():
            self.wallProperties.layout().setRowVisible(button, type(wall) is Furnishing)
        self.wallProperties.layout().setRowVisible(self.propertyFields["doorSize"], isSlidingDoor or isPocketDoor)
        pairedSize = not isWindow or isinstance(wall, Fireplace)
        lengthContainer = self.sizeRow if pairedSize else self.openingLengthRow
        if self.propertyFields["length"].parentWidget() is not lengthContainer:
            self.propertyFields["length"].parentWidget().layout().removeWidget(self.propertyFields["length"])
            lengthContainer.layout().addWidget(self.propertyFields["length"], 1)
            self.propertyFields["length"].show()
            QtWidgets.QWidget.setTabOrder(self.propertyFields["width"], self.propertyFields["length"])
            QtWidgets.QWidget.setTabOrder(self.propertyFields["length"], self.propertyFields["doorSize"])
        self.wallProperties.layout().setRowVisible(self.sizeRow, pairedSize)
        self.wallProperties.layout().setRowVisible(self.openingLengthRow, not pairedSize and not isPocketDoor)
        self.wallProperties.layout().setRowVisible(self.materialField, isinstance(wall, Fireplace) or not isWindow and not hasSizing and not isFurnishing and not isinstance(wall, (Counter, Elevator)))
        self.wallProperties.layout().setRowVisible(self.autosizeField, hasSizing)
        for container in self.stairStepWidgets.values():
            self.wallProperties.layout().setRowVisible(container, hasSizing)
        self.wallProperties.layout().setRowVisible(self.stairDirectionButton, isStair)
        if isStair:
            self.stairDirectionButton.setIcon(HeaderIcon("Undo" if wall.directionReversed else "Redo"))
        self.propertyFields["width"].setSuffix(" m" if isStair else " cm")
        self.propertyFields["length"].setSuffix(" cm" if isFurnishing else " m")
        self.propertyFields["length"].setSingleStep(1.0 if isFurnishing else .1)
        self.propertyFields["width"].setRange(.001 if isStair else .1, 1e9)
        self.propertyFields["width"].setSingleStep(.1 if isStair else 1)
        if isinstance(wall, (Wall, Fireplace)):
            blocker = QtCore.QSignalBlocker(self.materialField)
            self.materialField.setCurrentText(wall.material)
            del blocker
        self.propertyFields["width"].setReadOnly(isWindow and not isinstance(wall, Fireplace))
        self.propertyFields["width"].setToolTip("Width is inherited from the parent wall" if isWindow else
                                               "Width. Drag left or right to adjust. Hold Alt for finer control. Click to type a value.")
        self.propertyFields["length"].setToolTip("Length. Drag left or right to adjust. Hold Alt for finer control. Click to type a value.")
        vertices = [(obj, index) for obj, index in entries if index is not None]
        showChamfer = bool(vertices)
        checkedJoints = set()
        for obj, index in vertices:
            if type(obj) not in (Wall, Counter, Stair):
                showChamfer = False
                break
            position = obj.firstVertex if index == 0 else obj.secondVertex
            key = (type(obj), position.x(), position.y())
            if key in checkedJoints:
                continue
            checkedJoints.add(key)
            rays = []
            for other in self.viewport.walls:
                if type(other) is not type(obj):
                    continue
                for endpoint, far in ((other.firstVertex, other.secondVertex), (other.secondVertex, other.firstVertex)):
                    if QtCore.QLineF(position, endpoint).length() > .01:
                        continue
                    delta = far - endpoint
                    length = math.hypot(delta.x(), delta.y())
                    if length > 1e-10:
                        rays.append(((delta.x() / length, delta.y() / length), other.width / 2, len(rays)))
            if len(rays) != 2:
                showChamfer = False
                break
            # Ask the numeric builder whether a moving cut actually exists.
            # Straight/duplicate rays and guarded local transitions have none;
            # fixed unequal-width cap planes alone do not enable the control.
            planes = BuildWallJunction((0, 0), rays, [1, 1], 0)[4]
            if not planes[0] or not planes[1] or planes[0][-1] != planes[1][-1]:
                showChamfer = False
                break
        self.vertexProperties.layout().setRowVisible(self.propertyFields["miter"], showChamfer)
        self.wallProperties.setVisible(wall is not None)
        self.vertexProperties.setVisible(wall is not None and vertexIndex is not None)
        self.vertexSpacing.setVisible(wall is not None and vertexIndex is not None)
        if wall is None:
            self.selectionLabel.setText("No selection")
            return
        objectType = "Elevator" if isinstance(wall, Elevator) else wall.definition["name"] if isFurnishing else "Fireplace" if isinstance(wall, Fireplace) else "Column" if isinstance(wall, Column) else "Pillar" if isPillar else "Railing" if isRailing else "Stair" if isStair else "Bifold Door" if isBifoldDoor else "Barn Door" if isBarnDoor else "Pocket Door" if isPocketDoor else "Sliding Door" if isSlidingDoor else "Double Door" if isinstance(wall, DoubleDoor) else "Swinging Door" if isinstance(wall, SwingingDoor) else "Standard Door" if isDoor else "Silled Window" if isSilledWindow else "Double Casement Window" if isinstance(wall, DoubleCasementWindow) else "Awning Window" if isinstance(wall, AwningWindow) else "Casement Window" if isinstance(wall, CasementWindow) else "Open Doorway" if isinstance(wall, OpenDoorway) else "Standard Window" if isWindow else "Counter" if isinstance(wall, Counter) else "Wall"
        furnishingNames = {}
        missingFurnishings = set()
        if isFurnishing:
            for obj in [wall] + [obj for obj, index in entries if obj is not wall]:
                key = getattr(obj, "definitionKey", obj.definition["key"])
                problems = FurnishingAssetProblems(key, self.viewport.furnishingDefinitions, obj.definition) if type(obj) is Furnishing else {}
                missing = bool(problems)
                status = "missing" if problems.get(key) == "missing" else "asset error"
                furnishingNames[id(obj)] = f"{key} ({status})" if missing else obj.definition["name"]
                if missing:
                    missingFurnishings.add(id(obj))
            objectType = furnishingNames[id(wall)]
        self.selectionLabel.setText(f"{objectType} (#{wall.objectId:04d})")
        values = {"width": wall.width, "length": QtCore.QLineF(wall.firstVertex, wall.secondVertex).length()}
        if isinstance(wall, Fireplace):
            self.propertyFields["width"].setToolTip("Width: size through the wall. Drag to adjust or click to type.")
            self.propertyFields["length"].setToolTip("Length: size along the wall. Drag to adjust or click to type.")
            values["width"] = wall.depth
        if isFurnishing or isPillar:
            values["angle"] = wall.angle
        if isSilledWindow:
            values["sillDepth"] = wall.sillDepth
        if hasWell:
            values["wellDepth"] = wall.wellDepth
        if isSlidingDoor or isPocketDoor:
            values["doorSize"] = wall.length / 2
        if hasSizing:
            self.stepCountLabel.setToolTip("Includes posts at both endpoints" if isRailing else "Includes calculated treads and one step for each landing")
            for fieldName, text in (("stepCount", "Post Count" if isRailing else "Step count"), ("stepSize", "Segment Width" if isRailing else "Tread depth")):
                self.wallProperties.layout().labelForField(self.stairStepWidgets[fieldName]).setText(text)
            countBlocker = QtCore.QSignalBlocker(self.propertyFields["stepCount"])
            self.propertyFields["stepCount"].setRange(2 if isRailing else 1, 100000)
            del countBlocker
            limits = self.viewport.AutoSizingLimits("railings" if isRailing else "stairs")
            minimumText = FormatLength(limits["minimum"], self.viewport.unitsMode, "cm")
            maximumText = FormatLength(limits["maximum"], self.viewport.unitsMode, "cm")
            self.stepSizeLabel.setToolTip(f"Targets {'spacing' if isRailing else 'tread depth'} between {minimumText} and {maximumText}")
            stairs = list({id(obj): obj for obj, index in entries}.values())
            modes = {obj.autosize for obj in stairs}
            blocker = QtCore.QSignalBlocker(self.autosizeField)
            self.autosizeField.setTristate(len(modes) > 1)
            self.autosizeField.setCheckState(QtCore.Qt.CheckState.PartiallyChecked if len(modes) > 1 else
                                            QtCore.Qt.CheckState.Checked if wall.autosize else QtCore.Qt.CheckState.Unchecked)
            del blocker
            for container in self.stairStepWidgets.values():
                container.setCurrentIndex(1 if modes == {False} else 0)
            self.stepCountLabel.setText(str((wall.postCount if isRailing else wall.stepCount)))
            self.stepSizeLabel.setText(f"{(wall.segmentWidth if isRailing else wall.stepSize) / 10:.2f} cm")
            values.update(stepCount = (wall.postCount if isRailing else wall.stepCount), stepSize = (wall.segmentWidth if isRailing else wall.stepSize))
            self.propertyFields["stepCount"].setSuffix("")
            self.propertyFields["stepSize"].setSuffix(" cm")
        if vertexIndex is not None:
            self.vertexProperties.setTitle(f"Point {vertexIndex + 1}")
            vertex = wall.firstVertex if vertexIndex == 0 else wall.secondVertex
            values.update({"x": vertex.x(), "y": vertex.y()})
            if not isWindow:
                values["miter"] = wall.firstMiter if vertexIndex == 0 else wall.secondMiter
        for fieldName, value in values.items():
            spinBox = self.propertyFields[fieldName]
            blocker = QtCore.QSignalBlocker(spinBox)
            if fieldName == "width" and isinstance(wall, Fireplace):
                spinBox.setMinimum(wall.parentWall.width / 10)
            if fieldName in ("length", "doorSize"):
                maximum = (1 - wall.firstFraction) * QtCore.QLineF(wall.parentWall.firstVertex, wall.parentWall.secondVertex).length() / 1000 if isWindow else 1e9
                minimum = 0.001 if isWindow else max(0.001, self.viewport.MinimumOpeningLength(wall) / 1000)
                if isFurnishing:
                    minimum = .1
                if isinstance(wall, Fireplace):
                    minimum, maximum = .001, QtCore.QLineF(wall.parentWall.firstVertex, wall.parentWall.secondVertex).length() / 1000
                if fieldName == "doorSize":
                    minimum /= 2
                    maximum /= 2
                spinBox.setRange(minimum, max(minimum, maximum))
            spinBox.setValue(value / (1.0 if fieldName in ("miter", "stepCount", "angle") else 10.0 if fieldName in ("sillDepth", "wellDepth", "stepSize") or fieldName == "width" and not isStair or fieldName == "length" and isFurnishing else 1000.0))
            del blocker
        if len(entries) > 1:
            objects = list({id(obj): obj for obj, index in entries}.values())
            if isFurnishing and len({furnishingNames[id(obj)] for obj in objects}) > 1:
                objectType = "Furnishing"
            self.selectionLabel.setText(f"{len(objects)} {objectType}s selected" if len(objects) > 1 else
                                        f"{objectType} (#{objects[0].objectId:04d})")
            if len(objects) > 1 and isFurnishing and len({furnishingNames[id(obj)] for obj in objects}) == 1 and missingFurnishings:
                self.selectionLabel.setText(f"{len(objects)} {objectType} objects selected")
            vertices = [(obj, index) for obj, index in entries if index is not None]
            self.vertexProperties.setVisible(bool(vertices))
            self.vertexSpacing.setVisible(bool(vertices))
            if vertices:
                self.vertexProperties.setTitle(f"Selected points ({len(vertices)})")
            for fieldName, spinBox in self.propertyFields.items():
                propertyValues = []
                if fieldName in ("x", "y", "miter"):
                    for obj, index in vertices:
                        if fieldName == "miter" and not hasattr(obj, "firstMiter"):
                            continue
                        vertex = obj.firstVertex if index == 0 else obj.secondVertex
                        propertyValues.append(vertex.x() / 1000 if fieldName == "x" else vertex.y() / 1000 if fieldName == "y" else
                                              obj.firstMiter if index == 0 else obj.secondMiter)
                elif fieldName == "angle" and (isFurnishing or isPillar):
                    propertyValues = [obj.angle for obj in objects]
                elif fieldName == "sillDepth" and isSilledWindow:
                    propertyValues = [obj.sillDepth / 10 for obj in objects]
                elif fieldName == "wellDepth" and hasWell:
                    propertyValues = [obj.wellDepth / 10 for obj in objects]
                elif fieldName in ("stepCount", "stepSize") and hasSizing:
                    propertyValues = [(obj.postCount if isinstance(obj, Railing) else obj.stepCount) if fieldName == "stepCount" else (obj.segmentWidth if isinstance(obj, Railing) else obj.stepSize) / 10 for obj in objects]
                elif fieldName in ("width", "length", "doorSize"):
                    for obj in objects:
                        propertyValues.append((obj.depth / 10 if fieldName == "width" else obj.length / 1000) if isinstance(obj, Fireplace) else
                                              obj.width / (1000 if isStair else 10) if fieldName == "width" else
                                              obj.length / 2000 if fieldName == "doorSize" and isinstance(obj, Window) else
                                              QtCore.QLineF(obj.firstVertex, obj.secondVertex).length() / (10 if isFurnishing else 1000))
                if propertyValues:
                    blocker = QtCore.QSignalBlocker(spinBox)
                    if fieldName == "width" and isinstance(wall, Fireplace):
                        spinBox.setMinimum(max(obj.parentWall.width for obj in objects) / 10)
                    if fieldName in ("length", "doorSize"):
                        minimum = max(.001, max((self.viewport.MinimumOpeningLength(obj) / 1000 for obj in objects), default = .001)) if not isWindow else .001
                        maximum = min(((1 - obj.firstFraction) * QtCore.QLineF(obj.parentWall.firstVertex, obj.parentWall.secondVertex).length() / 1000
                                       for obj in objects), default = 1e9) if isWindow else 1e9
                        if isFurnishing:
                            minimum = .1
                        if isinstance(wall, Fireplace):
                            minimum, maximum = .001, min(QtCore.QLineF(obj.parentWall.firstVertex, obj.parentWall.secondVertex).length() for obj in objects) / 1000
                        if fieldName == "doorSize":
                            minimum /= 2
                            maximum /= 2
                        spinBox.setRange(minimum, max(minimum, maximum))
                    common = all(math.isclose(value, propertyValues[0], abs_tol = 1e-6) for value in propertyValues)
                    spinBox.commonSuffix = spinBox.suffix()
                    spinBox.mixedEdited = False
                    spinBox.mixedValue = not common
                    if not common:
                        # A suffix keeps the editor nonempty and hides its placeholder.
                        spinBox.setSuffix("")
                    spinBox.setValue(propertyValues[0])
                    spinBox.lineEdit().setPlaceholderText("(different)" if not common else "")
                    if not common:
                        spinBox.lineEdit().clear()
                    del blocker
            if isinstance(wall, Fireplace) or not isWindow and not isStair and not isFurnishing:
                blocker = QtCore.QSignalBlocker(self.materialField)
                materials = {obj.material for obj in objects}
                self.materialField.setPlaceholderText("(different)")
                self.materialField.setCurrentIndex(self.materialField.findText(next(iter(materials))) if len(materials) == 1 else -1)
                del blocker
            if hasSizing:
                counts = {(obj.postCount if isinstance(obj, Railing) else obj.stepCount) for obj in objects}
                sizes = {round((obj.segmentWidth if isinstance(obj, Railing) else obj.stepSize) / 10, 2) for obj in objects}
                self.stepCountLabel.setText(str(next(iter(counts))) if len(counts) == 1 else "(different)")
                self.stepSizeLabel.setText(f"{next(iter(sizes)):.2f} cm" if len(sizes) == 1 else "(different)")
        else:
            for spinBox in self.propertyFields.values():
                spinBox.mixedValue = False
                spinBox.lineEdit().setPlaceholderText("")
        if self.viewport.unitsMode != "Adaptive Metric":
            for fieldName, field in self.propertyFields.items():
                if fieldName in ("angle", "miter", "stepCount"):
                    continue
                oldDivisor, unused = PropertyUnit(fieldName, wall, "Adaptive Metric")
                divisor, unit = PropertyUnit(fieldName, wall, self.viewport.unitsMode)
                factor = oldDivisor / divisor
                value, minimum, maximum, step = field.value(), field.minimum(), field.maximum(), field.singleStep()
                blocker = QtCore.QSignalBlocker(field)
                if unit == "mm":
                    field.setDecimals(0)
                elif fieldName == "stepSize" and unit == "m":
                    field.setDecimals(4)
                field.setRange(minimum * factor, maximum * factor)
                field.setSingleStep(step * factor)
                field.commonSuffix = " " + unit
                field.setSuffix("" if field.mixedValue else field.commonSuffix)
                field.setValue(value * factor)
                if field.mixedValue:
                    field.lineEdit().clear()
                del blocker
            if hasSizing:
                sizes = {round((obj.segmentWidth if isinstance(obj, Railing) else obj.stepSize), 6) for obj, index in entries}
                self.stepSizeLabel.setText(FormatLength(next(iter(sizes)), self.viewport.unitsMode, "cm", 4) if len(sizes) == 1 else "(different)")
        # These are separate forms, but their fields form one visual column.
        visibleLabels = []
        for panel in (self.wallProperties, self.doorProperties):
            form = panel.layout()
            for row in range(form.rowCount()):
                item = form.itemAt(row, QtWidgets.QFormLayout.ItemRole.LabelRole)
                label = item.widget() if item is not None else None
                if label is not None:
                    label.setMinimumWidth(0)
                    if not panel.isHidden() and form.isRowVisible(row):
                        visibleLabels.append(label)
        columnWidth = max((label.sizeHint().width() for label in visibleLabels), default = 0)
        for label in visibleLabels:
            label.setMinimumWidth(columnWidth)

    def EditSelectionProperty(self, callback, *arguments):
        entries = self.viewport.SelectionEntries()
        if len(entries) <= 1:
            return False
        if len({Wall if type(obj) in (Wall, Pillar, Column) else type(obj) for obj, index in entries}) > 1:
            return True
        fieldName = arguments[0] if callback.__name__ == "EditProperty" else None
        if fieldName in ("x", "y", "miter"):
            targets = [(obj, index) for obj, index in entries if index is not None]
        else:
            targets = list({id(obj): (obj, index) for obj, index in entries}.values())
        before = self.viewport.CaptureState()
        primary = self.viewport.selectedWall, self.viewport.selectedVertex
        self.bulkPropertyEdit = True
        validTargets = True
        try:
            for obj, index in targets:
                self.viewport.selectedWall, self.viewport.selectedVertex = obj, index
                validTargets = callback(*arguments) is not False and validTargets
        finally:
            self.bulkPropertyEdit = False
            self.viewport.selectedWall, self.viewport.selectedVertex = primary
        valid = self.viewport.OpeningsValid() if all(isinstance(obj, Window) for obj, index in targets) else self.viewport.FitWallOpenings(before)
        valid = valid and validTargets
        if fieldName is not None:
            requested = arguments[1]
            for obj, index in targets:
                if fieldName in ("length", "doorSize"):
                    actual = QtCore.QLineF(obj.firstVertex, obj.secondVertex).length() / (2000 if fieldName == "doorSize" else 10 if isinstance(obj, Furnishing) else 1000)
                elif fieldName == "width":
                    actual = obj.depth / 10 if isinstance(obj, Fireplace) else obj.width / (1000 if isinstance(obj, Stair) else 10)
                elif fieldName == "miter":
                    actual = obj.firstMiter if index == 0 else obj.secondMiter
                elif fieldName in ("x", "y"):
                    vertex = obj.firstVertex if index == 0 else obj.secondVertex
                    actual = (vertex.x() if fieldName == "x" else vertex.y()) / 1000
                else:
                    continue
                if fieldName != "miter":
                    oldDivisor, unused = PropertyUnit(fieldName, obj, "Adaptive Metric")
                    divisor, unused = PropertyUnit(fieldName, obj, self.viewport.unitsMode)
                    actual *= oldDivisor / divisor
                if not math.isclose(actual, requested, abs_tol = 1e-6):
                    valid = False
                    break
        if not valid:
            self.viewport.RestoreState(before)
        elif self.propertyDragBefore is None:
            self.viewport.RecordEdit(before)
        self.viewport.update()
        self.RefreshProperties()
        return True

    def EditStairAutosize(self, enabled):
        if not self.bulkPropertyEdit and self.EditSelectionProperty(self.EditStairAutosize, enabled):
            return
        stair = self.viewport.selectedWall
        if not isinstance(stair, (Stair, Railing)) or stair.autosize == enabled:
            return
        before = self.viewport.CaptureState()
        stair.SetAutosize(enabled)
        if not self.bulkPropertyEdit:
            self.viewport.RecordEdit(before)
            self.RefreshProperties()
            self.viewport.update()

    def EditMaterial(self, material):
        if not self.bulkPropertyEdit and self.EditSelectionProperty(self.EditMaterial, material):
            return
        wall = self.viewport.selectedWall
        if type(wall) not in (Wall, Pillar, Column, Fireplace) or material not in wallMaterials or wall.material == material:
            return
        before = self.viewport.CaptureState()
        wall.material = material
        if not self.bulkPropertyEdit:
            self.viewport.RecordEdit(before)
        self.viewport.update()

    def EditFurnishingFlip(self, fieldName):
        objects = list({id(obj): obj for obj, index in self.viewport.SelectionEntries()}.values())
        if fieldName not in self.furnishingFlipFields or not objects:
            return
        self.viewport.ApplyObjectContextAction(objects, fieldName)

    def FlipStairDirection(self):
        if not self.bulkPropertyEdit and self.EditSelectionProperty(self.FlipStairDirection):
            return
        stair = self.viewport.selectedWall
        if isinstance(stair, Stair):
            before = self.viewport.CaptureState()
            stair.directionReversed = not stair.directionReversed
            if not self.bulkPropertyEdit:
                self.viewport.RecordEdit(before)
                self.RefreshProperties()
            self.viewport.update()

    def BeginPropertyDrag(self):
        self.propertyDragBefore = self.viewport.CaptureState()
        self.propertyDragPivotBefore = QtCore.QPointF(self.viewport.rotationPivot) if self.viewport.rotationPivot is not None else None
        self.propertyDragRotationBefore = self.viewport.furnishingRotationObject

    def FinishPropertyDrag(self, canceled):
        if self.propertyDragBefore is not None:
            if canceled:
                self.viewport.RestoreState(self.propertyDragBefore)
                self.viewport.rotationPivot = self.propertyDragPivotBefore
                self.viewport.furnishingRotationObject = self.propertyDragRotationBefore
            else:
                self.viewport.RecordEdit(self.propertyDragBefore)
            self.propertyDragBefore = None
            self.viewport.update()
            self.RefreshProperties()

    def ApplySizeProperty(self, wall, fieldName, millimeters):
        if isinstance(wall, Fireplace):
            if fieldName == "length":
                wall.length = millimeters
                wall.SetCenter((wall.firstVertex + wall.secondVertex) / 2 + wall.Axes()[1] * wall.depthOffset)
            else:
                wall.depth = millimeters
                wall.depthOffset = wall.depthOffset
        elif fieldName == "width":
            wall.width = millimeters
        else:
            millimeters = max(millimeters, self.viewport.MinimumOpeningLength(wall))
            direction = wall.secondVertex - wall.firstVertex
            oldLength = math.hypot(direction.x(), direction.y())
            if oldLength > 0:
                if isinstance(wall, Pillar):
                    center = (wall.firstVertex + wall.secondVertex) / 2
                    halfAxis = direction * (millimeters / oldLength / 2)
                    wall.firstVertex, wall.secondVertex = center - halfAxis, center + halfAxis
                else:
                    wall.secondVertex = wall.firstVertex + direction * (millimeters / oldLength)
            else:
                wall.secondVertex = wall.firstVertex + QtCore.QPointF(millimeters, 0)
            self.viewport.PropagateMiter(wall, 1)

    def EditProperty(self, fieldName, value):
        entries = self.viewport.SelectionEntries()
        if fieldName in ("x", "y") and entries and all(isinstance(obj, AngleGuide) for obj, index in entries):
            divisor, unused = PropertyUnit(fieldName, entries[0][0], self.viewport.unitsMode)
            before = self.viewport.CaptureState()
            for obj, index in entries:
                if index not in (0, 1):
                    continue
                position = QtCore.QPointF(ObjectControlPoints(obj)[index])
                if fieldName == "x":
                    position.setX(value * divisor)
                else:
                    position.setY(value * divisor)
                SetControlPoint(obj, index, position)
            if self.propertyDragBefore is None:
                self.viewport.RecordEdit(before)
            self.viewport.update()
            self.RefreshProperties()
            return
        if not self.bulkPropertyEdit and self.EditSelectionProperty(self.EditProperty, fieldName, value):
            return
        wall = self.viewport.selectedWall
        if wall is None:
            return
        if fieldName not in ("miter", "angle", "stepCount"):
            divisor, unused = PropertyUnit(fieldName, wall, self.viewport.unitsMode)
            oldDivisor, unused = PropertyUnit(fieldName, wall, "Adaptive Metric")
            value *= divisor / oldDivisor
        if fieldName in ("stepCount", "stepSize"):
            if not isinstance(wall, (Stair, Railing)) or wall.autosize:
                return
            before = self.viewport.CaptureState()
            if fieldName == "stepCount":
                if isinstance(wall, Railing):
                    wall.SetPostCount(value)
                else:
                    wall.SetStepCount(value)
            else:
                if isinstance(wall, Railing):
                    wall.SetSegmentWidth(value * 10)
                else:
                    wall.SetStepSize(value * 10)
            if self.propertyDragBefore is None and not self.bulkPropertyEdit:
                self.viewport.RecordEdit(before)
            self.viewport.update()
            self.RefreshProperties()
            return
        before = self.viewport.CaptureState()
        millimeters = value * (10.0 if fieldName in ("sillDepth", "wellDepth") or fieldName == "width" and not isinstance(wall, Stair) or fieldName == "length" and isinstance(wall, Furnishing) else 1000.0)
        if fieldName == "doorSize" and isinstance(wall, (SlidingDoor, PocketDoor)):
            millimeters *= 2
        sizeValid = True
        if fieldName in ("width", "length") and (not isinstance(wall, Window) or isinstance(wall, Fireplace)):
            if self.sizeLinkButton.isChecked():
                oldWidth = wall.depth if isinstance(wall, Fireplace) else wall.width
                oldLength = QtCore.QLineF(wall.firstVertex, wall.secondVertex).length()
                original = oldWidth if fieldName == "width" else oldLength
                if min(oldWidth, oldLength) <= 0:
                    self.RefreshProperties()
                    return False
                factor = millimeters / original
                width, length = oldWidth * factor, oldLength * factor
                self.ApplySizeProperty(wall, "width", width)
                self.ApplySizeProperty(wall, "length", length)
                actualWidth = wall.depth if isinstance(wall, Fireplace) else wall.width
                sizeValid = (math.isclose(actualWidth, width, abs_tol = 1e-6)
                             and math.isclose(QtCore.QLineF(wall.firstVertex, wall.secondVertex).length(), length, abs_tol = 1e-6))
            else:
                self.ApplySizeProperty(wall, fieldName, millimeters)
        elif fieldName == "angle" and isinstance(wall, (Furnishing, Pillar)):
            wall.angle = value
        elif isinstance(wall, Fireplace):
            pass
        elif isinstance(wall, Window):
            if fieldName == "sillDepth" and isinstance(wall, SilledWindow):
                wall.sillDepth = max(0.0, millimeters)
            elif fieldName == "wellDepth" and type(wall) in (Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow):
                wall.wellDepth = max(1.0, millimeters)
            elif fieldName in ("length", "doorSize"):
                direction = wall.parentWall.secondVertex - wall.parentWall.firstVertex
                parentLength = math.hypot(direction.x(), direction.y())
                if parentLength > 1e-10:
                    self.viewport.SetOpeningVertex(wall, 1, wall.firstVertex + direction * (millimeters / parentLength))
            elif fieldName in ("x", "y") and self.viewport.selectedVertex is not None:
                position = wall.firstVertex if self.viewport.selectedVertex == 0 else wall.secondVertex
                if fieldName == "x":
                    position.setX(millimeters)
                else:
                    position.setY(millimeters)
                self.viewport.SetOpeningVertex(wall, self.viewport.selectedVertex, position)
        elif fieldName == "miter" and self.viewport.selectedVertex is not None:
            if self.viewport.selectedVertex == 0:
                wall.firstMiter = max(0.0, min(1.0, value))
            else:
                wall.secondMiter = max(0.0, min(1.0, value))
            self.viewport.PropagateMiter(wall, self.viewport.selectedVertex)
        elif self.viewport.selectedVertex is not None:
            vertex = wall.firstVertex if self.viewport.selectedVertex == 0 else wall.secondVertex
            if fieldName == "x":
                vertex.setX(millimeters)
            else:
                vertex.setY(millimeters)
            self.viewport.PropagateMiter(wall, self.viewport.selectedVertex)
        if not sizeValid:
            if not self.bulkPropertyEdit:
                self.viewport.RestoreState(before)
                self.RefreshProperties()
            return False
        if not self.bulkPropertyEdit and not (self.viewport.OpeningsValid() if isinstance(wall, Window) else self.viewport.FitWallOpenings(before)):
            self.viewport.RestoreState(before)
            return
        if self.propertyDragBefore is None and not self.bulkPropertyEdit:
            self.viewport.RecordEdit(before)
        self.viewport.update()
        self.RefreshProperties()

    def EditWindowWell(self, fieldName, enabled):
        if fieldName not in ("windowWell", "wellDashed"):
            return
        before = self.viewport.CaptureState()
        for obj, index in self.viewport.SelectionEntries():
            if type(obj) in (Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow):
                setattr(obj, fieldName, enabled)
        self.viewport.RecordEdit(before)
        self.viewport.update()
        self.RefreshProperties()

    def EditDoorProperty(self, fieldName):
        if not self.bulkPropertyEdit and self.EditSelectionProperty(self.EditDoorProperty, fieldName):
            return
        door = self.viewport.selectedWall
        if not isinstance(door, Window):
            return
        before = self.viewport.CaptureState()
        if fieldName == "measurement":
            measurementClass = "windows" if type(door) in (Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow) else "doors"
            if (type(door) not in (Door, DoubleDoor, SlidingDoor, BarnDoor, Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow)
                    or self.viewport.measurementSettings[measurementClass] != 1):
                return
            door.measurementFlipped = not door.measurementFlipped
        elif fieldName == "swing" and type(door) in (Window, Door, DoubleDoor, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, BarnDoor, BifoldDoor, Fireplace):
            door.swingsOutwards = not door.swingsOutwards
        elif fieldName == "swing" and isinstance(door, SlidingDoor):
            door.panelsFlipped = not door.panelsFlipped
        elif fieldName == "hinge" and isinstance(door, (Door, SwingingDoor, SlidingDoor, PocketDoor, CasementWindow)):
            door.hingeAtSecond = not door.hingeAtSecond
        else:
            return
        if not self.bulkPropertyEdit:
            self.viewport.RecordEdit(before)
        self.viewport.update()
        self.RefreshProperties()
