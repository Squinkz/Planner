"""Recovery, properties, transport and exports agree on unresolved asset identity."""
from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from planner import MainWindow
from planner_app.catalog import LoadFurnishings
from planner_app.paths import furnishingsDirectory
from planner_app.furnishing_assets import FurnishingAssetProblems
from planner_app.models import Furnishing, NorthArrow
from planner_app.project_recovery import RecoverProject
from planner_app.project_codec import DecodeProject
from planner_app.export_plan import RenderPlan
from planner_app.graphics.furnishings import FurnishingRenderer, CompoundFurnishingSvg


def Main():
    app = QtWidgets.QApplication([])
    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        (folder / "definitions").mkdir()
        (folder / "images").mkdir()
        shutil.copyfile(furnishingsDirectory / "images/null.svg", folder / "images/null.svg")
        nullDefinition = json.loads((furnishingsDirectory / "definitions/null.json").read_text(encoding = "utf-8"))
        for key, definition in {
            "null": nullDefinition,
            "bad_image": {"name": "Missing image", "image": "does_not_exist"},
            "compound": {"name": "Compound", "children": [{"furnishing": "Gone child"}]},
        }.items():
            (folder / "definitions" / (key + ".json")).write_text(json.dumps(definition), encoding = "utf-8")
        local = {definition["key"]: definition for definition in LoadFurnishings(folder)}
        assert local["compound"]["components"][0]["definitionKey"] == "Gone child"
        assert FurnishingAssetProblems("compound", local) == {"Gone child": "missing"}
        assert FurnishingAssetProblems("bad_image", local) == {"bad_image": "artwork"}
        definitions = {**v.furnishingDefinitions, **local}
        null = definitions["null"]
        damaged = dict(definitions["desk"], key = "damaged", graphicData = Path(null["imagePath"]).read_bytes())
        definitions["damaged"] = damaged
        damagedCompound = dict(damaged, components = [{"definition": definitions["desk"]}])
        assert FurnishingAssetProblems("damaged", definitions, damagedCompound) == {"damaged": "artwork"}
        v.furnishingDefinitions = definitions
        v.walls, v.windows, v.labels, v.objectGroups, v.hiddenObjects = [], [], [], [], []
        objects = [Furnishing(definitions[key], QtCore.QPointF(index * 2000, 0))
                   for index, key in enumerate(("compound", "bad_image", "damaged"))]
        missing = Furnishing(null, QtCore.QPointF(6000, 0))
        missing.definitionKey = "Gone object"
        north = NorthArrow(QtCore.QPointF(8000, 0))
        v.furnishings = objects + [missing, north]
        v.EnsureObjectIds()
        expectedKeys = {"Gone child", "bad_image", "damaged", "Gone object"}
        assert set(main.RecoveryObjectEntries()) == expectedKeys
        for obj in objects + [missing]:
            v.SetSelection([(obj, None)])
            assert not v.CanCopySelection()
            assert "asset error" in main.selectionLabel.text() or "(missing)" in main.selectionLabel.text()
        v.SetSelection([(north, None)])
        assert v.CanCopySelection() and "missing" not in main.selectionLabel.text()
        v.SetSelection([])
        data = main.BuildProjectData(includeHistory = False)
        decoded, notices = RecoverProject(data, definitions, main.defaultProjectData)
        assert all(any(key in notice for notice in notices) for key in expectedKeys), notices
        decodedProblems = {key for obj in decoded[2] if type(obj) is Furnishing
                           for key in FurnishingAssetProblems(obj.definitionKey, definitions, obj.definition)}
        assert decodedProblems == expectedKeys
        # Saving the repaired records must retain the errors, not launder them
        # into available definitions simply because fallback artwork exists.
        assert set(FurnishingAssetProblems("damaged", definitions)) == {"damaged"}
        embeddedData = dict(data, furnishingDefinitions = {"damaged": {
            "name": "Damaged asset", "category": "Miscellaneous", "width": damaged["width"],
            "length": damaged["length"], "svg": damaged["graphicData"].decode("utf-8")}})
        for attempt in range(2):
            embeddedDecoded, embeddedNotices = RecoverProject(embeddedData, definitions, main.defaultProjectData)
            assert any("Unavailable furnishing artwork damaged:" in notice for notice in embeddedNotices)
            embeddedDefinitions = {**definitions, **embeddedDecoded[5]["embeddedFurnishings"]}
            assert FurnishingAssetProblems("damaged", embeddedDefinitions) == {"damaged": "artwork"}
        checkpoint = folder / "session.json"
        main.sessionPath = checkpoint
        v.sceneChanged.emit()
        main.RefreshProjectDirty()
        assert main.WriteSession(wait = True)
        with patch.object(main, "ShowAppMessage") as report:
            main.RestoreSession(checkpoint)
        assert report.call_count == 1, (report.call_args_list, checkpoint.exists(), v.clipboardError, main.RecoveryObjectEntries())
        assert set(report.call_args.kwargs["locateEntries"]) == expectedKeys
        main.viewport.exportOverlay.bounds = (-1000, -1500, 11000, 3000)
        with patch("planner_app.catalog.LoadFurnishings", side_effect = AssertionError("GUI export must use the editor's catalog")):
            for outputFormat in ("png", "svg"):
                assert main.exportPanel.Render(outputFormat, preview = True) is not None
        for outputFormat in ("png", "svg"):
            messages = io.StringIO()
            with patch("planner_app.catalog.LoadFurnishings", return_value = list(definitions.values())), redirect_stderr(messages):
                result = RenderPlan("Missing.plan", 30, (-1000, -1500, 11000, 3000),
                                    outputFormat = outputFormat, projectData = data, applyTheme = False)
            assert "missing furnishings" not in messages.getvalue().lower()
            assert result is not None
            roundTrip = DecodeProject(data, definitions)
            assert {key for obj in roundTrip[2] if type(obj) is Furnishing
                    for key in FurnishingAssetProblems(obj.definitionKey, definitions, obj.definition)} == expectedKeys

        colors = {"outline": "#0000ff", "background": "#ffffff", "missing": "#ff0000"}
        # Inspect exported vector paints as well as pixels: the hatch and border
        # must be error-colored, even for selected and transparent variants.
        source = Path(null["imagePath"]).read_bytes()
        compound, *unused = CompoundFurnishingSvg([
            {"definition": null, "x": 0, "y": 0, "width": 1000, "length": 1000, "angle": 0, "zIndex": 0}])
        legacySource = source.replace(b'   data-theme-outline="missing"', b'', 1)
        legacyCompound = compound.replace(b'data-theme-outline="missing"', b'', 1)
        for graphic in (source, legacySource, compound, legacyCompound):
            for selection in (None, "#00ff00"):
                for solid in (True, False):
                    renderer = FurnishingRenderer(graphic, palette = colors, selectionColor = selection, solidBackground = solid)
                    image = QtGui.QImage(240, 240, QtGui.QImage.Format.Format_ARGB32)
                    image.fill(QtCore.Qt.GlobalColor.transparent)
                    with QtGui.QPainter(image) as painter:
                        renderer.render(painter, QtCore.QRectF(20, 20, 200, 200))
                    ink = {image.pixelColor(x, y).name() for x in range(240) for y in range(240)
                           if image.pixelColor(x, y).alpha() > 0}
                    assert "#ff0000" in ink and "#0000ff" not in ink and "#00ff00" not in ink
                    buffer = QtCore.QBuffer()
                    buffer.open(QtCore.QIODevice.OpenModeFlag.ReadWrite)
                    generator = QtSvg.QSvgGenerator()
                    generator.setOutputDevice(buffer)
                    generator.setSize(QtCore.QSize(240, 240))
                    generator.setViewBox(QtCore.QRect(0, 0, 240, 240))
                    with QtGui.QPainter(generator) as painter:
                        renderer.render(painter, QtCore.QRectF(20, 20, 200, 200))
                    svg = bytes(buffer.data())
                    assert b"#ff0000" in svg and b"#0000ff" not in svg and b"#00ff00" not in svg
    main.projectDirty = False
    main.close()
    print("PASS: shared asset status, nested provenance, recovered artwork, built-ins, quiet PNG/SVG export and all Null foreground colors")


if __name__ == "__main__":
    Main()
