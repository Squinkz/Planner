"""Released dialogs/documents, bounded native artwork, export batches and snapshots."""
import gc
import base64
import json
import os
from pathlib import Path
import sys
import weakref
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from shiboken6 import isValid
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.models import Furnishing
from planner_app.project_codec import DecodeProject
from planner_app.graphics.furnishings import FurnishingRenderer, FurnishingRendererMap, FurnishingRendererCache
from planner_app.graphics import palette
from planner_app.history_edits import RetainedBytes
from planner_app.ui.furnishing_quick_search import FurnishingQuickSearch
from planner_app.viewport.widget import DrawingViewport
from planner_app.export_plan import RenderPlan
from planner_app.export_worker import RunExportWorker, ExportJobEncoder


def Main():
    with ExampleWindow() as (main, folder):
        v, panel = main.viewport, main.exportPanel
        clean = main.BuildProjectData()
        references = []
        for accept in (False, False, False, True):
            objects = [Furnishing(v.furnishingDefinitions["desk"], QtCore.QPointF(index * 2000, 0)) for index in range(2)]
            references.extend(weakref.ref(obj) for obj in objects)
            InstallScene(main, objects)
            def Dismiss():
                dialog = next(widget for widget in QtWidgets.QApplication.topLevelWidgets()
                              if isinstance(widget, QtWidgets.QDialog) and widget.windowTitle() == "Create Furnishing")
                if accept:
                    dialog.findChild(QtWidgets.QLineEdit, "furnishingName").setText("Test compound")
                    dialog.findChild(QtWidgets.QDialogButtonBox).button(QtWidgets.QDialogButtonBox.StandardButton.Save).click()
                else:
                    dialog.reject()
            QtCore.QTimer.singleShot(0, Dismiss)
            with patch.object(main, "SaveUserFurnishing", return_value = v.furnishingDefinitions["desk"]):
                main.CreateFurnishingFromSelection(objects)
            del objects
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
            assert not any(dialog.windowTitle() == "Create Furnishing" for dialog in main.findChildren(QtWidgets.QDialog))
        main.ApplyProject(DecodeProject(clean, v.furnishingDefinitions), None)
        v.grab()
        gc.collect()
        assert not any(reference() is not None for reference in references)

        # An ordinary blank replacement also releases both native renderer maps.
        renderer = v.furnishingRenderers["desk"]
        selected = v.selectedFurnishingRenderers["desk"]
        main.ApplyProject(DecodeProject(clean, v.furnishingDefinitions), None)
        assert not v.furnishingRenderers and not v.selectedFurnishingRenderers and not v.groupedFurnishingRenderers
        gc.collect()
        # Holding a renderer externally must keep it usable until that owner ends.
        assert isValid(renderer) and isValid(selected)
        del renderer, selected
        oldModels, oldRenderers = [], []
        for index in range(12):
            obj = Furnishing(v.furnishingDefinitions["desk"], QtCore.QPointF(index * 10, 0))
            InstallScene(main, [obj])
            v.grab()
            oldModels.append(weakref.ref(obj))
            oldRenderers.append(weakref.ref(v.furnishingRenderers["desk"]))
            del obj
            main.ApplyProject(DecodeProject(clean, v.furnishingDefinitions), None)
            v.grab()
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        gc.collect()
        assert not any(reference() is not None for reference in oldModels + oldRenderers)

        oldDefinition = dict(v.furnishingDefinitions["desk"], key = "old_embedded", name = "Old embedded")
        v.projectFurnishingDefinitions = {"old_embedded": oldDefinition}
        v.furnishingDefinitions = dict(v.furnishingDefinitions, old_embedded = oldDefinition)
        main.RefreshFurnishingRenderers()
        main.BuildFurnishTab(refresh = True)
        main.furnishingQuickSearch = FurnishingQuickSearch(main)
        main.furnishingQuickSearch.OpenAt(QtCore.QPointF(400, 300))
        main.furnishingQuickSearch.hide()
        assert any(main.furnishingQuickSearch.results.item(index).definition is oldDefinition
                   for index in range(main.furnishingQuickSearch.results.count()))
        main.ApplyProject(DecodeProject(clean, v.localFurnishingDefinitions), None)
        assert not main.furnishingQuickSearch.results.count() and main.furnishingQuickSearch.preview is None
        assert "old_embedded" not in v.furnishingDefinitions

        source = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="white" stroke="black"/></svg>'
        definitions = {str(index): dict(key = str(index), graphicData = source, width = 100, length = 100) for index in range(6)}
        renderers = FurnishingRendererMap(definitions)
        renderers.entryLimit = 2
        retired = renderers["0"]
        reference = weakref.ref(retired)
        renderers["1"]
        assert renderers.get("0") is retired
        renderers["2"]
        assert "1" not in renderers and "0" in renderers
        renderers["3"]
        assert "0" not in renderers
        del retired
        gc.collect()
        assert reference() is None, "Evicted native artwork remains retained"
        renderers.byteLimit = 1
        uncached = renderers["4"]
        assert uncached.isValid() and "4" not in renderers
        renderers.clear()
        assert renderers.byteCount == 0 and not renderers.costs
        transparent = FurnishingRendererMap(definitions, solidBackground = False)
        transparent.entryLimit = 2
        solids = transparent.Copy(solidBackground = True)
        for key in definitions:
            solids[key]
            assert len(solids) <= 2 and len(transparent.solidVariants) <= 2
        grouped = FurnishingRendererCache()
        grouped.entryLimit = 2
        for key in definitions:
            grouped[key] = uncached
        assert len(grouped) == 2
        grouped.update({key: uncached for key in definitions})
        assert len(grouped) == 2 and len(grouped.costs) == 2
        image = QtGui.QImage(4, 4, QtGui.QImage.Format.Format_ARGB32)
        image.fill("red")
        buffer = QtCore.QBuffer()
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        assert image.save(buffer, "PNG")
        encoded = base64.b64encode(bytes(buffer.data())).decode("ascii")
        wrapped = " ".join(encoded[index:index + 8] for index in range(0, len(encoded), 8))
        rasterSource = ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 4 4">'
                        '<image width="4" height="4" xlink:href="data:image/png;base64,' + wrapped + '"/></svg>').encode()
        rasterRenderer = FurnishingRenderer(rasterSource)
        assert rasterRenderer.isValid() and rasterRenderer.retainedByteEstimate >= len(rasterSource) * 4 + 4 * 4 * 8

        # Byte pruning preserves recent undo/redo, branches and single gestures.
        panel.ResetExportHistory()
        panel.exportHistoryByteBudget = 20000
        for index in range(8):
            panel.overrides["titleBlock"] = dict(logo = str(index) * 6000)
            panel.RecordExportHistory()
            assert RetainedBytes((panel.exportUndoHistory, panel.exportRedoHistory)) <= panel.exportHistoryByteBudget
        assert 0 < len(panel.exportUndoHistory) < 8
        expected = panel.ExportHistoryState()
        panel.UndoExport()
        panel.RedoExport()
        assert panel.ExportHistoryState() == expected
        panel.BeginExportGesture()
        panel.overrides["titleBlock"] = dict(logo = "x" * 25000)
        panel.EndExportGesture()
        assert not panel.exportUndoHistory and not panel.exportRedoHistory
        panel.overrides.clear()
        panel.ResetExportHistory()
        panel.exportHistoryByteBudget = 16 * 1024 * 1024

        main.sidebarTabs.setCurrentWidget(panel)
        arguments = panel.RenderArguments("svg")
        arguments.update(bounds = (-1000, -1000, 2000, 2000), scale = 40)
        jobPath = folder / "batch.json"
        pages = [dict(render = {}, stagingPath = str(folder / f"page-{index}.svg")) for index in range(8)]
        job = dict(render = arguments, optimized = False, stagingPath = pages[0]["stagingPath"], pages = pages,
                   style = QtWidgets.QApplication.style().objectName(), uiTheme = "Dark UI", canvasTheme = "Dark Canvas",
                   colors = dict(palette.themeColors), labelFont = palette.labelFont)
        jobPath.write_text(json.dumps(job, cls = ExportJobEncoder), encoding = "utf-8")
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        def RenderPage(**options):
            assert not any(isinstance(widget, DrawingViewport) for widget in QtWidgets.QApplication.topLevelWidgets()), "Previous SVG scene survived to the next page"
            return RenderPlan(**options)
        with patch("planner_app.export_plan.RenderPlan", side_effect = RenderPage) as render:
            assert RunExportWorker(jobPath) == 0
            assert render.call_count == 8
        assert not any(isinstance(widget, DrawingViewport) for widget in QtWidgets.QApplication.topLevelWidgets())
        expected = RenderPlan(**arguments)
        assert all(Path(page["stagingPath"]).read_bytes() == expected for page in pages)
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)

        # Drive the real dialog/process through the public export entry point.
        panel.overrides.update(bounds = [-1000, -1000, 2000, 2000], scale = 40)
        panel.folderField.setText(str(folder))
        panel.fileNameField.setText("single-snapshot")
        with patch.object(panel, "ExportJobs", wraps = panel.ExportJobs) as prepare:
            panel.Export()
            assert prepare.call_count == 1, "GUI export encoded its scene twice"
        # Print exports can number their only page. This check concerns one
        # prepared scene and a valid output, rather than the naming convention.
        outputs = list(folder.glob("single-snapshot*.png"))
        assert len(outputs) == 1 and not QtGui.QImage(str(outputs[0])).isNull()
    print("PASS: dialog/model lifetimes, document replacement, native cache eviction, export memory bounds and one prepared snapshot")


if __name__ == "__main__":
    Main()
