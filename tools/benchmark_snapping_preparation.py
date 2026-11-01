"""Alternating frozen/current movement and resize snapping preparation."""
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
from planner_app.models import Wall, Furnishing
from planner_app.viewport.widget import DrawingViewport
from fixtures.qt_snapping_preparation_reference_20261030 import ReferenceViewport


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument('--output', type = Path, default = root / 'diagnostics/performance-snapping-20261030/benchmark.json')
    args = parser.parse_args()
    app = QtWidgets.QApplication([])
    app.setStyle('Fusion')
    point, modifier = QtCore.QPointF, QtCore.Qt.KeyboardModifier
    results = dict(python = platform.python_version(), qt = QtCore.qVersion(), platform = platform.platform(),
                   unit = 'milliseconds', repeats = 5, queriesPerSample = 5,
                   methodology = 'Alternate frozen/current viewports; discard one warmup; median five per-query averages. '
                       'Include footprint/control/midpoint collection, numeric conversion, lookup preparation and exact queries. '
                       'Change moving furnishing geometry each query; stationary geometry unchanged except in target-edit cases. '
                       'No viewport painting, properties, collision validation or pointer-event handling; not end-to-end input latency.', cases = [])
    for count in (16, 128, 512, 1024):
        views, sources = [], []
        for cls in (ReferenceViewport, DrawingViewport):
            view = cls()
            view.walls = [Wall(point(index % 32 * 2000, index // 32 * 2000),
                               point(index % 32 * 2000 + 1400, index // 32 * 2000), 200) for index in range(count)]
            source = Furnishing(view.furnishingDefinitions['desk'], point(-2000, -2000))
            view.furnishings = [source]
            view.SetSelection([(source, None)], notify = False)
            view.dragStart, view.isDragging = point(400, 300), True
            views.append(view)
            sources.append(source)
        modes = ['movement', 'constrained', 'resize-edge', 'resize-corner']
        if count == 1024:
            modes += ['group-64-anchors', 'target-edit', 'dense-alignment']
        for mode in modes:
            if mode == 'dense-alignment':
                for view in views:
                    view.walls = [Wall(point(index * 2000, 0), point(index * 2000 + 1400, 0), 200) for index in range(count)]
            samples = [[], []]
            for repeat in range(6):
                for variant in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                    view, source = views[variant], sources[variant]
                    state = dict(object = source, members = [], north = point(0, 1), center = point(-2000, -2000),
                                 width = 1200, length = 600, handle = ('resize', 'corner', (1, 1)) if mode == 'resize-corner' else ('resize', 'width', 1))
                    view.furnishingHandleDrag = state if mode.startswith('resize') else None
                    anchors = [point(-2000 + index % 8 * 137, -2000 + index // 8 * 71)
                               for index in range(64 if mode == 'group-64-anchors' else 4)]
                    if mode == 'dense-alignment':
                        anchors = [point(-2000 + index * 137, 0) for index in range(4)]
                    start = perf_counter()
                    for frame in range(5):
                        source.secondVertex += point(.13, .17)
                        if mode == 'target-edit':
                            view.walls[-1].firstVertex += point(.13, .17)
                        if mode.startswith('resize'):
                            view.SnapFurnishingResize(state, 1200 + frame * 3.7, 600 + frame * 1.3, modifier.NoModifier)
                        else:
                            targets = view.StairSnapTargets(source) + list(view.SnapVertices())
                            view.SnapObjectMovement(anchors, point(frame * 3.7, frame * 1.3),
                                modifier.ControlModifier if mode == 'constrained' else modifier.NoModifier, snapTargets = targets)
                    elapsed = (perf_counter() - start) * 1000 / 5
                    if repeat:
                        samples[variant].append(elapsed)
            row = dict(walls = count, mode = mode, beforeMs = statistics.median(samples[0]), afterMs = statistics.median(samples[1]), samplesMs = samples)
            results['cases'].append(row)
            print(count, mode, round(row['beforeMs'], 3), round(row['afterMs'], 3), flush = True)
        for view in views:
            view.close()
    args.output.parent.mkdir(parents = True, exist_ok = True)
    args.output.write_text(json.dumps(results, indent = 2) + '\n', encoding = 'utf-8')


if __name__ == '__main__':
    Main()
