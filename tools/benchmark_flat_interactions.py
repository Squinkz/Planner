"""Frozen/current real-project input plus one synchronous viewport render."""
import argparse
from contextlib import ExitStack
import gc
import json
import os
from pathlib import Path
import platform
from statistics import median
import sys
from types import MethodType
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks"), str(root / "tools")]
from PySide6 import QtCore, QtWidgets
from profile_flat_interactions import LoadFlat, BeginEndpoint, Step
from fixtures.parity_examples import ExampleWindow
from fixtures.flat_view_reference_20261031 import ReferenceViewport
from fixtures import flat_renderers_reference_20261031 as oldRenderers
from planner_app.graphics import furnishings
from check_drag_fitting_preparation import Snapshot

folder = root / "diagnostics/performance-flat-20261031"


def UseBaseline(view):
    for name in ("SceneRenderValueKey", "EditSceneSnapshot", "JoinedObjectBounds", "JoinedObjectsOverlap"):
        setattr(view, name, MethodType(ReferenceViewport.__dict__[name], view))
    for name in ("furnishingRenderers", "selectedFurnishingRenderers"):
        current = getattr(view, name)
        previous = oldRenderers.FurnishingRendererMap(current.definitions, selected = current.selected,
            lineWidth = current.lineWidth, solidBackground = current.solidBackground, colors = current.colors,
            selectionColor = current.selectionColor, excludeErrors = current.excludeErrors)
        previous.changed = current.changed
        object.__setattr__(view, name, previous)
    view.renderChanges.Bump("appearance")
    view.ClearGeometryCaches()


def PrepareCase(main, case, baseline, width = 1500, height = 900):
    main.hide()
    view = LoadFlat(main)
    main.hide()
    view.setFixedSize(width, height)
    main.resize(width + 450, height + 100)
    if baseline:
        UseBaseline(view)
    if case == "drag":
        wall = next(wall for wall in view.walls if wall.objectId == 256)
        BeginEndpoint(view, wall, 1)
    elif case == "zoom-deep":
        for frame in range(8):
            view.ZoomBy(1 / 1.15, view.DrawingRect().center())
    return view


def Main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices = ("drag", "zoom-in", "zoom-out", "zoom-deep"), required = True)
    parser.add_argument("--width", type = int, default = 1500)
    parser.add_argument("--height", type = int, default = 900)
    args = parser.parse_args()
    gcEnabled = gc.isenabled()
    gc.disable()
    try:
        with ExitStack() as stack:
            windows = [stack.enter_context(ExampleWindow())[0] for variant in range(2)]
            for main in windows:
                main.hide()
            views = [PrepareCase(main, args.case, variant == 0, args.width, args.height) for variant, main in enumerate(windows)]
            samples = [[], []]
            case = "zoom-out" if args.case == "zoom-deep" else args.case
            for frame in range(11):
                for variant in ((0, 1) if frame % 2 == 0 else (1, 0)):
                    row = Step(views[variant], case, frame)
                    if frame >= 2:
                        samples[variant].append(row)
            assert Snapshot(views[0]) == Snapshot(views[1]), "Gesture/model state changed"
            assert views[0].zoom == views[1].zoom and views[0].panOffset == views[1].panOffset
            assert views[0].grab().toImage() == views[1].grab().toImage(), "Final viewport pixels changed"
            counts = []
            for variant, module in enumerate((oldRenderers, furnishings)):
                with patch.object(module, "FurnishingRenderer", wraps = module.FurnishingRenderer) as factory:
                    Step(views[variant], case, 11)
                cache = views[variant].furnishingRenderers
                counts.append(dict(baseRendererConstructions = factory.call_count, retainedEstimate = cache.byteCount,
                                   limitBytes = cache.byteLimit, entries = len(cache)))
                assert cache.byteCount <= cache.byteLimit and len(cache) <= cache.entryLimit
            result = dict(case = args.case, viewportSize = [args.width, args.height],
                python = platform.python_version(), qt = QtCore.qVersion(), devicePixelRatio = views[0].devicePixelRatioF(),
                methodology = "Original flat.plan and saved settings in independent real MainWindows, hidden to avoid incidental double paints. "
                    "Endpoint UpdateInteraction or wheelEvent, connected UI signals, processEvents, then one synchronous viewport grab. "
                    "Two warmups, nine alternating unprofiled samples, cyclic GC disabled equally. Deep zoom begins after eight outward ticks; "
                    "all zoom ticks then continue in one direction. Additional factory counts are outside timings. Frozen pre-change bookkeeping and native renderer maps; "
                    "shared current interaction/rendering infrastructure. Exact final pixels/model state/zoom/pan compared. Not display latency.",
                medians = [{key: median(row[key] for row in rows) for key in rows[0]} for rows in samples],
                samples = samples, factoryProbe = counts, finalZoom = views[0].zoom)
            for view in views:
                view.CancelInteraction()
            (folder / f"benchmark-{args.case}.json").write_text(json.dumps(result, indent = 2), encoding = "utf-8")
            print(json.dumps({key: value for key, value in result.items() if key not in ("samples", "methodology")}, indent = 2))
    finally:
        if gcEnabled:
            gc.enable()


if __name__ == "__main__":
    Main()
