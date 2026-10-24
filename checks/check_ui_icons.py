"""Neutral UI artwork, cached runtime colors and stylesheet indicator variants."""
import os
import re
import sys
import xml.etree.ElementTree as ElementTree
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtGui, QtWidgets
from planner_app.graphics.icons import UiIcon, UiIconPath, uiIconColors
from planner_app.graphics.theme import BuildStyle, HeaderIcon
from planner_app.paths import assetsDirectory
from planner_app.ui.widgets import WindowButton


def OpaqueColors(icon):
    image = icon.pixmap(96, 96).toImage()
    return {image.pixelColor(x, y).name() for x in range(image.width()) for y in range(image.height())
            if image.pixelColor(x, y).alpha() == 255}


def Main():
    app = QtWidgets.QApplication([])
    folder = assetsDirectory / "icons_ui"
    assert folder.is_dir() and not (assetsDirectory / "dark").exists() and not (assetsDirectory / "light").exists()
    assert not list(assetsDirectory.glob("titlebar_*.svg"))
    originals = {path: path.read_bytes() for path in folder.rglob("*.svg")}
    assert len(originals) >= 60 and (folder / "palette.svg") in originals
    assert len(list(folder.glob("radio_button_checked*.svg"))) == 1
    assert len(list(folder.glob("radio_button_unchecked*.svg"))) == 1
    pattern = re.compile(r"\b(?:fill|stroke|color|stop-color)\s*:\s*([^;}]+)", re.IGNORECASE)
    for path, source in originals.items():
        for element in ElementTree.fromstring(source).iter():
            style = element.get("style", "")
            # Fully transparent editor fills do not contribute a rendered color.
            transparentFill = element.get("fill-opacity") == "0" or bool(re.search(r"\bfill-opacity\s*:\s*0(?:[;\s]|$)", style))
            paints = [element.get(attribute) for attribute in ("fill", "stroke", "color", "stop-color")
                      if attribute != "fill" or not transparentFill]
            if transparentFill:
                style = re.sub(r"\bfill\s*:[^;}]+", "fill:none", style)
            paints += pattern.findall(style)
            if element.tag.rsplit("}", 1)[-1] == "style":
                paints += pattern.findall(element.text or "")
            assert all(paint is None or paint.strip().lower() in ("none", "transparent", "inherit", "currentcolor")
                       or paint.strip().startswith("url(#") or QtGui.QColor(paint.strip()).isValid()
                       for paint in paints), path
            for attribute in ("fill", "stroke", "color", "stop-color"):
                role = element.get("data-theme-" + attribute)
                assert role is None or role in uiIconColors, (path, attribute, role)
        name = path.relative_to(folder).with_suffix("").as_posix()
        assert not UiIcon(name).isNull(), name
    assert OpaqueColors(HeaderIcon("Check")) == {uiIconColors["icon"]}
    assert OpaqueColors(UiIcon("radio_button_checked", uiIconColors["disabled"])) == {uiIconColors["disabled"]}
    for kind in ("warning", "error", "info"):
        assert OpaqueColors(UiIcon(kind, uiIconColors[kind])) == {uiIconColors[kind]}
        assert OpaqueColors(UiIcon(kind, uiIconColors[kind + "Title"])) == {uiIconColors[kind + "Title"]}
    assert {uiIconColors["fieldBackground"], uiIconColors["icon"]}.issubset(OpaqueColors(UiIcon("objects/counter")))
    assert not WindowButton(objectType = "casement-window").icon().isNull()
    style = BuildStyle()
    paths = re.findall(r'image:\s*url\("([^"]+)"\)', style)
    assert paths and all(Path(path).is_file() for path in paths)
    for name in ("radio_button_unchecked", "radio_button_checked", "radio_button_halfchecked"):
        assert UiIconPath(name).as_posix() in paths
        assert UiIconPath(name, uiIconColors["disabled"]).as_posix() in paths
    assert "__ICON_" not in style and "__ASSETS__" not in style
    assert "icons_ui" not in style  # Stylesheets use tinted cache files, never source SVGs.
    cached = UiIconPath("radio_button_checked")
    assert cached == UiIconPath("radio_button_checked")
    assert not cached.is_relative_to(assetsDirectory)
    disabled = UiIconPath("radio_button_checked", uiIconColors["disabled"])
    assert disabled != cached and disabled.as_posix() in style
    # A new palette creates a new variant; restoring it reuses the old cached path.
    previous = uiIconColors["icon"]
    try:
        uiIconColors["icon"] = "#ffffff"
        assert UiIconPath("radio_button_checked") != cached
        assert OpaqueColors(UiIcon("radio_button_checked")) == {"#ffffff"}
    finally:
        uiIconColors["icon"] = previous
    assert UiIconPath("radio_button_checked") == cached
    assert all(path.read_bytes() == source for path, source in originals.items())
    app.processEvents()


if __name__ == "__main__":
    Main()
