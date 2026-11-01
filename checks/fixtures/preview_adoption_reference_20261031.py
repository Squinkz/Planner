"""Coalesce preview work in one persistent process; adopt only current results."""
from collections import OrderedDict
import json
import os
import pickle
from pathlib import Path
import sys
import tempfile
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.graphics import palette
from planner_app.paths import appDirectory


class ExportPreviewProcess(QtCore.QObject):
    def __init__(self, overlay):
        super().__init__(overlay)
        self.overlay = overlay
        self.process = QtCore.QProcess(self)
        self.process.readyReadStandardOutput.connect(self.ReadOutput)
        self.process.readyReadStandardError.connect(lambda: self.process.readAllStandardError())
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
        self.closing = False
        self.generation = None
        self.prefetching = False
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
            path = stored[1]
            if kind == "svg":
                from planner_app.graphics.svg_preview import SvgPreviewDocument
                with path.open("rb") as source:
                    return SvgPreviewDocument(pickle.load(source), path.stat().st_size * 2)
            with path.open("rb") as source:
                header = json.loads(source.readline())
                image = QtGui.QImage(header["width"], header["height"], QtGui.QImage.Format(header["format"]))
                if image.isNull() or image.bytesPerLine() != header["stride"] or source.readinto(image.bits()) != image.sizeInBytes():
                    raise ValueError("Could not read the preview image.")
                image.setDotsPerMeterX(header["dpiX"])
                image.setDotsPerMeterY(header["dpiY"])
            return image
        if not (self.current is not None and self.current["slot"] == slot and self.current["key"] == key
                or slot in self.queue and self.queue[slot][0] == key):
            # Callers without a source-state guard retain their eager snapshot.
            # Guarded requests can discard obsolete work before scene encoding.
            self.queue[slot] = (key, renderFactory() if isCurrent is None else renderFactory, kind, isCurrent)
        self.StartNext()
        self.overlay.previewPending = True
        return None

    def BeginFrame(self, generation):
        if generation == self.generation:
            return
        self.generation = generation
        if "snapshot" in self.queue or self.current is not None and self.current["slot"] == "snapshot":
            self.overlay.snapshotKey = None
        self.queue.clear()
        self.requests.clear()
        for key, path, error in self.results.values():
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
            self.current = dict(id = self.counter, slot = slot, key = key, path = output)
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
                self.Complete(str(error), startNext = False)
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
            self.Complete(message.get("error"))

    def Complete(self, error = None, startNext = True):
        current = self.current
        self.timeout.stop()
        self.current = None
        slot, key, path = current["slot"], current["key"], current["path"]
        previous = self.results.pop(slot, None)
        if previous is not None:
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
        if startNext:
            self.StartNext()

    def Finished(self, code, status):
        if self.closing:
            return
        if self.current is not None:
            self.Complete("The preview process stopped while rendering. Change an export setting to retry.")

    def ProcessError(self, error):
        if error == QtCore.QProcess.ProcessError.FailedToStart and self.current is not None:
            self.Complete("Could not start the preview process: " + self.process.errorString())

    def Close(self):
        self.closing = True
        self.timeout.stop()
        self.queue.clear()
        self.requests.clear()
        self.results.clear()
        if self.process.state() != QtCore.QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)
        self.current = None
        self.buffer = b""
        self.generation = None
        if self.temporary is not None:
            self.temporary.cleanup()
            self.temporary = None
        self.closing = False


def PreviewProcess(overlay):
    # Core renderer checks intentionally exercise the synchronous path. A
    # separate integration check drives the real process and event loop.
    if os.environ.get("PLANNER_SYNCHRONOUS_PREVIEW") == "1":
        return None
    if getattr(overlay, "previewProcess", None) is None:
        overlay.previewProcess = ExportPreviewProcess(overlay)
    return overlay.previewProcess
