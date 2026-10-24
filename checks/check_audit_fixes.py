"""Security boundaries, portable assets, recovery ownership and export failure safety."""
import base64
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
workspace = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(workspace / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets
from planner_app.catalog import LoadFurnishings
from planner_app.export_plan import RenderPlan, WriteExportFile
from planner_app.furnishing_limits import FurnishingExpansionSizes
from planner_app.graphics.furnishings import CompoundFurnishingSvg
from planner_app.models import Furnishing, Wall
from planner_app.project_codec import DecodeProject, DecodeFurnishingDefinitions, ReadProjectBytes
from planner_app.project_recovery import RecoverProject
from planner_app.svg_safety import ValidateFurnishingSvg
from planner_app.ui.main_window import MainWindow
from planner_app.ui.session import AcquireSessionLock
from planner_app.viewport.geometry import FootprintGeometry
from planner_app.viewport.widget import DrawingViewport


def Main():
    app = QtWidgets.QApplication([])
    assert tuple(int(part) for part in QtCore.qVersion().split(".")[:3]) >= (6, 11, 2)
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100"/></svg>'
    unsafe = [
        '<image href="C:/private/image.png"/>', '<image href="//server/share/image.png"/>',
        '<image href="https://example.com/image.png"/>', '<image href="file:///private/image.png"/>',
        '<style>path {fill:url(C:/private/image.svg)}</style>',
        '<style>@import "https://example.com/style.css";</style>',
        '<path style="fill:u\\72l(C:/private/image.svg)"/>',
        '<g xml:base="C:/private/"><use href="#shape"/></g>', '<script>alert(1)</script>',
        '<image href="data:image/png;base64,PHN2Zy8+"/>',
        '<g>' * 65 + '</g>' * 65,
    ]
    for content in unsafe:
        try:
            ValidateFurnishingSvg(svg.replace('<rect width="100" height="100"/>', content))
        except ValueError:
            pass
        else:
            raise AssertionError("Unsafe SVG reached the native renderer: " + content[:80])
    for source in ('<!DOCTYPE svg [<!ENTITY x "text">]>' + svg, b'\xff\xfe<\x00s\x00v\x00g\x00/\x00>\x00'):
        try:
            ValidateFurnishingSvg(source)
        except ValueError:
            pass
        else:
            raise AssertionError("Unsafe XML encoding/declaration was accepted")
    ValidateFurnishingSvg(svg.replace('<rect width="100" height="100"/>', '<defs><path id="shape" d="M0 0H10"/></defs><use href="#shape"/>'))
    image = QtGui.QImage(8, 8, QtGui.QImage.Format.Format_RGB32)
    image.fill(QtGui.QColor("#1234ab"))
    buffer = QtCore.QBuffer()
    buffer.open(QtCore.QIODevice.OpenModeFlag.ReadWrite)
    assert image.save(buffer, "PNG")
    encoded = base64.b64encode(bytes(buffer.data())).decode("ascii")
    ValidateFurnishingSvg(svg.replace('<rect width="100" height="100"/>', f'<image href="data:image/png;base64,{encoded}" width="100" height="100"/>'))
    for path in (workspace / "planner-main/furnishings/images").glob("*.svg"):
        ValidateFurnishingSvg(path.read_bytes())
    deepSvg = svg.replace('<rect width="100" height="100"/>', '<g>' * 62 + '<rect width="100" height="100"/>' + '</g>' * 62)
    ValidateFurnishingSvg(deepSvg)
    try:
        CompoundFurnishingSvg([dict(definition = {"graphicData": deepSvg.encode("utf-8"), "width": 100, "length": 100},
            x = 0, y = 0, angle = 0, width = 100, length = 100, zIndex = 0)])
    except ValueError as error:
        assert "nested" in str(error)
    else:
        raise AssertionError("Generated compound exceeded the SVG depth budget")

    main = MainWindow()
    main.sessionTimer.stop()
    main.sessionPollTimer.stop()
    v = main.viewport
    local = dict(v.furnishingDefinitions)
    defaults = copy.deepcopy(main.defaultProjectData)
    definitions = {}
    for level in range(15):
        record = dict(name = f"Nested {level}", category = "Miscellaneous", width = 100, length = 100, svg = svg)
        if level:
            record.update(compoundCenter = [0, 0], components = [dict(definition = f"nested{level - 1}",
                x = 0, y = 0, width = 100, length = 100, angle = 0, zIndex = index) for index in (0, 1)])
        definitions[f"nested{level}"] = record
    try:
        DecodeFurnishingDefinitions(definitions, local)
    except ValueError as error:
        assert "10,000" in str(error)
    else:
        raise AssertionError("Exponential compound expansion was accepted")
    bounded = DecodeFurnishingDefinitions({key: value for key, value in definitions.items() if int(key[6:]) < 10}, local)
    sizes = FurnishingExpansionSizes(bounded.values())
    assert sizes[id(bounded["nested9"])] == 1023
    # Resolve leaves first to exercise the memoized-child depth boundary.
    chain = [{}]
    for level in range(64):
        chain.append({"components": [{"definition": chain[-1]}]})
    try:
        FurnishingExpansionSizes(chain)
    except ValueError as error:
        assert "nested" in str(error)
    else:
        raise AssertionError("Memoized child definitions bypassed the depth limit")
    data = copy.deepcopy(defaults)
    data["furnishingDefinitions"] = {key: definitions[key] for key in bounded}
    data["scene"]["objects"] = [dict(type = "Furnishing", id = index + 1, definition = "nested9",
        first = [index * 1000, 0], second = [index * 1000, 100], width = 100) for index in range(100)]
    try:
        DecodeProject(data, local)
    except ValueError as error:
        assert "100,000" in str(error)
    else:
        raise AssertionError("Aggregate compound expansion exceeded the scene budget")

    # A deleted portable asset and a redo-only asset both survive a real journal reload.
    graphic = Path(local["desk"]["imagePath"]).read_bytes()
    custom = dict(local["desk"], key = "audit_portable", name = "Audit portable", isUser = True,
                  isEmbedded = True, graphicData = graphic)
    v.furnishingDefinitions = {**local, custom["key"]: custom}
    v.projectFurnishingDefinitions = {custom["key"]: custom}
    before = v.CaptureState()
    v.furnishings = [Furnishing(custom)]
    v.RecordEdit(before)
    before = v.CaptureState()
    v.furnishings.clear()
    v.RecordEdit(before)
    saved = main.BuildProjectData()
    assert custom["key"] in saved["furnishingDefinitions"]
    assert "furnishingDefinitions" not in main.BuildProjectData(includeHistory = False)
    main.ApplyProject(DecodeProject(saved, local), None)
    v.Undo()
    assert v.furnishings[0].definition["graphicData"] == graphic
    v.Undo()
    assert not v.furnishings and v.redoHistory
    redo = DecodeProject(main.BuildProjectData(), local)
    main.ApplyProject(redo, None)
    v.Redo()
    assert v.furnishings[0].definition["graphicData"] == graphic

    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        catalogue = folder / "catalogue"
        (catalogue / "definitions").mkdir(parents = True)
        (catalogue / "images").mkdir()
        for relative in ("definitions/null.json", "images/null.svg"):
            shutil.copy2(workspace / "planner-main/furnishings" / relative, catalogue / relative)
        v.furnishingsFolder = catalogue
        children = [dict(furnishing = custom["key"], x = index * 2000, y = 0) for index in (0, 1)]
        arrangement = main.SaveUserFurnishing("Portable arrangement", "Miscellaneous", children)
        assert arrangement and arrangement["components"][0]["definition"]["graphicData"] == graphic
        reloaded = {definition["key"]: definition for definition in LoadFurnishings(catalogue)}
        assert reloaded[arrangement["key"]]["components"][0]["definition"]["graphicData"] == graphic
        invalid = dict(custom, graphicData = b'<svg><image href="C:/private/image.png"/></svg>')
        with patch.dict(v.projectFurnishingDefinitions, {custom["key"]: invalid}), patch.object(main, "ShowAppMessage") as message:
            assert main.SaveUserFurnishing("Unsafe arrangement", "Miscellaneous", children) is False
            assert message.call_args.args[0] == "Cannot Create Furnishing"
            assert not (catalogue / "definitions_user/unsafe_arrangement.json").exists()

        main.sidebarTabs.setCurrentIndex(0)
        v.zoom, v.panOffset = 2.0, QtCore.QPointF(100, 200)
        main.sidebarTabs.setCurrentWidget(main.exportPanel)
        v.panOffset = QtCore.QPointF(900, 1200)
        expectedView = main.BuildProjectData()["view"]
        with patch.object(main.sessionWriter, "Write", return_value = None) as write:
            assert main.WriteSession(wait = True)
        assert write.call_args.args[1]["project"]["view"] == expectedView
        main.sessionSignature = None
        main.sidebarTabs.setCurrentIndex(0)

        # A process cannot acquire a live owner's recovery file; normal release works.
        with patch.dict(os.environ, {"PLANNER_SESSION_PATH": str(folder / "locked.json")}):
            lock = AcquireSessionLock()
            program = ('from PySide6 import QtCore\nfrom planner_app.ui.session import AcquireSessionLock\n'
                       'app = QtCore.QCoreApplication([])\n'
                       'try: lock = AcquireSessionLock()\nexcept OSError: raise SystemExit(3)\n')
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(workspace / "planner-main") + os.pathsep + environment.get("PYTHONPATH", "")
            child = subprocess.run([sys.executable, "-B", "-c", program], env = environment,
                                   capture_output = True, text = True, timeout = 15)
            assert child.returncode == 3, child.stderr
            lock.unlock()
            released = AcquireSessionLock()
            released.unlock()
            # A crashed process leaves its file behind; dead-owner recovery must
            # still work with age-based stale detection disabled.
            crashed = subprocess.run([sys.executable, "-B", "-c", program + 'import os\nos._exit(0)\n'],
                env = environment, capture_output = True, text = True, timeout = 15)
            assert crashed.returncode == 0, crashed.stderr
            assert (folder / "locked.json.lock").exists()
            recovered = AcquireSessionLock()
            recovered.unlock()

        app.processEvents()
        previous = {id(widget) for widget in app.topLevelWidgets() if isinstance(widget, DrawingViewport)}
        for attempt in range(3):
            try:
                RenderPlan("unused.plan", 1000, (0, 0, 40000, 40000), projectData = defaults,
                           applyTheme = False, furnishingDefinitions = local)
            except ValueError:
                pass
            else:
                raise AssertionError("Oversized export was accepted")
        app.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
        assert {id(widget) for widget in app.topLevelWidgets() if isinstance(widget, DrawingViewport)} == previous

        path = folder / "bounded.plan"
        path.write_bytes(b" " * 128)
        with patch("planner_app.project_codec.projectFileLimit", 64):
            try:
                RenderPlan(path, 100, (0, 0, 1000, 1000), applyTheme = False)
            except ValueError as error:
                assert "64 MiB" in str(error)
            else:
                raise AssertionError("CLI rendering ignored the project input limit")
        for outputFormat, result in (("svg", b"<svg/>"), ("png", image)):
            path = folder / ("atomic." + outputFormat)
            path.write_bytes(b"keep previous export")
            with patch.object(QtCore.QSaveFile, "commit", return_value = False):
                try:
                    WriteExportFile(path, result, outputFormat)
                except OSError:
                    pass
                else:
                    raise AssertionError("Atomic commit failure was ignored")
            assert path.read_bytes() == b"keep previous export"
            WriteExportFile(path, result, outputFormat)
            assert path.read_bytes() != b"keep previous export"

        # The check runner must reject callback errors and disabled assertions.
        check = folder / "callback_probe.py"
        check.write_text('from PySide6 import QtCore, QtWidgets\napp = QtWidgets.QApplication([])\n'
            'QtCore.QTimer.singleShot(0, lambda: 1 / 0)\nQtCore.QTimer.singleShot(20, app.quit)\napp.exec()\n')
        command = [sys.executable, "-B", str(workspace / "checks/run_checks.py"), str(check)]
        failed = subprocess.run(command, capture_output = True, text = True, timeout = 15)
        assert failed.returncode == 1 and "unhandled callback/thread" in failed.stdout
        check.write_text(check.read_text() + 'raise SystemExit(0)\n')
        failed = subprocess.run(command, capture_output = True, text = True, timeout = 15)
        assert failed.returncode == 1 and "unhandled callback/thread" in failed.stdout
        optimized = subprocess.run(command, env = dict(os.environ, PYTHONOPTIMIZE = "1"),
                                   capture_output = True, text = True, timeout = 15)
        assert optimized.returncode == 1 and "disable optimization" in optimized.stdout

    # Independent walls must not produce all-pairs collision work during import.
    data = copy.deepcopy(defaults)
    count = 250
    data["scene"]["objects"] = [dict(type = "Wall", id = index + 1, first = [0, index * 2000],
        second = [5000, index * 2000], width = 200, firstMiter = 0, secondMiter = 0, material = "Generic") for index in range(count)]
    data["scene"]["objects"] += [dict(type = "Window", id = count + index + 1, parent = index,
        center = .5, length = 1000, swingsOutwards = False) for index in range(count)]
    overlap = FootprintGeometry.ObjectsOverlap
    with patch.object(FootprintGeometry, "ObjectsOverlap", autospec = True, side_effect = overlap) as calls:
        DecodeProject(data, local)
        RecoverProject(data, local, defaults, chooseGeometry = lambda issue: None)
        assert calls.call_count < count * 4, calls.call_count
    data["scene"]["objects"].append(dict(type = "Wall", id = 1000, first = [2500, -1000],
        second = [2500, 1000], width = 200, firstMiter = 0, secondMiter = 0, material = "Generic"))
    try:
        DecodeProject(data, local)
    except ValueError as error:
        assert "obstructed" in str(error)
    else:
        raise AssertionError("Indexed import missed an actual opening obstruction")
    main.close()
    print("PASS: SVG safety, compound budgets, portable history/catalogue assets, camera recovery, process lock, failure cleanup, atomic/bounded CLI and trustworthy checks")


if __name__ == "__main__":
    Main()
