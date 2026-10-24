"""Bundled typography shared by widgets, scene labels and offscreen exports."""

from PySide6 import QtGui
from planner_app.paths import assetsDirectory

fontFamily = "Noto Sans"
fontFiles = ("NotoSans-Regular.ttf", "NotoSans-SemiBold.ttf", "NotoSans-Bold.ttf")


def LoadApplicationFonts(app = None):
    app = app or QtGui.QGuiApplication.instance()
    if app is None:
        raise RuntimeError("Create the Qt application before loading Planner fonts.")
    if getattr(app, "plannerFontIds", None) is not None:
        return
    fontIds = []
    fontDirectory = assetsDirectory / "fonts"
    paths = [fontDirectory / filename for filename in fontFiles]
    paths.extend(path for path in sorted(fontDirectory.iterdir())
                 if path.suffix.lower() in (".ttf", ".otf", ".ttc", ".otc") and path not in paths)
    for path in paths:
        fontId = QtGui.QFontDatabase.addApplicationFont(str(path))
        if fontId < 0:
            raise RuntimeError(f"Could not load bundled font: {path}")
        fontIds.append(fontId)
    app.plannerFontIds = tuple(fontIds)
    font = QtGui.QFont(fontFamily, 10)
    # Preserve glyph proportions at small sizes instead of the Windows default
    # hinting that can distort lowercase bowls and crossbars.
    font.setHintingPreference(QtGui.QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)
