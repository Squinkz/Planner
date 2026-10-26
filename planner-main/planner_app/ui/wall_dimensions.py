"""Shared wall dimension controls for project settings and export overrides."""
from PySide6 import QtCore, QtWidgets
from planner_app.graphics.icons import UiIcon
from planner_app.preferences import measurementDefaults
from planner_app.geometry.measurements import EffectiveWallSplitSettings
from .widgets import SectionHeading, DownwardComboBox, DragSlider


class WallDimensionControlsMixin:
    def BuildWallDimensionControls(self, layout, mode, settings, setMode, setReference, setSplit):
        self.wallDimensionWidget = QtWidgets.QWidget()
        wallLayout = QtWidgets.QVBoxLayout(self.wallDimensionWidget)
        wallLayout.setContentsMargins(0, 0, 0, 0)
        wallLayout.setSpacing(8)
        layout.addWidget(self.wallDimensionWidget)
        layout = wallLayout
        self.wallSplitChanged = setSplit
        self.wallMeasurementHeading = SectionHeading("Walls", "Walls")
        layout.addWidget(self.wallMeasurementHeading)
        modeForm = QtWidgets.QFormLayout()
        modeForm.setHorizontalSpacing(16)
        self.wallMeasurementModeField = DownwardComboBox()
        self.wallMeasurementModeField.setAccessibleName("Wall dimension mode")
        self.wallMeasurementModeField.setFixedHeight(32)
        self.wallMeasurementModeField.addItems(["All", "Exterior", "Exterior stacked"])
        self.wallMeasurementModeField.setCurrentText(mode)
        self.wallMeasurementModeField.currentTextChanged.connect(setMode)
        self.wallMeasurementModeLabel = QtWidgets.QLabel("Mode")
        modeForm.addRow(self.wallMeasurementModeLabel, self.wallMeasurementModeField)
        layout.addLayout(modeForm)
        self.wallReferenceWidget = QtWidgets.QWidget()
        referenceForm = QtWidgets.QFormLayout(self.wallReferenceWidget)
        referenceForm.setContentsMargins(0, 0, 0, 0)
        referenceForm.setHorizontalSpacing(16)
        self.wallReferenceField = DownwardComboBox()
        self.wallReferenceField.setAccessibleName("Wall reference")
        self.wallReferenceField.setFixedHeight(32)
        self.wallReferenceField.addItems(["Centerline", "Wall faces"])
        self.wallReferenceField.currentTextChanged.connect(setReference)
        referenceForm.addRow("Wall reference", self.wallReferenceField)
        self.wallReferenceLabel = referenceForm.labelForField(self.wallReferenceField)
        referenceWidth = referenceForm.labelForField(self.wallReferenceField).sizeHint().width()
        self.wallMeasurementModeLabel.setMinimumWidth(referenceWidth)
        layout.addWidget(self.wallReferenceWidget)
        self.measurementSplitWidget = QtWidgets.QWidget()
        splitLayout = QtWidgets.QVBoxLayout(self.measurementSplitWidget)
        splitLayout.setContentsMargins(0, 0, 0, 0)
        self.measurementSplitTabs = QtWidgets.QTabWidget()
        self.measurementSplitTabs.setAccessibleName("Wall dimension split categories")
        self.measurementSplitTabs.tabBar().setDrawBase(False)
        splitLayout.addWidget(self.measurementSplitTabs)
        layout.addWidget(self.measurementSplitWidget)
        self.measurementSliders = {}
        self.measurementLabels = {}
        self.measurementResetButtons = {}
        self.measurementDragging = None
        self.measurementWheelDeltas = {key: 0 for key in measurementDefaults}
        self.measurementModes = {"doors": (0, 1, 2), "windows": (0, 1, 2), "stairs": (0, 2), "counters": (0, 2)}
        for key, title in (("doors", "Doors"), ("windows", "Windows"), ("stairs", "Stairs"), ("counters", "Counters")):
            categoryPage = QtWidgets.QWidget()
            categoryLayout = QtWidgets.QVBoxLayout(categoryPage)
            categoryLayout.setContentsMargins(16, 20, 16, 16)
            self.measurementSplitTabs.addTab(categoryPage, title)
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(16)
            slider = DragSlider(QtCore.Qt.Orientation.Vertical)
            slider.setObjectName("measurementMode")
            slider.ensurePolished()
            slider.setFixedWidth(20)
            slider.setRange(0, len(self.measurementModes[key]) - 1)
            slider.setInvertedAppearance(True)
            slider.setInvertedControls(True)
            slider.setSingleStep(1)
            slider.setPageStep(1)
            sliderHeight = 49 if key in ("stairs", "counters") else 112
            slider.setFixedHeight(sliderHeight)
            # Disabled/visible-state repolishing reapplies the generic slider's
            # minimum height. Keep discrete selector geometry fixed in QSS too,
            # so a compact stacked-mode dialog scrolls rather than squeezing it.
            slider.setStyleSheet(f"QSlider#measurementMode {{ min-height: {sliderHeight}px; max-height: {sliderHeight}px; }}")
            slider.setAccessibleName(f"{title} wall dimension splits")
            value = settings[key]
            slider.setValue(self.measurementModes[key].index(value))
            row.addWidget(slider)
            labelArea = QtWidgets.QWidget()
            labels = QtWidgets.QVBoxLayout(labelArea)
            labels.setContentsMargins(0, 0, 0, 0)
            labels.setSpacing(0)
            texts = ("Split wall dimensions", "Do not split wall dimensions") if key in ("stairs", "counters") else (
                "Split all wall dimensions", "Split on facing side only", "Do not split wall dimensions")
            self.measurementLabels[key] = []
            for index, text in enumerate(texts):
                label = QtWidgets.QLabel(text)
                label.setProperty("measurementKey", key)
                label.installEventFilter(self)
                alignment = QtCore.Qt.AlignmentFlag.AlignTop if index == 0 else (
                    QtCore.Qt.AlignmentFlag.AlignBottom if index == len(texts) - 1 else QtCore.Qt.AlignmentFlag.AlignVCenter)
                labels.addWidget(label, 1, alignment)
                self.measurementLabels[key].append(label)
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
            reset.setToolTip(f"Reset wall dimension splits for {title.lower()}")
            reset.setEnabled(value != measurementDefaults[key])
            reset.clicked.connect(lambda checked = False, key = key: self.ChangeWallSplit(key, measurementDefaults[key]))
            row.addWidget(reset)
            slider.valueChanged.connect(lambda value, key = key: self.ChangeWallSplit(key, self.measurementModes[key][value]))
            self.measurementSliders[key] = slider
            self.measurementResetButtons[key] = reset
            categoryLayout.addLayout(row)
            categoryLayout.addStretch(1)
        self.measurementSplitTabs.currentChanged.connect(self.FitMeasurementSplitTabs)

    def FitMeasurementSplitTabs(self):
        tabs = self.measurementSplitTabs
        page = tabs.currentWidget()
        if page is None:
            return
        tabs.ensurePolished()
        page.layout().invalidate()
        page.layout().activate()
        frameHeight = tabs.tabBar().sizeHint().height() + 2 * tabs.style().pixelMetric(QtWidgets.QStyle.PixelMetric.PM_DefaultFrameWidth)
        tabs.setFixedHeight(page.layout().sizeHint().height() + frameHeight)

    def ChangeWallSplit(self, key, value):
        if self.wallMeasurementModeField.currentText() == "Exterior" and value == 1:
            value = 0
        self.wallSplitChanged(key, value)

    def RefreshWallDimensionControls(self, wallMode, reference, splitSettings, wallDimensionsEnabled):
        blocker = QtCore.QSignalBlocker(self.wallMeasurementModeField)
        self.wallMeasurementModeField.setCurrentText(wallMode)
        del blocker
        self.wallMeasurementHeading.setEnabled(wallDimensionsEnabled)
        self.wallMeasurementModeField.setEnabled(wallDimensionsEnabled)
        self.wallMeasurementModeLabel.setEnabled(wallDimensionsEnabled)
        stacked = wallMode == "Exterior stacked"
        self.wallReferenceWidget.setVisible(stacked)
        self.wallReferenceWidget.setEnabled(wallDimensionsEnabled)
        self.measurementSplitWidget.setVisible(not stacked)
        referenceBlocker = QtCore.QSignalBlocker(self.wallReferenceField)
        self.wallReferenceField.setCurrentText(reference)
        del referenceBlocker
        splitsEnabled = wallDimensionsEnabled and not stacked
        self.measurementSplitTabs.setEnabled(splitsEnabled)
        settings = EffectiveWallSplitSettings(splitSettings, wallMode)
        defaults = EffectiveWallSplitSettings(measurementDefaults, wallMode)
        resizedSplits = False
        for key, slider in self.measurementSliders.items():
            modes = (0, 1, 2) if key in ("doors", "windows") and wallMode != "Exterior" else (0, 2)
            self.measurementModes[key] = modes
            blocker = QtCore.QSignalBlocker(slider)
            if slider.maximum() != len(modes) - 1:
                resizedSplits = True
                slider.setRange(0, len(modes) - 1)
                height = 112 if len(modes) == 3 else 49
                slider.setFixedHeight(height)
                slider.setStyleSheet(f"QSlider#measurementMode {{ min-height: {height}px; max-height: {height}px; }}")
            slider.setValue(modes.index(settings[key]))
            del blocker
            labels = self.measurementLabels[key]
            if len(labels) == 3:
                labels[0].setText("Split wall dimensions" if wallMode == "Exterior" else "Split all wall dimensions")
                labels[1].setVisible(wallMode != "Exterior")
            slider.setEnabled(splitsEnabled)
            for widget in self.measurementSplitWidget.findChildren(QtWidgets.QWidget):
                if widget.property("measurementKey") == key or widget.property("measurementHeadingKey") == key:
                    widget.setEnabled(splitsEnabled)
            self.measurementResetButtons[key].setEnabled(splitsEnabled and settings[key] != defaults[key])
        self.FitMeasurementSplitTabs()
        if resizedSplits:
            # Stylesheet size changes settle in Qt's next layout pass.
            QtCore.QTimer.singleShot(0, self.FitMeasurementSplitTabs)

    def HandleWallDimensionEvent(self, watched, event):
        if (event.type() in (QtCore.QEvent.Type.WindowDeactivate, QtCore.QEvent.Type.Hide, QtCore.QEvent.Type.UngrabMouse)
                and getattr(self, "measurementDragging", None) is not None):
            slider = self.measurementSliders[self.measurementDragging]
            self.measurementDragging = None
            slider.setSliderDown(False)
        key = watched.property("measurementKey")
        if key in getattr(self, "measurementSliders", {}):
            slider = self.measurementSliders[key]
            if not slider.isEnabled():
                return False
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
                return False
            pressed = eventType == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.LeftButton
            moved = eventType == QtCore.QEvent.Type.MouseMove and self.measurementDragging == key
            if moved and not event.buttons() & QtCore.Qt.MouseButton.LeftButton:
                self.measurementDragging = None
                slider.setSliderDown(False)
                return False
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
        return False

    def eventFilter(self, watched, event):
        if self.HandleWallDimensionEvent(watched, event):
            return True
        return super().eventFilter(watched, event)

    def event(self, event):
        if (event.type() in (QtCore.QEvent.Type.WindowDeactivate, QtCore.QEvent.Type.Hide, QtCore.QEvent.Type.UngrabMouse)
                and getattr(self, "measurementDragging", None) is not None):
            slider = self.measurementSliders[self.measurementDragging]
            self.measurementDragging = None
            slider.setSliderDown(False)
        return super().event(event)
