"""Alternating frozen/current native column preparation and active redraws."""
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
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.models import Wall, Column
from planner_app.viewport.geometry import GeometryMixin
from planner_app.viewport.widget import DrawingViewport
from fixtures.qt_column_occlusion_reference_20261030 import ReferenceViewport


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument('--output', type = Path, default = root / 'diagnostics/performance-column-occlusion-20261030/benchmark.json')
    parser.add_argument('--layout', choices = ('row', 'grid', 'dense'))
    parser.add_argument('--repeats', type = int, default = 5)
    args = parser.parse_args()
    app = QtWidgets.QApplication([])
    app.setStyle('Fusion')
    point = QtCore.QPointF
    results = dict(python = platform.python_version(), qt = QtCore.qVersion(), platform = platform.platform(), unit = 'milliseconds', repeats = args.repeats,
                   methodology = 'Alternate frozen/current variants; discard one warmup; median of the requested sample count. '
                       'Each sample changes one real endpoint. Preparation includes regular-wall geometry, column curves/polygons, '
                       'occluders and the exact sequential exterior union. Paints are 1200x800 offscreen QWidget.render calls '
                       'in active drag state with measurements/tips disabled and most objects offscreen. '
                       'Frozen column assembly also applies to geometry workspaces. Excludes pointer handling/properties; '
                       'not end-to-end display latency.', preparation = [], paint = [])
    workloads = [('row', count) for count in (8, 32, 128, 512)] + [('grid', 64), ('dense', 64)]
    for layout, count in workloads:
        if args.layout is not None and layout != args.layout:
            continue
        for operation in (('preparation', 'paint') if layout == 'row' and count in (128, 512) else ('preparation',)):
            for edit in (('wall', 'last', 'first', 'middle') if operation == 'preparation' and layout != 'dense' else ('wall', 'last')):
                views, images = [], []
                spacing = 50 if layout == 'dense' else 2000
                columns = count if layout == 'row' else 8
                sourcePosition = 0 if edit == 'wall' else count if edit == 'last' else 1 + count // 2 if edit == 'middle' else 1
                for cls in (ReferenceViewport, DrawingViewport):
                    view = cls(furnishingDefinitions = {})
                    view.resize(1200, 800)
                    view.showMeasurements = view.showTips = False
                    view.walls = [Wall(point(-10000, -5000), point(-5000, -5000), 200)] + [
                        Column(point(index % columns * spacing, index // columns * spacing - 300),
                               point(index % columns * spacing, index // columns * spacing + 300), 600) for index in range(count)]
                    source = view.walls[sourcePosition]
                    view.SetSelection([(source, None)], notify = False)
                    view.dragStart, view.isDragging = point(400, 300), True
                    image = QtGui.QImage(view.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
                    views.append(view)
                    images.append(image)
                samples = [[], []]
                for repeat in range(args.repeats + 1):
                    for variant in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                        view = views[variant]
                        source = view.walls[sourcePosition]
                        source.secondVertex += point(1, .3)
                        context = (patch.object(GeometryMixin, 'ConnectedColumnWallPath', ReferenceViewport.ConnectedColumnWallPath)
                                   if variant == 0 else nullcontext())
                        with context:
                            start = perf_counter()
                            if operation == 'paint':
                                view.render(images[variant])
                            else:
                                view.ConnectedWallPath(view.walls)
                            elapsed = (perf_counter() - start) * 1000
                        if repeat:
                            samples[variant].append(elapsed)
                row = dict(layout = layout, columns = count, regularWalls = 1, edit = edit,
                           beforeMs = statistics.median(samples[0]), afterMs = statistics.median(samples[1]), samplesMs = samples)
                results[operation].append(row)
                print(operation, layout, count, edit, round(row['beforeMs'], 3), round(row['afterMs'], 3), flush = True)
                for view in views:
                    view.close()
                    view.deleteLater()
                QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    args.output.parent.mkdir(parents = True, exist_ok = True)
    args.output.write_text(json.dumps(results, indent = 2) + '\n', encoding = 'utf-8')


if __name__ == '__main__':
    Main()
