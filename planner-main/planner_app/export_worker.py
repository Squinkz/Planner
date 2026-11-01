"""Isolated GUI-export renderer. Communicates stages over the process stdout pipe."""
import json
import base64
import sys
from pathlib import Path

from PySide6 import QtCore, QtWidgets


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
    sceneCache = None
    optimizedEncoder = None
    pdf = None
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
        from planner_app.export_plan import ExportSceneCache, RenderPlan
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
        pages = job.get("pages", [dict(render = job["render"], stagingPath = job["stagingPath"])])
        if len(pages) > 1 and (job["render"]["outputFormat"] == "png" or job.get("pdf", False)):
            sceneCache = ExportSceneCache()
        for index, page in enumerate(pages, 1):
            render = dict(job["render"], **page["render"])
            if sceneCache is not None:
                render["sceneCache"] = sceneCache
            Report(f"Rendering page {index} of {len(pages)}" if len(pages) > 1 else "Rendering")
            result = RenderPlan(**render)
            # This worker has no app.exec() loop to retire uncached SVG scenes.
            # The returned bytes/image no longer need their temporary viewport.
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
            if job.get("pdf", False):
                from planner_app.pdf_export import PdfExporter
                if pdf is None:
                    pdf = PdfExporter(page["stagingPath"], Path(render["planPath"]).stem)
                Report(f"Writing PDF page {index} of {len(pages)}")
                pdf.AddPage(result, render["pageSize"])
                del result
                QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
                continue
            if job["optimized"]:
                Report("Optimizing PNG")
                if len(pages) > 1:
                    from planner_app.optimized_png import OptimizedPngEncoder
                    if optimizedEncoder is None:
                        optimizedEncoder = OptimizedPngEncoder()
                    result = optimizedEncoder.Encode(result)
                else:
                    from planner_app.optimized_png import EncodeOptimizedPng
                    result = EncodeOptimizedPng(result)
            elif render["outputFormat"] == "png":
                Report("Encoding and saving PNG")
                if not result.save(page["stagingPath"], "PNG"):
                    raise OSError("Could not encode the PNG image.")
                del result
                continue
            Report("Saving file")
            with Path(page["stagingPath"]).open("wb") as output:
                if output.write(result) != len(result):
                    raise OSError("Could not write the complete export.")
            del result
        if pdf is not None:
            Report("Saving PDF")
            pdf.Close()
        return 0
    except Exception as error:
        from .crash_reporting import ExceptionDetails
        print("PLANNER_EXPORT:" + json.dumps(ExceptionDetails(error)), flush = True)
        return 1
    finally:
        if pdf is not None:
            pdf.Close()
        if optimizedEncoder is not None:
            optimizedEncoder.Close()
        if sceneCache is not None:
            sceneCache.Clear()
