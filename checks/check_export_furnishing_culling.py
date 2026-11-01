"""Off-page ordinary artwork avoids native construction without changing pixels."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Furnishing
from planner_app.graphics.furnishings import FurnishingRendererMap, FurnishingRenderer, FurnishingArtworkBounds
from planner_app.graphics.svg_preview import SvgPreviewRenderer
from planner_app.export_plan import RenderPlan


def SvgPixels(data):
    renderer = SvgPreviewRenderer(data)
    image = QtGui.QImage(renderer.size, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    with QtGui.QPainter(image) as painter:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        renderer.render(painter)
    return image


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        base = v.furnishingDefinitions["washer"]
        sources = (
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="45" fill="white" stroke="black"/><text x="35" y="55">A</text></svg>',
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect id="planner-bounds" x="20" y="20" width="60" height="60"/><path d="M-100 0L200 100" fill="none" stroke="black"/></svg>')
        definitions = []
        for key, source in zip(("cull-near", "cull-far", "cull-custom"), (sources[0], sources[0], sources[1])):
            definition = dict(base, key = key, graphicData = source)
            v.furnishingDefinitions[key] = definition
            definitions.append(definition)
            # Seed neutral preparation, as the editor does before export.
            FurnishingRenderer(source, lineWidth = v.lineWidths["furnishings"], nominalSize = (definition["width"], definition["length"]))
        near = Furnishing(definitions[0], QtCore.QPointF(1500, 1500))
        far = Furnishing(definitions[1], QtCore.QPointF(80000, 1500))
        custom = Furnishing(definitions[2], QtCore.QPointF(3000, 1800))
        custom.flipHorizontal = True
        InstallScene(main, [Wall(QtCore.QPointF(0, 0), QtCore.QPointF(4000, 0), 200), near, far, custom])
        data = main.BuildProjectData(includeHistory = False, includeActivity = False)
        for solid in (False, True):
            for kind in ("png", "svg"):
                realized = []
                original = FurnishingRendererMap.__missing__
                def Track(renderers, key):
                    realized.append(key)
                    return original(renderers, key)
                arguments = dict(planPath = "cull.plan", scale = 100, bounds = (-500, -500, 5000, 4000),
                                 outputFormat = kind, projectData = data, applyTheme = False,
                                 solidObjects = solid, furnishingDefinitions = v.furnishingDefinitions)
                with patch.object(FurnishingRendererMap, "__missing__", Track):
                    actual = RenderPlan(**arguments)
                assert "cull-far" not in realized, "Off-page ordinary asset constructed a native renderer"
                assert "cull-near" in realized and "cull-custom" in realized
                with patch.object(FurnishingRendererMap, "ArtworkGeometry", lambda renderers, key: renderers[key]):
                    expected = RenderPlan(**arguments)
                assert (SvgPixels(actual) == SvgPixels(expected) if kind == "svg" else actual == expected), (kind, solid)
        renderers = FurnishingRendererMap(v.furnishingDefinitions)
        for obj in (near, far, custom):
            key = obj.definition["key"]
            metadata = renderers.ArtworkGeometry(key)
            native = renderers[key]
            assert FurnishingArtworkBounds(obj, metadata) == FurnishingArtworkBounds(obj, native)
        assert not isinstance(renderers.ArtworkGeometry("cull-custom"), QtCore.QRectF)
    print("Off-page native construction skipped; exact solid/transparent PNG/SVG pixels and authored/flipped bounds preserved")


if __name__ == "__main__":
    Main()
