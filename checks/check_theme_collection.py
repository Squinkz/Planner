"""Bundled palette completeness, neutral surfaces and readable drafting contrast."""
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from planner_app.graphics.palette import LoadThemes, uiRoles, canvasRoles


def Contrast(first, second):
    values = []
    for color in (first, second):
        channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        channels = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in channels]
        values.append(sum(value * weight for value, weight in zip(channels, (.2126, .7152, .0722))))
    low, high = sorted(values)
    return (high + .05) / (low + .05)


def Main():
    with warnings.catch_warnings(record = True) as messages:
        themes = LoadThemes()
    assert not messages, [str(message.message) for message in messages]
    expectedUI = {"Dark UI", "Light UI", "Heather UI", "Neutral UI", "Dark Fire UI", "Dark Ice UI", "Light Fire UI",
                  "Light Ice UI", "Driftwood UI", "Sage UI", "Candy Shop UI", "Periwinkle UI"}
    expectedCanvas = {"Dark Canvas", "Light Canvas", "Blueprint Canvas", "Deep Blueprint Canvas", "Cyanotype Canvas",
                      "Cyan Blueprint Canvas", "Vellum Canvas", "Graphite Canvas", "Sepia Canvas", "Redline Canvas", "Risograph Canvas"}
    assert expectedUI | expectedCanvas <= themes.keys()
    for name in expectedUI:
        colors = themes[name]["colors"]
        assert themes[name]["type"] == "ui" and set(colors) == set(uiRoles), name
        for surface in ("windowBackground", "controlBackground", "fieldBackground", "hoverBackground"):
            assert Contrast(colors["text"], colors[surface]) >= 4.5, (name, surface)
        for surface in ("activeBackground", "activeHoverBackground"):
            assert Contrast(colors["activeText"], colors[surface]) >= 4.5, (name, surface)
            assert Contrast(colors["icon"], colors[surface]) >= 3, (name, surface, "icon")
    for name in expectedCanvas:
        colors = themes[name]["colors"]
        assert themes[name]["type"] == "canvas" and set(colors) == set(canvasRoles), name
        assert Contrast(colors["objectOutline"], colors["canvas"]) >= 7, name
        assert Contrast(colors["measurementLine"], colors["canvas"]) >= 3, name
        assert Contrast(colors["selectionOutline"], colors["canvas"]) >= 3, name
        assert Contrast(colors["rulerText"], colors["rulerBackground"]) >= 4.5, name
        assert colors["selectionOutline"] != colors["groupSelectionOutline"], name
    neutral = themes["Neutral UI"]["colors"]
    for role in ("text", "mutedText", "activeText", "windowBackground", "controlBackground", "fieldBackground",
                 "hoverBackground", "pressedBackground", "activeBackground", "activeHoverBackground", "icon"):
        color = neutral[role]
        assert color[1:3] == color[3:5] == color[5:7], (role, color)
    assert themes["Heather UI"]["colors"]["windowBackground"] == "#bfb8bf"
    assert themes["Heather UI"]["colors"]["activeBackground"] == "#b6a5c6"
    print(f"PASS: {len(expectedUI | expectedCanvas)} bundled UI/canvas palettes, inherited roles, untinted Neutral and text/icon/drafting contrast.")


if __name__ == "__main__":
    Main()
