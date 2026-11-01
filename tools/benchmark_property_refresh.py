"""Alternating frozen/current synchronous property refresh benchmarks."""
import argparse
from contextlib import nullcontext
import json
import os
from pathlib import Path
import platform
import statistics
import sys
from time import perf_counter
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / 'planner-main'), str(root / 'checks')]
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow
from fixtures.qt_properties_reference_20261030 import ReferenceProperties, ReferenceScene, ReferenceSceneObject
from planner_app.models import Wall, Stair, Railing, Furnishing
from planner_app.scene_changes import SceneObject


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument('--output', type = Path, default = root / 'diagnostics/performance-properties-20261030/benchmark.json')
    args = parser.parse_args()
    results = dict(python = platform.python_version(), qt = QtCore.qVersion(), platform = platform.platform(),
                   unit = 'milliseconds', repeats = 7, updatesPerSample = 20,
                   methodology = 'One isolated main window; alternate frozen/current handlers on the actual selectionChanged signal. '
                       'Change selected geometry each update. Discard one warmup; median seven per-update sample averages. '
                       'Measure synchronous refresh with no event-loop flush, and separately refresh plus explicit properties-panel rendering. '
                       'Exclude viewport painting, input handling and snapping; not end-to-end latency.', refresh = [], panel = [])
    point = QtCore.QPointF
    with ExampleWindow() as (main, folder):
        v = main.viewport
        v.performanceTimer.stop()
        v.performanceLabel.hide()
        v.showMeasurements = v.showTips = False
        current = main.RefreshProperties
        reference = ReferenceProperties.RefreshProperties.__get__(main)
        v.selectionChanged.disconnect(current)
        for count in (128, 1024, 4096):
            for kind in ('wall', 'vertex', 'furnishing', 'stair', 'railing'):
                v.walls = [Wall(point(10000 + index * 2000, 10000), point(11000 + index * 2000, 10000), 200) for index in range(count)]
                selected = (Furnishing(v.furnishingDefinitions['desk']) if kind == 'furnishing' else
                            Stair(point(), point(0, 3000), 1000) if kind == 'stair' else
                            Railing(point(), point(3000, 0), 100) if kind == 'railing' else v.walls[0])
                v.furnishings = [selected] if kind == 'furnishing' else []
                if kind in ('stair', 'railing'):
                    v.walls.append(selected)
                v.SetSelection([(selected, 0 if kind == 'vertex' else None)], notify = False)
                current()
                original = point(selected.secondVertex)
                image = QtGui.QImage(main.propertiesScrollArea.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                for operation in (('refresh', 'panel') if count == 1024 else ('refresh',)):
                    samples = [[], []]
                    for repeat in range(8):
                        for variant in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                            handler = reference if variant == 0 else current
                            context = (patch.object(v, 'EnsureObjectIds', ReferenceScene.EnsureObjectIds.__get__(v))
                                       if variant == 0 else nullcontext())
                            modelContext = (patch.object(SceneObject, '__setattr__', ReferenceSceneObject.__setattr__)
                                            if variant == 0 else nullcontext())
                            with context, modelContext:
                                v.selectionChanged.connect(handler)
                                start = perf_counter()
                                for frame in range(20):
                                    selected.secondVertex = original + point((frame + 1) * .37, (frame + 1) * .11)
                                    v.selectionChanged.emit()
                                    if operation == 'panel':
                                        main.propertiesScrollArea.render(image)
                                elapsed = (perf_counter() - start) * 1000 / 20
                                v.selectionChanged.disconnect(handler)
                            if repeat:
                                samples[variant].append(elapsed)
                    row = dict(sceneWalls = len(v.walls), selection = kind, beforeMs = statistics.median(samples[0]),
                               afterMs = statistics.median(samples[1]), samplesMs = samples)
                    results[operation].append(row)
                    print(operation, count, kind, round(row['beforeMs'], 4), round(row['afterMs'], 4), flush = True)
        v.selectionChanged.connect(current)
    args.output.parent.mkdir(parents = True, exist_ok = True)
    args.output.write_text(json.dumps(results, indent = 2) + '\n', encoding = 'utf-8')


if __name__ == '__main__':
    Main()
