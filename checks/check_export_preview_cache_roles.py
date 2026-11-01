"""Real worker keeps native pages and sampled context preparations warm."""
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
from planner_app.models import Wall, Furnishing
from planner_app.export_plan import RenderPlan
from planner_app import export_preview


def Main():
    with ExampleWindow() as (main, folder):
        folder = Path(folder)
        trace = folder / "preparations.jsonl"
        # The shim records real cache/viewport ownership; all rendering still
        # runs through the production worker in its separate Qt process.
        (folder / "main.py").write_text(f'''
import os, sys, json
from pathlib import Path
sys.path.insert(0, {str(root / "planner-main")!r})
# Match the real worker's stable application directory. A Windows venv child
# may briefly outlive its launcher and must not hold the test folder as its cwd.
os.chdir({str(root / "planner-main")!r})
from planner_app import export_plan
original = export_plan.RenderPlan
def Render(*args, **kwargs):
    cache = kwargs["sceneCache"]
    previous = id(cache.viewport) if cache.viewport is not None else None
    result = original(*args, **kwargs)
    with Path({str(trace)!r}).open("a", encoding = "utf-8") as output:
        output.write(json.dumps(dict(cache = id(cache), before = previous, after = id(cache.viewport))) + "\\n")
    return result
export_plan.RenderPlan = Render
from planner_app.export_preview_worker import Main
Main()
''', encoding = "utf-8")
        v, panel = main.viewport, main.exportPanel
        InstallScene(main, [Wall(QtCore.QPointF(0, 0), QtCore.QPointF(6000, 0), 200),
                            Furnishing(v.furnishingDefinitions["washer"], QtCore.QPointF(2000, 1500))])
        main.sidebarTabs.setCurrentWidget(panel)
        render = panel.RenderArguments("png", preview = True)
        render.update(bounds = (-500, -1000, 8000, 5000), pageSize = None, scale = 80,
                      architecturalScale = None, dpi = None, border = "None", titleBlock = {}, scaleBar = {})
        worker = export_preview.ExportPreviewProcess(v.exportOverlay)
        try:
            with patch.object(export_preview, "appDirectory", folder):
                for index in range(3):
                    for slot, sampling in (("page-probe", 1), ("snapshot", .3)):
                        arguments = dict(render, rasterSampling = sampling)
                        key = (index, slot)
                        assert worker.Request(slot, key, lambda: arguments, "png") is None
                        deadline = perf_counter() + 10
                        while worker.current is not None and perf_counter() < deadline:
                            QtTest.QTest.qWait(5)
                        assert worker.current is None, "Worker did not settle"
                        actual = worker.Request(slot, key, lambda: arguments, "png")
                        assert actual == RenderPlan(**arguments), "Role cache changed raster pixels"
                records = [json.loads(line) for line in trace.read_text(encoding = "utf-8").splitlines()]
                assert len(records) == 6
                assert records[0]["cache"] != records[1]["cache"], "Native pages and sampled context share one preparation"
                for index, record in enumerate(records[2:], 2):
                    assert record["cache"] == records[index % 2]["cache"]
                    assert record["before"] == record["after"] == records[index % 2]["after"], "Alternating roles rebuilt a prepared scene"
        finally:
            worker.Close()
        assert not worker.results and not worker.queue and worker.temporary is None
    print("Separate page/context worker scenes retain preparation across alternation; all six images match direct raster output")


if __name__ == "__main__":
    Main()
