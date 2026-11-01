"""Alternate frozen/current furnishing renders through continuous transforms."""
import argparse
import cProfile
import json
import os
from pathlib import Path
import platform
import pstats
import statistics
import sys
from time import perf_counter
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
from planner_app.graphics.fonts import LoadApplicationFonts
from fixtures.furnishing_variant_cases_20261031 import MakeRenderer, VariantCases


def RenderFrames(renderer, image, nominal, operation, start, count):
    with QtGui.QPainter(image) as painter:
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        for frame in range(start, start + count):
            painter.save()
            painter.translate(400.37, 300.71)
            angle = 13 + frame * .17 if operation == "rotation" else 13
            zoom = .7 + frame * .0017 if operation == "zoom" else 1
            width = 420 + frame * .17 if operation == "resize" else 420
            length = 320 + frame * .11 if operation == "resize" else 320
            painter.rotate(angle)
            painter.scale(zoom, zoom)
            renderer.render(painter, QtCore.QRectF(-width / 2, -length / 2, width, length),
                            worldSize = (nominal[0] * width / 420, nominal[1] * length / 320) if renderer.fixedElements else None)
            painter.restore()


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--output", type = Path, default = root / "diagnostics/performance-furnishing-svg-20261031/benchmark-final.json")
    parser.add_argument("--samples", type = int, default = 7)
    parser.add_argument("--frames", type = int, default = 24)
    args = parser.parse_args()
    if args.samples < 1 or args.frames < 1:
        parser.error("Sample and frame counts must be positive")
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    results = dict(python = platform.python_version(), qt = QtCore.qVersion(), platform = platform.platform(),
                   unit = "milliseconds per furnishing render", samples = args.samples, framesPerSample = args.frames,
                   methodology = "Alternate frozen/current methods, discard one warmup batch, median of per-frame batch means. "
                       "Continuous unique transforms on 800x600 offscreen QImage with antialiasing; includes matrix preparation, "
                       "variant construction and native raster drawing. Excludes renderer initialization, scene traversal, input, "
                       "properties and display latency. Artwork is real washer/coffee-table SVG or synthetic mixed compounds.",
                   measurements = [], coldMeasurements = [], callCounts = [])
    for name, source, nominal in VariantCases():
        coldSamples = [[], []]
        coldImage = QtGui.QImage(800, 600, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        coldImage.fill(QtCore.Qt.GlobalColor.transparent)
        for sample in range(args.samples):
            for variant in ((0, 1) if sample % 2 == 0 else (1, 0)):
                renderer = MakeRenderer(source, nominal, reference = variant == 0)
                start = perf_counter()
                RenderFrames(renderer, coldImage, nominal, "rotation", 0, 1)
                coldSamples[variant].append((perf_counter() - start) * 1000)
        results["coldMeasurements"].append(dict(asset = name, operation = "first variant after renderer initialization",
            beforeMs = statistics.median(coldSamples[0]), afterMs = statistics.median(coldSamples[1]), samplesMs = coldSamples))
        for operation in ("rotation", "zoom", "resize", "unchanged"):
            renderers = [MakeRenderer(source, nominal, reference = variant == 0) for variant in range(2)]
            images = [QtGui.QImage(800, 600, QtGui.QImage.Format.Format_ARGB32_Premultiplied) for variant in range(2)]
            for image in images:
                image.fill(QtCore.Qt.GlobalColor.transparent)
            samples = [[], []]
            for sample in range(args.samples + 1):
                for variant in ((0, 1) if sample % 2 == 0 else (1, 0)):
                    start = perf_counter()
                    RenderFrames(renderers[variant], images[variant], nominal, operation, sample * args.frames, args.frames)
                    elapsed = (perf_counter() - start) * 1000 / args.frames
                    if sample:
                        samples[variant].append(elapsed)
            row = dict(asset = name, sourceBytes = len(source), lettering = len(renderers[1].lettering),
                       fixedDetails = len(renderers[1].fixedElements), operation = operation,
                       beforeMs = statistics.median(samples[0]), afterMs = statistics.median(samples[1]), samplesMs = samples)
            results["measurements"].append(row)
            print(name, operation, round(row["beforeMs"], 3), round(row["afterMs"], 3), flush = True)
            # Profiles are separate from timings and measure a warmed sequence.
            for variant, renderer in enumerate(renderers):
                profile = cProfile.Profile()
                with patch.object(QtSvg, "QSvgRenderer", wraps = QtSvg.QSvgRenderer) as construct:
                    profile.enable()
                    RenderFrames(renderer, images[variant], nominal, operation, (args.samples + 1) * args.frames, args.frames)
                    profile.disable()
                    instances = construct.call_count
                stats = pstats.Stats(profile).stats
                counts = {name: sum(value[1] for key, value in stats.items() if key[2] == name)
                          for name in ("tostring", "deepcopy", "PrepareLetteringTemplate")}
                counts["rendererInstances"] = instances
                results["callCounts"].append(dict(asset = name, operation = operation, variant = "before" if variant == 0 else "after", calls = counts))
    args.output.parent.mkdir(parents = True, exist_ok = True)
    args.output.write_text(json.dumps(results, indent = 2) + "\n", encoding = "utf-8")


if __name__ == "__main__":
    Main()
