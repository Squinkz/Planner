"""Recovery metadata decisions are portable and retain their repair order."""
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree


def CheckWithoutQt():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
    from planner_app.recovery_records import RepairRecoveryScene, RepairRecoveryDefinitions, RepairRecoverySettings
    from planner_app.furnishing_records import ReadEmbeddedFurnishings
    from planner_app.project_settings import ReadProjectSettings, snapNames, visibilityNames
    scene = dict(objects = [dict(type = "Wall", id = 7, material = "Lost", measurementHidden = 1, geometryIssues = ["unknown", "opening_bounds", "opening_bounds"]),
        dict(type = "Wall", id = 7, material = "Generic"), dict(type = "Furnishing", id = True)],
        groups = [[0, 0, 1], [1, 2]], hidden = [True, 2, 2])
    changed, notices = RepairRecoveryScene(scene, {"Generic"})
    assert changed and [record["id"] for record in scene["objects"]] == [7, 8, 9]
    assert scene["groups"] == [[0, 1]] and scene["hidden"] == [2]
    assert scene["objects"][0]["originalMaterial"] == "Lost" and scene["objects"][0]["geometryIssues"] == ["opening_bounds"]
    defaults = dict(snapEnabled = True, connectedVertices = True, connectedObjects = True, groupMode = False,
        showGrid = True, showMeasurements = True, snap = {name: True for name in snapNames}, visibility = {name: True for name in visibilityNames},
        wallWidth = 240, wallMaterial = "Generic", doorType = "Door", windowType = "Window", roomStyle = "Tinted", exportSettings = {})
    original = dict(defaults, wallWidth = -1, floors = False)
    original.pop("roomStyle")
    settings, image, notices = RepairRecoverySettings(original, defaults,
        lambda record: ReadProjectSettings(record, {"Generic"}, {"overall": 1}, str, dict), {})
    assert settings["wallWidth"] == 240 and settings["roomStyle"] == "Canvas" and image is None
    svg = '<svg xmlns="http://www.w3.org/2000/svg"/>'
    null = dict(key = "null", width = 100, length = 200, graphicData = svg.encode())
    definitions = {"null": null}
    validate = lambda key, record: ReadEmbeddedFurnishings({key: record}, definitions, ElementTree.fromstring)
    recovered, notices = RepairRecoveryDefinitions({"broken": {}}, definitions, validate, lambda payload: True)
    assert recovered["broken"]["svg"] == svg and recovered["broken"]["width"] == 100
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: portable settings, IDs, memberships, geometry flags and embedded-definition recovery")


if __name__ == "__main__":
    if "--without-qt" in sys.argv:
        CheckWithoutQt()
    else:
        result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"], capture_output = True, text = True, timeout = 10)
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout.strip())
