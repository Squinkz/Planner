"""Cancellable modal export with rendering and encoding isolated from the editor."""
import json
import os
from pathlib import Path
import sys
import tempfile

from PySide6 import QtCore, QtWidgets
from planner_app.graphics.theme import HeaderIcon
from planner_app.graphics import palette
from planner_app.paths import appDirectory
from planner_app.export_worker import ExportJobEncoder


class ExportProgressDialog(QtWidgets.QDialog):
    def __init__(self, panel, path, outputFormat, optimized):
        super().__init__(panel.mainWindow)
        self.panel, self.path = panel, path
        self.outputFormat, self.optimized = outputFormat, optimized
        self.cancelled = False
        self.error = None
        self.completed = False
        self.temporary = None
        self.stagingPath = None
        self.pendingOutput = b""
        self.diagnostics = ""
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
            descriptor, staging = tempfile.mkstemp(prefix = ".planner-export-", suffix = ".tmp", dir = self.path.parent)
            os.close(descriptor)
            self.stagingPath = Path(staging)
            render = self.panel.RenderArguments(self.outputFormat)
            render["planPath"] = str(render["planPath"])
            # Reference images are never exported; do not duplicate their embedded
            # raster data or decode it again in the export process.
            render["projectData"]["settings"].pop("referenceImage", None)
            job = {"render": render, "optimized": self.optimized, "stagingPath": staging,
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
            self.error = str(error)
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
        try:
            if succeeded:
                os.replace(self.stagingPath, self.path)
            elif not self.cancelled and not self.error:
                self.error = "The export process stopped unexpectedly."
                if self.diagnostics.strip():
                    self.error += "\n\n" + self.diagnostics.strip()
        except OSError as error:
            succeeded = False
            self.error = str(error)
        finally:
            try:
                if self.stagingPath is not None:
                    self.stagingPath.unlink(missing_ok = True)
                if self.temporary is not None:
                    self.temporary.cleanup()
            except OSError as error:
                if not succeeded and not self.cancelled and not self.error:
                    self.error = str(error)
        self.completed = True
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
