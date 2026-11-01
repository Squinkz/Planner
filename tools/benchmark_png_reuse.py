"""Alternating fresh/reused UPNG engines with the production palette RNG."""
import argparse
import gc
import json
import os
from pathlib import Path
import platform
import statistics
import sys
from time import perf_counter

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app import optimized_png
from fixtures import optimized_png_reference_20261031 as reference
from benchmark_geometry_memory import ProcessMemory


def EncodeJob(images, variant):
    encoder = None
    durations, memory = [], []
    start = perf_counter()
    try:
        for image in images:
            pageStart = perf_counter()
            if variant == 0:
                result = reference.EncodeOptimizedPng(image)
            elif len(images) == 1:
                result = optimized_png.EncodeOptimizedPng(image)
            else:
                if encoder is None:
                    encoder = optimized_png.OptimizedPngEncoder()
                result = encoder.Encode(image)
            durations.append((perf_counter() - pageStart) * 1000)
            memory.append(ProcessMemory())
            assert result.startswith(b"\x89PNG\r\n\x1a\n")
    finally:
        if encoder is not None:
            encoder.Close()
    return (perf_counter() - start) * 1000, durations, memory


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--samples", type = int, default = 5)
    parser.add_argument("--output", type = Path, default = root / "diagnostics/performance-memory-gc-20261031/png-benchmark-final.json")
    args = parser.parse_args()
    app = QtWidgets.QApplication([])
    gc.disable()
    images = []
    for page in range(3):
        image = QtGui.QImage(256, 256, QtGui.QImage.Format.Format_RGBA8888)
        image.fill(QtGui.QColor("#123456"))
        with QtGui.QPainter(image) as painter:
            for stripe in range(15):
                painter.fillRect(stripe * 256 // 15, 0, 256 // 30, 256,
                    QtGui.QColor((stripe * 17 + page * 3) % 256, stripe * 13, stripe * 7, 200 + stripe))
        image.setDotsPerMeterX(11811)
        image.setDotsPerMeterY(11811)
        images.append(image)
    rows = []
    for pages in (1, 3):
        samples, pageSamples, memorySamples = [[], []], [[], []], [[], []]
        for repeat in range(args.samples + 1):
            for variant in ((0, 1) if repeat % 2 == 0 else (1, 0)):
                gc.collect()
                total, durations, memory = EncodeJob(images[:pages], variant)
                if repeat:
                    samples[variant].append(total)
                    pageSamples[variant].append(durations)
                    memorySamples[variant].append(memory)
        row = dict(size = [256, 256], pages = pages, beforeMs = statistics.median(samples[0]), afterMs = statistics.median(samples[1]),
            samplesMs = samples, pageSamplesMs = pageSamples, pageMemory = memorySamples)
        rows.append(row)
        print(pages, "pages", round(row["beforeMs"], 3), round(row["afterMs"], 3), flush = True)
    result = dict(python = platform.python_version(), qt = QtCore.qVersion(), samples = args.samples,
        methodology = "Alternate frozen/current jobs; discard one warmup job; medians include engine construction, encoding and cleanup. "
            "Production Math.random; stochastic palette work is not identical between samples. Exact parity is tested separately with equal seeds. "
            "Per-page memory counter sampling is included. Offscreen native UPNG/pako/zlib, 256x256 opaque RGBA flat-color images. "
            "Single-page API remains fresh-engine; three-page jobs reuse one engine. Excludes scene rendering, image creation and file output. "
            "Per-page working-set/private counters share one process and include allocator high-water effects; they do not demonstrate live native bytes.",
        measurements = rows)
    args.output.parent.mkdir(parents = True, exist_ok = True)
    args.output.write_text(json.dumps(result, indent = 2) + "\n", encoding = "utf-8")


if __name__ == "__main__":
    Main()
