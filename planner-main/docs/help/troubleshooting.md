# Troubleshooting

## An object will not place or move

Check that a door, window or fireplace is on a valid supporting wall and has
enough room. A fireplace cannot be shallower than its wall. **Collision** settings
may prevent a physical object from overlapping another one. Review the preview and
adjust the size or position before releasing the mouse. Disable **Collision**
per object type in the **Settings** menu if you do not want collisions enforced.

If more objects move than expected, check **Connected Points**, **Connected Objects**
and **Group Mode**. See [Selecting, moving and editing](editing.md).

## Movement or rotation follows unexpected axes

Check the **Local/Global Transforms** button beside the canvas. Press `Tab` with
the canvas focused to switch between the two modes.

Global transforms use the plan's fixed horizontal and vertical axes. Local
transforms use the object's direction at the start of the drag. This affects
movement constraints and their guides. Hold `Ctrl` during a move to constrain
it to those axes. Rotation snapping also follows this
choice: global mode snaps to the plan's 15-degree angle increments, while local
mode measures those increments from the object's starting angle.

If a rotated object snaps to unexpected angles, switch to global mode. If you
want to move along a rotated object's own axes or rotate relative to its current
angle, switch to local mode. The toggle does not change an object's geometry by
itself, and **Size** properties still describe its local width and length.

The rotation pivot is separate from this setting. In rotation mode, drag the
pivot to move it, or `Double-click` it to return it to the center. **Position**
shows the pivot in rotation mode and the object center in resize mode.

## An object or measurement is missing

Check the World tab's category filters and master visibility. Press `Alt + H`
to restore individually hidden objects. For dimensions, check the global
measurement toggle, category measurement switches and the object's
**Show measurement** context action when available.

## An object is shown in an error color

A project may have retained highlighted geometry for manual repair, or a graphic
may be missing. Read the load warning and inspect the affected object. Correct
its dimensions, position or attachment, or remove it. Use **Save As** after
recovering a project to keep a separate copy.

## Chamfer is not shown

Select a control point at a usable two-wall corner. Lone endpoints, straight
joins and junctions of three or more walls do not expose Chamfer. Mixed control point
selections hide it if any selected control point is ineligible.

## Units or rounding look unexpected

Check **Units** and **Precision** in the **Settings** menu. **Adaptive Metric** changes the displayed
unit with the grid interval. Canvas **Precision** rounds displayed dimensions.
Properties retain more precise values. Changing units does not alter geometry.

## The exported drawing looks different

Export may have its own theme, visibility, line weight and color overrides.
Check those controls before returning to the editing view. SVG hides raster
Composite effects. Optimized PNG can approximate colors and gradients. Use
ordinary PNG if you need the full-color render.

Preview zoom is separate from export scale. For printing, check architectural
scale, PNG print density and the print dialog's fit-to-page setting.

## A large export or preview fails

Reduce the crop or export density and retry. Larger dimensions use more memory.

## A project cannot be opened

Read the error or recovery message. A truncated or invalid file may be unusable.
Try a known saved copy or the backup named in a recovery message. Cancelling
recovery leaves the currently open drawing intact. See [Projects and recovery](projects.md)

[< Previous: Keyboard and mouse shortcuts](shortcuts.md)

[Back to Help](README.md)
