"""Angle Guide identity and numeric angle edits, including mixed selections."""
import math
from PySide6 import QtCore, QtWidgets
from planner_app.models import AngleGuide
from .widgets import DragSpinBox


class AnglePropertiesMixin:
    def BuildAngleProperties(self, layout):
        self.angleGuideProperties = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(self.angleGuideProperties)
        form.setContentsMargins(0, 16, 0, 0)
        form.setHorizontalSpacing(16)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        self.angleGuidePositionRow, self.angleGuidePositionFields = self.BuildPositionFields(form)
        control = self.angleGuideAngleField = DragSpinBox()
        control.setRange(0, 180)
        control.setDecimals(1)
        control.setSingleStep(1)
        control.setSuffix("°")
        control.commonSuffix = "°"
        control.setKeyboardTracking(False)
        control.setMinimumHeight(32)
        control.angleEdited = False
        control.setToolTip("Equalize both arms to the shorter length, then rotate the arm farther from north (+Y). Ties rotate the last arm.")
        control.dragStarted.connect(self.BeginPropertyDrag)
        control.dragFinished.connect(self.FinishPropertyDrag)
        control.valueChanged.connect(self.EditAngleGuideAngle)
        control.lineEdit().textEdited.connect(lambda: setattr(control, "angleEdited", True))
        control.editingFinished.connect(lambda: self.EditAngleGuideAngle(control.value()) if control.angleEdited else None)
        form.addRow("Angle", control)
        layout.addWidget(self.angleGuideProperties)
        self.angleGuideProperties.hide()

    def RefreshAngleProperties(self, entries):
        guides = list({id(obj): obj for obj, index in entries}.values())
        enabled = bool(guides) and all(isinstance(obj, AngleGuide) for obj in guides)
        self.angleGuideProperties.setVisible(enabled)
        if not enabled:
            return False
        self.wallProperties.hide()
        self.doorProperties.hide()
        self.arrowProperties.hide()
        self.RefreshPositionFields(self.angleGuidePositionFields, guides)
        self.RefreshGuidePointProperties([(obj, index) for obj, index in entries if index in (0, 1)])
        self.selectionLabel.setText(f"Angle Guide (#{guides[0].objectId:04d})" if len(guides) == 1 else f"{len(guides)} Angle Guides selected")
        values = [obj.angle for obj in guides]
        defined = all(value is not None for value in values)
        mixed = defined and not all(math.isclose(value, values[0], abs_tol = 1e-6) for value in values)
        control = self.angleGuideAngleField
        blocker = QtCore.QSignalBlocker(control)
        control.setEnabled(defined)
        control.mixedValue, control.mixedEdited = mixed, False
        control.setSuffix("" if mixed or not defined else "°")
        control.setValue(values[0] if defined else 0)
        control.lineEdit().setPlaceholderText("(different)" if mixed else "Undefined" if not defined else "")
        if mixed or not defined:
            control.lineEdit().clear()
        del blocker
        return True

    def EditAngleGuideAngle(self, degrees):
        guides = list({id(obj): obj for obj, index in self.viewport.SelectionEntries()}.values())
        if not guides or any(not isinstance(obj, AngleGuide) for obj in guides):
            return
        before = self.viewport.CaptureState()
        # A property drag keeps its original pivot arm and side even when the
        # moving arm passes north, or the angle reaches zero or 180 degrees.
        reference = self.propertyDragBefore if self.propertyDragBefore is not None else before
        states = {id(entry[0]): entry for entry in reference[0]}
        for guide in guides:
            entry = states[id(guide)]
            middle = QtCore.QPointF(*entry[10][:2])
            arms = QtCore.QPointF(entry[1], entry[2]) - middle, QtCore.QPointF(entry[3], entry[4]) - middle
            guide.SetAngle(degrees, arms = arms)
        self.angleGuideAngleField.angleEdited = False
        if self.propertyDragBefore is None:
            self.viewport.RecordEdit(before)
        self.viewport.update()
        self.RefreshProperties()
