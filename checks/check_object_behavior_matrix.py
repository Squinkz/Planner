"""Capture/replay per-type properties, context actions, handles and collision policy."""
import json
import os
import sys
from pathlib import Path

workspace = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(workspace / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtWidgets
from planner_app import models
from planner_app.geometry.collisions import AllowsCollision, ExcludesFootprintCollision
from planner_app.project_codec import EncodeScene
from planner_app.viewport.collision_types import CollisionFlags
from fixtures.parity_examples import ExampleWindow, CreateObject, InstallScene, CompareExamples, objectTypes, openingTypes, referenceDirectory


def CaptureMatrix():
    result = {"format": "Planner observed object behavior", "version": 1, "unitsMode": "Millimeters", "objects": []}
    with ExampleWindow() as (main, folder):
        v = main.viewport
        # This is a control/geometry probe; rendering has its own independent corpus.
        v.setUpdatesEnabled(False)
        v.unitsMode = "Millimeters"
        v.showMeasurements = True
        v.measurementVisibility = {key: True for key in v.measurementVisibility}
        v.measurementSettings = {key: 1 for key in v.measurementSettings}
        result["buildDefaultsCentimeters"] = {"wallWidths": list(v.wallPresetWidths),
            "openings": dict(v.openingDefaultSizes), "misc": dict(v.miscDefaultSizes)}
        for name in objectTypes:
            obj = CreateObject(v, name)
            InstallScene(main, [obj.parentWall, obj] if name in openingTypes else [obj])
            row = {"type": name, "seedScene": EncodeScene(v), "properties": {}}
            states = [("whole", None), ("firstVertex", 0), ("secondVertex", 1)]
            if isinstance(obj, models.AngleGuide):
                states.append(("middleVertex", 2))
            if isinstance(obj, models.MeasurementGuide):
                states.append(("label", 3))
            for state, vertex in states:
                # Vertex fields are observed only for objects whose UI exposes endpoint selection.
                if vertex is not None and (isinstance(obj, (models.Furnishing, models.Pillar, models.Fireplace))):
                    continue
                v.SetSelection([(obj, vertex)])
                QtWidgets.QApplication.processEvents()
                fields = {}
                mapping = {**{"property:" + key: value for key, value in main.propertyFields.items()},
                           **{"opening:" + key: value for key, value in main.doorFields.items()},
                           **{"well:" + key: value for key, value in main.windowWellFields.items()},
                           **{"arrow:" + key: value for key, value in main.arrowFields.items()},
                           **{"label:" + key: value for key, value in main.labelFields.items()},
                           **{"position:" + key: value for key, value in main.objectPositionFields.items()},
                           **{"labelPosition:" + key: value for key, value in main.labelPositionFields.items()},
                           **{"anglePosition:" + key: value for key, value in main.angleGuidePositionFields.items()},
                           "angle": main.angleGuideAngleField, "sizeLink": main.sizeLinkButton,
                           "material": main.materialField, "autosize": main.autosizeField,
                           "direction": main.stairDirectionButton, "arrowDirection": main.arrowDirectionButton,
                           "labelText": main.labelTextField,
                           "roomArea": main.roomAreaValue,
                           "lineWeight": main.lineWeightField,
                           "roomName": main.roomNameField,
                           "roomUnits": main.roomUnitsField,
                           "labelIntensity": main.labelIntensitySlider,
                           **{"flip:" + key: value for key, value in main.furnishingFlipFields.items()}}
                forms = main.propertiesPanel.findChildren(QtWidgets.QFormLayout)
                for key, widget in mapping.items():
                    if not widget.isVisibleTo(main.propertiesPanel):
                        continue
                    label = next((form.labelForField(widget) for form in forms if form.labelForField(widget) is not None), None)
                    entry = {"label": label.text() if isinstance(label, QtWidgets.QLabel) else widget.accessibleName(),
                             "enabled": widget.isEnabled(), "tooltip": widget.toolTip(), "widget": type(widget).__name__}
                    if isinstance(widget, QtWidgets.QAbstractSpinBox):
                        entry.update(value = widget.value(), minimum = widget.minimum(), maximum = widget.maximum(),
                                     decimals = widget.decimals(), singleStep = widget.singleStep(), suffix = widget.suffix(),
                                     readOnly = widget.isReadOnly(), keyboardTracking = widget.keyboardTracking())
                    elif isinstance(widget, QtWidgets.QComboBox):
                        entry.update(value = widget.currentText(), options = [widget.itemText(i) for i in range(widget.count())])
                    elif isinstance(widget, QtWidgets.QAbstractButton):
                        entry.update(checked = widget.isChecked())
                    elif isinstance(widget, QtWidgets.QSlider):
                        entry.update(value = widget.value(), minimum = widget.minimum(), maximum = widget.maximum())
                    elif isinstance(widget, QtWidgets.QPlainTextEdit):
                        entry.update(value = widget.toPlainText())
                    elif isinstance(widget, QtWidgets.QLineEdit):
                        entry.update(value = widget.text(), maxLength = widget.maxLength())
                    elif isinstance(widget, QtWidgets.QLabel):
                        entry.update(value = widget.text())
                    fields[key] = entry
                row["properties"][state] = fields
            v.SetSelection([(obj, None)])
            if isinstance(obj, (models.Furnishing, models.Pillar, models.Fireplace)):
                handles = v.FurnishingHandles(obj)
                row["handles"] = {kind: sum(h[0] == kind for h in handles) for kind in ("resize", "rotate", "pivot")}
            else:
                row["handles"] = {"endpoints": len(models.ObjectControlPoints(obj))}
            visibility = []
            for key in v.visibility:
                if key == "World":
                    continue
                previous = v.visibility[key]
                v.visibility[key] = False
                if not v.IsObjectVisible(obj):
                    visibility.append(key)
                v.visibility[key] = previous
            row["visibilityKeys"] = visibility
            center = (obj.firstVertex + obj.secondVertex) / 2
            if isinstance(obj, models.Fireplace):
                direction, normal = obj.Axes()
                center += normal * (obj.depthOffset + obj.depth * .3)
            position = v.AngleLayout(obj, selected = True)[1].center() if isinstance(obj, models.AngleGuide) else v.WorldToViewport(center)
            assert v.HitTest(position)[0] is obj, (name, "context seed did not hit object")
            row["context"] = {}
            for enabled in (True, False):
                v.showMeasurements = enabled
                v.ShowObjectContextMenu(position, v.mapToGlobal(position.toPoint()))
                row["context"]["measurementsOn" if enabled else "measurementsOff"] = [
                    None if action.isSeparator() else action.defaultWidget().accessibleName() for action in v.objectContextMenu.actions()]
                v.objectContextMenu.hide()
            v.showMeasurements = True
            if isinstance(obj, (models.Stair, models.Railing)):
                obj.SetAutosize(False)
                main.RefreshProperties()
                row["manualSizing"] = {key: {"visible": control.isVisibleTo(main.propertiesPanel), "value": control.value()}
                                       for key, control in main.propertyFields.items() if key in ("stepCount", "stepSize")}
            result["objects"].append(row)
        result["collisionPolicy"] = {}
        flags = [CollisionFlags(getattr(models, name)) for name in objectTypes]
        for profile in range(8):
            settings = dict(walls = bool(profile & 1), architectural = bool(profile & 2), furnishings = bool(profile & 4))
            result["collisionPolicy"][str(profile)] = {"settings": settings,
                "enabledRows": [[AllowsCollision(a, b, settings) for b in flags] for a in flags]}
        result["footprintExclusionRows"] = [[ExcludesFootprintCollision(a, b) for b in flags] for a in flags]
    return result


def Main():
    modelTypes = {name for name, cls in vars(models).items() if isinstance(cls, type)
                  and cls.__module__ == models.__name__ and issubclass(cls, models.SceneObject)}
    assert set(objectTypes) == modelTypes, ("Object matrix inventory is stale", modelTypes ^ set(objectTypes))
    actual = CaptureMatrix()
    target = referenceDirectory / "object-behavior.json"
    if "--record" in sys.argv:
        target.write_text(json.dumps(actual, indent = 2, ensure_ascii = False), encoding = "utf-8", newline = "\n")
        print(f"Recorded {len(actual['objects'])} object types")
    else:
        expected = json.loads(target.read_text(encoding = "utf-8"))
        CompareExamples(actual, expected)
        assert len(actual["objects"]) == len(objectTypes)
        print(f"PASS: {len(objectTypes)} object types, properties/menus/handles/visibility and all 8 collision-setting profiles")


if __name__ == "__main__":
    Main()
