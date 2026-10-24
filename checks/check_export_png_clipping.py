"""Cropped connected walls retain doorway cutouts in sampled transparent previews."""
import json
import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall
from planner_app.project_codec import DecodeProject
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.graphics.palette import themeColors


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    main = MainWindow()
    # High-contrast fixture isolates cutout coverage from theme preferences.
    themeColors.update(canvas = "#000000", wallFill = "#ffffff", wallOutline = "#ffffff")
    v = main.viewport
    data = json.loads((Path(__file__).parent / "fixtures/png_clip_crop.plan").read_text(encoding = "utf-8"))
    decoded = DecodeProject(data, v.furnishingDefinitions, validatePlacement = False)
    v.walls, v.windows, v.furnishings, v.objectGroups, v.hiddenObjectIds, settings, view, v.labels = decoded
    v.wallStyle = "Solid"
    v.showMeasurements = v.showGrid = False
    v.sceneRevision += 1
    overlay = v.exportOverlay
    overlay.scale = 750
    coverage = QtCore.QRectF(-10500, -5100, 14100, 12500)
    for sampling in (.07, .17, .20213, .23426, .37):
        captures = []
        for solid in (True, False):
            v.solidObjects = solid
            captures.append(overlay.CaptureRaster(coverage, sampling, "detail"))
        solidImage, transparentImage = captures
        assert all(image is not None for image in captures)
        tested = 0
        for wall in v.walls:
            if type(wall) is not Wall:
                continue
            for fraction in (.12, .33, .56, .87):
                if any(opening.parentWall is wall and opening.firstFraction - .02 <= fraction <= opening.secondFraction + .02
                       for opening in v.windows):
                    continue
                world = wall.firstVertex + (wall.secondVertex - wall.firstVertex) * fraction
                if not coverage.adjusted(100, 100, -100, -100).contains(world):
                    continue
                point = QtCore.QPoint(round((world.x() - coverage.x()) / coverage.width() * solidImage.width()),
                                     round((coverage.bottom() - world.y()) / coverage.height() * solidImage.height()))
                if solidImage.pixelColor(point).lightness() > 90:
                    tested += 1
                    assert transparentImage.pixelColor(point).lightness() > 90, (sampling, wall.objectId, fraction)
        assert tested >= 30, tested
        # Doorway centers must remain empty, rather than receiving the wall fill.
        tested = 0
        for opening in v.windows:
            if type(opening).__name__ not in ("Door", "OpenDoorway"):
                continue
            world = (opening.firstVertex + opening.secondVertex) / 2
            if not coverage.adjusted(100, 100, -100, -100).contains(world):
                continue
            point = QtCore.QPoint(round((world.x() - coverage.x()) / coverage.width() * solidImage.width()),
                                 round((coverage.bottom() - world.y()) / coverage.height() * solidImage.height()))
            if solidImage.pixelColor(point).lightness() < 30:
                tested += 1
                assert transparentImage.pixelColor(point).lightness() < 30, (sampling, opening.objectId)
        assert tested >= 5, tested
    main.close()


if __name__ == "__main__":
    Main()
