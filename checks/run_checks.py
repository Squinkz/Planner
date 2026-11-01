"""Run UI checks in isolated processes, discarding unsaved fixtures at teardown."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import ctypes
from datetime import datetime
import json
import os
from queue import Queue
import shutil
import subprocess
import sys
import tempfile
from time import perf_counter
from pathlib import Path


def DefaultJobs():
    # Keep ordinary audits responsive on a developer workstation. A check can
    # launch a preview process with its own substantial image memory budget.
    jobs = min(4, os.process_cpu_count() or 1)
    if sys.platform == "win32":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in ("total", "available", "pageTotal",
                    "pageAvailable", "virtualTotal", "virtualAvailable", "extended")]
        memory = MemoryStatus()
        memory.length = ctypes.sizeof(memory)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            jobs = min(jobs, max(1, (memory.available - 1024 ** 3) // (2 * 1024 ** 3)))
    return jobs


def CopyWorkspace(source, destination, checks):
    # Copies, not links: many older checks write captures beside __file__, and
    # some temporarily modify source fixtures. Neither may touch another worker.
    ignored = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".venv", "venv",
        ".pytest_cache", ".mypy_cache", "*.egg-info", "build", "dist", "renders",
        "diagnostics", "screenshots", "tmp*", "*.bak", "*.log", ".env", ".env.*")
    for name in ("planner-main", "checks", "docs", "tools", "demos", ".github"):
        if (source / name).is_dir():
            shutil.copytree(source / name, destination / name, ignore = ignored)
    for name in (".gitignore", ".gitattributes", "README.md", "CONTRIBUTING.md",
                 "requirements-dev.txt", "requirements-build.txt", "LICENSE", "LICENSE.txt", "CHANGELOG.md"):
        if (source / name).is_file():
            shutil.copy2(source / name, destination / name)
    # Explicit probes inside an ignored diagnostics/tmp directory remain usable.
    for check in checks:
        if check.is_relative_to(source):
            target = destination / check.relative_to(source)
            if not target.exists():
                target.parent.mkdir(parents = True, exist_ok = True)
                shutil.copy2(check, target)
    for name in ("diagnostics", "screenshots", "tmp"):
        (destination / name).mkdir(exist_ok = True)


def Main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding = "utf-8", errors = "backslashreplace")
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("checks", nargs = "*", help = "Check paths relative to checks/, or absolute paths")
    parser.add_argument("--report", type = Path, help = "Write per-check status, duration and failure output as JSON")
    parser.add_argument("--jobs", type = int, default = os.environ.get("PLANNER_CHECK_JOBS"),
                        help = "Maximum concurrent checks (automatic, capped at 4 by default; 1 runs serially)")
    args = parser.parse_args()
    if args.jobs is not None and args.jobs < 1:
        parser.error("--jobs must be at least 1")
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetErrorMode(3)
    # Individual reference checks can import NumPy before application startup.
    # Avoid their unused BLAS pools and capture native fault details in CI.
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["PYTHONFAULTHANDLER"] = "1"
    folder = Path(__file__).resolve().parent
    for name in ("diagnostics", "screenshots", "tmp"):
        (folder.parent / name).mkdir(exist_ok = True)
    names = args.checks
    checks = [(folder / name).resolve() for name in names] if names else sorted(folder.glob("check_*.py"))
    for check in checks:
        if not check.is_file():
            parser.error(f"Check does not exist: {check}")
    jobs = min(args.jobs if args.jobs is not None else DefaultJobs(), max(1, len(checks)))
    if any(not check.is_relative_to(folder.parent) or any(check.is_relative_to(folder.parent / name)
            for name in ("diagnostics", "screenshots")) for check in checks):
        # External probes can have sibling inputs we do not own or know how to
        # copy. Probes in output directories would also be moved away when a
        # preceding check's artifacts are collected. Keep both kinds serial.
        jobs = 1
    bootstrap = """import os, runpy, sys, tempfile, threading
from pathlib import Path
from PySide6 import QtWidgets
os.environ['PLANNER_SYNCHRONOUS_PREVIEW'] = '1'
if not __debug__:
    raise RuntimeError("Checks require Python assertions; disable optimization.")
callbackErrors = []
def ReportCallbackError(errorType, error, errorTraceback):
    callbackErrors.append(error)
    sys.__excepthook__(errorType, error, errorTraceback)
sys.excepthook = ReportCallbackError
threading.excepthook = lambda args: ReportCallbackError(args.exc_type, args.exc_value, args.exc_traceback)
sys.path.insert(0, str(Path(sys.argv[1]).parent))
QtWidgets.QMessageBox.question = lambda *args: QtWidgets.QMessageBox.StandardButton.Discard
QtWidgets.QMessageBox.exec = lambda *args: QtWidgets.QMessageBox.StandardButton.Discard
with tempfile.TemporaryDirectory() as sessionFolder:
    os.environ['PLANNER_SESSION_PATH'] = str(Path(sessionFolder) / 'session.json')
    os.environ['PLANNER_STARTUP_PATH'] = str(Path(sessionFolder) / 'startup.plan')
    os.environ['PLANNER_PREFERENCES_PATH'] = str(Path(sessionFolder) / 'preferences.json')
    try:
        runpy.run_path(sys.argv[1], run_name = '__main__')
    finally:
        if callbackErrors:
            raise RuntimeError(f'{len(callbackErrors)} unhandled callback/thread exceptions occurred during this check.')
"""
    results = [None] * len(checks)
    suiteStarted = perf_counter()
    # Full catalog theme changes, repeated session launches and integration renders
    # run substantially slower on hosted Windows workers than locally.
    timeouts = {"check_external_themes.py": 120, "check_furnishings_on_counters.py": 60,
                "check_column_occlusion_preparation.py": 60, "check_room_edit_preparation.py": 60,
                "check_optimized_png_reuse.py": 60,
                "check_angled_mask_clipping.py": 120,
                "check_dorm_opening_masks.py": 60, "check_print_mode.py": 60,
                "check_about_dialog.py": 60, "check_app_preferences.py": 60, "check_canvas_theme_refresh.py": 60,
                "check_export_settings.py": 60, "check_export_solid_objects.py": 60,
                "check_export_cli_settings.py": 120, "check_parity_rendering.py": 60,
                "check_export_bounds.py": 60, "check_export_plan.py": 60,
                "check_furnishing_list_view.py": 60,
                "check_furnishing_quick_search.py": 60, "check_furnishing_sort.py": 60,
                "check_help_typography.py": 60, "check_help_viewer.py": 60,
                "check_linework_settings.py": 60,
                "check_native_paths.py": 60, "check_pan_dpi.py": 60,
                "check_session_recovery.py": 60,
                # The 200-edit/1,000-object matrix approaches 60 seconds
                # locally; allow hosted two-worker runs adequate headroom.
                "check_sparse_history.py": 120,
                "check_viewport_settings.py": 60,
                "check_stairs.py": 60, "check_startup_projects.py": 60, "check_user_furnishings.py": 60,
                "check_export_button.py": 60, "check_export_progress.py": 60, "check_optimized_png.py": 60,
                "check_export_floors.py": 60, "check_exterior_hidden_dimensions.py": 60,
                "check_selection_dimension_overlay.py": 120,
                "check_session_guide_selection.py": 60}
    # Frozen/current gesture matrices include many real-window frames and must
    # also complete at 200% scaling on slower hosted Windows workers.
    timeouts.update({name: 120 for name in ("check_flat_interactions.py", "check_flat_next.py",
        "check_local_paint.py", "check_retained_paint.py", "check_wall_boundary.py",
        "check_snap_preparation.py", "check_snap_local.py")})
    root = folder.parent
    runId = datetime.now().strftime("%Y%m%d-%H%M%S-%f") + f"-{os.getpid()}"
    artifactRoot = root / "diagnostics" / "check-runs" / runId
    workspaces = Queue()

    def RunCheck(index):
        check = checks[index]
        workspace = workspaces.get()
        childCheck = workspace / check.relative_to(root) if check.is_relative_to(root) else check
        # Nested runner regression checks must not multiply the outer worker pool.
        environment = dict(os.environ, PLANNER_CHECK_JOBS = "1", PYTHONUTF8 = "1", PYTHONIOENCODING = "utf-8")
        timeout = timeouts.get(check.name, 30) * max(1, (jobs + 1) // 2)
        started = perf_counter()
        try:
            with tempfile.TemporaryDirectory(prefix = "check-", dir = workspace / "tmp") as tempFolder:
                environment.update(TEMP = tempFolder, TMP = tempFolder, TMPDIR = tempFolder)
                try:
                    completed = subprocess.run([sys.executable, "-c", bootstrap, str(childCheck)],
                        cwd = workspace, env = environment, capture_output = True, text = True,
                        encoding = "utf-8", errors = "replace", timeout = timeout)
                    result = dict(check = check.name, status = "failed" if completed.returncode else "passed",
                        seconds = round(perf_counter() - started, 3), timeoutSeconds = timeout,
                        returnCode = completed.returncode, stdout = completed.stdout, stderr = completed.stderr)
                except subprocess.TimeoutExpired as error:
                    stdout, stderr = error.stdout or "", error.stderr or ""
                    stdout = stdout.decode("utf-8", "replace") if isinstance(stdout, bytes) else stdout
                    stderr = stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else stderr
                    result = dict(check = check.name, status = "timeout", seconds = round(perf_counter() - started, 3),
                        timeoutSeconds = timeout, returnCode = None, stdout = stdout, stderr = stderr)
            if jobs > 1:
                for name in ("diagnostics", "screenshots"):
                    generated = workspace / name
                    if any(generated.iterdir()):
                        target = artifactRoot / f"{index + 1:03d}-{check.stem}" / name
                        # Both paths are constructed beneath our own output roots.
                        assert generated.resolve().is_relative_to(workspace.resolve())
                        assert target.resolve().is_relative_to(artifactRoot.resolve())
                        target.parent.mkdir(parents = True, exist_ok = True)
                        shutil.move(str(generated), str(target))
                        generated.mkdir()
                        result["artifacts"] = str(target.parent.relative_to(root))
            return result
        except OSError as error:
            return dict(check = check.name, status = "failed", seconds = round(perf_counter() - started, 3),
                        timeoutSeconds = timeout, returnCode = None, stdout = "", stderr = str(error))
        finally:
            workspaces.put(workspace)

    def RecordResult(index, result):
        results[index] = result
        count = sum(entry is not None for entry in results)
        print(f"[{count}/{len(checks)}] {result['check']}: {result['status']} ({result['seconds']:.1f}s)", flush = True)
        if result["status"] != "passed":
            log = artifactRoot / f"{index + 1:03d}-{checks[index].stem}" / "failure.json"
            log.parent.mkdir(parents = True, exist_ok = True)
            result.setdefault("artifacts", str(log.parent.relative_to(root)))
            log.write_text(json.dumps(result, indent = 2), encoding = "utf-8")
            print(result["stdout"], result["stderr"], flush = True)

    print(f"Running {len(checks)} checks with {jobs} worker{'s' if jobs != 1 else ''}", flush = True)
    if jobs == 1:
        workspaces.put(root)
        for index in range(len(checks)):
            RecordResult(index, RunCheck(index))
    else:
        # Disposable copies isolate source-relative output without modifying the
        # checks' fixture paths. They never include private workspace drawings.
        with tempfile.TemporaryDirectory(prefix = "check-workers-", dir = root / "tmp") as directory:
            workerFolder = Path(directory).resolve()
            assert workerFolder.is_relative_to((root / "tmp").resolve())
            for number in range(jobs):
                workspace = workerFolder / str(number + 1)
                CopyWorkspace(root, workspace, checks)
                workspaces.put(workspace)
            nativeChecks = {"check_export_text_paths.py", "check_title_block_native_raster.py"}
            with ThreadPoolExecutor(max_workers = jobs) as pool:
                futures = {pool.submit(RunCheck, index): index for index, check in enumerate(checks)
                           if check.name not in nativeChecks}
                try:
                    for future in as_completed(futures):
                        index = futures[future]
                        RecordResult(index, future.result())
                except BaseException:
                    # An interrupted audit must not launch the remaining queue.
                    for future in futures:
                        future.cancel()
                    raise
            # Real desktop font/clipboard state must not compete with other checks.
            for index, check in enumerate(checks):
                if check.name in nativeChecks:
                    RecordResult(index, RunCheck(index))
    failures = [entry for entry in results if entry["status"] != "passed"]
    if args.report is not None:
        args.report.parent.mkdir(parents = True, exist_ok = True)
        args.report.write_text(json.dumps(dict(format = "Planner check results", version = 1,
            total = len(checks), passed = len(checks) - len(failures), failed = len(failures),
            seconds = round(perf_counter() - suiteStarted, 3), jobs = jobs,
            results = results), indent = 2), encoding = "utf-8")
    print(f"{len(checks) - len(failures)}/{len(checks)} checks passed", flush = True)
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    Main()
