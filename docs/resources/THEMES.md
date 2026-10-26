# UI and canvas themes

Theme resources live in `themes/` and load at startup. UI and canvas selections
are independent application preferences; export canvas overrides are project data.
For choosing palettes in the application, see [Appearance](../../planner-main/docs/help/appearance.md).

Each resource has a unique `name` and a `type` of `"ui"` or `"canvas"`. Both JSON
and JSONC are supported; JSONC accepts `//` comments. Restart after resource edits.

## Color roles

UI themes control widget text, surfaces, controls, icons and dialog accents. `fieldBackground` supplies editor fields and furnishing-icon surfaces. `controlBackground` supplies buttons, and `disabledBackground` supplies disabled fields. UI palette icons use `icon` for foreground artwork.

Canvas themes control drawing surfaces, object outlines, grids, selections, measurements, rulers and overlays. `canvas` supplies drawing and furnishing backgrounds; `grid` is modulated by grid intensity. Ruler unit corners use `rulerBackground`. `missing` supplies missing-artwork accents on the canvas and in furnishing icons. Line weights are separate project settings.

`roomFill` supplies the editor background inside detected rooms, underneath the
reference image and grid. It is an independent canvas role, not a brightness
adjustment to `canvas`. White palettes use a subtle darker fill; dark and colored
palettes use a fill chosen for their own background and ink. It remains visible with the grid hidden and
does not affect exports. Selectable canvas themes must define or inherit this
role; there is no automatically generated fallback.

Use the supplied files as the complete role reference. Selectable themes define every role for their type, directly or through inheritance. Colors use `#RRGGBB` or Qt's alpha-first `#AARRGGBB` notation.

## Fonts

Canvas `labelFont` selects a font by its internal family name. For example, `D-DINCondensed.ttf` registers as **D-DIN Condensed**.

Planner registers `.ttf`, `.otf`, `.ttc` and `.otc` resources in `assets/fonts/` at startup; installed fonts are also available through Qt. Restart after adding a font.

Canvas labels and north-marker lettering use `labelFont`; the default is Noto Sans. UI text, rulers and measurements use Noto Sans. Imperial measurements use native fraction shaping where supported, or assembled fractions from the font's digits and slash. SVG exports outline text.

## Inheritance

`extends` refers to theme names and accepts a name or a list of names of the same type. Parents merge left to right, then the child's values override them. Colors merge by role, and canvas fonts inherit in the same order.

```jsonc
{
    "name": "Light Blue UI",
    "type": "ui",
    "extends": "Light UI",
    "colors": {
        "activeBackground": "#397ac7",
        "activeHoverBackground": "#498bd8"
    }
}
```

`"abstract": true` defines a reusable partial theme hidden from selectors. Abstract themes specify a type and may supply a subset of roles. Each child's abstract status is set explicitly.

Validation checks required roles, role types, parents and inheritance cycles. Warnings identify invalid files; valid themes remain available. An unavailable UI selection falls back to Heather UI, and an unavailable canvas selection falls back to Magnetite Canvas. If that fallback is unavailable, the first valid theme of that type is used. Planner requires at least one valid UI and canvas theme.
