# Annotation behavior

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
`check_angle_right_marker.py`, `check_guide_labels.py`, the 23-type object matrix
and the AngleGuide render example. The fixture matrix observes both endpoints,
middle and label states, not just whole-object selection.
