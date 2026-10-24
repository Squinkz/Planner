"""Modeless scene inspection, using recovery checks and canvas navigation."""
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics.icons import UiIcon
from planner_app.scene_problems import FindSceneProblems, RepairPotentialIssue, RepairCoincidentObjects


class ProblemsWindow(QtWidgets.QDialog):
    def __init__(self, mainWindow):
        super().__init__(mainWindow)
        self.setWindowTitle("Check for Problems")
        self.setWindowIcon(UiIcon("report"))
        self.setModal(False)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.toolShortcut = QtGui.QShortcut(QtGui.QKeySequence("Alt+P"), self)
        self.toolShortcut.setAutoRepeat(False)
        self.toolShortcut.activated.connect(mainWindow.ShowProblems)
        self.gridContext = mainWindow.viewport.unitsMode, tuple(mainWindow.viewport.gridOrigin)
        self.gridStep = mainWindow.viewport.GridSteps()[1]
        layout = QtWidgets.QVBoxLayout(self)
        self.summary = QtWidgets.QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.tabs = QtWidgets.QTabWidget()
        self.trees = []
        for title, name in (("Problems", "problemObjects"), ("Potential issues", "potentialIssueObjects")):
            tree = QtWidgets.QTreeWidget()
            tree.setObjectName(name)
            tree.setHeaderLabel("Click an entry to select it and zoom to it")
            self.trees.append(tree)
            self.tabs.addTab(tree, title)
        layout.addWidget(self.tabs, 1)
        self.description = QtWidgets.QLabel()
        self.description.setWordWrap(True)
        self.description.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.description.setMinimumHeight(self.fontMetrics().height() * 3)
        layout.addWidget(self.description)
        buttons = QtWidgets.QHBoxLayout()
        self.repairButton = QtWidgets.QPushButton("Auto-Repair")
        self.deleteButton = QtWidgets.QPushButton("Delete")
        self.ignoreButton = QtWidgets.QPushButton("Ignore")
        self.ignoreButton.setToolTip("Ignore the selected potential issues for their current geometry. Saved with this plan.")
        self.restoreIgnoredButton = QtWidgets.QPushButton("Restore ignored")
        self.restoreIgnoredButton.setToolTip("Restore all ignored potential issues in this plan")
        self.recheckButton = QtWidgets.QPushButton("Recheck")
        self.closeButton = QtWidgets.QPushButton("Close")
        for button in (self.repairButton, self.deleteButton, self.ignoreButton, self.restoreIgnoredButton, self.recheckButton, self.closeButton):
            button.setAutoDefault(False)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.refreshTimer = QtCore.QTimer(self)
        self.refreshTimer.setSingleShot(True)
        self.refreshTimer.setInterval(100)
        self.refreshTimer.timeout.connect(self.RefreshObjects)
        mainWindow.viewport.sceneChanged.connect(self.QueueRefresh)
        mainWindow.viewport.settingsChanged.connect(self.QueueRefresh)
        self.finished.connect(self.StopUpdates)
        for tree in self.trees:
            tree.itemSelectionChanged.connect(self.RefreshActions)
            tree.itemClicked.connect(self.JumpTo)
            tree.itemActivated.connect(self.JumpTo)
        self.tabs.currentChanged.connect(self.RefreshActions)
        self.repairButton.clicked.connect(self.RepairCurrent)
        self.deleteButton.clicked.connect(self.DeleteCurrent)
        self.ignoreButton.clicked.connect(self.IgnoreCurrent)
        self.restoreIgnoredButton.clicked.connect(self.RestoreIgnored)
        self.recheckButton.clicked.connect(self.Recheck)
        self.closeButton.clicked.connect(self.close)
        self.resize(650, 460)
        self.RefreshObjects()

    @property
    def tree(self):
        return self.tabs.currentWidget()

    def QueueRefresh(self):
        v = self.parentWidget().viewport
        context = v.unitsMode, tuple(v.gridOrigin)
        if context != self.gridContext:
            self.gridContext = context
            self.gridStep = v.GridSteps()[1]
        self.refreshTimer.start()

    def Recheck(self):
        self.gridStep = self.parentWidget().viewport.GridSteps()[1]
        self.RefreshObjects()

    def RefreshObjects(self):
        self.refreshTimer.stop()
        main = self.parentWidget()
        self.problems = FindSceneProblems(main.viewport, gridStep = self.gridStep)
        for tabIndex, (section, potential) in enumerate((("Problems", False), ("Potential issues", True))):
            tree = self.trees[tabIndex]
            previous = tree.currentItem()
            selected = previous.data(0, QtCore.Qt.ItemDataRole.UserRole) if previous is not None else []
            selectedKeys = {(id(issue["object"]), issue["code"]) for issue in selected}
            expanded = {tree.topLevelItem(index).text(0).rsplit(" (", 1)[0]: tree.topLevelItem(index).isExpanded()
                        for index in range(tree.topLevelItemCount())}
            blocker = QtCore.QSignalBlocker(tree)
            tree.clear()
            entries = [issue for issue in self.problems if bool(issue.get("potential")) == potential]
            self.tabs.setTabText(tabIndex, f"{section} ({len(entries)})")
            tree.setHeaderLabel("Click an entry to select it and zoom to it" if entries else
                                "No potential issues found" if potential else "No problems found")
            groups = {}
            for issue in entries:
                groups.setdefault(issue["label"], []).append(issue)
            for label, issues in sorted(groups.items()):
                parent = QtWidgets.QTreeWidgetItem(tree, [f"{label} ({len(issues)})"])
                parent.setData(0, QtCore.Qt.ItemDataRole.UserRole, issues)
                parent.setExpanded(expanded.get(label, True))
                for issue in issues:
                    obj = issue["object"]
                    name = getattr(obj, "definitionKey", obj.definition["key"]) if hasattr(obj, "definition") else type(obj).__name__
                    child = QtWidgets.QTreeWidgetItem(parent, [f"{name} — Object {obj.objectId}"])
                    child.setToolTip(0, issue["description"])
                    child.setData(0, QtCore.Qt.ItemDataRole.UserRole, [issue])
                    if selectedKeys == {(id(obj), issue["code"])}:
                        tree.setCurrentItem(child)
            del blocker
        affected, potentialObjects = {}, {}
        for issue in self.problems:
            collection = potentialObjects if issue.get("potential") else affected
            for obj in issue.get("objects", (issue["object"],)):
                collection[id(obj)] = obj
        main.viewport.problemObjects = tuple(affected.values())
        main.viewport.potentialProblemObjects = tuple(obj for key, obj in potentialObjects.items() if key not in affected)
        main.viewport.update()
        count = sum(not issue.get("potential", False) for issue in self.problems)
        potentialCount = len(self.problems) - count
        self.summary.setText(f"{count} problem{'s' if count != 1 else ''} and {potentialCount} potential issue{'s' if potentialCount != 1 else ''}."
                             if self.problems else "No problems found.")
        self.RefreshActions()

    def RefreshActions(self):
        item = self.tree.currentItem()
        issues = item.data(0, QtCore.Qt.ItemDataRole.UserRole) if item is not None else []
        self.repairButton.setEnabled(bool(issues) and (all(issue.get("repairKind") == "duplicates" for issue in issues)
                                     or len(issues) == 1 and issues[0]["repair"] is not None))
        self.deleteButton.setEnabled(bool(issues))
        potential = self.tabs.currentIndex() == 1
        self.ignoreButton.setVisible(potential)
        self.restoreIgnoredButton.setVisible(potential)
        self.ignoreButton.setEnabled(bool(issues) and all(issue.get("potential") for issue in issues))
        self.restoreIgnoredButton.setEnabled(bool(self.parentWidget().viewport.ignoredPotentialIssues))
        if len(issues) == 1:
            issue = issues[0]
            description = issue["description"]
            if issue["repair"] is not None:
                description += "\n\n" + issue["repairText"] + "\nThe change can be undone."
            self.description.setText(description)
        else:
            self.description.setText("Auto-Repair removes extra copies in each coincident group, keeping one copy per group. The change can be undone."
                                     if issues and all(issue.get("repairKind") == "duplicates" for issue in issues) else
                                     "Select an individual problem to inspect its repair options." if issues else "")

    def JumpTo(self, *unused):
        item = self.tree.currentItem()
        if item is not None:
            issues = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            self.parentWidget().LocateRecoveryObjects([obj for issue in issues for obj in issue.get("objects", (issue["object"],))])

    def RepairCurrent(self):
        item = self.tree.currentItem()
        if item is None:
            return
        selected = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if selected and all(issue.get("repairKind") == "duplicates" for issue in selected):
            v = self.parentWidget().viewport
            v.CancelInteraction()
            RepairCoincidentObjects(v, selected)
            self.RefreshObjects()
            return
        if len(selected) != 1:
            return
        # Recompute before acting, so a pending refresh cannot apply a stale fix.
        v = self.parentWidget().viewport
        v.CancelInteraction()
        issue = next((issue for issue in FindSceneProblems(v, gridStep = self.gridStep) if issue["object"] is selected[0]["object"]
                      and issue["code"] == selected[0]["code"]), None)
        if issue is None or issue["repair"] is None:
            self.RefreshObjects()
            return
        if issue.get("potential"):
            repaired, message = RepairPotentialIssue(v, issue)
            self.RefreshObjects()
            if not repaired:
                self.description.setText(message)
                self.repairButton.setEnabled(False)
            return
        before = v.CaptureState()
        obj = issue["object"]
        record = issue["repair"]
        for name, value in record.items():
            if name in ("first", "second", "middle", "textOffset"):
                attribute = {"first": "firstVertex", "second": "secondVertex", "middle": "middleVertex", "textOffset": "textOffset"}[name]
                setattr(obj, attribute, QtCore.QPointF(*value))
            elif name in ("width", "length", "firstMiter", "secondMiter", "sillDepth", "depth", "depthOffset"):
                setattr(obj, name, value)
            elif name == "center":
                obj.centerFraction = value
        v.RecordEdit(before)
        v.selectionChanged.emit()
        self.RefreshObjects()

    def DeleteCurrent(self):
        item = self.tree.currentItem()
        if item is None:
            return
        issues = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        v = self.parentWidget().viewport
        sceneIds = {id(obj) for obj in v.walls + v.windows + v.furnishings + v.labels}
        objects = [issue["object"] for issue in issues if id(issue["object"]) in sceneIds]
        if objects:
            self.parentWidget().LocateRecoveryObjects(objects, expandGroups = False)
            if {id(obj) for obj, index in v.SelectionEntries()} == {id(obj) for obj in objects}:
                v.DeleteSelected()
        self.RefreshObjects()

    def IgnoreCurrent(self):
        item = self.tree.currentItem()
        if item is None or self.tabs.currentIndex() != 1:
            return
        selected = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        fingerprints = {issue["fingerprint"] for issue in selected if issue.get("potential")}
        v = self.parentWidget().viewport
        v.CancelInteraction()
        # Only ignore still-current suggestions, not a stale row's old geometry.
        current = {issue["fingerprint"] for issue in FindSceneProblems(v, gridStep = self.gridStep) if issue.get("potential")}
        added = fingerprints & current
        if added:
            v.ignoredPotentialIssues = sorted(set(v.ignoredPotentialIssues) | added)
            v.settingsChanged.emit()
        self.RefreshObjects()

    def RestoreIgnored(self):
        v = self.parentWidget().viewport
        if v.ignoredPotentialIssues:
            v.ignoredPotentialIssues = []
            v.settingsChanged.emit()
        self.RefreshObjects()

    def StopUpdates(self, result):
        self.refreshTimer.stop()
        v = self.parentWidget().viewport
        v.sceneChanged.disconnect(self.QueueRefresh)
        v.settingsChanged.disconnect(self.QueueRefresh)
        v.problemObjects = ()
        v.potentialProblemObjects = ()
        v.update()
        self.parentWidget().problemsWindow = None
