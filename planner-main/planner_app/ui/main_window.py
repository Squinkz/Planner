"""Main window composition and application-level input/settings."""

from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.theme import HeaderIcon
from planner_app.graphics.icons import UiIcon
from planner_app.graphics.palette import themeColors
from planner_app.garbage_collection import ConfigureGarbageCollection
from .appearance import AppearanceMixin
from .app_preferences import AppPreferencesMixin
from .widgets import FurnishingButton, WindowButton
from .header import HeaderMixin
from .properties import PropertiesMixin
from .sidebar import SidebarMixin
from .projects import ProjectsMixin
from .session import SessionMixin
from .dialogs import DialogsMixin
from .furnishing_catalog import FurnishingCatalogMixin
from planner_app.viewport.widget import DrawingViewport
from .reference_image import ReferenceImageController


class MainWindow(AppPreferencesMixin, AppearanceMixin, FurnishingCatalogMixin, DialogsMixin, SessionMixin, ProjectsMixin, HeaderMixin, SidebarMixin, PropertiesMixin, QtWidgets.QMainWindow):
    def __init__(self):
        ConfigureGarbageCollection()
        super().__init__()
        self.InitializeAppPreferences()
        self.setWindowTitle("Planner")
        self.setAcceptDrops(True)
        self.resize(1440, 900)
        centralWidget = QtWidgets.QWidget()
        mainLayout = QtWidgets.QHBoxLayout(centralWidget)
        mainLayout.setContentsMargins(12, 12, 12, 12)

        self.viewport = DrawingViewport()
        self.referenceImage = ReferenceImageController(self)
        self.viewport.referenceImage = self.referenceImage
        for option in ("showTips", "showFpsCounter"):
            value = self.appPreferences.get(option)
            if type(value) is bool:
                if option == "showFpsCounter":
                    self.viewport.SetFpsCounterVisible(value)
                else:
                    self.viewport.showTips = value
        self.viewportOnlyMode = False
        self.savedSplitterSizes = None
        self.fullscreenButton = QtWidgets.QPushButton(self.viewport)
        self.fullscreenButton.setObjectName("fullscreenButton")
        self.fullscreenButton.setAccessibleName("Toggle fullscreen")
        self.fullscreenButton.setIcon(UiIcon("fullscreen"))
        self.fullscreenButton.setIconSize(QtCore.QSize(24, 24))
        self.fullscreenButton.setFixedSize(30, 30)
        self.fullscreenButton.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.fullscreenButton.setToolTip("Fullscreen (F)")
        self.fullscreenButton.clicked.connect(self.ToggleViewportOnlyMode)
        self.sidebarPanel = QtWidgets.QWidget()
        self.sidebarPanel.setMinimumWidth(200)
        sidebarLayout = QtWidgets.QVBoxLayout(self.sidebarPanel)
        sidebarLayout.setContentsMargins(0, 0, 0, 0)
        sidebarLayout.setSpacing(10)

        self.BuildHeader(sidebarLayout)
        sidebarBody = QtWidgets.QWidget()
        sidebarBodyLayout = QtWidgets.QHBoxLayout(sidebarBody)
        sidebarBodyLayout.setContentsMargins(0, 0, 0, 0)
        sidebarBodyLayout.setSpacing(10)
        self.sidebarToolbarStrip = QtWidgets.QWidget()
        self.sidebarToolbarStrip.setFixedWidth(40)
        toolbarLayout = QtWidgets.QVBoxLayout(self.sidebarToolbarStrip)
        toolbarLayout.setContentsMargins(0, 0, 0, 0)
        toolbarLayout.setSpacing(10)
        self.BuildViewportToolbar(toolbarLayout)
        sidebarBodyLayout.addWidget(self.sidebarToolbarStrip, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        self.BuildSidebarTabs()
        self.viewport.selectionChanged.connect(self.RefreshProperties)
        self.viewport.openingToolChanged.connect(self.RefreshOpeningToolHighlight)
        self.RefreshProperties()
        sidebarBodyLayout.addWidget(self.sidebarContentPanel, 1)
        sidebarLayout.addWidget(sidebarBody, 1)

        self.mainSplitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.mainSplitter.setChildrenCollapsible(False)
        self.mainSplitter.setHandleWidth(8)
        self.mainSplitter.addWidget(self.viewport)
        self.mainSplitter.addWidget(self.sidebarPanel)
        self.mainSplitter.setStretchFactor(0, 1)
        self.mainSplitter.setStretchFactor(1, 0)
        self.mainSplitter.setSizes([948, 460])
        self.mainSplitter.handle(1).setToolTip("Double-click to reset sidebar width")
        mainLayout.addWidget(self.mainSplitter)
        self.setCentralWidget(centralWidget)
        QtWidgets.QApplication.instance().installEventFilter(self)
        self.RefreshControlCursors(self)
        self.InitializeProject()
        self.InitializeSession()

    def RefreshControlCursors(self, widget):
        # QWidget.isAncestorOf stops at window boundaries, including our dialogs.
        owner = widget
        while owner is not None and owner is not self:
            owner = owner.parent()
        if owner is None:
            return
        controls = [widget] + widget.findChildren(QtWidgets.QWidget)
        for control in controls:
            if isinstance(control, (FurnishingButton, WindowButton)):
                shape = QtCore.Qt.CursorShape.OpenHandCursor
            elif isinstance(control, QtWidgets.QSlider):
                shape = (QtCore.Qt.CursorShape.SizeHorCursor if control.orientation() == QtCore.Qt.Orientation.Horizontal
                         else QtCore.Qt.CursorShape.SizeVerCursor)
            elif control.property("measurementKey") is not None:
                shape = QtCore.Qt.CursorShape.SizeVerCursor
            elif isinstance(control, (QtWidgets.QAbstractButton, QtWidgets.QTabBar)):
                shape = QtCore.Qt.CursorShape.PointingHandCursor
            else:
                continue
            control.setCursor(shape if control.isEnabled() else QtCore.Qt.CursorShape.ArrowCursor)

    def eventFilter(self, watched, event):
        if (event.type() in (QtCore.QEvent.Type.DragEnter, QtCore.QEvent.Type.DragMove, QtCore.QEvent.Type.Drop)
                and isinstance(watched, QtWidgets.QWidget) and watched.window() is self
                and event.mimeData().hasUrls()):
            urls = event.mimeData().urls()
            path = Path(urls[0].toLocalFile()) if len(urls) == 1 and urls[0].isLocalFile() else None
            if path is not None and path.suffix.lower() == ".plan" and path.is_file():
                # Use the normal replacement prompt, recovery and failure handling.
                event.setDropAction(QtCore.Qt.DropAction.CopyAction)
                event.accept()
                if event.type() == QtCore.QEvent.Type.Drop:
                    self.viewport.StopDragPan()
                    self.OpenProject(path)
            else:
                event.ignore()
            return True
        referenceKey = (self.referenceImage.active and event.type() in
                        (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease)
                        and isinstance(watched, QtWidgets.QWidget) and watched.window() is self
                        and not any(isinstance(widget, (QtWidgets.QLineEdit, QtWidgets.QAbstractSpinBox, QtWidgets.QTextEdit,
                                                       QtWidgets.QPlainTextEdit, QtWidgets.QComboBox))
                                    for widget in (watched, QtWidgets.QApplication.focusWidget())))
        if (watched is self.viewport or referenceKey) and self.referenceImage.HandleEvent(event):
            if event.type() == QtCore.QEvent.Type.MouseMove:
                self.viewport.UpdateDragPan(event.position(), event.buttons())
            elif (event.type() == QtCore.QEvent.Type.MouseButtonRelease
                  or self.referenceImage.drag is None and self.referenceImage.calibration.draggedPoint is None):
                self.viewport.StopDragPan()
            return True
        eventType = event.type()
        if watched is self and eventType in (QtCore.QEvent.Type.WindowDeactivate, QtCore.QEvent.Type.Hide):
            self.viewport.StopDragPan()
        if (eventType in (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress)
                and isinstance(watched, QtWidgets.QWidget) and watched.window() is self
                and event.key() == QtCore.Qt.Key.Key_Space
                and event.modifiers() == QtCore.Qt.KeyboardModifier.NoModifier
                and not self.viewport.exportOverlay.active
                and not any(isinstance(widget, (QtWidgets.QLineEdit, QtWidgets.QAbstractSpinBox, QtWidgets.QTextEdit,
                                               QtWidgets.QPlainTextEdit, QtWidgets.QComboBox))
                            for widget in (watched, QtWidgets.QApplication.focusWidget()))):
            position = QtCore.QPointF(self.viewport.mapFromGlobal(QtGui.QCursor.pos()))
            if self.viewport.DrawingRect().contains(position):
                if eventType == QtCore.QEvent.Type.KeyPress and not event.isAutoRepeat():
                    self.ShowFurnishingSearch(position)
                event.accept()
                return True
        if self.viewport.exportOverlay.active:
            if (eventType in (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress)
                    and isinstance(watched, QtWidgets.QWidget) and (watched.window() is self or self.isAncestorOf(watched))
                    and event.key() == QtCore.Qt.Key.Key_Z and event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
                if eventType == QtCore.QEvent.Type.KeyPress and not event.isAutoRepeat():
                    focused = QtWidgets.QApplication.focusWidget()
                    if isinstance(focused, QtWidgets.QAbstractSpinBox):
                        focused.interpretText()
                    elif isinstance(focused, QtWidgets.QLineEdit) and isinstance(focused.parentWidget(), QtWidgets.QAbstractSpinBox):
                        focused.parentWidget().interpretText()
                    elif isinstance(focused, QtWidgets.QLineEdit) and self.exportPanel.isAncestorOf(focused):
                        focused.editingFinished.emit()
                    if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                        self.viewport.Redo()
                    else:
                        self.viewport.Undo()
                event.accept()
                return True
            if (isinstance(watched, QtWidgets.QWidget)
                    and (watched is self.viewport or self.exportPanel.isAncestorOf(watched))):
                if eventType == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.LeftButton:
                    self.exportPanel.BeginExportGesture()
                elif eventType == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.LeftButton:
                    QtCore.QTimer.singleShot(0, self.exportPanel.EndExportGesture)
        if (self.viewport.exportOverlay.active
                and eventType in (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease)
                and isinstance(watched, QtWidgets.QWidget) and (watched.window() is self or self.isAncestorOf(watched))
                and not any(isinstance(widget, (QtWidgets.QLineEdit, QtWidgets.QAbstractSpinBox, QtWidgets.QTextEdit,
                                               QtWidgets.QPlainTextEdit, QtWidgets.QComboBox))
                            for widget in (watched, QtWidgets.QApplication.focusWidget()))
                and (event.key() in (QtCore.Qt.Key.Key_D, QtCore.Qt.Key.Key_S, QtCore.Qt.Key.Key_Delete,
                                    QtCore.Qt.Key.Key_T, QtCore.Qt.Key.Key_Tab, QtCore.Qt.Key.Key_Q, QtCore.Qt.Key.Key_W,
                                    QtCore.Qt.Key.Key_H)
                     and not event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier
                     or event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier
                     and event.key() in (QtCore.Qt.Key.Key_A, QtCore.Qt.Key.Key_V, QtCore.Qt.Key.Key_X,
                                         QtCore.Qt.Key.Key_C, QtCore.Qt.Key.Key_G, QtCore.Qt.Key.Key_H)
                     or event.modifiers() == QtCore.Qt.KeyboardModifier.AltModifier and event.key() == QtCore.Qt.Key.Key_G)):
            event.accept()
            return True
        if (watched is self.viewport
                and eventType in (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress)
                and event.key() == QtCore.Qt.Key.Key_Tab
                and event.modifiers() == QtCore.Qt.KeyboardModifier.NoModifier):
            if eventType == QtCore.QEvent.Type.KeyPress and not event.isAutoRepeat():
                self.SetTransformOrientation(not self.viewport.localTransforms)
            event.accept()
            return True
        if (eventType in (QtCore.QEvent.Type.Polish, QtCore.QEvent.Type.Show, QtCore.QEvent.Type.Enter, QtCore.QEvent.Type.EnabledChange)
                and (isinstance(watched, (QtWidgets.QAbstractButton, QtWidgets.QTabBar, QtWidgets.QSlider))
                     or eventType == QtCore.QEvent.Type.Show and isinstance(watched, QtWidgets.QWidget) and watched.isWindow())):
            self.RefreshControlCursors(watched)
        if (eventType == QtCore.QEvent.Type.ShortcutOverride
                and isinstance(watched, QtWidgets.QWidget) and watched.window() is self
                and not (event.key() == QtCore.Qt.Key.Key_S and event.modifiers() in (
                    QtCore.Qt.KeyboardModifier.ControlModifier,
                    QtCore.Qt.KeyboardModifier.ControlModifier | QtCore.Qt.KeyboardModifier.ShiftModifier))):
            focused = QtWidgets.QApplication.focusWidget()
            while focused is not None and focused is not self:
                if isinstance(focused, (QtWidgets.QLineEdit, QtWidgets.QAbstractSpinBox,
                                        QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)):
                    # Reserve the key for the editor before Qt activates window shortcuts.
                    # KeyPress still reaches the editor for typing and native editing commands.
                    event.accept()
                    return True
                focused = focused.parentWidget()
        if (eventType in (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress)
                and isinstance(watched, QtWidgets.QWidget) and watched.window() is self
                and event.modifiers() == QtCore.Qt.KeyboardModifier.NoModifier
                and event.key() == QtCore.Qt.Key.Key_T
                and not any(isinstance(widget, (QtWidgets.QLineEdit, QtWidgets.QAbstractSpinBox,
                                               QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit, QtWidgets.QComboBox))
                            for widget in (watched, QtWidgets.QApplication.focusWidget()))):
            if eventType == QtCore.QEvent.Type.KeyPress and not event.isAutoRepeat():
                self.ShowMoveSpecial()
            event.accept()
            return True
        if (watched is getattr(self, "furnishingSearchClearButton", None)
                and eventType in (QtCore.QEvent.Type.Enter, QtCore.QEvent.Type.Leave)):
            self.furnishingSearchClearAction.setIcon(UiIcon("close", themeColors["activeText"]
                                                          if eventType == QtCore.QEvent.Type.Enter else themeColors["mutedText"]))
        if watched is self.viewport and eventType == QtCore.QEvent.Type.Resize:
            self.fullscreenButton.move(max(0, self.viewport.width() - 42), 40)
            self.fullscreenButton.raise_()
        if (eventType in (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress)
                and isinstance(watched, QtWidgets.QWidget) and watched.window() is self
                and event.modifiers() == QtCore.Qt.KeyboardModifier.NoModifier
                and (event.key() == QtCore.Qt.Key.Key_Escape and self.viewportOnlyMode
                     or event.key() == QtCore.Qt.Key.Key_F
                     and not any(isinstance(widget, (QtWidgets.QLineEdit, QtWidgets.QAbstractSpinBox,
                                                    QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit, QtWidgets.QComboBox))
                                 for widget in (watched, QtWidgets.QApplication.focusWidget())))):
            if eventType == QtCore.QEvent.Type.KeyPress and not event.isAutoRepeat():
                self.ToggleViewportOnlyMode()
            event.accept()
            return True
        if (watched is self.mainSplitter.handle(1)
                and eventType == QtCore.QEvent.Type.MouseButtonDblClick
                and event.button() == QtCore.Qt.MouseButton.LeftButton):
            availableWidth = sum(self.mainSplitter.sizes())
            self.mainSplitter.setSizes([max(0, availableWidth - 460), 460])
            event.accept()
            return True
        if watched is self.sidebarContentSplitter.handle(1):
            if (eventType == QtCore.QEvent.Type.MouseButtonDblClick
                    and event.button() == QtCore.Qt.MouseButton.LeftButton):
                self.propertiesDividerDragging = False
                self.propertiesRestoreHeight = None
                self.SetPropertiesCollapsed(False)
                self.SetPropertiesSplitterSizes([600, 300])
                event.accept()
                return True
            elif (eventType == QtCore.QEvent.Type.MouseButtonPress
                    and event.button() == QtCore.Qt.MouseButton.LeftButton):
                self.propertiesDividerDragging = True
                self.propertiesPanel.setMaximumHeight(16777215)
            elif (eventType == QtCore.QEvent.Type.MouseButtonRelease
                    and event.button() == QtCore.Qt.MouseButton.LeftButton):
                self.propertiesDividerDragging = False
                if self.propertiesCollapsed:
                    self.propertiesPanel.setFixedHeight(self.propertiesHeadingHeight)
        if (self.viewport.guiDragActive and eventType == QtCore.QEvent.Type.MouseButtonPress
                and event.button() == QtCore.Qt.MouseButton.RightButton):
            self.viewport.CancelGuiDrag()
            event.accept()
            return True
        if (eventType in (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress)
                and isinstance(watched, QtWidgets.QWidget)
                and (watched.window() is self or self.isAncestorOf(watched))
                and event.modifiers() in (QtCore.Qt.KeyboardModifier.NoModifier, QtCore.Qt.KeyboardModifier.KeypadModifier)
                and event.key() in (QtCore.Qt.Key.Key_1, QtCore.Qt.Key.Key_2, QtCore.Qt.Key.Key_3, QtCore.Qt.Key.Key_4)
                and not any(isinstance(widget, (QtWidgets.QLineEdit, QtWidgets.QAbstractSpinBox,
                                               QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit, QtWidgets.QComboBox))
                            for widget in (watched, QtWidgets.QApplication.focusWidget()))):
            if eventType == QtCore.QEvent.Type.KeyPress and not event.isAutoRepeat():
                self.sidebarTabs.setCurrentIndex(event.key() - QtCore.Qt.Key.Key_1)
            event.accept()
            return True
        if (eventType in (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress)
                and isinstance(watched, QtWidgets.QWidget)
                and (watched.window() is self or self.isAncestorOf(watched))
                and event.key() == QtCore.Qt.Key.Key_H
                and event.modifiers() in (QtCore.Qt.KeyboardModifier.NoModifier,
                                          QtCore.Qt.KeyboardModifier.ControlModifier,
                                          QtCore.Qt.KeyboardModifier.AltModifier)
                and not any(isinstance(widget, (QtWidgets.QLineEdit, QtWidgets.QAbstractSpinBox,
                                               QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit, QtWidgets.QComboBox))
                            for widget in (watched, QtWidgets.QApplication.focusWidget()))):
            if eventType == QtCore.QEvent.Type.KeyPress and not event.isAutoRepeat():
                command = (self.viewport.HideUnselected if event.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier else
                           self.viewport.UnhideObjects if event.modifiers() == QtCore.Qt.KeyboardModifier.AltModifier else self.viewport.HideSelection)
                command()
            event.accept()
            return True
        if (eventType in (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress)
                and isinstance(watched, QtWidgets.QWidget)
                and (watched.window() is self or self.isAncestorOf(watched))
                and (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier
                     and event.key() in (QtCore.Qt.Key.Key_X, QtCore.Qt.Key.Key_C, QtCore.Qt.Key.Key_V,
                                         QtCore.Qt.Key.Key_G)
                     or event.modifiers() == QtCore.Qt.KeyboardModifier.AltModifier and event.key() == QtCore.Qt.Key.Key_G)
                and not any(isinstance(widget, (QtWidgets.QLineEdit, QtWidgets.QAbstractSpinBox,
                                               QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit, QtWidgets.QComboBox))
                            for widget in (watched, QtWidgets.QApplication.focusWidget()))):
            if eventType == QtCore.QEvent.Type.KeyPress and not event.isAutoRepeat():
                self.editMenu.hide()
                self.viewport.objectContextMenu.hide()
                command = {QtCore.Qt.Key.Key_X: self.viewport.CutSelection,
                           QtCore.Qt.Key.Key_C: self.viewport.CopySelection,
                           QtCore.Qt.Key.Key_V: self.viewport.PasteSelection,
                           QtCore.Qt.Key.Key_G: self.viewport.UngroupSelection if event.modifiers() == QtCore.Qt.KeyboardModifier.AltModifier else self.viewport.GroupSelection}[event.key()]
                if event.key() == QtCore.Qt.Key.Key_V and event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                    self.viewport.PasteSelection(inPlace = True)
                else:
                    command()
            event.accept()
            return True
        if (eventType == QtCore.QEvent.Type.Wheel and self.viewport.openingPlacementMode is not None
                and isinstance(watched, QtWidgets.QWidget) and watched is not self.viewport
                and (watched.window() is self or self.isAncestorOf(watched))):
            delta = event.angleDelta().y() or event.pixelDelta().y()
            if delta:
                self.viewport.lastInteractionPosition = QtCore.QPointF(self.viewport.mapFromGlobal(event.globalPosition().toPoint()))
                self.viewport.CycleOpeningType(1 if delta < 0 else -1)
            event.accept()
            return True
        if (eventType in (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease)
                and isinstance(watched, QtWidgets.QWidget) and (watched.window() is self or self.isAncestorOf(watched))
                and event.key() in (QtCore.Qt.Key.Key_D, QtCore.Qt.Key.Key_S)):
            mode = "Door" if event.key() == QtCore.Qt.Key.Key_D else "Window"
            if eventType == QtCore.QEvent.Type.KeyRelease:
                if self.viewport.openingPlacementMode == mode:
                    if not event.isAutoRepeat():
                        self.viewport.EndOpeningMode()
                    event.accept()
                    return True
            elif (not any(isinstance(widget, (QtWidgets.QLineEdit, QtWidgets.QAbstractSpinBox, QtWidgets.QTextEdit,
                                             QtWidgets.QPlainTextEdit, QtWidgets.QComboBox))
                          for widget in (watched, QtWidgets.QApplication.focusWidget()))
                  and not event.modifiers() & (QtCore.Qt.KeyboardModifier.ControlModifier | QtCore.Qt.KeyboardModifier.MetaModifier)):
                if eventType == QtCore.QEvent.Type.KeyPress and not event.isAutoRepeat():
                    self.viewport.BeginOpeningMode(mode)
                    if self.viewport.openingPlacementMode is not None:
                        self.viewport.setFocus()
                event.accept()
                return True
        if (eventType in (QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease)
                and isinstance(watched, QtWidgets.QWidget) and watched.window() is self
                and event.key() == QtCore.Qt.Key.Key_Control and not event.isAutoRepeat()):
            self.viewport.controlHeld = eventType == QtCore.QEvent.Type.KeyPress
            if self.viewport.lastInteractionPosition is not None:
                modifiers = event.modifiers()
                if self.viewport.controlHeld:
                    modifiers |= QtCore.Qt.KeyboardModifier.ControlModifier
                else:
                    modifiers &= ~QtCore.Qt.KeyboardModifier.ControlModifier
                self.viewport.UpdateInteraction(self.viewport.lastInteractionPosition, modifiers)
        if (eventType in (QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease)
                and isinstance(watched, QtWidgets.QWidget) and watched.window() in (self, self.snapMenu)
                and event.key() == QtCore.Qt.Key.Key_Shift):
            modifiers = event.modifiers()
            if eventType == QtCore.QEvent.Type.KeyPress:
                modifiers |= QtCore.Qt.KeyboardModifier.ShiftModifier
            else:
                modifiers &= ~QtCore.Qt.KeyboardModifier.ShiftModifier
            self.viewport.UpdateMode(modifiers)
            if self.viewport.dragStart is not None and self.viewport.lastInteractionPosition is not None:
                self.viewport.UpdateInteraction(self.viewport.lastInteractionPosition, modifiers)
        if (eventType in (QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease)
                and isinstance(watched, QtWidgets.QWidget) and watched.window() in (self, self.snapMenu)
                and event.key() == QtCore.Qt.Key.Key_Alt and not event.isAutoRepeat()):
            self.altHeld = eventType == QtCore.QEvent.Type.KeyPress
            self.RefreshSnapState(event.modifiers())
        if eventType == QtCore.QEvent.Type.ApplicationDeactivate:
            self.viewport.StopDragPan()
            if self.viewport.isPanning:
                self.viewport.EndPan()
            if self.viewport.openingPlacementMode is not None:
                self.viewport.EndOpeningMode()
            self.altHeld = False
            self.viewport.controlHeld = False
            self.RefreshSnapState(QtCore.Qt.KeyboardModifier.NoModifier)
            self.viewport.UpdateMode(QtCore.Qt.KeyboardModifier.NoModifier)
        if (eventType in (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress)
                and isinstance(watched, QtWidgets.QWidget) and watched.window() in (self, self.editMenu)
                and not any(isinstance(widget, (QtWidgets.QLineEdit, QtWidgets.QAbstractSpinBox,
                                               QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit, QtWidgets.QComboBox))
                            for widget in (watched, QtWidgets.QApplication.focusWidget()))
                and event.key() == QtCore.Qt.Key.Key_Z
                and event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier):
            if eventType == QtCore.QEvent.Type.KeyPress:
                self.editMenu.hide()
                if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                    self.viewport.Redo()
                else:
                    self.viewport.Undo()
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def RefreshOpeningToolHighlight(self, openingType):
        for objectType, button in self.openingToolButtons.items():
            active = objectType is openingType
            if bool(button.property("placementActive")) != active:
                button.setProperty("placementActive", active)
                button.style().unpolish(button)
                button.style().polish(button)
                button.update()

    def SetSnapping(self, enabled):
        if enabled and not any(checkBox.isChecked() for checkBox in self.snapOptions.values()):
            checkBox = self.snapOptions["grid"]
            blocker = QtCore.QSignalBlocker(checkBox)
            checkBox.setChecked(True)
            del blocker
            self.viewport.gridSnapEnabled = True
        self.viewport.snapEnabled = enabled != self.altHeld
        self.RefreshSnapState()
        self.viewport.settingsChanged.emit()

    def RefreshSnapState(self, modifiers = None):
        # The button reflects temporary Alt inversion without changing the saved choice.
        blocker = QtCore.QSignalBlocker(self.snapButton)
        self.snapButton.setChecked(self.viewport.snapEnabled != self.altHeld)
        del blocker
        if modifiers is None:
            modifiers = QtWidgets.QApplication.keyboardModifiers()
        if self.altHeld:
            modifiers |= QtCore.Qt.KeyboardModifier.AltModifier
        else:
            modifiers &= ~QtCore.Qt.KeyboardModifier.AltModifier
        if self.viewport.lastInteractionPosition is not None:
            self.viewport.UpdateInteraction(self.viewport.lastInteractionPosition, modifiers)

    def SetConnectedOptions(self):
        self.viewport.connectedVerticesEnabled = self.connectedOptions["vertices"].isChecked()
        self.viewport.connectedObjectsEnabled = self.connectedOptions["objects"].isChecked()
        self.viewport.connectedEnabled = self.viewport.connectedVerticesEnabled or self.viewport.connectedObjectsEnabled
        if self.viewport.lastInteractionPosition is not None:
            self.viewport.UpdateInteraction(self.viewport.lastInteractionPosition, QtWidgets.QApplication.keyboardModifiers())
        self.viewport.settingsChanged.emit()

    def SetSnapOptions(self):
        for button in self.snapOptions.values():
            if button.isChecked():
                button.iconLabel.setPixmap(HeaderIcon("Check").pixmap(18, 18))
            else:
                button.iconLabel.clear()
        self.viewport.gridSnapEnabled = self.snapOptions["grid"].isChecked()
        self.viewport.vertexSnapEnabled = self.snapOptions["vertices"].isChecked()
        self.viewport.cornerSnapEnabled = self.snapOptions["corners"].isChecked()
        self.viewport.midpointSnapEnabled = self.snapOptions["midpoints"].isChecked()
        self.viewport.alignmentSnapEnabled = self.snapOptions["alignment"].isChecked()
        if not any(checkBox.isChecked() for checkBox in self.snapOptions.values()):
            self.viewport.snapEnabled = False
        self.RefreshSnapState()
        self.viewport.settingsChanged.emit()

    def ToggleViewportOnlyMode(self):
        self.SetViewportOnlyMode(not self.viewportOnlyMode)

    def SetViewportOnlyMode(self, enabled):
        if self.viewportOnlyMode == enabled:
            return
        self.viewport.CancelInteraction()
        self.viewport.EndOpeningMode()
        if enabled:
            self.savedSplitterSizes = self.mainSplitter.sizes()
        self.viewportOnlyMode = enabled
        self.sidebarPanel.setVisible(not enabled)
        self.centralWidget().layout().setContentsMargins(*(0, 0, 0, 0) if enabled else (12, 12, 12, 12))
        self.fullscreenButton.setIcon(UiIcon("fullscreen_exit" if enabled else "fullscreen"))
        self.fullscreenButton.setToolTip("Exit fullscreen (F or Esc)" if enabled else "Fullscreen (F)")
        if not enabled and self.savedSplitterSizes is not None:
            self.mainSplitter.setSizes(self.savedSplitterSizes)
            self.savedSplitterSizes = None
        self.viewport.setFocus()

    def SetWallWidth(self, index):
        self.viewport.newWallWidth = self.wallWidthSelector.widths[index] * 10.0
        self.viewport.settingsChanged.emit()
