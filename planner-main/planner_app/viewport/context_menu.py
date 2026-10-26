"""Object menus with generic commands and shared class-specific actions."""
from planner_app.dimension_policy import AvailableDimensionActions
from planner_app.models import Elevator

from PySide6 import QtCore, QtGui
from planner_app.graphics.palette import themeColors
from planner_app.graphics.theme import HeaderIcon, MaterialIcon, UiIcon, wallMaterials
from planner_app.models import Door, SwingingDoor, DoubleDoor, Furnishing, PocketDoor, BarnDoor, BifoldDoor, OpenDoorway, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, SlidingDoor, Arrow, Stair, Counter, Railing, MeasurementGuide, Wall, Pillar, Column, Label, Window, Fireplace
from planner_app.models import BoundaryLine, DashedLine, SolidLine, AngleGuide
from planner_app.ui.menus import AddMenuButton, AddSubmenuButton


class ContextMenuMixin:
    def ShowObjectContextMenu(self, position, globalPosition):
        hitObject, hitIndex, handle = self.SelectionTarget(position)
        members = getattr(hitObject, "selectionMembers", ())
        if members:
            hitObject = self.selectedWall if self.selectedWall in members else members[-1]
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
                    for wall in self.walls if type(wall) is type(hitObject) and type(wall) not in (Pillar, Column, Elevator, AngleGuide) and self.IsObjectVisible(wall)
                    for vertex in (wall.firstVertex, wall.secondVertex)]
        nearestVertex = min(vertices, key = lambda entry: entry[0]) if vertices else None
        if nearestVertex is not None and nearestVertex[0] <= self.vertexSnapRange:
            vertex = QtCore.QPointF(nearestVertex[1])
            sharedWalls = [wall for wall in self.walls if type(wall) is type(hitObject) and any(
                QtCore.QLineF(vertex, endpoint).length() <= .01 for endpoint in (wall.firstVertex, wall.secondVertex))]
            if len(sharedWalls) == 2:
                button = AddMenuButton(menu, "Dissolve Control Point", iconName = "Construction")
                button.clicked.connect(lambda checked = False, vertex = vertex: self.DissolveWalls(vertex, type(hitObject)))
        if len({Wall if type(obj) in (Wall, Pillar, Column) else type(obj) for obj in objects}) == 1:
            objectType = Wall if any(type(obj) is Wall for obj in objects) else type(objects[0])
            options = []
            if all(isinstance(obj, Wall) and type(obj) not in (Pillar, Column, Elevator, AngleGuide) for obj in objects):
                button = AddMenuButton(menu, "Subdivide Wall" if objectType is Wall else "Subdivide", iconName = "Construction")
                button.clicked.connect(lambda checked = False, objects = objects: self.SubdivideWalls(objects))
            if objectType in (Wall, Pillar, Column):
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
                options = [("Bring to Front", "front", "flip_to_front"), ("Move to Back", "back", "flip_to_back")]
                if len(objects) >= 2:
                    button = AddMenuButton(menu, "Create Furnishing from Selection…", iconName = "Chair")
                    button.clicked.connect(lambda checked = False, objects = objects:
                                           self.window().CreateFurnishingFromSelection(objects))
                if any(obj.definition.get("components") for obj in objects):
                    button = AddMenuButton(menu, "Decompose", iconName = "Construction")
                    button.clicked.connect(lambda checked = False, objects = objects: self.DecomposeFurnishings(objects))
            elif objectType is Arrow:
                options = [("Flip Direction", "reverseDirection", "Undo" if objects[0].directionReversed else "Redo")]
            elif objectType is Stair:
                options = [("Flip Direction", "directionReversed", "Undo" if objects[0].directionReversed else "Redo")]
            elif objectType in (Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, Fireplace):
                options = [("Flip Facing", "swingsOutwards", "flip_v")]
                if objectType is CasementWindow:
                    options.append(("Flip Hinge Side", "hingeAtSecond", "flip_h"))
            elif objectType is Door:
                options = [("Flip Swing Direction", "swingsOutwards", "flip_v"),
                           ("Flip Hinge Side", "hingeAtSecond", "flip_h")]
            elif objectType is SwingingDoor:
                options = [("Flip Hinge Side", "hingeAtSecond", "flip_h")]
            elif objectType is DoubleDoor:
                options = [("Flip Swing Direction", "swingsOutwards", "flip_v")]
            elif objectType is SlidingDoor:
                options = [("Flip Panel Side", "panelsFlipped", "flip_v"),
                           ("Flip Slide Direction", "hingeAtSecond", "flip_h")]
            elif objectType is BifoldDoor:
                options = [("Flip Swing Direction", "swingsOutwards", "flip_v")]
            elif objectType is BarnDoor:
                options = [("Flip Facing", "swingsOutwards", "flip_v"), ("Flip Slide Direction", "hingeAtSecond", "flip_h")]
            elif objectType is PocketDoor:
                options = [("Flip Pocket Side", "hingeAtSecond", "flip_h")]
            if any(AvailableDimensionActions(self, obj).canFlip for obj in objects):
                options.append(("Flip Dimension", "measurementFlipped", "Measurements"))
            if options:
                for label, command, iconName in options:
                    button = AddMenuButton(menu, label, iconName = UiIcon(iconName) if iconName.startswith("flip_") else iconName)
                    button.clicked.connect(lambda checked = False, command = command, objects = objects:
                                           self.ApplyObjectContextAction(objects, command))
        if not (len(objects) == 1 and isinstance(objects[0], Window)):
            for label, command, icon in (("Flip Horizontal", "flipHorizontal", "flip_h"),
                                          ("Flip Vertical", "flipVertical", "flip_v")):
                button = AddMenuButton(menu, label, iconName = UiIcon(icon))
                axis = "vertical" if command == "flipHorizontal" else "horizontal"
                button.setToolTip("Mirror across the selection's " + axis + " axis, or each object's local " + axis + " axis in Local mode")
                button.clicked.connect(lambda checked = False, command = command, objects = objects:
                                       self.ApplyObjectContextAction(objects, command))
        if AvailableDimensionActions(self, hitObject).canHide:
            hide = not hitObject.measurementHidden
            button = AddMenuButton(menu, "Hide Dimension" if hide else "Show Dimension", iconName = "View")
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
        if command == "measurementFlipped":
            objects = [obj for obj in objects if AvailableDimensionActions(self, obj).canFlip]
            if not objects:
                return False
        if command in ("front", "back"):
            self.MoveFurnishingLayer(objects, command == "front")
            return
        if command in ("flipHorizontal", "flipVertical"):
            return self.FlipObjects(objects, command == "flipHorizontal", value)
        before = self.CaptureState()
        for obj in objects:
            if isinstance(obj, Arrow) and command == "reverseDirection":
                obj.firstVertex, obj.secondVertex = QtCore.QPointF(obj.secondVertex), QtCore.QPointF(obj.firstVertex)
                obj.firstMiter, obj.secondMiter = obj.secondMiter, obj.firstMiter
                obj.directionReversed = not obj.directionReversed
                continue
            setattr(obj, command, value if value is not None else not getattr(obj, command))
        if command == "reverseDirection":
            reversedIds = {id(obj) for obj in objects if isinstance(obj, Arrow)}
            self.SetSelection([(obj, 1 - index if id(obj) in reversedIds and index in (0, 1) else index)
                               for obj, index in self.SelectionEntries()])
        self.RecordEdit(before)
        self.selectionChanged.emit()
        self.update()
