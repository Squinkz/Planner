"""Read-only recovery-scene CPU prototype; leaves the actual editor unchanged."""
import argparse
import json
import os
from pathlib import Path
import statistics
import sys
from contextlib import ExitStack
from time import perf_counter
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "planner-main"), str(root / "checks")]
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow
from planner_app.ui.main_window import MainWindow
from planner_app.project_codec import DecodeProject
from planner_app.viewport.rendering import RenderingMixin
from retained_editor_annotations import RetainedAnnotations
from retained_editor_model import RetainedModel


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--project", type = Path, help = "Optional project JSON; otherwise read the recovery snapshot.")
    parser.add_argument("--camera", choices = ("saved", "room", "detail"), default = "saved")
    parser.add_argument("--model", action = "store_true", help = "Also retain model commands; known visual differences.")
    parser.add_argument("--integrated", action = "store_true", help = "Compare the integrated dimension layer with the previous painter.")
    parser.add_argument("--parity", action = "store_true", help = "Compare seven images; differences are reported, not accepted.")
    options = parser.parse_args()
    if options.integrated and options.model:
        parser.error("--integrated measures dimensions only and cannot be combined with --model")
    source = options.project or Path(os.environ["LOCALAPPDATA"]) / "Planner/session.json"
    project = json.loads(source.read_text(encoding = "utf-8-sig"))
    project = project.get("project", project)
    project.pop("history", None)
    project.pop("activityLog", None)
    applicationMeasurements = RenderingMixin.DrawSceneMeasurements
    def PreviousMeasurements(self, *arguments, **keywords):
        with patch.object(self, "DrawRetainedMeasurements", return_value = False):
            return applicationMeasurements(self, *arguments, **keywords)
    original = PreviousMeasurements
    result = {"viewport": [1600, 1000], "backend": "CPU QGraphicsScene on the existing raster painter",
              "camera": options.camera, "runs": [], "productionIntegration": options.integrated}
    with patch.object(MainWindow, "show", lambda self: None), ExampleWindow() as (main, folder):
        viewport = main.viewport
        main.ApplyProject(DecodeProject(project, viewport.furnishingDefinitions), None)
        viewport.setFixedSize(1600, 1000)
        viewport.ensurePolished()
        if options.camera != "saved":
            viewport.zoom = .6 if options.camera == "room" else 1.5
            viewport.panOffset += viewport.DrawingRect().center() - viewport.WorldToViewport(QtCore.QPointF(6000, 8000))
        viewport.grab()
        assert viewport.showMeasurements and getattr(viewport, "measurementLabelRecords", None) is not None, "The probe requires visible dimensions."
        result["startingZoom"] = viewport.zoom
        result["devicePixelRatio"] = viewport.devicePixelRatioF()
        result["objects"] = len(viewport.walls) + len(viewport.windows) + len(viewport.furnishings) + len(viewport.labels)
        if not options.integrated:
            image = QtGui.QImage(viewport.size(), QtGui.QImage.Format.Format_RGB32)
            with QtGui.QPainter(image) as painter:
                painter.setFont(viewport.viewportBackgroundFont)
                retained = RetainedAnnotations(viewport, painter)
            print("retained", len(retained.entries), "dimension groups", flush = True)
        started = perf_counter()
        model = RetainedModel(viewport) if options.model else None
        if model is not None:
            print("retained model", model.picture.size(), "bytes", flush = True)
            result["model"] = dict(pictureBytes = model.picture.size(), buildMs = (perf_counter() - started) * 1000)
        originalScene = RenderingMixin.DrawScene
        originalLabels = RenderingMixin.DrawLabels

        def ModelPrototype(self, painter, drawingRect, origin, pixelsPerMillimeter, dirtyRects = None,
                           drawAnnotations = True, retainAnnotations = False, **kwargs):
            state = model.Paint(self, painter)
            if drawAnnotations:
                self.DrawSceneMeasurements(painter, drawingRect, state, dirtyRects, retainCommands = retainAnnotations)
            return state

        def SkipLabels(self, *args, **kwargs):
            return None

        def Prototype(self, painter, drawingRect, sceneState, dirtyRects = None, retainCommands = False):
            if options.integrated:
                return applicationMeasurements(self, painter, drawingRect, sceneState, dirtyRects, retainCommands)
            retained.Paint(painter, drawingRect)

        def UseMethod(method):
            scope = ExitStack()
            useModel = model is not None and method is Prototype
            scope.enter_context(patch.object(RenderingMixin, "DrawSceneMeasurements", method))
            scope.enter_context(patch.object(RenderingMixin, "DrawScene", ModelPrototype if useModel else originalScene))
            scope.enter_context(patch.object(RenderingMixin, "DrawLabels", SkipLabels if useModel else originalLabels))
            return scope

        savedZoom, savedPan = viewport.zoom, QtCore.QPointF(viewport.panOffset)
        variant = "integrated" if options.integrated else "model" if model is not None else "annotations"
        suffix = f"-{options.camera}-{variant}-dpr{viewport.devicePixelRatioF():g}"
        output = root / "diagnostics"
        output.mkdir(exist_ok = True)
        if options.parity:
            import numpy as np
            result["parity"] = []
            for factor in (1, 1.12, .8, 1.4, .6, 2, .5):
                viewport.ZoomBy(factor, viewport.DrawingRect().center())
                images = []
                for method in (original, Prototype):
                    viewport.viewportSceneKey = None
                    viewport.measurementPictures = []
                    viewport.measurementPaintZoom = viewport.zoom / 1.1
                    with UseMethod(method):
                        images.append(viewport.grab().toImage().convertToFormat(QtGui.QImage.Format.Format_RGB32))
                arrays = [np.frombuffer(item.constBits(), dtype = np.uint8).reshape(item.height(), item.width(), 4) for item in images]
                delta = np.abs(arrays[0].astype(np.int16) - arrays[1].astype(np.int16))
                different = np.any(delta != 0, axis = 2)
                comparison = dict(zoom = viewport.zoom, pixels = int(different.sum()), maximum = int(delta.max()),
                                  pixelsAbove8 = int(np.any(delta > 8, axis = 2).sum()))
                result["parity"].append(comparison)
                # Ensure the experiment restores the original renderer and can
                # redraw the exact reference after its temporary substitutions.
                assert RenderingMixin.DrawSceneMeasurements is applicationMeasurements
                assert RenderingMixin.DrawScene is originalScene
                assert RenderingMixin.DrawLabels is originalLabels
                viewport.viewportSceneKey = None
                viewport.measurementPictures = []
                viewport.measurementPaintZoom = viewport.zoom / 1.1
                with UseMethod(original):
                    restored = viewport.grab().toImage().convertToFormat(QtGui.QImage.Format.Format_RGB32)
                assert restored == images[0], "Original renderer changed after prototype render."
                print("parity", comparison, flush = True)
                if len(result["parity"]) <= 2:
                    frameSuffix = "" if len(result["parity"]) == 1 else "-zoomed"
                    for name, image in zip(("original", "retained"), images):
                        image.save(str(output / f"retained-editor{suffix}{frameSuffix}-{name}.png"))
                    difference = QtGui.QImage((different.astype(np.uint8) * 255).tobytes(), images[0].width(),
                        images[0].height(), images[0].width(), QtGui.QImage.Format.Format_Grayscale8).copy()
                    difference.save(str(output / f"retained-editor{suffix}{frameSuffix}-difference.png"))
        timesByMethod = {"current": [], "retained": []}
        for repeat in range(5):
            methods = [("current", original), ("retained", Prototype)]
            if repeat % 2:
                methods.reverse()
            for name, method in methods:
                viewport.zoom = savedZoom
                viewport.panOffset = QtCore.QPointF(savedPan)
                viewport.viewportSceneKey = None
                viewport.measurementPictures = []
                times = []
                with UseMethod(method):
                    for frame in range(16):
                        started = perf_counter()
                        viewport.ZoomBy(1.12 if frame < 8 else 1 / 1.12, viewport.DrawingRect().center())
                        viewport.grab()
                        times.append((perf_counter() - started) * 1000)
                print(repeat, name, round(statistics.median(times), 2), flush = True)
                if repeat:
                    timesByMethod[name].extend(times)
                    result["runs"].append(dict(repeat = repeat, method = name, medianMs = statistics.median(times)))
        for name, times in timesByMethod.items():
            result[name] = dict(medianMs = statistics.median(times), p95Ms = sorted(times)[int(len(times) * .95)])
        print(result["current"], result["retained"], flush = True)
        result["originalRendererRestored"] = RenderingMixin.DrawSceneMeasurements is applicationMeasurements and RenderingMixin.DrawScene is originalScene and RenderingMixin.DrawLabels is originalLabels
        assert result["originalRendererRestored"]
    (output / f"retained-editor-results{suffix}.json").write_text(json.dumps(result, indent = 2), encoding = "utf-8")


if __name__ == "__main__":
    Main()
