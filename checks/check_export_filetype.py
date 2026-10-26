"""Export file types persist per project and participate in export undo."""
import copy
import os
from pathlib import Path
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from fixtures.parity_examples import ExampleWindow
from planner_app.project_codec import DecodeProject


def Main():
    with ExampleWindow() as (main, folder):
        panel = main.exportPanel
        clean = main.BuildProjectData(includeHistory = False)
        for kind in ("SVG", "PNG_OPTIMIZED", "PNG"):
            main.sidebarTabs.setCurrentWidget(panel)
            previous = panel.typeField.currentData()
            panel.typeField.setCurrentIndex(panel.typeField.findData(kind))
            main.RefreshProjectDirty()
            assert panel.overrides["fileType"] == kind and main.projectDirty
            if previous != kind:
                panel.UndoExport()
                assert panel.typeField.currentData() == previous
                panel.RedoExport()
                assert panel.typeField.currentData() == kind
            path = folder / (kind + ".plan")
            assert main.SaveProject(path)
            main.ApplyProject(DecodeProject(clean, main.viewport.furnishingDefinitions), None)
            assert panel.typeField.currentData() == "PNG" and "fileType" not in panel.overrides
            assert main.OpenProject(path)
            assert panel.typeField.currentData() == kind
            main.sidebarTabs.setCurrentWidget(panel)
            assert main.viewport.exportOverlay.outputFormat == ("svg" if kind == "SVG" else "png")
            assert panel.OutputPath().suffix == (".svg" if kind == "SVG" else ".png")
        for kind in ("JPEG", "", None, 1):
            invalid = copy.deepcopy(clean)
            invalid["settings"]["exportSettings"] = {"fileType": kind}
            try:
                DecodeProject(invalid, main.viewport.furnishingDefinitions)
            except ValueError:
                pass
            else:
                raise AssertionError("Invalid export file type accepted")
    print("PASS: export file-type persistence, project isolation, undo/redo and validation")


if __name__ == "__main__":
    Main()
