"""Reusable PNG engines retain exact seeded palette/pixels and release per-page data."""
import io
import json
import os
from contextlib import redirect_stdout
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import weakref
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app import optimized_png, export_plan
from planner_app.graphics import palette
from planner_app.export_worker import RunExportWorker, ExportJobEncoder
from check_optimized_png_parity import SeededEngine, TestImage, PngFingerprint
from fixtures import optimized_png_reference_20261031 as reference


def Main():
    app = QtWidgets.QApplication([])
    cases = json.loads((root / "checks/fixtures/optimized_png_parity.json").read_text(encoding = "utf-8"))["cases"]
    images = [TestImage(case) for case in cases]
    with patch.object(optimized_png, "QJSEngine", SeededEngine):
        encoder = optimized_png.OptimizedPngEncoder()
    retained = weakref.ref(encoder.engine)
    try:
        for index in (*range(len(images)), 0, len(images) - 1):
            # UPNG's palette seed is stochastic in both implementations. Equal
            # starting random states must still produce identical PNG bytes.
            encoder.engine.evaluate("plannerTestSeed = 123;")
            with patch.object(reference, "QJSEngine", SeededEngine):
                expected = reference.EncodeOptimizedPng(images[index])
            actual = encoder.Encode(images[index])
            assert actual == expected, (index, "encoded bytes")
            assert PngFingerprint(actual) == cases[index]["expected"]
            assert encoder.engine.globalObject().property("plannerRgba").isNull()
        append = encoder.engine.globalObject().property("AppendPngPixels")
        encoder.engine.globalObject().setProperty("AppendPngPixels", encoder.engine.evaluate("(function(){ throw new Error('Injected transfer failure'); })"))
        try:
            encoder.Encode(images[0])
        except RuntimeError as error:
            assert "transfer optimized PNG pixels" in str(error)
        else:
            raise AssertionError("Transfer failure was not reported")
        assert encoder.engine.globalObject().property("plannerRgba").isNull()
        encoder.engine.globalObject().setProperty("AppendPngPixels", append)
        del append
        encoder.engine.evaluate("plannerTestSeed = 123;")
        assert PngFingerprint(encoder.Encode(images[0])) == cases[0]["expected"]
        with ThreadPoolExecutor(max_workers = 1) as pool:
            for method in (lambda: encoder.Encode(images[0]), encoder.Close):
                try:
                    pool.submit(method).result()
                except RuntimeError as error:
                    assert "owning thread" in str(error)
                else:
                    raise AssertionError("Engine used or destroyed on another thread")
    finally:
        encoder.Close()
    assert retained() is None, "Closed encoder retained the native engine"
    try:
        encoder.Encode(images[0])
    except RuntimeError as error:
        assert "closed" in str(error)
    else:
        raise AssertionError("Closed engine accepted another page")
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        pages = [dict(render = {}, stagingPath = str(folder / f"page-{index}.png")) for index in range(3)]
        job = dict(render = dict(outputFormat = "png"), pages = pages, stagingPath = pages[0]["stagingPath"], optimized = True,
                   style = app.style().objectName(), uiTheme = palette.activeUITheme, canvasTheme = palette.activeCanvasTheme,
                   colors = dict(palette.themeColors), labelFont = palette.labelFont)
        path = folder / "job.json"
        path.write_text(json.dumps(job, cls = ExportJobEncoder), encoding = "utf-8")
        class CountedEncoder(optimized_png.OptimizedPngEncoder):
            instances = []
            def __init__(self):
                super().__init__()
                self.calls = 0
                self.instances.append(self)
            def Encode(self, image):
                self.calls += 1
                self.engine.evaluate("plannerTestSeed = 123;")
                return super().Encode(image)
        chosen = images[:3] if len(images) >= 3 else [images[0]] * 3
        output = io.StringIO()
        with patch.object(optimized_png, "QJSEngine", SeededEngine), \
                patch.object(optimized_png, "OptimizedPngEncoder", CountedEncoder), \
                patch.object(export_plan, "RenderPlan", side_effect = chosen), redirect_stdout(output):
            assert RunExportWorker(path) == 0, output.getvalue()
        assert len(CountedEncoder.instances) == 1 and CountedEncoder.instances[0].calls == 3
        assert CountedEncoder.instances[0].engine is None
        for page, image in zip(pages, chosen):
            with patch.object(reference, "QJSEngine", SeededEngine):
                expected = reference.EncodeOptimizedPng(image)
            assert Path(page["stagingPath"]).read_bytes() == expected
        class FailingEncoder(CountedEncoder):
            def Encode(self, image):
                if self.calls == 1:
                    raise RuntimeError("Injected second-page failure")
                return super().Encode(image)
        Path(pages[1]["stagingPath"]).write_bytes(b"existing staging data")
        output = io.StringIO()
        with patch.object(optimized_png, "QJSEngine", SeededEngine), \
                patch.object(optimized_png, "OptimizedPngEncoder", FailingEncoder), \
                patch.object(export_plan, "RenderPlan", side_effect = chosen), redirect_stdout(output):
            assert RunExportWorker(path) == 1
        assert "Injected second-page failure" in output.getvalue()
        assert CountedEncoder.instances[-1].engine is None
        assert Path(pages[1]["stagingPath"]).read_bytes() == b"existing staging data"
    print("PASS: exact reusable/frozen PNG bytes, palettes/pixels/DPI, buffer reset, failure recovery, thread ownership, engine release and one encoder per three-page worker job.")


if __name__ == "__main__":
    Main()
