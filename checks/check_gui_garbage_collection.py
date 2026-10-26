"""Recovery allocations must not finalize GUI cycles on the recovery worker."""
import gc
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtWidgets
from planner import MainWindow
from planner_app.ui.session import WriteSessionFile


def Main():
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    collector = app.plannerGarbageCollector
    # Native scroll areas expose viewport() as a method, not a Planner canvas.
    editor = QtWidgets.QPlainTextEdit()
    editor.show()
    # Settle the editor's queued window-activation events before simulating a
    # drag. A real deactivation intentionally cancels the canvas interaction.
    app.processEvents()
    assert callable(editor.viewport)
    assert not gc.isenabled()
    guiThread = threading.get_ident()
    finalizedThreads = []

    class GuiCycle(QtCore.QObject):
        def __init__(self):
            super().__init__()
            self.cycle = self

        def __del__(self):
            finalizedThreads.append(threading.get_ident())

    gc.collect()
    for index in range(200):
        cycle = GuiCycle()
    del cycle

    def SaveRepeatedly():
        payload = json.dumps({"format": "Planner Session", "version": 1,
                              "items": [{"value": index} for index in range(4000)]})
        for index in range(30):
            assert WriteSessionFile(window.sessionPath, json.loads(payload)) is None
        return threading.get_ident()

    # Keep collection deferred as it would be during a canvas drag. Recovery still
    # repeatedly decodes JSON and writes atomic checkpoints on its own thread.
    window.viewport.dragStart = QtCore.QPointF(10, 10)
    with ThreadPoolExecutor(max_workers = 1) as executor:
        future = executor.submit(SaveRepeatedly)
        deadline = time.monotonic() + 10
        while not future.done() and time.monotonic() < deadline:
            window.viewport.repaint()
            app.processEvents()
        assert future.result(timeout = 5) != guiThread
    assert not finalizedThreads, "Background allocations collected GUI wrappers"
    collector.lastFullCollection -= 31
    assert window.viewport.dragStart is not None
    collector.Collect()
    assert not finalizedThreads, "Collection should wait until dragging ends"
    window.viewport.dragStart = None
    collector.Collect()
    assert len(finalizedThreads) == 200
    assert set(finalizedThreads) == {guiThread}
    editor.close()
    window.close()
    app.processEvents()


if __name__ == "__main__":
    Main()
