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
| `planner_app/object_schema.py` | Desktop object metadata and shared model-record encoding |
| `planner_app/scene_snapshot.py` | Model capture/replay without viewport or interaction imports |
| `planner_app/view_settings.py` | Shared view capture/application for projects, previews and exports |
| `planner_app/units.py` | Unit conversion and measurement formatting |
| `planner_app/number_expressions.py` | Bounded arithmetic parsing for numeric editors without code execution |
| `planner_app/paths.py` | Resource locations |
| `planner_app/preferences.py` | Initial presets and preferences |
| `planner_app/project_codec.py` | Project serialization and validation |
| `planner_app/project_history.py`, `history_edits.py` | Undo/redo storage and edits |
| `planner_app/scene_changes.py` | Scene change tracking |
| `planner_app/room_detection.py` | Shared wall-boundary classification, enclosure paths and derived room areas |
| `planner_app/geometry/` | Portable numeric core and explicitly Qt-dependent stair/dimension adapters |
| `planner_app/export_bounds.py` | Export footprint bounds |
| `planner_app/export_plan.py` | PNG/SVG rendering and module CLI |
| `planner_app/pdf_export.py` | Physical multipage PDF assembly and vector material tiles |
| `planner_app/export_preview.py`, `export_preview_worker.py` | Coalesced asynchronous preview jobs and isolated persistent renderer |
| `planner_app/print_layout.py`, `ui/print_export.py` | Physical paper lattice, overlap, selection and page export jobs |
| `planner_app/graphics/title_block.py`, `graphics/scale_bar.py` | Export-only decorations shared by preview and file rendering |
| `planner_app/graphics/retained_dimensions.py` | CPU-native editor dimension replay with painter fallback |
| `planner_app/crash_reporting.py` | Crash reports |
| `planner_app/garbage_collection.py` | Garbage-collection scheduling |
| `planner_app/graphics/` | Palettes, fonts, icons, symbols and vector artwork |
| `planner_app/ui/` | Window, sidebar, properties, settings, projects and recovery |
| `planner_app/ui/export_panel.py` | Export controls, overrides and preview configuration |
| `planner_app/ui/reference_image.py`, `reference_calibration.py` | Exclusive backdrop editing and two-point scale calibration |
| `planner_app/ui/problems.py` | Modeless current-scene problem inspection, repair, location and ignored suggestions |
| `planner_app/ui/help_viewer.py` | Native Markdown help rendering and navigation |
| `planner_app/ui/about.py` | Standalone About splash and bundled license notices |
| `help/` | Bundled user guide, independent of the renderer |
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

`activity_log.py` records lightweight project activity independently from bounded
undo retention. Its modeless browser lives in `ui/activity_log.py` and is opened
from View > Activity Log. Restorable entries link to live scene or Export
journals; persistence validates scene links against encoded edit fingerprints.
See [Activity Log](ACTIVITY_LOG.md) for scope, lifecycle and validation rules.

## Viewport

The viewport is a QWidget composed from behavior classes sharing state initialized in `planner_app/viewport/widget.py`.
Model snapshot transformations live in `scene_snapshot.py`; named tuple layouts
in `history_records.py` preserve the existing sparse-edit and file contracts.
History decoding imports those transformations directly. The viewport retains
gesture cancellation, scene membership, stair links, notifications and repainting.

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
Stable editor dimensions reuse a retained CPU layer; editing, guides, panning
and exports retain their painter paths. See the [editor audit](EDITOR_PERFORMANCE_AUDIT.md)
for eligibility, exact-pixel checks and measured limitations.

Set `PLANNER_VERIFY_RENDER_REVISIONS=1` to compare revision-keyed caches with value-based validation during development.
The reference includes arrow direction, furnishing layer order, room-label unit
overrides, raw opening dimensions and recovery geometry flags.

Scene rendering dispatches to explicit opaque and transparent passes. Transparent
capture passes renderer maps and the capture engine as arguments; it does not
replace the live viewport's renderers or solid-object state. Annotation objects
form a separate ordered pass. Existing command, geometry and raster caches keep
their ownership and limits.

`interaction.SelectionTarget` resolves the effective pointer target for hover,
cursor, left press, double-click and context menus. `geometry.HitTest` supplies
the underlying scene hit; furnishing handles can supersede it. Keep handle paint
order and control-point/body priority consistent with that resolver. Selected
whole-object groups resolve nearby endpoints to group movement, while explicit
vertex selections keep vertex editing.

Room detection reuses structural wall boundaries and revision keys for live tint,
room-label area lookup and exterior dimension classification. Its derived paths
and areas are not saved as scene objects. Wall/stair occupancy is combined by
the cached numeric boundary tracer in world units, with a separate room trace
context. This avoids malformed Qt boolean-union holes at near-coincident faces
without changing project coordinates or rebuilding on camera changes.
The traced contours retain clockwise outer boundaries in world coordinates:
exterior dimensions offset to the left of directed spans, into empty space.
The desktop `geometry/measurement_stacks.py`
and `geometry/stair_annotations.py` adapters depend on Qt, unlike the portable
numeric core. Stacked dimensions support one/two/three tiers, wall-axis or
wall-face references, and combined faces for overlapping partition assemblies.
Their displayed overall comes directly from the measured endpoints. The portable
`geometry/dimension_chains.py` balances shared rounded positions across all tiers,
preserving nominal opening widths and preferring mirror symmetry before minimizing
display error. Incomplete chains retain ordinary geometric labels; rounding never
changes model coordinates. Editor and export use the same display-length overrides.

Options always edits the project settings. While Export is active, the export
panel snapshots that project view, applies sparse overrides to the viewport,
and restores the project view on exit. Dimension units, precision, mode/reference,
splitting and visibility each support sparse export overrides. Project and Export
share `ui/wall_dimensions.py` for the wall controls and their input/layout rules.
Project serialization, project loading, preview capture and file rendering also
share `view_settings.py`. Captured/applied option dictionaries are independent
copies. Settings controls explicitly route project edits through
`EditProjectSettings` while Export owns the effective preview; reconciliation
remains available for direct viewport mutations.
Opening Options while Export is active first switches to Build and restores the
project view. Export's dimension master sets all category overrides,
whereas the editor master preserves remembered category choices.

## Appearance and text

`graphics/palette.py` supplies named UI and canvas color roles. Theme loading resolves inheritance and applies the selected pair. Stylesheets and cached artwork use these roles.

UI icons and furnishing palette previews use UI colors. Canvas furnishing artwork uses canvas colors. SVG paint is mapped into cached renderers; source assets retain their authored colors.

Scene furnishing renderers load on demand. Color changes replace lightweight palette maps without parsing unused catalog entries. A bounded cache (128 entries, 8 MiB of source SVG) reuses parsed artwork, normalized dash patterns, lettering measurements and fixed-detail anchors by source contents, canvas font, nominal furnishing dimensions and line width; color variants do not accumulate in that cache. Native renderer maps separately retain at most 128 entries and 16 MiB of estimated artwork storage each, accounting for embedded PNG dimensions and capacity for size variants. Oversized artwork remains drawable without cache admission. Project replacement clears realized normal, selected and grouped artwork, plus hidden quick-search rows. Per-size SVG variants retain at most 16 entries per renderer. Fixed-detail transforms use physical furnishing dimensions, independently of camera zoom; SVG exports bake the resulting transforms. Hit coverage includes physical dimensions in its cache identity when fixed details are present.

Furnishing text retains its authored glyph-center position within its owning component and stays horizontal in the final drawing, with size capped by both the authored screen size and its proportion to the source artwork. The smallest singular scale of the component's text transform caps uniform lettering scale during zooming and nonuniform resizing. Compound SVGs retain component coordinate frames for this layout. Text transforms compensate for SVG and painter orientation, preserve drawing order and reuse a bounded cache of prepared renderers across painting and export.

Fonts in `assets/fonts/` register with Qt at startup. UI text, rulers and measurements use Noto Sans. Canvas labels and north-marker lettering use the canvas theme's `labelFont`. Measurement text uses native fraction shaping, constructed fractions or fallback glyphs according to font support. SVG export converts text to outlines.

## Export and recovery

The Export tab configures a crop, scale and presentation overrides. Digital,
Architectural and Print modes share scene geometry and decorations. Physical
modes use a 300-PPI design space; output PPI changes resolution while preserving
physical geometry, strokes and camera alignment. Print selects only complete
paper cells, repeating the border, title block and scale bar per sheet. Signed
overlap shifts source drawing coverage while sheet spacing remains fixed.

PNG texture compositing applies normal-map lighting, then AO multiplication
controlled by overall texture strength. NumPy computes exact double-precision
lighting and RGBA palette expansion. Its unused OpenBLAS pool is limited to one
thread before lazy import. AO sampling matches the normal map's dimensions.
The vignette uses a fifth-order smoothstep transition. Interactive Composite
sliders reuse the scene and decoration buffers while updating effects live.

`export_preview.py` manages a persistent offscreen QProcess, coalesces stale
jobs and adopts only current results. Scene preparation is reused across PNG
pages, and SVG pages share prepared model vectors. The worker has a 768 MiB
Windows memory limit independent of the viewport's retained-raster budget;
allocation failures release prepared caches and retry once. See the
[export audit](EXPORT_PERFORMANCE_AUDIT.md) for cache keys and validation.

Saved GUI exports use `ui/export_progress.py` and `export_worker.py`. A modal,
cancellable dialog runs a QProcess while keeping the editor event loop responsive.
The worker receives an unsaved scene snapshot, resolved catalog, export arguments,
palette and typography. It creates its own Qt application without showing widgets
and never acquires the editor's session lock. Source and frozen builds dispatch
the private `--export-worker` entry point before normal app startup. Preview
rendering uses the separate private `--preview-worker` entry point. The public
CLI continues to render directly.

PDF types reuse the same PNG/SVG Print page renderers. `pdf_export.PdfExporter`
places raster pages losslessly at their physical sheet size or paints outlined
SVG pages through the shared clipping renderer into Qt's QPdfWriter. Material
patterns are converted into clipped vector tile references, avoiding Qt SVG's
bitmap pattern brushes. SVG fill-only leaves use transparent strokes to avoid
Qt PDF expanding a NoBrush pen around their ink. The progress process uses one
staging destination for all PDF pages, publishes only after the writer closes,
and retains existing cancellation/failure guarantees. No extra runtime dependency
or editor-rendering path is introduced.

The worker reports preparation, rendering, encoding/optimization and saving stages.
It writes to a temporary file beside the destination. Success atomically replaces
the destination; cancellation kills the isolated process and removes temporary
files. Errors preserve the destination and return to the normal export error UI.
Reference-image payloads are excluded from the worker snapshot. Optimized PNG
transfers RGBA pixels through Qt's QByteArray/ArrayBuffer conversion in 192 KiB
chunks and returns encoded bytes through the same binary bridge, without base64.
UPNG uses scalar statistics accumulators and bulk 8-bit index copies without
changing the quantizer's sample or arithmetic order. Python's native zlib handles
lossless deflation at pako's original compression level. Frozen seeded parity
checks preserve palette, alpha, filtered pixels, decoded pixels and DPI while
allowing the compressed stream to differ. Windows workers suppress system crash dialogs so native failures return
to the parent's error UI instead of waiting for an inaccessible crash prompt.

Preview borders are painted independently of the PNG scene snapshot or SVG scene data. Border-background changes invalidate border strips without rebuilding scene artwork. Color-picker events update the effective palette immediately and coalesce viewport repaint requests over 33 ms; accepting or cancelling stops pending requests and applies the final or restored settings. Saved SVG files still contain the complete border and scene.

PNG preview borders and scale bars use native-export-density bitmap caches with
filtered display scaling, including during interaction and Print drag previews.
All border styles share the strip cache. If retention is refused or a strip is
oversized, `graphics/preview_bitmap.py` streams only visible native pixels in
temporary tiles below 300 KiB instead of switching to vector display. Cached
strips and tiles include filter guards to preserve fractional pan/zoom edges.
Scale-bar bitmaps participate in the aggregate viewport raster budget. SVG
previews continue to paint vector decorations.

SVG preview data retains named paint roles for canvas, architectural/furnishing lines and grid. Palette edits recolor existing vector layers while retaining parsed clip paths; they do not regenerate the export scene. Transparent-object replay caches overlap clips by ordered command bounds, background silhouettes and unfilled stroke geometry, independently of paint colors. Geometry, pen-width, stroke-style and mask changes invalidate those clips, including reshapes that retain their bounding rectangle. This cache retains at most 8192 commands and 262144 native path elements.

SVG material fills paint the wall silhouette's base color once, with transparent vector hatch patterns above it. Background rectangles must not repeat inside tiles: antialiasing in SVG viewers exposes tile seams. Preview layers retain only referenced definitions and their dependencies; identical clip definitions share parsed native paths. Global styles conservatively retain all definitions.

Transparent replay skips visibility calculations for background-only commands while retaining their occlusion masks. Large unfilled outlines reject masks outside a conservative stroked ink envelope before the ordered boolean operations. Sparse antialias differences from Qt curve quantization are checked against a frozen dense-scene reference. SVG previews retain at most one alternate solid-object state with source size capped at 8 MB; scene geometry, layout and non-palette appearance changes invalidate it. Alternate states retain vectors only, with raster images still subject to the shared preview budget.

SVG paint bindings index the layers affected by each role, including inherited group paints and transitively referenced gradient/pattern definitions. Only affected layers reload; unchanged colors reload none. Adjacent layers combine when their ordered, transformed clip paths have identical native geometry and fill rules. Clip IDs do not determine equivalence, and paint order, ancestor wrappers and opacity remain intact. Frozen-renderer checks compare exact pixels across recolors, zooms, crops and nonuniform scales.

Session handling checkpoints scene and UI state and restores recovery data on launch. Project file operations and recovery checkpoints have separate storage responsibilities.
Committed scene notifications precede ancillary activity-log I/O. Archive errors
cannot suppress dirty tracking or undo/redo. Routine problem checks prepare one
wall/interval index per pass, sharing recovery's indexed validation.
Opening placement and collision validation share physical wall-body construction.
Material ownership partitions used for painting do not remove overlapping solid
bodies from placement constraints; actual footprint cuts remain respected.
Startup, restored sessions and project replacement select Build. Save and Save As
preserve the current workspace and active export preview, committing pending
export-field text while serializing the editor camera/settings separately.
Export settings remain saved, but loading does not activate Export or its preview worker.
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

Startup establishes crash reporting before importing resource-dependent UI code.
Theme collection replacement validates both UI and canvas resources before
changing the active dictionaries. A damaged initial collection remains available
as a recorded initialization error until the entry point reports its path.
Export workers return bounded exception types/tracebacks; preview stderr is also
retained and forwarded to the editor's existing crash log.

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
