# Object behavior reference

All dimensions below are millimeters. Scene coordinates use +Y upward. Display
units change presentation, never the geometry. These tables describe the current
desktop app, including distinctions between structural objects and furnishings
that happen to share handles or an SVG renderer.

[object-behavior.json](reference/object-behavior.json) is the executable companion:
31 current types, exact visible property widgets, ranges, increments, tooltips, handles,
visibility categories, context actions with measurements on/off, seed records,
all eight collision setting combinations and footprint exclusions. Replay it with
`python checks/run_checks.py check_object_behavior_matrix.py` from the workspace.

[Annotation contracts](ANNOTATIONS.md) specify angle editing, point identities,
movable labels and rendering. These are represented in the current matrix and
render corpus as well as dedicated interaction checks.

## Creation and editing

The wall tool's factory presets apply to new drawing gestures and are also stored
in the bundled startup plan. Saved projects and custom startup templates retain
their own values. The raw Wall model constructor still
has a 240 mm fallback, used by authored geometry fixtures and callers that omit
width; that fallback is separate from the tool's selected 200 mm factory preset.

“Endpoints” means two control points. “Box” means eight resize handles, four
rotation handles and a movable pivot. Labels use four proportional corner resize
handles instead of eight. Shift resizes from the center; Shift during rotation
duplicates. Shift resize does **not** duplicate. See [EDIT-01](INTERACTIONS.md)
for gesture rules, snapping, connected movement, groups and cancellation.

| Object | Build default | Editing and important properties | Attachment |
|---|---|---|---|
| Wall | Tool width 200; presets 100/150/200/300 | Endpoints; width, length, material; control point X/Y/chamfer | Structural junctions |
| Counter | Width 600 | Endpoints; width, length; eligible control point chamfer | Independent |
| Railing | Width 80 | Endpoints; width, length, autosize; manual post count/spacing | Independent |
| Stair | Width 1000 | Endpoints; width, length, autosize, direction; manual count/step size; eligible control point chamfer | Connected stairs can form landings |
| Pillar | 300 × 300 | Box; width, length, angle, material; rectangular body | Independent |
| Column | 300 × 300 | Same as Pillar; elliptical body | Independent |
| Elevator | 1200 × 1200 | Box; width, length, angle; architectural SVG/line weight; no material or furnishing artwork flip controls | Independent |
| Door | Span 900 | Endpoints; length, swing, hinge, measurement side | Wall child |
| Double door | Span 1800 | Endpoints; total length, shared swing, measurement side; two half-span leaves with outer hinges and no center jamb | Wall child |
| Swinging door | Span 900 | Endpoints; length, hinge; two opposed 90-degree swing arcs; no facing or measurement-side control | Wall child |
| Sliding door | Initial span 1800; panel size 900 | Endpoints; length, door size, panel side, slide direction, measurement side | Wall child |
| Pocket door | Initial span 1800; panel size 900 | Endpoints; door size, pocket side | Wall child |
| Barn door | Initial span 1800; panel size 900 | Endpoints; door size, facing, slide direction, measurement side | Wall child |
| Bifold door | Span 1200 | Endpoints; length, swing | Wall child |
| Open doorway | Span 900 | Endpoints; length | Wall child |
| Window | Span 1200 | Endpoints; length, facing, measurement side | Wall child |
| Silled window | Span 1200 | Window plus sill depth | Wall child |
| Casement window | Span 600 | Window plus hinge | Wall child |
| Awning window | Span 1200 | Window with dashed rectangular projection, limited to its span; facing | Wall child |
| Double casement window | Span 1200 | Two opposite half-span casement leaves in one frame; no central crossbar or hinge toggle | Wall child |
| Fireplace | Width 1200; depth 500 or wall thickness, whichever is larger | Eight resize handles; width, length/depth, facing, material; no free rotation/pivot | Wall child; depth offset across wall |
| Furnishing | From definition | Box; width, length, angle, horizontal/vertical flip | Independent; compound definitions retain child order |
| Label | From text/font bounds at 32 points | Proportional box; text, point size, intensity; width/length presentation | Independent annotation |
| Room label | Centered name at 32 points, area line at 55% of the name size | Label controls with Name and calculated Area; area follows the detected room under its center | Independent annotation in Labels visibility |
| North arrow | 600 × 1000 | Box; width, length, angle | Independent annotation |
| Arrow | Tail thickness 10 | Endpoints; length, solid tip, tip size, tail thickness, intensity, direction flip | Independent annotation |
| Measurement guide | Zero body width | Endpoints; length, text offset | Independent annotation |
| Boundary line | Zero body width | Endpoints; length, selected-only dimensions; dash-dot stroke | Independent annotation |
| Dashed line | Zero body width; Objects weight | Boundary controls plus Weight class; dashed stroke | Independent annotation |
| Solid line | Zero body width; Objects weight | Boundary controls plus Weight class; solid stroke | Independent annotation |
| Angle guide | Zero body width | Two arm endpoints and a middle control point; unsigned angle, text offset | Independent annotation |

Lengths for drawn linear objects come from the drawing gesture. The
[CHAMFER-01](CHAMFERS.md) convention is: 0 is an uncut sharp join and 1 is the
full translating-plane cut; new control points start at zero.

All five window types offer a Window well checkbox, off by default. Enabling it
reveals Well depth (600 mm initially) and Dashed well outline (off initially).
The open rounded outline extends 150 mm beyond each jamb and returns to the
wall face. It follows the window's facing and span. Depth remains an independent
physical dimension. The well is part of its window, with no separate selection,
visibility or collision body. Clicking its outline selects the window.
Well settings participate in history, clipboard, project/session persistence,
recovery, render invalidation, automatic export bounds and PNG/SVG export.
Legacy records default to no well. Coverage: `check_window_variants.py`.

Swinging doors are double-acting openings. Their hinge side is shared by both
swings and can be flipped in properties, the context menu or Ctrl orientation.
They have no stored facing direction. With door measurement cuts enabled, they
split both wall faces; the no-cuts mode omits both. Their default size is 900 mm,
with the normal nominal imperial conversion for new objects. They appear in the
Doors palette and visibility category. The D-key cycle appends Swinging Door
after Open Doorway, preserving existing saved type choices. Coverage:
`check_swinging_doors.py`, the object matrix and the frozen render corpus.

Double doors pair two standard 90-degree door leaves with opposite outer hinges.
Both leaves use half the opening span and share one facing direction. Only the
outer jambs are drawn. Properties and the context menu expose swing direction
and the usual one-sided measurement flip, with no hinge-side control. Placement,
Ctrl orientation, copy/paste, history, recovery, visibility and export follow
standard doors. The D-key cycle appends Double Door after Swinging Door; the
palette and default-size settings place it next to Standard Door. Coverage:
`check_double_doors.py` and the shared opening/measurement/render checks.

The matrix uses a **2000 mm example axis**, not a product default length. Opening seed parents
are 6000 mm long. A furnishing seed uses Desk; other definitions have their own
dimensions. Build settings are stored in centimeters in the machine-readable
matrix and project settings; multiply by ten for metric placement millimeters.
Imperial placement derives nominal whole inches from these source defaults,
unless an explicit imperial default override exists. See
[placement sizing](INTERACTIONS.md#measure-01-displayed-dimensions).

For sliding/pocket doors, the door-size property represents half the opening
span; do not replace it with a second independent length. Opening orientation
controls are type-specific, even where they share an implementation class.

Fireplace depth cannot be smaller than wall thickness. Its placement snaps to
either flush extreme or the centered depth position. Dragging onto a thicker wall
may enlarge the preview; returning before committing must recover the original
size. Its U-shaped material body has a complete outline through the wall;
measurements go in front and behind it. It has no opaque rectangular background.

Elevators are symmetrical and have no furnishing flip state. Sharing the SVG
drawing path must not require these flags or expose furnishing artwork controls.
Generic context-menu reflections transform their geometry like other objects.

## Visibility, measurements and drawing

Each object follows its named visibility category in the matrix. Pillar and
Column use Walls; Elevator has Elevators. World is the master visibility switch.
Hiding/deleting a wall includes its attached openings/fireplaces; undo restores
the relationships. Hidden objects are different from measurement-hidden objects.

Counter and stair shapes merge only through shared control endpoints at their
end caps. Side contact and end-to-side contact preserve separate outlines.
Side seams remain visible in end-connected U-shaped chains. Ordinary wall
intersection merging is unchanged. Stair flights have one inset line along each
long edge, 25 mm from the outer edge (capped at one quarter of narrow widths).
Treads and collinear join dividers stop at these lines. Insets continue around
joined landing outlines and the ends of shared side seams, without adding a
second cap at a free flight end. They use the normal architectural color/line
width. Stair direction shafts continue through landings when an unambiguous
incoming/outgoing pair agrees on direction. Intermediate heads are suppressed.
Conflicting directions and branches keep independent arrows; directed cycles
retain a direction head. Geometry is cached independently of camera and color.
Coverage: `check_run_end_merging.py`, `check_stair_landing_annotations.py`, the
stair junction and landing checks.

Stair direction arrowheads are fixed at 12 drawing units long and 7 units on
each side of the shaft. Stair length, width, trimmed landings and direction do
not resize the head. Canvas and export rendering share this symbol geometry.
Coverage: `check_stair_arrowheads.py`.

Global measurements gate all ambient measurements and related UI options.
Walls, pillars, columns and fireplaces follow wall measurement visibility;
stairs, counters and railings have their own switches. Elevators have no ambient,
selected or context-menu measurements. Doors/windows
also follow their measurement mode (both sides, facing side or no cuts).
Measurement guides draw their explicit measurement. Furnishings, labels, north
arrows and arrows do not gain ambient object measurements merely because they
have bounds.
Boundary lines draw a dash-dot stroke at all times while visible, with a length
label only when selected. They share measurement-guide editing and annotation
collision exclusion, but have their own visibility category. Exports omit their
selected-only measurement labels. See [annotation behavior](ANNOTATIONS.md).

Hide/Show dimensions belongs at the bottom of the object's top context-menu
section, before Transform. Offer it only when that class currently draws ambient
measurements, including allowing an individually hidden measurement to be shown
again. Flip Dimension additionally requires a supported type and facing-side
mode. Global measurement disable also removes these controls from Properties.
Individual hiding never suppresses selection dimensions. A selected group gets
bounding-box dimensions, rather than dimensions on each member.

Physical objects use theme fills/outlines and the appropriate wall,
architectural or furnishing line weight. Counters normally draw below furniture;
Move to Back/Front on furniture overrides/re-enables this relationship. North
arrows draw above physical objects. Compound child z-order must survive creation,
save/load and export. Transparent objects preserve occlusion of graphics below
them without changing text weight. Wall Material/Solid/Outline and export color
overrides are presentation choices; they do not rewrite model material values.

SVG export bakes stroke widths at export scale, removes non-scaling stroke, and
outlines text. PNG uses raster output scale. Neither exports selection handles.
See the [rendering examples](EXAMPLES.md) for actual output and scale metadata.

## Collision policy is not placement validation

The matrix's `collisionPolicy.enabledRows` are pair-policy booleans, in the same
23-type order as `objects`. Profile bits are Walls=1, Architectural=2,
Furnishings=4. `footprintExclusionRows` independently identifies pairs excluded
from footprint collision. A true policy entry does **not** mean every overlap
is illegal: attachment, openings, junctions and valid movement impose additional
rules.

Structural walls may join/intersect. Openings must fit a valid parent and avoid
conflicting openings/obstructions. Pillars/columns use structural validation;
elevators use architectural validation and collide with physical blockers.
Ordinary furnishings may overlap other furnishings and counters; they cannot
pass through blocking walls when the relevant collision settings apply. Railing
footprint exclusions differ from elevators. Labels, arrows, linear/angular guides
and north arrows are nonphysical. Connected-object movement and collision
validation are separate concepts: overlap can connect a movement set without
making two objects an invalid placement.

Use the existing collision/attachment regression checks for exact placement
examples. Do not implement a new collision engine using only this boolean table.

## Evidence boundaries

The property probe enables all measurement categories and facing-side opening
measurement mode to reveal conditional fields; those settings are **not** factory
defaults. It also captures manual stair/railing fields separately. Geometry and
menu probes run with painting disabled; rendering has its own corpus. Context
menus in this matrix are single-object menus. Multi-selection, junction-specific
actions and native input behavior remain covered by the interaction specification
and existing regression checks rather than every possible table combination.


## ART-01: authored furnishing geometry

Definition files are authoritative for default dimensions and artwork. Frozen
examples must follow reviewed definition edits, not force catalog dimensions
back to a historical value. See the selective recording procedure in EXAMPLES.
SVG `planner-bounds` controls the physical body while retaining protruding ink.
`planner-fixed-` IDs on groups or individual shapes keep details at their authored
world size when enlarging, anchored at their midpoint; below nominal size they
shrink uniformly by the smaller furnishing scale. This is independent of zoom.
Compound child `fixedSize: true` retains that child's authored dimensions by the
same shrink rule while its center follows arrangement scaling. Nested geometry,
flips, collision footprints, connected-object contact, decomposition and export
must use the resulting child geometry. Empty compound bounds do not collide or
connect objects. Detailed resource fields live in
[the furnishing schema](../resources/FURNISHINGS.md).

## Shared subdivision and dissolution

Walls, counters, stairs, railings, arrows, measurement guides, boundary lines,
dashed lines and solid lines offer Subdivide in their context menus. Walls retain
their clear-segment search around openings and blocking geometry; other straight
objects divide at their midpoint. New halves retain the concrete type and its
appearance, sizing, direction and Weight settings. Outer chamfers remain; the
new joint is sharp. Groups and hidden state follow the replacements. Subdivision
clears the whole-object selection and selects both endpoints at each new joint
(endpoint 1 of the first half and endpoint 0 of the second). Dragging the joint
keeps the halves together even with Connected Points and Connected Objects off.
Subdividing multiple objects selects both endpoints of every split. Redo restores
this control-point selection.

Dissolve Control Point is offered at a shared endpoint of exactly two objects of
the same concrete class. It replaces them with the chord between their outer
endpoints, retaining the lower-ID object's settings and both outer chamfers.
A zero-length result is rejected. Wall dissolution retains opening rebasing and
fit validation. Mixed classes never dissolve together. Both actions form a single
undoable edit, including object/group/visibility replacement. Box-controlled
objects, wall attachments and three-point angle guides do not offer these actions.
Coverage: `check_linear_subdivision.py`, `check_wall_dissolve.py` and
`check_opening_transform_core.py`.
