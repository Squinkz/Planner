"""Profile selection, unrelated wall and crossing vertex drags in a heavy scene."""
import cProfile
import math
import os
import pstats
import sys
import tempfile
import time
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6 import QtCore, QtTest, QtWidgets
from planner import MainWindow, Wall


def Main():
    app = QtWidgets.QApplication([])
    point = QtCore.QPointF
    with tempfile.TemporaryDirectory() as sessionFolder:
        os.environ["PLANNER_SESSION_PATH"] = str(Path(sessionFolder) / "session.json")
        main = MainWindow()
        main.show()
        app.processEvents()
        viewport = main.viewport
        viewport.connectedEnabled = "--connected" in sys.argv
        vertices = [point(math.cos(index * math.tau / 63) * 1500,
                          math.sin(index * math.tau / 63) * 1500) for index in range(63)]
        viewport.walls = [Wall(vertices[index], vertices[(index + 1) % 63], 120) for index in range(63)]
        vertex = "--vertex" in sys.argv
        single = "--single" in sys.argv or vertex
        if single:
            moving = Wall(point(500, 0), point(1400, 0), 120) if vertex else Wall(point(-500, 0), point(500, 0), 120)
            viewport.walls.append(moving)
            viewport.walls.extend(Wall(point(2200 + index % 4 * 1000, index // 4 * 800),
                                       point(3000 + index % 4 * 1000, index // 4 * 800), 120)
                                  for index in range(16))
            viewport.SetSelection([(moving, 1 if vertex else None)])
        else:
            moving = viewport.walls[0]
            viewport.SetSelection([(wall, None) for wall in viewport.walls])
        for snapping in (False, True):
            viewport.snapEnabled = snapping
            app.processEvents()
            first = moving
            start = viewport.WorldToViewport(first.secondVertex if vertex else (first.firstVertex + first.secondVertex) / 2).toPoint()
            pressStarted = time.perf_counter()
            QtTest.QTest.mousePress(viewport, QtCore.Qt.MouseButton.LeftButton, pos = start)
            print(f"Drag start: {(time.perf_counter() - pressStarted) * 1000:.2f} ms", flush = True)
            assert viewport.groupDrag != single
            samples = []
            profile = cProfile.Profile()
            profiling = "--profile" in sys.argv
            if profiling:
                profile.enable()
            for frame in range(12):
                started = time.perf_counter()
                position = viewport.WorldToViewport(point(1510 + frame * 7, frame * 8)) if vertex else point(start) + point(30 + frame * 1.1, 30 + frame * .7)
                viewport.UpdateInteraction(position,
                                           QtCore.Qt.KeyboardModifier.NoModifier)
                app.processEvents()
                samples.append((time.perf_counter() - started) * 1000)
            if profiling:
                profile.disable()
            operation = "vertex crossing" if vertex else "single wall" if single else "whole selection"
            print(f"{len(viewport.walls)} walls, {operation}, snapping {snapping}: median {median(samples[2:]):.2f} ms", flush = True)
            if profiling:
                pstats.Stats(profile).strip_dirs().sort_stats("cumulative").print_stats(18)
            viewport.CancelInteraction()
        main.close()
        app.processEvents()


if __name__ == "__main__":
    Main()
