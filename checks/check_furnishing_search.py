"""Live furnishing search, unit ranking, dimensions, keywords and card reuse."""
import json
import os
import sys
import tempfile
import warnings
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from PySide6 import QtCore, QtGui, QtWidgets, QtTest
from planner import MainWindow
from planner_app.catalog import LoadFurnishings
from planner_app.furnishing_search import FindFurnishings
from planner_app.paths import furnishingsDirectory
from theme import BuildStyle
from planner_app.graphics.palette import themeColors


def Main():
    app = QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    app.setStyleSheet(BuildStyle())
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        definitions = folder / "definitions"
        definitions.mkdir()
        (definitions / "null.json").write_bytes((furnishingsDirectory / "definitions/null.json").read_bytes())
        fixtures = {
            "mm": {"name": "Small Seat", "width": 40, "length": 60, "keywords": ["needle", "Sit"]},
            "cm": {"name": "Dining Seat", "category": "Office", "width": 400, "length": 600, "keywords": "needle upholstery"},
            "m": {"name": "Large Seat", "width": 40000, "length": 60000, "keywords": ["needle"]},
            "reversed": {"name": "Turned Seat", "width": 600, "length": 400},
            "square": {"name": "Square Seat", "width": 400, "length": 400},
            "inherited": {"inherits": "cm", "name": "Inherited Seat"},
            "cleared": {"inherits": "cm", "name": "Plain Seat", "keywords": []},
            "invalid": {"keywords": 40},
            "officeName": {"name": "Office Desk", "category": "Living", "width": 800, "length": 600},
        }
        for key, definition in fixtures.items():
            (definitions / (key + ".json")).write_text(json.dumps(definition), encoding = "utf-8")
        with warnings.catch_warnings(record = True) as messages:
            catalog = LoadFurnishings(folder)
        byKey = {definition["key"]: definition for definition in catalog}
        assert "invalid" not in byKey and messages
        assert byKey["inherited"]["keywords"] == ["needle upholstery"]
        assert byKey["cleared"]["keywords"] == []
        assert {definition["key"] for definition in FindFurnishings(catalog, "oFfIcE", "Centimeters")} == {"cm", "inherited", "cleared", "officeName"}
        assert FindFurnishings(catalog, "office upholstery", "Centimeters")
        uncached = dict(byKey["cm"])
        uncached.pop("searchText")
        assert FindFurnishings([uncached], "office", "Centimeters")
        matches = FindFurnishings(catalog, "sEaT NeEdLe", "Centimeters")
        assert {definition["key"] for definition in matches} == {"cm", "mm", "m", "inherited"}
        assert not FindFurnishings(catalog, "nonexistent", "Centimeters")
        assert {definition["key"] for definition in FindFurnishings(catalog, " * ", "Centimeters")} == set(byKey) - {"null"}
        assert FindFurnishings(catalog, "* office", "Centimeters") == FindFurnishings(catalog, "office", "Centimeters")
        base = [byKey[key] for key in ("mm", "cm", "m")]
        assert [definition["key"] for definition in FindFurnishings(base, "40", "Centimeters")] == ["cm", "mm", "m"]
        assert FindFurnishings(base, "40", "Millimeters")[0]["key"] == "mm"
        assert FindFurnishings(base, "40", "Meters")[0]["key"] == "m"
        assert FindFurnishings(base, "40", "Adaptive Metric")[0]["key"] == "cm"
        assert len(FindFurnishings(base, "40 60", "Centimeters")) == 3
        assert FindFurnishings([byKey["reversed"]], "40 60", "Centimeters")
        assert not FindFurnishings([byKey["reversed"]], "w:40 l:60", "Centimeters")
        assert FindFurnishings([byKey["cm"]], "W: 40 L:60", "Centimeters")
        assert not FindFurnishings([byKey["square"]], "40 60", "Centimeters")
        assert FindFurnishings([byKey["square"]], "40 40", "Centimeters")
        assert [definition["key"] for definition in FindFurnishings(base, "w:400mm l:60cm", "Meters")] == ["cm"]
        assert FindFurnishings(base, "w:0.4m l:.6m", "Centimeters")[0]["key"] == "cm"
        assert not FindFurnishings(base, "w:", "Centimeters")

        ranked = [dict(key = key, name = name, width = 600, length = 600, category = category, keywords = keywords)
                  for key, name, category, keywords in (
                      ("partial", "A Dining Set", "Dining", ["arrangement"]),
                      ("keyword", "B Cooker", "Kitchen", ["range"]),
                      ("category", "C Appliance", "Range", []),
                      ("name", "Gas Range", "Kitchen", []),
                      ("punctuation", "Range-Cooker", "Kitchen", []),
                      ("namePartial", "Ranger", "Kitchen", []))]
        assert [item["key"] for item in FindFurnishings(ranked, "RaNgE", "Millimeters")] == [
            "name", "punctuation", "keyword", "category", "partial", "namePartial"]
        assert [item["key"] for item in FindFurnishings(ranked, "range kitchen", "Millimeters")] == [
            "name", "punctuation", "keyword", "namePartial"]

    main = MainWindow()
    catalog = list(main.viewport.furnishingDefinitions.values())
    dinner = {item["key"] for item in FindFurnishings(catalog, "dinner", "Millimeters")}
    assert dinner
    for query in ("dinn", "dinne", "DINNE"):
        assert dinner <= {item["key"] for item in FindFurnishings(catalog, query, "Millimeters")}, query
    assert {item["key"] for item in FindFurnishings(catalog, "dinne chair", "Millimeters")} == {
        item["key"] for item in FindFurnishings(catalog, "dinner chair", "Millimeters")}
    aliases = [dict(key = key, name = name, width = 450, length = 500, category = "Furniture", keywords = keywords)
               for key, name, keywords in (("partialAlias", "Dining Table", []),
                                           ("keyword", "Bench", ["dinne"]),
                                           ("wholeName", "Dinne", []))]
    assert [item["key"] for item in FindFurnishings(aliases, "dinne", "Millimeters")] == [
        "wholeName", "keyword", "partialAlias"]
    assert FindFurnishings(aliases[:1], "dinne w:450mm", "Millimeters") == aliases[:1]
    ranges = FindFurnishings(catalog, "range", "Millimeters")
    nameMatches = [item for item in ranges if "range" in item["name"].casefold().split()]
    assert ranges[:len(nameMatches)] == nameMatches, "Appliance names must precede dining-set arrangement keywords"
    for query, expected in (("washbasin", {"basin_hung", "basin_ped", "basin_vessel"}),
                            ("couch", {"sofa_single", "sofa_double", "sofa_triple", "sofa_apartment", "sofa_quad",
                                       "sectional_sofa_1", "sectional_sofa_2", "sectional_sofa_3", "sofa_section",
                                       "sofa_section_corner", "sofa_section_end", "daybed", "pillow_throw"}),
                            ("queen mattress", {"bed_queen"}),
                            ("full size mattress", {"bed_double"}),
                            ("hot water cylinder", {"water_heater"}),
                            ("computer peripheral", {"keyboard", "mouse", "deskpad_setup", "mouse_setup_large",
                                                     "mousepad_setup_regular"}),
                            ("laundry appliance", {"washer", "dryer", "washer_built", "dryer_built",
                                                  "washer_dryer", "washer_dryer_built"}),
                            ("double bowl drainer", {"sink_drainer_dbl", "sink_drainer_dbl2"}),
                            ("floor waste", {"drain"}),
                            ("television wall mount", {"tv_55_wall", "tv_65_wall", "tv_75_wall", "tv_85_wall"}),
                            ("six chairs", {"dining_set_6", "dining_set_round_6"}),
                            ("two square table", {"table_dining_square_2", "dining_set_square_2"}),
                            ("four square table", {"table_dining_square_4", "dining_set_square_4"}),
                            ("saloon", {"sedan"}),
                            ("geyser", {"water_heater"}),
                            ("cot", {"crib", "bassinet"}),
                            ("parasol", {"umbrella_balcony", "umbrella_patio"}),
                            ("wall coat hooks", {"peg_rail", "peg_rail_small", "peg_rail_large"}),
                            ("barbecue", {"bbq_drum", "bbq_kettle", "bbq_pit"}),
                            ("shower rose", {"showerhead"}),
                            ("shower tray", {"shower_angled", "shower_quad", "shower_square1",
                                             "shower_square2", "shower_square3"}),
                            ("mouse pointing device", {"mouse", "mouse_setup_large", "mousepad_setup_regular",
                                                       "deskpad_setup"}),
                            ("double oven", {"oven_built_dbl"}),
                            ("hallway runner", {"rug_runner", "rug_runner_large", "rug_runner_small"}),
                            ("pedestrian", {"man"}),
                            ("belfast", {"sink_farmhouse"})):
        assert {definition["key"] for definition in FindFurnishings(catalog, query, "Centimeters")} == expected, query
    overheadCabinets = {"cabinet_trans", "cabinet_single_trans", "cabinet_corn_trans", "cabinet_corn2_trans"}
    assert not overheadCabinets.intersection(item["key"] for item in FindFurnishings(catalog, "base cabinet", "Millimeters"))
    assert overheadCabinets <= {item["key"] for item in FindFurnishings(catalog, "wall cupboard", "Millimeters")}
    main.show()
    main.sidebarTabs.setCurrentIndex(1)
    app.processEvents()
    field = main.furnishingSearchField
    grids = dict(main.furnishingCategoryGrids)
    field.setFocus()
    QtTest.QTest.keyClicks(field, "bEd")
    QtTest.QTest.qWait(180)
    assert main.furnishingResultsWidget.isVisible()
    assert all(not widget.isVisible() for widget in main.furnishingCategoryWidgets.values())
    results = main.furnishingResultsGrid.model().keys
    assert len(results) == len(FindFurnishings(catalog, "bed", main.viewport.unitsMode))
    assert all("bed" in main.viewport.furnishingDefinitions[key]["searchText"] for key in results)
    assert main.furnishingCategoryGrids == grids
    assert field.hasFocus()
    main.grab().save("screenshots/furnishing-search.png")
    field.setText("zzzz no match")
    QtTest.QTest.qWait(180)
    assert main.furnishingNoResults.isVisible() and main.furnishingResultsGrid.model().rowCount() == 0
    assert main.furnishingSearchClearAction.isVisible()
    clearButton = main.furnishingSearchClearButton
    assert clearButton is not None and clearButton.isVisible()
    # Deliver hover events directly: offscreen QTest mouse coordinates can
    # miss a small tool button at fractional display scaling.
    center = QtCore.QPointF(clearButton.rect().center())
    QtCore.QCoreApplication.sendEvent(clearButton, QtGui.QEnterEvent(center, center,
        QtCore.QPointF(clearButton.mapToGlobal(center.toPoint()))))
    app.processEvents()
    hoverImage = clearButton.icon().pixmap(24, 24).toImage()
    hoverColors = {hoverImage.pixelColor(x, y).name() for x in range(24) for y in range(24)
                   if hoverImage.pixelColor(x, y).alpha() == 255}
    assert themeColors["activeText"] in hoverColors, hoverColors
    QtCore.QCoreApplication.sendEvent(clearButton, QtCore.QEvent(QtCore.QEvent.Type.Leave))
    app.processEvents()
    idleImage = clearButton.icon().pixmap(24, 24).toImage()
    idleColors = {idleImage.pixelColor(x, y).name() for x in range(24) for y in range(24)
                  if idleImage.pixelColor(x, y).alpha() == 255}
    assert themeColors["mutedText"] in idleColors and themeColors["activeText"] not in idleColors, idleColors
    main.furnishingSearchClearAction.trigger()
    assert not field.text() and not main.furnishingSearchClearAction.isVisible()
    QtTest.QTest.qWait(180)
    assert not main.furnishingResultsWidget.isVisible()
    assert all(grid.isVisible() for grid in grids.values())
    field.setText("w:120 l:60")
    QtTest.QTest.qWait(180)
    assert "desk" in main.furnishingResultsGrid.model().keys
    main.BuildFurnishTab(refresh = True)
    assert main.furnishingSearchField.text() == "w:120 l:60"
    assert "desk" in main.furnishingResultsGrid.model().keys
    main.close()
    print("PASS: substring/keyword search, mm/cm/m priority, pairs, axis filters, debounce and reusable draggable cards.")


if __name__ == "__main__":
    Main()
