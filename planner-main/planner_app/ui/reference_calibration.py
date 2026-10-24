"""Temporary two-point reference-image calibration and a one-use unit choice."""
import math
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.icons import UiIcon
from planner_app.graphics.palette import themeColors
from planner_app.units import FormatLength, MetricUnit, unitModes
from planner_app.models import MeasurementGuide
from .widgets import DownwardComboBox, UnitSpinBox


class CalibrationDistanceDialog(QtWidgets.QDialog):
    def __init__(self, calibration):
        super().__init__(calibration.reference.mainWindow)
        self.calibration = calibration
        self.setWindowTitle("Calibrate Reference Image")
        self.setWindowIcon(UiIcon("measure"))
        self.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        layout = QtWidgets.QVBoxLayout(self)
        explanation = QtWidgets.QLabel("Enter the actual distance between the two points.")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        form = QtWidgets.QFormLayout()
        self.distanceField = UnitSpinBox()
        self.distanceField.setObjectName("settingsValue")
        self.distanceField.setAccessibleName("Actual distance")
        self.distanceField.setKeyboardTracking(False)
        self.unitsField = DownwardComboBox()
        self.unitsField.setAccessibleName("Calibration units")
        labels = {"Meters": "m", "Centimeters": "cm", "Millimeters": "mm",
                  "Feet and Inches": "ft / in", "Inches": "in"}
        for mode in unitModes:
            if mode == "Adaptive Metric":
                continue
            self.unitsField.addItem(labels[mode], mode)
            self.unitsField.setItemData(self.unitsField.count() - 1, mode, QtCore.Qt.ItemDataRole.ToolTipRole)
        mode = calibration.reference.viewport.unitsMode
        if mode == "Adaptive Metric":
            mode = "Meters"
        self.unitsField.setCurrentIndex(self.unitsField.findData(mode))
        self.divisor, unit = MetricUnit(mode)
        self.distanceField.setDecimals(6)
        self.distanceField.setRange(0, 1e12 / self.divisor)
        self.distanceField.setSuffix(" " + unit)
        # The adjacent selector supplies units; keep UnitSpinBox's imperial parsing.
        QtWidgets.QDoubleSpinBox.setSuffix(self.distanceField, "")
        self.distanceField.setValue(QtCore.QLineF(*calibration.points).length() / self.divisor)
        self.unitsField.currentIndexChanged.connect(lambda index: self.ChangeUnits(self.unitsField.itemData(index)))
        distanceRow = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(distanceRow)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.unitsField.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        row.addWidget(self.distanceField, 1)
        row.addWidget(self.unitsField, 0, QtCore.Qt.AlignmentFlag.AlignRight)
        form.addRow("Distance", distanceRow)
        layout.addLayout(form)
        self.errorLabel = QtWidgets.QLabel()
        self.errorLabel.setWordWrap(True)
        self.errorLabel.setStyleSheet("color: " + themeColors["error"] + ";")
        self.errorLabel.hide()
        layout.addWidget(self.errorLabel)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok |
                                            QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        available = self.screen().availableGeometry()
        self.setMinimumWidth(min(440, available.width()))
        self.resize(self.minimumWidth(), self.sizeHint().height())
        self.distanceField.selectAll()
        self.distanceField.setFocus()

    def ChangeUnits(self, mode):
        self.distanceField.interpretText()
        distance = self.distanceField.value() * self.divisor
        self.divisor, unit = MetricUnit(mode)
        self.distanceField.setDecimals(6)
        self.distanceField.setRange(0, 1e12 / self.divisor)
        self.distanceField.setSuffix(" " + unit)
        QtWidgets.QDoubleSpinBox.setSuffix(self.distanceField, "")
        self.distanceField.setValue(distance / self.divisor)

    def accept(self):
        self.distanceField.interpretText()
        error = self.calibration.Apply(self.distanceField.value() * self.divisor)
        if error:
            self.errorLabel.setText(error)
            self.errorLabel.show()
            return
        super().accept()


class ReferenceCalibration:
    def __init__(self, reference):
        self.reference = reference
        self.active = False
        self.points = []
        self.hover = None
        self.draggedPoint = None
        self.dragBefore = None
        self.dragStart = None
        self.placementPress = None
        self.dialog = None

    def Start(self):
        reference = self.reference
        if not reference.active or not reference.state or not reference.state["visible"]:
            return
        reference.CancelDrag()
        reference.FinishPropertyDrag(True)
        self.Stop()
        self.active = True
        reference.panel.setEnabled(False)
        reference.viewport.setFocus()
        reference.viewport.UpdateCanvasCursor()
        reference.viewport.update()

    def Stop(self):
        self.active = False
        self.points = []
        self.hover = None
        if self.draggedPoint is not None or self.placementPress is not None:
            self.reference.viewport.releaseMouse()
        self.placementPress = None
        self.draggedPoint = None
        self.dragBefore = None
        self.dragStart = None
        self.reference.viewport.alignmentGuides = []
        self.reference.viewport.axisConstraintOrigin = None
        self.reference.viewport.axisConstraintDirection = None
        if self.dialog is not None:
            self.dialog.reject()
        self.reference.panel.setEnabled(True)
        self.reference.viewport.UpdateCanvasCursor()
        self.reference.viewport.update()

    def Confirm(self):
        if len(self.points) != 2 or QtCore.QLineF(*self.points).length() <= 1e-6 or self.dialog is not None:
            return
        self.dialog = CalibrationDistanceDialog(self)
        self.dialog.finished.connect(self.DialogFinished)
        self.dialog.open()

    def DialogFinished(self, result):
        dialog, self.dialog = self.dialog, None
        if dialog is not None:
            dialog.deleteLater()
        if result == QtWidgets.QDialog.DialogCode.Accepted:
            self.Stop()
        elif self.active:
            self.reference.viewport.setFocus()
            self.reference.viewport.update()

    def Apply(self, distance):
        if not self.active or len(self.points) != 2:
            return "Choose two points before setting the distance."
        measured = QtCore.QLineF(*self.points).length()
        if not math.isfinite(distance) or distance <= 0 or measured <= 1e-6:
            return "Enter a distance greater than zero."
        reference = self.reference
        factor = distance / measured
        # Keep the first picked point fixed while uniformly scaling the image.
        anchor = self.points[0]
        center = anchor + (QtCore.QPointF(*reference.state["center"]) - anchor) * factor
        width, height = reference.state["width"] * factor, reference.state["height"] * factor
        values = (center.x(), center.y(), width, height)
        if any(not math.isfinite(value) or abs(value) > 1e12 for value in values) or min(width, height) < 1:
            return "That distance would make the reference image too small or too large."
        reference.state.update(center = [center.x(), center.y()], width = width, height = height)
        if reference.pivot is not None:
            reference.pivot = anchor + (reference.pivot - anchor) * factor
        reference.SyncProperties()
        reference.Changed()
        return None

    def HitPoint(self, position):
        v = self.reference.viewport
        if position is None or not v.DrawingRect().contains(position):
            return None
        return next((index for index, point in enumerate(self.points)
                     if QtCore.QLineF(v.WorldToViewport(point), position).length() <= 9), None)

    def UpdatePoint(self, modifiers):
        v = self.reference.viewport
        original = self.dragBefore
        guide = MeasurementGuide(original[0], original[1] if len(original) == 2 else original[0] + QtCore.QPointF(0, 1))
        # Reuse the annotation control-point snap path, including local/global
        # angle origins, target-type switches, grid snapping and Alt inversion.
        names = ("selectedWall", "selectedVertex", "dragStart", "dragVertices", "dragSourceVertices",
                 "vertexAxisFromDragged", "connectedEnabled")
        previous = [getattr(v, name) for name in names]
        try:
            v.axisConstraintOrigin = v.axisConstraintDirection = None
            v.selectedWall, v.selectedVertex = guide, self.draggedPoint
            v.dragStart = self.dragStart
            v.dragVertices = v.dragSourceVertices = (guide.firstVertex, guide.secondVertex)
            v.vertexAxisFromDragged, v.connectedEnabled = False, False
            anchor = self.points[1 - self.draggedPoint] if len(self.points) == 2 else original[0]
            self.points[self.draggedPoint] = v.SnapStairVertex(self.hover, anchor, guide, modifiers)
        finally:
            for name, value in zip(names, previous):
                setattr(v, name, value)
        v.update()

    def EndPointDrag(self, cancelled):
        if cancelled:
            self.points = self.dragBefore
        self.draggedPoint = None
        self.dragBefore = None
        self.dragStart = None
        v = self.reference.viewport
        v.releaseMouse()
        v.alignmentGuides = []
        v.axisConstraintOrigin = v.axisConstraintDirection = None
        v.UpdateCanvasCursor()
        v.update()

    def HandleEvent(self, event):
        v = self.reference.viewport
        eventType = event.type()
        if (self.placementPress is not None
                and (eventType == QtCore.QEvent.Type.MouseMove
                     or eventType == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.LeftButton)
                and (event.position() - self.placementPress).manhattanLength() >= QtWidgets.QApplication.startDragDistance()):
            # A first-point press can become a second-point drag. Keep the
            # single-point snapshot so cancelling the drag restores that point.
            self.dragBefore = [QtCore.QPointF(self.points[0])]
            self.points.append(QtCore.QPointF(self.points[0]))
            self.draggedPoint = 1
            self.dragStart, self.placementPress = self.placementPress, None
        if eventType in (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease):
            if event.key() == QtCore.Qt.Key.Key_B:
                return False
            if eventType == QtCore.QEvent.Type.KeyPress and not event.isAutoRepeat():
                if event.key() == QtCore.Qt.Key.Key_Escape:
                    if self.draggedPoint is not None:
                        self.EndPointDrag(True)
                    else:
                        self.Stop()
                elif event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                    if self.draggedPoint is None:
                        self.Confirm()
            if (self.draggedPoint is not None and eventType in (QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease)
                    and event.key() in (QtCore.Qt.Key.Key_Control, QtCore.Qt.Key.Key_Alt)):
                modifiers = event.modifiers()
                flag = QtCore.Qt.KeyboardModifier.ControlModifier if event.key() == QtCore.Qt.Key.Key_Control else QtCore.Qt.KeyboardModifier.AltModifier
                modifiers = modifiers | flag if eventType == QtCore.QEvent.Type.KeyPress else modifiers & ~flag
                self.UpdatePoint(modifiers)
            event.accept()
            return True
        if v.isPanning:
            return False
        if eventType == QtCore.QEvent.Type.MouseMove:
            self.hover = v.ViewportToWorld(event.position())
            v.hoverPosition = event.position()
            if self.draggedPoint is not None:
                self.UpdatePoint(event.modifiers())
            v.UpdateCanvasCursor()
            v.update()
            return True
        if eventType in (QtCore.QEvent.Type.MouseButtonPress, QtCore.QEvent.Type.MouseButtonDblClick):
            if event.button() == QtCore.Qt.MouseButton.MiddleButton:
                return False
            if event.button() == QtCore.Qt.MouseButton.RightButton:
                if self.draggedPoint is not None:
                    self.EndPointDrag(True)
                else:
                    self.Stop()
                self.reference.suppressRelease = True
                return True
            if event.button() == QtCore.Qt.MouseButton.LeftButton and v.DrawingRect().contains(event.position()):
                self.hover = v.ViewportToWorld(event.position())
                v.hoverPosition = event.position()
                index = self.HitPoint(event.position())
                if index is not None:
                    self.draggedPoint = index
                    self.dragBefore = [QtCore.QPointF(point) for point in self.points]
                    self.dragStart = QtCore.QPointF(event.position())
                    v.grabMouse()
                elif len(self.points) < 2:
                    if not self.points or QtCore.QLineF(self.points[0], self.hover).length() > 1e-6:
                        self.points.append(QtCore.QPointF(self.hover))
                        if len(self.points) == 1:
                            self.placementPress = QtCore.QPointF(event.position())
                            v.grabMouse()
                v.setFocus()
                v.UpdateCanvasCursor()
                v.update()
            return True
        if eventType == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.LeftButton:
            if self.placementPress is not None:
                self.placementPress = None
                v.releaseMouse()
            if self.draggedPoint is not None:
                self.hover = v.ViewportToWorld(event.position())
                self.UpdatePoint(event.modifiers())
                self.EndPointDrag(False)
            return True
        return False

    def Draw(self, painter, drawingRect):
        v = self.reference.viewport
        painter.save()
        painter.setClipRect(drawingRect, QtCore.Qt.ClipOperation.IntersectClip)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setFont(v.font())
        color = QtGui.QColor(themeColors["selectionOutline"])
        painter.setPen(QtGui.QPen(color, 1.5))
        points = list(self.points)
        if len(points) == 1 and self.hover is not None:
            points.append(self.hover)
        if len(points) == 2:
            first, second = (v.WorldToViewport(point) for point in points)
            direction = second - first
            length = math.hypot(direction.x(), direction.y())
            if length > 1e-8:
                painter.drawLine(QtCore.QLineF(first, second))
                normal = QtCore.QPointF(direction.y(), -direction.x()) / length
                tick = (direction / length + normal) * 3
                for point in (first, second):
                    painter.drawLine(QtCore.QLineF(point - tick, point + tick))
                angle = math.degrees(math.atan2(direction.y(), direction.x()))
                angle = (angle + 90) % 180 - 90
                label = FormatLength(QtCore.QLineF(*points).length(), v.unitsMode)
                width = painter.fontMetrics().horizontalAdvance(label) + 12
                painter.save()
                painter.translate((first + second) / 2)
                painter.rotate(angle)
                rect = QtCore.QRectF(-width / 2, -10, width, 20)
                painter.fillRect(rect, QtGui.QColor(themeColors["canvas"]))
                painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, label)
                painter.restore()
        hovered = self.HitPoint(v.hoverPosition)
        for index, point in enumerate(self.points):
            active = index == hovered or index == self.draggedPoint
            painter.setPen(QtGui.QPen(QtGui.QColor(themeColors["selectionOutline"] if active else themeColors["wallOutline"]), 1.5))
            painter.setBrush(QtGui.QColor(themeColors["selectionOutline"] if active else themeColors["windowBackground"]))
            painter.drawEllipse(v.WorldToViewport(point), 7, 7)
        painter.restore()
