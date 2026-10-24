# Fonts

Planner registers font resources in `assets/fonts/` with Qt at startup. Supported extensions are `.ttf`, `.otf`, `.ttc` and `.otc`. Restart the app after adding a font.

Themes select the font's internal family name. `D-DINCondensed.ttf` provides **D-DIN Condensed**. Canvas labels and north-arrow lettering use the canvas theme's `labelFont`. Measurements use Noto Sans.

Noto Sans version 2.015, normal width, supplies UI text and rulers:

- Regular (400): ordinary text.
- SemiBold (600): headings and emphasized controls.
- Bold (700): bold headings.

Noto Sans also supplies fallback measurement glyphs. Imperial fractions use font shaping or assembled digits and a slash according to the chosen font's glyph support. SVG export outlines text for consistent appearance in external viewers.

All bundled fonts are under **SIL OFL 1.1**, separately from Planner's GPL code
and reserved-graphics terms:

| Bundled files | Origin | Complete notice |
| --- | --- | --- |
| NotoSans-Regular.ttf, NotoSans-SemiBold.ttf, NotoSans-Bold.ttf | Unmodified Noto Sans 2.015, copyright 2022 The Noto Project Authors | [OFL.txt](../../planner-main/assets/fonts/OFL.txt) |
| D-DINCondensed.ttf | D-DIN Condensed 1.00, copyright 2017 Datto Inc., designer Charles Nix; Reserved Font Name D-DIN Condensed | [OFL-D-DIN.txt](../../planner-main/assets/fonts/OFL-D-DIN.txt) |
| DraftingSmallCaps-Regular.ttf | Modified small-caps version of Architects Daughter, originally copyright 2010 Kimberly Geswein | [OFL-DraftingSmallCaps.txt](../../planner-main/assets/fonts/OFL-DraftingSmallCaps.txt) |

[FONTLOG.txt](../../planner-main/assets/fonts/FONTLOG.txt) records sources and the
known modification history. Drafting Small Caps retains the upstream copyright
and OFL; its small-caps changes do not make it a reserved Planner graphic.
Its internal family and PostScript names already identify the renamed derivative.
Adding these notices does not alter the font binaries or rendering.

The Licenses window includes every bundled font's complete notice. The build
copies the entire external font directory, including these files. Retain the
applicable notices and record provenance when adding another font. See the
[OFL modification guidance](https://openfontlicense.org/how-to-modify-ofl-fonts/)
and [Architects Daughter's upstream notice](https://github.com/google/fonts/blob/main/ofl/architectsdaughter/OFL.txt).
