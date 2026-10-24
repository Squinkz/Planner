"""Check bundled weights and comparable GUI/offscreen text metrics."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import warnings

appDirectory = Path(__file__).resolve().parent.parent / "planner-main"
sys.path.insert(0, str(appDirectory))


def Main():
    if len(sys.argv) == 1:
        results = []
        for platform in ("windows", "offscreen"):
            environment = dict(os.environ, QT_QPA_PLATFORM = platform,
                               QT_QPA_FONTDIR = str(appDirectory / "assets" / "fonts"))
            result = subprocess.run([sys.executable, __file__, platform], env = environment,
                                    capture_output = True, text = True)
            assert result.returncode == 0, result.stderr
            results.append(json.loads(result.stdout))
        # Native Windows and FreeType hinting can round glyph widths differently.
        for guiMetric, exportMetric in zip(*results):
            assert abs(guiMetric - exportMetric) / guiMetric < .02, "Font metrics differ substantially between GUI and exporter"
        print("Bundled fonts and GUI/offscreen metrics checks passed")
        return

    from PySide6 import QtGui, QtWidgets
    from planner_app.graphics.fonts import fontFamily, LoadApplicationFonts
    from planner_app.graphics.theme import ApplyApplicationTheme
    from planner_app.models import Label
    from planner_app.graphics import palette

    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    fontIds = app.plannerFontIds
    LoadApplicationFonts(app)
    fontPaths = [path for path in (appDirectory / "assets/fonts").iterdir()
                 if path.suffix.lower() in (".ttf", ".otf", ".ttc", ".otc")]
    assert app.plannerFontIds == fontIds and len(fontIds) == len(fontPaths)
    assert all(fontId >= 0 for fontId in fontIds)
    metrics = []
    for weight, style in ((400, "Regular"), (600, "SemiBold"), (700, "Bold")):
        font = QtGui.QFont(fontFamily, 10)
        font.setWeight(QtGui.QFont.Weight(weight))
        info = QtGui.QFontInfo(font)
        assert info.family() == fontFamily and info.styleName() == style, (info.family(), info.styleName())
        metrics.append(QtGui.QFontMetricsF(font).horizontalAdvance("Planner 0123456789"))

    for objectName, weight in (("", 400), ("selectionHeading", 600), ("objectSubheading", 700)):
        widget = QtWidgets.QLabel("Heading")
        widget.setObjectName(objectName)
        widget.ensurePolished()
        assert QtGui.QFontInfo(widget.font()).family() == fontFamily
        assert widget.font().weight() == weight
    label = Label(text = "Planner 0123456789")
    assert QtGui.QFontInfo(label.Font()).family() == fontFamily
    metrics.extend((label.width, label.length))
    with tempfile.TemporaryDirectory() as folder:
        directory = Path(folder)
        colors = dict(palette.themeDefinitions["Dark Canvas"]["colors"])
        for name, family in (("Default", None), ("Custom", "monospace"), ("Invalid", 123)):
            definition = {"name": name, "type": "canvas", "colors": colors}
            if family is not None:
                definition["labelFont"] = family
            (directory / f"{name}.json").write_text(json.dumps(definition), encoding = "utf-8")
        with warnings.catch_warnings(record = True) as errors:
            definitions = palette.LoadThemes(directory)
        assert set(definitions) == {"Default", "Custom"} and len(errors) == 1
        assert definitions["Default"]["labelFont"] == fontFamily
        palette.themeDefinitions.update(definitions)
        originalBounds = (label.firstVertex, label.secondVertex, label.width)
        palette.SetThemes(canvasTheme = "Custom")
        assert label.Font().family() == "monospace", "Existing label ignored theme font"
        assert (label.firstVertex, label.secondVertex, label.width) == originalBounds
        assert QtGui.QFontInfo(app.font()).family() == fontFamily, "Label font changed UI font"
        palette.SetThemes(canvasTheme = "Dark Canvas")
        assert label.Font().family() == fontFamily
        for name in definitions:
            del palette.themeDefinitions[name]
    print(json.dumps(metrics))


if __name__ == "__main__":
    Main()
