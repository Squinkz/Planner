import os, sys, time, cProfile, pstats
from pathlib import Path
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'planner-main'))
from PySide6 import QtCore, QtGui, QtWidgets
from planner import MainWindow, Wall, Stair
from furnishings import Furnishing
from theme import BuildStyle
app = QtWidgets.QApplication([])
QtGui.QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
app.setStyleSheet(BuildStyle())
w = MainWindow()
w.show()
app.processEvents()
v = w.viewport
p = QtCore.QPointF
for row in range(5):
    for col in range(8):
        start = p(col * 3000 - 10000, row * 3500 - 7000)
        v.walls.append(Wall(start, start + p(2200, 0), 240))
        v.furnishings.append(Furnishing(v.furnishingDefinitions['desk'], start + p(1000, 1000)))
        if col % 2 == 0:
            v.walls.append(Stair(start + p(1800, 1200), start + p(1800, 2700), 800))
v.zoom = .25
v.grab()
profiler = cProfile.Profile()
profiler.enable()
start = time.perf_counter()
for frame in range(30):
    v.panOffset = p(frame * 3, frame)
    v.grab()
elapsed = time.perf_counter() - start
profiler.disable()
print(f'Pan frame average: {elapsed / 30 * 1000:.2f} ms')
pstats.Stats(profiler).strip_dirs().sort_stats('cumulative').print_stats(18)
w.close()
