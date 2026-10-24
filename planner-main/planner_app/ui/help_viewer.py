"""Modeless navigation for bundled, portable Markdown user help."""
from pathlib import Path
import math
import re
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.paths import appDirectory
from planner_app.graphics.palette import themeColors
from planner_app.graphics.theme import HeaderIcon
from planner_app.graphics.icons import UiIcon


helpDirectory = appDirectory / "docs" / "help"
inlinePaddingProperty = QtGui.QTextFormat.Property.UserProperty.value + 1
tableHeaderStyledProperty = QtGui.QTextFormat.Property.UserProperty.value + 2


class HelpScrollAnchor(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedSize(36, 36)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.hide()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor(themeColors["controlBackground"]))
        painter.drawEllipse(QtCore.QRectF(1, 1, 34, 34))
        painter.setPen(QtGui.QPen(QtGui.QColor(themeColors["text"]), 2.5,
                                 QtCore.Qt.PenStyle.SolidLine, QtCore.Qt.PenCapStyle.RoundCap,
                                 QtCore.Qt.PenJoinStyle.RoundJoin))
        for points in (((13, 11), (18, 6), (23, 11)), ((13, 25), (18, 30), (23, 25))):
            painter.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in points]))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor(themeColors["text"]))
        painter.drawEllipse(QtCore.QPointF(18, 18), 2.5, 2.5)


class HelpBrowser(QtWidgets.QTextBrowser):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QtGui.QPainter(self.viewport())
        color = QtGui.QColor(themeColors["text"])
        color.setAlphaF(.3)
        painter.setPen(QtGui.QPen(color, 1))
        document = self.document()
        layout = document.documentLayout()
        offset = QtCore.QPointF(-self.horizontalScrollBar().value(), -self.verticalScrollBar().value())
        block = document.begin()
        while block.isValid():
            if block.blockFormat().headingLevel() in (1, 2):
                rect = layout.blockBoundingRect(block).translated(offset)
                y = rect.bottom() + 5
                if event.rect().top() <= y <= event.rect().bottom():
                    painter.drawLine(QtCore.QPointF(rect.left(), y), QtCore.QPointF(rect.right(), y))
            block = block.next()

    def loadResource(self, resourceType, name):
        resource = super().loadResource(resourceType, name)
        if resourceType != QtGui.QTextDocument.ResourceType.MarkdownResource or not isinstance(resource, QtCore.QByteArray):
            return resource
        source = bytes(resource).decode("utf-8-sig")
        marker = "\ue000"
        while marker in source:
            marker += "\ue001"
        self.markdownBreakMarker = marker
        # Let Qt parse code spans, fences, lists and formatting normally. A
        # temporary marker prevents its importer from turning hard breaks into
        # separate paragraphs. Restore literal backslashes in code after import.
        source = re.sub(r"(\\+)(\r?\n)", lambda match:
                        match[1][:-1] + marker + match[2] if len(match[1]) % 2 else match[0], source)
        return QtCore.QByteArray(source.encode("utf-8"))

    def RestoreMarkdownBreaks(self):
        marker = getattr(self, "markdownBreakMarker", None)
        if marker is None:
            return
        document = self.document()
        cursor = document.find(marker)
        while not cursor.isNull():
            blockFormat = cursor.blockFormat()
            isCode = cursor.charFormat().fontFixedPitch() or any(blockFormat.hasProperty(property) for property in
                (QtGui.QTextFormat.Property.BlockCodeFence, QtGui.QTextFormat.Property.BlockCodeLanguage))
            following = QtGui.QTextCursor(cursor)
            following.setPosition(cursor.selectionEnd())
            following.movePosition(QtGui.QTextCursor.MoveOperation.NextCharacter, QtGui.QTextCursor.MoveMode.KeepAnchor)
            if not isCode and following.selectedText() == " ":
                cursor.setPosition(following.selectionEnd(), QtGui.QTextCursor.MoveMode.KeepAnchor)
                cursor.insertText("\u2028")
            else:
                cursor.insertText("\\")
            cursor = document.find(marker, cursor)

    def event(self, event):
        if event.type() == QtCore.QEvent.Type.Wheel:
            # Viewport margins belong to the scroll-area frame, so Qt does not
            # route their wheel events through QTextBrowser's viewport handler.
            self.wheelEvent(event)
            return True
        return super().event(event)

    def createMimeDataFromSelection(self):
        # Rendering-only padding must not appear when copying instructions.
        document = QtGui.QTextDocument()
        cursor = QtGui.QTextCursor(document)
        cursor.insertFragment(QtGui.QTextDocumentFragment(self.textCursor()))
        padding = []
        block = document.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.charFormat().boolProperty(inlinePaddingProperty):
                    padding.append((fragment.position(), fragment.length()))
                iterator += 1
            block = block.next()
        for position, length in reversed(padding):
            cursor.setPosition(position)
            cursor.setPosition(position + length, QtGui.QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
        mime = QtCore.QMimeData()
        mime.setText(document.toPlainText())
        mime.setHtml(document.toHtml())
        return mime


class HelpWindow(QtWidgets.QDialog):
    def __init__(self, mainWindow):
        super().__init__(mainWindow)
        self.imageAnimations = {}
        self.autoScrollOrigin = None
        self.autoScrollDragging = False
        self.autoScrollCancelButton = None
        self.autoScrollRemainder = 0.0
        self.autoScrollClock = QtCore.QElapsedTimer()
        self.autoScrollTimer = QtCore.QTimer(self)
        self.autoScrollTimer.setInterval(16)
        self.autoScrollTimer.timeout.connect(self.UpdateAutoScroll)
        self.autoScrollAnchor = HelpScrollAnchor(self)
        self.setWindowFlag(QtCore.Qt.WindowType.WindowMinMaxButtonsHint, True)
        self.setWindowTitle("Planner Help")
        self.setWindowIcon(HeaderIcon("Help"))
        self.setModal(False)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        navigation = QtWidgets.QHBoxLayout()
        self.navigation = navigation
        navigation.setSpacing(6)
        self.backButton = QtWidgets.QPushButton()
        self.forwardButton = QtWidgets.QPushButton()
        self.homeButton = QtWidgets.QPushButton()
        for button, name, icon, rotation in ((self.backButton, "Back", "handle_up", -90),
                                             (self.forwardButton, "Forward", "handle_up", 90),
                                             (self.homeButton, "Home", "home", 0)):
            button.setObjectName("settingsIconButton")
            button.setIcon(UiIcon(icon, rotation = rotation))
            button.setIconSize(QtCore.QSize(24, 24))
            button.setFixedSize(32, 32)
            button.setAutoDefault(False)
            button.setDefault(False)
            button.setAccessibleName("Help " + name)
            button.setToolTip(name)
            navigation.addWidget(button)
        navigation.addStretch(1)
        layout.addLayout(navigation)
        self.browser = HelpBrowser()
        self.browser.setAccessibleName("Help document")
        self.browser.setBackgroundRole(QtGui.QPalette.ColorRole.Window)
        self.browser.setAutoFillBackground(True)
        self.browser.viewport().setObjectName("helpTextViewport")
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        # Polish before importing Markdown: otherwise the application stylesheet
        # changes the font after Qt has calculated paragraph spacing on first load.
        self.browser.setStyleSheet("QTextBrowser { font-size: 11pt; }")
        self.browser.ensurePolished()
        font = self.browser.font()
        self.browser.setFont(font)
        self.browser.document().setDefaultFont(font)
        self.browser.document().setDocumentMargin(20)
        self.imageResizeTimer = QtCore.QTimer(self)
        self.imageResizeTimer.setSingleShot(True)
        self.imageResizeTimer.timeout.connect(self.ResizeImages)
        self.browser.viewport().installEventFilter(self)
        navigation.setContentsMargins(self.browser.contentsMargins().left() + 20, 0, 0, 0)
        layout.addWidget(self.browser, 1)
        self.statusLabel = QtWidgets.QLabel()
        self.statusLabel.setWordWrap(True)
        self.statusLabel.hide()
        layout.addWidget(self.statusLabel)
        self.backButton.clicked.connect(self.browser.backward)
        self.forwardButton.clicked.connect(self.browser.forward)
        self.homeButton.clicked.connect(lambda checked = False: self.ShowPage("README.md"))
        self.browser.backwardAvailable.connect(self.backButton.setEnabled)
        self.browser.forwardAvailable.connect(self.forwardButton.setEnabled)
        self.browser.anchorClicked.connect(self.OpenLink)
        self.browser.sourceChanged.connect(self.PageChanged)
        self.finished.connect(lambda result: self.browser.clearHistory())
        self.finished.connect(self.StopAnimations)
        self.backButton.setEnabled(False)
        self.forwardButton.setEnabled(False)
        self.helpShortcut = QtGui.QShortcut(QtGui.QKeySequence("F1"), self)
        self.helpShortcut.activated.connect(lambda: self.ShowPage("README.md"))
        for standardKey, deviceKey, action in ((QtGui.QKeySequence.StandardKey.Back, QtCore.Qt.Key.Key_Back, self.browser.backward),
                                               (QtGui.QKeySequence.StandardKey.Forward, QtCore.Qt.Key.Key_Forward, self.browser.forward)):
            keys = QtGui.QKeySequence.keyBindings(standardKey)
            deviceSequence = QtGui.QKeySequence(deviceKey)
            if deviceSequence not in keys:
                keys.append(deviceSequence)
            shortcut = QtGui.QShortcut(self)
            shortcut.setKeys(keys)
            shortcut.activated.connect(action)
        for widget in [self] + self.findChildren(QtWidgets.QWidget):
            widget.installEventFilter(self)
        self.RefreshTheme()
        available = self.screen().availableGeometry()
        width, height = min(880, max(1, available.width() - 40)), min(720, max(1, available.height() - 60))
        self.setMinimumSize(min(420, width), min(300, height))
        self.resize(width, height)
        center = mainWindow.frameGeometry().center()
        self.move(max(available.left(), min(center.x() - width // 2, available.right() - width + 1)),
                  max(available.top(), min(center.y() - height // 2, available.bottom() - height + 1)))
        # Give the first document its final reading width before importing it.
        # Otherwise hidden-child defaults cause an extra image/text relayout.
        self.layout().activate()

    def RefreshTheme(self):
        browserStyle = f'QTextBrowser {{ font-size: 11pt; background: {themeColors["windowBackground"]}; }}'
        viewportStyle = f'QWidget#helpTextViewport {{ background: {themeColors["fieldBackground"]}; }}'
        if self.browser.styleSheet() != browserStyle:
            self.browser.setStyleSheet(browserStyle)
        if self.browser.viewport().styleSheet() != viewportStyle:
            self.browser.viewport().setStyleSheet(viewportStyle)
        colors = self.browser.palette()
        for role, color in ((QtGui.QPalette.ColorRole.Base, "fieldBackground"),
                            (QtGui.QPalette.ColorRole.Text, "text"),
                            (QtGui.QPalette.ColorRole.Link, "info"),
                            (QtGui.QPalette.ColorRole.LinkVisited, "info")):
            colors.setColor(role, QtGui.QColor(themeColors[color]))
        self.browser.setPalette(colors)
        # Qt's Markdown importer gives links an explicit blue foreground, which
        # overrides the palette. Restyle native anchor formats for either theme.
        document = self.browser.document()
        block = document.begin()
        anchors = []
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.charFormat().isAnchor():
                    anchors.append((fragment.position(), fragment.length()))
                iterator += 1
            block = block.next()
        linkFormat = QtGui.QTextCharFormat()
        linkFormat.setForeground(QtGui.QColor(themeColors["info"]))
        linkFormat.setFontUnderline(True)
        for position, length in anchors:
            cursor = QtGui.QTextCursor(document)
            cursor.setPosition(position)
            cursor.setPosition(position + length, QtGui.QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(linkFormat)
        self.StyleCode()
        self.browser.viewport().update()

    def StyleCode(self):
        """Shade native Markdown code formats, including after a theme change."""
        background = QtGui.QColor(themeColors["fieldBackground"])
        foreground = QtGui.QColor(themeColors["text"])
        codeBackground = QtGui.QColor(*(round(backgroundComponent * .92 + textComponent * .08)
                                       for backgroundComponent, textComponent in zip(background.getRgb()[:3], foreground.getRgb()[:3])))
        document = self.browser.document()
        if document.isEmpty():
            return
        codeFont = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)
        codeFormat = QtGui.QTextCharFormat()
        codeFormat.setFontFamilies([codeFont.family()])
        codeFormat.setFontFixedPitch(True)
        codeFormat.setFontPointSize(document.defaultFont().pointSizeF())
        cursor = QtGui.QTextCursor(document)
        cursor.beginEditBlock()
        block = document.begin()
        while block.isValid():
            blockFormat = block.blockFormat()
            isCode = any(blockFormat.hasProperty(property) for property in
                         (QtGui.QTextFormat.Property.BlockCodeFence, QtGui.QTextFormat.Property.BlockCodeLanguage))
            if isCode:
                blockFormat.setBackground(codeBackground)
                cursor.setPosition(block.position())
                cursor.setBlockFormat(blockFormat)
                cursor.movePosition(QtGui.QTextCursor.MoveOperation.EndOfBlock, QtGui.QTextCursor.MoveMode.KeepAnchor)
                cursor.mergeCharFormat(codeFormat)
            else:
                spans = []
                iterator = block.begin()
                while not iterator.atEnd():
                    fragment = iterator.fragment()
                    if fragment.charFormat().fontFixedPitch():
                        if spans and spans[-1][0] + spans[-1][1] == fragment.position():
                            spans[-1] = (spans[-1][0], spans[-1][1] + fragment.length())
                        else:
                            spans.append((fragment.position(), fragment.length()))
                    iterator += 1
                inlineFormat = QtGui.QTextCharFormat(codeFormat)
                inlineFormat.setFontPointSize(document.defaultFont().pointSizeF() + 1)
                inlineFormat.setFontWeight(QtGui.QFont.Weight.DemiBold)
                inlineFormat.setBackground(codeBackground)
                paddingFormat = QtGui.QTextCharFormat(inlineFormat)
                paddingFormat.setProperty(inlinePaddingProperty, True)
                # A thin space on each side reserves a few pixels in Qt's native
                # text layout. The Markdown source and copied text stay clean.
                for position, length in reversed(spans):
                    cursor.setPosition(position)
                    cursor.setPosition(position + length, QtGui.QTextCursor.MoveMode.KeepAnchor)
                    cursor.mergeCharFormat(inlineFormat)
                    cursor.setPosition(position)
                    cursor.setPosition(position + 1, QtGui.QTextCursor.MoveMode.KeepAnchor)
                    if not cursor.charFormat().boolProperty(inlinePaddingProperty):
                        cursor.setPosition(position + length)
                        cursor.insertText("\u2009", paddingFormat)
                        cursor.setPosition(position)
                        cursor.insertText("\u2009", paddingFormat)
            block = block.next()
        cursor.endEditBlock()

    def ShowPage(self, page = "README.md", fragment = ""):
        path = (helpDirectory / page).resolve()
        if path == (helpDirectory / "about").resolve():
            self.parentWidget().ShowAbout()
            return True
        if not path.is_relative_to(helpDirectory.resolve()) or path.suffix.lower() != ".md" or not path.is_file():
            self.statusLabel.setText("This help page is unavailable. Use Home to return to the guide.")
            self.statusLabel.show()
            return False
        self.statusLabel.hide()
        url = QtCore.QUrl.fromLocalFile(str(path))
        url.setFragment(fragment)
        # Qt handles Markdown, relative resources and back/forward scroll history.
        # Help uses portable Markdown plus conventional pipe tables.
        document = self.browser.document()
        layoutEnabled = document.isLayoutEnabled()
        document.setLayoutEnabled(False)
        try:
            self.browser.setSource(url, QtGui.QTextDocument.ResourceType.MarkdownResource)
        finally:
            document.setLayoutEnabled(layoutEnabled)
        if not fragment:
            self.browser.verticalScrollBar().setValue(0)
        return True

    def OpenLink(self, link):
        url = self.browser.source().resolved(link)
        if url.scheme() in ("https", "http"):
            QtGui.QDesktopServices.openUrl(url)
        elif url.isLocalFile():
            self.ShowPage(Path(url.toLocalFile()), url.fragment())

    def StyleDocument(self):
        """Apply the reading contract to native blocks without changing Markdown."""
        document = self.browser.document()
        font = document.defaultFont()
        em = font.pointSizeF() * self.browser.logicalDpiY() / 72
        headings = {1: (2, 32, 20), 2: (1.5, 28, 14), 3: (1.25, 24, 10),
                    4: (1.1, 20, 8), 5: (1, 18, 8), 6: (1, 18, 8)}
        cursor = QtGui.QTextCursor(document)
        cursor.beginEditBlock()
        block = document.begin()
        while block.isValid():
            cursor.setPosition(block.position())
            blockFormat = block.blockFormat()
            level = blockFormat.headingLevel()
            inTable = cursor.currentTable() is not None
            imageOnly = bool(block.text()) and not block.text().replace("\ufffc", "").strip()
            codeProperties = (QtGui.QTextFormat.Property.BlockCodeFence, QtGui.QTextFormat.Property.BlockCodeLanguage)
            isCode = any(blockFormat.hasProperty(property) for property in codeProperties)
            lineHeight = em * 1.5
            top, bottom = 0, 12
            if level:
                scale, top, bottom = headings[level]
                top = 0 if block == document.begin() else top
                lineHeight = em * scale * 1.25
                iterator = block.begin()
                fragments = []
                while not iterator.atEnd():
                    fragment = iterator.fragment()
                    fragments.append((fragment.position(), fragment.length(), fragment.charFormat()))
                    iterator += 1
                for position, length, textFormat in fragments:
                    textFormat.clearProperty(QtGui.QTextFormat.Property.FontSizeAdjustment)
                    textFormat.setFontPointSize(font.pointSizeF() * scale)
                    textFormat.setFontWeight(QtGui.QFont.Weight.DemiBold)
                    cursor.setPosition(position)
                    cursor.setPosition(position + length, QtGui.QTextCursor.MoveMode.KeepAnchor)
                    cursor.setCharFormat(textFormat)
            elif isCode:
                previous, following = block.previous(), block.next()
                top = 0 if previous.isValid() and any(previous.blockFormat().hasProperty(property) for property in codeProperties) else 8
                bottom = 0 if following.isValid() and any(following.blockFormat().hasProperty(property) for property in codeProperties) else 16
                blockFormat.setLeftMargin(10)
                blockFormat.setRightMargin(10)
                lineHeight = em * 1.4
            elif imageOnly:
                top, bottom = 8, 16
            elif block.textList() is not None:
                bottom = 6
            tableSpacer = (not inTable and not isCode and not block.text()
                           and any(neighbor.isValid() and QtGui.QTextCursor(neighbor).currentTable() is not None
                                   for neighbor in (block.previous(), block.next())))
            if tableSpacer:
                top, bottom = 0, 0
            if inTable:
                top, bottom = 0, 0
            blockFormat.setTopMargin(top)
            blockFormat.setBottomMargin(bottom)
            # MinimumHeight retains the full height of inline images and tall
            # glyphs, while establishing an em-based reading rhythm for text.
            if tableSpacer:
                # QTextDocument needs a block outside a table, but it must not
                # add a full empty paragraph to the table's own spacing.
                blockFormat.setLineHeight(1, QtGui.QTextBlockFormat.LineHeightTypes.FixedHeight.value)
                spacerFormat = QtGui.QTextCharFormat()
                spacerFormat.setFontPointSize(1)
                cursor.setBlockCharFormat(spacerFormat)
            elif isCode:
                blockFormat.setLineHeight(100, QtGui.QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            else:
                blockFormat.setLineHeight(lineHeight, QtGui.QTextBlockFormat.LineHeightTypes.MinimumHeight.value)
            cursor.setBlockFormat(blockFormat)
            block = block.next()
        frames = list(document.rootFrame().childFrames())
        while frames:
            frame = frames.pop()
            frames.extend(frame.childFrames())
            if not isinstance(frame, QtGui.QTextTable):
                continue
            tableFormat = frame.format()
            # Qt imports Markdown headers without setting headerRowCount.
            # Mark processed tables so a blank body row is never mistaken for
            # another header when styling runs again.
            if not tableFormat.boolProperty(tableHeaderStyledProperty) and frame.rows() > 1:
                emptyHeader = True
                for column in range(frame.columns()):
                    cell = frame.cellAt(0, column)
                    cellCursor = cell.firstCursorPosition()
                    cellCursor.setPosition(cell.lastCursorPosition().position(), QtGui.QTextCursor.MoveMode.KeepAnchor)
                    if cellCursor.selectedText().strip():
                        emptyHeader = False
                if emptyHeader:
                    frame.removeRows(0, 1)
                    tableFormat.setHeaderRowCount(0)
            tableFormat.setProperty(tableHeaderStyledProperty, True)
            tableFormat.setBorder(0)
            tableFormat.setBorderStyle(QtGui.QTextFrameFormat.BorderStyle.BorderStyle_None)
            tableFormat.setCellSpacing(0)
            tableFormat.setCellPadding(8)
            preceding = QtGui.QTextCursor(document)
            preceding.setPosition(max(0, frame.firstPosition() - 1))
            previousFormat = preceding.blockFormat()
            tableFormat.setTopMargin(max(8, previousFormat.bottomMargin()) if previousFormat.headingLevel() else 8)
            tableFormat.setBottomMargin(16)
            frame.setFormat(tableFormat)
            for row in range(frame.rows()):
                for column in range(frame.columns()):
                    cell = frame.cellAt(row, column)
                    cellFormat = cell.format().toTableCellFormat()
                    cellFormat.setBorder(0)
                    cellFormat.setBorderStyle(QtGui.QTextFrameFormat.BorderStyle.BorderStyle_None)
                    cell.setFormat(cellFormat)
        cursor.endEditBlock()

    def eventFilter(self, watched, event):
        eventType = event.type()
        if (eventType == QtCore.QEvent.Type.MouseButtonRelease
                and event.button() == self.autoScrollCancelButton):
            self.autoScrollCancelButton = None
            event.accept()
            return True
        if self.autoScrollOrigin is not None:
            if eventType in (QtCore.QEvent.Type.MouseButtonPress, QtCore.QEvent.Type.MouseButtonDblClick):
                self.StopAutoScroll()
                self.autoScrollCancelButton = event.button()
                event.accept()
                return True
            if eventType == QtCore.QEvent.Type.MouseMove:
                if (event.buttons() & QtCore.Qt.MouseButton.MiddleButton
                        and (event.globalPosition() - self.autoScrollOrigin).manhattanLength() >= QtWidgets.QApplication.startDragDistance()):
                    self.autoScrollDragging = True
                event.accept()
                return True
            if eventType == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.MiddleButton:
                if (self.autoScrollDragging
                        or (event.globalPosition() - self.autoScrollOrigin).manhattanLength() >= QtWidgets.QApplication.startDragDistance()):
                    self.StopAutoScroll()
                event.accept()
                return True
            if (eventType in (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress)
                    and event.key() == QtCore.Qt.Key.Key_Escape):
                if eventType == QtCore.QEvent.Type.KeyPress:
                    self.StopAutoScroll()
                event.accept()
                return True
            if eventType in (QtCore.QEvent.Type.Wheel, QtCore.QEvent.Type.WindowDeactivate):
                self.StopAutoScroll()
        if (eventType == QtCore.QEvent.Type.MouseButtonPress
                and event.button() == QtCore.Qt.MouseButton.MiddleButton
                and watched in (self, self.browser, self.browser.viewport())):
            scrollbar = self.browser.verticalScrollBar()
            if scrollbar.maximum() > scrollbar.minimum():
                self.autoScrollOrigin = QtCore.QPointF(event.globalPosition())
                self.autoScrollDragging = False
                self.autoScrollRemainder = 0.0
                position = self.mapFromGlobal(event.globalPosition().toPoint())
                self.autoScrollAnchor.move(position - QtCore.QPoint(18, 18))
                self.autoScrollAnchor.show()
                self.autoScrollAnchor.raise_()
                self.grabMouse(QtGui.QCursor(QtCore.Qt.CursorShape.SizeVerCursor))
                self.autoScrollClock.start()
                self.autoScrollTimer.start()
            event.accept()
            return True
        if event.type() in (QtCore.QEvent.Type.MouseButtonPress, QtCore.QEvent.Type.MouseButtonRelease,
                            QtCore.QEvent.Type.MouseButtonDblClick):
            if event.button() in (QtCore.Qt.MouseButton.BackButton, QtCore.Qt.MouseButton.ForwardButton):
                if event.type() == QtCore.QEvent.Type.MouseButtonRelease:
                    if event.button() == QtCore.Qt.MouseButton.BackButton:
                        self.browser.backward()
                    else:
                        self.browser.forward()
                event.accept()
                return True
        if watched is self.browser.viewport() and event.type() == QtCore.QEvent.Type.Resize:
            margins = self.browser.viewportMargins()
            available = self.browser.viewport().width() + margins.left() + margins.right()
            inset = max(0, (available - 880) // 2)
            if margins.left() != inset or margins.right() != inset:
                self.browser.setViewportMargins(inset, 0, inset, 0)
            self.navigation.setContentsMargins(self.browser.viewport().x() + 20, 0, 0, 0)
            self.imageResizeTimer.start(0)
        return super().eventFilter(watched, event)

    def UpdateAutoScroll(self):
        if self.autoScrollOrigin is None:
            return
        elapsed = min(.05, self.autoScrollClock.restart() / 1000)
        offset = QtGui.QCursor.pos().y() - self.autoScrollOrigin.y()
        distance = max(0.0, abs(offset) - 10)
        if not distance:
            self.autoScrollRemainder = 0.0
            return
        speed = math.copysign(min(2400.0, distance ** 1.4 * 1.2), offset)
        movement = speed * elapsed + self.autoScrollRemainder
        pixels = math.trunc(movement)
        self.autoScrollRemainder = movement - pixels
        scrollbar = self.browser.verticalScrollBar()
        scrollbar.setValue(scrollbar.value() + pixels)

    def StopAutoScroll(self):
        self.autoScrollTimer.stop()
        self.autoScrollOrigin = None
        self.autoScrollDragging = False
        self.autoScrollCancelButton = None
        self.autoScrollRemainder = 0.0
        self.autoScrollAnchor.hide()
        if QtWidgets.QWidget.mouseGrabber() is self:
            self.releaseMouse()

    def wheelEvent(self, event):
        self.browser.wheelEvent(event)

    def ResizeImages(self):
        document = self.browser.document()
        available = max(1, self.browser.viewport().width() - document.documentMargin() * 2)
        frames = list(document.rootFrame().childFrames())
        padding = 7 if self.browser.viewport().width() < 480 else 8
        while frames:
            frame = frames.pop()
            frames.extend(frame.childFrames())
            if isinstance(frame, QtGui.QTextTable) and frame.format().cellPadding() != padding:
                tableFormat = frame.format()
                tableFormat.setCellPadding(padding)
                frame.setFormat(tableFormat)
        images = []
        block = document.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.charFormat().isImageFormat():
                    images.append((fragment.position(), fragment.length(), fragment.charFormat().toImageFormat()))
                iterator += 1
            block = block.next()
        for position, length, imageFormat in images:
            url = self.browser.source().resolved(QtCore.QUrl(imageFormat.name().replace("\\", "/")))
            resource = document.resource(QtGui.QTextDocument.ResourceType.ImageResource, url)
            if not isinstance(resource, (QtGui.QImage, QtGui.QPixmap)) or resource.isNull():
                continue
            natural = resource.deviceIndependentSize()
            width = min(available, natural.width())
            height = natural.height() * width / natural.width()
            if abs(imageFormat.width() - width) < .1 and abs(imageFormat.height() - height) < .1:
                continue
            imageFormat.setWidth(width)
            imageFormat.setHeight(height)
            cursor = QtGui.QTextCursor(document)
            cursor.setPosition(position)
            cursor.setPosition(position + length, QtGui.QTextCursor.MoveMode.KeepAnchor)
            cursor.setCharFormat(imageFormat)

    def StopAnimations(self):
        for animation in self.imageAnimations.values():
            animation["movie"].stop()
            animation["movie"].deleteLater()
        self.imageAnimations.clear()

    def LoadAnimations(self, baseUrl = None):
        document = self.browser.document()
        source = baseUrl if baseUrl is not None else self.browser.source()
        block = document.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                iterator += 1
                if not fragment.charFormat().isImageFormat():
                    continue
                name = fragment.charFormat().toImageFormat().name()
                url = source.resolved(QtCore.QUrl(name.replace("\\", "/")))
                if not url.isLocalFile():
                    continue
                path = Path(url.toLocalFile()).resolve()
                if not path.is_relative_to(helpDirectory.resolve()) or path.suffix.lower() != ".gif" or not path.is_file():
                    continue
                animation = self.imageAnimations.get(path)
                if animation is None:
                    movie = QtGui.QMovie(str(path), parent = self)
                    movie.setCacheMode(QtGui.QMovie.CacheMode.CacheNone)
                    if not movie.isValid():
                        movie.deleteLater()
                        continue
                    animation = {"movie": movie, "urls": [], "positions": []}
                    self.imageAnimations[path] = animation
                    movie.frameChanged.connect(lambda frame, path = path: self.UpdateAnimationFrame(path))
                for resourceUrl in (QtCore.QUrl(name), url, source.resolved(QtCore.QUrl(name)),
                                    document.baseUrl().resolved(QtCore.QUrl(name))):
                    if resourceUrl not in animation["urls"]:
                        animation["urls"].append(resourceUrl)
                animation["positions"].append((fragment.position(), fragment.length()))
            block = block.next()
        self.UpdateAnimations()

    def UpdateAnimationFrame(self, path):
        animation = self.imageAnimations.get(path)
        if animation is None:
            return
        frame = animation["movie"].currentImage()
        if frame.isNull():
            return
        document = self.browser.document()
        for url in animation["urls"]:
            document.addResource(QtGui.QTextDocument.ResourceType.ImageResource, url, frame)
        # Only invalidate the embedded image runs; retain document formatting,
        # selection, scroll position and the existing navigation history.
        for position, length in animation["positions"]:
            document.markContentsDirty(position, length)
        self.browser.viewport().update()

    def UpdateAnimations(self):
        active = self.isVisible() and not self.isMinimized()
        for animation in self.imageAnimations.values():
            movie = animation["movie"]
            if active:
                if movie.state() == QtGui.QMovie.MovieState.NotRunning:
                    movie.start()
                elif movie.state() == QtGui.QMovie.MovieState.Paused:
                    movie.setPaused(False)
            elif movie.state() == QtGui.QMovie.MovieState.Running:
                movie.setPaused(True)

    def showEvent(self, event):
        super().showEvent(event)
        self.UpdateAnimations()

    def hideEvent(self, event):
        self.StopAutoScroll()
        super().hideEvent(event)
        self.UpdateAnimations()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.WindowStateChange:
            self.StopAutoScroll()
            self.UpdateAnimations()

    def PageChanged(self, url):
        self.StopAutoScroll()
        self.StopAnimations()
        self.statusLabel.hide()
        document = self.browser.document()
        layoutEnabled = document.isLayoutEnabled()
        document.setLayoutEnabled(False)
        try:
            self.browser.RestoreMarkdownBreaks()
            self.StyleDocument()
            self.ResizeImages()
            self.RefreshTheme()
            # sourceChanged arrives before QTextBrowser.source() is updated on the
            # first page load. Resolve media against the signal's destination URL.
            self.LoadAnimations(url)
        finally:
            # Import, typography, link/code colors and image sizes should trigger
            # one final layout, rather than laying out intermediate documents.
            document.setLayoutEnabled(layoutEnabled)
        title = self.browser.document().firstBlock().text()
        self.setWindowTitle((title + " — " if title else "") + "Planner Help")
