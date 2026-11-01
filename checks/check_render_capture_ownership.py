"""Transparent capture receives resources explicitly and never borrows live state."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Wall, Furnishing
from planner_app.graphics.text import PathTextPainter


def Main():
    with ExampleWindow() as (main, folder):
        v = main.viewport
        InstallScene(main, [Wall(QtCore.QPointF(), QtCore.QPointF(3000, 0)),
                            Furnishing(v.furnishingDefinitions["washer"], QtCore.QPointF(1000, 1500))])
        v.solidObjects = False
        v.resize(640, 480)
        resources = tuple(getattr(v, name) for name in ("furnishingRenderers", "selectedFurnishingRenderers", "groupedFurnishingRenderers"))
        image = QtGui.QImage(v.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QtCore.Qt.GlobalColor.white)
        original = v.DrawOpaqueScene
        calls = []

        def Draw(*arguments, **options):
            assert not v.solidObjects
            assert all(getattr(v, name) is value for name, value in zip(
                ("furnishingRenderers", "selectedFurnishingRenderers", "groupedFurnishingRenderers"), resources))
            assert options["captureEngine"] is not None and options["rendererMaps"] is not None
            calls.append(True)
            return original(*arguments, **options)

        with PathTextPainter(image) as painter, patch.object(v, "DrawOpaqueScene", side_effect = Draw):
            v.DrawScene(painter, QtCore.QRectF(v.rect()), v.WorldToViewport(QtCore.QPointF()), v.zoom * v.basePixelsPerMillimeter)
        assert calls and not v.solidObjects and "objectCaptureEngine" not in v.__dict__
        revision = v.renderChanges.appearance
        with PathTextPainter(image) as painter, patch.object(v, "DrawOpaqueScene", side_effect = RuntimeError("capture fault")):
            try:
                v.DrawScene(painter, QtCore.QRectF(v.rect()), v.WorldToViewport(QtCore.QPointF()), v.zoom * v.basePixelsPerMillimeter)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Capture failure was hidden")
        assert not v.solidObjects and v.renderChanges.appearance == revision
        assert all(getattr(v, name) is value for name, value in zip(
            ("furnishingRenderers", "selectedFurnishingRenderers", "groupedFurnishingRenderers"), resources))
    print("PASS: explicit transparent capture resources, live ownership and exception isolation")


if __name__ == "__main__":
    Main()
