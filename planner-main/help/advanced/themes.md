# Adding custom themes

Planner loads themes from the `themes/` folder when it starts. You can choose UI and canvas themes separately. These selections are remembered across projects, while export theme overrides are saved with each plan.

For changing themes in Planner, see [Appearance](../appearance.md).

Themes can use JSON or JSONC, which allows `//` comments. Each theme needs a unique `name` and a `type` of either `"ui"` or `"canvas"`. Restart Planner after adding or editing a theme.

## Colors

UI themes set the appearance of buttons, fields, text, icons and dialogs. Some useful roles are:

| Role | Purpose |
|---|---|
| `fieldBackground` | Input fields and furnishing-icon backgrounds |
| `controlBackground` | Buttons |
| `disabledBackground` | Disabled fields |
| `icon` | UI icon artwork |

Canvas themes control the plan itself, including backgrounds, object outlines, selections, dimensions, grids and rulers.

| Role | Purpose |
|---|---|
| `canvas` | Canvas and furnishing backgrounds |
| `grid` | Grid lines, adjusted by the grid intensity settings |
| `rulerBackground` | Ruler backgrounds, including the unit corner |
| `missing` | Missing-artwork accents on the canvas and furnishing icons |
| `roomFill` | Background shading inside detected rooms |

`roomFill` sits underneath the reference image and grid, and remains visible when the grid is hidden. Choose a color that suits the rest of your palette.

Line weights are project settings and are not part of a theme.

Use the supplied theme files as a reference for all available roles. A selectable theme must define every role for its type, either itself or through inheritance.

Colors accept `#RRGGBB` or Qt’s `#AARRGGBB` notation. In the latter, the first two digits control opacity: `00` is transparent and `FF` is fully opaque.

## Fonts

Canvas themes can set `labelFont`. Use the font’s internal family name, which may differ from its filename. For example, `D-DINCondensed.ttf` uses the family name **D-DIN Condensed**.

To add fonts, place `.ttf`, `.otf`, `.ttc` or `.otc` files in `assets/fonts/`, then restart Planner. Fonts already installed on your computer are also available.

`labelFont` applies to canvas labels and other canvas lettering. It defaults to Noto Sans. UI text, rulers and dimensions use Noto Sans.

SVG exports convert text to outlines.

## Inheritance

You don’t need to write a complete palette from scratch. Use `extends` to inherit an existing theme, then supply only the values you want to change:

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

`extends` accepts either one theme name or a list. Parents must have the same type as the child. When using a list, later parents override earlier ones, and the child’s own values take precedence over all parents. Colors merge by role, and `labelFont` follows the same order.

Set `"abstract": true` to create a partial theme for other themes to inherit. Abstract themes stay out of the theme selectors and do not need a complete palette. The abstract setting is not inherited.

Planner checks themes for missing roles, invalid values, missing parents and inheritance cycles. Invalid files produce warnings, while valid themes remain available.

If a selected theme is unavailable, Planner falls back to **Heather UI** or **Magnetite Canvas**. If those are also unavailable, it uses the first valid theme of the appropriate type. At least one valid UI theme and one valid canvas theme must be present.

[<< Back to Help](../README.md)