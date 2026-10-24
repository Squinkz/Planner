"""Arrow appearance and dimension controls, including mixed selections."""
import math
from PySide6 import QtCore, QtWidgets
from planner_app.models import Arrow, MeasurementGuide, ObjectControlPoints
from planner_app.units import MetricUnit
from planner_app.graphics.icons import UiIcon
from .widgets import DragSpinBox, DragSlider


class ArrowPropertiesMixin:
    def BuildArrowProperties(self, layout, rowHeight = 32):
        self.arrowProperties = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(self.arrowProperties)
        form.setContentsMargins(0, 16, 0, 0)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        self.arrowFields = {}
        for name, label in (("length", "Length"), ("solidTip", "Solid tip"),
                            ("tipSize", "Tip size"), ("width", "Tail thickness"), ("intensity", "Intensity")):
            if name == "solidTip":
                control = QtWidgets.QCheckBox()
                control.stateChanged.connect(lambda state: self.EditArrowProperty("solidTip", state == QtCore.Qt.CheckState.Checked.value))
            elif name == "intensity":
                control = DragSlider(QtCore.Qt.Orientation.Horizontal)
                control.setRange(0, 100)
                control.sliderPressed.connect(self.BeginPropertyDrag)
                control.sliderReleased.connect(lambda: self.FinishPropertyDrag(False))
                control.valueChanged.connect(lambda value: self.EditArrowProperty("intensity", value / 100))
                control.setToolTip("Controls arrow opacity: 0 is invisible and 1 is fully opaque")
            else:
                control = DragSpinBox()
                control.setKeyboardTracking(False)
                control.dragStarted.connect(self.BeginPropertyDrag)
                control.dragFinished.connect(self.FinishPropertyDrag)
                control.valueChanged.connect(lambda value, name = name: self.EditArrowProperty(name, value))
                control.editingFinished.connect(lambda name = name, control = control:
                    self.EditArrowProperty(name, control.value()) if control.mixedValue and control.mixedEdited else None)
            control.setMinimumHeight(rowHeight)
            if name == "intensity":
                row = QtWidgets.QWidget()
                row.setMinimumHeight(rowHeight)
                rowLayout = QtWidgets.QHBoxLayout(row)
                rowLayout.setContentsMargins(0, 0, 0, 0)
                rowLayout.setSpacing(10)
                opacityIcon = QtWidgets.QLabel()
                opacityIcon.setPixmap(UiIcon("opacity").pixmap(24, 24))
                opacityIcon.setToolTip("Opacity")
                opacityIcon.setAccessibleName("Opacity")
                rowLayout.addWidget(opacityIcon)
                control.setAccessibleName("Arrow opacity")
                self.arrowIntensityValue = QtWidgets.QLabel("1.00")
                rowLayout.addWidget(control, 1)
                rowLayout.addWidget(self.arrowIntensityValue)
                form.addRow(row)
            else:
                form.addRow(label, control)
            self.arrowFields[name] = control
        layout.addWidget(self.arrowProperties)
        self.arrowProperties.hide()

    def RefreshArrowProperties(self, entries):
        arrows = list({id(obj): obj for obj, index in entries}.values())
        enabled = bool(arrows) and all(isinstance(obj, (Arrow, MeasurementGuide)) and type(obj) is type(arrows[0]) for obj in arrows)
        self.arrowProperties.setVisible(enabled)
        if not enabled:
            return False
        self.wallProperties.hide()
        self.doorProperties.hide()
        guide = isinstance(arrows[0], MeasurementGuide)
        name = "Measurement guide" if guide else "Arrow"
        self.selectionLabel.setText(f"{name} (#{arrows[0].objectId:04d})" if len(arrows) == 1 else f"{len(arrows)} {name.lower()}s selected")
        for fieldName, field in self.arrowFields.items():
            row = self.arrowIntensityValue.parentWidget() if fieldName == "intensity" else field
            self.arrowProperties.layout().setRowVisible(row, not guide or fieldName == "length")
        self.RefreshGuidePointProperties(entries)
        for name, control in self.arrowFields.items():
            if guide and name != "length":
                continue
            values = [QtCore.QLineF(obj.firstVertex, obj.secondVertex).length() if name == "length" else getattr(obj, name) for obj in arrows]
            blocker = QtCore.QSignalBlocker(control)
            mixed = not all(math.isclose(value, values[0], abs_tol = 1e-6) for value in values)
            if name == "solidTip":
                control.setTristate(mixed)
                control.setCheckState(QtCore.Qt.CheckState.PartiallyChecked if mixed else
                                      QtCore.Qt.CheckState.Checked if values[0] else QtCore.Qt.CheckState.Unchecked)
            elif name == "intensity":
                control.setValue(round(values[0] * 100))
                self.arrowIntensityValue.setText("(different)" if mixed else f"{values[0]:.2f}")
            else:
                divisor, unit = MetricUnit(self.viewport.unitsMode, "m" if name == "length" else "mm")
                control.setDecimals(0 if unit == "mm" else 3)
                control.setRange(1 / divisor, 1e9 / divisor)
                control.setSingleStep(10 / divisor if name == "length" else 1 / divisor)
                control.mixedValue = mixed
                control.mixedEdited = False
                control.commonSuffix = " " + unit
                control.setSuffix("" if mixed else control.commonSuffix)
                control.setValue(values[0] / divisor)
                control.lineEdit().setPlaceholderText("(different)" if mixed else "")
                if mixed:
                    control.lineEdit().clear()
                if name == "tipSize":
                    control.setToolTip("Sets a fixed head width for solid and open tips, independent of tail thickness")
            del blocker
        return True

    def RefreshGuidePointProperties(self, entries):
        vertices = [(obj, index) for obj, index in entries if index is not None and index < len(ObjectControlPoints(obj))]
        self.vertexProperties.setVisible(bool(vertices))
        self.vertexSpacing.setVisible(bool(vertices))
        self.vertexProperties.layout().setRowVisible(self.propertyFields["miter"], False)
        if vertices:
            self.vertexProperties.setTitle(f"Point {vertices[0][1] + 1}" if len(vertices) == 1 else f"Selected points ({len(vertices)})")
            divisor, unit = MetricUnit(self.viewport.unitsMode)
            for name in ("x", "y"):
                values = [getattr(ObjectControlPoints(obj)[index], name)() for obj, index in vertices]
                control = self.propertyFields[name]
                blocker = QtCore.QSignalBlocker(control)
                control.setDecimals(0 if unit == "mm" else 3)
                control.setRange(-1e9, 1e9)
                control.mixedValue = not all(math.isclose(value, values[0], abs_tol = 1e-6) for value in values)
                control.mixedEdited = False
                control.commonSuffix = " " + unit
                control.setSuffix("" if control.mixedValue else control.commonSuffix)
                control.setValue(values[0] / divisor)
                control.lineEdit().setPlaceholderText("(different)" if control.mixedValue else "")
                if control.mixedValue:
                    control.lineEdit().clear()
                del blocker

    def EditArrowProperty(self, name, value):
        arrows = list({id(obj): obj for obj, index in self.viewport.SelectionEntries()}.values())
        if not arrows or any(not isinstance(obj, (Arrow, MeasurementGuide)) for obj in arrows):
            return
        before = self.viewport.CaptureState()
        for arrow in arrows:
            converted = value
            if name in ("length", "width", "tipSize"):
                divisor, unit = MetricUnit(self.viewport.unitsMode, "m" if name == "length" else "mm")
                converted *= divisor
            if name == "length":
                run = arrow.secondVertex - arrow.firstVertex
                length = QtCore.QLineF(arrow.firstVertex, arrow.secondVertex).length()
                if length > 0:
                    arrow.secondVertex = arrow.firstVertex + run * (max(1, converted) / length)
            else:
                setattr(arrow, name, converted)
        if self.propertyDragBefore is None:
            self.viewport.RecordEdit(before)
        self.viewport.update()
        self.RefreshProperties()
