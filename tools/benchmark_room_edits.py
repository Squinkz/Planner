"""Alternate frozen/current room preparation and single-wall drag redraws."""
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
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Wall
from planner_app.viewport.widget import DrawingViewport
from check_room_detection import Rectangle
from fixtures.qt_room_edits_reference_20261030 import ReferenceViewport


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument('--output', type = Path, default = root / 'diagnostics/performance-room-edits-20261030/benchmark.json')
    args = parser.parse_args()
    app = QtWidgets.QApplication([])
    app.setStyle('Fusion')
    point = QtCore.QPointF
    results = dict(python = platform.python_version(), qt = QtCore.qVersion(), platform = platform.platform(),
                   unit = 'milliseconds', repeats = 5, baseline = 'After connected discovery and jamb optimization',
                   methodology = 'Alternating frozen/current views; one warmup discarded; medians of five samples. '
                       '1200x800 offscreen viewport, measurements/tips disabled, most geometry offscreen. '
                       'Each sample changes actual wall geometry. Preparation includes room classification; '
                       'paint includes QWidget.render, excludes input handling/snapping. No end-to-end latency claim.',
                   preparation = [], paint = [])
    workloads = [('rooms', count) for count in (16, 64, 128, 256)]
    workloads += [('sparse', count) for count in (128, 512, 1024)] + [('chain', 512), ('grid', 128)]
    for layout, count in workloads:
        for operation in ('preparation', 'paint'):
            for gesture in (('endpoint', 'whole') if operation == 'paint' else ('endpoint',)):
                views, images = [], []
                for cls in (ReferenceViewport, DrawingViewport):
                    view = cls(furnishingDefinitions = {})
                    view.resize(1200, 800)
                    view.showMeasurements = view.showTips = False
                    view.zoom = .2
                    if layout == 'rooms':
                        view.walls = [wall for index in range(count) for wall in Rectangle(index % 16 * 6000, index // 16 * 6000, 4000, 4000)]
                    elif layout == 'grid':
                        view.walls = [Wall(point(x * 4000, 0), point(x * 4000, 32000), 200) for x in range(17)]
                        view.walls += [Wall(point(0, y * 4000), point(64000, y * 4000), 200) for y in range(9)]
                    else:
                        spacing = 100 if layout == 'chain' else 2000
                        columns = count if layout == 'chain' else 32
                        length = 100 if layout == 'chain' else 1400
                        view.walls = [Wall(point(index % columns * spacing, index // columns * spacing),
                            point(index % columns * spacing + length, index // columns * spacing), 200) for index in range(count)]
                    # Edit an offscreen object so stationary-layer reuse can be
                    # distinguished from the cost of the changed visible artwork.
                    view.SetSelection([(view.walls[-1], 1 if gesture == 'endpoint' else None)], notify = False)
                    view.dragStart, view.isDragging = point(400, 300), True
                    view.interactionBefore = view.CaptureState()
                    image = QtGui.QImage(view.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                    if operation == 'paint':
                        view.render(image)
                    else:
                        view.roomDetection.Check()
                    views.append(view)
                    images.append(image)
                samples = [[], []]
                for repeat in range(6):
                    for variant in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                        view = views[variant]
                        view.walls[-1].secondVertex += point(1, 0)
                        if gesture == 'whole':
                            view.walls[-1].firstVertex += point(1, 0)
                        start = perf_counter()
                        if operation == 'paint':
                            view.render(images[variant])
                        else:
                            view.roomDetection.Check()
                        elapsed = (perf_counter() - start) * 1000
                        if repeat:
                            samples[variant].append(elapsed)
                row = dict(layout = layout, objects = len(views[0].walls), rooms = views[0].roomDetection.count, gesture = gesture,
                           beforeMs = statistics.median(samples[0]), afterMs = statistics.median(samples[1]), samplesMs = samples)
                results[operation].append(row)
                print(operation, layout, count, gesture, round(row['beforeMs'], 3), round(row['afterMs'], 3), flush = True)
                for view in views:
                    view.close()
    args.output.parent.mkdir(parents = True, exist_ok = True)
    args.output.write_text(json.dumps(results, indent = 2) + '\n', encoding = 'utf-8')


if __name__ == '__main__':
    Main()
