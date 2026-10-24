"""Isolated native Windows CPU/event-loop and working-set soak (not PresentMon)."""
import argparse
import ctypes
from ctypes import wintypes
import gc
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
from time import perf_counter

root = Path(__file__).resolve().parent.parent
(root / "diagnostics").mkdir(exist_ok = True)
sys.path.insert(0, str(root / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow, Wall, Door
from planner_app.graphics import icons
from planner_app.graphics.theme import ApplyApplicationTheme


class MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD),
               ("peakWorkingSet", ctypes.c_size_t), ("workingSet", ctypes.c_size_t),
               ("peakPagedPool", ctypes.c_size_t), ("pagedPool", ctypes.c_size_t),
               ("peakNonPagedPool", ctypes.c_size_t), ("nonPagedPool", ctypes.c_size_t),
               ("pagefile", ctypes.c_size_t), ("peakPagefile", ctypes.c_size_t), ("privateBytes", ctypes.c_size_t)]


def Main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--seconds", type = int, default = 1200)
    parser.add_argument("--switch-projects", action = "store_true")
    parser.add_argument("--output", type = Path, default = root / "diagnostics/native-render-soak-20261008.json")
    args = parser.parse_args()
    if sys.platform != "win32" or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        raise RuntimeError("Run this probe on native Windows, without QT_QPA_PLATFORM=offscreen")
    kernel = ctypes.WinDLL("kernel32", use_last_error = True)
    psapi = ctypes.WinDLL("psapi", use_last_error = True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    with tempfile.TemporaryDirectory(prefix = "planner-native-soak-") as folder:
        os.environ["PLANNER_SESSION_PATH"] = str(Path(folder) / "session.json")
        os.environ["PLANNER_STARTUP_PATH"] = str(Path(folder) / "startup.plan")
        app = QtWidgets.QApplication([])
        app.setApplicationName("Planner isolated render soak")
        app.setStyle("Fusion")
        ApplyApplicationTheme(app)
        main = MainWindow()
        v = main.viewport
        point = QtCore.QPointF
        v.walls = [Wall(point((index % 20) * 1800, (index // 20) * 1600),
                        point((index % 20) * 1800 + 1500, (index // 20) * 1600), 180) for index in range(200)]
        v.windows = [Door(wall, .2, .4) for wall in v.walls[::10]]
        v.EnsureObjectIds()
        v.sceneRevision += 1
        v.sceneChanged.emit()
        v.SetRenderDiagnosticsEnabled(True)
        main.setWindowTitle("Planner — isolated 20-minute rendering validation")
        main.resize(1441, 901)
        main.show()
        fixturePath = Path(folder) / "native-fixture.plan"
        main.MarkProjectClean()
        fixturePath.write_text(json.dumps(main.BuildProjectData()), encoding = "utf-8")
        sourcePaths = [root / "planner-main/planner_app" / name for name in (
            "models.py", "scene_changes.py", "viewport/rendering.py", "viewport/geometry.py", "viewport/scene.py", "graphics/icons.py")]
        sourceHashes = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sourcePaths}
        started = perf_counter()
        samples = []
        failures = []
        ticks = 0
        projectSwitches = 0

        def Tick():
            nonlocal ticks, projectSwitches
            ticks += 1
            elapsed = perf_counter() - started
            try:
                phase = ticks % 120
                if v.exportOverlay.active and v.exportOverlay.previewError:
                    raise RuntimeError(v.exportOverlay.previewError)
                if phase < 70 and main.sidebarTabs.currentIndex() != 3:
                    v.isPanning = True
                    v.panOffset += point(3 if phase % 2 else .4, 1)
                else:
                    v.isPanning = False
                if ticks % 15 == 0:
                    before = v.CaptureState()
                    v.walls[0].secondVertex.setY(((ticks // 15) % 3) * 100)
                    v.RecordEdit(before)
                    v.ZoomBy(1.1 if ticks % 30 else 1 / 1.1, v.DrawingRect().center())
                if ticks % 25 == 0:
                    main.resize(1441 + (ticks % 3) * 31, 901 + (ticks % 4) * 17)
                if ticks % 90 == 0:
                    main.sidebarTabs.setCurrentIndex(3 if main.sidebarTabs.currentIndex() != 3 else 0)
                if ticks % 30 == 0 and main.sidebarTabs.currentIndex() == 3:
                    panel = main.exportPanel
                    panel.typeField.setCurrentText("SVG" if panel.typeField.currentText() == "PNG" else "PNG")
                if ticks % 60 == 0:
                    themes = ("Dark UI", "Light UI", "Neutral UI")
                    main.SetThemes(uiTheme = themes[(ticks // 60) % 3])
                    icons.PruneArtworkCaches()
                    gc.collect()
                    if args.switch_projects:
                        main.sidebarTabs.setCurrentIndex(0)
                        main.MarkProjectClean()
                        if not main.OpenProject(fixturePath):
                            raise RuntimeError("Native fixture reload failed")
                        projectSwitches += 1
                v.update()
                if ticks % 5 == 0:
                    memory = MemoryCounters()
                    memory.cb = ctypes.sizeof(memory)
                    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(memory), memory.cb):
                        raise ctypes.WinError(ctypes.get_last_error())
                    retained = v.rasterCacheBudget.RetainedBytes()
                    if retained > v.viewportRasterByteLimit:
                        raise AssertionError("Retained raster budget exceeded")
                    samples.append({"seconds": elapsed, "workingSet": memory.workingSet, "privateBytes": memory.privateBytes,
                                    "retainedRasterBytes": retained, "iconSources": len(icons.iconSources),
                                    "pixmapSources": len(icons.pixmapSources), "paths": len(icons.uiIconCache)})
                if elapsed >= args.seconds:
                    timer.stop()
                    v.isPanning = False
                    main.MarkProjectClean()
                    main.close()
            except Exception as error:
                failures.append({"seconds": elapsed, "error": repr(error)})
                timer.stop()
                main.MarkProjectClean()
                main.close()
        timer = QtCore.QTimer(main)
        timer.setInterval(200)
        timer.timeout.connect(Tick)
        timer.start()
        app.exec()
        diagnostics = v.renderDiagnostics
        diagnostics.Stop()
        report = diagnostics.Report()
        halves = [sample for sample in samples if sample["seconds"] >= args.seconds / 2]
        report.update(requestedSeconds = args.seconds, elapsedSeconds = perf_counter() - started,
                      projectSwitches = projectSwitches, sourceHashes = sourceHashes,
                      sourceUnchanged = all(hashlib.sha256(path.read_bytes()).hexdigest() == sourceHashes[str(path.relative_to(root))] for path in sourcePaths),
                      platformPlugin = app.platformName(), devicePixelRatio = v.devicePixelRatioF(),
                      memorySamples = samples, failures = failures,
                      lastHalfWorkingSetRange = [min(sample["workingSet"] for sample in halves), max(sample["workingSet"] for sample in halves)] if halves else None,
                      note = "Native Qt paint/event-loop timings and process memory. No app-specific GPU presentation or input-to-photon measurements.")
        output = args.output
        output.write_text(json.dumps(report, indent = 2) + "\n", encoding = "utf-8")
        print(f"Saved {output}; elapsed {report['elapsedSeconds']:.1f}s; failures {len(failures)}", flush = True)
        if failures or report["elapsedSeconds"] < args.seconds:
            raise SystemExit(1)


if __name__ == "__main__":
    Main()
