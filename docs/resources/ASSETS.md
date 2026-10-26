# Artwork resources

UI SVGs live in `assets/icons_ui/`; Build symbols live in `assets/icons_ui/objects/`. Cursor bitmaps live in `assets/cursors/`, and fonts live in `assets/fonts/`.

`assets/planner.svg` is the Planner About logo. The About window loads it at
300 by 300 logical pixels. The `about_*` footer
icons also come from Stacker and use Planner's usual theme tinting.

## UI SVGs

Use white (`#ffffff`) for tintable paint and `fill="none"` for transparent regions. Name files after the icon's purpose.

`UiIcon(name, color = None, rotation = 0)` loads an icon with an optional tint and rotation in degrees around its SVG viewBox center. Rotation preserves vector rendering, disabled artwork and theme refresh. For multiple paint roles, add `data-theme-fill` or `data-theme-stroke` to SVG elements. UI foreground and surface roles use `icon` and `fieldBackground`; `missing` supplies missing-artwork accents. Markers also apply to inline paint styles.

`planner_app/graphics/icons.py` resolves artwork colors from `graphics/palette.py`. Tinted renderers are cached by artwork, palette, requested tint and rotation. Missing or malformed icons log one warning per source path and use transparent fallback artwork so the application can launch. Qt stylesheet images use SVG variants in a process-owned temporary directory, cleaned up at shutdown.

## Cursors

Cursor PNGs use their authored colors and transparency. `rotate.png` is 32 × 32 pixels with a hotspot at (16, 16). Black outlines and white interiors keep it visible on light and dark canvases. Restart Planner after changing a cursor.

## Furnishing artwork and fonts

Furnishing graphics use black foreground and white surface paint, mapped to UI colors in the palette and canvas colors in the drawing. See [furnishing definitions](FURNISHINGS.md) for authoring details.

See [fonts](FONTS.md) for registration and licensing information.
