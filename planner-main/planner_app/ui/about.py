"""Stacker-style About presentation with Planner resources."""
import html
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.paths import appDirectory, assetsDirectory, fontsDirectory
from planner_app.version import displayVersion
from planner_app.graphics.icons import UiIcon
from planner_app.graphics.palette import themeColors
from planner_app.graphics.theme import HeaderIcon


class ClickDismissFilter(QtCore.QObject):
    def __init__(self, dialog, actionCallbacks = None):
        super().__init__(dialog)
        self.dialog = dialog
        self.pendingUrl = None
        self.pendingAction = None
        self.actionCallbacks = actionCallbacks or {}

    def UrlForWidget(self, widget):
        while widget is not None:
            url = widget.property("aboutUrl")
            if url:
                return url
            widget = widget.parentWidget()
        return None

    def UrlForEvent(self, watched):
        if isinstance(watched, QtWidgets.QWidget):
            url = self.UrlForWidget(watched)
            if url:
                return url

        widget = QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())
        if widget is not None:
            return self.UrlForWidget(widget)

        return None

    def ActionForWidget(self, widget):
        while widget is not None:
            actionName = widget.property("aboutAction")
            if actionName:
                return actionName
            widget = widget.parentWidget()
        return None

    def ActionForEvent(self, watched):
        if isinstance(watched, QtWidgets.QWidget):
            actionName = self.ActionForWidget(watched)
            if actionName:
                return actionName

        widget = QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())
        if widget is not None:
            return self.ActionForWidget(widget)

        return None

    def OpenUrl(self, url):
        if not url:
            return False
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))
        return True

    def TriggerAction(self, actionName):
        callback = self.actionCallbacks.get(actionName)
        if not callback:
            return False
        callback()
        return True

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Type.MouseButtonPress:
            url = self.UrlForEvent(watched)
            if url:
                self.pendingUrl = url
                return True
            actionName = self.ActionForEvent(watched)
            if actionName:
                self.pendingAction = actionName
                return True
            self.dialog.accept()
            return True

        if event.type() == QtCore.QEvent.Type.MouseButtonRelease:
            url = self.pendingUrl or self.UrlForEvent(watched)
            actionName = self.pendingAction or self.ActionForEvent(watched)
            self.pendingUrl = None
            self.pendingAction = None
            if self.OpenUrl(url):
                self.dialog.accept()
                return True
            if self.TriggerAction(actionName):
                self.dialog.accept()
                return True
            self.dialog.accept()
            return True

        if event.type() == QtCore.QEvent.Type.MouseButtonDblClick:
            url = self.UrlForEvent(watched)
            if self.OpenUrl(url):
                self.dialog.accept()
                return True
            actionName = self.ActionForEvent(watched)
            if self.TriggerAction(actionName):
                self.dialog.accept()
                return True
            self.dialog.accept()
            return True

        return super().eventFilter(watched, event)


class AboutDialog(QtWidgets.QDialog):
    def __init__(self, mainWindow):
        super().__init__(mainWindow)
        self.setWindowTitle("About Planner")
        self.setWindowIcon(HeaderIcon("About"))
        self.setWindowFlag(QtCore.Qt.WindowType.FramelessWindowHint, True)
        self.setMinimumWidth(600)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 18)
        layout.setSpacing(12)

        self.logoLabel = QtWidgets.QLabel()
        self.logoLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.logoLabel.setPixmap(QtGui.QIcon(str(assetsDirectory / "planner.svg")).pixmap(300, 300))
        layout.addWidget(self.logoLabel, 0, QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(8)
        versionLabel = QtWidgets.QLabel(displayVersion)
        versionLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        versionLabel.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(versionLabel)

        copyrightRow = QtWidgets.QHBoxLayout()
        copyrightRow.setContentsMargins(0, 0, 0, 0)
        copyrightRow.setSpacing(6)
        copyrightRow.addStretch(1)
        copyrightIcon = QtWidgets.QLabel()
        copyrightIcon.setFixedSize(18, 18)
        copyrightIcon.setPixmap(UiIcon("about_copyright").pixmap(18, 18))
        copyrightRow.addWidget(copyrightIcon)
        copyrightLabel = QtWidgets.QLabel("2026 Dieter Stassen")
        copyrightLabel.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        copyrightRow.addWidget(copyrightLabel)
        copyrightRow.addStretch(1)
        layout.addLayout(copyrightRow)

        layout.addSpacing(8)
        descriptionLabel = QtWidgets.QLabel(
            "Build your dream,\ndesign your space.\n\nMake your house a Home.")
        descriptionLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        descriptionLabel.setWordWrap(True)
        descriptionLabel.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        descriptionRow = QtWidgets.QHBoxLayout()
        descriptionRow.setContentsMargins(64, 0, 64, 0)
        descriptionRow.addWidget(descriptionLabel)
        layout.addLayout(descriptionRow)

        layout.addSpacing(32)
        linkRow = QtWidgets.QHBoxLayout()
        linkRow.setContentsMargins(0, 0, 0, 0)
        linkRow.setSpacing(32)
        linkRow.addStretch(1)
        linkRow.addWidget(self.CreateLinkItem("about_github", "Github", url = "https://github.com/Squinkz/Planner"))
        linkRow.addSpacing(8)
        linkRow.addWidget(self.CreateLinkItem("about_issue", "Report Issue", url = "https://github.com/Squinkz/Planner/issues"))
        linkRow.addSpacing(8)
        linkRow.addWidget(self.CreateLinkItem("about_licenses", "Licenses", actionName = "licenses"))
        linkRow.addStretch(1)
        layout.addLayout(linkRow)
        layout.addSpacing(24)

        self.dismissFilter = ClickDismissFilter(self, {"licenses": mainWindow.ShowLicenses})
        app = QtWidgets.QApplication.instance()
        app.installEventFilter(self.dismissFilter)
        self.finished.connect(lambda result: app.removeEventFilter(self.dismissFilter))

    def CreateLinkItem(self, iconName, text, url = "", actionName = ""):
        item = QtWidgets.QWidget()
        item.setAccessibleName(text)
        if url:
            item.setProperty("aboutUrl", url)
        if actionName:
            item.setProperty("aboutAction", actionName)
        item.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        layout = QtWidgets.QHBoxLayout(item)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        iconLabel = QtWidgets.QLabel()
        iconLabel.setFixedSize(28, 28)
        iconLabel.setPixmap(UiIcon(iconName).pixmap(28, 28))
        layout.addWidget(iconLabel)
        color = themeColors["text"]
        content = html.escape(text)
        textLabel = QtWidgets.QLabel(
            f'<a href="{url}" style="color: {color}; text-decoration: underline;">{content}</a>' if url else
            f'<span style="color: {color}; text-decoration: underline;">{content}</span>')
        if url:
            textLabel.setOpenExternalLinks(True)
            textLabel.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextBrowserInteraction)
        layout.addWidget(textLabel)
        return item


class LicensesDialog(QtWidgets.QDialog):
    def __init__(self, mainWindow):
        super().__init__(mainWindow)
        self.setWindowTitle("Licenses")
        self.setWindowIcon(HeaderIcon("About"))
        self.setWindowFlag(QtCore.Qt.WindowType.WindowMinMaxButtonsHint, True)
        self.resize(760, 560)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        text = QtWidgets.QPlainTextEdit()
        text.setReadOnly(True)
        text.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
        notices = (appDirectory / "LICENSES.txt", appDirectory / "COPYING",
                   appDirectory / "ASSET_LICENSE.txt", appDirectory / "BRANDING_LICENSE.txt", fontsDirectory / "OFL.txt",
                   fontsDirectory / "OFL-D-DIN.txt", fontsDirectory / "OFL-DraftingSmallCaps.txt", fontsDirectory / "FONTLOG.txt",
                   appDirectory / "vendor" / "upng" / "UPNG-LICENSE", appDirectory / "vendor" / "upng" / "PAKO-LICENSE")
        sections = []
        for path in notices:
            try:
                sections.append(path.name + "\n\n" + path.read_text(encoding = "utf-8"))
            except OSError:
                sections.append(path.name + " could not be loaded.")
        text.setPlainText("\n\n".join(sections))
        layout.addWidget(text, 1)
        buttonRow = QtWidgets.QHBoxLayout()
        buttonRow.addStretch(1)
        closeButton = QtWidgets.QPushButton("Close")
        closeButton.clicked.connect(self.close)
        buttonRow.addWidget(closeButton)
        layout.addLayout(buttonRow)


