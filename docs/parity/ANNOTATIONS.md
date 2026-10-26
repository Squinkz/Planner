# Annotation behavior

## GUIDE-03: boundary lines

BoundaryLine is a zero-width, nonphysical annotation with two control points.
It is placed from Boundary in Build's Annotations section and uses the same
placement, endpoint/body editing, Ctrl angle snapping, cancellation,
properties, clipboard, duplication and undo behavior as MeasurementGuide.
Boundary lines have their own World/export visibility category, Boundary lines.
They do not collide with architecture or furnishings.

Draw a dash-dot stroke directly between the control points using the dimension
line width and measurement-line color (selection color when selected). It has
dash/gap/dot/gap lengths of 6/3/1/3 times the larger of one logical pixel and
the stroke width, so thin strokes retain a readable pattern. It has
no measurement ticks or label when unselected, independently of the global
measurement switch. Selection displays its length, including when automatic
measurements are hidden. Its selected measurement is a body-selection target, not an independently
draggable label. Its hidden label and leader are not hit targets when unselected.
Visible boundary/dashed/solid strokes and endpoints take hit priority over
structural wall bodies, including selected walls behind them.
Export always includes only the dash-dot line, with no measurements. Preserve
dash patterns in both solid/transparent PNG and SVG rendering. The object's
nonselected bounds follow its line, not an invisible dimension label.

Persist the type as BoundaryLine with zero width and optional textOffset. History,
recovery, session handle selections and clipboard transports retain the type.
Existing files without Boundary lines visibility default that category to on.
Coverage: `check_boundary_lines.py`, `check_session_guide_selection.py`.

## GUIDE-04: dashed and solid lines

DashedLine and SolidLine share BoundaryLine placement, control points, body
editing, snapping, selected-only measurements and collision exemption.
Build's Annotations section includes Dashed Line and Solid Line beside Boundary.
Each has its own World/export visibility category, enabled by default.

Their additional Weight dropdown follows Length, defaults to Objects and offers
Walls, Objects, Furnishings and Dimensions. It uses the normal property row
height and spacing. Mixed weight selections show `(different)` until edited.
Changing Weight is one ordinary undoable edit. It changes appearance only, not
object classification, collision behavior or geometric width.

The Walls option uses wallOutline color and walls line width. Objects uses
objectOutline and architectural width. Furnishings uses objectOutline and
furnishings width. Dimensions uses measurementLine and dimensions width.
These resolve from the current editor/export appearance, including live theme
and line-width changes. Selection uses the usual selection color.
Dashed strokes use dash/gap lengths of 6/3 times the larger of one logical pixel
and the stroke width. Solid strokes have no dash pattern. Zero class line width
hides the stroke, matching the corresponding class.

Persist the concrete type, zero body width, textOffset and weightClass. Missing
weightClass defaults to Objects; unknown values are rejected. The Dimensions
option retains the stored `Measurements` key for existing projects. Clipboard,
duplication, scene/session history and recovery retain the class and weight.
PNG and SVG export use the configured class style without selection measurements.
Coverage: `check_weighted_lines.py`, object behavior matrix and render examples.

## GUIDE-01: angle guides

AngleGuide is a nonphysical scene annotation, not a wall attachment. It shares
Measurement guides visibility and has zero body width. World and annotation
visibility apply, while ambient wall/stair measurement switches do not turn an
explicit guide into a physical object. Its persisted control points are `first`,
`second` and `middle`; desktop endpoint indices remain 0/1, with middle at 2.

The measured value is the unsigned smaller angle, 0–180 degrees, between arms
from middle to the two endpoints. A collapsed arm makes it undefined. Properties
show Undefined and disable the angle editor in that state. Endpoint Position
edits move just that endpoint. Object Position refers to middle; moving middle,
including its handle, translates both arms by the same displacement. Position
supports mixed selections and atomic property scrubs, cancellation and undo.

The angle field has one decimal place, one-degree steps, and a 0–180 range.
Editing equalizes both arms to the shorter captured length. The arm farther from
north (+Y) rotates, preserving its existing side of the fixed arm; ties rotate
the second arm. A scrub keeps that initial choice throughout, including crossing
north or passing through 0/180. Editing does not continually reselect the fixed
arm from intermediate preview geometry.

Ctrl endpoint dragging snaps its arm around middle in 15-degree steps. Global
steps use fixed axes; local steps start from that arm's initial direction, not
the chord joining endpoints. Ctrl middle dragging uses global X/Y constraints
and translates all three points even in local transform mode. Show the constraint
guides. Grid/target switches and temporary Alt inversion retain their normal
meaning. Connected geometry must not carry the guide's free arms as junctions.

An exact right angle uses a square marker capped at 12 logical screen pixels,
reduced for short arms. The decision uses the geometric angle, with 1e-10 radians
of numerical tolerance, never the rounded text: an 89.96-degree angle can display
90 degrees while retaining its arc. Non-right angles draw the smaller arc.
Collapsed arms have no angle marker or label. Construction arms appear on
selection/hover and disappear afterward without an undo edit or scene change.
Invisible arms are not body hit targets. Unselected marker ends retain short
radial extensions unless nearby visible geometry aligned with that arm explains
its direction; a perpendicular crossing or hidden wall does not suppress them.

Whole-body move, Shift duplication, clipboard, Delete, undo/redo, save/load,
automatic export bounds and PNG/SVG export preserve all three points. Deleting
a selected middle or arm handle deletes the annotation as an object.

## GUIDE-02: movable measurement labels

Linear and angular guide labels are independent drag targets (desktop hit index
3). Dragging a label edits only its world-space `textOffset`, never its control
points or measured value. One drag is one reversible edit; Escape/right-click
restores the previous offset. Double-click resets it to zero, with undo support.
Double-clicking an already centered label does not reset the camera or create an
empty history entry. Nudge with the label selected changes the offset alone.

A moved linear label has a selectable leader from the measured segment's center.
Guide labels remain upright/readable under their normal layout rules. Offsets
survive copy/paste, save/load and history. Older linear records omit the offset
and load centered. Both PNG and SVG use the moved label, and automatic bounds
include remote labels. An exact right-angle square remains a square when its
label moves; the marker's geometric anchor stays in place.

Evidence: `check_angle_guides.py`, `check_angle_guide_controls.py`,
`check_angle_point_properties.py`, `check_angle_guide_hover.py`,
`check_angle_right_marker.py`, `check_guide_labels.py`, the 24-type object matrix
and the AngleGuide render example. The fixture matrix observes both endpoints,
middle and label states, not just whole-object selection.
