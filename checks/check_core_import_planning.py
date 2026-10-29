"""Asset import planning and opening orientation work without Qt installed."""
import copy
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))


def CheckWithoutQt():
    from planner_app.furnishing_import_plan import PlanFurnishingImports
    from planner_app.geometry.editing import OpeningOrientationChanges

    incoming = {"assembly": {"name": "Assembly", "components": [{"definition": "leaf", "x": 20}]},
                "leaf": {"name": "New leaf", "width": 1234}}
    existing = {"assembly": copy.deepcopy(incoming["assembly"]), "leaf": {"name": "Old leaf"},
                "leaf_imported": copy.deepcopy(incoming["leaf"]), "ASSEMBLY_IMPORTED": {"name": "Reserved"}}
    before = copy.deepcopy((incoming, existing))
    portable, remapped = PlanFurnishingImports(incoming, existing, iter(existing))
    assert remapped == {"leaf": "leaf_imported", "assembly": "assembly_imported_2"}
    assert portable["assembly_imported_2"]["components"][0] == {"definition": "leaf_imported", "x": 20}
    assert portable["leaf_imported"] == incoming["leaf"]
    assert (incoming, existing) == before
    destination = {**existing, **portable}
    repeated, repeatedKeys = PlanFurnishingImports(incoming, destination, destination)
    assert repeated == portable and repeatedKeys == remapped
    portable["assembly_imported_2"]["components"][0]["x"] = 99
    assert incoming["assembly"]["components"][0]["x"] == 20

    plain, remapped = PlanFurnishingImports(incoming, {}, ())
    assert plain == incoming and remapped == {}
    same, remapped = PlanFurnishingImports(incoming, incoming, incoming)
    assert same == incoming and remapped == {}
    custom, remapped = PlanFurnishingImports({"leaf": incoming["leaf"]}, existing, existing, suffix = "decomposed")
    assert set(custom) == {"leaf_decomposed"} and remapped == {"leaf": "leaf_decomposed"}
    assert PlanFurnishingImports({}, existing, existing) == ({}, {})
    external = {"assembly": {"components": [{"definition": "installed_only"}]}}
    assert PlanFurnishingImports(external, {}, {"installed_only"}) == (external, {})
    for cycle in ({"a": {"components": [{"definition": "a"}]}},
                  {"a": {"components": [{"definition": "b"}]}, "b": {"components": [{"definition": "a"}]}}):
        before = copy.deepcopy(cycle)
        try:
            PlanFurnishingImports(cycle, {}, ())
        except ValueError:
            pass
        else:
            raise AssertionError("Cyclic dependencies must fail before import.")
        assert cycle == before

    fields = {"hingeAtSecond": True, "swingsOutwards": False, "panelsFlipped": True,
              "depthOffset": 25, "measurementFlipped": True, "wellDepth": 600}
    expected = {
        (False, False): {},
        (True, False): {"hingeAtSecond": False, "swingsOutwards": True, "panelsFlipped": False, "depthOffset": -25},
        (False, True): {"swingsOutwards": True, "panelsFlipped": False, "depthOffset": -25},
        (True, True): {"hingeAtSecond": False},
    }
    before = dict(fields)
    for (reversedAlongWall, reflected), changes in expected.items():
        assert OpeningOrientationChanges(fields, reversedAlongWall, reflected = reflected) == changes
        transformed = {**fields, **changes}
        assert {**transformed, **OpeningOrientationChanges(transformed, reversedAlongWall, reflected = reflected)} == fields
        assert OpeningOrientationChanges({}, reversedAlongWall, reflected = reflected) == {}
    assert OpeningOrientationChanges({"hingeAtSecond": False}, True) == {"hingeAtSecond": True}
    assert fields == before
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: dependency planning and opening orientation without Qt or site packages")


def Main():
    result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"],
                            capture_output = True, text = True, timeout = 10)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout.strip())


if __name__ == "__main__":
    CheckWithoutQt() if "--without-qt" in sys.argv else Main()
