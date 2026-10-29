"""Preserve polygon wheel input while Windows owns the native drag loop."""
from contextlib import contextmanager
import logging
import sys

from PySide6 import QtCore, QtGui, QtWidgets


@contextmanager
def NativeDragWheel(viewport):
    if sys.platform != "win32" or QtGui.QGuiApplication.platformName() != "windows":
        yield
        return

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error = True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error = True)
    hookType = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)
    user32.SetWindowsHookExW.argtypes = (ctypes.c_int, hookType, wintypes.HINSTANCE, wintypes.DWORD)
    user32.SetWindowsHookExW.restype = wintypes.HANDLE
    user32.CallNextHookEx.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)
    user32.CallNextHookEx.restype = ctypes.c_ssize_t
    user32.UnhookWindowsHookEx.argtypes = (wintypes.HANDLE,)
    user32.UnhookWindowsHookEx.restype = wintypes.BOOL
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    @hookType
    def WheelMessage(code, removed, address):
        # WH_GETMESSAGE also observes PeekMessage(PM_NOREMOVE). Only handle
        # removal, otherwise one wheel notch can be applied several times.
        if code == 0 and removed == 1 and viewport.guiDragActive and not viewport.guiDragCancelled:
            message = ctypes.cast(address, ctypes.POINTER(wintypes.MSG)).contents
            if message.message == 0x020A and viewport.guiDragKind == "wall-circle":  # WM_MOUSEWHEEL
                try:
                    delta = ctypes.c_short((message.wParam >> 16) & 0xFFFF).value
                    globalPosition = QtGui.QCursor.pos()
                    event = QtGui.QWheelEvent(QtCore.QPointF(viewport.mapFromGlobal(globalPosition)),
                        QtCore.QPointF(globalPosition), QtCore.QPoint(), QtCore.QPoint(0, delta),
                        QtWidgets.QApplication.mouseButtons(), QtWidgets.QApplication.keyboardModifiers(),
                        QtCore.Qt.ScrollPhase.NoScrollPhase, False)
                    viewport.wheelEvent(event)
                    # Prevent OLE or Qt from applying the same input a second time.
                    message.message = 0  # WM_NULL
                    message.wParam = message.lParam = 0
                except Exception:
                    # Exceptions must never cross the native callback boundary.
                    logging.exception("Cannot process polygon drag wheel input")
        return user32.CallNextHookEx(None, code, removed, address)

    # Thread-local and temporary: no global mouse hook or idle message overhead.
    hook = user32.SetWindowsHookExW(3, WheelMessage, None, kernel32.GetCurrentThreadId())
    if not hook:
        logging.warning("Cannot capture native drag wheel input: %s", ctypes.WinError(ctypes.get_last_error()))
    try:
        yield
    finally:
        if hook:
            user32.UnhookWindowsHookEx(hook)
