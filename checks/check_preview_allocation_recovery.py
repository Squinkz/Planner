"""Recover a transient texture-preview allocation failure in the real worker."""
import json
import os
from pathlib import Path
import sys
from time import perf_counter
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtTest
from fixtures.parity_examples import ExampleWindow, InstallScene
from check_export_preview_process import WaitForPreview
from planner_app.export_plan import RenderPlan
from planner_app.models import Wall


def Main():
    with ExampleWindow() as (main, folder):
        panel, v = main.exportPanel, main.viewport
        InstallScene(main, [Wall(QtCore.QPointF(1000, 1000), QtCore.QPointF(5000, 3500), 200)])
        main.sidebarTabs.setCurrentWidget(panel)
        panel.SetScaleOption("scaleMode", "Print")
        panel.SetScaleOption("dpi", 96)
        panel.SetOverride("titleBlock", dict(enabled = True, logoMode = "None"))
        panel.SetOverride("texture", "wrinkled_paper_t1.33_5_5_5_5.png")
        overlay = v.exportOverlay
        width, height = panel.PrintLayout()["paperTile"]
        overlay.bounds = (*overlay.pageOrigin, width, height)
        panel.SetBounds(overlay.bounds)
        faultPath, attemptsPath = folder / "fault.json", folder / "attempts.jsonl"
        faultPath.write_text(json.dumps(dict(mode = "none", calls = 0)))
        # Exercise the ordinary worker protocol with an injected allocation
        # failure, without exhausting machine memory or changing production code.
        entry = folder / "worker.py"
        entry.write_text(f"""import json, sys
from pathlib import Path
sys.path.insert(0, {str(root / 'planner-main')!r})
from planner_app import export_plan, export_preview_worker
from planner_app.graphics import compositing, title_block
faultPath = Path({str(faultPath)!r})
attemptsPath = Path({str(attemptsPath)!r})
originalBitmap = title_block.RenderTitleBlockBitmap
originalRender = export_plan.RenderPlan
def Bitmap(*args, **kwargs):
    fault = json.loads(faultPath.read_text())
    if fault['mode'] != 'none':
        fault['calls'] += 1
        faultPath.write_text(json.dumps(fault))
        if fault['mode'] == 'always' or fault['calls'] == 1:
            if fault.get('memoryError'):
                raise MemoryError('Injected texture allocation failure')
            raise ValueError('Could not allocate the title block bitmap.')
    return originalBitmap(*args, **kwargs)
def Render(*args, **kwargs):
    cache = kwargs['sceneCache']
    with attemptsPath.open('a') as output:
        output.write(json.dumps(dict(cache = id(cache), prepared = cache.viewport is not None,
            textureCache = compositing.NormalTextureLookup.cache_info().currsize)) + '\\n')
    return originalRender(*args, **kwargs)
title_block.RenderTitleBlockBitmap = Bitmap
export_plan.RenderPlan = Render
export_preview_worker.Main()
""", encoding = "utf-8")
        originalStart = QtCore.QProcess.start

        def Start(process, program, arguments, *args):
            if "--preview-worker" in arguments:
                arguments = [str(entry)]
            return originalStart(process, program, arguments, *args)

        os.environ.pop("PLANNER_SYNCHRONOUS_PREVIEW", None)
        try:
            with patch.object(QtCore.QProcess, "start", Start):
                WaitForPreview(v, "png")
                worker = overlay.previewProcess
                pid = worker.process.processId()
                for memoryError, angle in ((False, 37), (True, 74)):
                    attemptsPath.write_text("")
                    faultPath.write_text(json.dumps(dict(mode = "once", calls = 0, memoryError = memoryError)))
                    panel.SetOverride("textureAngle", angle)
                    WaitForPreview(v, "png")
                    assert worker.process.processId() == pid, "Recovery restarted the worker"
                    attempts = [json.loads(line) for line in attemptsPath.read_text().splitlines()]
                    assert len(attempts) >= 2, attempts
                    assert attempts[0]["prepared"] and attempts[0]["textureCache"], attempts
                    assert not attempts[1]["prepared"] and not attempts[1]["textureCache"], attempts
                    assert attempts[0]["cache"] != attempts[1]["cache"], attempts
                    assert json.loads(faultPath.read_text())["calls"] == 2, "Transient failure was not retried exactly once"
                    arguments = panel.ExportJobs(folder / "page.png", "png")[0][1]
                    assert next(iter(overlay.printPageCache.values())) == RenderPlan(**arguments)
                    assert v.rasterCacheBudget.RetainedBytes() <= v.viewportRasterByteLimit
                # A persistent allocation failure must stop after one retry;
                # the next valid settings must still recover in this process.
                faultPath.write_text(json.dumps(dict(mode = "always", calls = 0)))
                panel.SetOverride("textureAngle", 111)
                deadline = perf_counter() + 10
                while not overlay.previewError and perf_counter() < deadline:
                    QtTest.QTest.qWait(10)
                    v.grab()
                assert overlay.previewError == "Could not allocate the title block bitmap.", overlay.previewError
                assert json.loads(faultPath.read_text())["calls"] == 2, "Persistent failure retried without a bound"
                faultPath.write_text(json.dumps(dict(mode = "none", calls = 0)))
                panel.SetOverride("textureAngle", 112)
                overlay.previewError = ""
                WaitForPreview(v, "png")
                assert worker.process.processId() == pid
                assert overlay.titleBlock["enabled"] and v.isVisible()
        finally:
            if overlay.previewProcess is not None:
                overlay.previewProcess.Close()
            os.environ["PLANNER_SYNCHRONOUS_PREVIEW"] = "1"
    print("Real worker retries transient allocation failures once, frees caches, preserves pixels and reports persistent failures")


if __name__ == "__main__":
    Main()
