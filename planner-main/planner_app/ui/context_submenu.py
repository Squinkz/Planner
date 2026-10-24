"""Submenu behavior copied from Stacker app/gui/widgets.py."""

from PySide6 import QtCore, QtGui, QtWidgets


class ContextSubmenuController(QtCore.QObject):
    def __init__(self, owner, rootMenu, parentButton, populateCallback):
        super().__init__(parentButton)
        self.owner = owner
        self.rootMenu = rootMenu
        self.parentButton = parentButton
        self.populateCallback = populateCallback
        self.childMenu = None
        self.leaveParentTimer = QtCore.QTimer(self)
        self.leaveParentTimer.setSingleShot(True)
        self.leaveParentTimer.setInterval(80)
        self.leaveParentTimer.timeout.connect(self.HideIfPointerLeftMenus)
        self.leaveChildTimer = QtCore.QTimer(self)
        self.leaveChildTimer.setSingleShot(True)
        self.leaveChildTimer.setInterval(500)
        self.leaveChildTimer.timeout.connect(self.HideIfPointerLeftChild)
        self.pointerWatchTimer = QtCore.QTimer(self)
        self.pointerWatchTimer.setInterval(25)
        self.pointerWatchTimer.timeout.connect(self.HideIfPointerLeftMenus)
        self.parentButton.installEventFilter(self)
        self.rootMenu.installEventFilter(self)
        self.rootMenu.aboutToHide.connect(self.HideChildMenu)

    def eventFilter(self, watched, event):
        if watched is QtWidgets.QApplication.instance():
            if event.type() == QtCore.QEvent.Type.MouseMove:
                if (
                    self.childMenu is not None
                    and not self.PointerInWidget(self.parentButton)
                    and not self.PointerInWidget(self.childMenu)
                ):
                    self.HideChildMenu()
                return False
            if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                if self.childMenu is not None:
                    inParent = self.PointerInWidget(self.parentButton)
                    inChild = self.PointerInWidget(self.childMenu)
                    inRoot = self.PointerInWidget(self.rootMenu)
                    if not inChild:
                        self.HideChildMenu()
                        if not inParent and not inRoot:
                            self.rootMenu.hide()
                return False

        if watched is self.rootMenu:
            if event.type() == QtCore.QEvent.Type.MouseButtonPress and self.childMenu is not None:
                self.HideChildMenu()
                return False

        if watched is self.parentButton:
            if event.type() == QtCore.QEvent.Type.Enter:
                self.SetParentForcedIdle(False)
                self.ShowChildMenu()
                return False
            if event.type() == QtCore.QEvent.Type.Leave:
                if not self.PointerInWidget(self.childMenu):
                    self.HideChildMenu()
                return False
            if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                self.SetParentForcedIdle(False)
                self.ShowChildMenu()
                return True
            if event.type() == QtCore.QEvent.Type.MouseButtonRelease:
                return True
        elif watched is self.childMenu:
            if event.type() == QtCore.QEvent.Type.Enter:
                self.pointerWatchTimer.stop()
                self.leaveChildTimer.stop()
                self.parentButton.setChecked(True)
                return False
            if event.type() == QtCore.QEvent.Type.Leave:
                self.leaveChildTimer.start()
                return False
        return super().eventFilter(watched, event)

    def ShowChildMenu(self):
        self.leaveParentTimer.stop()
        self.leaveChildTimer.stop()
        if self.childMenu is None:
            self.childMenu = QtWidgets.QMenu(self.rootMenu)
            self.childMenu.setObjectName("viewportContextMenu")
            self.childMenu.installEventFilter(self)
            self.childMenu.aboutToHide.connect(self.ChildMenuAboutToHide)
            self.populateCallback(self.childMenu)
            QtWidgets.QApplication.instance().installEventFilter(self)
            self.pointerWatchTimer.start()
        self.parentButton.setChecked(True)
        self.SetParentForcedIdle(False)
        self.childMenu.popup(self.ChildMenuPosition())

    def ChildMenuPosition(self):
        if self.childMenu is None:
            return QtCore.QPoint()

        parentTopLeft = self.parentButton.mapToGlobal(QtCore.QPoint(0, 0))
        parentRect = QtCore.QRect(parentTopLeft, self.parentButton.size())
        size = self.childMenu.sizeHint()
        screen = QtGui.QGuiApplication.screenAt(parentRect.center()) or QtGui.QGuiApplication.primaryScreen()
        available = screen.availableGeometry() if screen else QtWidgets.QApplication.primaryScreen().availableGeometry()
        x = parentRect.right() + 1
        if x + size.width() > available.right():
            x = parentRect.left() - size.width()
        x = max(available.left(), x)

        y = parentRect.top()
        if y + size.height() > available.bottom():
            y = available.bottom() - size.height()
        y = max(available.top(), y)
        return QtCore.QPoint(x, y)

    def PointerInWidget(self, widget):
        if widget is None or not widget.isVisible():
            return False
        position = QtGui.QCursor.pos()
        return widget.rect().contains(widget.mapFromGlobal(position))

    def HideIfPointerLeftMenus(self):
        if self.PointerInWidget(self.parentButton):
            return
        if self.PointerInWidget(self.childMenu):
            self.pointerWatchTimer.stop()
            return
        self.HideChildMenu()

    def HideIfPointerLeftChild(self):
        if self.PointerInWidget(self.childMenu) or self.PointerInWidget(self.parentButton):
            return
        self.HideChildMenu()

    def HideChildMenu(self):
        self.leaveParentTimer.stop()
        self.leaveChildTimer.stop()
        self.pointerWatchTimer.stop()
        if self.childMenu is not None:
            self.childMenu.hide()
            self.childMenu.deleteLater()
            self.childMenu = None
        QtWidgets.QApplication.instance().removeEventFilter(self)
        self.parentButton.setChecked(False)
        self.parentButton.setDown(False)
        self.parentButton.clearFocus()
        if not self.PointerInWidget(self.parentButton):
            self.SetParentForcedIdle(True)
        self.parentButton.style().unpolish(self.parentButton)
        self.parentButton.style().polish(self.parentButton)
        self.parentButton.update()
        self.rootMenu.update()

    def SetParentForcedIdle(self, enabled):
        self.parentButton.setProperty("forceIdle", bool(enabled))
        self.parentButton.style().unpolish(self.parentButton)
        self.parentButton.style().polish(self.parentButton)
        self.parentButton.update()

    def ChildMenuAboutToHide(self):
        if QtWidgets.QApplication.mouseButtons() == QtCore.Qt.MouseButton.NoButton:
            return
        if self.PointerInWidget(self.parentButton) or self.PointerInWidget(self.rootMenu):
            return
        QtCore.QTimer.singleShot(0, self.rootMenu.hide)


