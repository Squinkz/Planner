"""User catalogs overlay bundled defaults and preserve custom artwork in plans."""
import json
import os
from pathlib import Path
import sys
import tempfile
import warnings

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtWidgets
from planner_app.catalog import LoadFurnishings
from planner_app.project_codec import EncodeFurnishingDefinitions, DecodeFurnishingDefinitions


def Main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        bundled, user = root / "_internal/furnishings", root / "furnishings"
        for directory in (bundled / "definitions", bundled / "images", user / "definitions_user", user / "images_user"):
            directory.mkdir(parents = True)
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="{}"/></svg>'
        for name in ("null", "leaf", "icon"):
            (bundled / "images" / (name + ".svg")).write_text(svg.format("black"))
        records = {
            "null": dict(name = "Null", image = "null", icon = "null", width = 100, length = 200, category = "Miscellaneous", inherits = None),
            "leaf": dict(name = "Default leaf", image = "leaf", icon = "icon", width = 150),
            "inherited": dict(name = "Inherited", inherits = "leaf"),
            "assembly": dict(name = "Assembly", children = [dict(furnishing = "leaf")]),
        }
        for key, record in records.items():
            (bundled / "definitions" / (key + ".json")).write_text(json.dumps(record))
        originals = {path: path.read_bytes() for path in bundled.rglob("*") if path.is_file()}
        catalog = {item["key"]: item for item in LoadFurnishings(user, builtInFolder = bundled)}
        assert catalog["leaf"]["width"] == 150 and not catalog["leaf"]["isUser"]
        # Artwork alone overrides a bundled definition, including inherited and
        # generated compound artwork, and must be embedded when saving a plan.
        (user / "images_user/LEAF.svg").write_text(svg.format("red"))
        (user / "images_user/icon.svg").write_text(svg.format("blue"))
        catalog = {item["key"]: item for item in LoadFurnishings(user, builtInFolder = bundled)}
        for key in ("leaf", "inherited", "assembly"):
            assert catalog[key]["isUser"]
            portable = EncodeFurnishingDefinitions([catalog[key]])
            restored = DecodeFurnishingDefinitions(portable, catalog)
            assert key in restored and "red" in portable[key]["svg"]
        assert catalog["leaf"]["imagePath"] == user / "images_user/LEAF.svg"
        assert catalog["leaf"]["iconPath"] == user / "images_user/icon.svg"
        overridePath = user / "definitions_user/LEAF.json"
        overridePath.write_text(json.dumps(dict(name = "User leaf", image = "leaf", width = 350)))
        catalog = {item["key"]: item for item in LoadFurnishings(user, builtInFolder = bundled)}
        assert "LEAF" not in catalog and catalog["leaf"]["width"] == 350
        assert catalog["leaf"]["sourcePath"] == overridePath
        assert catalog["inherited"]["width"] == 350
        assert catalog["assembly"]["components"][0]["definition"] is catalog["leaf"]
        catalog = {item["key"]: item for item in LoadFurnishings(user, builtInFolder = bundled,
            definitionOverrides = {"LEAF": dict(name = "Preview", image = "leaf", width = 450)})}
        assert catalog["leaf"]["name"] == "Preview" and catalog["leaf"]["width"] == 450
        assert json.loads(overridePath.read_text())["width"] == 350
        overridePath.write_text("{broken JSON")
        with warnings.catch_warnings(record = True) as messages:
            catalog = {item["key"]: item for item in LoadFurnishings(user, builtInFolder = bundled)}
        assert messages and catalog["leaf"]["width"] == 150
        overridePath.unlink()
        for path in (user / "images_user").iterdir():
            path.unlink()
        catalog = {item["key"]: item for item in LoadFurnishings(user, builtInFolder = bundled)}
        assert catalog["leaf"]["imagePath"] == bundled / "images/leaf.svg" and not catalog["leaf"]["isUser"]
        assert all(path.read_bytes() == content for path, content in originals.items())
        # Source/custom catalogs still load both folders from a single root.
        (bundled / "images_user").mkdir()
        (bundled / "images_user/leaf.svg").write_text(svg.format("green"))
        catalog = {item["key"]: item for item in LoadFurnishings(bundled)}
        assert catalog["leaf"]["imagePath"] == bundled / "images_user/leaf.svg"
    print("PASS: bundled/user precedence, casing, inheritance, compound/save portability, preview overrides and default fallback")


if __name__ == "__main__":
    Main()
