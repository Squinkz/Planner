"""Export navigation reuses exact artwork bounds without hiding scene edits."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.export_bounds import AutomaticBounds
from planner_app.models import Wall, Furnishing


def Main():
    with ExampleWindow() as (main, folder):
        v, panel = main.viewport, main.exportPanel
        wall = Wall(QtCore.QPointF(0, 0), QtCore.QPointF(5000, 0), 200)
        furnishing = Furnishing(v.furnishingDefinitions["washer"], QtCore.QPointF(2000, 2000))
        InstallScene(main, [wall, furnishing])
        main.sidebarTabs.setCurrentWidget(panel)
        overlay = v.exportOverlay
        for mode in ("Digital", "Architectural", "Print"):
            panel.SetScaleOption("scaleMode", mode)
            for kind in ("PNG", "SVG"):
                panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
                v.grab()
                baseline = v.grab().toImage()
                with patch.object(overlay, "AutomaticModelBounds", side_effect = lambda: AutomaticBounds(v)):
                    assert v.grab().toImage() == baseline, "Cached bounds changed preview pixels"
                overlay.AutomaticModelBounds()
                with patch("planner_app.viewport.export_bounds.AutomaticBounds", wraps = AutomaticBounds) as calculate:
                    for index in range(3):
                        v.isPanning = True
                        v.panOffset += QtCore.QPointF(4, 0)
                        v.grab()
                        v.isPanning = False
                        overlay.AutomaticModelBounds()
                    panel.SetTitleBlockOption("comments", "Updated comments")
                    panel.SetOverride("borderSize", panel.overrides.get("borderSize", 56) + 1)
                    v.grab()
                    assert not calculate.called, "Navigation or frame edits recalculated model bounds"
                assert not overlay.previewError, overlay.previewError
        # Compare against a fresh calculation after mutable geometry, visibility,
        # artwork, font and complete-project replacement changes.
        changedFont = QtGui.QFont(v.font())
        changedFont.setPointSizeF(max(1, changedFont.pointSizeF()) + 2)
        for mutate in (
                lambda: wall.secondVertex.setX(12000),
                lambda: setattr(furnishing, "flipHorizontal", not furnishing.flipHorizontal),
                lambda: v.visibility.__setitem__("Furnishings", False),
                lambda: setattr(wall, "width", 800),
                lambda: v.setFont(changedFont),
                lambda: InstallScene(main, [Wall(QtCore.QPointF(-9000, 0), QtCore.QPointF(-7000, 0), 100)])):
            mutate()
            assert overlay.AutomaticModelBounds() == AutomaticBounds(v), "Scene edit retained stale model bounds"
        InstallScene(main, [])
        for attempt in range(2):
            try:
                overlay.AutomaticModelBounds()
            except ValueError:
                pass
            else:
                raise AssertionError("Empty scene reused previous nonempty bounds")
        InstallScene(main, [Wall(QtCore.QPointF(0, 0), QtCore.QPointF(1000, 0), 100)])
        assert overlay.AutomaticModelBounds() == AutomaticBounds(v)
    print("Bounds reuse, exact PNG/SVG pixels and scene invalidation passed")


if __name__ == "__main__":
    Main()
