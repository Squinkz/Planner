"""Catalog discoverability, numeric intent, normalization and bounded typo recovery."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "planner-main"))
from planner_app.catalog import LoadFurnishings
from planner_app.furnishing_search import FindFurnishings, FurnishingDimensionText
from planner_app.units import unitModes


def Main():
    catalog = LoadFurnishings()
    for mode in unitModes:
        for definition in catalog:
            if definition["key"] == "null":
                continue
            # Exercise the full catalog: unrelated matches must not hide the
            # item's own name or a size copied directly from its caption.
            matches = FindFurnishings(catalog, definition["name"], mode)
            assert definition in matches, (mode, definition["key"], "full name")
            assert matches[0]["name"] == definition["name"], (mode, definition["key"], "name relevance")
            width, length = FurnishingDimensionText(definition, mode).split(" × ")
            matches = FindFurnishings(catalog, "w:" + width + " l:" + length, mode)
            assert definition in matches, (mode, definition["key"], width, length)

    for first, second in (("office chair", "office chairs"), ("fridge", "fridges"),
                          ("2 seater sofa", "two seater sofa"), ("6 seat", "6-seat"),
                          ("office chair", "chair, office"), ("tv 55\"", "tv 55″"),
                          ("tv 55", "tv 55."),
                          ("w:1200mm l:600mm", "w:1200 mm l:600 mm"),
                          ("120 60", "120x60"), ("120 60", "120 × 60"),
                          ("120cm 60cm", "120 cm x 60 cm")):
        firstKeys = [item["key"] for item in FindFurnishings(catalog, first, "Centimeters")]
        secondKeys = [item["key"] for item in FindFurnishings(catalog, second, "Centimeters")]
        assert firstKeys and firstKeys == secondKeys, (first, second, firstKeys, secondKeys)
    for query in ("dining table", "table dining"):
        assert FindFurnishings(catalog, query, "Centimeters")[0]["key"].startswith("table_dining_"), query
    assert FindFurnishings(catalog, "55", "Centimeters")[0]["key"] in ("tv_55", "tv_55_wall")
    assert not FindFurnishings(catalog, "tv 5", "Centimeters")
    couch = FindFurnishings(catalog, "couch", "Centimeters")
    assert "sofa" in couch[0]["name"].casefold() and couch[0]["key"] != "pillow_throw"
    for typo in ("soffa", "sfoa"):
        assert "sofa" in FindFurnishings(catalog, typo, "Centimeters")[0]["name"].casefold(), typo
    assert not FindFurnishings(catalog, "sxfxa", "Centimeters")
    assert not FindFurnishings(catalog, "zxqv", "Centimeters")
    for name, alias, partial in (("Dining Table", "dinner", "dinne"),
                                 ("Child Chair", "children", "childr"),
                                 ("Shelf", "shelves", "shelv")):
        definition = dict(key = "alias", name = name, width = 400, length = 600)
        assert FindFurnishings([definition], alias, "Centimeters") == [definition]
        assert FindFurnishings([definition], partial, "Centimeters") == [definition]

    fixtures = [dict(key = "exact", name = "Seat", width = 400, length = 600),
                dict(key = "rounded", name = "A Rounded Seat", width = 400.4, length = 600.4),
                dict(key = "wrong", name = "40 Seat", width = 400, length = 300)]
    for mode in unitModes:
        matches = FindFurnishings(fixtures, "w:400mm l:600mm", mode)
        assert [item["key"] for item in matches] == ["exact", "rounded"], mode
    assert [item["key"] for item in FindFurnishings(fixtures, "40 60", "Centimeters")] == ["exact", "rounded"]
    assert not FindFurnishings(fixtures, "w:40 w:40", "Centimeters")
    assert not FindFurnishings(fixtures, "w:-40", "Centimeters")
    assert not FindFurnishings(fixtures, "w:invalid", "Centimeters")
    assert not FindFurnishings(fixtures, "w:" + "9" * 400, "Centimeters")
    # Fuzzy recovery cannot weaken a valid word or an explicit size constraint.
    assert FindFurnishings([fixtures[0]], "seat", "Centimeters") == [fixtures[0]]
    assert not FindFurnishings([fixtures[0]], "seet w:999mm", "Centimeters")
    assert FindFurnishings([fixtures[0]], "sea", "Centimeters") == [fixtures[0]]
    nearWord = dict(key = "near", name = "Seam", width = 400, length = 600)
    assert FindFurnishings([fixtures[0], nearWord], "seat", "Centimeters") == [fixtures[0]]
    print("PASS: full names and displayed sizes in all modes, normalization, relevance, numeric intent and bounded typos")


if __name__ == "__main__":
    Main()
