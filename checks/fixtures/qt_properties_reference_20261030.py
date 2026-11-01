"""Frozen synchronous property refresh and scene metadata maintenance."""
from planner_app.ui.properties import *
from planner_app.viewport.scene import *
from planner_app.scene_changes import *


class ReferenceProperties:
    def RefreshProperties(self):
        if self.bulkPropertyEdit:
            return
        if self.referenceImage.active:
            self.referenceImage.SyncProperties()
            return
        self.selectionLabel.show()
        # Keep all property signals blocked until refresh returns. Intermediate
        # ranges/suffixes use metric units and must never edit the selected object.
        propertyBlockers = [QtCore.QSignalBlocker(field) for field in self.propertyFields.values()]
        entries = self.viewport.SelectionEntries()
        sizeSelection = frozenset(id(obj) for obj, index in entries)
        if sizeSelection != self.sizeLinkSelection:
            self.sizeLinkSelection = sizeSelection
            self.sizeLinkButton.setChecked(all(isinstance(obj, (Furnishing, Pillar, Fireplace)) for obj, index in entries))
        self.viewport.EnsureObjectIds()
        labelSelection = bool(entries) and all(isinstance(obj, Label) for obj, index in entries)
        northSelection = bool(entries) and all(isinstance(obj, NorthArrow) for obj, index in entries)
        self.northArrowOpacityRow.setVisible(northSelection)
        if northSelection:
            arrows = [obj for obj, index in entries]
            blocker = QtCore.QSignalBlocker(self.northArrowIntensitySlider)
            self.northArrowIntensitySlider.setValue(round(arrows[0].intensity * 100))
            self.northArrowIntensityValue.setText(f"{arrows[0].intensity:.2f}" if all(obj.intensity == arrows[0].intensity for obj in arrows) else "(different)")
            del blocker
        self.labelProperties.setVisible(labelSelection)
        if self.RefreshAngleProperties(entries):
            return
        if self.RefreshArrowProperties(entries):
            return
        if labelSelection:
            self.wallProperties.hide()
            self.doorProperties.hide()
            self.vertexProperties.hide()
            self.vertexSpacing.hide()
            self.labelProperties.show()
            labels = list({id(obj): obj for obj, index in entries}.values())
            self.RefreshPositionFields(self.labelPositionFields, labels)
            for name, control in self.labelFields.items():
                values = [getattr(label, name) for label in labels]
                divisor, unit = (1, "pt") if name == "pointSize" else PropertyUnit(name, labels[0], self.viewport.unitsMode)
                blocker = QtCore.QSignalBlocker(control)
                mixed = not all(math.isclose(value, values[0], abs_tol = 1e-6) for value in values)
                control.setDecimals(0 if unit == "mm" else 3)
                control.setRange(.001 / divisor, 1e9 / divisor)
                control.setSingleStep(1 if name == "pointSize" else 10 / divisor)
                control.mixedValue = mixed
                control.mixedEdited = False
                control.commonSuffix = " " + unit
                control.setSuffix("" if mixed else control.commonSuffix)
                control.setValue(values[0] / divisor)
                control.lineEdit().setPlaceholderText("(different)" if mixed else "")
                if mixed:
                    control.lineEdit().clear()
                del blocker
            rooms = all(isinstance(label, RoomLabel) for label in labels)
            form = self.labelProperties.layout()
            form.setRowVisible(self.labelTextField, not rooms)
            form.setRowVisible(self.roomNameField, rooms)
            form.setRowVisible(self.roomAreaValue, rooms)
            form.setRowVisible(self.roomUnitsField, rooms)
            if rooms:
                blocker = QtCore.QSignalBlocker(self.roomUnitsField)
                modes = [label.unitsOverride for label in labels]
                self.roomUnitsField.setCurrentIndex(self.roomUnitsField.findData(modes[0]) if all(mode == modes[0] for mode in modes) else -1)
                self.roomUnitsField.setPlaceholderText("(different)")
                del blocker
                self.viewport.roomDetection.UpdateLabels(force = True)
                areas = [FormatArea(label.areaSquareMillimeters, label.areaUnitsMode) for label in labels]
                self.roomAreaValue.setText(areas[0] if len(set(areas)) == 1 else "(different)")
            title = "Room Label" if rooms else "Label"
            self.selectionLabel.setText(f"{title} (#{labels[0].objectId:04d})" if len(labels) == 1 else f"{len(labels)} {title}s selected")
            text = labels[0].text if all(obj.text == labels[0].text for obj in labels) else ""
            blocker = QtCore.QSignalBlocker(self.roomNameField)
            name = text if rooms else ""
            if self.roomNameField.text() != name:
                self.roomNameField.setText(name)
            self.roomNameField.setPlaceholderText("(different)" if any(obj.text != labels[0].text for obj in labels) else "")
            del blocker
            blocker = QtCore.QSignalBlocker(self.labelTextField)
            if self.labelTextField.toPlainText() != text:
                self.labelTextField.setPlainText(text)
            self.labelTextField.setPlaceholderText("(different)" if any(obj.text != labels[0].text for obj in labels) else "")
            del blocker
            blocker = QtCore.QSignalBlocker(self.labelIntensitySlider)
            self.labelIntensitySlider.setValue(round(labels[0].intensity * 100))
            self.labelIntensityValue.setText(f"{labels[0].intensity:.2f}" if all(obj.intensity == labels[0].intensity for obj in labels) else "(different)")
            del blocker
            return
        for spinBox in self.propertyFields.values():
            if spinBox.mixedValue:
                blocker = QtCore.QSignalBlocker(spinBox)
                spinBox.mixedValue = False
                spinBox.setSuffix(spinBox.commonSuffix)
                del blocker
        wall = self.viewport.selectedWall
        for fieldName, field in self.propertyFields.items():
            if fieldName in ("angle", "miter", "stepCount"):
                continue
            blocker = QtCore.QSignalBlocker(field)
            field.setRange(.01 if fieldName == "stepSize" else .1 if fieldName == "wellDepth" else 0 if fieldName == "sillDepth" else .1 if fieldName == "width" else .001 if fieldName in ("length", "doorSize") else -1e9, 100000 if fieldName == "stepSize" else 1e9)
            # These metric values are staging values for the final unit conversion.
            # Rounding them to display precision loses exact imperial grid lengths.
            field.setDecimals(9 if self.viewport.unitsMode in imperialModes else 2 if fieldName == "stepSize" else 3)
            field.setSingleStep(1 if fieldName in ("width", "sillDepth", "wellDepth", "stepSize") else .1)
            field.setSuffix(" " + PropertyUnit(fieldName, wall, "Adaptive Metric")[1] if fieldName not in ("x", "y") else "")
            del blocker
        entries = self.viewport.SelectionEntries()
        if len({Wall if type(obj) in (Wall, Pillar, Column) else type(obj) for obj, index in entries}) > 1:
            objects = len({id(obj) for obj, index in entries})
            self.selectionLabel.setText(f"Multiple types ({objects} objects)")
            self.wallProperties.hide()
            self.doorProperties.hide()
            self.vertexProperties.hide()
            self.vertexSpacing.hide()
            return
        vertexIndex = self.viewport.selectedVertex
        if len({type(obj) for obj, index in entries}) > 1 and all(type(obj) in (Wall, Pillar, Column) for obj, index in entries):
            wall = next(obj for obj, index in entries if type(obj) is Wall)
        isWindow = isinstance(wall, Window)
        isDoor = isinstance(wall, Door)
        isSilledWindow = isinstance(wall, SilledWindow)
        isSlidingDoor = isinstance(wall, SlidingDoor)
        isPocketDoor = isinstance(wall, PocketDoor)
        isBarnDoor = isinstance(wall, BarnDoor)
        isBifoldDoor = isinstance(wall, BifoldDoor)
        isStair = isinstance(wall, Stair)
        isRailing = isinstance(wall, Railing)
        hasSizing = isStair or isRailing
        isFurnishing = isinstance(wall, Furnishing)
        isPillar = isinstance(wall, Pillar)
        self.wallProperties.layout().setRowVisible(self.objectPositionRow, isFurnishing or isPillar)
        if isFurnishing or isPillar:
            self.RefreshPositionFields(self.objectPositionFields, list({id(obj): obj for obj, index in entries}.values()) or [wall])
        self.viewport.EnsureObjectIds()
        self.doorProperties.setVisible(isWindow and not isinstance(wall, OpenDoorway))
        self.doorProperties.layout().setRowVisible(self.doorFields["swing"], isDoor or isinstance(wall, DoubleDoor) or isSlidingDoor or isBarnDoor or isBifoldDoor or type(wall) in (Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, Fireplace))
        self.doorProperties.layout().setRowVisible(self.doorFields["hinge"], isDoor or isSlidingDoor or isPocketDoor or isinstance(wall, (CasementWindow, SwingingDoor)))
        self.doorProperties.layout().setRowVisible(self.doorFields["measurement"],
            isWindow and any(AvailableDimensionActions(self.viewport, obj).canFlip for obj, index in entries))
        sideLabel = self.doorProperties.layout().labelForField(self.doorFields["swing"])
        sideLabel.setText("Facing" if isBarnDoor or type(wall) in (Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow, Fireplace) else "Panel side" if isSlidingDoor else "Swing direction")
        sideLabel.setMinimumWidth(sideLabel.sizeHint().width())
        self.doorFields["swing"].setToolTip("Flip the panel to the other side of its wall" if isBarnDoor else "Flip the window to the other side of its wall" if type(wall) in (Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow) else
                                          "Mirror the panels across the wall" if isSlidingDoor else
                                          "Flip the door to the other side of its wall")
        hingeLabel = self.doorProperties.layout().labelForField(self.doorFields["hinge"])
        hingeLabel.setText("Slide direction" if isBarnDoor else "Pocket side" if isPocketDoor else "Slide direction" if isSlidingDoor else "Hinge side")
        hingeLabel.setMinimumWidth(hingeLabel.sizeHint().width())
        self.doorFields["hinge"].setToolTip("Swap the opening and parking sides" if isBarnDoor else "Swap the opening and pocket sides" if isPocketDoor else
                                          "Reverse the sliding direction" if isSlidingDoor else "Move the hinge to the opposite endpoint")
        self.wallProperties.layout().setRowVisible(self.propertyFields["sillDepth"], isSilledWindow)
        hasWell = type(wall) in (Window, SilledWindow, CasementWindow, AwningWindow, DoubleCasementWindow)
        for name, checkbox in self.windowWellFields.items():
            self.wallProperties.layout().setRowVisible(self.windowWellRows[name], hasWell and (name == "windowWell" or wall.windowWell))
            if hasWell:
                states = {getattr(obj, name) for obj, index in entries}
                blocker = QtCore.QSignalBlocker(checkbox)
                checkbox.setTristate(len(states) > 1)
                checkbox.setCheckState(QtCore.Qt.CheckState.PartiallyChecked if len(states) > 1 else
                                       QtCore.Qt.CheckState.Checked if getattr(wall, name) else QtCore.Qt.CheckState.Unchecked)
                del blocker
        self.wallProperties.layout().setRowVisible(self.propertyFields["wellDepth"], hasWell and wall.windowWell)
        self.wallProperties.layout().setRowVisible(self.propertyFields["angle"], isFurnishing or isPillar)
        for button in self.furnishingFlipFields.values():
            self.wallProperties.layout().setRowVisible(button, type(wall) is Furnishing)
        self.wallProperties.layout().setRowVisible(self.propertyFields["doorSize"], isSlidingDoor or isPocketDoor)
        pairedSize = not isWindow or isinstance(wall, Fireplace)
        lengthContainer = self.sizeRow if pairedSize else self.openingLengthRow
        if self.propertyFields["length"].parentWidget() is not lengthContainer:
            self.propertyFields["length"].parentWidget().layout().removeWidget(self.propertyFields["length"])
            lengthContainer.layout().addWidget(self.propertyFields["length"], 1)
            self.propertyFields["length"].show()
            QtWidgets.QWidget.setTabOrder(self.propertyFields["width"], self.propertyFields["length"])
            QtWidgets.QWidget.setTabOrder(self.propertyFields["length"], self.propertyFields["doorSize"])
        self.wallProperties.layout().setRowVisible(self.sizeRow, pairedSize)
        self.wallProperties.layout().setRowVisible(self.openingLengthRow, not pairedSize and not isPocketDoor)
        self.wallProperties.layout().setRowVisible(self.materialField, isinstance(wall, Fireplace) or not isWindow and not hasSizing and not isFurnishing and not isinstance(wall, (Counter, Elevator)))
        self.wallProperties.layout().setRowVisible(self.autosizeField, hasSizing)
        for container in self.stairStepWidgets.values():
            self.wallProperties.layout().setRowVisible(container, hasSizing)
        self.wallProperties.layout().setRowVisible(self.stairDirectionButton, isStair)
        if isStair:
            self.stairDirectionButton.setIcon(HeaderIcon("Undo" if wall.directionReversed else "Redo"))
        self.propertyFields["width"].setSuffix(" m" if isStair else " cm")
        self.propertyFields["length"].setSuffix(" cm" if isFurnishing else " m")
        self.propertyFields["length"].setSingleStep(1.0 if isFurnishing else .1)
        self.propertyFields["width"].setRange(.001 if isStair else .1, 1e9)
        self.propertyFields["width"].setSingleStep(.1 if isStair else 1)
        if isinstance(wall, (Wall, Fireplace)):
            blocker = QtCore.QSignalBlocker(self.materialField)
            self.materialField.setCurrentText(wall.material)
            del blocker
        self.propertyFields["width"].setReadOnly(isWindow and not isinstance(wall, Fireplace))
        self.propertyFields["width"].setToolTip("Matches the wall thickness" if isWindow else
                                               "Width. Drag left or right to adjust. Hold Alt for finer control. Click to type a value.")
        self.propertyFields["length"].setToolTip("Length. Drag left or right to adjust. Hold Alt for finer control. Click to type a value.")
        vertices = [(obj, index) for obj, index in entries if index is not None]
        showChamfer = bool(vertices)
        checkedJoints = set()
        for obj, index in vertices:
            if type(obj) not in (Wall, Counter, Stair):
                showChamfer = False
                break
            position = obj.firstVertex if index == 0 else obj.secondVertex
            key = (type(obj), position.x(), position.y())
            if key in checkedJoints:
                continue
            checkedJoints.add(key)
            rays = []
            for other in self.viewport.walls:
                if type(other) is not type(obj):
                    continue
                for endpoint, far in ((other.firstVertex, other.secondVertex), (other.secondVertex, other.firstVertex)):
                    if QtCore.QLineF(position, endpoint).length() > .01:
                        continue
                    delta = far - endpoint
                    length = math.hypot(delta.x(), delta.y())
                    if length > 1e-10:
                        rays.append(((delta.x() / length, delta.y() / length), other.width / 2, len(rays)))
            if len(rays) != 2:
                showChamfer = False
                break
            # Ask the numeric builder whether a moving cut actually exists.
            # Straight/duplicate rays and guarded local transitions have none;
            # fixed unequal-width cap planes alone do not enable the control.
            planes = BuildWallJunction((0, 0), rays, [1, 1], 0)[4]
            if not planes[0] or not planes[1] or planes[0][-1] != planes[1][-1]:
                showChamfer = False
                break
        self.vertexProperties.layout().setRowVisible(self.propertyFields["miter"], showChamfer)
        self.wallProperties.setVisible(wall is not None)
        self.vertexProperties.setVisible(wall is not None and vertexIndex is not None)
        self.vertexSpacing.setVisible(wall is not None and vertexIndex is not None)
        if wall is None:
            self.selectionLabel.setText("No selection")
            return
        objectType = "Elevator" if isinstance(wall, Elevator) else wall.definition["name"] if isFurnishing else "Fireplace" if isinstance(wall, Fireplace) else "Column" if isinstance(wall, Column) else "Pillar" if isPillar else "Railing" if isRailing else "Stair" if isStair else "Bifold Door" if isBifoldDoor else "Barn Door" if isBarnDoor else "Pocket Door" if isPocketDoor else "Sliding Door" if isSlidingDoor else "Double Door" if isinstance(wall, DoubleDoor) else "Swinging Door" if isinstance(wall, SwingingDoor) else "Standard Door" if isDoor else "Silled Window" if isSilledWindow else "Double Casement Window" if isinstance(wall, DoubleCasementWindow) else "Awning Window" if isinstance(wall, AwningWindow) else "Casement Window" if isinstance(wall, CasementWindow) else "Open Doorway" if isinstance(wall, OpenDoorway) else "Standard Window" if isWindow else "Counter" if isinstance(wall, Counter) else "Wall"
        furnishingNames = {}
        missingFurnishings = set()
        if isFurnishing:
            for obj in [wall] + [obj for obj, index in entries if obj is not wall]:
                key = getattr(obj, "definitionKey", obj.definition["key"])
                problems = FurnishingAssetProblems(key, self.viewport.furnishingDefinitions, obj.definition) if type(obj) is Furnishing else {}
                missing = bool(problems)
                status = "missing" if problems.get(key) == "missing" else "asset error"
                furnishingNames[id(obj)] = f"{key} ({status})" if missing else obj.definition["name"]
                if missing:
                    missingFurnishings.add(id(obj))
            objectType = furnishingNames[id(wall)]
        self.selectionLabel.setText(f"{objectType} (#{wall.objectId:04d})")
        values = {"width": wall.width, "length": QtCore.QLineF(wall.firstVertex, wall.secondVertex).length()}
        if isinstance(wall, Fireplace):
            self.propertyFields["width"].setToolTip("Width: size through the wall. Drag to adjust or click to type.")
            self.propertyFields["length"].setToolTip("Length: size along the wall. Drag to adjust or click to type.")
            values["width"] = wall.depth
        if isFurnishing or isPillar:
            values["angle"] = wall.angle
        if isSilledWindow:
            values["sillDepth"] = wall.sillDepth
        if hasWell:
            values["wellDepth"] = wall.wellDepth
        if isSlidingDoor or isPocketDoor:
            values["doorSize"] = wall.length / 2
        if hasSizing:
            self.stepCountLabel.setToolTip("Includes posts at both endpoints" if isRailing else "Includes calculated treads and one step for each landing")
            for fieldName, text in (("stepCount", "Post Count" if isRailing else "Step count"), ("stepSize", "Segment Width" if isRailing else "Tread depth")):
                self.wallProperties.layout().labelForField(self.stairStepWidgets[fieldName]).setText(text)
            countBlocker = QtCore.QSignalBlocker(self.propertyFields["stepCount"])
            self.propertyFields["stepCount"].setRange(2 if isRailing else 1, sizingCountLimit)
            del countBlocker
            limits = self.viewport.AutoSizingLimits("railings" if isRailing else "stairs")
            minimumText = FormatLength(limits["minimum"], self.viewport.unitsMode, "cm")
            maximumText = FormatLength(limits["maximum"], self.viewport.unitsMode, "cm")
            self.stepSizeLabel.setToolTip(f"Targets {'spacing' if isRailing else 'tread depth'} between {minimumText} and {maximumText}")
            stairs = list({id(obj): obj for obj, index in entries}.values())
            modes = {obj.autosize for obj in stairs}
            blocker = QtCore.QSignalBlocker(self.autosizeField)
            self.autosizeField.setTristate(len(modes) > 1)
            self.autosizeField.setCheckState(QtCore.Qt.CheckState.PartiallyChecked if len(modes) > 1 else
                                            QtCore.Qt.CheckState.Checked if wall.autosize else QtCore.Qt.CheckState.Unchecked)
            del blocker
            for container in self.stairStepWidgets.values():
                container.setCurrentIndex(1 if modes == {False} else 0)
            self.stepCountLabel.setText(str((wall.postCount if isRailing else wall.stepCount)))
            self.stepSizeLabel.setText(f"{(wall.segmentWidth if isRailing else wall.stepSize) / 10:.2f} cm")
            values.update(stepCount = (wall.postCount if isRailing else wall.stepCount), stepSize = (wall.segmentWidth if isRailing else wall.stepSize))
            self.propertyFields["stepCount"].setSuffix("")
            self.propertyFields["stepSize"].setSuffix(" cm")
        if vertexIndex is not None:
            self.vertexProperties.setTitle(f"Point {vertexIndex + 1}")
            vertex = wall.firstVertex if vertexIndex == 0 else wall.secondVertex
            values.update({"x": vertex.x(), "y": vertex.y()})
            if not isWindow:
                values["miter"] = wall.firstMiter if vertexIndex == 0 else wall.secondMiter
        for fieldName, value in values.items():
            spinBox = self.propertyFields[fieldName]
            blocker = QtCore.QSignalBlocker(spinBox)
            if fieldName == "width" and isinstance(wall, Fireplace):
                spinBox.setMinimum(wall.parentWall.width / 10)
            if fieldName in ("length", "doorSize"):
                maximum = self.viewport.OpeningLengthLimit(wall) / 1000 if isWindow else 1e9
                minimum = 0.001 if isWindow else max(0.001, self.viewport.MinimumOpeningLength(wall) / 1000)
                if isFurnishing:
                    minimum = .1
                if isinstance(wall, Fireplace):
                    minimum, maximum = .001, QtCore.QLineF(wall.parentWall.firstVertex, wall.parentWall.secondVertex).length() / 1000
                if fieldName == "doorSize":
                    minimum /= 2
                    maximum /= 2
                spinBox.setRange(minimum, max(minimum, maximum))
            spinBox.setValue(value / (1.0 if fieldName in ("miter", "stepCount", "angle") else 10.0 if fieldName in ("sillDepth", "wellDepth", "stepSize") or fieldName == "width" and not isStair or fieldName == "length" and isFurnishing else 1000.0))
            del blocker
        if len(entries) > 1:
            objects = list({id(obj): obj for obj, index in entries}.values())
            if isFurnishing and len({furnishingNames[id(obj)] for obj in objects}) > 1:
                objectType = "Furnishing"
            self.selectionLabel.setText(f"{len(objects)} {objectType}s selected" if len(objects) > 1 else
                                        f"{objectType} (#{objects[0].objectId:04d})")
            if len(objects) > 1 and isFurnishing and len({furnishingNames[id(obj)] for obj in objects}) == 1 and missingFurnishings:
                self.selectionLabel.setText(f"{len(objects)} {objectType} objects selected")
            vertices = [(obj, index) for obj, index in entries if index is not None]
            self.vertexProperties.setVisible(bool(vertices))
            self.vertexSpacing.setVisible(bool(vertices))
            if vertices:
                self.vertexProperties.setTitle(f"Selected points ({len(vertices)})")
            for fieldName, spinBox in self.propertyFields.items():
                propertyValues = []
                if fieldName in ("x", "y", "miter"):
                    for obj, index in vertices:
                        if fieldName == "miter" and not hasattr(obj, "firstMiter"):
                            continue
                        vertex = obj.firstVertex if index == 0 else obj.secondVertex
                        propertyValues.append(vertex.x() / 1000 if fieldName == "x" else vertex.y() / 1000 if fieldName == "y" else
                                              obj.firstMiter if index == 0 else obj.secondMiter)
                elif fieldName == "angle" and (isFurnishing or isPillar):
                    propertyValues = [obj.angle for obj in objects]
                elif fieldName == "sillDepth" and isSilledWindow:
                    propertyValues = [obj.sillDepth / 10 for obj in objects]
                elif fieldName == "wellDepth" and hasWell:
                    propertyValues = [obj.wellDepth / 10 for obj in objects]
                elif fieldName in ("stepCount", "stepSize") and hasSizing:
                    propertyValues = [(obj.postCount if isinstance(obj, Railing) else obj.stepCount) if fieldName == "stepCount" else (obj.segmentWidth if isinstance(obj, Railing) else obj.stepSize) / 10 for obj in objects]
                elif fieldName in ("width", "length", "doorSize"):
                    for obj in objects:
                        propertyValues.append((obj.depth / 10 if fieldName == "width" else obj.length / 1000) if isinstance(obj, Fireplace) else
                                              obj.width / (1000 if isStair else 10) if fieldName == "width" else
                                              obj.length / 2000 if fieldName == "doorSize" and isinstance(obj, Window) else
                                              QtCore.QLineF(obj.firstVertex, obj.secondVertex).length() / (10 if isFurnishing else 1000))
                if propertyValues:
                    blocker = QtCore.QSignalBlocker(spinBox)
                    if fieldName == "width" and isinstance(wall, Fireplace):
                        spinBox.setMinimum(max(obj.parentWall.width for obj in objects) / 10)
                    if fieldName in ("length", "doorSize"):
                        minimum = max(.001, max((self.viewport.MinimumOpeningLength(obj) / 1000 for obj in objects), default = .001)) if not isWindow else .001
                        maximum = min((self.viewport.OpeningLengthLimit(obj) / 1000
                                       for obj in objects), default = 1e9) if isWindow else 1e9
                        if isFurnishing:
                            minimum = .1
                        if isinstance(wall, Fireplace):
                            minimum, maximum = .001, min(QtCore.QLineF(obj.parentWall.firstVertex, obj.parentWall.secondVertex).length() for obj in objects) / 1000
                        if fieldName == "doorSize":
                            minimum /= 2
                            maximum /= 2
                        spinBox.setRange(minimum, max(minimum, maximum))
                    common = all(math.isclose(value, propertyValues[0], abs_tol = 1e-6) for value in propertyValues)
                    spinBox.commonSuffix = spinBox.suffix()
                    spinBox.mixedEdited = False
                    spinBox.mixedValue = not common
                    if not common:
                        # A suffix keeps the editor nonempty and hides its placeholder.
                        spinBox.setSuffix("")
                    spinBox.setValue(propertyValues[0])
                    spinBox.lineEdit().setPlaceholderText("(different)" if not common else "")
                    if not common:
                        spinBox.lineEdit().clear()
                    del blocker
            if isinstance(wall, Fireplace) or not isWindow and not isStair and not isFurnishing:
                blocker = QtCore.QSignalBlocker(self.materialField)
                materials = {obj.material for obj in objects}
                self.materialField.setPlaceholderText("(different)")
                self.materialField.setCurrentIndex(self.materialField.findText(next(iter(materials))) if len(materials) == 1 else -1)
                del blocker
            if hasSizing:
                counts = {(obj.postCount if isinstance(obj, Railing) else obj.stepCount) for obj in objects}
                sizes = {round((obj.segmentWidth if isinstance(obj, Railing) else obj.stepSize) / 10, 2) for obj in objects}
                self.stepCountLabel.setText(str(next(iter(counts))) if len(counts) == 1 else "(different)")
                self.stepSizeLabel.setText(f"{next(iter(sizes)):.2f} cm" if len(sizes) == 1 else "(different)")
        else:
            for spinBox in self.propertyFields.values():
                spinBox.mixedValue = False
                spinBox.lineEdit().setPlaceholderText("")
        if self.viewport.unitsMode != "Adaptive Metric":
            for fieldName, field in self.propertyFields.items():
                if fieldName in ("angle", "miter", "stepCount"):
                    continue
                oldDivisor, unused = PropertyUnit(fieldName, wall, "Adaptive Metric")
                divisor, unit = PropertyUnit(fieldName, wall, self.viewport.unitsMode)
                factor = oldDivisor / divisor
                value, minimum, maximum, step = field.value(), field.minimum(), field.maximum(), field.singleStep()
                blocker = QtCore.QSignalBlocker(field)
                if unit == "mm":
                    field.setDecimals(0)
                elif fieldName == "stepSize" and unit == "m":
                    field.setDecimals(4)
                field.setRange(minimum * factor, maximum * factor)
                field.setSingleStep(step * factor)
                field.commonSuffix = " " + unit
                field.setSuffix("" if field.mixedValue else field.commonSuffix)
                field.setValue(value * factor)
                if field.mixedValue:
                    field.lineEdit().clear()
                del blocker
            if hasSizing:
                sizes = {round((obj.segmentWidth if isinstance(obj, Railing) else obj.stepSize), 6) for obj, index in entries}
                self.stepSizeLabel.setText(FormatLength(next(iter(sizes)), self.viewport.unitsMode, "cm", 4) if len(sizes) == 1 else "(different)")
        # These are separate forms, but their fields form one visual column.
        visibleLabels = []
        for panel in (self.wallProperties, self.doorProperties):
            form = panel.layout()
            for row in range(form.rowCount()):
                item = form.itemAt(row, QtWidgets.QFormLayout.ItemRole.LabelRole)
                label = item.widget() if item is not None else None
                if label is not None:
                    label.setMinimumWidth(0)
                    if not panel.isHidden() and form.isRowVisible(row):
                        visibleLabels.append(label)
        columnWidth = max((label.sizeHint().width() for label in visibleLabels), default = 0)
        for label in visibleLabels:
            label.setMinimumWidth(columnWidth)


class ReferenceScene:
    def EnsureObjectIds(self, capturedState = None):
        # Committed objects, including deletions, need IDs. Placement previews do not.
        objects = self.walls + self.windows + self.furnishings + self.labels
        if capturedState is not None:
            objects = objects + [entry[0] for category in (0, 3, 5, 8) for entry in capturedState[category]]
        pending = {id(obj): obj for obj in objects if obj.objectId is None}
        if pending:
            usedIds = {obj.objectId for obj in objects if obj.objectId is not None}
            # Loaded IDs can be ahead of the process counter. Retired objects
            # must keep their IDs reserved until they leave both history stacks.
            usedIds.update(entry[0].objectId for edit in self.undoHistory + self.redoHistory
                           for change in edit.changes for entry in change[3:] if entry is not None)
            for drawingObject in pending.values():
                objectId = next(objectIdCounter)
                while objectId in usedIds:
                    objectId = next(objectIdCounter)
                drawingObject.objectId = objectId
                usedIds.add(objectId)
        stairs = [wall for wall in self.walls if isinstance(wall, Stair)]
        stepLimits, railingLimits = self.AutoSizingLimits("stairs"), self.AutoSizingLimits("railings")
        for drawingObject in self.walls + self.windows + self.furnishings + self.labels:
            if isinstance(drawingObject, Stair):
                drawingObject.sceneStairs = stairs
                drawingObject.stepSizeBounds = (stepLimits["minimum"], stepLimits["maximum"])
            if isinstance(drawingObject, Railing):
                drawingObject.spacingBounds = tuple(railingLimits[key] for key in ("minimum", "maximum", "target"))


class ReferenceSceneObject:
    def __setattr__(self, name, value):
        old = self.__dict__.get(name)
        pointField = name in ("firstVertex", "secondVertex", "middleVertex", "textOffset")
        if pointField:
            value = ScenePoint(value, self)
        elif name in ("stepSizeBounds", "spacingBounds"):
            value = tuple(value)
        object.__setattr__(self, name, value)
        guideDepth = name == "depth" and type(self).__name__ == "MeasurementGuide"
        if name not in geometryFields and name not in appearanceFields and not guideDepth:
            return
        if pointField:
            # QPointF equality is fuzzy at large coordinates. Revision-keyed
            # geometry must observe every representable coordinate change.
            changed = old is None or old.x() != value.x() or old.y() != value.y()
        else:
            changed = old is not value if name in ("parentWall", "definition") else old != value
        if name == "definition" and changed:
            for observer in self.__dict__.get("_renderObservers", ()):
                observer.Watch(self)
        if (name in geometryFields or guideDepth) and changed:
            if name == "parentWall":
                for observer in self.__dict__.get("_renderObservers", ()):
                    observer.Watch(value)
            self.NotifyRender("geometry")
        elif name in appearanceFields and changed:
            self.NotifyRender("appearance")

