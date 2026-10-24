# Fonts

Planner registers font resources in `assets/fonts/` with Qt at startup. Supported extensions are `.ttf`, `.otf`, `.ttc` and `.otc`. Restart the app after adding a font.

Themes select the font's internal family name. `D-DINCondensed.ttf` provides **D-DIN Condensed**. Canvas labels and north-arrow lettering use the canvas theme's `labelFont`. Measurements use Noto Sans.

Noto Sans version 2.015, normal width, supplies UI text and rulers:

- Regular (400): ordinary text.
- SemiBold (600): headings and emphasized controls.
- Bold (700): bold headings.

Noto Sans also supplies fallback measurement glyphs. Imperial fractions use font shaping or assembled digits and a slash according to the chosen font's glyph support. SVG export outlines text for consistent appearance in external viewers.

The Noto Sans files are unmodified copies. Copyright 2022 The Noto Project Authors. They are distributed under the SIL Open Font License 1.1; see [OFL.txt](../../planner-main/assets/fonts/OFL.txt) for the notice. Additional font resources should retain their applicable license notices.
