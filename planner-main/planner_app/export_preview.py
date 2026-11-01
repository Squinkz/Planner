"""Coalesce preview work in one persistent process; adopt only current results."""
from collections import OrderedDict
import json
import os
import pickle
from pathlib import Path
import sys
import tempfile
from time import sleep
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics import palette
from planner_app.paths import appDirectory
from planner_app.crash_reporting import ExceptionDetails


def LoadPreviewResult(path, kind, targetThread = None, cancelled = None, rendererByteLimit = None):
    if kind == "svg":
        from planner_app.graphics.svg_preview import SvgPreviewDocument, SvgPreviewRenderer
        with path.open("rb") as source:
            transport = pickle.Unpickler(source)
            value = transport.load()
            try:
                preparation = transport.load()
            except EOFError:
                preparation = None
        document = SvgPreviewDocument(value, path.stat().st_size * 2 if preparation is None else preparation["size"])
        if preparation is not None:
            document.prepared = preparation["data"]
        if targetThread is not None and (rendererByteLimit is None or document.size <= rendererByteLimit):
            from shiboken6 import delete, isValid
            renderer = SvgPreviewRenderer.__new__(SvgPreviewRenderer)
            try:
                renderer.__init__(document, cancelled = cancelled)
                if not renderer.moveToThread(targetThread):
                    raise RuntimeError("Could not transfer the SVG preview renderer.")
            except Exception:
                if isValid(renderer):
                    delete(renderer)
                raise
            document.renderer = renderer
        elif targetThread is not None:
            # Preserve the original oversized-document retention and caller
            # fallback path; its transport-only preparation is not retained.
            document.prepared = None
        return document
    with path.open("rb") as source:
        header = json.loads(source.readline())
        image = QtGui.QImage(header["width"], header["height"], QtGui.QImage.Format(header["format"]))
        if image.isNull() or image.bytesPerLine() != header["stride"] or source.readinto(image.bits()) != image.sizeInBytes():
            raise ValueError("Could not read the preview image.")
        image.setDotsPerMeterX(header["dpiX"])
        image.setDotsPerMeterY(header["dpiY"])
    return image


class PreviewAdoptionTask(QtCore.QThread):
    """Read and prepare one completed result, then transfer native SVG ownership."""
    def __init__(self, path, kind, parent):
        super().__init__(parent)
        self.path, self.kind = path, kind
        self.targetThread = parent.thread()
        self.rendererByteLimit = max(4096, parent.overlay.viewport.viewportRasterByteLimit // 2)
        self.value = self.error = None
        self.failure = None

    def run(self):
        try:
            if not self.isInterruptionRequested():
                self.value = LoadPreviewResult(self.path, self.kind, self.targetThread, self.isInterruptionRequested, self.rendererByteLimit)
        except Exception as error:
            self.failure = ExceptionDetails(error)
            self.error = self.failure["error"]


class ExportPreviewProcess(QtCore.QObject):
    def __init__(self, overlay):
        super().__init__(overlay)
        self.overlay = overlay
        self.process = QtCore.QProcess(self)
        self.process.readyReadStandardOutput.connect(self.ReadOutput)
        self.process.readyReadStandardError.connect(self.ReadDiagnostics)
        self.process.finished.connect(self.Finished)
        self.process.errorOccurred.connect(self.ProcessError)
        self.timeout = QtCore.QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.setInterval(30000)
        self.timeout.timeout.connect(self.process.kill)
        self.queue = OrderedDict()
        self.results = OrderedDict()
        self.current = self.temporary = None
        self.requests = {}
        self.counter = 0
        self.buffer = b""
        self.diagnostics = ""
        self.workerFailure = None
        self.closing = False
        self.generation = None
        self.prefetching = False
        self.adoption = self.readyResult = None
        overlay.viewport.destroyed.connect(self.Close)

    def Request(self, slot, key, renderFactory, kind, isCurrent = None):
        self.requests[slot] = key
        stored = self.results.get(slot)
        if stored is not None and stored[0] == key:
            if self.prefetching:
                return None
            self.results.move_to_end(slot)
            if stored[2]:
                raise ValueError(stored[2])
            if self.readyResult is not None and self.readyResult[:2] == (slot, key):
                value = self.readyResult[2]
                self.readyResult = None
                return value
            # Revisit a disk-only result through the same asynchronous loader.
            # None is a cached-result queue entry, never a render factory.
            self.queue[slot] = (key, None, kind, None)
            self.StartNext()
            self.overlay.previewPending = True
            return None
        if not (self.current is not None and self.current["slot"] == slot and self.current["key"] == key
                or slot in self.queue and self.queue[slot][0] == key):
            # Callers without a source-state guard retain their eager snapshot.
            # Guarded requests can discard obsolete work before scene encoding.
            try:
                render = renderFactory() if isCurrent is None else renderFactory
            except Exception as error:
                from .crash_reporting import ReportWorkerFailure
                failure = ExceptionDetails(error)
                ReportWorkerFailure("Export preview snapshot", failure["error"], failure["traceback"])
                raise ValueError(failure["error"]) from error
            self.queue[slot] = (key, render, kind, isCurrent)
        self.StartNext()
        self.overlay.previewPending = True
        return None

    def BeginFrame(self, generation):
        if generation == self.generation:
            return
        self.generation = generation
        self.DiscardReadyResult()
        if "snapshot" in self.queue or self.current is not None and self.current["slot"] == "snapshot":
            self.overlay.snapshotKey = None
        self.queue.clear()
        self.requests.clear()
        for key, path, error in self.results.values():
            if self.current is None or self.current.get("path") != path:
                path.unlink(missing_ok = True)
        self.results.clear()

    def StartNext(self):
        if self.current is not None or not self.queue or self.closing:
            return
        if self.temporary is None:
            self.temporary = tempfile.TemporaryDirectory(prefix = "planner-preview-")
        while self.queue:
            slot, (key, render, kind, isCurrent) = self.queue.popitem(last = False)
            self.counter += 1
            directory = Path(self.temporary.name)
            output = directory / f"result-{self.counter}.{'vector' if kind == 'svg' else 'frame'}"
            jobPath = directory / "job.pickle"
            stored = self.results.get(slot)
            if render is None and stored is not None and stored[0] == key:
                self.current = dict(id = self.counter, slot = slot, key = key, path = stored[1], kind = kind)
                self.Complete()
                return
            if render is None:
                continue
            self.current = dict(id = self.counter, slot = slot, key = key, path = output, kind = kind)
            self.diagnostics = ""
            self.workerFailure = None
            current = self.current
            try:
                if isCurrent is not None:
                    valid = isCurrent()
                    if self.current is not current:
                        return
                    if not valid:
                        self.current = None
                        self.overlay.viewport.update()
                        continue
                    render = render()
                    if self.current is not current:
                        return
                font = QtWidgets.QApplication.font()
                job = dict(render = render, context = slot in ("snapshot", "detail"), colors = dict(palette.themeColors), labelFont = palette.labelFont,
                           uiTheme = palette.activeUITheme, canvasTheme = palette.activeCanvasTheme,
                           style = QtWidgets.QApplication.style().objectName(), font = font.toString(),
                           fontHinting = font.hintingPreference().value, fontStrategy = font.styleStrategy().value)
                # Only this parent writes the private transport. Native bytes
                # and paths avoid repeated base64/text conversion of the catalog.
                with jobPath.open("wb") as destination:
                    pickle.dump(job, destination, protocol = pickle.HIGHEST_PROTOCOL)
            except Exception as error:
                if self.current is not current:
                    return
                self.RecordFailure(ExceptionDetails(error))
                self.Complete(self.workerFailure["error"], startNext = False)
                continue
            self.timeout.start()
            if self.process.state() == QtCore.QProcess.ProcessState.NotRunning:
                environment = QtCore.QProcessEnvironment.systemEnvironment()
                environment.insert("QT_QPA_PLATFORM", QtWidgets.QApplication.platformName())
                self.process.setProcessEnvironment(environment)
                self.process.setWorkingDirectory(str(appDirectory))
                arguments = ["--preview-worker"] if getattr(sys, "frozen", False) else [str(appDirectory / "main.py"), "--preview-worker"]
                self.process.start(sys.executable, arguments)
            self.process.write((json.dumps(dict(id = self.counter, job = str(jobPath), output = str(output))) + "\n").encode("utf-8"))
            return

    def ReadOutput(self):
        self.buffer += bytes(self.process.readAllStandardOutput())
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            if not line.startswith(b"PLANNER_PREVIEW:"):
                continue
            try:
                message = json.loads(line[len(b"PLANNER_PREVIEW:"):])
            except (ValueError, UnicodeError):
                continue
            if self.current is None or message["id"] != self.current["id"]:
                continue
            if message.get("error"):
                self.RecordFailure(message)
            self.Complete(message.get("error"))

    def RecordFailure(self, details):
        self.workerFailure = {name: details[name] for name in ("error", "exceptionType", "traceback") if name in details}
        self.diagnostics = (self.diagnostics + "\n" + details.get("traceback", ""))[-16384:]

    def ReadDiagnostics(self):
        self.diagnostics = (self.diagnostics + bytes(self.process.readAllStandardError()).decode("utf-8", errors = "replace"))[-16384:]

    def Complete(self, error = None, startNext = True, adopted = False):
        if self.adoption is not None:
            return
        current = self.current
        if error:
            from .crash_reporting import ReportWorkerFailure
            ReportWorkerFailure("Export preview", error, self.diagnostics)
        self.timeout.stop()
        if not adopted and error is None and self.requests.get(current["slot"]) == current["key"]:
            task = PreviewAdoptionTask(current["path"], current["kind"], self)
            self.adoption = task
            task.finished.connect(self.AdoptionFinished)
            task.start()
            return
        self.current = None
        slot, key, path = current["slot"], current["key"], current["path"]
        previous = self.results.pop(slot, None)
        if previous is not None and previous[1] != path:
            previous[1].unlink(missing_ok = True)
        if self.requests.get(slot) == key:
            self.results[slot] = (key, path, error)
            if slot == "model":
                self.overlay.printPageKey = None
            elif slot == "snapshot":
                self.overlay.snapshotKey = None
            elif slot == "detail":
                self.overlay.detailKey = None
            self.overlay.viewport.update()
        else:
            path.unlink(missing_ok = True)
        while self.results and (len(self.results) > 32 or sum(item[1].stat().st_size for item in self.results.values()
                                    if item[1].exists()) > self.overlay.viewport.viewportRasterByteLimit * 2):
            discarded, item = self.results.popitem(last = False)
            item[1].unlink(missing_ok = True)
            if self.readyResult is not None and self.readyResult[0] == discarded:
                self.DiscardReadyResult()
        if startNext:
            self.StartNext()

    def DiscardReadyResult(self):
        if self.readyResult is not None:
            value = self.readyResult[2]
            renderer = getattr(value, "renderer", None)
            if renderer is not None:
                renderer.deleteLater()
                value.renderer = None
            self.readyResult = None

    def AdoptionFinished(self):
        task = self.sender()
        if task is not self.adoption:
            return
        self.adoption = None
        self.DiscardReadyResult()
        current = self.current
        if self.requests.get(current["slot"]) == current["key"] and task.error is None:
            self.readyResult = current["slot"], current["key"], task.value
        else:
            renderer = getattr(task.value, "renderer", None)
            if renderer is not None:
                renderer.deleteLater()
                task.value.renderer = None
        task.value = None
        if task.failure is not None:
            self.RecordFailure(task.failure)
        task.deleteLater()
        self.Complete(task.error, adopted = True)

    def Finished(self, code, status):
        if self.closing:
            return
        if self.current is not None and self.adoption is None:
            self.ReadDiagnostics()
            error = "The preview process stopped while rendering. Change an export setting to retry."
            if self.diagnostics.strip():
                error += "\n\n" + self.diagnostics.strip()
            self.Complete(error)

    def ProcessError(self, error):
        if error == QtCore.QProcess.ProcessError.FailedToStart and self.current is not None:
            self.Complete("Could not start the preview process: " + self.process.errorString())

    def Close(self):
        self.closing = True
        self.timeout.stop()
        self.queue.clear()
        self.requests.clear()
        self.results.clear()
        self.DiscardReadyResult()
        if self.adoption is not None:
            task, self.adoption = self.adoption, None
            task.requestInterruption()
            # The task never waits on the GUI thread. Join before removing its
            # private files or destroying its QThread; native SVGs now belong here.
            task.wait()
            renderer = getattr(task.value, "renderer", None)
            if renderer is not None:
                renderer.deleteLater()
                task.value.renderer = None
            task.value = None
            task.deleteLater()
        if self.process.state() != QtCore.QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)
        self.current = None
        self.buffer = b""
        self.generation = None
        if self.temporary is not None:
            for attempt in range(4):
                try:
                    self.temporary.cleanup()
                except PermissionError as error:
                    # Windows can briefly retain a transport-file sharing lock
                    # after the worker has stopped. Retry only that exact error.
                    if getattr(error, "winerror", None) != 32 or attempt == 3:
                        raise
                    sleep(.01 * (attempt + 1))
                else:
                    self.temporary = None
                    break
        self.closing = False


def PreviewProcess(overlay):
    # Core renderer checks intentionally exercise the synchronous path. A
    # separate integration check drives the real process and event loop.
    if os.environ.get("PLANNER_SYNCHRONOUS_PREVIEW") == "1":
        return None
    if getattr(overlay, "previewProcess", None) is None:
        overlay.previewProcess = ExportPreviewProcess(overlay)
    return overlay.previewProcess
