"""Every bundled font has its own complete OFL notice and preserved provenance."""
from pathlib import Path
import struct


def FontNames(path):
    data = path.read_bytes()
    count = struct.unpack_from(">H", data, 4)[0]
    tables = [struct.unpack_from(">4sIII", data, 12 + index * 16) for index in range(count)]
    tag, checksum, offset, length = next(row for row in tables if row[0] == b"name")
    table = data[offset:offset + length]
    version, count, strings = struct.unpack_from(">HHH", table)
    names = {}
    for index in range(count):
        platform, encoding, language, name, size, start = struct.unpack_from(">HHHHHH", table, 6 + index * 12)
        if platform in (0, 3):
            value = table[strings + start:strings + start + size].decode("utf-16-be")
            names.setdefault(name, value.replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n").strip())
    return names


def Main():
    root = Path(__file__).resolve().parents[1]
    folder = root / "planner-main/assets/fonts"
    notices = {"NotoSans-Regular.ttf": ("OFL.txt", "The Noto Project Authors"),
               "NotoSans-SemiBold.ttf": ("OFL.txt", "The Noto Project Authors"),
               "NotoSans-Bold.ttf": ("OFL.txt", "The Noto Project Authors"),
               "D-DINCondensed.ttf": ("OFL-D-DIN.txt", "Datto Inc."),
               "DraftingSmallCaps-Regular.ttf": ("OFL-DraftingSmallCaps.txt", "Kimberly Geswein")}
    actual = {path.name for path in folder.iterdir() if path.suffix.lower() in (".ttf", ".otf", ".ttc", ".otc")}
    assert actual == set(notices), "A bundled font is missing license coverage"
    for filename, (notice, author) in notices.items():
        text = (folder / notice).read_text(encoding = "utf-8")
        assert author in text and "SIL OPEN FONT LICENSE Version 1.1" in text and "DISCLAIMER" in text
        names = FontNames(folder / filename)
        if filename in ("D-DINCondensed.ttf", "DraftingSmallCaps-Regular.ttf"):
            assert names[13] in text, filename + " lost its embedded license or copyright notice"
    names = FontNames(folder / "DraftingSmallCaps-Regular.ttf")
    assert names[1] == "Drafting Small Caps" and names[6] == "DraftingSmallCaps-Regular"
    assert "with Reserved Font Name D-DIN Condensed." in (folder / "OFL-D-DIN.txt").read_text(encoding = "utf-8")
    log = (folder / "FONTLOG.txt").read_text(encoding = "utf-8")
    assert all(filename in log for filename in notices)
    assert "modified small-caps variant of Architects Daughter" in log and "Kimberly Geswein" in log
    print("Font licenses: every bundled face, full upstream notices, reserved name and renamed OFL derivative passed")


if __name__ == "__main__":
    Main()
