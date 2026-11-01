"""Alternating frozen/current drag updates, group setup and opening fitting."""
import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import sys
from time import perf_counter

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / 'planner-main'), str(root / 'checks')]
from PySide6 import QtCore, QtWidgets
from planner_app.models import Wall, Door, Furnishing, Label
from planner_app.viewport.widget import DrawingViewport
from fixtures.qt_drag_fitting_reference_20261030 import ReferenceViewport


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument('--output', type = Path, default = root / 'diagnostics/performance-drag-fitting-20261030/benchmark.json')
    args = parser.parse_args()
    app = QtWidgets.QApplication([])
    app.setStyle('Fusion')
    prototype = DrawingViewport()
    definitions = prototype.furnishingDefinitions
    point = QtCore.QPointF
    results = dict(python = platform.python_version(), qt = QtCore.qVersion(), platform = platform.platform(),
                   unit = 'milliseconds', repeats = 5, updatesPerSample = 5,
                   methodology = 'Alternate frozen/current viewports, discard one warmup; median five per-update sample averages. '
                       'Each scene has N walls, N furnishings and N labels, plus the stated openings. '
                       'Real UpdateInteraction for wall/small-group updates, no painting/properties; connections disabled. '
                       'Snapping disabled except in wall-snap cases. '
                       'Fit probes change one wall endpoint and retain the same immutable baseline. '
                       'No end-to-end display latency claim.', cases = [])
    for count, stride in ((128, 0), (128, 16), (512, 0), (512, 16), (512, 2), (1024, 0), (1024, 16), (1024, 2)):
        modes = ['wall', 'group-small', 'fit', 'group-start']
        if count >= 512 and stride == 16:
            modes.append('wall-snap')
        for mode in modes:
            views = []
            for cls in (ReferenceViewport, DrawingViewport):
                view = cls(furnishingDefinitions = definitions)
                view.snapEnabled, view.connectedEnabled = mode == 'wall-snap', False
                view.walls = [Wall(point(index * 6000, 0), point(index * 6000 + 4000, 0), 200) for index in range(count)]
                view.windows = [Door(wall, .2, .4) for wall in view.walls[::stride]] if stride else []
                view.furnishings = [Furnishing(definitions['desk'], point(index * 6000, 10000)) for index in range(count)]
                view.labels = [Label(point(index * 6000, 15000), 'Label') for index in range(count)]
                view.SetSelection([(view.walls[0], None)] if mode.startswith('wall') else
                                  [(view.furnishings[0], None), (view.labels[0], None)], notify = False)
                view.interactionBefore = view.CaptureState()
                view.dragStart, view.isDragging = point(400, 300), True
                if mode.startswith('wall'):
                    view.dragVertices = (point(view.walls[0].firstVertex), point(view.walls[0].secondVertex))
                else:
                    view.StartGroupDrag()
                views.append(view)
            samples = [[], []]
            for repeat in range(6):
                for variant in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                    view = views[variant]
                    start = perf_counter()
                    for frame in range(5):
                        if mode == 'fit':
                            view.walls[0].secondVertex += point(.37, .13)
                            view.FitWallOpenings(view.interactionBefore, validateFurnishings = False, validateScene = False)
                        elif mode == 'group-start':
                            view.groupDrag = False
                            view.StartGroupDrag()
                        else:
                            view.UpdateInteraction(view.dragStart + point(50 + repeat * 3 + frame, 50 + frame), QtCore.Qt.KeyboardModifier.NoModifier)
                    elapsed = (perf_counter() - start) * 1000 / 5
                    if repeat:
                        samples[variant].append(elapsed)
            row = dict(walls = count, furnishings = count, labels = count, openings = len(views[0].windows), mode = mode,
                       beforeMs = statistics.median(samples[0]), afterMs = statistics.median(samples[1]), samplesMs = samples)
            results['cases'].append(row)
            print(count, row['openings'], mode, round(row['beforeMs'], 3), round(row['afterMs'], 3), flush = True)
            for view in views:
                view.close()
                view.deleteLater()
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    prototype.close()
    args.output.parent.mkdir(parents = True, exist_ok = True)
    args.output.write_text(json.dumps(results, indent = 2) + '\n', encoding = 'utf-8')


if __name__ == '__main__':
    Main()
