"""Unavailable UI artwork warns once and does not prevent window construction."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtGui, QtWidgets
from planner import MainWindow
from planner_app.graphics import icons
from planner_app.graphics.theme import ApplyApplicationTheme


def Main():
    app = QtWidgets.QApplication([])
    ApplyApplicationTheme(app)
    with tempfile.TemporaryDirectory() as directory:
        assets = Path(directory)
        (assets / "icons_ui").mkdir()
        (assets / "icons_ui" / "broken.svg").write_text("<svg><broken>", encoding = "utf-8")
        with patch.object(icons, "assetsDirectory", assets), patch.object(icons.logger, "warning") as warning:
            for name in ("missing", "broken"):
                for color in (None, "#123456"):
                    icon = icons.UiIcon(name, color)
                    image = icon.pixmap(24, 24).toImage()
                    assert not image.isNull()
                    assert all(image.pixelColor(x, y).alpha() == 0 for x in range(24) for y in range(24))
                    assert icons.UiIconPath(name, color).is_file()
            assert warning.call_count == 2, "Warn once per source, not per color or disabled state"

    readBytes = Path.read_bytes

    def ReadWithoutLink(path):
        if path == icons.assetsDirectory / "icons_ui" / "link.svg":
            raise FileNotFoundError("Missing link.svg")
        return readBytes(path)

    with patch.object(Path, "read_bytes", ReadWithoutLink), patch.object(icons.logger, "warning") as warning:
        main = MainWindow()
        main.show()
        app.processEvents()
        assert main.sizeLinkButton.isEnabled() and main.sizeLinkButton.isChecked()
        main.sizeLinkButton.click()
        assert not main.sizeLinkButton.isChecked()
        assert warning.call_count == 1
        main.MarkProjectClean()
        main.close()


if __name__ == "__main__":
    Main()
