"""Build and Furnish tab construction; catalog categories are populated once."""
from planner_app.models import Elevator

from PySide6 import QtCore, QtGui, QtWidgets

from planner_app.graphics.palette import themeColors
from planner_app.graphics.icons import UiIcon, UiIconPath, GroupModeIcon
from planner_app.furnishing_search import FindFurnishings, FurnishingDimensionText, SortFurnishings
from planner_app.graphics.theme import HeaderIcon, MaterialIcon, wallMaterials
from planner_app.models import OpenDoorway, Door, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, Window, SilledWindow, CasementWindow, MeasurementGuide, Arrow, Counter, Railing, Stair, Pillar, Column, Label, NorthArrow, Fireplace
from planner_app.ui.menus import AddMenuButton
from planner_app.ui.export_panel import ExportPanel
from planner_app.ui.furnishing_list import FurnishingCatalogList
from planner_app.ui.widgets import (
    VisibilityItemDelegate, CollapsibleSectionHeading, DownwardComboBox, FurnishingButton, FurnishingIconLayout, SectionHeading, SidebarTabBar, WallWidthSelector, WindowButton,
)


class SidebarMixin:
    def BuildSidebarTabs(self):
        self.sidebarTabs = QtWidgets.QTabWidget()
        self.sidebarTabs.setTabBar(SidebarTabBar(self.sidebarTabs))
        self.sidebarTabs.tabBar().setObjectName("sidebarTabBar")
        self.sidebarTabs.setIconSize(QtCore.QSize(32, 32))
        self.sidebarTabs.tabBar().setDrawBase(False)
        self.sidebarTabs.tabBar().setExpanding(False)
        self.sidebarTabs.tabBar().setUsesScrollButtons(False)
        self.BuildBuildTab()
        self.BuildFurnishTab()
        self.BuildVisibilityTab()
        self.exportPanel = ExportPanel(self)
        exportIndex = self.sidebarTabs.addTab(self.exportPanel, UiIcon("save_alt_24dp_E3E3E3"), "")
        self.sidebarTabs.setTabToolTip(exportIndex, "Export")
        for index in range(self.sidebarTabs.count()):
            name = self.sidebarTabs.tabText(index) or self.sidebarTabs.tabToolTip(index)
            self.sidebarTabs.setTabToolTip(index, name)
            self.sidebarTabs.tabBar().setAccessibleTabName(index, name)
        self.propertiesPanel = QtWidgets.QWidget()
        self.propertiesCollapsed = False
        self.propertiesRestoreHeight = None
        self.propertiesResizeChanging = False
        self.propertiesExportSizes = None
        self.propertiesDividerDragging = False
        propertiesLayout = QtWidgets.QVBoxLayout(self.propertiesPanel)
        propertiesLayout.setContentsMargins(1, 12, 1, 0)
        self.propertiesHeading = CollapsibleSectionHeading("Object Properties", "Objects")
        self.propertiesHeading.setContentsMargins(13, 0, 13, 0)
        self.propertiesHeading.clicked.connect(lambda: self.SetPropertiesCollapsed(not self.propertiesCollapsed))
        propertiesLayout.addWidget(self.propertiesHeading)
        self.propertiesHeadingHeight = (self.propertiesHeading.sizeHint().height() +
                                        propertiesLayout.contentsMargins().top() + propertiesLayout.contentsMargins().bottom())
        self.propertiesPanel.setMinimumHeight(self.propertiesHeadingHeight)
        propertiesPage = QtWidgets.QWidget()
        propertiesPageLayout = QtWidgets.QVBoxLayout(propertiesPage)
        propertiesPageLayout.setContentsMargins(13, 8, 14, 14)
        self.BuildProperties(propertiesPageLayout)
        self.referenceImage.BuildPanel(propertiesPageLayout)
        propertiesPageLayout.addStretch(1)
        self.propertiesScrollArea = QtWidgets.QScrollArea()
        self.propertiesScrollArea.setWidgetResizable(True)
        self.propertiesScrollArea.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.propertiesScrollArea.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.propertiesScrollArea.setWidget(propertiesPage)
        propertiesLayout.addWidget(self.propertiesScrollArea, 1)
        self.sidebarContentSplitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.sidebarContentSplitter.setObjectName("sidebarContentSplitter")
        self.sidebarContentSplitter.setChildrenCollapsible(False)
        self.sidebarContentSplitter.setHandleWidth(8)
        self.sidebarTabs.setMinimumHeight(100)
        self.sidebarContentSplitter.addWidget(self.sidebarTabs)
        self.sidebarContentSplitter.addWidget(self.propertiesPanel)
        self.sidebarContentSplitter.setStretchFactor(0, 2)
        self.sidebarContentSplitter.setStretchFactor(1, 1)
        self.sidebarContentSplitter.setSizes([600, 300])
        self.sidebarContentSplitter.handle(1).setToolTip("Double-click to reset Object Properties height")
        self.exportActionPanel = QtWidgets.QWidget()
        exportActionLayout = QtWidgets.QVBoxLayout(self.exportActionPanel)
        exportActionLayout.setContentsMargins(14, 8, 14, 14)
        self.exportButton = QtWidgets.QPushButton("Export")
        self.exportButton.setObjectName("exportActionButton")
        self.exportButton.setIcon(UiIcon("save_alt_24dp_E3E3E3"))
        self.exportButton.setIconSize(QtCore.QSize(28, 28))
        self.exportButton.setFixedHeight(48)
        self.exportButton.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.exportButton.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.exportButton.clicked.connect(self.exportPanel.Export)
        exportActionLayout.addWidget(self.exportButton)
        self.exportActionPanel.hide()
        self.sidebarContentPanel = QtWidgets.QWidget()
        contentLayout = QtWidgets.QVBoxLayout(self.sidebarContentPanel)
        contentLayout.setContentsMargins(0, 0, 0, 0)
        contentLayout.setSpacing(0)
        contentLayout.addWidget(self.sidebarContentSplitter, 1)
        contentLayout.addWidget(self.exportActionPanel)
        self.sidebarContentSplitter.splitterMoved.connect(self.PropertiesSplitterMoved)
        self.sidebarTabs.currentChanged.connect(self.UpdatePropertiesVisibility)

    def UpdatePropertiesVisibility(self, index):
        self.exportPanel.SetActive(self.sidebarTabs.widget(index) is self.exportPanel)
        if self.sidebarTabs.widget(index) is self.exportPanel:
            if self.propertiesExportSizes is None:
                self.propertiesExportSizes = self.sidebarContentSplitter.sizes()
            self.propertiesPanel.hide()
            self.exportActionPanel.show()
        else:
            self.exportActionPanel.hide()
            self.sidebarContentPanel.layout().activate()
            self.propertiesPanel.show()
            if self.propertiesExportSizes is not None:
                self.sidebarContentSplitter.setSizes(self.propertiesExportSizes)
                self.propertiesExportSizes = None

    def SetPropertiesSplitterSizes(self, sizes):
        if self.sidebarTabs.currentWidget() is self.exportPanel:
            self.propertiesExportSizes = list(sizes)
        else:
            self.sidebarContentSplitter.setSizes(sizes)

    def SetPropertiesCollapsed(self, collapsed, rememberHeight = True):
        if collapsed == self.propertiesCollapsed:
            return
        self.propertiesResizeChanging = True
        try:
            sizes = self.propertiesExportSizes if self.propertiesExportSizes is not None else self.sidebarContentSplitter.sizes()
            available = sum(sizes)
            if collapsed:
                self.propertiesRestoreHeight = sizes[1] if rememberHeight else None
                self.propertiesScrollArea.hide()
                if not self.propertiesDividerDragging:
                    self.propertiesPanel.setFixedHeight(self.propertiesHeadingHeight)
                self.SetPropertiesSplitterSizes([max(0, available - self.propertiesHeadingHeight), self.propertiesHeadingHeight])
            else:
                self.propertiesPanel.setMaximumHeight(16777215)
                self.propertiesPanel.setMinimumHeight(self.propertiesHeadingHeight)
                self.propertiesScrollArea.show()
                height = self.propertiesRestoreHeight if self.propertiesRestoreHeight is not None else round(available / 3)
                height = max(self.propertiesHeadingHeight, min(height, available - self.sidebarTabs.minimumHeight()))
                self.SetPropertiesSplitterSizes([max(0, available - height), height])
            self.propertiesCollapsed = collapsed
            self.propertiesHeading.SetCollapsed(collapsed)
        finally:
            self.propertiesResizeChanging = False

    def PropertiesSplitterMoved(self, position, index):
        if self.propertiesResizeChanging or index != 1:
            return
        if self.propertiesCollapsed:
            if self.sidebarContentSplitter.sizes()[1] > self.propertiesHeadingHeight + 24:
                self.propertiesCollapsed = False
                self.propertiesRestoreHeight = None
                self.propertiesScrollArea.show()
                self.propertiesHeading.SetCollapsed(False)
            return
        if self.sidebarContentSplitter.sizes()[1] <= self.propertiesHeadingHeight + 24:
            self.SetPropertiesCollapsed(True, rememberHeight = False)

    def BuildVisibilityTab(self):
        visibilityPage = QtWidgets.QWidget()
        self.visibilityPage = visibilityPage
        layout = QtWidgets.QVBoxLayout(visibilityPage)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.addWidget(SectionHeading("Visibility", "View"))
        self.visibilityTree = QtWidgets.QTreeWidget()
        self.visibilityTree.setObjectName("visibilityTree")
        self.visibilityTree.setItemDelegate(VisibilityItemDelegate(self.visibilityTree))
        self.visibilityTree.setHeaderHidden(True)
        self.visibilityTree.setIndentation(24)
        self.visibilityTree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.visibilityTree.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.visibilityItems = {}
        for name, parentName in (("World", None), ("Walls", "World"), ("Doors", "Walls"),
                                 ("Windows", "Walls"), ("Fireplaces", "Walls"), ("Elevators", "World"), ("Stairs", "World"), ("Counters", "World"), ("Railings", "World"), ("Furnishings", "World"), ("Labels", "World"), ("Arrows", "World"), ("Measurement guides", "World"), ("North arrows", "World")):
            parent = self.visibilityItems[parentName] if parentName else self.visibilityTree
            item = QtWidgets.QTreeWidgetItem(parent, [name])
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, QtCore.Qt.CheckState.Checked)
            self.visibilityItems[name] = item
        self.referenceImageItem = QtWidgets.QTreeWidgetItem(self.visibilityTree, ["Reference Image"])
        self.referenceImageItem.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
        self.referenceImageItem.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
        self.visibilityTree.expandAll()
        self.visibilityTree.itemChanged.connect(self.SetVisibility)
        self.visibilityTree.itemClicked.connect(lambda item, column: self.referenceImage.Show() if item is self.referenceImageItem else None)
        self.viewport.sceneChanged.connect(self.RefreshVisibilityCounts)
        self.RefreshVisibilityCounts()
        layout.addWidget(self.visibilityTree, 1)
        self.sidebarTabs.addTab(visibilityPage, UiIcon("world"), "Visibility")

    def RefreshVisibilityCounts(self):
        stairs = sum(isinstance(obj, Stair) for obj in self.viewport.walls)
        guides = sum(isinstance(obj, MeasurementGuide) for obj in self.viewport.walls)
        arrows = sum(isinstance(obj, Arrow) for obj in self.viewport.walls)
        railings = sum(isinstance(obj, Railing) for obj in self.viewport.walls)
        counters = sum(isinstance(obj, Counter) for obj in self.viewport.walls)
        doors = sum(isinstance(obj, (Door, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway)) for obj in self.viewport.windows)
        counts = {"World": len(self.viewport.walls) + len(self.viewport.windows) + len(self.viewport.furnishings) + len(self.viewport.labels),
                  "Walls": len(self.viewport.walls) - sum(isinstance(obj, Elevator) for obj in self.viewport.walls) - stairs - counters - arrows - guides - railings, "Stairs": stairs, "Counters": counters, "Railings": railings,
                  "Doors": doors, "Windows": len(self.viewport.windows) - doors - sum(isinstance(obj, Fireplace) for obj in self.viewport.windows),
                  "Elevators": sum(isinstance(obj, Elevator) for obj in self.viewport.walls),
                  "Fireplaces": sum(isinstance(obj, Fireplace) for obj in self.viewport.windows),
                  "North arrows": sum(isinstance(obj, NorthArrow) for obj in self.viewport.furnishings),
                  "Furnishings": sum(not isinstance(obj, NorthArrow) for obj in self.viewport.furnishings), "Labels": len(self.viewport.labels), "Arrows": arrows, "Measurement guides": guides}
        blocker = QtCore.QSignalBlocker(self.visibilityTree)
        for name, count in counts.items():
            label = f"{name} ({count} {'object' if count == 1 else 'objects'})"
            if self.visibilityItems[name].text(0) != label:
                self.visibilityItems[name].setText(0, label)
            node = self.visibilityItems[name]
            visible = True
            ancestor = node
            while ancestor is not None:
                visible = visible and ancestor.checkState(0) != QtCore.Qt.CheckState.Unchecked
                ancestor = ancestor.parent()
            color = "treeDisabledText" if not visible else "treeEmptyText" if count == 0 else "text"
            node.setForeground(0, QtGui.QBrush(QtGui.QColor(themeColors[color])))
        del blocker

    def SetVisibility(self, item, column):
        if item is self.referenceImageItem:
            self.referenceImage.ToggleVisibility(item.checkState(0) == QtCore.Qt.CheckState.Checked)
            return
        blocker = QtCore.QSignalBlocker(self.visibilityTree)
        if item is None:
            visibility = {name: node.checkState(0) == QtCore.Qt.CheckState.Checked
                          for name, node in self.visibilityItems.items()}
            # Older projects used World as a gate over remembered child choices.
            if not visibility["World"]:
                visibility = dict.fromkeys(visibility, False)
        else:
            visibility = dict(self.viewport.visibility)
            enabled = item.checkState(0) != QtCore.Qt.CheckState.Unchecked
            descendants = [item]
            while descendants:
                node = descendants.pop()
                name = next(name for name, candidate in self.visibilityItems.items() if candidate is node)
                visibility[name] = enabled
                node.setCheckState(0, QtCore.Qt.CheckState.Checked if enabled else QtCore.Qt.CheckState.Unchecked)
                descendants.extend(node.child(index) for index in range(node.childCount()))
        for name, node in self.visibilityItems.items():
            node.setCheckState(0, QtCore.Qt.CheckState.Checked if visibility[name] else QtCore.Qt.CheckState.Unchecked)
        # Walls contains its own objects as well as the Doors and Windows branches.
        # Keep its object visibility separate from the aggregate checkbox state.
        for name in ("Walls", "World"):
            node = self.visibilityItems[name]
            states = [node.child(index).checkState(0) for index in range(node.childCount())]
            if name == "Walls":
                states.append(QtCore.Qt.CheckState.Checked if visibility[name] else QtCore.Qt.CheckState.Unchecked)
            state = (QtCore.Qt.CheckState.Checked if all(value == QtCore.Qt.CheckState.Checked for value in states)
                     else QtCore.Qt.CheckState.Unchecked if all(value == QtCore.Qt.CheckState.Unchecked for value in states)
                     else QtCore.Qt.CheckState.PartiallyChecked)
            node.setCheckState(0, state)
        visibility["World"] = self.visibilityItems["World"].checkState(0) != QtCore.Qt.CheckState.Unchecked
        self.viewport.visibility = visibility
        del blocker
        self.RefreshVisibilityCounts()
        self.viewport.update()
        self.viewport.settingsChanged.emit()

    def BuildViewportToolbar(self, sidebarLayout):
        self.viewportToolbar = QtWidgets.QWidget()
        self.viewportToolbar.setObjectName("viewportToolbar")
        toolbarLayout = QtWidgets.QVBoxLayout(self.viewportToolbar)
        toolbarLayout.setContentsMargins(0, 0, 0, 0)
        toolbarLayout.setSpacing(6)
        self.altHeld = False
        self.snapButton = QtWidgets.QToolButton()
        self.snapButton.setAccessibleName("Snap")
        self.snapButton.setIcon(HeaderIcon("Snap"))
        self.snapButton.setIconSize(QtCore.QSize(32, 32))
        self.snapButton.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.snapButton.setObjectName("viewportToolbarButton")
        self.snapButton.ensurePolished()
        self.snapButton.setFixedSize(40, 40)
        self.snapButton.setCheckable(True)
        self.snapButton.setToolTip("Toggle snapping. Hold Alt to disable temporarily.")
        self.snapOptionsButton = QtWidgets.QToolButton()
        self.snapOptionsButton.setObjectName("viewportToolbarButton")
        self.snapOptionsButton.setAccessibleName("Snapping Options")
        self.snapOptionsButton.setToolTip("Snapping options")
        self.snapOptionsButton.setIcon(HeaderIcon("Snapping Options"))
        self.snapOptionsButton.setIconSize(QtCore.QSize(32, 32))
        self.snapOptionsButton.setFixedSize(40, 40)
        self.snapOptionsButton.setCheckable(True)
        self.snapMenu = QtWidgets.QMenu(self.snapOptionsButton)
        self.snapMenu.setObjectName("snapMenu")
        self.snapOptionsButton.clicked.connect(lambda: self.snapMenu.popup(
            self.snapOptionsButton.mapToGlobal(QtCore.QPoint(-self.snapMenu.sizeHint().width() - 6, 0))))
        self.snapMenu.aboutToShow.connect(lambda: self.snapOptionsButton.setChecked(True))
        self.snapMenu.aboutToHide.connect(lambda: self.snapOptionsButton.setChecked(False))
        self.snapOptions = {}
        for option, label, checked in (("grid", "Grid", True),
                                       ("vertices", "Control Points", True),
                                       ("corners", "Corners", True),
                                       ("midpoints", "Midpoints", True),
                                       ("alignment", "Alignment", True)):
            button = AddMenuButton(self.snapMenu, label, iconName = "Check")
            button.setCheckable(True)
            button.setChecked(checked)
            if option == "vertices":
                button.setToolTip("Snap to object control points")
            if option == "corners":
                button.setToolTip("Snap to object corners and joined wall corners")
            if option == "midpoints":
                button.setToolTip("Snap to object centers and use their X and Y coordinates for alignment")
            if option == "alignment":
                button.setToolTip("Match the nearest X or Y coordinate of another control point, independent of grid spacing")
            button.toggled.connect(self.SetSnapOptions)
            self.snapOptions[option] = button
        self.snapButton.toggled.connect(self.SetSnapping)
        self.snapButton.setChecked(True)
        toolbarLayout.addWidget(self.snapButton, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        toolbarLayout.addWidget(self.snapOptionsButton, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        self.connectedOptions = {}
        for option, label, tooltip, iconName, checked in (("vertices", "Connected Points", "Move connected points together", "con_vert", True),
                                                        ("objects", "Connected Objects", "Move connected objects together", "con_obj", False)):
            button = QtWidgets.QToolButton()
            button.setObjectName("viewportToolbarButton")
            button.setAccessibleName(label)
            button.setToolTip(tooltip)
            button.setIcon(UiIcon(iconName))
            button.setIconSize(QtCore.QSize(32, 32))
            button.setFixedSize(40, 40)
            button.setCheckable(True)
            button.setChecked(checked)
            button.toggled.connect(self.SetConnectedOptions)
            self.connectedOptions[option] = button
            toolbarLayout.addWidget(button, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        self.groupModeButton = QtWidgets.QToolButton()
        self.groupModeButton.setObjectName("viewportToolbarButton")
        self.groupModeButton.setAccessibleName("Group Mode")
        self.groupModeButton.setToolTip("Toggle group selection (Ctrl + Tab)")
        self.groupModeButton.setIcon(GroupModeIcon())
        self.groupModeButton.setIconSize(QtCore.QSize(32, 32))
        self.groupModeButton.setFixedSize(40, 40)
        self.groupModeButton.setCheckable(True)
        self.groupModeButton.setChecked(self.viewport.groupModeEnabled)
        self.groupModeButton.toggled.connect(self.viewport.SetGroupMode)
        self.groupModeShortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Tab"), self)
        self.groupModeShortcut.setAutoRepeat(False)
        self.groupModeShortcut.activated.connect(self.groupModeButton.click)
        toolbarLayout.addWidget(self.groupModeButton, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        self.groupActionButtons = {}
        # Keep internal keys stable when editing the user-facing tooltip labels.
        for name, label, shortcut, iconName, command in (("Group", "Group selected", "Ctrl + G", "Group", self.viewport.GroupSelection),
                                                        ("Ungroup", "Ungroup selected", "Alt + G", "Ungroup", self.viewport.UngroupSelection),
                                                        ("Hide", "Hide selected", "H", "Hide selected", self.viewport.HideSelection),
                                                        ("HideUnselected", "Hide unselected", "Ctrl + H", "Hide unselected", self.viewport.HideUnselected),
                                                        ("Unhide", "Unhide all", "Alt + H", "Unhide", self.viewport.UnhideObjects)):
            button = QtWidgets.QToolButton()
            button.setObjectName("viewportToolbarButton")
            button.setAccessibleName(name)
            button.setToolTip(f"{label} ({shortcut})")
            button.setIcon(HeaderIcon(iconName))
            button.setIconSize(QtCore.QSize(32, 32))
            button.setFixedSize(40, 40)
            button.setEnabled(False)
            button.clicked.connect(command)
            self.groupActionButtons[name] = button
            toolbarLayout.addWidget(button, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        self.transformOrientationButton = QtWidgets.QToolButton()
        self.transformOrientationButton.setObjectName("viewportToolbarButton")
        self.transformOrientationButton.setProperty("modeSelector", True)
        self.transformOrientationButton.setAccessibleName("Transform orientation")
        self.transformOrientationButton.setIconSize(QtCore.QSize(32, 32))
        self.transformOrientationButton.setFixedSize(40, 40)
        self.transformOrientationButton.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.transformOrientationButton.clicked.connect(lambda checked = False: self.SetTransformOrientation(not self.viewport.localTransforms))
        toolbarLayout.addWidget(self.transformOrientationButton, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        self.SetTransformOrientation(self.viewport.localTransforms, notify = False)
        for button in (self.connectedOptions["vertices"], self.groupModeButton, self.groupActionButtons["Hide"], self.transformOrientationButton):
            separator = QtWidgets.QFrame()
            separator.setObjectName("sectionHeadingLine")
            separator.setFrameShape(QtWidgets.QFrame.Shape.HLine)
            separator.setFixedSize(40, 1)
            index = toolbarLayout.indexOf(button)
            toolbarLayout.insertSpacing(index, 6)
            toolbarLayout.insertWidget(index + 1, separator)
            toolbarLayout.insertSpacing(index + 2, 6)
        self.viewport.selectionChanged.connect(self.RefreshGroupActions)
        self.viewport.sceneChanged.connect(self.RefreshGroupActions)
        sidebarLayout.addWidget(self.viewportToolbar)

    def SetTransformOrientation(self, local, notify = True):
        self.viewport.localTransforms = local
        self.transformOrientationButton.setIcon(UiIcon("o_local" if local else "o_global"))
        self.transformOrientationButton.setToolTip("Local transforms (Tab: switch to global)" if local else "Global transforms (Tab: switch to local)")
        if self.viewport.isDragging and self.viewport.lastInteractionPosition is not None:
            self.viewport.UpdateInteraction(self.viewport.lastInteractionPosition, QtWidgets.QApplication.keyboardModifiers())
        self.viewport.update()
        if notify:
            self.viewport.settingsChanged.emit()

    def RefreshGroupActions(self):
        if self.viewport.exportOverlay.active:
            for button in self.groupActionButtons.values():
                button.setEnabled(False)
            return
        selectedIds = {id(obj) for obj, index in self.viewport.SelectionEntries()}
        self.groupActionButtons["Group"].setEnabled(len(selectedIds) > 1)
        self.groupActionButtons["Ungroup"].setEnabled(any(id(obj) in selectedIds
                                                       for group in self.viewport.objectGroups for obj in group))
        self.groupActionButtons["Hide"].setEnabled(bool(selectedIds))
        self.groupActionButtons["HideUnselected"].setEnabled(bool(selectedIds))
        self.groupActionButtons["Unhide"].setEnabled(bool(self.viewport.hiddenObjects))

    def SetWallToolShape(self, index):
        self.viewport.wallShape = ("line", "square", "circle")[index]
        self.viewport.settingsChanged.emit()

    def BuildBuildTab(self):
        toolsPage = QtWidgets.QWidget()
        toolsLayout = QtWidgets.QVBoxLayout(toolsPage)
        toolsLayout.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetMinimumSize)
        toolsLayout.setContentsMargins(14, 14, 14, 14)
        toolsLayout.addWidget(SectionHeading("Wall Tool", "Walls"))
        toolsLayout.addSpacing(8)
        wallToolLayout = QtWidgets.QHBoxLayout()
        wallToolLayout.setSpacing(14)
        wallShapeLayout = QtWidgets.QVBoxLayout()
        wallShapeLayout.setSpacing(0)
        wallSettingsLayout = QtWidgets.QVBoxLayout()
        wallSettingsLayout.setSpacing(0)
        self.wallToolButtonGroup = QtWidgets.QButtonGroup(self)
        self.wallToolButtonGroup.setExclusive(True)
        self.wallToolButtons = {}
        for index, shape in enumerate(("line", "square", "circle")):
            button = QtWidgets.QToolButton()
            button.setObjectName("viewportToolbarButton")
            button.setAccessibleName(shape.capitalize())
            button.setToolTip(shape.capitalize())
            button.setIcon(UiIcon("octagon" if shape == "circle" else shape))
            button.setIconSize(QtCore.QSize(24, 24))
            button.setFixedSize(24, 28)
            button.setCheckable(True)
            self.wallToolButtonGroup.addButton(button, index)
            button.setChecked(index == 0)
            self.wallToolButtons[shape] = button
            if index:
                wallShapeLayout.addStretch(1)
            wallShapeLayout.addWidget(button)
        wallToolLayout.addLayout(wallShapeLayout)
        wallToolDivider = QtWidgets.QFrame()
        wallToolDivider.setObjectName("wallToolDivider")
        wallToolDivider.setFrameShape(QtWidgets.QFrame.Shape.VLine)
        wallToolDivider.setFixedWidth(1)
        wallToolLayout.addWidget(wallToolDivider)
        wallToolLayout.addLayout(wallSettingsLayout, 1)
        self.wallToolButtonGroup.idClicked.connect(self.SetWallToolShape)
        newWallForm = QtWidgets.QFormLayout()
        newWallForm.setContentsMargins(0, 0, 0, 0)
        newWallForm.setHorizontalSpacing(16)
        newWallForm.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        self.newWallMaterialField = DownwardComboBox()
        self.materialIcons = {material: MaterialIcon(material) for material in wallMaterials}
        self.newWallMaterialField.setIconSize(QtCore.QSize(32, 24))
        for material in wallMaterials:
            self.newWallMaterialField.addItem(self.materialIcons[material], material)
        self.newWallMaterialField.setCurrentText(self.viewport.newWallMaterial)
        self.newWallMaterialField.currentTextChanged.connect(lambda material: setattr(self.viewport, "newWallMaterial", material))
        self.newWallMaterialField.currentTextChanged.connect(lambda material: self.viewport.settingsChanged.emit())
        newWallForm.addRow("Material", self.newWallMaterialField)
        self.wallWidthSelector = WallWidthSelector()
        self.wallWidthSelector.slider.valueChanged.connect(self.SetWallWidth)
        wallSettingsLayout.addWidget(self.wallWidthSelector)
        wallSettingsLayout.addSpacing(8)
        wallSettingsLayout.addLayout(newWallForm)
        toolsLayout.addLayout(wallToolLayout)
        for key, action in (("Q", QtWidgets.QAbstractSlider.SliderAction.SliderSingleStepSub),
                            ("W", QtWidgets.QAbstractSlider.SliderAction.SliderSingleStepAdd)):
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(key), self)
            shortcut.activated.connect(lambda action = action: self.wallWidthSelector.slider.triggerAction(action))
        toolsLayout.addSpacing(16)
        toolsLayout.addWidget(SectionHeading("Objects", "Objects"))
        toolsLayout.addSpacing(8)
        self.doorButton = WindowButton(objectType = "door")
        self.slidingDoorButton = WindowButton(objectType = "sliding-door")
        self.pocketDoorButton = WindowButton(objectType = "pocket-door")
        self.barnDoorButton = WindowButton(objectType = "barn-door")
        self.bifoldDoorButton = WindowButton(objectType = "bifold-door")
        self.openDoorwayButton = WindowButton(objectType = "open-doorway")
        self.windowButton = WindowButton()
        self.silledWindowButton = WindowButton(objectType = "silled-window")
        self.casementWindowButton = WindowButton(objectType = "casement-window")
        self.stairButton = WindowButton(objectType = "stair")
        self.otherButton = self.stairButton
        self.counterButton = WindowButton(objectType = "counter")
        self.railingButton = WindowButton(objectType = "railing")
        self.pillarButton = WindowButton(objectType = "pillar")
        self.columnButton = WindowButton(objectType = "column")
        self.elevatorButton = WindowButton(objectType = "elevator")
        self.fireplaceButton = WindowButton(objectType = "fireplace")
        self.northArrowButton = WindowButton(objectType = "north-arrow")
        self.labelButton = WindowButton(objectType = "label")
        self.arrowButton = WindowButton(objectType = "arrow")
        self.measurementGuideButton = WindowButton(objectType = "measurement-guide")
        self.angleGuideButton = WindowButton(objectType = "angle-guide")
        self.angleGuideButton.setAccessibleName("Angle Guide")
        self.angleGuideButton.setToolTip("Drag an Angle Guide onto the canvas. Move its middle point to carry both arms.")
        categories = (("Doors", ((self.doorButton, "Standard"), (self.slidingDoorButton, "Sliding"),
                                  (self.pocketDoorButton, "Pocket"), (self.barnDoorButton, "Barn"),
                                  (self.bifoldDoorButton, "Bifold"), (self.openDoorwayButton, "Open"))),
                      ("Windows", ((self.windowButton, "Standard"), (self.silledWindowButton, "Silled"),
                                    (self.casementWindowButton, "Casement"))),
                      ("Miscellaneous", ((self.stairButton, "Stair"), (self.counterButton, "Counter"), (self.railingButton, "Railing"), (self.pillarButton, "Pillar"), (self.columnButton, "Column"), (self.fireplaceButton, "Fireplace"), (self.elevatorButton, "Elevator"))),
                      ("Annotations", ((self.labelButton, "Label"), (self.arrowButton, "Arrow"), (self.measurementGuideButton, "Measure"), (self.angleGuideButton, "Angle"), (self.northArrowButton, "North"))))
        self.buildObjectLayouts = {}
        for category, buttons in categories:
            heading = QtWidgets.QLabel(category)
            heading.setObjectName("objectSubheading")
            toolsLayout.addWidget(heading)
            toolsLayout.addSpacing(6)
            grid = FurnishingIconLayout()
            self.buildObjectLayouts[category] = grid
            for button, caption in buttons:
                iconWidget = QtWidgets.QWidget()
                iconLayout = QtWidgets.QVBoxLayout(iconWidget)
                iconLayout.setContentsMargins(0, 0, 0, 0)
                iconLayout.setSpacing(4)
                iconLayout.addWidget(button, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)
                captionLabel = QtWidgets.QLabel(caption)
                captionLabel.setObjectName("openingIconCaption")
                captionLabel.setFixedWidth(64)
                captionLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                iconLayout.addWidget(captionLabel)
                grid.addWidget(iconWidget)
            toolsLayout.addLayout(grid)
            toolsLayout.addSpacing(16)
        toolsLayout.addStretch(1)
        self.buildScrollArea = QtWidgets.QScrollArea()
        self.buildScrollArea.setWidgetResizable(True)
        self.buildScrollArea.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.buildScrollArea.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.buildScrollArea.setWidget(toolsPage)
        self.sidebarTabs.addTab(self.buildScrollArea, HeaderIcon("Construction"), "Build")
        self.openingToolButtons = {Door: self.doorButton, SlidingDoor: self.slidingDoorButton,
                                   PocketDoor: self.pocketDoorButton, BarnDoor: self.barnDoorButton, BifoldDoor: self.bifoldDoorButton, OpenDoorway: self.openDoorwayButton, Window: self.windowButton,
                                   SilledWindow: self.silledWindowButton, CasementWindow: self.casementWindowButton}

    def BuildFurnishTab(self, refresh = False):
        searchText = self.furnishingSearchField.text() if refresh else ""
        if refresh:
            self.furnishingViewPanel.setParent(self.furnishPage)
            self.furnishPage.layout().removeWidget(self.furnishingSearchPanel)
            self.furnishingSearchPanel.deleteLater()
        else:
            self.furnishPage = QtWidgets.QWidget()
            furnishPageLayout = QtWidgets.QVBoxLayout(self.furnishPage)
            furnishPageLayout.setContentsMargins(0, 0, 0, 0)
            furnishPageLayout.setSpacing(0)
        furnishingsPage = QtWidgets.QWidget()
        furnishingsLayout = QtWidgets.QVBoxLayout(furnishingsPage)
        furnishingsLayout.setContentsMargins(14, 0, 14, 14)
        self.furnishingSearchPanel = QtWidgets.QWidget()
        searchLayout = QtWidgets.QHBoxLayout(self.furnishingSearchPanel)
        searchLayout.setContentsMargins(14, 14, 14, 16)
        searchLayout.setSpacing(10)
        self.furnishingSearchField = QtWidgets.QLineEdit()
        self.furnishingSearchField.setObjectName("furnishingSearch")
        self.furnishingSearchField.setAccessibleName("Search furnishings")
        self.furnishingSearchField.setPlaceholderText("Search…")
        self.furnishingSearchClearAction = self.furnishingSearchField.addAction(
            UiIcon("close", themeColors["mutedText"]), QtWidgets.QLineEdit.ActionPosition.TrailingPosition)
        self.furnishingSearchClearAction.setToolTip("Clear search")
        self.furnishingSearchClearButton = self.furnishingSearchField.findChild(QtWidgets.QToolButton)
        self.furnishingSearchField.addAction(UiIcon("search"), QtWidgets.QLineEdit.ActionPosition.LeadingPosition)
        self.furnishingSearchClearAction.triggered.connect(self.furnishingSearchField.clear)
        self.furnishingSearchClearAction.setVisible(bool(searchText))
        self.furnishingSearchField.textChanged.connect(lambda text: self.furnishingSearchClearAction.setVisible(bool(text)))
        self.furnishingSearchField.setToolTip("Search names, categories, keywords or dimensions: 40, 40 60, w:40 l:60.\n"
                                            "Also accepts 40 × 60 and 400 mm. Bare dimensions prefer the selected units.\n"
                                            "Results are sorted by relevance. Clear the search to use the browsing sort.")
        self.furnishingSearchField.setText(searchText)
        searchLayout.addWidget(self.furnishingSearchField, 1)
        self.furnishPage.layout().insertWidget(0, self.furnishingSearchPanel)
        if not refresh:
            self.furnishingListView = self.appPreferences.get("furnishingListView") is True
            self.furnishingViewPanel = QtWidgets.QWidget()
            viewLayout = QtWidgets.QHBoxLayout(self.furnishingViewPanel)
            viewLayout.setContentsMargins(0, 0, 0, 0)
            viewLayout.setSpacing(8)
            self.furnishingViewButton = QtWidgets.QToolButton()
            self.furnishingViewButton.setObjectName("viewportToolbarButton")
            self.furnishingViewButton.setProperty("modeSelector", True)
            self.furnishingViewButton.setAccessibleName("Furnishing list view")
            self.furnishingViewButton.setCheckable(True)
            self.furnishingViewButton.setChecked(self.furnishingListView)
            self.furnishingViewButton.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            self.furnishingViewButton.setFixedSize(32, 32)
            self.furnishingViewButton.setIconSize(QtCore.QSize(26, 26))
            self.furnishingViewButton.setIcon(UiIcon("grid_view"))
            self.furnishingViewButton.setToolTip("Switch to list view")
            self.furnishingViewButton.toggled.connect(self.SetFurnishingListView)
            self.furnishingSortMode = self.appPreferences.get("furnishingSortMode", "Category")
            if self.furnishingSortMode not in ("Category", "Alphabetical", "Width", "Length", "Area"):
                self.furnishingSortMode = "Category"
            self.furnishingSortDescending = self.appPreferences.get("furnishingSortDescending") is True
            self.furnishingSortButton = QtWidgets.QToolButton()
            self.furnishingSortButton.setObjectName("viewportToolbarButton")
            self.furnishingSortButton.setAccessibleName("Sort furnishings")
            self.furnishingSortButton.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            self.furnishingSortButton.setFixedSize(32, 32)
            self.furnishingSortButton.setIconSize(QtCore.QSize(26, 26))
            self.furnishingSortButton.setIcon(UiIcon("sort"))
            self.furnishingSortMenu = QtWidgets.QMenu(self.furnishingSortButton)
            self.furnishingSortMenu.setObjectName("viewportContextMenu")
            self.furnishingSortOptions = {}
            for name in ("Category", "Alphabetical", "Width", "Length", "Area"):
                button = AddMenuButton(self.furnishingSortMenu, name, iconName = UiIcon("check"))
                button.setCheckable(True)
                button.clicked.connect(lambda checked = False, name = name: self.SetFurnishingSort(name))
                self.furnishingSortOptions[name] = button
            self.furnishingSortButton.clicked.connect(lambda: self.furnishingSortMenu.popup(
                self.furnishingSortButton.mapToGlobal(QtCore.QPoint(0, self.furnishingSortButton.height()))))
            viewLayout.addWidget(self.furnishingSortButton)
            viewLayout.addWidget(self.furnishingViewButton)
            self.furnishingList = FurnishingCatalogList(self)
            self.furnishingList.hide()
            self.furnishPage.layout().addWidget(self.furnishingList, 1)
        searchLayout.addWidget(self.furnishingViewPanel)
        self.furnishingViewPanel.show()
        self.furnishingList.resultKey = None
        categories = {}
        for definition in self.viewport.furnishingDefinitions.values():
            if definition["key"] == "null":
                continue
            for category in definition.get("categories", [definition["category"]]):
                categories.setdefault(category, []).append(definition)
        self.furnishingButtons = {}
        self.furnishingCards = {}
        self.furnishingDimensionLabels = {}
        self.furnishingCategoryCards = {}
        self.furnishingCategoryDimensionLabels = {}
        self.furnishingCategoryWidgets = {}
        self.furnishingCategoryLayouts = {}
        self.furnishingCardStorage = QtWidgets.QWidget(furnishingsPage)
        self.furnishingCardStorage.hide()
        for category in sorted(categories, key = lambda name: (name.casefold() in ("misc", "miscellaneous"), name.casefold())):
            definitions = sorted(categories[category], key = lambda item: (item["name"].strip().casefold(), item["key"]))
            categoryWidget = QtWidgets.QWidget()
            categoryLayout = QtWidgets.QVBoxLayout(categoryWidget)
            categoryLayout.setContentsMargins(0, 0, 0, 0)
            categoryLayout.setSpacing(0)
            heading = QtWidgets.QLabel(category)
            heading.setObjectName("objectSubheading")
            categoryLayout.addWidget(heading)
            categoryLayout.addSpacing(6)
            grid = FurnishingIconLayout()
            self.furnishingCategoryWidgets[category] = categoryWidget
            self.furnishingCategoryLayouts[category] = grid
            for definition in definitions:
                button = FurnishingButton(definition)
                self.furnishingButtons.setdefault(definition["key"], button)
                dimensions = QtWidgets.QLabel()
                dimensions.setObjectName("furnishingDimensions")
                dimensions.setWordWrap(True)
                dimensions.setFixedWidth(64)
                dimensions.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop)
                self.furnishingDimensionLabels.setdefault(definition["key"], dimensions)
                self.furnishingCategoryDimensionLabels[(definition["key"], category)] = dimensions
                caption = QtWidgets.QLabel(definition["name"])
                caption.setObjectName("openingIconCaption")
                caption.setWordWrap(True)
                caption.setFixedWidth(64)
                caption.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop)
                iconWidget = QtWidgets.QWidget()
                self.furnishingCards.setdefault(definition["key"], iconWidget)
                self.furnishingCategoryCards[(definition["key"], category)] = iconWidget
                iconLayout = QtWidgets.QVBoxLayout(iconWidget)
                iconLayout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
                iconLayout.setContentsMargins(0, 0, 0, 0)
                iconLayout.setSpacing(4)
                iconLayout.addWidget(button, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)
                iconLayout.addWidget(dimensions)
                iconLayout.addWidget(caption)
                grid.addWidget(iconWidget)
            categoryLayout.addLayout(grid)
            categoryLayout.addSpacing(16)
            furnishingsLayout.addWidget(categoryWidget)
        self.furnishingResultsWidget = QtWidgets.QWidget()
        resultsLayout = QtWidgets.QVBoxLayout(self.furnishingResultsWidget)
        resultsLayout.setContentsMargins(0, 0, 0, 0)
        resultsLayout.setSpacing(6)
        resultsHeading = QtWidgets.QLabel("Search Results")
        self.furnishingResultsHeading = resultsHeading
        resultsHeading.setObjectName("objectSubheading")
        resultsLayout.addWidget(resultsHeading)
        self.furnishingResultsLayout = FurnishingIconLayout()
        resultsLayout.addLayout(self.furnishingResultsLayout)
        self.furnishingNoResults = QtWidgets.QLabel("No results")
        self.furnishingNoResults.setObjectName("furnishingNoResults")
        self.furnishingNoResults.setContentsMargins(0, 12, 0, 0)
        resultsLayout.addWidget(self.furnishingNoResults)
        furnishingsLayout.addWidget(self.furnishingResultsWidget)
        furnishingsLayout.addStretch(1)
        if not refresh:
            self.furnishScrollArea = QtWidgets.QScrollArea()
            self.furnishScrollArea.setWidgetResizable(True)
            self.furnishScrollArea.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            self.furnishScrollArea.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.furnishScrollArea.setWidget(furnishingsPage)
        if not refresh:
            self.furnishPage.layout().addWidget(self.furnishScrollArea, 1)
            self.sidebarTabs.addTab(self.furnishPage, HeaderIcon("Chair"), "Furnish")
        self.furnishingSearchKey = None
        self.furnishingDimensionMode = None
        self.furnishingSearchActive = False
        self.furnishingResultKeys = ()
        self.furnishingCategoryOrderKey = None
        self.furnishingSearchTimer = QtCore.QTimer(self.furnishingSearchField)
        self.furnishingSearchTimer.setSingleShot(True)
        self.furnishingSearchTimer.setInterval(120)
        self.furnishingSearchTimer.timeout.connect(self.UpdateFurnishingSearch)
        self.furnishingSearchField.textChanged.connect(lambda text: self.furnishingSearchTimer.start())
        self.furnishingSearchField.textChanged.connect(lambda text: self.furnishingSortButton.setEnabled(not text.strip()))
        self.SetFurnishingListView(self.furnishingListView)
        self.SetFurnishingSort(self.furnishingSortMode, toggle = False)

    def SetFurnishingSort(self, mode, toggle = True):
        if mode not in self.furnishingSortOptions:
            return
        if toggle:
            self.furnishingSortDescending = not self.furnishingSortDescending if mode == self.furnishingSortMode else False
        self.furnishingSortMode = mode
        for name, button in self.furnishingSortOptions.items():
            button.setChecked(name == mode)
            if name == mode:
                button.iconLabel.setPixmap(UiIcon("check").pixmap(18, 18))
                button.shortcutLabel.setPixmap(UiIcon("arrow_drop_down" if self.furnishingSortDescending else "arrow_drop_up").pixmap(18, 18))
            else:
                button.iconLabel.clear()
                button.shortcutLabel.clear()
        direction = "descending" if self.furnishingSortDescending else "ascending"
        self.furnishingSortButton.setToolTip("Sort furnishings: " + mode + " (" + direction + ")")
        self.UpdateFurnishingSearch()
        if (self.appPreferences.get("furnishingSortMode", "Category") != mode or
                self.appPreferences.get("furnishingSortDescending", False) != self.furnishingSortDescending):
            self.appPreferences.update(furnishingSortMode = mode, furnishingSortDescending = self.furnishingSortDescending)
            self.SaveAppPreferences()

    def SetFurnishingListView(self, enabled):
        self.furnishingListView = enabled
        self.furnishingViewButton.setIcon(UiIcon("view_list" if enabled else "grid_view"))
        self.furnishingViewButton.setToolTip("Switch to grid view" if enabled else "Switch to list view")
        self.furnishScrollArea.setVisible(not enabled)
        self.furnishingList.setVisible(enabled)
        self.UpdateFurnishingSearch()
        if self.appPreferences.get("furnishingListView", False) != enabled:
            self.appPreferences["furnishingListView"] = enabled
            self.SaveAppPreferences()

    def UpdateFurnishingSearch(self):
        query = self.furnishingSearchField.text().strip()
        self.furnishingSortButton.setEnabled(not query)
        direction = "descending" if self.furnishingSortDescending else "ascending"
        self.furnishingSortButton.setToolTip("Search results are sorted by relevance. Clear the search to change sorting."
                                            if query else "Sort furnishings: " + self.furnishingSortMode + " (" + direction + ")")
        if query:
            self.furnishingSortMenu.hide()
        key = (query, self.viewport.unitsMode, self.furnishingListView, self.furnishingSortMode, self.furnishingSortDescending)
        if key == self.furnishingSearchKey:
            return
        self.furnishingSearchKey = key
        definitions = list(self.viewport.furnishingDefinitions.values())
        mode = self.viewport.unitsMode
        if mode != self.furnishingDimensionMode:
            for definition in definitions:
                if definition["key"] == "null":
                    continue
                dimensions = FurnishingDimensionText(definition, mode)
                for category in definition.get("categories", [definition["category"]]):
                    self.furnishingCategoryDimensionLabels[(definition["key"], category)].setText(dimensions)
            self.furnishingDimensionMode = mode
        results = (FindFurnishings(definitions, query, self.viewport.unitsMode) if query else
                   SortFurnishings(definitions, self.furnishingSortMode, self.furnishingSortDescending, self.viewport.unitsMode))
        resultKeys = tuple(definition["key"] for definition in results if definition["key"] != "null")
        if self.furnishingListView:
            self.furnishingList.UpdateItems(results, query)
            self.furnishScrollArea.hide()
            return
        flat = bool(query) or self.furnishingSortMode != "Category"
        self.furnishingResultsHeading.setVisible(bool(query))
        if flat:
            if not self.furnishingSearchActive:
                for category, grid in self.furnishingCategoryLayouts.items():
                    self.furnishingCategoryWidgets[category].hide()
                    while grid.count():
                        card = grid.takeAt(grid.count() - 1).widget()
                        card.hide()
                        card.setParent(self.furnishingCardStorage)
                    grid.invalidate()
            if not self.furnishingSearchActive or resultKeys != self.furnishingResultKeys:
                # Batch insertions in a hidden container; retain shared cards
                # and layout items rather than reparenting them per keystroke.
                self.furnishingResultsWidget.hide()
                self.furnishingResultsLayout.SetWidgets([self.furnishingCards[key] for key in resultKeys])
            self.furnishingResultsWidget.show()
        else:
            self.furnishingResultsWidget.hide()
            categoryOrderKey = self.furnishingSortDescending
            if self.furnishingSearchActive or self.furnishingCategoryOrderKey != categoryOrderKey:
                self.furnishingResultsLayout.SetWidgets([])
                categories = list(self.furnishingCategoryLayouts)
                if self.furnishingSortDescending:
                    categories.reverse()
                for position, category in enumerate(categories):
                    grid = self.furnishingCategoryLayouts[category]
                    cards = [card for (key, cardCategory), card in self.furnishingCategoryCards.items() if cardCategory == category]
                    grid.SetWidgets(cards[::-1] if self.furnishingSortDescending else cards)
                    self.furnishScrollArea.widget().layout().insertWidget(position, self.furnishingCategoryWidgets[category])
                    self.furnishingCategoryWidgets[category].show()
                self.furnishingCategoryOrderKey = categoryOrderKey
        self.furnishingNoResults.setVisible(flat and not results)
        self.furnishingSearchActive = flat
        self.furnishingResultKeys = resultKeys if flat else ()
        self.furnishScrollArea.verticalScrollBar().setValue(0)
