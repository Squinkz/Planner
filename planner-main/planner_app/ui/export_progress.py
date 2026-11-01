"""Cancellable modal export with rendering and encoding isolated from the editor."""
import json
import os
from pathlib import Path
import sys
import tempfile
import shutil

from PySide6 import QtCore, QtWidgets
from planner_app.graphics.theme import HeaderIcon
from planner_app.graphics import palette
from planner_app.paths import appDirectory
from planner_app.export_worker import ExportJobEncoder


class ExportProgressDialog(QtWidgets.QDialog):
    def __init__(self, panel, path, outputFormat, optimized, jobs = None):
        super().__init__(panel.mainWindow)
        self.panel, self.path = panel, path
        self.jobs = jobs
        self.outputFormat, self.optimized = outputFormat, optimized
        self.pdf = outputFormat in ("pdf_raster", "pdf_vector")
        self.cancelled = False
        self.error = None
        self.completed = False
        self.temporary = None
        self.stagingPath = None
        self.outputFiles = []
        self.pendingOutput = b""
        self.diagnostics = ""
        self.workerFailure = None
        self.setWindowTitle("Exporting")
        self.setWindowIcon(HeaderIcon("Export"))
        self.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        self.setMinimumWidth(380)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        filename = QtWidgets.QLabel(path.name)
        filename.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        filename.setWordWrap(True)
        layout.addWidget(filename)
        self.statusLabel = QtWidgets.QLabel("Preparing plan")
        layout.addWidget(self.statusLabel)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setAccessibleName("Export progress")
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        self.cancelButton = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.process = QtCore.QProcess(self)
        self.process.readyReadStandardOutput.connect(self.ReadOutput)
        self.process.readyReadStandardError.connect(self.ReadDiagnostics)
        self.process.errorOccurred.connect(self.ProcessError)
        self.process.finished.connect(self.Finished)
        QtCore.QTimer.singleShot(0, self.Start)

    def Start(self):
        if self.completed or self.cancelled:
            return
        try:
            self.temporary = tempfile.TemporaryDirectory(prefix = "planner-export-")
            self.path.parent.mkdir(parents = True, exist_ok = True)
            pages = []
            baseRender = None
            jobs, self.jobs = self.jobs, None
            if jobs is None:
                jobs = self.panel.ExportJobs(self.path, self.outputFormat)
            for target, render in jobs:
                if self.pdf and self.outputFiles:
                    if target != self.outputFiles[0][1]:
                        raise ValueError("PDF pages must share one output file.")
                    staging = str(self.outputFiles[0][0])
                else:
                    descriptor, staging = tempfile.mkstemp(prefix = ".planner-export-", suffix = ".tmp", dir = target.parent)
                    os.close(descriptor)
                    self.outputFiles.append((Path(staging), target))
                render["planPath"] = str(render["planPath"])
                render["projectData"]["settings"].pop("referenceImage", None)
                if baseRender is None:
                    baseRender = render
                # A batch shares its scene/catalog; serialize only page-specific
                # differences rather than duplicating the whole project per page.
                overrides = {key: value for key, value in render.items() if key not in baseRender or
                             (value is not baseRender[key] and value != baseRender[key])}
                pages.append(dict(render = overrides, stagingPath = staging))
            self.stagingPath = self.outputFiles[0][0]
            job = {"render": baseRender, "optimized": self.optimized, "pdf": self.pdf, "stagingPath": str(self.stagingPath), "pages": pages,
                   "style": QtWidgets.QApplication.style().objectName(), "uiTheme": palette.activeUITheme,
                   "canvasTheme": palette.activeCanvasTheme, "colors": dict(palette.themeColors), "labelFont": palette.labelFont}
            font = QtWidgets.QApplication.font()
            job.update(font = font.toString(), fontHinting = font.hintingPreference().value, fontStrategy = font.styleStrategy().value)
            jobPath = Path(self.temporary.name) / "job.json"
            jobPath.write_text(json.dumps(job, ensure_ascii = False, cls = ExportJobEncoder), encoding = "utf-8")
            environment = QtCore.QProcessEnvironment.systemEnvironment()
            # No worker widgets are shown. Keep the editor's platform backend
            # so text uses the same font engine and DPI rules.
            environment.insert("QT_QPA_PLATFORM", QtWidgets.QApplication.platformName())
            self.process.setProcessEnvironment(environment)
            if getattr(sys, "frozen", False):
                arguments = ["--export-worker", str(jobPath)]
            else:
                arguments = [str(appDirectory / "main.py"), "--export-worker", str(jobPath)]
            self.process.start(sys.executable, arguments)
        except Exception as error:
            from planner_app.crash_reporting import ExceptionDetails
            self.workerFailure = ExceptionDetails(error)
            self.error = self.workerFailure["error"]
            self.diagnostics = self.workerFailure["traceback"]
            self.Finished(1, QtCore.QProcess.ExitStatus.NormalExit)

    def ReadOutput(self):
        self.pendingOutput += bytes(self.process.readAllStandardOutput())
        while b"\n" in self.pendingOutput:
            line, self.pendingOutput = self.pendingOutput.split(b"\n", 1)
            if not line.startswith(b"PLANNER_EXPORT:"):
                continue
            try:
                message = json.loads(line[len(b"PLANNER_EXPORT:"):])
            except (ValueError, UnicodeError):
                continue
            if "error" in message:
                self.error = message["error"]
                self.diagnostics = (self.diagnostics + "\n" + message.get("traceback", ""))[-16384:]
                self.workerFailure = {name: message[name] for name in ("exceptionType", "traceback") if name in message}
            if "stage" in message and not self.cancelled:
                self.statusLabel.setText(message["stage"])

    def ReadDiagnostics(self):
        self.diagnostics = (self.diagnostics + bytes(self.process.readAllStandardError()).decode("utf-8", errors = "replace"))[-8192:]

    def ProcessError(self, error):
        if error == QtCore.QProcess.ProcessError.FailedToStart:
            self.error = "Could not start the export process: " + self.process.errorString()
            self.Finished(1, QtCore.QProcess.ExitStatus.NormalExit)

    def Finished(self, exitCode, exitStatus):
        if self.completed:
            return
        self.ReadOutput()
        self.ReadDiagnostics()
        succeeded = not self.cancelled and not self.error and exitCode == 0 and exitStatus == QtCore.QProcess.ExitStatus.NormalExit
        backups, published, preserved = [], [], set()
        try:
            if succeeded:
                for staging, target in self.outputFiles:
                    if target.exists():
                        descriptor, backup = tempfile.mkstemp(prefix = ".planner-export-", suffix = ".bak", dir = target.parent)
                        os.close(descriptor)
                        backup = Path(backup)
                        # Copy first: a failed replacement must leave the original intact.
                        try:
                            shutil.copy2(target, backup)
                        except OSError:
                            backup.unlink(missing_ok = True)
                            raise
                        backups.append((backup, target))
                    os.replace(staging, target)
                    published.append(target)
            elif not self.cancelled and not self.error:
                self.error = "The export process stopped unexpectedly."
                if self.diagnostics.strip():
                    self.error += "\n\n" + self.diagnostics.strip()
        except OSError as error:
            succeeded = False
            self.error = str(error)
            originals = {target for backup, target in backups}
            for target in published:
                if target not in originals:
                    try:
                        target.unlink(missing_ok = True)
                    except OSError as cleanupError:
                        self.error += "\n" + str(cleanupError)
            for backup, target in backups:
                try:
                    os.replace(backup, target)
                except OSError as restoreError:
                    preserved.add(backup)
                    self.error += f"\nCould not restore {target}: {restoreError}. Original preserved at {backup}"
        finally:
            try:
                for staging, target in self.outputFiles:
                    staging.unlink(missing_ok = True)
                for backup, target in backups:
                    if backup not in preserved:
                        backup.unlink(missing_ok = True)
                if self.temporary is not None:
                    self.temporary.cleanup()
            except OSError as error:
                if not succeeded and not self.cancelled and not self.error:
                    self.error = str(error)
        self.completed = True
        if self.error:
            from planner_app.crash_reporting import ReportWorkerFailure
            ReportWorkerFailure("Export", self.error, self.diagnostics)
        self.jobs = None
        self.done(QtWidgets.QDialog.DialogCode.Accepted if succeeded else QtWidgets.QDialog.DialogCode.Rejected)

    def reject(self):
        if self.completed:
            super().reject()
            return
        self.cancelled = True
        self.statusLabel.setText("Cancelling…")
        self.cancelButton.setEnabled(False)
        if self.process.state() != QtCore.QProcess.ProcessState.NotRunning:
            self.process.kill()
        else:
            self.Finished(1, QtCore.QProcess.ExitStatus.NormalExit)

    def closeEvent(self, event):
        if self.completed:
            super().closeEvent(event)
        else:
            event.ignore()
            self.reject()
