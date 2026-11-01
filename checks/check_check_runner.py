"""Runner isolation, callback/thread failures, exit codes and structured reports."""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
from time import perf_counter
from unittest.mock import patch


def Main():
    runner = Path(__file__).with_name("run_checks.py")
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory).resolve()
        report = folder / "results.json"
        scripts = {
            "pass.py": """import os
from pathlib import Path
for name in ('PLANNER_SESSION_PATH', 'PLANNER_STARTUP_PATH', 'PLANNER_PREFERENCES_PATH'):
    assert Path(os.environ[name]).parent.is_dir()
    assert os.environ[name] != os.environ.get('RUNNER_PARENT_' + name)
assert os.environ['OPENBLAS_NUM_THREADS'] == '1'
assert os.environ['PYTHONFAULTHANDLER'] == '1'
print('Unicode report: 297 × 210 mm')
""",
            "assertion.py": "assert False, 'deliberate assertion failure ∞'\n",
            "callback.py": """from PySide6 import QtCore, QtWidgets, QtTest
app = QtWidgets.QApplication([])
def Fail():
    raise RuntimeError('deliberate Qt callback failure')
QtCore.QTimer.singleShot(0, Fail)
QtTest.QTest.qWait(20)
""",
            "thread.py": """import threading
def Fail():
    raise RuntimeError('deliberate thread failure')
thread = threading.Thread(target = Fail)
thread.start()
thread.join()
"""}
        for name, script in scripts.items():
            (folder / name).write_text(script, encoding = "utf-8")
        # Simulate a redirected Windows console even on UTF-8 CI machines.
        environment = dict(os.environ, PYTHONUTF8 = "1", PYTHONIOENCODING = "cp1252")
        for name in ("PLANNER_SESSION_PATH", "PLANNER_STARTUP_PATH", "PLANNER_PREFERENCES_PATH"):
            environment["RUNNER_PARENT_" + name] = os.environ.get(name, "")
        result = subprocess.run([sys.executable, str(runner), *(str(folder / name) for name in scripts),
                                 "--report", str(report)], env = environment, capture_output = True,
                                text = True, encoding = "utf-8", timeout = 20)
        assert result.returncode == 1, result.stdout + result.stderr
        recorded = json.loads(report.read_text(encoding = "utf-8"))
        assert (recorded["total"], recorded["passed"], recorded["failed"]) == (4, 1, 3)
        assert [entry["status"] for entry in recorded["results"]] == ["passed", "failed", "failed", "failed"]
        assert "297 × 210" in recorded["results"][0]["stdout"]
        assert "∞" in recorded["results"][1]["stderr"]
        assert "∞" in result.stdout
        for entry, message in zip(recorded["results"][1:], ("deliberate assertion", "deliberate Qt callback", "deliberate thread")):
            assert message in entry["stderr"] and entry["returnCode"] != 0, entry
        assert all(entry["seconds"] >= 0 and entry["timeoutSeconds"] >= 30 for entry in recorded["results"])
        # Exercise timeout accounting without burning 30 seconds or leaving a
        # hanging process. Real subprocess behavior is covered above.
        module = runpy.run_path(str(runner), run_name = "runner_test")
        with patch.object(sys, "argv", [str(runner), str(folder / "pass.py"), "--jobs", "1", "--report", str(report)]), \
                patch.object(subprocess, "run", side_effect = subprocess.TimeoutExpired("fixture", 30,
                    output = "partial × output".encode("utf-8"), stderr = b"timeout detail")), \
                contextlib.redirect_stdout(io.StringIO()):
            try:
                module["Main"]()
            except SystemExit as error:
                assert error.code == 1
            else:
                raise AssertionError("Timeout returned success")
        recorded = json.loads(report.read_text(encoding = "utf-8"))
        assert recorded["failed"] == 1 and recorded["results"][0]["status"] == "timeout"
        assert "partial × output" in recorded["results"][0]["stdout"]
        assert recorded["results"][0]["stderr"] == "timeout detail"

        # A rendezvous proves real overlap without imposing a machine-specific
        # speed target. Every check writes the same capture path and modifies its
        # own copied fixture; neither may affect another worker or this checkout.
        with tempfile.NamedTemporaryFile(prefix = "runner-fixture-", suffix = ".txt", dir = runner.parent,
                mode = "w", encoding = "utf-8", delete_on_close = False) as sourceFixture, \
                tempfile.TemporaryDirectory(prefix = "tmp-runner-", dir = runner.parent) as scriptsDirectory:
            scriptsFolder = Path(scriptsDirectory).resolve()
            fixture = Path(sourceFixture.name).resolve()
            sourceFixture.write("original fixture")
            sourceFixture.flush()
            parallelScripts = []
            for index in range(4):
                script = scriptsFolder / f"parallel_{index}.py"
                script.write_text(f"""import os, time
from pathlib import Path
root = Path(__file__).resolve().parents[2]
shared = Path(os.environ['RUNNER_COORDINATION'])
index = {index}
assert os.environ['PLANNER_CHECK_JOBS'] == '1'
assert Path(os.environ['TEMP']).resolve().is_relative_to(root / 'tmp')
active = shared / ('active-' + str(index))
active.touch()
try:
    assert len(list(shared.glob('active-*'))) <= 2, 'worker limit exceeded'
    (shared / ('arrived-' + str(index))).touch()
    deadline = time.monotonic() + 10
    while index < 2 and len(list(shared.glob('arrived-*'))) < 2:
        assert time.monotonic() < deadline, 'checks did not run concurrently'
        time.sleep(.01)
    capture = root / 'diagnostics' / 'shared.txt'
    with capture.open('x', encoding = 'utf-8') as output:
        output.write(str(index))
    fixture = root / 'checks' / {fixture.name!r}
    assert fixture.is_file(), 'source fixture was not copied'
    fixture.write_text(str(index), encoding = 'utf-8')
    time.sleep(.05)
    assert fixture.read_text(encoding = 'utf-8') == str(index), 'workers share source files'
finally:
    active.unlink()
assert index != 3, 'deliberate parallel failure'
""", encoding = "utf-8")
                parallelScripts.append(script)
            native = scriptsFolder / "check_title_block_native_raster.py"
            native.write_text("import os\nfrom pathlib import Path\n"
                "shared = Path(os.environ['RUNNER_COORDINATION'])\n"
                "assert len(list(shared.glob('arrived-*'))) == 4\n"
                "assert not list(shared.glob('active-*')), 'desktop check overlapped the parallel batch'\n",
                encoding = "utf-8")
            environment["RUNNER_COORDINATION"] = str(folder)
            started = perf_counter()
            result = subprocess.run([sys.executable, str(runner), *(str(path) for path in parallelScripts),
                str(native), "--jobs", "2", "--report", str(report)], env = environment,
                capture_output = True, text = True, encoding = "utf-8", timeout = 40)
            assert result.returncode == 1, result.stdout + result.stderr
            recorded = json.loads(report.read_text(encoding = "utf-8"))
            assert recorded["jobs"] == 2 and (recorded["passed"], recorded["failed"]) == (4, 1)
            assert [entry["status"] for entry in recorded["results"]] == ["passed"] * 3 + ["failed", "passed"]
            assert "deliberate parallel failure" in recorded["results"][3]["stderr"]
            assert [entry["check"] for entry in recorded["results"]] == [path.name for path in parallelScripts] + [native.name]
            assert fixture.read_text(encoding = "utf-8") == "original fixture"
            artifactDirectories = []
            for index, entry in enumerate(recorded["results"][:4]):
                artifactDirectory = runner.parent.parent / entry["artifacts"]
                artifactDirectories.append(artifactDirectory)
                assert (artifactDirectory / "diagnostics/shared.txt").read_text(encoding = "utf-8") == str(index)
            assert len(set(artifactDirectories)) == 4
            print(f"Parallel runner isolation verified in {perf_counter() - started:.1f}s")
    # An explicit diagnostic is an input, even though its directory normally
    # holds movable output. Artifact collection must not remove a later probe.
    with tempfile.TemporaryDirectory(prefix = "runner-probes-", dir = runner.parent.parent / "diagnostics") as directory:
        folder = Path(directory).resolve()
        scripts = [folder / f"probe_{index}.py" for index in range(2)]
        for script in scripts:
            script.write_text("from pathlib import Path\nassert Path(__file__).is_file()\n", encoding = "utf-8")
        report = folder / "results.json"
        result = subprocess.run([sys.executable, str(runner), *(str(script) for script in scripts),
            "--jobs", "2", "--report", str(report)], capture_output = True, text = True, encoding = "utf-8", timeout = 20)
        assert result.returncode == 0, result.stdout + result.stderr
        recorded = json.loads(report.read_text(encoding = "utf-8"))
        assert recorded["jobs"] == 1 and recorded["passed"] == 2
        assert all(script.is_file() for script in scripts)
    print("Runner preserves isolation/Unicode, reports failures/timeouts, bounds parallel work and serializes native checks and diagnostic inputs")


if __name__ == "__main__":
    Main()
