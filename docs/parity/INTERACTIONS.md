# Layout and interaction contracts

## LAYOUT-01: window and sidebar

The desktop constructor initially requests 1440 x 900. This is a fallback normal
window size and the reference capture size, **not a minimum supported resolution
or a fixed layout requirement**. Without restored session/startup state, the
entry point shows the window maximized. Session recovery restores saved window
geometry/state. Projects and startup templates retain panel layout but do not
restore window placement, monitor, outer size or maximized state.
The current constructor does not calculate its fallback size
from the available desktop work area.

A future framework must size the outer surface to its available work area or
browser viewport, not reproduce 1440 x 900 as a required window. A screen-relative,
work-area-clamped fallback would be preferable for the desktop's normal window;
that is a proposed sizing improvement, not existing behavior. Include 1280 x 720
and 1920 x 1080 viewport scenarios plus fractional display scaling in acceptance
review; those sizes alone do not certify current minimum-size support. Browser
chrome, OS taskbars and display scaling reduce the usable logical area below
the monitor's physical resolution. Sidebar scrolling, wrapping and pinned actions
still have to work in that smaller area.

Outer margins are 12. The canvas and right sidebar
are separated by a draggable horizontal splitter. Sidebar minimum width is 200;
actual content minimums can require more. Preserve readable minimum widget
sizes: a deliberately narrow sidebar may overflow horizontally. Users can use
horizontal scrolling or reset the divider width; clipping to the currently
visible viewport alone is not a layout failure if content remains scrollable. Header sits above sidebar content,
with 6 px button spacing. Below it, a 40 px toolbar strip sits left of the tab
panel, separated by 10 px. The sidebar's major vertical spacing is 10.
The initial sidebar width is 460 logical pixels. Double-clicking its resize
handle restores that width within the available space.

Build, Furnish and World sit above Object Properties in an independently
resizable vertical splitter. Handle width is 8; initial proportions are 600:300.
Tabs have minimum height 100. Properties heading margins are 13 left/right;
content margins 13 left, 8 top, 14 right/bottom. Its content scrolls vertically,
without a horizontal scrollbar. Collapse remembers the previous height;
restoring uses it, or one third of available space. Dragging the divider within
24 px of the heading-only height collapses; dragging beyond restores.
Double-clicking the properties divider expands the panel and restores the
600:300 split between the tabs and properties.

Export hides Object Properties and shows a 48 px Export action fixed below the
scrolling options. Returning restores the previous properties split. The action
must remain reachable when options overflow. Fullscreen hides the sidebar and
restores its splitter sizes when exited.

The Wall Tool's shape/divider/preset/material composition and Settings
measurement split rows are specified in [LAYOUTS.md](LAYOUTS.md).

Build uses shared Wall Tool and Objects headings, wrapping icon palettes and
material swatches. Furnish has search and category palettes. Palette captions
and dimension readouts anchor immediately below their icon, rather than being
vertically centered in the tallest item of a row. Wrap rows as width changes;
do not clip their text. Search matches names, keywords and supported dimension
queries; `*` matches all. A definition can appear in multiple categories.
Text relevance puts whole-word name matches first, whole-word keyword/category
matches second, and substring matches last. For multiple text terms, the weakest
match tier sorts first, then the total rank; names and keys break ties.
Dimension matching retains its unit-preference ranking.
Partial matching also recognizes alternate spellings from normalization aliases,
so `dinn` and `dinne` find the dining furnishings matched by `dinner`. These
remain partial matches below whole-word names and keywords. Alias expansion
does not expand the fuzzy-search vocabulary or relax dimension constraints.

Furnish search stays pinned above the scrolling catalog, with Sort and then
the view toggle to the right of its search field.
The view toggle defaults to the tiled grid (`grid_view`); list mode uses
`view_list` and the same icon/dimensions/name rows as canvas quick search.
Both layouts retain category headings in Category order and use the same search
results and drag-to-canvas payloads. Switching views retains the query; catalog
refreshes retain the selected layout. The layout is an application preference
restored on restart, independent of projects. Both the catalog view selector and
global/local transform selector retain active styling in either mode; their
icons identify the current mode. Category headings do not select or drag.

The pinned `sort` button opens Category, Alphabetical, Width, Length and Area choices.
Category is the default grouped order; the other choices show each furnishing
once without category headings. Width and Length sort the effective placement
dimensions for the selected units; Area sorts their
width × length product. Names and
definition keys break ties consistently.
Choosing a different sort starts ascending; choosing the active sort reverses it.
Category reversal reverses category order and the order within each category.
Search filters retain the chosen sort; Category searches retain relevance order
(reversed when descending). The active menu choice is checked and shows its
direction. Sort choice and direction persist as application preferences across
view changes, catalog refreshes and restarts.

Furnishing ordering actions use `flip_to_front` and `flip_to_back`. Door/window
direction actions use `flip_h` for changes along the supporting wall (hinge,
slide or pocket side) and `flip_v` for facing/panel-side changes across it.
Properties buttons and context menu actions use the same mapping.

Factory wall presets are 10/15/20/30 cm (100/150/200/300 mm), with the third
selected initially. The bundled startup plan uses these same values. Reset controls
use these defaults. Stored project/session
presets and exact active wall widths, including non-preset values, remain intact;
custom saved startup templates retain their authored values. Changing factory defaults
does not resize existing walls or rewrite saved plans.

The World tab uses an expanded visibility checkbox tree without selected-row selection.
World has three branches: Walls, Objects and Annotations. Walls contains
Doors/Windows/Fireplaces. Objects groups Elevators, Stairs, Counters, Railings
and Furnishings. Annotations groups Labels, Arrows, Dimension guides, Boundary
lines, Dashed lines, Solid lines and North markers. Objects and Annotations are
collapsible checkbox parents that toggle all categories in their group and show
partial states when only some children are enabled. Their states are derived from
the category flags, with summed child object counts and no separate saved visibility flags. World
cascades through them and aggregates the real categories' states.
The export visibility tree uses the same hierarchy and fits its height to the
currently expanded rows. World-tab heading expansion persists in session UI
state, separately from project visibility. The dimension guide wire key remains
`Measurement guides`. Parent counts/check states reflect children. A partially
checked parent toggles to unchecked, including via keyboard Space. Only the
enabled checkbox hit area gets a hand cursor; ordinary row text retains arrow.
Coverage: `check_visibility.py`, `check_visibility_grouping.py`.

Reference Image is the first top-level branch, above and independent of World, off until
an image is chosen. Checking it initially opens the image file picker; cancel or
failure leaves it unchecked. Successfully loading an image switches to World and
opens its reference controls, just like Alt+B. Subsequent toggles reuse the embedded image. While
enabled, clicking its row text in World opens reference controls
in the properties area, expanding that area if collapsed. Returning to Visibility
alone does not reopen them. Leaving that tab, disabling the image, pressing Esc
outside a gesture or clicking canvas void closes the controls. Restore the
previous selection, splitter sizes, expanded/collapsed state and scroll position.
`B`, View and the tree checkbox only toggle reference visibility. Enabling does
not change the active tab or open reference controls when an image is already
loaded. `Alt+B` opens those controls only if the image is
already visible. While active,
the image is the sole transform target; scene picking, hover handles, selection
and building shortcuts are blocked. A click over a scene object within the image
acts on the image; a click outside the image cancels without selecting through it.

Reference controls contain the export-style path field/folder button, an amount
opacity slider (0–100%, initially 50%), draggable X/Y and local Width/Length
editors in current units, an Angle editor in degrees, and a Calibrate
Scale text button. X/Y describe the image center in resize mode and the rotation
pivot in rotation mode (center unless a custom pivot is set). Moving the pivot
updates X/Y without moving the image; editing X/Y translates the image and pivot
together. Angle edits rotate about that pivot in rotation mode and about the
image center in resize mode. Width and Length start linked for proportional
property edits and can be unlinked. Canvas handles retain their own proportional
and single-axis behavior. There is no lock control: opening the panel selects
the image automatically. Replacement images preserve position, rotation and
width, adapting height to their aspect ratio. The image shares furnishing handle
geometry, rendering and transform calculations: edge resize arrows, proportional
corner resize arrows, click-to-toggle rotation handles/pivot, Shift resize from
center, snapping and local/global angle origins. Esc/right-click cancels a gesture.
Other objects remain visible at about half their normal contrast, while the
reference image and its handles stay undimmed. Hide idle canvas hints in this
mode, retaining active transform hints. Camera panning remains available; arrow
keys nudge the image by a visible grid
unit. Reference data is project settings, outside scene objects, groups,
collision and measurements. Ctrl+Z/Ctrl+Shift+Z and the Edit menu use the normal
shared undo history, even after reference controls close. Reference edits and
scene edits undo and redo in chronological order. Moves, resizes, rotations,
pivot edits, property fields, opacity, image replacement and calibration can be
undone. Each canvas/property/opacity drag is one edit; cancellation adds none.
New edits clear redo. Visibility and entering/leaving editing are not edits.
Reference edits use the same history count and payload limits as scene edits.
Changed properties are stored as deltas, so transforms do not repeat embedded
image data. The mixed journal is saved in project/session files and validated
on load. Restoring image edits does not enter image editing or alter visibility.
Coverage: `check_reference_history.py`.
Painting places the image above the
canvas background and below grid/geometry, including cached pan strips; editor
handles are painted separately. The current export visibility tree and exported
artwork remain scene-only; no reference-image export option is implemented.

Calibrate Scale enters an exclusive two-point canvas mode. Separate clicks place
the endpoints; the second endpoint follows the pointer as a preview after the
first click. Alternatively, press to place the first point and drag past the
platform drag-distance threshold to place the second point on release. Small
pointer movement keeps the separate-click workflow. This drag uses the normal
point constraints and cancellation; cancelling leaves the first point placed.
A measurement line and normal control-point circles are drawn,
independent of scene measurement visibility. Once placed, either point can be
dragged to adjust it. The image itself cannot transform during calibration;
point hover/drag uses the normal move cursor. Point dragging reuses annotation
snapping (including Ctrl 15-degree constraints, local/global origins, enabled
target types, grid snapping and Alt inversion). Right-click/Esc during a point
drag restores that drag's starting points and retains calibration mode. The
standard two-column canvas hints show Left Mouse / Place point and Escape /
Cancel while placing, Enter / Confirm and Escape / Cancel after placement, and
Ctrl / Snap to 15° increments and Right mouse / Cancel during a point drag.
Camera pan and zoom remain available. Enter after two distinct points opens a
window-modal distance editor, with a unit dropdown initialized from project
units. The dropdown is local to this action, supports mixed feet/inches input,
and converts the current value when changed. Adaptive Metric is not an input
option here; adaptive projects initialize this one-use selector to Meters. Zero/nonfinite distances and scales
outside reference-record bounds are rejected without changing the image.

Confirmation scales width, height, center and a custom image pivot uniformly
about the first picked point; the corresponding image feature stays fixed.
Image angle, aspect ratio and opacity are preserved. Cancelling the distance
dialog returns to the picked points. Esc/right-click outside a point drag, leaving
reference mode, replacing the image or loading a project cancels the temporary
calibration. Only the resulting image dimensions/position are saved; picked
points and the one-use units are not persisted.

## HOVER-01: picking, handles and cursors

Hover does not change selection or create an undo edit. Selection and overlap
priority matter: an already selected object wins overlapping body hits; exposed parts
of other objects remain selectable, and hidden objects are not pick targets.
Do not let a nearby unselected furnishing handle steal a hit on a selected object.
Eligible control points are tested before boundary, dashed and solid line bodies,
so a line crossing a visible vertex cannot intercept its click or drag. Away from
control points, these lines remain selectable inside walls, even selected walls.
Hidden objects and wall endpoints concealed beneath an unselected pillar retain
their existing picking exclusions. Coverage: `check_line_vertex_priority.py`.

Hover highlighting, cursor selection, left presses, double-click actions and
context menus share the resolved interaction target. Furnishing resize/rotation/
pivot handles take precedence over underlying control points and label bodies;
those underlying objects must not acquire the active hover highlight. Selected
handles paint after unselected handles, matching their hit order. Unselected
handles blocked by a selected body stay hidden. Whole-object multi-selections
resolve endpoint hits to the group move, while explicitly selected vertices keep
their vertex drag. Reference editing and calibration remain exclusive modes,
using their own shared hover/click handle tests.
Coverage: `check_hover_click_targets.py`, `check_selected_hit_priority.py`,
`check_canvas_cursors.py`, `check_reference_image.py`, `check_reference_calibration.py`.

Furnishing-style handles appear for selected or hovered objects and when the
pointer approaches their handles. The current visibility broad phase uses
56 screen px and handle hits use a 9 screen px radius; these distances do not
grow/shrink with world zoom. Handle positions follow rotation and geometry.
Resize artwork uses `handle_up.svg` and `handle_up_right.svg`, rotation uses
`refresh.svg`, and the pivot uses `pivot.svg`. Each is drawn in a centered
20 × 20 logical-pixel box with the appropriate selection or invalid-state tint.
Fireplaces have resize handles but no independent rotation mode.

Canvas cursor priority, highest first:

| Condition | Cursor |
| --- | --- |
| Export active | Export's crop/ruler/pan rules |
| External palette drag active | Keep the drag system's preview/validity cursor |
| Panning | Closed hand |
| Opening placement | Hidden cursor, drawn placement graphic |
| Wall drawing mode/gesture | Crosshair |
| Active handle drag | The dragged handle's cursor |
| Active object/control point translation | Move/all-directions |
| Hover resize handle | Oriented horizontal, vertical or diagonal resize |
| Hover rotation handle | Bundled `assets/cursors/rotate.png`, hotspot (16,16) |
| Hover pivot | Move/all-directions |
| Hover object or control point | Move/all-directions |
| Empty canvas | Arrow |

Resize cursors quantize the handle's outward screen vector to the nearest
45 degrees. They must follow object rotation. Do not use pointing-hand cursors
for movable scene geometry. Enabled buttons/tabs use pointing hand, palette
drag sources open hand, sliders resize, color planes crosshair, and disabled
controls arrow. Reset cursor state on cancel, hide and teardown.

## EDIT-01: selection and gesture lifecycle

`G` toggles the grid regardless of selection. `Ctrl+G` groups the selection and
does nothing without a selection. `Alt+G` removes selected objects from groups.
`H` hides selected objects, `Ctrl+H` hides unselected objects, and `Alt+H`
restores individually hidden objects while retaining category visibility filters.
`U` has no binding. These scene commands do not intercept text-field editing.
Export and reference-image editing block scene grouping and hiding commands.

Left-click selects objects or control points; empty left-drag draws a selection box.
Shift-click adds selection members; Ctrl-click removes them. Ctrl-drag retains its transform snapping behavior. Group Mode expands selection to members.
On empty canvas, Shift-box selection adds fully enclosed objects and Ctrl-box selection removes them, expanding groups in Group Mode. Modifiers are captured on press; an empty click preserves the selection.
Clicking a resize handle while Shift is already held must begin centered resize,
not box selection. Handles have priority over the modifier's empty-canvas action.
Whole selected groups show one combined selection-dimension box, not per-member
overlays. Ambient member dimensions remain unchanged.

Object drag translates the selection; Shift-drag duplicates it. Wall copies
include their openings. Connected Objects recursively carries physical connected
objects, including colliding furnishings; Connected Points follows eligible
endpoints. These are separate options. Duplicating does not pull connected
unselected neighbors. Whole-object moves offer control points as snap anchors.

Shift-dragging an arrow or stair endpoint extrudes a new segment with the same
endpoint orientation as its source. Extending endpoint 0 drags the new endpoint
0, leaving endpoint 1 at the junction; extending endpoint 1 does the reverse.
Arrow tips continue along the directed chain. Stairs retain directionReversed,
including when extending the back of a reversed flight. Appearance and sizing
settings are copied. Releasing Shift or cancelling restores the normal captured
gesture state; committing extrusion is one undoable edit.

Arrow Properties and its context menu offer Flip Direction. This exchanges the
two endpoints and their chamfers without changing shape or style. Selected
endpoint indices follow their physical point. Multiple selected arrows reverse
together in one edit, and save/load, duplication and exports retain the direction
through the existing endpoint geometry. Measurement and boundary line tools do
not show this arrow-only control. Coverage: `check_arrow_direction.py`.

Flip Horizontal and Flip Vertical are generic context actions for single or mixed
selections, except an individually selected wall attachment. Individual doors,
windows and fireplaces expose their specific hinge/facing actions instead.
In Global mode generic flips reflect X or Y respectively around the combined
axis-aligned footprint's center. Every selected control point uses that same
reflection, preserving junctions within the selection. Groups and hidden state
are retained; connections outside the selection are not expanded implicitly.

Local mode uses each object's own center and axes. Furnishing artwork flips
around its own local axis without moving its center or changing its angle.
Global furnishing flips also reflect the center and orientation; existing
artwork flags encode the mirror with positive width and length. Both property
buttons and context actions use the complete selection. Labels follow the
reflection while keeping their glyphs readable. Guide label offsets reflect as
vectors, and all three angle-guide points reflect together.

Wall children follow a reflected parent exactly once even when both are
selected. Hinge, facing/panel side and fireplace offset are rebased to preserve
the mirrored symbol. An independently selected attachment must still fit its
parent wall. Invalid placement rolls the whole action back and creates no undo
entry. A successful reflection is one undoable edit and survives save/reopen.
Coverage: `check_selection_flips.py`, `check_furnishing_flips.py`.

Whole doors/windows selected on one stationary wall can transfer together to
another wall during a body drag. Use the grabbed opening as the placement anchor,
including after Shift creates copies. Preserve each opening's length, properties
and center spacing along the destination wall; reverse the offsets when its axis
is reversed. Clamp the group as a whole at wall ends and validate all members
against the final scene. A short or blocked destination must not produce a
partial transfer or shrink individual openings. Other openings can remain in the
gaps between selected members. Between valid placements, hide all moving members
on their captured parent and draw each as a pointer-following ghost, using the
same invalid outline color and artwork as a single detached opening. Preserve
their spacing and orientation. Releasing an invalid ghost cancels the gesture
without an undo entry or leftover copies. Shift transfers copies and retains the originals;
returning to the source wall, changing Shift state and cancellation restore the
captured state without accumulating drift or copies. Mixed wall/object selections,
endpoint edits and selections spanning multiple parents retain their existing
group constraints. Coverage: `checks/check_group_opening_transfer.py`.

Corner resize preserves proportions; side resize changes one dimension. Shift
resizes from center and **does not duplicate during resize**. Clicking a selected
furnishing toggles handle mode. Rotation uses the chosen pivot, which can be
dragged or double-clicked to center. A multi-selection's pivot stays fixed during
rotation and subsequent rotation gestures, even when its axis-aligned bounding
box changes center. Deselection clears it; cancelling restores the previous pivot.
Shift-rotation duplicates; the new selection
retains its pivot until deselected. Transform dialog shared rotation uses that
pivot; local origins rotates each object about its own center.

Multi-selections containing walls expose rotation and pivot handles directly,
without resize handles. Whole-object entries can mix walls, furnishings and
openings; endpoint selections do not expose these handles. Rotation captures
connected endpoints according to Connected Points/Objects, using the same
attachment discovery as movement. Unselected attached openings follow their
parent; explicitly selecting a child as well must not transform it twice.
Shift copies selected objects and all openings on copied walls, retaining
opening types/settings and remapping their parents. Unselected connected
neighbors stay original when duplicating. Modifier toggles restore captured
geometry before switching copies. Validate and commit one edit on release;
invalid openings/collisions and cancellation restore everything. Coverage:
`checks/check_wall_selection_rotation.py`.

Selected counters use `selectionFill` and `selectionOutline`; grouped counters
use their group equivalents. Clip each highlight to its owned portion of the
joined counter geometry, so adjacent unselected counters keep their normal fill.

Handle rotation snaps at 15-degree intervals when snapping is active, retaining
the existing Snap toggle and temporary Alt inversion. Global transforms use
absolute angles; local transforms use the handle's captured drag-start angle as
the snap origin. Never rebase to the previous preview frame's angle. Preserve
this origin with a custom pivot and when Shift transfers rotation to a copy.

Capture the gesture's starting state once. Preview live; commit one edit on
release. Right-click during a move or Escape cancels and restores the start.
Rejected placements must not leave partial copies, geometry or attachment
changes. Previewing a fireplace on a thicker wall can temporarily enlarge it;
moving back before release restores the original requested size. Confirming
placement makes the final valid dimensions permanent.

Arrow keys nudge one currently visible minor grid interval. Shift+Arrow creates
copies and nudges them. Ctrl+Shift+V pastes at original coordinates without grid
snapping, subject to normal placement validation. Text-editor arrow/clipboard
operations must not leak into canvas commands.

Missing or errored furnishing assets, including unresolved compound children,
block Copy/Cut and clipboard paste. A mixed selection is blocked as a whole.
Shift movement, rotation and arrow nudging do not create duplicates when the
source selection contains such an asset; ordinary movement/rotation remains
available for locating and removing the affected objects.

## SNAP-01: navigation and constraints

Middle-drag pans; wheel zooms about the pointer. Double-click empty drawing
canvas resets its camera; export uses its own reset described below. Opening
placement, polygon creation and constrained-control point gestures can consume the wheel
for their own adjustments. Preserve those exceptions from the shortcut guide.

The editor fills detected structural wall enclosures with the canvas theme's
required `roomFill` color. It is independent of `canvas`, with no generated fallback.
Room geometry and areas remain derived, with no saved region objects or geometry.
Door/window openings do not break enclosures. The visible wall boundary includes
walls, pillars, columns and current wall/polygon previews, matching exterior
measurements. Other object classes do not create enclosures. Open floor paths
remain undimmed. Regions use the wall renderer's actual
junctions, crossings, thicknesses and chamfers. Nested wall islands remain excluded.
The fill is below the reference image and grid. Grid opacity and rulers remain
unchanged, and room shading remains visible when the grid is hidden.
Export's Canvas section has a Floors checkbox immediately below Solid Objects.
It inherits the editor's floor shading on entry until an explicit export override
is made. The override persists per project/session and supports export undo/redo.
Floors controls only the room-fill paint, independently of object fill, grid,
borders, room detection, areas and labels. PNG, Optimized PNG, SVG, both preview
paths and the saved-settings CLI apply the same resolved choice. Leaving Export
restores the editor's floor state. Coverage: `check_export_floors.py`.

Room detection reads structural-geometry/topology/visibility revisions and wall
preview values before the canvas background is painted. Changes update the tint
in the same frame, including during drags and wall/polygon previews. It consumes
the viewport's canonical wall geometry and retains one boundary classification
for tint, room-label areas and exterior/stacked measurements. Furniture, opening
and annotation motion do not rebuild room geometry. Unrelated collection changes
may check the geometry key but skip classification when the walls match.
Stable paints and camera changes reuse the world-space
mask. A changed mask advances the background revision so scene, edit, reference
focus and pan caches cannot retain the previous room shading. Coverage:
`check_room_detection.py`, `check_live_room_tint.py` and the shared background/pan/cache checks.

Wall measurement mode defaults to Exterior stacked for new projects. Older
projects without a saved mode retain All. Exterior uses the same contour nesting
classification as room detection and measures only the unbounded outer faces of
visible wall geometry. Internal room faces and enclosed wall islands are omitted,
including the fallback dimensions for selected interior walls. Concave outlines
and separate buildings retain their actual boundaries. Opening splits remain in
effect on exterior spans, and other measurement categories are unchanged.
The mode is saved with the project/session and used by export previews, PNG/SVG
output and command-line export. Exterior stacked uses at most three rows:
opening spans nearest the wall, room divisions next, and overall length outermost.
Wall reference is a project/session setting shared by editor, previews and PNG/SVG
or command-line exports. Wall faces is the default, retaining exterior-face overall
spans and splitting room divisions at both partition faces, including a separate
wall-thickness span. Centerline references intersecting wall axes at chain endpoints
and uses one division at each partition axis. Opening widths remain the actual
opening widths in both modes. Face offsets account for partition angle.
Room divisions are introduced only where a partition separates two detected
rooms. Free wall stubs do not introduce room divisions.
Touching or overlapping parallel walls can form a single partition assembly.
Room probes must step beyond that assembly's complete cross-section. Wall faces
uses its exposed faces, while Centerline uses the midpoint of those faces; do
not introduce dimensions at the buried seams between its constituent walls.
The inner chain includes both room and opening breaks. Omit redundant rows, leaving one row for an
unbroken wall, two for room-only or opening-only chains, and three when both are
needed. Rows start 20 px from the boundary, with 30 px between active tiers.
Stair/counter split selectors do not cut stacked wall rows. Furnishings never
interrupt architectural measurements, including stairs and counters. Architectural
blockers still trim covered stair/counter spans.
Splitting preferences are retained and restored when leaving stacked mode. In
stacked mode, the split controls are hidden and disabled, replaced by the single
Wall reference dropdown, which is disabled while wall dimensions are off.
All active tiers share ambient visibility and normal dimension formatting.
Selection dimensions are a separate overlay and cannot alter tier construction.
Coverage: `check_exterior_measurements.py`, `check_stacked_measurements.py`,
`check_room_measurement_stacks.py`, `check_furnishing_measurement_blockers.py`.

Room Label is a draggable Annotations tool that can be placed anywhere on the
canvas. Its editable single-line name and calculated area are
centered on separate lines, with the area font at 55% of the name size. Default
name size is 32 points at the same fixed reference used by ordinary labels.
Position, proportional size, rotation/pivot and opacity reuse Label controls.
Moving the center into another room updates its area. Outside any enclosure the
area displays an em-dash placeholder, while preserving the name and transform.

Area is the enclosed polygon area inside wall faces, less contained wall islands.
Partitioned and nested rooms are separate lookup regions. Adaptive Metric and
Meters use m², Centimeters cm², Millimeters mm², Feet and Inches ft², and Inches
in². Meter/foot areas have two decimals, other modes display whole square units.
Room labels default to project units in the editor and the selected export units in
exports and export previews. A per-label Units override takes precedence in both.
Name and area text use the canvas objectOutline role.

The name, ordinary label transform, opacity and units override are serialized.
Changing the override is undoable. Derived area and inherited unit changes do not
resize the stored box, mark the project dirty or create undo steps.
Derived values refresh through room/label revision keys. Exports calculate
areas synchronously and use independent room-label clones, so export previews
cannot alter editor label state. Room labels use Labels visibility and normal
annotation history, session/project recovery, copy/paste and export paths.
Coverage: `check_room_labels.py`, the object matrix and render examples.

During editing-canvas panning, every delivered move updates the camera immediately.
Repaint requests share one precise, single-shot deadline based on the current
screen's reported refresh rate (60 Hz fallback for invalid reports). Late ticks
skip obsolete slots and draw the latest camera, without smoothing, animation or
replaying intermediate positions. Idle movement does not start a repeating render
timer. Release, cancellation, lost mouse capture and deactivation stop pending
pan ticks and schedule the final state immediately. Read the refresh rate again
for each new gesture, including after moving to another monitor. Export retains
its existing preview scheduling. `check_pan_frame_pacing.py` and
`check_pan_lifecycle.py` cover this contract. Paint cadence is not a guarantee of
native display presentation or input-to-photon latency.

Camera-only panning reuses prepared furnishing visibility/layers and world-space
artwork extents. Geometry, appearance, visibility and topology changes invalidate
that preparation. Whole-device-pixel movement can scroll retained pixels and
redraw exposed strips; fractional movement retains the accurate fresh-render
path. Partial wall-outline redraws retain complete intersecting contours so
joins, hatch-edge antialiasing and door re-entry match the direct renderer.
During whole-device-pixel pans, the desktop may retain Qt's complete vector
stroke at its initial device-pixel phase and translate that shape for large
contours whose bounds span the canvas. Smaller contours retain native culling.
Geometry, zoom, display scale and pen geometry changes invalidate it. Fractional phase
changes use native stroking. This is a single vector cache, with no extra retained
raster surface, camera quantization or alpha-compositing layer. Offscreen opening
cutouts are omitted only from pan viewport clips, while full opening geometry
remains available to stair occlusion and other consumers. Lumber clips are installed only
when a visible lumber cross-cut needs them during a pan. Stationary and export
rendering retain their original clipping operations. `check_pan_wall_outline.py`
compares angled negative-coordinate geometry with native rendering and tests invalidation.
For thin pan strips, wall strokes may be drawn on guarded temporary patches copied
from the current destination. Replay the original clip operations separately,
then replace destination pixels once. Do not combine clips through a path boolean
or introduce another source-over blend. Disjoint write regions avoid double ink.
The temporary surface must fit within the remaining aggregate raster budget.
Partial physical viewport-edge pixels and unsupported devices use the native
full-device path. Keep all visible railings in scene state, but omit their paint
and wall-mask construction when their complete symbol bounds, including stroke
padding, miss the dirty area. `check_pan_wall_patches.py` compares patch drawing
against the same native pan history, including five DPR values, clip masks,
post edges, offscreen railing state, partial viewport edges and low memory limits.
Do not quantize camera movement, weaken render comparisons or hide artwork to
meet a timing target. See `check_pan_preparation.py`, `check_pan_dpi.py`,
`check_pan_dirty_regions.py` and `check_door_pan_reentry.py`.

Alt temporarily inverts snapping. The toolbar reflects the effective state,
while project/session saves retain the base snap preference. Alt presses and
releases remain paired across Options and other Planner windows, including
reference tools that consume keyboard events. Ignore modifier auto-repeat.
Application deactivation clears the override; pointer modifiers reconcile a
release lost to a native dialog before processing a toolbar click. With no snap
target types enabled, the indicator remains off even while Alt is held.
Ctrl and Shift use the same cross-window tracking before any tool consumes a key.
Pointer events reconcile all three modifiers. Main-window deactivation or hiding,
application deactivation, lost canvas capture and missing held mouse buttons end
unfinished gestures. Canvas transforms and reference-image drags roll back;
box selection, wall drawing, pending context-clicks, D/S placement, panning and
edge-pan timers clear. Calibration cancels its active point drag but keeps already
placed points. Export crop/ruler drags retain their last value as an undoable
gesture and clear the held flags. Application deactivation clears cached modifiers.
Coverage: `check_snap_state.py`, `check_held_input.py`, `check_snap_options.py`,
`check_interactions.py`, `check_pan_lifecycle.py`.
Ctrl constrains translation to an axis.
Held object drags and box selection automatically pan near or beyond the visible canvas edges.
Use a 24-logical-pixel inner edge band with speed increasing toward the edge,
reaching 480 logical pixels per second at the edge. Beyond the edge, add 480
logical pixels per second for every 96 logical pixels of outward travel, capped
at 2400 logical pixels per second in total. Normalize the direction vector
so diagonal movement matches axial speed at the same edge penetration. Continue while the pointer is
stationary, and cap elapsed steps at 50 ms after stalls. Panning changes the
camera and replays the current drag through its existing snapping, constraints,
collision and transform rules. Carry screen-space drag anchors with the camera
while keeping captured world-space geometry fixed. Do not introduce extra undo
steps. Moves, control points, handles, wall drawing, reference images, calibration
point drags and catalogue placement share this navigation behavior. Box selection
starts panning after the normal drag threshold, keeps its origin on the original
world point and extends to the pointer as new areas become visible. Preserve
Shift-add and Ctrl-remove selection without creating geometry edits. Waiting for
a click and ordinary hover do not trigger it. Catalogue drags
must remain inside the native canvas drop target. Stop on release, cancellation,
return to the interior, lost buttons/capture, deactivation, hiding, export entry,
drop or native drag exit. Manual middle-button panning takes priority. Reference
image and calibration input filters must participate even when they consume the
mouse event before the viewport receives it. See `check_drag_edge_pan.py` and
`check_drag_edge_pan_reference.py`.

Control point constraints use 15-degree axes from the opposite endpoint;
global mode starts at global axes, local mode at the initial object direction.
Wheel switches the constraint origin between endpoints. Show the active guide.
Snapping priority and tie ordering are part of geometry behavior, not a framework
default. See the numeric core contracts and snapping regression checks.

Control Points and Corners independently enable direct snapping to control
endpoints and footprint/joined-boundary corners. Both default to enabled.
Disabling either target type also removes its X/Y alignment candidates.
Alignment only projects coordinates from enabled target types. Grid and
Midpoints retain their own switches.

The wall thickness selector defaults to its third preset, 200 mm (20 cm).
The bundled startup template uses that value; saved project and custom startup
template selections retain their stored widths.

## MEASURE-01: displayed dimensions

In the editor, M and the View menu's Toggle dimensions action toggle the
master visibility flag while preserving nonempty category choices. Hiding and showing a
walls-only configuration restores walls only. Category checkmarks retain the
remembered choices while the master is off; Settings dims their labels. The
editor master is independent of the number of enabled categories. Settings has a
collapsible Draw dimensions tree root with four category children. With
all categories off, the root checkbox is unchecked and read-only, with disabled
appearance while its children remain interactive; toggling dimensions
from View or M in that state restores walls only. Enabling a category shows measurements without clearing other
choices; disabling the last category also turns the master off. Save the master
and category choices separately. Export's Draw dimensions root remains a show/hide-all action,
which explicitly enables or disables all categories. The View menu contains only
Toggle dimensions (M), with a partial-state indicator in Export. Per-category
controls remain in Settings and Export. Elevators have no measurement category.
Coverage: `check_measurement_master_toggle.py`, `check_header_menus.py`.

Geometry remains millimeters. Display precision affects canvas dimensions/guides,
not stored coordinates or property values. Medium is default. Metric High/Medium/
Low round to 1/5/20 mm; imperial to 1/16, 1/4, 1 inch. Adaptive Metric follows
the visible major grid unit: mm, cm or m. Imperial canvas modes are feet/inches
and inches only, with fractional glyphs; ordinary editors use decimal readouts.

New-object sizes use a separate nominal placement rule in imperial modes:
`max(1, floor(metricMillimeters / 25 + 0.5))` inches, converted to model
millimeters with the exact 25.4 factor. Thus 900 mm becomes a real 36-inch
object (914.4 mm), and 2000 mm becomes 80 inches (2032 mm). Apply this to both
furnishing axes, Build size defaults and fixed architectural placement lengths.
Catalog dimension readouts, sorting and placement previews use these effective
sizes. Explicit metric dimension searches use authored metric dimensions even
while imperial display is active; imperial queries use nominal placement sizes. Metric catalog/default dimensions remain their source
values. Existing geometry, clones, pasted objects and source-object moves retain
their exact sizes; changing unit modes never resizes scene objects.

Explicit imperial Build defaults are stored separately as exact millimeter
overrides and are shared by both imperial modes. Do not nominalize an override
again. Metric edits or Reset clear that size's override. Switching back to metric
uses the metric defaults; switching to imperial restores its saved overrides.

Auto Tread Depth and Auto Railing Sizing use nominal whole-inch limits in
imperial modes too: 250/300 mm becomes 10/12 inches, and 900/1200/1500 mm becomes
36/48/60 inches. Their fields step by one inch. Typed fractional-inch limits
remain exact and are shared between imperial modes; metric source limits are
kept separately. The effective limits drive autosizing and its tooltips, including
export previews. Unit changes preserve object endpoints and width; automatic
tread/post counts follow the active limits, while manual counts stay unchanged.

Measurement context actions exist only for object types that actually draw
measurements under current global/category settings. They go at the bottom of
the object's top action section, before Transform/clipboard/delete. Labels and
north markers have no such actions. Hide Dimension/Show Dimension affects normal drawing,
not selection dimensions. Related property controls obey the same eligibility.

`AvailableDimensionActions` supplies shared eligibility for context menus and
Properties, based on potential ambient geometry rather than selection overlays:

| Wall mode | Flip Dimension | Hide Dimension/Show Dimension |
| --- | --- | --- |
| All | Supported directional openings with facing-side splitting | Objects contributing ambient dimensions under the active split settings |
| Exterior | Unavailable | Exterior dimensions with splitting enabled, independently of object facing |
| Exterior stacked | Unavailable | Exterior dimensions, using stacked mode's split-all policy |

Own-hidden dimensions are evaluated as if shown for Show Dimension eligibility,
but cannot be flipped until shown again in All mode. Exterior ignores facing.
Parent-hidden chains and disabled categories/master suppress child
actions. Interior-only openings offer neither action in exterior modes.
Fireplace face dimensions do not depend on window split settings. Explicit
dimension guides keep Hide/Show when the ambient master is off; selected-only
line annotations do not. `check_dimension_action_policy.py` covers the opening
type/mode/split/facing/hidden matrix and both UI surfaces.

In All, Exterior and Exterior stacked modes, hidden opening dimensions do not split
their parent wall's chain. The wall remains continuous, and unused stacked tiers
collapse. Hiding a wall suppresses its openings' ambient chain as well. On a
collinear run, hidden wall sections are clipped before building stacked tiers
rather than retaining the entire run through a visible neighbor's ownership.
Room detection and room areas are unaffected. Selecting a hidden object shows
only a separate overlay; its world dimensions remain hidden. Selecting walls,
openings, control points or groups never changes ambient splits, ownership or
stack tiers. Group bounds supplement ambient member dimensions instead of
replacing them. Coverage: `check_exterior_hidden_dimensions.py`
includes both wall references, rotated runs, undo/redo and PNG/SVG output.
`check_selection_dimension_overlay.py` checks selection invariance across all
modes, references, split preferences, hidden objects, groups and exports.

## EDIT-02: coincident furnishing warnings

Exact coincident copies of the same furnishing definition are advisory warnings,
independent of collision toggles and placement validity. Compare original
definition key, both oriented endpoints, width and horizontal/vertical flips.
Different dimensions/orientations/flips, different definitions and near-coincident
placements are not duplicates. This applies to furnishing objects, including
whole compounds, rather than labels or built-in north markers.

Among visible copies, keep the rear copy normal and draw every copy in front of
it with `warningOutline`, the same role as contained walls. Behind Counters
objects paint first, then ordinary furnishings; list order determines order
within each layer. Hidden copies do not cause visible copies to warn. Selection
does not replace the warning artwork color. Moving, resizing, flipping, hiding,
reordering or deleting a member updates the other member's warning, including
dirty-region redraw, pan caching and undo/redo. Do not delete or reject copies,
change their saved records, or block clipboard/duplication merely for coincidence.

Stationary architectural objects that fail the checker's placement rules use
`warningOutline` on the editing canvas, including when selected. Optional
collision switches retain their existing effects; overlapping openings remain
intrinsically invalid. Cache validation across unchanged hover/pan frames and
refresh it after geometry or collision-setting changes. Export previews and
PNG/SVG file rendering suppress these editor-only colors. Existing muted invalid
drag previews keep their behavior. Coverage: `check_architectural_error_highlights.py`.
One shared duplicate check covers every architectural type, including stairs,
railings and wall attachments, independently of collision switches. Compare
serialized geometry and visual settings while ignoring object IDs, measurement
visibility/flipping and recovery acknowledgements. Keep the rear equal object
normal, highlight front copies and exclude redundant copies from PNG/SVG exports.
Connected end-to-end segments are not duplicates. The problem dialog names the
actual type, such as Coincident stair or Elevator contained in another object,
rather than labeling every structural object as a wall.
Coverage: `check_architectural_duplicates.py`, `check_elevator_duplicate_warning.py`.

Check for Problems offers Auto-Repair for exact coincident copies of every scene
object type, including annotations. Repairing a duplicate category handles all
its coincident groups in one undoable edit. Keep one existing copy, preferring a
visible copy, and preserve unique attachments when merging duplicate walls.
Remove matching child copies after reparenting without deleting unrelated grouped
or connected objects. An opening from 1 mm through 10 mm long is a potential issue, not
invalid geometry. Tiny and collapsed openings retain a minimum screen-space hit
area so they can be selected through their parent wall; selected openings keep
their normal endpoint handles. Coverage: `check_problem_duplicate_repair.py`.
Counter and railing highlight clips include the complete outline stroke, rather
than exposing a normal half-stroke outside the surface. Coincident counters keep
a warning footprint even when merged geometry assigns their surface to another
owner. Fully covered rear furnishing copies do not contribute dark antialias
fringes beneath the front warning, in solid or transparent object mode.

## ACTIVITY-01: activity history and restoration

View > Activity Log opens the non-modal activity browser. Entries persist with
the project beyond normal undo retention. Restore to Here navigates retained
scene/reference or Export history without deleting activity descriptions, and
explicitly identifies which scope it restores. Branches, expired edits, errors
and recovery/issue events remain readable when restoration is unavailable.
See [Activity Log](../ACTIVITY_LOG.md) and `check_activity_log.py` /
`check_activity_events.py` for the complete contract.

## EXPORT-01: layout and enabled states

Order: Export heading; folder/browse; filename; Type; separator; Digital/Architectural tabs;
scrolling sections Canvas, Border, Grid, Line Weight, Dimensions, Composite,
Visibility; pinned Export action. Sections start collapsed unless restored.
Section gap 20, heading/content gap 12, ordinary export controls 32 high,
section buttons 40. Scroll content margins 14. Canvas labels are content-sized,
right aligned, with 8 px gap; fields take remaining width. Avoid a stretched
label column that wastes half the row. Reference captures contain exact bounds.

The folder and filename are separate 32-pixel-high text entries, pinned above
the scrolling sections. Keep the original full-width folder/browse row with
14-pixel side margins, 6-pixel field/button gap and 44-pixel browse button. Do not
add a label column. Filename sits 8 pixels below and spans the full row, aligned
with the folder field's left edge and browse button's right edge. Use placeholders
and accessible names to identify the entries. Browse opens the native folder-only
picker and remembers that folder in the current project without changing the selected
file type or a custom filename. Typed folder changes are also saved with the project
and session, and participate in export undo/redo. A project without a saved destination
defaults to its own directory, or the application directory before its first save.
Global browse preferences do not affect export destinations. Closing the project
clears its destination. Custom filenames are saved with the project and session,
restored on reopen, and cleared on Close. Filename displays a base name without
an automatically appended extension. Optional `.png`/`.svg` suffixes are ignored
case-insensitively and removed when committing the field; other dots remain part
of the name. Type determines the output extension without adding it to the field.
Previously saved names containing an export extension are displayed without it. Automatic
project-based filenames keep their existing collision suffixes; custom names
retain overwrite confirmation. Export joins the two entries and rejects folder
components or reserved characters in Filename. Both entries participate in export
undo/redo. Coverage: `check_export_destination.py`, `check_parity_panel_layouts.py`.

| Format/mode | Scale controls | Resolution | Composite |
| --- | --- | --- | --- |
| PNG Digital | Density + px/m or px/cm | Editable linked width and height | Visible |
| PNG Architectural | Ratio and PPI on one row | Readout | Visible |
| Optimized PNG Digital/Architectural | Same as corresponding PNG mode | Same as PNG | Visible |
| SVG Digital | Density in units/m | Absent | Entire section absent |
| SVG Architectural | Ratio, no PPI | Absent | Entire section absent |

The current print-density label is **PPI**, with explanatory DPI wording in its
tooltip; the serialized key remains `dpi`. Do not rename the wire key to match
a new framework's label. Density displays two decimals; changing density units converts the value while
preserving physical scale. PNG width/height/density are linked and include border
extent. Defaults: density 100 per meter, ratio 1:100, PNG PPI 300. Architectural
density is `DPI * 1000 / (25.4 * denominator)`; SVG uses 96 for its coordinate
density and physical output dimensions. Tooltips explain density units and DPI.

Canvas order: Theme, Background, Walls (Material/Solid/Outline), Lines, Solid
Objects. Border style has no redundant label; Color follows it, then Border
Size. Options: None, Plain, Frame, Corner Marks, Reference Zones, Marked, Ruler,
Ruler + Reference Zones. Border None disables its color/size dependents; Show
Grid off disables grid color dependents. Border minimums respect marks/text.
Combined border draws ruler first, darker reference-zone backgrounds and outlined
zone corners. Solid Objects affects physical backgrounds, not annotations;
transparent objects still occlude parts hidden beneath other physical objects.

Composite uses centered shared Vignette/Texture subheadings. Vignette off disables
the whole strength group. Texture None disables all its control groups. Stretch
textures disable Scale. Sliders have matching input/reset controls. Texture
defaults can come from filename hints. Do not assume every reset means zero.
Default vignette strength is **0.25**, texture strength **0.5**. These are the
intended baseline defaults; texture filename hints can supply other defaults.

## EXPORT-02: camera, crop, grid origin and undo

Export remembers its own zoom/pan separately from the editing camera. On entry,
retain zoom. Recenter only on first use or if the crop lies entirely on one side
of the viewport midpoint: right edge left of midpoint, left edge right of it,
top edge below it or bottom edge above it. Strict comparisons; an edge exactly
at the midpoint does not trigger recenter. Otherwise retain pan. Exit restores
the editing camera and presentation settings.

While Export is active, G and the View menu's grid toggle update the export grid
override. M and the View menu's measurement toggles update export
measurement-visibility overrides, including before any export GUI control has
been changed. The View menu reflects the resolved export grid and measurements.
These changes use export undo/redo and are saved under export settings. They do
not modify the editor's grid or measurement visibility; leaving Export restores it.
Outside Export, the same actions retain their normal editor behavior.
Tips and FPS remain app preferences. Maximize remains a window layout action,
and reference-image visibility remains project metadata outside export artwork.
Coverage: `check_export_measurement_shortcuts.py`.

Opening Options from Export switches to Build before showing either a new or
existing Options dialog. The editor camera/settings are restored, and export
overrides remain saved. Options controls always edit the project.
Export has Units and Precision rows followed by Measure and Walls sections.
The shared Walls controls include Mode, conditional Wall reference and the
Doors/Windows/Stairs/Counters split tabs, with identical sizing, reset, wheel,
drag and disabled-state rules to Options. Each control writes its own sparse
export override. Units, precision, mode/reference and each individual split
category inherit project values until overridden. Clearing an override restores
inheritance immediately. Returning to Build restores project settings.
Save/reopen, export undo/redo, PNG/SVG and CLI use the same resolved values.
Coverage: `check_export_dimension_settings.py`, `check_export_dimension_overrides.py`,
`check_export_cli_settings.py`.

Double-click a crop guide resets that edge to its automatic-bounds position.
Otherwise double-click inside the drawing region returns to 1:1 output pixels
(SVG units for SVG), accounting for device pixel ratio and preserving the world
point under the pointer. Crop hit tolerance is 8 logical px; nearest edge wins,
with ties in left/right/bottom/top world-edge order. Guide hit testing uses the
edge's extended line throughout the drawing rectangle, not only its finite
segment. Left/right crop edges and horizontal rulers use horizontal-resize cursor;
top/bottom edges and vertical rulers use vertical-resize. Middle pan takes cursor
priority. The viewport's own ruler strips and exported Ruler/Marked/combined
border ruler strips can move the corresponding grid-origin axis; crop-edge hits
exclude exported-border ruler hits.

Crop edges snap only to the grid visible in the exported output:
master snap enables it, Alt inverts it; individual snap target toggles are ignored.
Automatic bounds retain their geometric behavior without this manual snapping.
Dragging export rulers offsets the export grid origin under the same snap policy.
Double-clicking a horizontal ruler resets only the X origin to zero; a vertical
ruler resets only Y. This bypasses grid snapping, clears pending ruler drags and
records one export undo step when the value changes. It leaves crop and camera unchanged.
This setting does not move project geometry or its editing grid origin.

Build/manipulation commands and controls are unavailable in Export. Undo/redo
routes to export options, including continuous slider/crop gestures, never the
scene undo stack. Commit pending typed export text before undo. Export-only
presentation changes must not leak back to the normal canvas. Save while Export
is active still records the editing camera/settings plus separate export overrides.


## EXPORT-03: encoding and bounded previews

Type offers PNG, SVG and Optimized PNG. Optimized PNG uses the PNG preview,
physical scale, crop, compositing and print-density controls and writes `.png`.
Its in-memory export-history selector value is `PNG_OPTIMIZED`, while renderer requests remain
`png`. Encoding quantizes to at most 256 palette entries and retains alpha and
print-density metadata; it can change colors and is not a pixel-lossless variant
of regular PNG. Encoding errors are reported without replacing an existing
file, and the Export button state is restored. Native save filters,
extensions and export undo retain the selected format. The selected format is
saved per project and session in `exportSettings.fileType`, defaulting to PNG
when absent. Changing projects restores that project's format. Coverage:
`check_export_filetype.py`.

All three saved export types open a window-modal Exporting dialog after path and
overwrite validation. It shows the filename, an indeterminate animated progress
bar, current stage and Cancel. The editor remains responsive but cannot be edited
until the dialog closes. A separate process renders the unsaved scene using the
resolved export settings and catalog. Cancel, Escape and the window close button
stop the process, discard its temporary output and leave any destination unchanged.
Worker startup, render, encode and write errors close the progress dialog and show
Export Failed. Success atomically replaces the destination and retains the existing
Exported feedback and automatic filename numbering. No editor session is launched
by the worker. Qt can round outlined SVG ruler glyph coordinates differently in a
fresh process by 1/64 px; scene geometry and layout stay exact.
Binary Qt/JavaScript transfer avoids base64 raster buffers. Native zlib deflation
retains the original compression level. Optimizations preserve quantizer sample
and arithmetic order, palette decisions, alpha and print density. Frozen seeded
checks compare decompressed PNG chunks and decoded pixels exactly; compressed
IDAT bytes and file sizes may differ.
Coverage: `check_export_progress.py`, `check_export_button.py`, `check_optimized_png.py`,
`check_optimized_png_parity.py`.

File output remains limited to 32,767 units per side; PNG additionally has a
100-million-pixel allocation limit. SVG has no raster-area limit. Preview
sampling is independent: oversized PNG previews use a bounded overview and
visible detail after navigation settles. SVG retains bounded navigation/detail
rasters. Caches share the raster budget; preview success does not bypass export
limits. Ordinary opaque PNG can encode RGB, while transparency requires alpha;
Qt RGB32 working images still occupy four bytes per pixel.

Recoloring updates relevant SVG paint layers, including inherited paints and
referenced patterns, without changing fill/occlusion, strokes or text. Equivalent
adjacent clip layers can consolidate without changing order. Solid-object state
caches must invalidate on geometry/non-palette changes. Material fills form
seamless coverage, and sampled PNG previews retain opening cutouts across zooms.
Original SVG numeric coordinate scale must not change normalized dash spacing
or visible lettering size/position. These are appearance requirements, not a
prescription that a browser duplicate Qt's cache implementation.

## EXPORT-04: exclude editor warnings from artwork

PNG, SVG, optimized PNG and all preview paths omit editor-only warning objects.
For coincident furnishings retain the normal rear copy and omit the warned front
copies. Omit contained walls/pillars/columns, including their attached openings.
Omit active recovered-opening geometry warnings and stationary furnishings whose
placement fails the editor's collision check. Do not paint their warning/error
colors in the output or simply recolor the faulty objects as normal geometry.
Partial furnishing overlaps remain ordinary artwork unless another existing
warning condition applies.

Null placeholders and unusable top-level fallback artwork are omitted. When a
compound contains a Null child, hide that child's complete artwork and retain
healthy siblings. This also applies to older embedded Null graphics. Hidden
placeholder backgrounds must not occlude healthy artwork. Preserve the explicit
crop and output scale. Export filtering operates on a separate viewport and
renderer variants, without removing objects from the editor, modifying recovery
references, changing saved data or adding undo entries. Bounded PNG overview and
detail snapshots use the same exclusions as final file output and SVG previews.

Coverage: `check_duplicate_furnishing_export.py`, `check_contained_walls.py`,
`check_large_export_preview.py` and `check_furnishing_asset_consistency.py`.
