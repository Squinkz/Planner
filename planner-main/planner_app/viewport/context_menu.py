"""Object menus with generic commands and shared class-specific actions."""
from planner_app.models import Elevator

from PySide6 import QtCore, QtGui
from planner_app.graphics.palette import themeColors
from planner_app.graphics.theme import HeaderIcon, MaterialIcon, UiIcon, wallMaterials
from planner_app.models import Door, Furnishing, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway, SilledWindow, CasementWindow, SlidingDoor, Stair, Counter, Railing, MeasurementGuide, Wall, Pillar, Column, Label, Window, Fireplace
from planner_app.models import BoundaryLine
from planner_app.ui.menus import AddMenuButton, AddSubmenuButton


class ContextMenuMixin:
    def ShowObjectContextMenu(self, position, globalPosition):
        hitObject, hitIndex = self.HitTest(position)
        menu = self.objectContextMenu
        if hasattr(menu, "materialController"):
            menu.materialController.HideChildMenu()
            del menu.materialController
        if hasattr(menu, "materialMenu"):
            del menu.materialMenu
        menu.clear()
        if hitObject is None:
            button = AddMenuButton(menu, "Paste", "Ctrl + V")
            enabled = self.ReadClipboardSelection() is not None
            button.setEnabled(enabled)
            button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor if enabled else QtCore.Qt.CursorShape.ArrowCursor)
            button.clicked.connect(lambda checked = False: self.PasteSelection(position))
            menu.popup(globalPosition)
            return
        entries = self.SelectionEntries()
        if not any(obj is hitObject for obj, index in entries):
            self.SetSelection([(hitObject, None)])
            entries = self.SelectionEntries()
        # Context commands act on objects, even when their vertices are selected.
        objects = list({id(obj): obj for obj, index in entries}.values())
        vertices = [(QtCore.QLineF(position, self.WorldToViewport(vertex)).length(), vertex)
                    for wall in self.walls if type(wall) is Wall and self.IsObjectVisible(wall)
                    for vertex in (wall.firstVertex, wall.secondVertex)]
        nearestVertex = min(vertices, key = lambda entry: entry[0]) if vertices else None
        if nearestVertex is not None and nearestVertex[0] <= self.vertexSnapRange:
            vertex = QtCore.QPointF(nearestVertex[1])
            sharedWalls = [wall for wall in self.walls if type(wall) is Wall and any(
                QtCore.QLineF(vertex, endpoint).length() <= .01 for endpoint in (wall.firstVertex, wall.secondVertex))]
            if len(sharedWalls) == 2:
                button = AddMenuButton(menu, "Dissolve Control Point", iconName = "Construction")
                button.clicked.connect(lambda checked = False, vertex = vertex: self.DissolveWalls(vertex))
        if len({Wall if type(obj) in (Wall, Pillar, Column) else type(obj) for obj in objects}) == 1:
            objectType = Wall if any(type(obj) is Wall for obj in objects) else type(objects[0])
            options = []
            if objectType in (Wall, Pillar, Column):
                if all(type(obj) is Wall for obj in objects):
                    button = AddMenuButton(menu, "Subdivide Wall", iconName = "Construction")
                    button.clicked.connect(lambda checked = False, objects = objects: self.SubdivideWalls(objects))
                def PopulateMaterials(materialMenu):
                    materialMenu.setStyleSheet("QPushButton#headerMenuItem { padding: 5px 0; } "
                                              "QPushButton#headerMenuItem:checked { background: " + themeColors["activeBackground"] + "; }")
                    menu.materialMenu = materialMenu
                    materials = {obj.material for obj in objects}
                    for material in wallMaterials:
                        materialButton = AddMenuButton(materialMenu, material, iconName = "Settings")
                        materialButton.iconLabel.setFixedSize(32, 24)
                        materialButton.iconLabel.setPixmap(MaterialIcon(material).pixmap(32, 24))
                        materialButton.layout().setSpacing(0)
                        materialButton.setCheckable(True)
                        materialButton.setChecked(materials == {material})
                        materialButton.clicked.connect(menu.hide)
                        materialButton.clicked.connect(lambda checked = False, material = material, objects = objects:
                                                       self.ApplyObjectContextAction(objects, "material", material))
                button = AddSubmenuButton(self, menu, "Settings", "Material", PopulateMaterials)
                menu.materialController = button._submenuController
            elif objectType is Furnishing:
                options = [("Bring to Front", "front", "flip_to_front"), ("Move to Back", "back", "flip_to_back"),
                           ("Flip Horizontal", "flipHorizontal", "flip_h"), ("Flip Vertical", "flipVertical", "flip_v")]
                if len(objects) >= 2:
                    button = AddMenuButton(menu, "Create Furnishing from Selection…", iconName = "Chair")
                    button.clicked.connect(lambda checked = False, objects = objects:
                                           self.window().CreateFurnishingFromSelection(objects))
                if any(obj.definition.get("components") for obj in objects):
                    button = AddMenuButton(menu, "Decompose", iconName = "Construction")
                    button.clicked.connect(lambda checked = False, objects = objects: self.DecomposeFurnishings(objects))
            elif objectType is Stair:
                options = [("Flip Direction", "directionReversed", "Undo" if objects[0].directionReversed else "Redo")]
            elif objectType in (Window, SilledWindow, CasementWindow, Fireplace):
                options = [("Flip Facing", "swingsOutwards", "flip_v")]
                if objectType is CasementWindow:
                    options.append(("Flip Hinge Side", "hingeAtSecond", "flip_h"))
            elif objectType is Door:
                options = [("Flip Swing Direction", "swingsOutwards", "flip_v"),
                           ("Flip Hinge Side", "hingeAtSecond", "flip_h")]
            elif objectType is SlidingDoor:
                options = [("Flip Panel Side", "panelsFlipped", "flip_v"),
                           ("Flip Slide Direction", "hingeAtSecond", "flip_h")]
            elif objectType is BifoldDoor:
                options = [("Flip Swing Direction", "swingsOutwards", "flip_v")]
            elif objectType is BarnDoor:
                options = [("Flip Facing", "swingsOutwards", "flip_v"), ("Flip Slide Direction", "hingeAtSecond", "flip_h")]
            elif objectType is PocketDoor:
                options = [("Flip Pocket Side", "hingeAtSecond", "flip_h")]
            if objectType in (Door, SlidingDoor, BarnDoor, Window, SilledWindow, CasementWindow):
                measurementClass = "windows" if objectType in (Window, SilledWindow, CasementWindow) else "doors"
                if (self.showMeasurements and self.measurementVisibility["walls"]
                        and self.measurementSettings[measurementClass] == 1
                        and any(not obj.measurementHidden for obj in objects)):
                    options.append(("Flip Measurement", "measurementFlipped", "Measurements"))
            if options:
                for label, command, iconName in options:
                    button = AddMenuButton(menu, label, iconName = UiIcon(iconName) if iconName.startswith("flip_") else iconName)
                    if objectType is Furnishing and command in ("flipHorizontal", "flipVertical"):
                        button.setToolTip("Mirror across the global " + ("Y" if command == "flipHorizontal" else "X") +
                                          " axis through the furnishing's center")
                    button.clicked.connect(lambda checked = False, command = command, objects = objects:
                                           self.ApplyObjectContextAction(objects, command))
        measurementEnabled = False
        if isinstance(hitObject, Elevator):
            measurementEnabled = self.measurementVisibility["elevators"]
        elif isinstance(hitObject, (Stair, Counter, Railing)):
            category = "stairs" if isinstance(hitObject, Stair) else "counters" if isinstance(hitObject, Counter) else "railings"
            measurementEnabled = self.measurementVisibility[category]
        elif type(hitObject) in (Wall, Pillar, Column) or isinstance(hitObject, Fireplace):
            measurementEnabled = self.measurementVisibility["walls"]
        elif isinstance(hitObject, Window):
            category = "doors" if isinstance(hitObject, (Door, SlidingDoor, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway)) else "windows"
            measurementEnabled = self.measurementVisibility["walls"] and self.measurementSettings[category] != 2
        elif isinstance(hitObject, MeasurementGuide) and not isinstance(hitObject, BoundaryLine):
            measurementEnabled = True
        if self.showMeasurements and measurementEnabled:
            hide = not hitObject.measurementHidden
            button = AddMenuButton(menu, "Hide measurement" if hide else "Show measurement", iconName = "View")
            button.clicked.connect(lambda checked = False, obj = hitObject, hide = hide:
                                   self.ApplyObjectContextAction([obj], "measurementHidden", hide))
        selectedIds = {id(obj) for obj in objects}
        canGroup = len(objects) > 1 and not any(
            {id(obj) for obj in group} == selectedIds for group in self.objectGroups)
        canUngroup = any(id(obj) in selectedIds for group in self.objectGroups for obj in group)
        if canGroup or canUngroup:
            if menu.actions():
                menu.addSeparator()
            if canGroup:
                button = AddMenuButton(menu, "Group selected", "Ctrl + G", iconName = "Group")
                button.clicked.connect(self.GroupSelection)
            if canUngroup:
                button = AddMenuButton(menu, "Ungroup selected", "Alt + G", iconName = "Ungroup")
                button.clicked.connect(self.UngroupSelection)
        if menu.actions():
            menu.addSeparator()
        button = AddMenuButton(menu, "Transform", "T")
        button.clicked.connect(lambda checked = False: self.window().ShowMoveSpecial())
        menu.addSeparator()
        button = AddMenuButton(menu, "Cut", "Ctrl + X")
        button.setEnabled(self.CanCopySelection())
        button.clicked.connect(self.CutSelection)
        button = AddMenuButton(menu, "Copy", "Ctrl + C")
        button.setEnabled(self.CanCopySelection())
        button.clicked.connect(self.CopySelection)
        menu.addSeparator()
        button = AddMenuButton(menu, "Delete", "Del", iconName = "Close Project")
        button.clicked.connect(self.DeleteSelected)
        menu.popup(globalPosition)

    def ApplyObjectContextAction(self, objects, command, value = None):
        if command in ("front", "back"):
            self.MoveFurnishingLayer(objects, command == "front")
            return
        before = self.CaptureState()
        for obj in objects:
            if (type(obj) is Furnishing and command in ("flipHorizontal", "flipVertical")
                    and (value is None or value != getattr(obj, command))):
                # Reflect the rotated local axes across the world axis through
                # this object's centre, then reflect its artwork on that axis.
                obj.angle = -obj.angle
            setattr(obj, command, value if value is not None else not getattr(obj, command))
        self.RecordEdit(before)
        self.selectionChanged.emit()
        self.update()
