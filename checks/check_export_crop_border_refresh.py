"""Mode/crop changes synchronize native border geometry before cached previews."""
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_export_preview_process import WaitForPreview
from planner_app.export_plan import RenderPlan
from planner_app.export_settings import ExportBorderSize
from planner_app.models import Wall


def Main():
    with ExampleWindow() as (main, folder):
        panel, view = main.exportPanel, main.viewport
        InstallScene(main, [Wall(QtCore.QPointF(-2500, 0), QtCore.QPointF(2500, 0), 200)])
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("pageSize", "A3")
        panel.SetScaleOption("architecturalScale", 50)
        panel.SetScaleOption("dpi", 96)
        panel.SetOverride("borderWidth", 1075)
        panel.SetBorder("Frame")
        panel.SetTitleBlockOption("enabled", True)
        overlay = view.exportOverlay
        count = 0
        for kind in ("PNG", "SVG"):
            panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
            for titlePosition in ("Right", "Bottom"):
                panel.SetTitleBlockOption("position", titlePosition)
                for mode in ("Digital", "Architectural", "Print", "Architectural", "Digital", "Print"):
                    panel.SetScaleOption("scaleMode", mode)
                    if mode != "Print":
                        if mode == "Architectural":
                            panel.SetScaleOption("architecturalScale", 125)
                        overlay.MoveEdge(1, overlay.bounds[0] + overlay.bounds[2] + 321.25,
                                         modifiers = QtCore.Qt.KeyboardModifier.AltModifier)
                    expected = ExportBorderSize(panel.overrides, panel.borderField.currentText())
                    assert overlay.borderSize == expected, (kind, mode, overlay.borderSize, expected)
                    view.grab()
                    assert not overlay.previewError, (kind, mode, overlay.previewError)
                    if mode == "Print":
                        layout = panel.PrintLayout()
                        assert overlay.PrintLayout() == layout, "Preview and output use different page drawing areas"
                        jobs = panel.ExportJobs(folder / ("pages." + kind.lower()), kind.lower())
                        assert len(jobs) == 1
                        result = RenderPlan(**jobs[0][1])
                        assert result is not None
                    # Crop/mode updates must not require an appearance toggle,
                    # nor invalidate a settled preview on every repaint.
                    key = overlay.printPageKey if mode == "Print" else overlay.snapshotKey if kind == "PNG" else overlay.svgKey
                    view.grab()
                    assert not overlay.previewError
                    assert key == (overlay.printPageKey if mode == "Print" else overlay.snapshotKey if kind == "PNG" else overlay.svgKey)
                    count += 1
        # Exercise the separate preview process too: cached worker failures
        # must never be produced by a stale border after changing modes/crops.
        os.environ.pop("PLANNER_SYNCHRONOUS_PREVIEW", None)
        try:
            for kind in ("PNG", "SVG"):
                panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
                for mode in ("Digital", "Architectural", "Print"):
                    panel.SetScaleOption("scaleMode", mode)
                    if mode != "Print":
                        overlay.MoveEdge(1, overlay.bounds[0] + overlay.bounds[2] + 187.5,
                                         modifiers = QtCore.Qt.KeyboardModifier.AltModifier)
                    WaitForPreview(view, kind.lower())
                    assert overlay.borderSize == ExportBorderSize(panel.overrides)
        finally:
            os.environ["PLANNER_SYNCHRONOUS_PREVIEW"] = "1"
    print("PASS:", count, "crop/mode transitions with different physical scales, A3 pages and both title positions; PNG/SVG previews match export without toggling settings")


if __name__ == "__main__":
    Main()
