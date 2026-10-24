"""Friendly control-point labels leave geometry and persisted setting keys intact."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from fixtures.parity_examples import ExampleWindow, CreateObject, InstallScene
from planner_app.project_codec import EncodeScene


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        assert main.snapOptions["vertices"].accessibleName() == "Control Points"
        assert "another control point" in main.snapOptions["alignment"].toolTip()
        for name in ("Wall", "Counter", "Railing", "Stair", "Door", "Window", "Arrow", "MeasurementGuide"):
            obj = CreateObject(v, name)
            objects = [obj.parentWall, obj] if name in ("Door", "Window") else [obj]
            InstallScene(main, objects)
            before = EncodeScene(v)
            for index in (0, 1):
                v.SetSelection([(obj, index)])
                main.RefreshProperties()
                assert main.vertexProperties.isVisible()
                assert main.vertexProperties.title() == f"Point {index + 1}", name
                assert EncodeScene(v) == before and not v.undoHistory
        for name in ("Wall", "Arrow", "MeasurementGuide"):
            objects = [CreateObject(v, name), CreateObject(v, name)]
            InstallScene(main, objects)
            before = EncodeScene(v)
            v.SetSelection([(objects[0], 0), (objects[1], 1)])
            main.RefreshProperties()
            assert main.vertexProperties.title() == "Selected points (2)", name
            assert EncodeScene(v) == before and not v.undoHistory
        settings = main.BuildProjectData(includeHistory = False)["settings"]
        assert "vertices" in settings["snap"] and "points" not in settings["snap"]
        assert "connectedVertices" in settings and "connectedPoints" not in settings
    print("Control-point terminology: snap labels, 8 object types, single/multiple points and unchanged geometry/keys passed")


if __name__ == "__main__":
    Main()
