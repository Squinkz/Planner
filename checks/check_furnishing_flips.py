"""Furnishing mirrors preserve artwork, history, clipboard and compound layouts."""
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets, QtSvg
from planner import MainWindow
from planner_app.models import Furnishing
from planner_app.catalog import LoadFurnishings
from planner_app.furnishing_parts import FurnishingParts
from planner_app.graphics.furnishings import DrawFurnishing, FurnishingRenderer, CompoundFurnishingSvg, FurnishingArtworkBounds
from planner_app.project_codec import DecodeProject
from check_pan_dpi import CompareDirect


def Render(objects, vector = False):
    image = QtGui.QImage(400, 400, QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtGui.QColor("white"))
    data = QtCore.QByteArray()
    buffer = QtCore.QBuffer(data)
    buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    generator = QtSvg.QSvgGenerator()
    generator.setOutputDevice(buffer)
    generator.setSize(image.size())
    generator.setViewBox(QtCore.QRect(0, 0, 400, 400))
    with QtGui.QPainter(generator if vector else image) as painter:
        for obj in objects:
            renderer = FurnishingRenderer(obj.definition["graphicData"], solidBackground = False,
                                          palette = {"outline": "#000000", "background": "#ffffff", "missing": "#000000"})
            first = QtCore.QPointF(200 + obj.firstVertex.x() * .5, 200 - obj.firstVertex.y() * .5)
            second = QtCore.QPointF(200 + obj.secondVertex.x() * .5, 200 - obj.secondVertex.y() * .5)
            DrawFurnishing(painter, obj, first, second, .5, renderer, drawBounds = False)
    if vector:
        renderer = QtSvg.QSvgRenderer(bytes(data))
        assert renderer.isValid()
        with QtGui.QPainter(image) as painter:
            renderer.render(painter)
    return image


def Main():
    app = QtWidgets.QApplication([])
    graphic = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 80"><rect width="100" height="80" fill="white"/><rect x="10" y="10" width="25" height="20" fill="black"/></svg>'
    definition = {"key": "test", "name": "Test", "width": 100, "length": 80, "graphicData": graphic}
    obj = Furnishing(definition)
    original = Render([obj])
    for horizontal, vertical, sampleX, sampleY in ((False, False, 185, 190), (True, False, 215, 190),
                                                 (False, True, 185, 210), (True, True, 215, 210)):
        obj.flipHorizontal, obj.flipVertical = horizontal, vertical
        for vector in (False, True):
            image = Render([obj], vector)
            assert image.pixelColor(sampleX, sampleY).lightness() < 30, (horizontal, vertical, vector)
            if horizontal or vertical:
                assert image != original
        clone = obj.Clone()
        assert (clone.flipHorizontal, clone.flipVertical) == (horizontal, vertical)
    protruding = FurnishingRenderer(b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 80"><rect x="100" y="0" width="30" height="20" fill="black"/></svg>')
    obj.flipHorizontal = obj.flipVertical = False
    bounds = FurnishingArtworkBounds(obj, protruding)
    obj.flipHorizontal = True
    flippedBounds = FurnishingArtworkBounds(obj, protruding)
    assert abs(bounds.right() + flippedBounds.left()) < 1e-6

    components = [{"definition": definition, "x": -70, "y": 20, "width": 100, "length": 80, "angle": 30,
                   "zIndex": 0, "flipHorizontal": True, "flipVertical": False},
                  {"definition": definition, "x": 70, "y": -20, "width": 100, "length": 80, "angle": 0,
                   "zIndex": 1, "flipHorizontal": False, "flipVertical": True}]
    graphic, width, length, center = CompoundFurnishingSvg(components)
    compound = Furnishing({"key": "compound", "width": width, "length": length, "graphicData": graphic,
                           "components": components, "compoundCenter": center})
    compound.angle = 27
    for horizontal, vertical in ((False, False), (True, False), (False, True), (True, True)):
        compound.flipHorizontal, compound.flipVertical = horizontal, vertical
        combinedImage = Render([compound])
        partsImage = Render(FurnishingParts(compound))
        differingPixels = sum(abs(combinedImage.pixelColor(x, y).lightness() - partsImage.pixelColor(x, y).lightness()) > 30
                              for y in range(400) for x in range(400))
        assert differingPixels < 100, (horizontal, vertical, differingPixels)

    main = MainWindow()
    main.show()
    app.processEvents()
    v = main.viewport
    v.localTransforms = False
    v.performanceTimer.stop()
    v.performanceLabel.hide()
    globalDefinition = {**v.furnishingDefinitions["desk"], **definition, "key": "desk"}
    for angle in (33, 90, 147):
        for horizontal, vertical in ((False, False), (True, False), (False, True), (True, True)):
            for command in ("flipHorizontal", "flipVertical"):
                mirrored = Furnishing(globalDefinition)
                mirrored.angle = angle
                mirrored.flipHorizontal, mirrored.flipVertical = horizontal, vertical
                v.furnishings = [mirrored]
                v.SetSelection([(mirrored, None)])
                expected = Render([mirrored]).mirrored(command == "flipHorizontal", command == "flipVertical")
                v.ApplyObjectContextAction([mirrored], command)
                actual = Render([mirrored])
                differingPixels = sum(a != b for a, b in zip(memoryview(actual.constBits()).cast("I"),
                                                             memoryview(expected.constBits()).cast("I")))
                assert differingPixels < 100, (angle, horizontal, vertical, command, differingPixels)
                assert QtCore.QLineF((mirrored.firstVertex + mirrored.secondVertex) / 2, QtCore.QPointF()).length() < 1e-8
                assert abs(mirrored.width - 100) < 1e-8 and abs(mirrored.length - 80) < 1e-8
                v.ApplyObjectContextAction([mirrored], command)
                assert abs(mirrored.angle - angle) < 1e-8
                assert (mirrored.flipHorizontal, mirrored.flipVertical) == (horizontal, vertical)
    v.undoHistory, v.redoHistory = [], []
    first = Furnishing(v.furnishingDefinitions["desk"])
    second = Furnishing(v.furnishingDefinitions["chair_dining"], QtCore.QPointF(2000, 0))
    first.angle, second.angle = 37, 118
    v.furnishings = [first, second]
    v.SetSelection([(first, None), (second, None)])
    renderKey = v.SceneRenderKey(None)
    renderValues = v.SceneRenderValueKey(None)
    main.RefreshProperties()
    sharedCenter = v.ObjectFootprint(first)[0].united(v.ObjectFootprint(second)[0]).center()
    main.furnishingFlipFields["flipHorizontal"].click()
    assert first.flipHorizontal and second.flipHorizontal
    assert abs(first.angle - 323) < 1e-8 and abs(second.angle - 242) < 1e-8
    assert QtCore.QLineF((second.firstVertex + second.secondVertex) / 2, QtCore.QPointF(2 * sharedCenter.x() - 2000, 0)).length() < 1e-8
    assert v.SceneRenderKey(None) != renderKey
    assert v.SceneRenderValueKey(None) != renderValues
    CompareDirect(v)
    assert len(v.undoHistory) == 1
    v.Undo()
    assert not first.flipHorizontal and not second.flipHorizontal
    assert abs(first.angle - 37) < 1e-8 and abs(second.angle - 118) < 1e-8
    v.Redo()
    assert first.flipHorizontal and second.flipHorizontal
    v.ApplyObjectContextAction([first], "flipVertical")
    assert first.flipVertical and not second.flipVertical
    v.isPanning = True
    CompareDirect(v)
    v.isPanning = False
    main.RefreshProperties()
    for button in main.furnishingFlipFields.values():
        assert isinstance(button, QtWidgets.QPushButton) and not button.isCheckable()
        assert button.size() == main.stairDirectionButton.size()
        assert button.iconSize() == main.stairDirectionButton.iconSize() and not button.icon().isNull()
    main.furnishingFlipFields["flipVertical"].click()
    assert not first.flipVertical and second.flipVertical
    v.Undo()
    assert first.flipVertical and not second.flipVertical
    data = main.BuildProjectData(includeHistory = False)
    data["history"] = main.ProjectHistory()
    decoded = DecodeProject(data, v.furnishingDefinitions, validatePlacement = False)
    assert [(item.flipHorizontal, item.flipVertical) for item in decoded[2]] == [(True, True), (True, False)]
    assert len(decoded[5]["history"]["undo"]) == 2
    main.ApplyProject(decoded, None)
    v.Undo()
    assert all(not item.flipVertical for item in v.furnishings)
    v.Redo()
    assert v.furnishings[0].flipVertical
    v.SetSelection([(v.furnishings[0], None)])
    assert v.CopySelection() and v.PasteSelection(inPlace = True)
    pasted = v.selectedWall
    assert pasted.flipHorizontal and pasted.flipVertical
    for record in data["scene"]["objects"]:
        record.pop("flipHorizontal", None)
        record.pop("flipVertical", None)
    data.pop("history")
    assert all(not item.flipHorizontal and not item.flipVertical
               for item in DecodeProject(data, v.furnishingDefinitions, validatePlacement = False)[2])

    catalog = LoadFurnishings(definitionOverrides = {"mirrored_test": {"name": "Mirrored Test", "children": [
        {"furnishing": "desk", "flipHorizontal": True, "flipVertical": True}]}})
    mirroredDefinition = next(item for item in catalog if item["key"] == "mirrored_test")
    mirrored = Furnishing(mirroredDefinition)
    v.furnishingDefinitions["mirrored_test"] = mirroredDefinition
    v.furnishings = [mirrored]
    v.SetSelection([])
    v.undoHistory, v.redoHistory = [], []
    embeddedData = main.BuildProjectData(includeHistory = False)
    embedded = DecodeProject(embeddedData, v.localFurnishingDefinitions, validatePlacement = False)[2][0]
    child = FurnishingParts(embedded)[0]
    assert child.flipHorizontal and child.flipVertical
    main.close()
    app.clipboard().clear()
    app.processEvents()
    print("PASS: raster/vector mirrors, bounds, compounds/decomposition, properties, history, clipboard and project compatibility.")


if __name__ == "__main__":
    Main()
