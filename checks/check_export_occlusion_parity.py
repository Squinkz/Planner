"""Dense furnished scenes retain pixels while skipping irrelevant overlap work."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow
from planner_app.graphics.theme import ApplyApplicationTheme
from planner_app.graphics.object_composite import ObjectPaintEngine
from planner_app.project_codec import DecodeProject
from fixtures.object_composite_reference_20261019 import ObjectPaintEngine as ReferencePaintEngine


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    main = MainWindow()
    path = root / "checks/fixtures/plans/dense_furnishings.plan"
    main.ApplyProject(DecodeProject(json.loads(path.read_text(encoding = "utf-8")), main.viewport.furnishingDefinitions, validatePlacement = False), path)
    v, panel = main.viewport, main.exportPanel
    main.sidebarTabs.setCurrentWidget(panel)
    panel.scaleField.setValue(750)
    panel.SetOverride("texture", None)
    panel.SetOverride("vignetteEnabled", False)
    panel.SetOverride("visibility", True, "Furnishings")
    panel.solidObjectsField.setChecked(False)
    overlay = v.exportOverlay
    coverage = QtCore.QRectF(*overlay.bounds)
    for sampling in (.07, .17):
        images = []
        for replay in (ReferencePaintEngine.Replay, ObjectPaintEngine.Replay):
            with patch.object(ObjectPaintEngine, "Replay", replay):
                if overlay.snapshotViewport is not None:
                    overlay.snapshotViewport.objectClipCache.clear()
                images.append(overlay.CaptureRaster(coverage, sampling, "snapshot"))
        first, second = bytes(images[0].constBits()), bytes(images[1].constBits())
        changed = [abs(a - b) for a, b in zip(first, second) if a != b]
        # Culling masks outside a conservative ink envelope avoids global curve
        # unions. Qt can quantize the remaining curved clip edges differently;
        # allow sparse antialias changes, not changed shapes or filled regions.
        assert len(changed) < len(first) * .001, (sampling, len(changed), len(first))
        assert sum(changed) < len(first) * .025, (sampling, sum(changed), len(first))
    main.MarkProjectClean()
    main.close()


if __name__ == "__main__":
    Main()
