"""Title block pixels agree on opaque/alpha devices using the native font engine."""
import os
import json
from pathlib import Path
import subprocess
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "windows" if sys.platform == "win32" else "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))

from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics import palette
from planner_app.graphics.fonts import LoadApplicationFonts
from planner_app.graphics.title_block import RenderTitleBlockBitmap, TitleBlockLayout
from planner_app.export_plan import RenderPlan
from planner_app.export_worker import ExportJobEncoder


def Main():
    app = QtWidgets.QApplication([])
    LoadApplicationFonts(app)
    options = dict(enabled = True, projectName = "New Project", address = "12 Oak Street\nCape Town", date = "2026-10-28")
    for family in ("Noto Sans", "D-DIN Condensed"):
        palette.labelFont = family
        width, height, block = TitleBlockLayout(100, 600, options)
        fullImage = QtGui.QImage(width, height, QtGui.QImage.Format.Format_RGB32)
        fullImage.fill(QtCore.Qt.GlobalColor.white)
        # Both production paths rasterize at a shared local origin. Fractional
        # right-aligned glyph positions can round differently if drawn globally.
        preview = RenderTitleBlockBitmap(block, options, 250)
        painter = QtGui.QPainter(fullImage)
        painter.drawImage(QtCore.QPointF(block[0], block[1]), preview)
        painter.end()
        expected = fullImage.copy(*map(int, block)).convertToFormat(QtGui.QImage.Format.Format_ARGB32)
        diagnostics = Path(__file__).resolve().parents[1] / "diagnostics" / "title-block"
        diagnostics.mkdir(parents = True, exist_ok = True)
        expected.save(str(diagnostics / "native-export.png"))
        preview.save(str(diagnostics / "native-preview.png"))
        assert preview == expected, f"Native raster preview differs from opaque export for {family}"
        # Verify the real file-producing process, not just an in-process render.
        with tempfile.TemporaryDirectory(dir = Path(__file__).parent) as folder:
            folder = Path(folder)
            appDirectory = Path(__file__).resolve().parents[1] / "planner-main"
            data = json.loads((appDirectory / "startup.plan").read_text(encoding = "utf-8-sig"))
            arguments = dict(planPath = "native.plan", scale = 250, bounds = (0, 0, 4000, 2400),
                             projectData = data, applyTheme = False, border = "None", titleBlock = options, outputFormat = "png")
            rendered = RenderPlan(**arguments)
            font = app.font()
            job = dict(render = arguments, optimized = False, stagingPath = str(folder / "export.png"),
                       style = app.style().objectName(), uiTheme = palette.activeUITheme,
                       canvasTheme = palette.activeCanvasTheme, colors = dict(palette.themeColors), labelFont = family,
                       font = font.toString(), fontHinting = font.hintingPreference().value,
                       fontStrategy = font.styleStrategy().value)
            jobPath = folder / "job.json"
            jobPath.write_text(json.dumps(job, cls = ExportJobEncoder), encoding = "utf-8")
            process = subprocess.run([sys.executable, str(appDirectory / "main.py"), "--export-worker", str(jobPath)],
                                     capture_output = True, text = True, timeout = 20)
            assert process.returncode == 0, process.stdout + process.stderr
            saved = QtGui.QImage(str(folder / "export.png"))
            expectedBlock = rendered.copy(1000, 0, int(block[2]), int(block[3])).convertToFormat(QtGui.QImage.Format.Format_ARGB32)
            assert saved.copy(1000, 0, int(block[2]), int(block[3])).convertToFormat(QtGui.QImage.Format.Format_ARGB32) == expectedBlock
            assert preview == expectedBlock, "Preview bitmap differs from the actual exported file"
    print("Native title block raster checks passed")


if __name__ == "__main__":
    Main()
