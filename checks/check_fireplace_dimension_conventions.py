"""Fireplace UI axes match walls while legacy span/depth records stay unchanged."""
import json
import math
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Fireplace
from planner_app.project_codec import EncodeScene
from planner_app.graphics.fireplace import FireplacePath
from planner_app.units import PropertyUnit, unitModes


def Main():
    with ExampleWindow() as (main, folder):
        v, point = main.viewport, QtCore.QPointF
        v.snapEnabled = False
        for angle in (0, 37, 90, 180, 270):
            transform = QtGui.QTransform().rotate(angle)
            parent = Wall(transform.map(point(-3000, 0)), transform.map(point(3000, 0)), 240)
            fireplace = Fireplace(parent, .4, .6)
            fireplace.depth, fireplace.depthOffset = 500, 80
            InstallScene(main, [parent, fireplace])
            v.SetSelection([(fireplace, None)])
            main.sizeLinkButton.setChecked(False)  # Axis-convention checks edit each dimension independently.
            before = EncodeScene(v)
            path = FireplacePath(fireplace)
            box = fireplace.HandleBox()
            direction, normal = fireplace.Axes()
            assert math.isclose(box.length, fireplace.length) and box.width == fireplace.depth
            assert QtCore.QLineF(box.secondVertex - box.firstVertex, direction * fireplace.length).length() < 1e-6
            for mode in unitModes:
                v.unitsMode = mode
                main.RefreshProperties()
                for field, value in (("length", 1200), ("width", 500)):
                    divisor, unused = PropertyUnit(field, fireplace, mode)
                    assert abs(main.propertyFields[field].value() * divisor - value) < .2, (mode, field)
                assert EncodeScene(v) == before and FireplacePath(fireplace) == path
            v.unitsMode = "Millimeters"
            main.RefreshProperties()
            assert main.propertyFields["width"].minimum() == 240
            assert main.propertyFields["length"].maximum() == 6000
            for field, axis in (("length", direction), ("width", -normal)):
                handle = next(handle for handle in v.FurnishingHandles(fireplace) if handle[:3] == ("resize", field, 1))
                v.BeginFurnishingHandleDrag(fireplace, handle, handle[3])
                end = v.WorldToViewport(v.ViewportToWorld(handle[3]) + axis * 200)
                v.UpdateFurnishingHandleDrag(end, QtCore.Qt.KeyboardModifier.NoModifier)
                assert math.isclose(fireplace.length, 1400 if field == "length" else 1200, abs_tol = 1e-6)
                assert math.isclose(fireplace.depth, 700 if field == "width" else 500, abs_tol = 1e-6)
                v.CancelInteraction()
                assert EncodeScene(v) == before

        # Read a legacy-format project without rewriting it or changing geometry.
        data = main.BuildProjectData(includeHistory = False)
        original = json.dumps(data, indent = 2).encode("utf-8")
        project = folder / "legacy-fireplace.plan"
        project.write_bytes(original)
        assert main.OpenProject(project)
        assert project.read_bytes() == original and EncodeScene(v) == before
        assert FireplacePath(v.windows[0]) == path
        assert main.BuildProjectData(includeHistory = False)["scene"] == data["scene"]

        # Multi-selection edits operate on the same axes and preserve unrelated
        # dimensions. The common width minimum respects every parent thickness.
        firstParent = Wall(point(-3000, 0), point(3000, 0), 240)
        secondParent = Wall(point(-3000, 3000), point(3000, 3000), 400)
        first = Fireplace(firstParent, .4, .6)
        second = Fireplace(secondParent, .4, .6)
        first.depth = second.depth = 600
        InstallScene(main, [firstParent, secondParent, first, second])
        v.unitsMode = "Millimeters"
        v.SetSelection([(first, None), (second, None)])
        main.sizeLinkButton.setChecked(False)
        main.RefreshProperties()
        assert main.propertyFields["length"].value() == 1200
        assert main.propertyFields["width"].value() == 600
        assert main.propertyFields["width"].minimum() == 400
        main.EditProperty("length", 1600)
        assert first.length == second.length == 1600 and first.depth == second.depth == 600
        v.Undo()
        assert math.isclose(first.length, 1200) and math.isclose(second.length, 1200)
        main.EditProperty("width", 800)
        assert first.depth == second.depth == 800 and math.isclose(first.length, 1200) and math.isclose(second.length, 1200)
        v.Undo()
        assert first.depth == second.depth == 600
        v.Redo()
        assert first.depth == second.depth == 800
        second.depth = 900
        main.RefreshProperties()
        assert main.propertyFields["width"].mixedValue and not main.propertyFields["length"].mixedValue

        # Switching to a thicker parent must only refresh the displayed minimum,
        # never apply that minimum as an edit to the newly selected object.
        firstParent.width, secondParent.width = 100, 700
        first.depth, second.depth = 200, 1000
        v.unitsMode = "Adaptive Metric"
        v.SetSelection([(first, None)])
        before = EncodeScene(v)
        historyCount = len(v.undoHistory)
        v.SetSelection([(second, None)])
        assert EncodeScene(v) == before and len(v.undoHistory) == historyCount
        assert main.propertyFields["width"].value() == 100 and main.propertyFields["width"].minimum() == 70
    print("Fireplace dimensions: properties/handles across angles and units, bulk edits, undo and legacy geometry/records passed")


if __name__ == "__main__":
    Main()
