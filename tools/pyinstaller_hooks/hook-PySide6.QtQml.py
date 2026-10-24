"""Planner uses QJSEngine for UPNG, without importing QML UI modules."""
from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
