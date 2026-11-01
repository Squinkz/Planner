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
from planner_app.graphics.compositing import LoadNumPy
from fixtures.object_composite_reference_20261019 import ObjectPaintEngine as ReferencePaintEngine


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    main = MainWindow()
    path = root / "checks/fixtures/plans/dense_furnishings.plan"
    main.ApplyProject(DecodeProject(json.loads(path.read_text(encoding = "utf-8")), main.viewport.furnishingDefinitions, validatePlacement = False), path)
    v, panel = main.viewport, main.exportPanel
    panel.overrides["scaleMode"] = "Digital"
    main.sidebarTabs.setCurrentWidget(panel)
    panel.scaleField.setValue(750)
    panel.SetOverride("texture", None)
    panel.SetOverride("vignetteEnabled", False)
    panel.SetOverride("visibility", True, "Furnishings")
    panel.solidObjectsField.setChecked(False)
    overlay = v.exportOverlay
    coverage = QtCore.QRectF(*overlay.bounds)
    np = LoadNumPy()
    for sampling in (.07, .17):
        images = []
        for replay in (ReferencePaintEngine.Replay, ObjectPaintEngine.Replay):
            with patch.object(ObjectPaintEngine, "Replay", replay):
                if overlay.snapshotViewport is not None:
                    overlay.snapshotViewport.objectClipCache.clear()
                images.append(overlay.CaptureRaster(coverage, sampling, "snapshot"))
        first, second = bytes(images[0].constBits()), bytes(images[1].constBits())
        # Quantized curved clips can differ at low sampling. In addition to
        # tight aggregate limits, require every changed pixel to remain in a
        # one-pixel neighborhood of an edge in the frozen reference. A missing
        # object or new filled region cannot pass by occupying a small area.
        width, height = images[0].width(), images[0].height()
        reference = np.frombuffer(first, dtype = np.uint8).reshape(height, width, 4).astype(np.int16)
        current = np.frombuffer(second, dtype = np.uint8).reshape(height, width, 4)
        difference = np.abs(reference - current)
        changedCount, totalDifference = int(np.count_nonzero(difference)), int(difference.sum())
        edges = np.zeros((height, width), dtype = bool)
        horizontal = np.any(np.abs(reference[:, 1:, :3] - reference[:, :-1, :3]) > 2, axis = 2)
        vertical = np.any(np.abs(reference[1:, :, :3] - reference[:-1, :, :3]) > 2, axis = 2)
        edges[:, 1:] |= horizontal
        edges[:, :-1] |= horizontal
        edges[1:, :] |= vertical
        edges[:-1, :] |= vertical
        padded = np.pad(edges, 1)
        edgeBand = np.logical_or.reduce([padded[y:y + height, x:x + width] for y in range(3) for x in range(3)])
        different = np.any(reference != current, axis = 2)
        assert not np.any(different & ~edgeBand), (sampling, "Change escaped the frozen ink edges")
        assert changedCount < len(first) * .002, (sampling, changedCount, len(first))
        assert totalDifference < len(first) * .05, (sampling, totalDifference, len(first))
    main.MarkProjectClean()
    main.close()


if __name__ == "__main__":
    Main()
