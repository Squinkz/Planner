"""Verify sparse composition, precedence, typography and inheritance errors."""

import json
from pathlib import Path
import sys
import tempfile
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from planner_app.graphics.palette import LoadThemes, themeDefinitions


def Main():
    baseColors = dict(themeDefinitions["Light Canvas"]["colors"])
    sources = [
        # Children are deliberately read before their parents.
        {"name": "Composed", "extends": ["Base", "Accent", "Canvas"],
         "colors": {"selectionFill": "#abcdef"}},
        {"name": "Inherited", "extends": "Composed"},
        {"name": "FontOverride", "extends": "Composed", "labelFont": "Noto Sans"},
        {"name": "Reverse", "extends": ["Base", "Canvas", "Accent"]},
        {"name": "Base", "abstract": True, "colors": baseColors, "labelFont": "monospace"},
        {"name": "Accent", "abstract": True, "colors": {"canvas": "#112233", "selectionFill": "#445566"}},
        {"name": "Canvas", "abstract": True, "colors": {"canvas": "#778899"}},
        {"name": "Legacy", "colors": baseColors},
        {"name": "Missing", "extends": "Absent"},
        {"name": "Cycle A", "extends": "Cycle B"},
        {"name": "Cycle B", "extends": "Cycle A"},
        {"name": "Dependent", "extends": "Cycle A"},
        {"name": "Incomplete", "colors": {"canvas": "#000000"}},
        {"name": "Incomplete Child", "extends": ["Incomplete", "Base"]},
        {"name": "Unknown", "extends": "Base", "colors": {"typo": "#000000"}},
        {"name": "BadColor", "extends": "Base", "colors": {"canvas": "red"}},
        {"name": "BadParents", "extends": [123]},
        {"name": "BadAbstract", "abstract": "true"},
        {"name": "UI Base", "type": "ui", "abstract": True,
         "colors": themeDefinitions["Light UI"]["colors"]},
        {"name": "Mixed Parents", "extends": ["Base", "UI Base"]},
        {"name": "Wrong Role", "colors": {"windowBackground": "#000000"}},
        {"name": "Wrong Type", "type": "other"},
    ]
    for source in sources:
        source.setdefault("type", "canvas")
    with tempfile.TemporaryDirectory() as folder:
        directory = Path(folder)
        for index, source in enumerate(sources):
            (directory / f"{index:02}.jsonc").write_text("// Theme\n" + json.dumps(source), encoding = "utf-8")
        with warnings.catch_warnings(record = True) as errors:
            warnings.simplefilter("always")
            definitions = LoadThemes(directory)
        assert set(definitions) == {"Composed", "Inherited", "FontOverride", "Reverse", "Legacy"}
        expected = dict(baseColors, canvas = "#778899", selectionFill = "#abcdef")
        assert definitions["Composed"]["colors"] == expected
        assert definitions["Inherited"] == definitions["Composed"]
        assert definitions["Reverse"]["colors"]["canvas"] == "#112233"
        assert definitions["Composed"]["labelFont"] == "monospace", "Sparse parent reset inherited font"
        assert definitions["FontOverride"]["labelFont"] == "Noto Sans"
        assert definitions["Legacy"] == {"type": "canvas", "colors": baseColors, "labelFont": "Noto Sans"}
        assert baseColors == themeDefinitions["Light Canvas"]["colors"], "Inheritance mutated parent colors"
        messages = "\n".join(str(error.message) for error in errors)
        assert len(errors) == 13, messages
        assert "Missing or invalid parent theme: Absent" in messages
        assert "Circular theme inheritance:" in messages and "Cycle A -> Cycle B -> Cycle A" in messages
        assert "Resolved theme Incomplete is missing color roles:" in messages
        assert "different theme type" in messages and "other theme type" in messages
        definitions["Composed"]["colors"]["canvas"] = "#ffffff"
        assert definitions["Inherited"]["colors"]["canvas"] == "#778899", "Resolved themes share mutable colors"
    with tempfile.TemporaryDirectory() as folder:
        directory = Path(folder)
        (directory / "partial.json").write_text(json.dumps(sources[5]), encoding = "utf-8")
        try:
            LoadThemes(directory)
        except ValueError as error:
            assert "No valid selectable theme" in str(error)
        else:
            raise AssertionError("Abstract-only theme folder was accepted")
    print("Theme inheritance checks passed")


if __name__ == "__main__":
    Main()
