"""Persistent offscreen preview renderer, isolated from the editor's Qt objects."""
import ctypes
import json
import pickle
from pathlib import Path
import sys



def WriteSvgPreview(output, root):
    """Prepare private transport, retaining the legacy path on memory pressure."""
    from planner_app.graphics.svg_preview import SvgPreviewRenderer
    from shiboken6 import delete, isValid
    with output.open("wb") as destination:
        transport = pickle.Pickler(destination, protocol = pickle.HIGHEST_PROTOCOL)
        transport.dump(root)
        rootBytes = destination.tell()
        prepared = data = None
        try:
            prepared = SvgPreviewRenderer.__new__(SvgPreviewRenderer)
            prepared.__init__(root, prepareOnly = True)
            data = prepared.PreparedData()
        except MemoryError:
            pass
        finally:
            if prepared is not None and isValid(prepared):
                delete(prepared)
            del prepared
        if data is not None:
            try:
                # One Pickler preserves shared XML identities across both records.
                # Logical vector budgets retain the original root's exact size.
                transport.dump(dict(format = "Planner prepared SVG", size = rootBytes * 2, data = data))
            except MemoryError:
                data = None
                transport.clear_memo()
                destination.seek(rootBytes)
                destination.truncate()


def Main():
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetErrorMode(0x8003)
        class BasicLimits(ctypes.Structure):
            _fields_ = [("processTime", ctypes.c_longlong), ("jobTime", ctypes.c_longlong), ("flags", ctypes.c_ulong),
                        ("minimum", ctypes.c_size_t), ("maximum", ctypes.c_size_t), ("processes", ctypes.c_ulong),
                        ("affinity", ctypes.c_size_t), ("priority", ctypes.c_ulong), ("scheduling", ctypes.c_ulong)]
        class JobLimits(ctypes.Structure):
            _fields_ = [("basic", BasicLimits), ("io", ctypes.c_ulonglong * 6), ("processMemory", ctypes.c_size_t),
                        ("jobMemory", ctypes.c_size_t), ("peakProcess", ctypes.c_size_t), ("peakJob", ctypes.c_size_t)]
        kernel = ctypes.windll.kernel32
        kernel.CreateJobObjectW.restype = ctypes.c_void_p
        memoryJob = kernel.CreateJobObjectW(None, None)
        limits = JobLimits()
        limits.basic.flags = 0x100
        limits.processMemory = 768 * 1024 * 1024
        if kernel.SetInformationJobObject(ctypes.c_void_p(memoryJob), 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            kernel.AssignProcessToJobObject(ctypes.c_void_p(memoryJob), ctypes.c_void_p(-1))
    from PySide6 import QtCore, QtGui, QtWidgets
    from planner_app.export_plan import ExportSceneCache, RenderPlan
    from planner_app.graphics import palette
    from planner_app.graphics.theme import ApplyApplicationTheme
    app = QtWidgets.QApplication([])
    caches = {}
    previousStyle = None
    try:
        for line in sys.stdin:
            request = json.loads(line)
            message = dict(id = request["id"])
            try:
                # Jobs come only from the owning parent's private directory.
                with Path(request["job"]).open("rb") as source:
                    job = pickle.load(source)
                palette.SetThemes(job["uiTheme"], job["canvasTheme"])
                palette.themeColors.update(job["colors"])
                palette.labelFont = job["labelFont"]
                style = tuple(job[name] for name in ("style", "uiTheme", "canvasTheme", "labelFont", "font", "fontHinting", "fontStrategy"))
                if style != previousStyle:
                    if app.style().objectName() != job["style"]:
                        app.setStyle(job["style"])
                    ApplyApplicationTheme(app)
                    font = QtGui.QFont()
                    font.fromString(job["font"])
                    font.setHintingPreference(QtGui.QFont.HintingPreference(job["fontHinting"]))
                    font.setStyleStrategy(QtGui.QFont.StyleStrategy(job["fontStrategy"]))
                    app.setFont(font)
                    previousStyle = style
                render = job["render"]
                kind = render["outputFormat"]
                # Sampled overview/detail and native pages alternate within one
                # frame. Keep their prepared state independent so one does not
                # evict the other's geometry and compensated furnishing strokes.
                cacheKey = (kind, bool(job.get("context", False)))
                for attempt in range(2):
                    if cacheKey not in caches:
                        caches[cacheKey] = ExportSceneCache()
                    render.update(sceneCache = caches[cacheKey], previewDocument = kind == "svg")
                    try:
                        result = RenderPlan(**render)
                        break
                    except (MemoryError, ValueError) as error:
                        allocationError = isinstance(error, MemoryError) or str(error) in (
                            "Could not allocate the title block bitmap.", "Could not allocate the render image.")
                        if attempt or not allocationError:
                            raise
                    # A long-lived worker can reach its memory limit while old
                    # scene/texture data are still retained. Unwind the failed
                    # render before releasing them, then retry this job once.
                    # Do not cache a transient failure as the finished preview.
                    for cache in caches.values():
                        cache.Clear()
                    caches.clear()
                    from planner_app.graphics import compositing
                    for cached in (compositing.LoadNormalTexture, compositing.NormalTextureLookup,
                                   compositing.NormalLightingTile, compositing.AmbientOcclusionTile):
                        cached.cache_clear()
                    QtGui.QPixmapCache.clear()
                    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
                output = Path(request["output"])
                if kind == "png":
                    # A lossless, uncompressed transport avoids spending the
                    # preview's time compressing an image which is read once.
                    header = dict(width = result.width(), height = result.height(), stride = result.bytesPerLine(),
                                  format = result.format().value, dpiX = result.dotsPerMeterX(), dpiY = result.dotsPerMeterY())
                    with output.open("wb") as destination:
                        destination.write((json.dumps(header) + "\n").encode("ascii"))
                        destination.write(result.constBits())
                else:
                    WriteSvgPreview(output, result)
                del result
            except Exception as error:
                from .crash_reporting import ExceptionDetails
                message.update(ExceptionDetails(error))
            print("PLANNER_PREVIEW:" + json.dumps(message), flush = True)
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    finally:
        for cache in caches.values():
            cache.Clear()


if __name__ == "__main__":
    Main()
