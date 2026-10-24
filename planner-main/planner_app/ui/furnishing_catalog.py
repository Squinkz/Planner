"""Create reusable furnishing definitions from a canvas selection."""
import json
import re
import unicodedata
import warnings
from pathlib import Path
from PySide6 import QtCore, QtWidgets
from planner_app.catalog import LoadFurnishings, FurnishingCategories
from planner_app.graphics.furnishings import FurnishingRenderer, SelectedFurnishingRenderer
from planner_app.graphics.theme import HeaderIcon
from planner_app.models import Furnishing
from planner_app.ui.widgets import DownwardComboBox


class FurnishingCatalogMixin:
    def ShowFurnishingSearch(self, position):
        v = self.viewport
        if (v.exportOverlay.active or not v.DrawingRect().contains(position)
                or v.pendingWall is not None or v.dragStart is not None or v.boxStart is not None
                or v.rightClickStart is not None or v.furnishingHandleDrag is not None
                or v.guiDragActive or v.isPanning or v.openingPlacementMode is not None):
            return False
        if getattr(self, "furnishingQuickSearch", None) is None:
            from .furnishing_quick_search import FurnishingQuickSearch
            self.furnishingQuickSearch = FurnishingQuickSearch(self)
        self.viewport.objectContextMenu.hide()
        self.furnishingQuickSearch.OpenAt(QtCore.QPointF(position))
        return True

    def CreateFurnishingFromSelection(self, objects):
        selectedIds = {id(obj) for obj in objects if type(obj) is Furnishing}
        furnishings = [obj for obj in self.viewport.furnishings if id(obj) in selectedIds]
        # Match DrawScene's two furnishing passes, retaining list order within
        # each pass. Duplicated back-layer objects can occur later in the list.
        furnishings.sort(key = lambda obj: not obj.behindCounters)
        if len(furnishings) < 2 or len(selectedIds) != len({id(obj) for obj in objects}):
            return
        corners = [corner for obj in furnishings for corner in self.viewport.ObjectCorners(obj)]
        center = QtCore.QPointF((min(point.x() for point in corners) + max(point.x() for point in corners)) / 2,
                                (min(point.y() for point in corners) + max(point.y() for point in corners)) / 2)
        children = []
        for index, obj in enumerate(furnishings):
            position = (obj.firstVertex + obj.secondVertex) / 2 - center
            children.append({"furnishing": obj.definition["key"], "x": round(position.x(), 6),
                             "y": round(position.y(), 6), "width": round(obj.width, 6),
                             "length": round(obj.length, 6), "angle": round(obj.angle, 6), "zIndex": index,
                             "flipHorizontal": obj.flipHorizontal, "flipVertical": obj.flipVertical})
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Create Furnishing")
        dialog.setWindowIcon(HeaderIcon("Chair"))
        dialog.setMinimumWidth(400)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        description = QtWidgets.QLabel("Save this selection as a reusable furnishing.")
        layout.addWidget(description)
        form = QtWidgets.QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        nameField = QtWidgets.QLineEdit()
        nameField.setObjectName("furnishingName")
        nameField.setMaxLength(128)
        categoryField = DownwardComboBox()
        categoryField.setObjectName("furnishingCategory")
        categoryField.setEditable(True)
        categories = sorted({category for definition in self.viewport.furnishingDefinitions.values()
                             for category in definition.get("categories", [definition["category"]])},
                            key = lambda name: (name.casefold() in ("misc", "miscellaneous"), name.casefold()))
        categoryField.addItems(categories)
        selectedCategories = set.intersection(*(set(obj.definition.get("categories", [obj.definition["category"]])) for obj in furnishings))
        categoryField.setCurrentText(", ".join(sorted(selectedCategories)) if selectedCategories else "Miscellaneous")
        categoryField.setToolTip("Choose a category, or type multiple categories separated by commas")
        form.addRow("Name", nameField)
        form.addRow("Categories", categoryField)
        layout.addLayout(form)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Save |
                                             QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        saveButton = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Save)
        saveButton.setEnabled(False)
        nameField.textChanged.connect(lambda text: saveButton.setEnabled(bool(text.strip())))
        buttons.rejected.connect(dialog.reject)

        def Save():
            definition = self.SaveUserFurnishing(nameField.text(), categoryField.currentText(), children)
            if definition:
                v = self.viewport
                before = v.CaptureState()
                compound = Furnishing(definition, center)
                # Keep the compound at the frontmost source object's layer.
                lastSource = furnishings[-1]
                compound.behindCounters = lastSource.behindCounters
                v.furnishings = [compound if obj is lastSource else obj for obj in v.furnishings
                                  if id(obj) not in selectedIds or obj is lastSource]
                # Preserve a common group, but never put the compound into multiple groups.
                commonGroup = next((group for group in v.objectGroups
                                    if selectedIds.issubset({id(obj) for obj in group})), None)
                v.objectGroups = [tuple(obj for obj in group if id(obj) not in selectedIds) +
                                   ((compound,) if group is commonGroup else ()) for group in v.objectGroups]
                v.SetSelection([(compound, None)])
                v.RecordEdit(before)
                dialog.accept()
            else:
                nameField.setFocus()
                nameField.selectAll()

        buttons.accepted.connect(Save)
        layout.addWidget(buttons)
        nameField.setFocus()
        dialog.exec()

    def SaveUserFurnishing(self, name, category, children):
        name = unicodedata.normalize("NFKC", name).strip()
        try:
            categories = FurnishingCategories(category.split(",") if isinstance(category, str) else category)
        except ValueError as error:
            self.ShowAppMessage("Invalid Categories", str(error), "warning")
            return False
        if not name:
            self.ShowAppMessage("Name Required", "Please enter a name for the furnishing.", "warning")
            return False
        key = re.sub(r"[^\w-]+", "_", name.casefold()).strip("_")[:96] or "furnishing"
        if re.fullmatch(r"(?:con|prn|aux|nul|com[0-9]|lpt[0-9])", key):
            key = "user_" + key
        folder = Path(self.viewport.furnishingsFolder)
        # Display names can repeat. Each new definition gets its own file/key so
        # existing objects and compound references keep their original meaning.
        usedKeys = {definitionKey.casefold() for definitionKey in self.viewport.furnishingDefinitions}
        usedKeys.update(path.stem.casefold() for directory in ("definitions", "definitions_user")
                        for path in (folder / directory).glob("*.json"))
        baseKey, number = key, 2
        while key.casefold() in usedKeys:
            suffix = f"_{number}"
            key = baseKey[:96 - len(suffix)] + suffix
            number += 1
        path = folder / "definitions_user" / (key + ".json")
        definition = {"name": name, "category": categories[0] if len(categories) == 1 else categories, "children": children}
        from planner_app.project_codec import EncodeFurnishingDefinitions
        try:
            portable = EncodeFurnishingDefinitions([self.viewport.projectFurnishingDefinitions[child["furnishing"]]
                for child in children if child.get("furnishing") in self.viewport.projectFurnishingDefinitions], includeBuiltIns = True)
        except (OSError, ValueError, TypeError) as error:
            self.ShowAppMessage("Cannot Create Furnishing", "This selection cannot be saved as a furnishing.",
                                "warning", informativeText = str(error))
            return False
        if portable:
            definition["embeddedFurnishings"] = portable
        with warnings.catch_warnings(record = True) as messages:
            candidates = LoadFurnishings(folder, definitionOverrides = {key: definition})
        if not any(item["key"] == key for item in candidates):
            detail = next((str(message.message) for message in messages if f"furnishing {key}:" in str(message.message)),
                          "The selection contains an invalid furnishing reference.")
            self.ShowAppMessage("Cannot Create Furnishing", "This selection cannot be saved as a furnishing.",
                                "warning", informativeText = detail)
            return False
        try:
            path.parent.mkdir(parents = True, exist_ok = True)
            output = QtCore.QSaveFile(str(path))
            if not output.open(QtCore.QIODevice.OpenModeFlag.WriteOnly):
                raise OSError(output.errorString())
            payload = (json.dumps(definition, indent = 4, ensure_ascii = False, allow_nan = False) + "\n").encode("utf-8")
            if output.write(payload) != len(payload) or not output.commit():
                raise OSError(output.errorString())
        except (OSError, ValueError) as error:
            self.ShowAppMessage("Cannot Save Furnishing", "The furnishing definition could not be saved.",
                                "error", informativeText = str(error))
            return False
        v = self.viewport
        v.localFurnishingDefinitions = {item["key"]: item for item in candidates}
        v.projectFurnishingDefinitions.pop(key, None)
        v.furnishingDefinitions = {**v.localFurnishingDefinitions, **v.projectFurnishingDefinitions}
        self.RefreshFurnishingRenderers()
        for obj in v.furnishings:
            obj.definition = v.furnishingDefinitions.get(obj.definition["key"], v.furnishingDefinitions["null"])
        scrollPosition = self.furnishScrollArea.verticalScrollBar().value()
        self.BuildFurnishTab(refresh = True)
        self.furnishScrollArea.verticalScrollBar().setValue(scrollPosition)
        self.RefreshProperties()
        v.update()
        return v.furnishingDefinitions[key]
