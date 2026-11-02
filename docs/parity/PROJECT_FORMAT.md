# Project interchange contract

Baseline: `ui/projects.py`, `project_codec.py`, `object_schema.py`,
`project_history.py`, `project_recovery.py`, `geometry_recovery.py`.
The generated [reference project](reference/example.plan) is a real encoded,
decoded and re-encoded example, with the settings tables captured at generation time. It is a
test asset, not a user's project. Do not confuse it with an exhaustive schema.

## FILE-01: envelope and units

`.plan` is UTF-8 JSON, envelope `format: "Planner Project"`, integer `version: 1`.
The desktop accepts a UTF-8 BOM through recovery. Current input/output limit is
64 MiB. Version mismatch, unreadable input and malformed JSON are not equivalent
to an individual invalid optional setting.

World coordinates/dimensions are millimeters, +Y upward. Numbers must be finite.
Do not round model geometry to display precision or use pixel coordinates in
records. JSON booleans are not numeric dimensions. Camera zoom and pan are view
data, not model transforms. Preserve collection order because it can affect
drawing, picking, attachment fitting and tie resolution.

| Root field | Meaning |
| --- | --- |
| `scene` | Object records, groups and individually hidden indices |
| `settings` | Build, visibility, units, collision, snapping, measurement and export settings |
| `view` | Editing zoom and `[panX, panY]` |
| `ui` | Project panel splitters, properties collapse state and export section state |
| `furnishingDefinitions` | Optional dictionary of embedded custom definitions |
| `history` | Optional versioned sparse undo/redo journal |

`scene` and `settings` are required for normal strict decoding. Other defaults
and recovery behavior are implemented separately. Window position, monitor,
outer size and maximized state belong to application session state, not projects
or startup templates. Project loading preserves the current window placement.
Legacy `ui.geometry`, `ui.size` and `ui.maximized` fields are ignored and omitted
from subsequent saves. Session recovery retains and validates its own window
geometry, size and maximized state independently of the embedded project.

## FILE-02: scene records and references

`scene.objects` is ordered. Groups and hidden entries contain **zero-based indices
into this array**, not object IDs. Opening `parent` is also an array index.
`id` is a separate persistent object identifier. Do not swap these two meanings.
Normal object IDs must be valid and unique; recovery can regenerate bad IDs.

All encoded objects include `type`, `id`, `measurementHidden`. Optional
`originalMaterial` retains missing-material provenance; `geometryIssues` retains
highlighted geometry problem codes. Unknown fields are not permission to invent
an unsupported object class.

Historical field names `firstMiter`/`secondMiter` now store chamfer amounts:
0 means uncut, 1 means the full flat cut. See [CHAMFER-01](CHAMFERS.md) for geometry
and the one-time workspace migration; the UI must display stored values directly.

| Family | Geometry/other fields |
| --- | --- |
| Wall-like objects | `first`, `second`, `width`, `firstMiter`, `secondMiter`, `material` |
| Furnishing | `first`, `second`, `width`, `definition`, `behindCounters`, `flipHorizontal`, `flipVertical` |
| Label | `first`, `second`, `width`, `text`, `intensity` |
| RoomLabel | Label fields plus optional `unitsOverride`; room area is derived, not serialized |
| NorthArrow | `first`, `second`, `width`, `intensity` (0–1, defaults to 1 when absent) |
| Attached opening | `parent`, `center` fraction along wall, `length`, class fields below |

Object types include Wall, Counter, Railing, Stair, Pillar, Column, Elevator,
Arrow, MeasurementGuide, BoundaryLine, DashedLine, SolidLine, AngleGuide, Furnishing,
Label, RoomLabel, NorthArrow and the opening types.
Class inheritance does not imply that every field applies to every type. The
encoder and examples define actual wire records. A furnishing's endpoint segment
and width encode oriented dimensions; it is not an axis-aligned screen rectangle.
Furnishing flip flags default to false when absent in older projects; saving can
write those defaults explicitly. They do not apply to symmetrical Elevator
objects just because those objects share the SVG renderer. The earlier gallery's
`example.plan` predates these optional fields; the new workflow/render projects
include them explicitly.

Opening class fields:

| Type | Additional fields |
| --- | --- |
| Door | `hingeAtSecond`, `swingsOutwards`, `measurementFlipped` |
| SwingingDoor | `hingeAtSecond`, `measurementFlipped`; no facing field |
| DoubleDoor | `swingsOutwards`, `measurementFlipped`; no hinge field |
| SlidingDoor | `hingeAtSecond`, `panelsFlipped`, `measurementFlipped` |
| PocketDoor | `hingeAtSecond`, `measurementFlipped` |
| BarnDoor | `hingeAtSecond`, `swingsOutwards`, `measurementFlipped` |
| BifoldDoor | `swingsOutwards`, `measurementFlipped` |
| OpenDoorway | `measurementFlipped` |
| Window | `swingsOutwards`, `measurementFlipped` |
| SilledWindow | `swingsOutwards`, `sillDepth`, `measurementFlipped` |
| CasementWindow | `hingeAtSecond`, `swingsOutwards`, `measurementFlipped` |
| AwningWindow | `swingsOutwards`, `measurementFlipped` |
| DoubleCasementWindow | `swingsOutwards`, `measurementFlipped` |
| Fireplace | `swingsOutwards`, `depth`, `depthOffset`, `material`, `measurementFlipped` |

Fireplace length is its span **along** the wall; depth is front-to-back and cannot
be less than wall thickness for a normally valid placement. Depth offset chooses
its position across that thickness. Openings require an actual Wall parent.
Resolve attachments after constructing unattached records, retaining indices.

All five window types additionally encode `windowWell`, `wellDepth` and
`wellDashed`. Older records default to false, 600 mm and false respectively.
These fields do not apply to doors or fireplaces. `RoomLabel.unitsOverride`
is a display unit from `unitModes`, or absent/null for project/export inheritance.
It overrides both project and export unit choices without changing geometry.

MeasurementGuide, BoundaryLine, DashedLine, SolidLine and AngleGuide encode `textOffset`. AngleGuide also
encodes `middle: [x, y]` for its central control point, in addition to `first`
and `second` for the arm endpoints.
DashedLine and SolidLine also encode `weightClass`, defaulting to `Objects`.
Accepted wire values are `Walls`, `Objects`, `Furnishings` and `Measurements`;
the last displays as Dimensions. All linear/angular guides have zero body width.

Railing/Stair include autosizing/manual count settings. Arrows encode `solidTip`,
`tipSize`, `tipSizeMode: "millimeters"`, `intensity`. Legacy tip modes need the
compatibility conversion in `ReadArrowTipSize`; a port must not multiply every
stored arrow-head size by width. Furnishing `children` can retain resolved
compound fallback records for installs missing the parent definition.
Arrows optionally encode `directionReversed` (false when absent), which tracks
their direction-button icon state. Stairs encode the same flag for flight
direction. Arrow geometry reverses by exchanging endpoints; the icon flag is
not an additional transform to apply on load.

## FILE-03: settings and embedded resources

UI and canvas theme selections are application preferences. Project settings
include the current wall tool/material/size; snap
master and grid/control-point/corner/midpoint/alignment flags (stored under `grid`,
`vertices`, `corners`, `midpoints`, `alignment`); connected modes/group/local
transforms; category visibility; grid/measurement visibility and precision;
build presets; linework, grid intensity, measurement and collision tables;
railing/stair defaults; units; separate export overrides. The reference project
contains a dated example of their keys and defaults. Omitted export keys inherit normal
project values or the option's own default; an explicit override is not the same
as an inherited value even if it presently renders identically. Legacy projects
without `snap.corners` inherit that flag from `snap.vertices`, preserving their
previous combined snapping preference.

A successful GUI export captures all effective export controls as explicit
`exportSettings`, including complete visibility, dimension, grid and line-weight
groups, crop, scaling, theme and compositing defaults. Later editor changes do
not replace this snapshot. Cancelled, declined or failed exports do not capture
it. The capture is a project edit and participates in export undo/redo.
Color values may be `null` to explicitly retain the Theme choice under the
captured `canvasTheme`; this preserves distinct wall and object outline colors.
`textureScale: null` retains a fixed filename's tiling ratio when it exceeds
the scale control's range, rather than changing the output or saving an invalid value.
Editor-only construction sizes and automatic-sizing units are not captured.
`check_export_snapshot.py` covers capture, persistence and isolation.

`settings.wallMeasurementMode` is `All`, `Exterior` or `Exterior stacked`.
New projects default to Exterior stacked; older files without the field load All.
`settings.wallMeasurementReference` is `Centerline` or `Wall faces`, defaulting
to Wall faces when absent. Default-valued fields may be omitted on save.
Only stacked mode uses the reference choice. Both fields can also occur under
`exportSettings` as independent sparse overrides. Without those overrides, Export
and CLI use the project values. `exportSettings.measurementPrecision` is High,
Medium or Low. `exportSettings.measurementSettings` is a sparse object containing
doors/windows (0, 1 or 2) and stairs/counters (0 or 2); absent keys inherit project
values. These overrides apply to preview, saved file output and CLI rendering.
`exportSettings.measurementTextSize` is 1.5 (Small), 2 (Medium, the default) or 2.5 (Large),
expressed in printed millimetres of visible numeral height. Font pixels round
to the nearest design pixel. Physical output uses a 300-PPI design space and
Digital assumes 300 PPI. Dimensions, guide labels and scale-bar numbers use
D-DIN Condensed and share this size; the editor's text remains unchanged.
`exportSettings.borderTextSize` independently selects ruler, unit and reference-zone
text height: 1.5 (Small), 2 (Medium, default) or 2.5 (Large) mm. Text-bearing border
minimums grow with this value, independently of dimensions.
Digital uses `exportSettings.borderSize` (integer pixels, 1–128, default 28).
Print/Architectural use `exportSettings.borderWidth`, a positive project length
in millimetres (default 200), displayed in project units. PPI and scale changes
preserve the requested project length. Layout rounds to the nearest design pixel
and applies the text-dependent minimum. Neither preference is an editor setting.
The earlier 3.5 mm value loads as Large (2.5 mm).
The earlier 0 value loads as Small (1.5 mm).
Options always edits project settings. Opening it while Export is active first
switches to Build and restores the editor view. Export
controls and active-export canvas shortcuts edit export overrides, never the
project view restored on leaving Export.

`settings.exportFolder` and `settings.exportFileName` remember destinations per
project/session. An unset folder resolves to the plan's directory, or the app
directory for an unsaved plan. These are not global browsing preferences.

Optional `settings.roomStyle` stores the editor's room appearance: `"Canvas"`
uses the canvas color and `"Tinted"` uses the theme's room fill. The default is
`"Tinted"`. Optional `settings.solidRooms` defaults to false; when true, grid
strokes are clipped out of detected room interiors independently of room style.
`solidRooms` requires an actual boolean.

`settings.exportSettings.roomStyle` and `settings.exportSettings.solidRooms` are
independent optional overrides. Without an override, Export inherits the editor's
corresponding value; overrides affect previews, saved files and the CLI's
saved-settings path. No room geometry is serialized.

`settings.exportSettings.drawOpeningOutlines` is an optional boolean, default true.
It independently controls the thin outlines across door passages in exports and
previews. It does not hide jambs or affect the editor. The value is captured in
export bundles and honored by the CLI's saved-settings path. Coverage:
`check_export_opening_outlines.py`, `check_export_settings_core.py`.

Legacy `settings.floors` and `settings.exportSettings.floors` booleans remain
accepted when loading and recovering projects: true maps to `"Tinted"`, false to
`"Canvas"`. An explicit `roomStyle` takes precedence at the same scope. Legacy
values still require actual booleans; new saves use `roomStyle` and `solidRooms`.
Coverage: `check_export_floors.py`, `check_project_recovery.py`.

`buildSettings.wallWidths`, `openingSizes` and `miscSizes` retain metric source
defaults in centimeters. Optional `buildSettings.imperialSizes` maps wall preset
indices (`"0"` through `"3"`) or opening/misc class names to explicit imperial
default overrides in **millimeters**. Omission means derive nominal whole inches
from the metric default using `placement_sizing.py`; it does not change existing
scene records. Overrides must be finite numbers from 1 through 101600 mm, with
known size keys. Projects and sessions preserve these overrides; metric edits
and Reset remove the corresponding override. Catalog resource dimensions always
remain authored metric dimensions, even when objects placed from them use
nominal imperial sizes. Current wall-tool width and all scene records remain
actual millimeter values.

`stairStepSizes` and `railingSpacings` retain their metric source limits in
centimeters. Optional `settings.imperialAutoSizes` holds `stairs` and/or
`railings` groups of exact millimeter overrides. A stairs group requires
`minimum`/`maximum`; railings also require `target`. Values must be finite,
between 1 and 101600 mm, and satisfy minimum ≤ target ≤ maximum. Without an
override, imperial limits use the same nominal-inch rule as placement sizes.
Metric edits clear that group's imperial overrides; imperial Reset restores
the nominal default. Project and session saves preserve custom imperial limits.
Export render data can carry `autoSizingUnitsMode` to keep autosizing tied to
the source project while rendering dimension text in another unit; normal
project saves derive it from `unitsMode`.

Optional `settings.referenceImage` holds a single reference backdrop. It contains
`path` (source path for the editor), `data` (base64 original raster bytes), boolean
`visible`, `opacity` in [0,1], `center: [x,y]`, positive `width` and
`height` in millimeters, and `angle` in degrees. Loading uses embedded bytes, not
the path. Records are absent when no image is loaded. New projects default to no
image; saved projects/sessions retain hidden images and their placement. Payloads
are limited to 40 MiB and decoded images to 32,767 pixels per side/100 million
pixels, within the existing 64 MiB project limit. Qt's decoder allocation limit
can also reject images below the pixel limits. Load errors distinguish unreadable
data, excessive side length, excessive pixel count and decoder memory failures.
Size errors report the source pixel dimensions, the relevant limit and advice to
resize the image. Failed replacements retain the existing reference image.
Coverage: `check_reference_image_errors.py`. Invalid image settings can be
dropped by metadata recovery without discarding scene geometry. Image decoding
and UI/canvas interaction use Qt adapters; the stored transform/opacity record is
independent of the UI framework. Calibration updates width/height and center in
this record; its temporary points and one-use unit choice are not serialized.
Legacy `locked` metadata is ignored and omitted when saved. Editing availability
comes from the active reference-image panel rather than a persisted lock flag.

`furnishingDefinitions` keys are definition keys, **not display names**. Name
collisions are allowed. Embedded records include name, category/categories,
keywords, physical width/length and inline `svg` text. Compounds include component
definition references/transforms and compound center. Used custom resources,
resources retained only by undo/redo, and their required custom dependencies are embedded.
History-free exports and startup templates omit history-only resources. Project definitions remain scoped
to the project; do not overwrite the installation's library on load.

Missing definitions use available resolved compound children when possible;
missing children can fall back to null artwork. Missing materials retain their
original name for later recovery. Missing assets should not make otherwise
recoverable geometry inaccessible. Validate embedded SVG and dependency cycles/
depth before using them; see codec/recovery checks for rejection/recovery cases.
SVG limits are 8 MiB, 50,000 elements and 64 nesting levels. References must be
local fragments or bounded inline PNG data; external resources, document types,
entities and active content are rejected. Expanded compounds are limited to
10,000 nodes each and complete scenes to 100,000 nodes, counting repeated placements.

## FILE-04: undo journal

History envelope: `format: "Planner Changes"`, integer `version: 1`, `undo` and
`redo` arrays. Each edit has `changes`, `groups`, `hidden`, `orders`. Change sides
are null or `[position, objectRecord]`; category indices are 0, 3, 5, 8. Unlike
scene records, history references parents/members by **object ID**. Serialized
orders use stringified category keys. Selection is not serialized as a scene
edit's geometry change. Do not serialize runtime identity addresses or tokens.

Scene edits with rotation context may additionally contain `editor`, a pair of
before/after dictionaries. Each dictionary contains `primary: [objectId, vertex]`,
`selection: [[objectId, vertex], ...]`, `rotation: objectId | null`, and
`pivot: [x, y] | null`. Primary object and vertex may both be null for an empty
selection. Validate object IDs, handle indices, selected rotation ownership and
finite pivot coordinates. This optional context preserves custom pivots and
their selections through geometry undo/redo and project/session round trips.
Older journals without `editor` retain their existing behavior.

Reference-image edits use the same journal. These edits have empty scene changes,
memberships and orders, plus `referenceImage: {changes, pivots}`. Its `changes`
maps each changed property to `[before, after]`; supported properties are center,
width, height, angle, opacity, path and data. Only replacement-image edits retain
pixel data. `pivots` holds the before/after editor pivot as null or `[x,y]`.
Visibility and panel activation are not journal edits. Validate the reference
delta chain against the current image alongside scene replay; validate historical
replacement bytes once per distinct image. Mixed edits survive project/session
restoration and remain undoable with reference controls closed.

Validate replay against the current scene in both directions before accepting
the journal. Incompatible history can be ignored without losing the scene;
malformed history is recoverable through the loader. Desktop limits: 200 edits,
16 MiB estimated retained payload; another runtime needs its own conservative
memory estimate. It need not reproduce Python `getsizeof` or Qt allocation sizes.
Export-option undo and scene undo are distinct workflows. See
[editing contracts](../EDITING_PORTS.md).

## FILE-04A: activity log

Optional top-level `activityLog` is a versioned `zlib-base64` envelope of
lightweight entries, validated scene-journal links and known issue state. It is
separate from the bounded `history` journal. Descriptions survive journal expiry;
Export links expire on reopening because Export's journal remains session-local.
Projects and session checkpoints retain this metadata, while startup templates
and export rendering snapshots exclude it. Invalid log data can be removed by
recovery without changing scene geometry. See [Activity Log](../ACTIVITY_LOG.md).

## FILE-05: recovery is a staged transaction

Dropping a single local `.plan` file anywhere in the main window, including the
canvas and sidebar input controls, uses the normal Open Project transaction.
Match the extension without case sensitivity. Preserve unsaved-change prompts,
recovery notices and restoration after load failure. Reject remote URLs,
directories, other extensions and multiple-file drops. Internal catalogue drags
continue through their existing placement handlers. See `check_project_file_drop.py`.

New Project loads the startup template. Close Project confirms unsaved changes,
then clears all scene objects, groups, hidden-object state, reference image,
export overrides and both undo histories without reading the startup file.
Category and measurement visibility return to factory defaults. Other editing
settings and panel layout remain in place, with the camera reset for the empty
canvas. The result is an unnamed, clean project with no recovery provenance.

Strict decoding is not the complete user-facing loading algorithm. Recoverable
loads first resolve Save/Discard/Cancel for the current project. Cancellation
stops before any incoming-map notices. After confirmation, clear the current
project and its recovery window before decoding or showing incoming issues.
Clearing the scene for loading preserves the current main-window geometry and
maximized/full-screen state; do not apply the factory window layout at this stage.
Keep a detached snapshot to restore the previous project if loading fails or
geometry recovery is cancelled. Read the incoming file after any requested Save,
including when reopening the same path.

Recoverable settings, IDs, references, resources and history are normalized in detached data.
Geometry problems show individual Remove/Highlight/Repair choices. Highlight
is unavailable for unrenderable geometry; Repair is unavailable without a valid
proposal. Removing a parent removes its attachments. Closing any issue dialog
cancels the whole load, including earlier staged choices.

Before applying a recovered project, preserve the exact original bytes in
`project-recovery` under the session folder. Open the recovered result unsaved,
show a save dialog suggesting the original path on Save, and show one report
of actions and backup location. Users may replace the original or choose a new
name. Successful saving clears the recovery-copy state; cancelling or failing
to save retains it. The original backup remains available. Preserve
recovery provenance and highlighted issues in subsequent saves. The existing
scene must survive any aborted/failed load. Do not replace it incrementally while
parsing a file. Recovery tests, not only valid-file examples, are required for
interchange parity.

The recovery report includes a scrollable tree of missing asset names and
affected scene objects. Clicking an asset frames/selects all its affected
objects; clicking an object frames/selects that instance. The report stays open
so users can inspect further entries, and closes with OK or the window controls.
The report is application-modal: users must dismiss it before interacting with
the editor or other Planner windows. Its entries still locate objects, keeping
keyboard focus inside the report. The report opens asynchronously so startup
restoration can finish without a nested dialog loop. Its missing-object list
refreshes after programmatic scene updates, including deletion and undo. An empty list
reports that no missing objects remain. Switching projects closes the report.
Location framing shows three times the selection bounds with a minimum 6000 mm
span in each axis, retaining surrounding context for small objects.
Missing compound dependencies locate their owning scene furnishing. Locating
reveals hidden targets (undoable) and enables furnishing visibility without
changing object geometry or replacing missing definitions.

Missing-asset notices belong to project loading/recovery. PNG/SVG rendering and
preview refreshes do not repeat them in the console. Built-in north markers are
not catalog assets and must not appear in the missing-furnishing list.
GUI previews and file exports use the editor's loaded catalog plus the project's
embedded definitions, rather than independently reloading the installation's
catalog. Standalone command-line rendering loads its own catalog once per run.
The module CLI applies saved export appearance and partial setting overrides with
the same inheritance as the Export tab. Mandatory scale is digital pixels/SVG
units per meter and supersedes saved scale mode, density and PPI. Format comes
from `-png`/`-svg` (PNG by default). Optional X/Y/width/length bounds in millimeters
override saved export bounds. Missing bounds use export-visible automatic bounds
with one-meter padding. Saved borders replace the removed `-ruler` option, and
automatic cropping no longer requires `-auto`. Input project files are not modified.


Missing furnishing provenance retains its original definition key/name for the
properties heading and recovery list. Recovery, properties and clipboard checks
share the same traversal of original keys, nested children and fallback artwork.
A missing catalog image or embedded Null artwork under an existing key is an
asset error too. Valid embedded definitions resolve their keys normally.
Catalog compounds retain unresolved child keys through decomposition and saving.
Properties show the original key with (missing) for unresolved definitions or
(asset error) for unavailable artwork or child dependencies. A real Null catalog
entry remains an available placeholder rather than a missing definition, but is
still prohibited from clipboard transport.

In the editor, the entire Null foreground, including its border, hatch and text, uses the
semantic error color even when selected. Preserve its background/transparent
regions and ordinary colors on neighboring compound children. Older embedded
Null graphics that marked only text receive the same treatment. This does not
make errored assets valid clipboard sources: Copy/Cut and Shift duplication are
blocked as described in EDIT-01. The built-in NorthArrow is an annotation with an
internal definition, not a missing catalog entry.
Export omits Null artwork and editor-warning objects rather than painting their
error colors into the output; see EXPORT-04 in INTERACTIONS.md.

Session restoration shows one application-modal, locatable asset report if problems
remain. Applying a project does not also create a transient clipboard warning;
project opening uses its recovery report. Preview and export remain quiet.

Optimized PNG uses `type: "PNG_OPTIMIZED"` in the in-memory export history
snapshot; it shares PNG controls and rendering but uses a separate encoding step.
Switching to SVG and undoing restores that selector. The project and session
persist the selection as `settings.exportSettings.fileType`, with values `PNG`,
`SVG`, `PNG_OPTIMIZED`, `PDF_RASTER` or `PDF_VECTOR`. PDF values require Print;
omitted `scaleMode` is normalized to Print for PDF, while explicit non-Print PDF
settings are rejected. Both PDFs write one multipage document. Raster uses PNG
page rendering and selected PPI, while vector uses SVG page rendering and
outlined text. PDF assembly belongs to the export worker, so preview render
arguments still use `png`/`svg`. Omission defaults to PNG. Output destinations remain
separate `exportFolder`/`exportFileName` values. The CLI's explicit file-type
argument takes precedence over the saved UI selection.

`settings.exportSettings.scaleBar` is an optional object with `enabled` (boolean,
default false), `position` (`Bottom left`, `Bottom right`, `Top left`, `Top right`;
default `Bottom left`), `divisionMode` (`Progressive`, `Equal`, `Subdivided`;
default `Subdivided`), and `style` (`Alternating`, `Checker`, `Stepped`; default
`Stepped`). Earlier `style` values `Progressive`, `Equal divisions` and
`Subdivided end` migrate to the corresponding `divisionMode` and retain the
`Alternating` appearance; an explicit
`divisionMode` takes precedence. Legacy `widthMM` (5–100), `widthPixels` (10–1000) and
`divisions` (integer 1–10) are validated on load, then discarded. They no longer
control rendering or appear in the UI. The bar chooses a clean distance in
five-based steps near 100 mm at the 300-PPI baseline (about 1181 export pixels)
in every mode, then derives its calibrated width from
the export scale. In Progressive, the three interior marks use clean 1/2/5 decimal distances
below the total, with proportional spacing and four segments. For example,
a 10 m bar uses 0, 1, 2, 5, 10 m. Equal chooses a clean major increment
that divides the total exactly, aiming for five equal sections. Subdivided
adds clean smaller divisions inside the first major section. The same 10 m bar
reads 0, 2, 4, 6, 8, 10 m or 0, 1, 2, 4, 6, 8, 10 m respectively; neither
dropdown changes the total distance or calibrated width. Alternating draws one
filled row; Checker adds an inverse second row of the same height; Stepped draws
a continuous open path down, across and up at alternating marks, with no fill.
Labels use the display units, choosing clean
feet/inch totals for imperial projects and inch increments for short imperial bars.
Each label has its own tightly padded, opaque canvas-color backing; the gaps and
surrounding area stay transparent. Filled segments and strokes are opaque, and labels use a 1.4 mm
font size at that baseline in every mode. Digital uses the same baseline
decoration sizing as Title Block; physical exports scale with output PPI.
Labels always use D-DIN Condensed, like title-block fields. Narrow pages select a shorter clean total
when needed to fit the drawing area.
The zero mark automatically aligns horizontally inward to a major export
gridline where it fits with the labels and ruler inset. The vertical inset
remains fixed. This uses the export
scale, project grid origin and page-specific drawing bounds, without adding
another saved setting or depending on viewport zoom or raster PPI.
The bar is an export decoration, absent
from scene-only caches and the Build canvas. Print repeats it per selected page.
Its section expansion state uses `ui.exportSections["Scale Bar"]`.

`settings.exportSettings.titleBlock` is an optional object. `enabled` defaults
false; `position` is `Right` (default) or `Bottom`. `logoMode` is `None`,
`Planner` (default) or `Custom`; legacy `logoEnabled` is still accepted. Custom
`logo` is base64 image data and `logoName` retains its source filename. Text
fields are `projectName`, `drawingTitle` (displayed as Sheet title), `address`,
`date`, `preparedBy`, `comments` (displayed as Notes), `sheetNumber` (displayed as Sheet prefix) and `revision`. Text values are
limited to 10,000 characters; encoded logo data to 8,000,000 characters.
The GUI defaults project name to the current project stem or `New Project`,
sheet title to `Ground Floor Plan` and sheet prefix to `A-1`. The `sheetNumber`
value stores the literal prefix; the rendered SHEET NUMBER appends an automatic
sequence, starting at `01`. Print pages run left to right, top to bottom within
the complete selected pages. The sequence is `01`–`99`, then `101`–`199`, then
`201` onwards, skipping each `00` ending. Digital/Architectural output uses `01`.
The one-based render argument `sheetIndex` selects a page's sequence without
changing the saved prefix. Explicit empty prefixes produce just the sequence.
Other explicit empty text is preserved. Scale is derived from export settings rather than a saved
text field. A blank date uses today; the picker and Today reset write the date.
The title block is absent from editor/scene-only artwork, appended after the
border in free-crop modes, and repeated inside each Print page. Its section
expansion state uses `ui.exportSections["Title Block"]`.
Print derives its uniform block scale from the shorter paper edge, independent
of orientation and PPI. Side width interpolates 40 mm at 210 mm (A4) to 50 mm
at 297 mm (A3), then to 60 mm at 841 mm (A0), clamped to 40–60 mm. Bottom
height uses the same relative growth from its existing 20.48 mm A4 height.
This is derived layout, not another saved preference; Digital/Architectural
retain their existing physical title-block dimensions.

Print mode uses `settings.exportSettings.scaleMode: "Print"` and is
the GUI's initial choice for a fresh export setup. Saved explicit modes are
restored; older nonempty overrides without a mode retain Digital semantics.
Architectural and Print retain independent `architecturalScale` (default 100)
and `dpi` (default 300) values. The active values remain in those top-level
export keys. Optional `modeScales` parks inactive physical modes' values as
`{"Architectural": {"architecturalScale": 50, "dpi": 300}}`, keyed only by
`Architectural` or `Print`; entries accept those two validated settings only.
Switching restores scale/PPI before restoring and constraining the destination
crop. New physical modes use defaults; old shared values belong to their saved
physical mode. A legacy Digital setup can seed the first physical mode from its
previous scale/PPI. Inactive scale records never enter the resolved render view.
`pageSize` currently
accepts `A0` through `A4`, `ARCH A` through `ARCH E`, `Letter`, `Legal` and
`Tabloid`, defaulting to `A4`;
`pageOrientation` accepts `Landscape` (default) or `Portrait`.
The active mode's crop remains in `bounds: [x, y, width, height]` in world
millimetres. Optional `cropRegions` parks the inactive modes' crops, keyed by
`Digital`, `Architectural` or `Print`, with the same four-number shape and
positive width/height. Switching modes archives the departing crop and removes
the restored mode's entry from this map. Unused Digital/Architectural modes start
with automatic scene bounds. When Print has neither `bounds` nor `pageOrigin`,
the GUI initializes both to select one complete sheet centred on the automatic
model bounds, using the selected paper, orientation and scale. An explicit crop
or page offset, including `[0, 0]`, prevents this initialization. Existing projects
without the map retain `bounds` for their saved mode.
Both active and inactive crops participate in export undo/redo and
project/session persistence. Inactive crops do not enter the resolved render view.
Architectural and Print geometry and pixel-based style values use a fixed 300 PPI design space.
`dpi` controls raster output density and metadata; it does not change page offsets,
drawing coverage, grid spacing, text size or physical stroke widths. SVG retains
the same geometry and physical page dimensions across PPI changes.
In Architectural mode, changing `architecturalScale` scales the crop dimensions
by the scale ratio around its centre and compensates the preview camera, keeping
the export footprint and printed dimensions fixed. Crop and scale share an undo
entry; undo/redo also applies the matching camera adjustment.
`pageOrigin` is a two-number world-millimetre offset, default `[0, 0]`, independent
of `gridOrigin`. `bounds` is the page-selection crop in the complete-paper preview,
not a single page's drawing bounds. Only fully enclosed paper cells are selected.
`pageOverlap` is a pair of signed world-millimetre lengths, default `[0, 0]`,
displayed in project units. Source-page strides are the available drawing width
and height minus these values. Positive values duplicate a strip between pages;
negative values leave a source-coverage gap. Paper dimensions and paper-cell
strides remain fixed, so sheets, borders and crop never bunch up or resize.
`pageOverlapOffset` stores the source offset in world millimetres, default `[0, 0]`.
An overlap edit adjusts this offset by the overlap delta times the crop-centre
page index, preserving the drawing at that anchor. Later crop movement only
changes selection; it does not move the already positioned drawing. These source
offsets are saved and restored with overlap in the same Export undo entry.
Overlap is independent of raster PPI and
is not rescaled when the architectural scale changes. Positive values must stay
below the available drawing extent; UI limits follow paper, scale and decorations.
Overlap controls are disabled when at most one complete page is selected;
their saved values are preserved and become editable again with multiple pages.
Interactive crop edges retain at least one fully enclosed paper cell; changing
paper size or orientation preserves the selected rows and columns. Paper and
architectural-scale edits resize the crop around the complete selected pages'
centre, discard partial margins, and update `pageOrigin` to retain cell indices.
Architectural-scale edits also adjust the preview camera to keep the selected
paper footprint fixed on screen. The setting, crop and origin change together
in Export undo/redo.
Border/title-block space is deducted before tiling source drawing areas. Page
indices map paper cells to drawing tiles with the selected overlap or gap,
retaining continuous source coverage at zero overlap while every preview/output
page includes its own decorations.
Files are ordered left to right then top to bottom; sheet-number text is unchanged.
Print fields participate in project/session serialization and Export undo/redo.


Application startup, project loading and session recovery activate Build.
Save and Save As preserve the current tab, including Export, and commit pending
export-field text without replacing the editor camera/settings or stopping the
preview worker. Cancellation and save failure also preserve the current tab.
Legacy session `ui.tab` values remain accepted for compatibility but are not
restored. Saved export options remain available when Export is opened explicitly.

Session UI selections use persistent object IDs with an optional handle index:
`null` for the whole object, 0/1 for endpoints, 2 for AngleGuide middle, and 3 for
MeasurementGuide/BoundaryLine/DashedLine/SolidLine/AngleGuide label indices. The
validator retains legacy boundary-style label indices; normal canvas clicks on
their selected-only dimension labels select the body instead.
Validate the handle against decoded scene
objects before applying recovery. A wall cannot acquire an index-2 middle point
or index-3 label merely because another class supports them. Unknown object IDs
are skipped as in earlier sessions. These are session UI fields, separate from
`middle` and `textOffset` in ordinary scene records. See the recovery coverage in
[VERIFICATION.md](VERIFICATION.md).

Session `ui.expanded` also stores the World tree's Objects and Annotations heading
expansion. Missing entries default to expanded. Their aggregate checkbox states
are derived from descendant category flags. These parents are
not new keys in `settings.visibility` or export visibility overrides; existing
project category flags and their schema remain unchanged.

## FILE-06: current scene problem inspection

Edit > Check for Problems or Alt + P opens one modeless inspection window. The
window and menu entry use report.svg, and the menu displays Alt + P. Reopening it
refreshes and raises the existing window. Opening the tool exits Export and
Reference Image editing and cancels active canvas gestures. It does not reload
or repair the project implicitly, mark it recovered, change object selection,
or replay notices about repairs already completed during loading.

Check missing furnishing definitions and graphics, including nested compound
children, through the same asset resolver used by recovery and properties.
Associate faulty children with their scene owner. Built-in North markers and
intentional Null placeholders are not missing definitions. Check geometry with
the recovery validator and current placement/collision rules, including problems
previously acknowledged through recovery's Highlight choice. Include existing
contained-wall and coincident-object warnings across architectural objects and
furnishings, including stairs, counters and elevators. Inspect hidden objects
as well.

Separate Problems and Potential issues into tabs with category groups, clickable
per-object entries and counts on each tab. Preserve each tab's selection and
expanded categories during refreshes and retain the active tab. Actions and
details always follow the active tab. Clicking an entry selects/reveals and frames its targets with
the same surrounding context as recovery navigation. Keep the window open and
refresh after scene changes, undo/redo and settings changes. Recheck rescans on
demand. Do not confuse presentation highlights with selection: all affected
objects receive error-colored outlines while potential issues use warning-colored
outlines while the tool is open, including hidden
targets. These overlays are absent from project data, caches and exports, and
are removed when the window closes.

Auto-Repair is available for a single issue with a recovery repair proposal or
a potential-issue correction. Describe
the proposed field changes before the action, recompute against the live scene
when clicked, and record the repair as one ordinary undoable edit. Do not invent
replacement definitions for missing assets. Delete uses normal deletion and
removes wall attachments with their parent, but does not expand into unrelated
group members. Stale entries must never delete a newer canvas selection. Closing
or rechecking the window changes no geometry. See `check_scene_problems.py`,
`check_geometry_recovery.py`, `check_recovery_locate.py` and `check_header_menus.py`.

Coincident-object Auto-Repair removes extra copies and keeps one existing copy,
using the same duplicate grouping as editor warnings and export filtering.
Preserve unique wall attachments when removing duplicate parents. Deletion and
repair remain undoable. Selectable openings from 1 mm through 10 mm long are
Potential issues with no automatic size repair, not fatal geometry errors.
See `check_problem_duplicate_repair.py` and `check_architectural_duplicates.py`.

Potential checks currently inspect regular wall endpoints, including hidden walls.
Report near-axis walls and joins within 0.5 degrees of a right angle, excluding
exact angles and endpoint corrections at or below 0.01 mm. Report endpoints up
to 5 mm apart that are not already connected within 0.01 mm, excluding endpoints
of the same wall. Report endpoints within 5 mm of a grid intersection, additionally
limited to 5% of the checked minor grid spacing. Use the grid's world origin and
project units. Capture the visible grid spacing when the checker opens or Recheck
runs, and keep it stable across navigation zoom changes. Unit/grid-origin changes
refresh that context. Do not treat intentionally diagonal or substantially off-grid
geometry as an error.

Axis repairs retain one endpoint and align the other, preferring a free endpoint
over a larger junction. Right-angle repairs retain the shared junction and a
reference wall and project the other wall's far endpoint onto its perpendicular.
Gap repairs join at an existing endpoint, preferring to move the smaller junction.
Grid repairs move to the nearest intersection. All co-located endpoints move
together, independent of connected-movement toggles. Explain the target coordinates
and affected junction in the detail text. Navigation frames all participating walls;
Delete still targets the listed primary wall rather than silently deleting every
reference wall involved in the check.

Potential repairs use the normal opening-fitting rules on changed parents, preserve
openings on unchanged parents, and compare the resulting hard validation problems
against the previous scene. Block repairs on already-invalid affected walls or their
attachments. If fitting fails or a new hard problem appears, restore all changed
endpoints and openings, record no history edit, and explain the refusal in the panel.
Successful repairs create one ordinary undo step. Recompute stale proposals before
applying them. See `check_potential_issues.py`.

Only the Potential issues tab offers Ignore and Restore ignored. Ignore suppresses
the selected suggestion or category's current instances, never confirmed problems
or an entire rule globally. Recompute before ignoring so stale rows cannot dismiss
changed geometry. Restore ignored clears all dismissals in this plan. Both actions
change project settings, mark the project dirty and refresh warning highlights
without moving geometry or adding a scene-history edit.

Store dismissals in the optional `settings.ignoredPotentialIssues` list as unique
64-character lowercase SHA-256 fingerprints, bounded to 100,000 entries. Older
projects default to an empty list. Reject malformed records during strict decoding
and reset them through ordinary settings recovery. Fingerprints include issue kind,
persistent participating object IDs, their geometry and proposed endpoint targets;
do not include runtime object IDs from pairwise issue codes. Normalize numeric
representations so integer widths and decoded float widths produce the same key.
An unchanged suggestion stays ignored after recheck, close/reopen and session
restoration. Changing participating geometry or the proposed target makes it a new
suggestion; undoing back to the ignored geometry respects the earlier dismissal.
New/other projects load their own dismissals, and Close Project clears them.
See `check_ignored_potential_issues.py`.
