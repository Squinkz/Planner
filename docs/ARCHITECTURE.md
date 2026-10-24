# Planner architecture

The `main.py` entry point configures crash reporting, application styling and
the main window. Source paths below are relative to the application directory
(`planner-main/`). See [Development](DEVELOPMENT.md) for setup and commands.

## Source layout

| Path | Responsibility |
| --- | --- |
| `planner_app/models.py` | Object data, dimensions and derived properties |
| `planner_app/catalog.py` | Furnishing definitions, inheritance and compounds |
| `planner_app/furnishing_search.py` | Text filtering and dimension ranking |
| `planner_app/object_schema.py` | Object property metadata |
| `planner_app/units.py` | Unit conversion and measurement formatting |
| `planner_app/number_expressions.py` | Bounded arithmetic parsing for numeric editors without code execution |
| `planner_app/paths.py` | Resource locations |
| `planner_app/preferences.py` | Initial presets and preferences |
| `planner_app/project_codec.py` | Project serialization and validation |
| `planner_app/project_history.py`, `history_edits.py` | Undo/redo storage and edits |
| `planner_app/scene_changes.py` | Scene change tracking |
| `planner_app/geometry/` | Qt-independent numeric geometry and ordered spatial queries |
| `planner_app/export_bounds.py` | Export footprint bounds |
| `planner_app/export_plan.py` | PNG/SVG rendering and module CLI |
| `planner_app/crash_reporting.py` | Crash reports |
| `planner_app/garbage_collection.py` | Garbage-collection scheduling |
| `planner_app/graphics/` | Palettes, fonts, icons, symbols and vector artwork |
| `planner_app/ui/` | Window, sidebar, properties, settings, projects and recovery |
| `planner_app/ui/export_panel.py` | Export controls, overrides and preview configuration |
| `planner_app/ui/help_viewer.py` | Native Markdown help rendering and navigation |
| `planner_app/ui/about.py` | Standalone About splash and bundled license notices |
| `docs/help/` | Bundled user guide, independent of the renderer |
| `planner_app/viewport/` | Interaction, placement, geometry, snapping and painting |
| `assets/` | UI SVGs, cursor bitmaps and fonts |
| `furnishings/` | Definitions, user definitions and SVG graphics |
| `themes/` | UI and canvas theme files |
| `textures/` | Normal maps and AO companions |

The root `planner.py`, `furnishings.py` and `theme.py` modules expose application APIs for imports.

## Data and coordinates

World positions and dimensions use millimeters, with positive Y pointing up. Screen coordinates use pixels. The viewport owns conversion between these coordinate systems.

Models hold object data and derived geometry. The catalog resolves furnishing definitions independently of the window. Compound furnishings carry composed artwork and resolved components while behaving as a single furnishing in selection, persistence and collision handling. Decompose creates scene objects from those components.

Walls host doors and windows. Pillars are rectangular wall subclasses with furnishing-style handles. Columns use curved footprints. Geometry code supplies footprints, joins, hit testing and measurement anchors.

Project serialization validates object data and embeds the custom furnishing resources needed by a drawing. History records undoable scene edits. Clipboard operations use portable selection snapshots and validate placements as a transaction.

## Viewport

The viewport is a QWidget composed from behavior classes sharing state initialized in `planner_app/viewport/widget.py`.

Numeric polygon clipping, spatial queries, wall-junction construction and boundary tracing live in `planner_app/geometry/` and run without Qt or scene models. The viewport adapts Qt points, owner identities and canonical contours at that boundary, retains bounded trace histories, and constructs final painter paths. The numeric core now also covers wall bodies/footprints, measurement planning, snapping, attachments, group constraints and opening validation. Native path operations use a backend contract with a Qt desktop implementation; sparse edit diff/replay is Qt-free while capture, restoration and event coordination remain desktop adapters. See the [geometry package contracts](GEOMETRY.md) and [editing boundary notes](EDITING_PORTS.md).

| Module | Responsibility |
| --- | --- |
| `interaction.py` | Mouse and keyboard gestures, modifiers and cancellation |
| `placement.py` | Sidebar drops, opening fitting and placement previews |
| `tools.py` | Held-key opening placement |
| `scene.py` | Selection, attachments and scene edits |
| `geometry.py` | Footprints, joins, hit testing and measurements |
| `snapping.py` | Grid, alignment and footprint targets |
| `furnishing_handles.py` | Resize, rotation and pivot gestures |
| `clipboard.py` | Copy, cut and paste |
| `context_menu.py` | Object actions |
| `rendering.py` | Grid, objects, measurements, rulers and overlays |

Scene revisions identify changes relevant to geometry, rendering and interaction caches. Painting reuses render commands and raster coverage where possible. Dirty regions limit repaint work during gestures. Raster allocation follows a shared 128 MiB preview budget.

Set `PLANNER_VERIFY_RENDER_REVISIONS=1` to compare revision-keyed caches with value-based validation during development.

## Appearance and text

`graphics/palette.py` supplies named UI and canvas color roles. Theme loading resolves inheritance and applies the selected pair. Stylesheets and cached artwork use these roles.

UI icons and furnishing palette previews use UI colors. Canvas furnishing artwork uses canvas colors. SVG paint is mapped into cached renderers; source assets retain their authored colors.

Scene furnishing renderers load on demand. Color changes replace lightweight palette maps without parsing unused catalog entries. A bounded cache (128 entries, 8 MiB of source SVG) reuses parsed artwork, normalized dash patterns, lettering measurements and fixed-detail anchors by source contents, canvas font, nominal furnishing dimensions and line width; color variants do not accumulate in that cache. Per-size SVG variants retain at most 16 entries per renderer. Fixed-detail transforms use physical furnishing dimensions, independently of camera zoom; SVG exports bake the resulting transforms. Hit coverage includes physical dimensions in its cache identity when fixed details are present.

Furnishing text is centered within its owning component and stays horizontal in the final drawing, with size capped by both the authored screen size and its proportion to the source artwork. The smallest singular scale of the component's text transform caps uniform lettering scale during zooming and nonuniform resizing. Compound SVGs retain component coordinate frames for this layout. Text transforms compensate for SVG and painter orientation, preserve drawing order and reuse a bounded cache of prepared renderers across painting and export.

Fonts in `assets/fonts/` register with Qt at startup. UI text, rulers and measurements use Noto Sans. Canvas labels and north-arrow lettering use the canvas theme's `labelFont`. Measurement text uses native fraction shaping, constructed fractions or fallback glyphs according to font support. SVG export converts text to outlines.

## Export and recovery

The Export tab configures a crop, scale and presentation overrides. PNG and SVG rendering share scene geometry, visibility and border drawing. PNG texture compositing applies normal-map lighting, then AO multiplication controlled by overall texture strength. AO sampling matches the normal map's dimensions. The vignette uses a fifth-order smoothstep transition.

Preview borders are painted independently of the PNG scene snapshot or SVG scene data. Border-background changes invalidate border strips without rebuilding scene artwork. Color-picker events update the effective palette immediately and coalesce viewport repaint requests over 33 ms; accepting or cancelling stops pending requests and applies the final or restored settings. Saved SVG files still contain the complete border and scene.

SVG preview data retains named paint roles for canvas, architectural/furnishing lines and grid. Palette edits recolor existing vector layers while retaining parsed clip paths; they do not regenerate the export scene. Transparent-object replay caches overlap clips by ordered command bounds, background silhouettes and unfilled stroke geometry, independently of paint colors. Geometry, pen-width, stroke-style and mask changes invalidate those clips, including reshapes that retain their bounding rectangle. This cache retains at most 8192 commands and 262144 native path elements.

SVG material fills paint the wall silhouette's base color once, with transparent vector hatch patterns above it. Background rectangles must not repeat inside tiles: antialiasing in SVG viewers exposes tile seams. Preview layers retain only referenced definitions and their dependencies; identical clip definitions share parsed native paths. Global styles conservatively retain all definitions.

Transparent replay skips visibility calculations for background-only commands while retaining their occlusion masks. Large unfilled outlines reject masks outside a conservative stroked ink envelope before the ordered boolean operations. Sparse antialias differences from Qt curve quantization are checked against a frozen dense-scene reference. SVG previews retain at most one alternate solid-object state with source size capped at 8 MB; scene geometry, layout and non-palette appearance changes invalidate it. Alternate states retain vectors only, with raster images still subject to the shared preview budget.

SVG paint bindings index the layers affected by each role, including inherited group paints and transitively referenced gradient/pattern definitions. Only affected layers reload; unchanged colors reload none. Adjacent layers combine when their ordered, transformed clip paths have identical native geometry and fill rules. Clip IDs do not determine equivalence, and paint order, ancestor wrappers and opacity remain intact. Frozen-renderer checks compare exact pixels across recolors, zooms, crops and nonuniform scales.

Session handling checkpoints scene and UI state and restores recovery data on launch. Project file operations and recovery checkpoints have separate storage responsibilities.
The production entry point holds a process lock for the resolved recovery path
through shutdown; dead owners can be reclaimed after crashes. Checkpoints retain
the editing camera while the Export tab uses its separate preview camera.
Project reads are bounded to 64 MiB, and CLI exports replace their destination
through an atomic save file. Detached opening validation uses per-parent intervals
and indexed wall bounds before exact collision checks.

Furnishing SVG validation runs before native parsing. Compound expansion has
per-definition and scene budgets, including repeated references in shared graphs.
Saved projects retain custom resources used only by undo/redo, and reusable
arrangements retain imported dependencies in their own definition file.

## Development checks

From the repository root:

```powershell
python checks/run_checks.py
python checks/run_checks.py check_export_plan.py
```

The runner executes checks in isolated Qt processes with temporary session,
startup and preference files. It rejects disabled assertions and unhandled Qt
callback or thread exceptions, even when Qt returns a successful exit code.
Use focused checks for the area being changed and the complete suite for broad validation.

[Rendering diagnostics](RENDER_DIAGNOSTICS.md) describes captures, probes and native interaction measurements. Resource authoring is covered by the [furnishing](resources/FURNISHINGS.md), [theme](resources/THEMES.md), [texture](resources/TEXTURES.md) and [asset](resources/ASSETS.md) guides.

## Cross-framework parity

The [parity specification](parity/README.md) records the implemented controls,
visual states, layouts, viewport gestures and file interchange rules. Its gallery
includes measured widget properties and resolved styles; its scenario index maps
rules to desktop regressions, with portable JSON examples for initial numeric
conformance. Consult the verification guide before claiming complete parity.
