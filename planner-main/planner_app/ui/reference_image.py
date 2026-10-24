"""Reference-image controls and canvas gestures; reference data stays out of scene geometry."""
import base64
import math
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.icons import UiIcon
from planner_app.graphics.cursors import RotationCursor
from planner_app.graphics.palette import themeColors
from planner_app.reference_image import ReadReferenceImage, imageByteLimit
from .widgets import DragSlider, DragSpinBox, SizeLinkButton
from .reference_calibration import ReferenceCalibration
from planner_app.models import Furnishing
from planner_app.units import PropertyUnit
from planner_app.history_edits import ReferenceImageEdit


class ReferenceImageController:
    def __init__(self, mainWindow):
        self.mainWindow = mainWindow
        self.viewport = mainWindow.viewport
        self.state = None
        self.image = QtGui.QImage()
        self.revision = 0
        self.active = False
        self.drag = None
        self.proxy = Furnishing(self.viewport.furnishingDefinitions["null"])
        self.rotating = False
        self.pivot = None
        self.fieldBefore = None
        self.fieldPivotBefore = None
        self.suppressRelease = False
        self.historyState = (None, None)
        self.historyRestoring = False
        self.calibration = ReferenceCalibration(self)

    def BuildPanel(self, layout):
        self.panel = QtWidgets.QWidget()
        form = QtWidgets.QVBoxLayout(self.panel)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(12)
        pathRow = QtWidgets.QHBoxLayout()
        pathRow.setContentsMargins(0, 0, 0, 0)
        pathRow.setSpacing(6)
        self.pathField = QtWidgets.QLineEdit()
        self.pathField.setPlaceholderText("Reference image path")
        self.pathField.setAccessibleName("Reference image path")
        self.pathField.editingFinished.connect(self.PathEdited)
        self.browseButton = QtWidgets.QToolButton()
        self.browseButton.setObjectName("exportBrowseButton")
        self.browseButton.setIcon(UiIcon("folder_open"))
        self.browseButton.setIconSize(QtCore.QSize(26, 26))
        self.browseButton.setFixedSize(44, 32)
        self.browseButton.setToolTip("Browse")
        self.browseButton.setAccessibleName("Browse reference image path")
        self.browseButton.clicked.connect(self.Browse)
        pathRow.addWidget(self.pathField, 1)
        pathRow.addWidget(self.browseButton)
        form.addLayout(pathRow)
        opacityRow = QtWidgets.QHBoxLayout()
        opacityIcon = QtWidgets.QLabel()
        opacityIcon.setPixmap(UiIcon("opacity").pixmap(24, 24))
        opacityIcon.setToolTip("Opacity")
        opacityIcon.setAccessibleName("Opacity")
        opacityRow.addWidget(opacityIcon)
        self.opacitySlider = DragSlider(QtCore.Qt.Orientation.Horizontal)
        self.opacitySlider.setObjectName("referenceImageOpacity")
        self.opacitySlider.setRange(0, 100)
        self.opacitySlider.setAccessibleName("Reference image opacity")
        self.opacitySlider.valueChanged.connect(self.SetOpacity)
        self.opacitySlider.sliderReleased.connect(self.RecordHistory)
        self.opacityValue = QtWidgets.QLabel()
        opacityRow.addWidget(self.opacitySlider, 1)
        opacityRow.addWidget(self.opacityValue)
        form.addLayout(opacityRow)
        properties = QtWidgets.QFormLayout()
        properties.setContentsMargins(0, 0, 0, 0)
        properties.setHorizontalSpacing(16)
        properties.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        positionRow = QtWidgets.QHBoxLayout()
        positionRow.setContentsMargins(0, 0, 0, 0)
        positionRow.setSpacing(6)
        properties.addRow("Position", positionRow)
        sizeRow = QtWidgets.QHBoxLayout()
        sizeRow.setContentsMargins(0, 0, 0, 0)
        sizeRow.setSpacing(6)
        properties.addRow("Size", sizeRow)
        self.fields = {}
        self.sizeLinkButton = SizeLinkButton()
        for name, label in (("x", "X"), ("y", "Y"), ("width", "Width"), ("length", "Length"), ("angle", "Angle")):
            field = DragSpinBox()
            field.setAccessibleName("Reference image " + label.lower())
            field.setKeyboardTracking(False)
            field.dragStarted.connect(self.BeginPropertyDrag)
            field.dragFinished.connect(self.FinishPropertyDrag)
            field.valueChanged.connect(lambda value, name = name: self.SetProperty(name, value))
            if name in ("x", "y"):
                positionRow.addWidget(field, 1)
            elif name in ("width", "length"):
                if name == "length":
                    sizeRow.addWidget(self.sizeLinkButton)
                sizeRow.addWidget(field, 1)
                field.setToolTip(label + ". Drag to adjust or click to type.")
            else:
                properties.addRow(label, field)
            self.fields[name] = field
        form.addLayout(properties)
        self.calibrateButton = QtWidgets.QPushButton("Calibrate Scale")
        self.calibrateButton.setToolTip("Pick two points, press Enter, then enter their actual distance")
        self.calibrateButton.clicked.connect(self.calibration.Start)
        form.addWidget(self.calibrateButton)
        layout.addWidget(self.panel)
        self.panel.hide()
        self.viewport.selectionChanged.connect(self.SelectionChanged)
        self.mainWindow.sidebarTabs.currentChanged.connect(self.TabChanged)

    def Snapshot(self):
        return dict(self.state, center = list(self.state["center"])) if self.state is not None else None

    def Restore(self, record):
        self.Hide(restoreSelection = False)
        image = ReadReferenceImage(base64.b64decode(record["data"])) if record is not None else QtGui.QImage()
        self.state = dict(record, center = list(record["center"])) if record is not None else None
        if self.state is not None:
            self.state.pop("locked", None)
        self.image = image
        self.rotating, self.pivot = False, None
        self.historyState = self.HistoryState()
        self.revision += 1
        self.SyncControls()
        self.viewport.update()

    def HistoryState(self):
        return self.Snapshot(), (self.pivot.x(), self.pivot.y()) if self.pivot is not None else None

    def RecordHistory(self):
        if (self.historyRestoring or self.mainWindow.projectLoading or self.drag is not None
                or self.fieldBefore is not None or self.opacitySlider.isSliderDown()):
            return
        after = self.HistoryState()
        if self.historyState != after:
            # The initial image establishes the baseline. Only changed properties
            # enter the shared journal, so moves do not repeat the embedded data.
            if self.historyState[0] is not None and after[0] is not None:
                before = self.historyState
                changes = {name: (before[0][name], value) for name, value in after[0].items()
                           if name != "visible" and before[0][name] != value}
                if changes or before[1] != after[1]:
                    v = self.viewport
                    v.undoHistory.append(ReferenceImageEdit(changes, (before[1], after[1])))
                    v.redoHistory.clear()
                    v.historyCoalesceKey = None
                    totalBytes = sum(edit.byteSize for edit in v.undoHistory)
                    while v.undoHistory and (len(v.undoHistory) > v.historyLimit or totalBytes > v.historyByteBudget):
                        totalBytes -= v.undoHistory.pop(0).byteSize
                    v.sceneRevision += 1
                    v.sceneChanged.emit()
            self.historyState = after

    def RestoreHistory(self, edit, forward):
        record = edit.ApplyReference(self.Snapshot(), forward)
        pivot = edit.pivots[1 if forward else 0]
        self.historyRestoring = True
        try:
            self.CancelDrag()
            self.FinishPropertyDrag(True)
            self.calibration.Stop()
            if self.state["data"] != record["data"]:
                self.image = ReadReferenceImage(base64.b64decode(record["data"]))
            self.state = dict(record, center = list(record["center"]), visible = self.state["visible"])
            self.pivot = QtCore.QPointF(*pivot) if pivot is not None else None
            self.SyncControls()
            self.historyState = self.HistoryState()
            self.Changed()
        finally:
            self.historyRestoring = False

    def SyncControls(self):
        main = self.mainWindow
        blocker = QtCore.QSignalBlocker(main.visibilityTree)
        main.referenceImageItem.setCheckState(0, QtCore.Qt.CheckState.Checked if self.state and self.state["visible"] else QtCore.Qt.CheckState.Unchecked)
        del blocker
        self.pathField.setText(self.state["path"] if self.state else "")
        blocker = QtCore.QSignalBlocker(self.opacitySlider)
        opacity = round(self.state["opacity"] * 100) if self.state else 50
        self.opacitySlider.setValue(opacity)
        self.opacityValue.setText(f"{opacity}%")
        self.SyncProperties()

    def SyncProxy(self, record = None):
        record = self.state if record is None else record
        center = QtCore.QPointF(*record["center"])
        angle = math.radians(record["angle"])
        north = QtCore.QPointF(-math.sin(angle), math.cos(angle))
        self.proxy.width = record["width"]
        self.proxy.firstVertex = center - north * (record["height"] / 2)
        self.proxy.secondVertex = center + north * (record["height"] / 2)

    def SyncProperties(self):
        if self.state is None:
            return
        self.SyncProxy()
        position = self.pivot if self.rotating and self.pivot is not None else QtCore.QPointF(*self.state["center"])
        values = dict(x = position.x(), y = position.y(), width = self.state["width"], length = self.state["height"], angle = self.state["angle"])
        for name, field in self.fields.items():
            divisor, unit = (1, "°") if name == "angle" else PropertyUnit(name, self.proxy, self.viewport.unitsMode)
            blocker = QtCore.QSignalBlocker(field)
            field.setDecimals(0 if unit == "mm" else 3)
            field.setRange((-1e12 if name in ("x", "y", "angle") else 1) / divisor, 1e12 / divisor)
            field.setSuffix(" " + unit)
            field.setSingleStep((1 if name == "angle" else 100 if name in ("x", "y") else 10) / divisor)
            field.setValue(values[name] / divisor)
            del blocker
        for name in ("x", "y"):
            self.fields[name].setToolTip(("Rotation pivot " if self.rotating else "Image center ") + name.upper() + ". Drag to adjust or click to type.")

    def SetProperty(self, name, value):
        if self.state is None:
            return
        divisor, unused = (1, "°") if name == "angle" else PropertyUnit(name, self.proxy, self.viewport.unitsMode)
        if name in ("x", "y"):
            index = 0 if name == "x" else 1
            position = self.pivot if self.rotating and self.pivot is not None else QtCore.QPointF(*self.state["center"])
            delta = value * divisor - (position.x() if index == 0 else position.y())
            self.state["center"][index] += delta
            if self.pivot is not None:
                self.pivot += QtCore.QPointF(delta if index == 0 else 0, delta if index == 1 else 0)
        elif name == "angle":
            if self.rotating and self.pivot is not None:
                angle = math.radians(value - self.state["angle"])
                offset = QtCore.QPointF(*self.state["center"]) - self.pivot
                center = self.pivot + QtCore.QPointF(offset.x() * math.cos(angle) - offset.y() * math.sin(angle),
                                                   offset.x() * math.sin(angle) + offset.y() * math.cos(angle))
                self.state["center"] = [center.x(), center.y()]
            self.state["angle"] = value
        else:
            dimension = "width" if name == "width" else "height"
            size = max(1, value * divisor)
            if self.sizeLinkButton.isChecked():
                other = "height" if name == "width" else "width"
                otherSize = self.state[other] * size / self.state[dimension]
                if not 1 <= otherSize <= 1e12:
                    self.SyncProperties()
                    return
                self.state[other] = otherSize
            self.state[dimension] = size
        self.SyncProperties()
        self.Changed()

    def BeginPropertyDrag(self):
        self.fieldBefore = self.Snapshot()
        self.fieldPivotBefore = QtCore.QPointF(self.pivot) if self.pivot is not None else None

    def FinishPropertyDrag(self, cancelled):
        if cancelled and self.fieldBefore is not None:
            self.state = self.fieldBefore
            self.pivot = self.fieldPivotBefore
            self.SyncProperties()
            self.Changed()
            for field in self.fields.values():
                field.dragging = False
                field.pressPosition = None
                field.lineEdit().unsetCursor()
        self.fieldBefore = None
        self.fieldPivotBefore = None
        self.RecordHistory()

    def Browse(self):
        current = self.state["path"] if self.state else str(self.mainWindow.BrowseDirectory())
        path, unused = QtWidgets.QFileDialog.getOpenFileName(self.mainWindow, "Choose Reference Image", current,
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff);;All files (*)")
        return self.Load(path) if path else False

    def PathEdited(self):
        path = self.pathField.text().strip()
        if path and (self.state is None or path != self.state["path"]):
            self.Load(path)
        self.SyncControls()

    def Load(self, path):
        try:
            path = Path(path).resolve()
            if path.stat().st_size > imageByteLimit:
                raise ValueError("The reference image exceeds 40 MiB.")
            payload = path.read_bytes()
            image = ReadReferenceImage(payload)
        except (OSError, ValueError, RuntimeError) as error:
            self.mainWindow.ShowAppMessage("Cannot Load Reference Image", str(error), kind = "warning")
            return False
        self.CancelDrag()
        self.calibration.Stop()
        if self.state is None:
            rect = self.viewport.DrawingRect()
            center = self.viewport.ViewportToWorld(rect.center())
            scale = min(rect.width() * .8 / image.width(), rect.height() * .8 / image.height())
            width = image.width() * scale / (self.viewport.basePixelsPerMillimeter * self.viewport.zoom)
            self.state = {"center": [center.x(), center.y()], "width": max(1, width),
                          "angle": 0.0, "opacity": .5}
        self.state.update(path = str(path), data = base64.b64encode(payload).decode("ascii"), visible = True,
                          height = max(1, self.state["width"] * image.height() / image.width()))
        self.image = image
        self.mainWindow.RememberBrowseFolder(path)
        self.SyncControls()
        self.Changed()
        return True

    def ToggleVisibility(self, enabled):
        if enabled and self.state is None:
            if not self.Browse():
                self.SyncControls()
            return
        if self.state is not None:
            self.CancelDrag()
            self.state["visible"] = enabled
            self.SyncControls()
            self.revision += 1
            self.viewport.update()
            self.mainWindow.ProjectSettingsChanged()
            self.historyState = self.HistoryState()
        if not enabled:
            self.Hide()

    def Show(self):
        if self.active or not self.state or not self.state["visible"] or self.mainWindow.sidebarTabs.currentWidget() is not self.mainWindow.visibilityPage:
            return
        main = self.mainWindow
        self.viewport.CancelInteraction()
        self.previous = (main.propertiesCollapsed, list(main.sidebarContentSplitter.sizes()), main.propertiesRestoreHeight,
                         list(self.viewport.SelectionEntries()), main.propertiesScrollArea.verticalScrollBar().value())
        self.viewport.SetSelection([])
        self.active = True
        self.sizeLinkButton.setChecked(True)
        main.propertiesHeading.SetContent("Reference Image", "Image")
        self.rotating, self.pivot = False, None
        self.historyState = (self.historyState[0], None)
        for index in range(main.propertiesScrollArea.widget().layout().count()):
            widget = main.propertiesScrollArea.widget().layout().itemAt(index).widget()
            if widget is not None:
                widget.hide()
        self.SyncControls()
        self.panel.show()
        main.SetPropertiesCollapsed(False)
        main.visibilityTree.scrollToItem(main.referenceImageItem)
        self.viewport.update()

    def Hide(self, restoreSelection = True):
        if not self.active:
            return
        self.CancelDrag()
        self.FinishPropertyDrag(True)
        self.calibration.Stop()
        self.active = False
        self.sizeLinkButton.setChecked(True)
        self.panel.hide()
        collapsed, sizes, restoreHeight, entries, scroll = self.previous
        main = self.mainWindow
        main.propertiesHeading.SetContent("Object Properties", "Objects")
        if restoreSelection:
            self.viewport.SetSelection(entries)
        main.RefreshProperties()
        main.SetPropertiesCollapsed(collapsed, rememberHeight = False)
        main.propertiesRestoreHeight = restoreHeight
        main.SetPropertiesSplitterSizes(sizes)
        if restoreSelection:
            QtCore.QTimer.singleShot(0, lambda: main.propertiesScrollArea.verticalScrollBar().setValue(scroll) if not self.active else None)
        self.viewport.UpdateCanvasCursor()
        self.viewport.update()

    def SelectionChanged(self):
        if self.active and self.viewport.SelectionEntries():
            self.viewport.selection = []
            self.viewport.selectedWall = self.viewport.selectedVertex = None

    def TabChanged(self, index):
        if self.mainWindow.sidebarTabs.widget(index) is not self.mainWindow.visibilityPage:
            self.Hide()

    def Changed(self):
        self.RecordHistory()
        self.revision += 1
        self.viewport.update()
        self.mainWindow.ProjectSettingsChanged()

    def SetOpacity(self, value):
        if self.state is not None:
            self.state["opacity"] = value / 100
            self.opacityValue.setText(f"{value}%")
            self.Changed()

    def ScreenTransform(self):
        center = self.viewport.WorldToViewport(QtCore.QPointF(*self.state["center"]))
        transform = QtGui.QTransform().translate(center.x(), center.y()).rotate(-self.state["angle"])
        scale = self.viewport.basePixelsPerMillimeter * self.viewport.zoom
        return transform.scale(scale, scale)

    def Draw(self, painter, drawingRect):
        if not self.state or not self.state["visible"] or self.image.isNull():
            return
        painter.save()
        painter.setClipRect(drawingRect, QtCore.Qt.ClipOperation.IntersectClip)
        painter.setOpacity(self.state["opacity"])
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        painter.setWorldTransform(self.ScreenTransform(), True)
        painter.drawImage(QtCore.QRectF(-self.state["width"] / 2, -self.state["height"] / 2,
                                       self.state["width"], self.state["height"]), self.image)
        painter.restore()

    def Handles(self):
        if self.calibration.active:
            return []
        self.SyncProxy()
        center = QtCore.QPointF(*self.state["center"])
        handles = self.viewport.FurnishingHandles(self.proxy, pivot = self.pivot if self.pivot is not None else center)
        mode = "rotate" if self.rotating else "resize"
        return [handle for handle in handles if handle[0] == mode or self.rotating and handle[0] == "pivot"]

    def DrawHandles(self, painter, drawingRect):
        if not self.active or not self.state or not self.state["visible"]:
            return
        if self.calibration.active:
            self.calibration.Draw(painter, drawingRect)
            return
        handles = self.Handles()
        color = QtGui.QColor(themeColors["selectionOutline"])
        painter.save()
        painter.setClipRect(drawingRect, QtCore.Qt.ClipOperation.IntersectClip)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtGui.QPen(color, 1))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPolygon(QtGui.QPolygonF([self.viewport.WorldToViewport(point) for point in self.viewport.ObjectCorners(self.proxy)]))
        self.viewport.DrawFurnishingHandleSet(painter, handles, color)
        painter.restore()

    def CancelDrag(self):
        self.viewport.StopDragPan()
        if self.drag is not None:
            self.state = self.drag["before"]
            self.pivot = self.drag["previousPivot"]
            self.drag = None
            self.viewport.releaseMouse()
            self.viewport.alignmentGuides = []
            self.SyncProperties()
            self.revision += 1
            self.viewport.update()

    def UpdateDrag(self, position, modifiers):
        v, state = self.viewport, self.drag
        if (position - state["mouseStart"]).manhattanLength() < QtWidgets.QApplication.startDragDistance() and not state["moved"]:
            return True
        state["moved"] = True
        mode = state["handle"][0] if state["handle"] is not None else "move"
        if mode == "pivot":
            delta = v.ViewportToWorld(position) - v.ViewportToWorld(state["mouseStart"])
            self.pivot = state["pivot"] + v.SnapObjectMovement([state["pivot"]], delta, modifiers, snapTargets = v.StairSnapTargets(self.proxy))
            self.SyncProperties()
        else:
            if mode == "move":
                self.SyncProxy(state["before"])
                delta = v.ViewportToWorld(position) - v.ViewportToWorld(state["mouseStart"])
                delta = v.SnapObjectMovement(v.ObjectCorners(self.proxy) + [state["center"]], delta,
                                            modifiers, snapTargets = v.StairSnapTargets(self.proxy))
                self.proxy.firstVertex += delta
                self.proxy.secondVertex += delta
                if state["previousPivot"] is not None:
                    self.pivot = state["previousPivot"] + delta
            else:
                state["centeredResize"] = bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier)
                v.TransformFurnishingHandle(state, position, modifiers)
            center = (self.proxy.firstVertex + self.proxy.secondVertex) / 2
            self.state.update(center = [center.x(), center.y()], width = self.proxy.width,
                              height = self.proxy.length, angle = self.proxy.angle)
            self.revision += 1
            self.SyncProperties()
        v.update()
        return True

    def HandleEvent(self, event):
        eventType = event.type()
        if self.suppressRelease and eventType == QtCore.QEvent.Type.MouseButtonRelease:
            self.suppressRelease = False
            return True
        if not self.active or not self.state or self.viewport.exportOverlay.active:
            return False
        if self.calibration.active:
            return self.calibration.HandleEvent(event)
        v = self.viewport
        if eventType in (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease):
            key = event.key()
            arrows = {QtCore.Qt.Key.Key_Left: (-1, 0), QtCore.Qt.Key.Key_Right: (1, 0),
                      QtCore.Qt.Key.Key_Up: (0, 1), QtCore.Qt.Key.Key_Down: (0, -1)}
            if key in arrows and self.opacitySlider.hasFocus():
                return False
            control = bool(event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier)
            blocked = (key in arrows or key in (QtCore.Qt.Key.Key_Escape, QtCore.Qt.Key.Key_Space,
                QtCore.Qt.Key.Key_Delete, QtCore.Qt.Key.Key_Backspace, QtCore.Qt.Key.Key_D,
                QtCore.Qt.Key.Key_T, QtCore.Qt.Key.Key_H, QtCore.Qt.Key.Key_Q, QtCore.Qt.Key.Key_W)
                or key == QtCore.Qt.Key.Key_S and not control
                or control and key in (QtCore.Qt.Key.Key_A, QtCore.Qt.Key.Key_C, QtCore.Qt.Key.Key_X,
                                       QtCore.Qt.Key.Key_V, QtCore.Qt.Key.Key_G, QtCore.Qt.Key.Key_Z))
            if blocked:
                if eventType == QtCore.QEvent.Type.KeyPress:
                    if key == QtCore.Qt.Key.Key_Escape:
                        if self.drag is not None:
                            self.CancelDrag()
                        else:
                            self.Hide()
                    elif control and key == QtCore.Qt.Key.Key_Z:
                        if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                            v.Redo()
                        else:
                            v.Undo()
                    elif key in arrows and self.drag is None:
                        step = v.GridSteps()[1]
                        dx, dy = arrows[key]
                        self.state["center"] = [self.state["center"][0] + dx * step, self.state["center"][1] + dy * step]
                        if self.pivot is not None:
                            self.pivot += QtCore.QPointF(dx * step, dy * step)
                        self.SyncProperties()
                        self.Changed()
                event.accept()
                return True
            return False
        if eventType in (QtCore.QEvent.Type.DragEnter, QtCore.QEvent.Type.DragMove, QtCore.QEvent.Type.Drop):
            event.ignore()
            return True
        if v.isPanning:
            return False
        if self.drag is not None:
            state = self.drag
            if eventType == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.RightButton:
                self.CancelDrag()
                self.suppressRelease = True
                return True
            if eventType == QtCore.QEvent.Type.MouseMove:
                self.UpdateDrag(event.position(), event.modifiers())
                return True
            if eventType == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.LeftButton:
                self.UpdateDrag(event.position(), event.modifiers())
                if not state["moved"] and state["handle"] is None:
                    self.rotating = not self.rotating
                    self.pivot = None
                    self.SyncProperties()
                self.drag = None
                v.releaseMouse()
                v.alignmentGuides = []
                if state["moved"]:
                    self.Changed()
                v.update()
                return True
        if eventType == QtCore.QEvent.Type.MouseButtonDblClick:
            if self.rotating and self.pivot is not None and QtCore.QLineF(event.position(), v.WorldToViewport(self.pivot)).length() <= 9:
                self.pivot = None
                self.SyncProperties()
                v.update()
                return True
            eventType = QtCore.QEvent.Type.MouseButtonPress
        if eventType not in (QtCore.QEvent.Type.MouseButtonPress, QtCore.QEvent.Type.MouseMove, QtCore.QEvent.Type.MouseButtonRelease):
            return False
        if eventType == QtCore.QEvent.Type.MouseButtonRelease:
            return event.button() != QtCore.Qt.MouseButton.MiddleButton
        position = event.position()
        if not v.DrawingRect().contains(position):
            return False
        handles = self.Handles()
        handle = next((handle for handle in handles if QtCore.QLineF(position, handle[3]).length() <= 9), None)
        local = self.ScreenTransform().inverted()[0].map(position)
        inside = abs(local.x()) <= self.state["width"] / 2 and abs(local.y()) <= self.state["height"] / 2
        v.hoverPosition = position
        if eventType == QtCore.QEvent.Type.MouseMove:
            v.UpdateCanvasCursor()
            v.update()
            return True
        if event.button() == QtCore.Qt.MouseButton.MiddleButton:
            return False
        if event.button() == QtCore.Qt.MouseButton.RightButton or event.button() == QtCore.Qt.MouseButton.LeftButton and not inside and handle is None:
            self.Hide()
            self.suppressRelease = True
            return True
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.SyncProxy()
            center = QtCore.QPointF(*self.state["center"])
            pivot = QtCore.QPointF(self.pivot if self.pivot is not None else center)
            offset = v.ViewportToWorld(position) - pivot
            self.drag = {"before": self.Snapshot(), "object": self.proxy, "handle": handle,
                         "mouseStart": QtCore.QPointF(position), "center": center,
                         "north": (self.proxy.secondVertex - self.proxy.firstVertex) / self.proxy.length,
                         "width": self.proxy.width, "length": self.proxy.length, "angle": self.proxy.angle,
                         "pivot": pivot, "previousPivot": self.pivot,
                         "mouseAngle": math.degrees(math.atan2(offset.y(), offset.x())), "moved": False}
            v.grabMouse()
            v.setFocus()
            return True
        return True

    def UpdateCursor(self):
        v = self.viewport
        shape = QtCore.Qt.CursorShape.ArrowCursor
        handle = self.drag["handle"] if self.drag is not None else None
        if v.isPanning:
            shape = QtCore.Qt.CursorShape.ClosedHandCursor
        elif self.calibration.active:
            if self.calibration.draggedPoint is not None or self.calibration.HitPoint(v.hoverPosition) is not None:
                shape = QtCore.Qt.CursorShape.SizeAllCursor
            else:
                shape = QtCore.Qt.CursorShape.CrossCursor if len(self.calibration.points) < 2 else QtCore.Qt.CursorShape.ArrowCursor
        elif self.drag is not None and handle is None:
            shape = QtCore.Qt.CursorShape.SizeAllCursor
        elif self.drag is None and v.hoverPosition is not None and v.DrawingRect().contains(v.hoverPosition):
            handle = next((item for item in self.Handles() if QtCore.QLineF(v.hoverPosition, item[3]).length() <= 9), None)
            local = self.ScreenTransform().inverted()[0].map(v.hoverPosition)
            if abs(local.x()) <= self.state["width"] / 2 and abs(local.y()) <= self.state["height"] / 2:
                shape = QtCore.Qt.CursorShape.SizeAllCursor
        if not v.isPanning and not self.calibration.active and handle is not None:
            if handle[0] == "rotate":
                cursor = RotationCursor()
                if v.cursor().shape() != cursor.shape() or v.cursor().pixmap().cacheKey() != cursor.pixmap().cacheKey():
                    v.setCursor(cursor)
                return
            if handle[0] == "pivot":
                shape = QtCore.Qt.CursorShape.SizeAllCursor
            else:
                outward = handle[4]
                direction = round(math.degrees(math.atan2(outward.y(), outward.x())) / 45) % 4
                shape = (QtCore.Qt.CursorShape.SizeHorCursor, QtCore.Qt.CursorShape.SizeFDiagCursor,
                         QtCore.Qt.CursorShape.SizeVerCursor, QtCore.Qt.CursorShape.SizeBDiagCursor)[direction]
        if v.cursor().shape() != shape:
            v.setCursor(shape)
