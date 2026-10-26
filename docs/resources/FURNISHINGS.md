# Furnishing definitions

Built-in JSON definitions live in `furnishings/definitions/`, user definitions in `furnishings/definitions_user/`, and SVG artwork in `furnishings/images/`. The catalog loads at startup and refreshes after saving a user furnishing. Dimensions and child positions use millimeters.

## User definition persistence

The creation transaction captures child positions, dimensions, angles and drawing
order. Children reference their source definitions. User JSON is written under
`furnishings/definitions_user/`. Repeated display names are valid; new file keys
receive `_2`, `_3`, etc. as needed without replacing existing references. The UI
serializes comma-separated categories as a category list. Creation/decomposition
are undoable scene edits; removing scene children does not delete catalog files.
See the [user furnishing guide](../../planner-main/docs/help/furnishings.md) for the workflow.

## Definition fields

| Field | Meaning |
| --- | --- |
| `name` | Display name |
| `image` | Graphic filename in `images/`, excluding `.svg` |
| `width`, `length` | Default dimensions in millimeters |
| `icon` | Optional palette graphic filename, excluding `.svg`; null uses the furnishing graphic |
| `category` | Palette category as text, or multiple categories as a list of strings |
| `inherits` | Optional parent definition key, excluding `.json` |
| `children` | Compound components |
| `keywords` | Search terms as a string or list of strings |

Each definition receives defaults from `null.json`, then its explicit parent's resolved fields, then its own fields. Null supplies every supported field and the Miscellaneous category. Missing graphics use the Null placeholder graphic. Validation warnings identify invalid definitions.

For example, `"category": ["Office", "Bedroom"]` displays a furnishing in both sections. Searches match every category and show each furnishing once. Categories are inherited when omitted; an explicit category replaces the inherited list. Empty categories default to Miscellaneous, and duplicate entries in a list are ignored.

For example:

```json
{
    "inherits": "desk",
    "name": "Large Desk",
    "width": 1600
}
```

Placed objects have a separate angle property, measured counterclockwise in degrees.

## Search indexing

Names, categories and keywords contribute case-insensitive search terms.
Whole-word name matches rank first, then whole-word keyword/category matches,
then partial matches. Multiple-word queries rank their weakest match tier first,
then their total score, with names and keys breaking ties.
An explicit keyword list replaces inherited keywords; `[]` clears them. Numeric
queries resolve against definition dimensions, with selected-unit matches ranked
first (centimeters for Adaptive Metric). The user-facing query examples belong
in the [furnishing search guide](../../planner-main/docs/help/furnishings.md).

## Compound definitions

A nonempty `children` list creates a compound. The union of the children's rotated bounds determines its default width and length. It has one selection and object ID, with per-child collision footprints, and scales as a complete arrangement.

Each child references a definition key through `furnishing`:

| Child field | Meaning and default |
| --- | --- |
| `x`, `y` | Center position in millimeters; 0. Positive X is right and positive Y is up |
| `angle` | Counterclockwise rotation in degrees; 0 |
| `width`, `length` | Dimensions; referenced definition's defaults |
| `scale` | Positive uniform multiplier; 1. Choose this or explicit dimensions |
| `zIndex` | Drawing priority; 0. Higher values draw on top, with list order breaking ties |
| `fixedSize` | Boolean; false. Retain this child's authored width and length as the compound grows |

Set `"fixedSize": true` on individual child entries to retain their physical size.
Their centers still follow the compound's scaling. Below default size they shrink
uniformly by the smaller scale; explicit child dimensions or `scale` define the
authored size to retain. Rotation, flips, collision footprints, connected-object
contact and decomposition use the resulting geometry. A marked compound child is
treated as one fixed group. This developer option is read from JSON and is not
exposed in the furnishing-creation dialog. Project-embedded components preserve it.

```json
{
    "furnishing": "chair_dining",
    "x": 700,
    "y": 0,
    "fixedSize": true
}
```

Authored positions share an origin; the resolved graphic is centered on the bounds' midpoint. Nested compounds are supported to 64 levels, with cycle validation. Missing child definitions use Null and any supplied dimensions.

Omitting `children` inherits the parent's list. Supplying a list replaces it; an empty list selects regular furnishing artwork. An explicit icon supplies the palette image; otherwise the composed graphic supplies it.

```json
{
    "name": "Dining Set 4",
    "category": "Dining Room",
    "children": [
        {"furnishing": "table_dining_4", "zIndex": 1},
        {"furnishing": "chair_dining", "x": -300, "y": 450},
        {"furnishing": "chair_dining", "x": 300, "y": 450},
        {"furnishing": "chair_dining", "x": -300, "y": -450, "angle": 180},
        {"furnishing": "chair_dining", "x": 300, "y": -450, "angle": 180}
    ]
}
```

This arrangement has default bounds of 1200 × 1400 mm. Composed graphics are cached in memory. Decomposition of a nonuniformly scaled compound derives each child's center, axis lengths and rotation from the transformed arrangement.

## SVG artwork

Furnishing SVGs are limited to 8 MiB, 50,000 XML elements and 64 levels of nesting.
External files, network references, document types, entities and active content
are rejected. References within the SVG use `#id`; raster images must be embedded
PNG data and stay within the reference-image dimension limits. Remove hidden
tracing images that still link to source files before installing artwork.

Compounds may expand to at most 10,000 component objects, including intermediate
compounds. A scene's complete fallback expansion may contain at most 100,000
objects. Shared definitions count once per placement in these expansion budgets.
Reusable arrangements preserve project-embedded dependencies in their JSON
`embeddedFurnishings` field; they do not depend on another project's catalogue.

Use a valid numeric `viewBox`, pure black (`#000000`) for foreground and outlines, and pure white (`#ffffff`) for filled surfaces. Transparent regions use `fill="none"`.

Unresolved compound children retain their original furnishing keys while displaying Null. Missing primary image files also display Null and remain asset errors even though their definition exists. Recovery and properties identify these errors, and clipboard/duplication actions reject them. In the editor, Null's complete foreground uses the semantic error color, including when selected; this does not recolor healthy siblings in a compound. Export omits Null artwork while preserving healthy compound children. Preview and export rendering do not repeat asset warnings in the console.

For artwork with handles or other protrusions, add a rectangle with ID `planner-bounds` around the physical body. In Inkscape, draw the rectangle, set its ID in **Object Properties**, then hide it using the eye icon in the **Objects** panel. No XML editing is needed. Planner uses that rectangle for mapping the graphic to the definition's width and length, keeping artwork outside it visible. Selection handles, measurements, snapping and collision footprints retain the stated dimensions; palette previews and automatic export bounds include protrusions.

The `planner-bounds` marker may be hidden directly or inside a hidden layer/group. Paths also work, including rectangles converted to paths. Planner uses the path's minimum and maximum extents as a rectangular dimension box, never as a clipping mask. The path does not have to be closed. Marker and ancestor transforms are supported; rotated markers use their axis-aligned bounds in SVG coordinates. Planner hides the marker even if it is visible in the source. Absent, duplicate, unsupported or empty markers fall back to the normal SVG bounds. `planner-fixed` details do not replace these dimension bounds. Keep the source page large enough for the full artwork to display in other SVG viewers.

For details that should retain their physical size, give the object or group an
ID `planner-fixed` or one starting with `planner-fixed-`, such as `planner-fixed-magazines`, in Inkscape's
**Object Properties**. Its default physical size comes from the furnishing
definition's width and length. Its midpoint follows the furnishing's scaling,
while its geometry retains its default proportions and size as the furnishing
grows. Below default size, it shrinks uniformly by the smaller width/length scale.
Mark a group to retain an arrangement together; mark separate objects to let their
midpoints spread apart. Nested markers use the outermost marked group. Marked
text follows this physical sizing rule instead of ordinary furnishing lettering
layout. Rotation, flips, compound children and exports preserve these rules.

Set `vector-effect="non-scaling-stroke"` on each stroked shape or path. This keeps outlines a consistent visual thickness as the furnishing is resized or the view is zoomed. Planner applies this property when loading graphics and sets their stroke width from the furnishing line-weight setting. Include it in source artwork so SVG previews also use this behavior.

Planner also normalizes `vector-effect` declarations in inline styles and embedded CSS, so an authored `vector-effect:none` cannot override its stroke widths. Dash patterns and offsets retain their normalized ratios; line caps, joins and path geometry remain authored.

Catalog SVGs use a source stroke width of `1`, including inherited group settings and CSS rules. Keep new artwork consistent with this convention; Planner's line-weight control sets the actual viewport and export thickness.

```svg
<path d="M 10,10 H 90 V 90 H 10 Z"
      fill="#ffffff" stroke="#000000" stroke-width="1"
      vector-effect="non-scaling-stroke" />
```

Canvas artwork maps black to `objectOutline` and white to `canvas`. Palette icons map these colors to the UI theme's `icon` and `fieldBackground`. Paint attributes, inline styles and CSS rules use the same mapping. Cached variants preserve source artwork.

Null marks its outline with `data-theme-outline="missing"` to use the missing-artwork accent. This marker is retained in compound graphics.

### Lettering

Use SVG `<text>` elements for furnishing lettering. Planner preserves the authored center of the visible glyphs, so text inside a feature such as a washer drum remains anchored to that feature during zoom and resizing. The authored font size sets its maximum screen size, and its proportion to the source artwork sets an additional maximum. Lettering shrinks uniformly as the furnishing becomes smaller on screen or along either dimension, with a small margin around the edges. Compound furnishings preserve each component's authored lettering positions.

Text uses the active canvas theme's `labelFont`, retaining its authored size, weight, styling and glyph-center position. It stays upright and horizontal as furnishings rotate. Export uses the export canvas theme's font. PNG and SVG exports use the same layout, with the authored size measured in output pixels or SVG units. Keep lettering as text in the source SVG so Planner can apply this layout; the source SVG's font remains unchanged.
