"""Embedded records and catalog policies run without native graphics."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from xml.etree import ElementTree


def CheckWithoutQt():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
    from planner_app.furnishing_records import ReadEmbeddedFurnishings, WriteEmbeddedFurnishings
    from planner_app.catalog_records import ReadFurnishingCatalog
    svg = '<svg xmlns="http://www.w3.org/2000/svg"/>'
    leaf = dict(name = "Leaf", category = "Miscellaneous", keywords = [], width = 100, length = 200, svg = svg)
    component = dict(definition = "leaf", x = 0, y = 0, angle = 0, width = 100, length = 200, zIndex = 0)
    embedded = dict(leaf = leaf, assembly = dict(leaf, name = "Assembly", compoundCenter = [0, 0], components = [component, dict(component, definition = "missing")]))
    before = copy.deepcopy(embedded)
    definitions = {"null": dict(key = "null")}
    decoded = ReadEmbeddedFurnishings(embedded, definitions, ElementTree.fromstring)
    children = decoded["assembly"]["components"]
    assert children[0]["definition"] is decoded["leaf"] and children[1]["definition"] is definitions["null"]
    assert embedded == before and set(definitions) == {"null"}
    encoded = WriteEmbeddedFurnishings([decoded["assembly"]], ElementTree.fromstring)
    assert set(encoded) == {"assembly", "leaf"}
    assert encoded["assembly"]["components"][1]["definition"] == "missing"
    cyclic = dict(embedded, assembly = dict(embedded["assembly"], components = [dict(component, definition = "assembly")]))
    try:
        ReadEmbeddedFurnishings(cyclic, definitions, ElementTree.fromstring)
    except ValueError:
        pass
    else:
        raise AssertionError("Cycle accepted")
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        (folder / "definitions").mkdir()
        (folder / "images").mkdir()
        (folder / "images/null.svg").write_text(svg)
        null = dict(name = "Null", image = "null", icon = "null", width = 100, length = 200, category = "Miscellaneous", inherits = None)
        (folder / "definitions/null.json").write_text(json.dumps(null))
        (folder / "definitions/leaf.json").write_text(json.dumps(dict(name = "Leaf", inherits = "null", width = 150)))
        catalog = ReadFurnishingCatalog(folder, lambda parts: (svg.encode(), 500, 500, (0, 0)),
            lambda records, installed: ReadEmbeddedFurnishings(records, installed, ElementTree.fromstring),
            definitionOverrides = {"assembly": dict(children = [dict(furnishing = "leaf")])})
        byKey = {definition["key"]: definition for definition in catalog}
        assert byKey["leaf"]["width"] == 150 and byKey["leaf"]["length"] == 200
        assert byKey["assembly"]["components"][0]["definition"] is byKey["leaf"]
    assert not any(name.startswith("PySide6") for name in sys.modules)
    print("PASS: portable furnishing records, authoritative graph references, missing assets, cycles and catalog inheritance")


if __name__ == "__main__":
    if "--without-qt" in sys.argv:
        CheckWithoutQt()
    else:
        result = subprocess.run([sys.executable, "-S", str(Path(__file__).resolve()), "--without-qt"], capture_output = True, text = True, timeout = 10)
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout.strip())
