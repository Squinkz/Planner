"""Isolated GUI-export renderer. Communicates stages over the process stdout pipe."""
import json
import base64
import sys
from pathlib import Path

from PySide6 import QtWidgets


class ExportJobEncoder(json.JSONEncoder):
    def default(self, value):
        if isinstance(value, Path):
            return {"__plannerExportType": "path", "value": str(value)}
        if isinstance(value, bytes):
            return {"__plannerExportType": "bytes", "value": base64.b64encode(value).decode("ascii")}
        return super().default(value)


def DecodeExportValue(value):
    if set(value) == {"__plannerExportType", "value"}:
        if value["__plannerExportType"] == "path":
            return Path(value["value"])
        if value["__plannerExportType"] == "bytes":
            return base64.b64decode(value["value"], validate = True)
    return value


def RunExportWorker(jobPath):
    if sys.platform == "win32":
        import ctypes
        # A native worker failure must exit back to the parent's error handler,
        # not wait behind the modal progress window for Windows crash UI.
        ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    def Report(stage):
        print("PLANNER_EXPORT:" + json.dumps({"stage": stage}), flush = True)

    try:
        Report("Preparing plan")
        job = json.loads(Path(jobPath).read_text(encoding = "utf-8"), object_hook = DecodeExportValue)
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        if app.style().objectName() != job["style"]:
            app.setStyle(job["style"])
        from planner_app.graphics import palette
        from planner_app.graphics.theme import ApplyApplicationTheme
        from planner_app.export_plan import RenderPlan
        palette.SetThemes(uiTheme = job["uiTheme"], canvasTheme = job["canvasTheme"])
        palette.themeColors.update(job["colors"])
        palette.labelFont = job["labelFont"]
        ApplyApplicationTheme(app)
        if "font" in job:
            from PySide6 import QtGui
            font = QtGui.QFont()
            font.fromString(job["font"])
            font.setHintingPreference(QtGui.QFont.HintingPreference(job["fontHinting"]))
            font.setStyleStrategy(QtGui.QFont.StyleStrategy(job["fontStrategy"]))
            app.setFont(font)
        Report("Rendering")
        result = RenderPlan(**job["render"])
        if job["optimized"]:
            from planner_app.optimized_png import EncodeOptimizedPng
            Report("Optimizing PNG")
            result = EncodeOptimizedPng(result)
        elif job["render"]["outputFormat"] == "png":
            Report("Encoding and saving PNG")
            if not result.save(job["stagingPath"], "PNG"):
                raise OSError("Could not encode the PNG image.")
            return 0
        Report("Saving file")
        with Path(job["stagingPath"]).open("wb") as output:
            if output.write(result) != len(result):
                raise OSError("Could not write the complete export.")
        return 0
    except Exception as error:
        print("PLANNER_EXPORT:" + json.dumps({"error": str(error)}), flush = True)
        return 1
