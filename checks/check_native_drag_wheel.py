"""Windows queue delivery survives an OLE-style consumer without Qt wheel events."""
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "planner-main"))
from PySide6 import QtCore, QtGui
from fixtures.parity_examples import ExampleWindow, InstallScene
from planner_app.ui.drag_wheel import NativeDragWheel


def Main():
    if sys.platform != "win32":
        print("SKIP: Windows native drag message queue")
        return
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error = True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error = True)
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    user32.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t)
    user32.PostThreadMessageW.restype = wintypes.BOOL
    user32.PeekMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT)
    user32.PeekMessageW.restype = wintypes.BOOL
    threadId = kernel32.GetCurrentThreadId()
    wheelMessage = 0x020A
    with ExampleWindow() as (main, folder):
        v = main.viewport
        InstallScene(main, [])
        v.snapEnabled = False
        v.guiDragActive, v.guiDragCancelled, v.guiDragKind = True, False, "wall-circle"
        v.circleSegments, v.circleWheelDelta = 8, 0
        mime = QtCore.QMimeData()
        mime.setData("application/x-planner-wall-circle", b"circle")
        position = v.DrawingRect().center()
        move = QtGui.QDragMoveEvent(position.toPoint(), QtCore.Qt.DropAction.CopyAction, mime,
            QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        v.dragMoveEvent(move)
        zoom = v.zoom
        # Keep rendering offscreen, but exercise the actual Windows thread hook.
        with patch("planner_app.ui.drag_wheel.QtGui.QGuiApplication.platformName", return_value = "windows"):
            with NativeDragWheel(v):
                for delta in [60, 60] + [120] * 30 + [-120] * 36 + [120] * 5:
                    before, remainder = v.circleSegments, v.circleWheelDelta
                    assert user32.PostThreadMessageW(threadId, wheelMessage, (delta & 0xFFFF) << 16, 0)
                    message = wintypes.MSG()
                    # Peeking must neither consume the notch nor change the preview.
                    for unused in range(3):
                        assert user32.PeekMessageW(ctypes.byref(message), None, wheelMessage, wheelMessage, 0)
                        assert message.message == wheelMessage and v.circleSegments == before
                    assert user32.PeekMessageW(ctypes.byref(message), None, wheelMessage, wheelMessage, 1)
                    assert message.message == 0, "Native input can be consumed twice"
                    expected = max(3, before + int((remainder + delta) / 120))
                    assert v.circleSegments == expected and len(v.pendingShapeWalls) == expected
                    assert v.zoom == zoom
                for kind, cancelled in (("wall-circle", True), ("wall-line", False), ("furnishing", False)):
                    v.guiDragKind, v.guiDragCancelled = kind, cancelled
                    before = v.circleSegments
                    assert user32.PostThreadMessageW(threadId, wheelMessage, 120 << 16, 0)
                    assert user32.PeekMessageW(ctypes.byref(message), None, wheelMessage, wheelMessage, 1)
                    assert message.message == wheelMessage and v.circleSegments == before
                v.guiDragKind, v.guiDragCancelled = "wall-circle", False
            # No hook remains after the drag ends, even if the viewport flag lingers.
            before = v.circleSegments
            assert user32.PostThreadMessageW(threadId, wheelMessage, 120 << 16, 0)
            assert user32.PeekMessageW(ctypes.byref(message), None, wheelMessage, wheelMessage, 1)
            assert message.message == wheelMessage and v.circleSegments == before
            try:
                with NativeDragWheel(v):
                    raise RuntimeError("Cancelled drag")
            except RuntimeError:
                pass
            assert user32.PostThreadMessageW(threadId, wheelMessage, 120 << 16, 0)
            assert user32.PeekMessageW(ctypes.byref(message), None, wheelMessage, wheelMessage, 1)
            assert message.message == wheelMessage and v.circleSegments == before
        v.guiDragActive, v.guiDragKind = False, None
        v.CancelInteraction()
    print("PASS: native queue bursts, partial/reverse ticks, minimum count, no duplicate delivery/zoom, cancellation and hook cleanup")


if __name__ == "__main__":
    Main()
