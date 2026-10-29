# Troubleshooting

- [An object will not place or move](#an-object-will-not-place-or-move)
- [Movement or rotation follows unexpected axes](#movement-or-rotation-follows-unexpected-axes)
- [An object or dimension is missing](#an-object-or-dimension-is-missing)
- [I cannot select objects while adjusting a reference image](#i-cannot-select-objects-while-adjusting-a-reference-image)
- [An object is shown in an error color](#an-object-is-shown-in-an-error-color)
- [Chamfer is not shown](#chamfer-is-not-shown)
- [Units or rounding look unexpected](#units-or-rounding-look-unexpected)
- [The exported drawing looks different](#the-exported-drawing-looks-different)
- [A large export or preview fails](#a-large-export-or-preview-fails)
- [A project cannot be opened](#a-project-cannot-be-opened)

## An object will not place or move

Check **Collisions** under **Settings > Build > General**. Turn off the relevant
setting if the overlap is intentional.

Doors, windows and fireplaces need enough free space on a supporting wall.
A fireplace must also be at least as deep as the wall is thick.

If other objects move along with your selection, check **Connected Points**,
**Connected Objects** and the grouping toggle beside the canvas.
See [Selecting, moving and editing](editing.md).

## Movement or rotation follows unexpected axes

Check the **Global/Local Transforms** button beside the canvas. Press `Tab`
with the canvas focused to switch modes.

| | | |
|---|---|---|
| ![Global Transforms](images/icons/global.png) | **Global** | Uses the plan's horizontal and vertical axes. |
| ![Local Transforms](images/icons/local.png) | **Local** | Uses the object's orientation at the start of the drag. |

Hold `Ctrl` while moving to constrain movement to those axes. Rotation snapping
uses the plan's fixed angles in Global mode and the object's starting angle in **Local**
mode. Switch to **Global** if you want to line a rotated object up with the plan.

Switching modes does not change the object itself. **Size** fields always show
its local width and length.

If rotation is off-center, `Double-click` the pivot to reset it. You can also
drag it to a new position. **Position** shows the pivot in rotation mode and
the object center in resize mode.

## An object or dimension is missing

Check the **World** tab's visibility controls. `Alt + H` restores individually
hidden objects, but disabled categories must be enabled separately.

For missing dimensions:

- Press `M`, or use **View > Toggle Dimensions**, to toggle their display.
- Check the object categories under **Settings > Dimensions**.
- If you hid an object's dimension manually, select it and choose
  **Show Dimension** from its context menu.
- Check the wall **Mode** and split settings. Exterior modes omit interior wall
  dimensions, and split settings control which objects contribute dimensions.

While exporting, use the dimension controls in the **Export** tab.

## I cannot select objects while adjusting a reference image

Only the image can be transformed while its controls are open. Click an empty
area of the canvas to return to normal editing. See [Reference image](reference.md).

## An object is shown in an error color

This can mean missing artwork, invalid geometry or overlapping duplicates.
Press `Alt + P` to open **Check for Problems**. Select an entry to locate the
object, then repair it manually, use **Auto-repair** if available, or delete it.

For missing assets, restore the definition or graphic, or replace the affected
object. Use **Save As** if you want a separate copy while cleaning up the plan.

## Chamfer is not shown

Select a control point where exactly two walls form a corner. Chamfer is not
available at lone endpoints, straight joins or junctions of three or more walls.
If several control points are selected, every selected point must qualify.

## Units or rounding look unexpected

Check **Units** and **Canvas precision** under **Settings > Dimensions**.
**Adaptive Metric** follows the grid interval. Precision rounds dimension labels,
while property fields keep more precise values. Changing units does not resize
existing objects.

Export has its own unit and precision controls. Room labels can also have an
individual unit override, which takes precedence over both project and export units.

## The exported drawing looks different

Export has its own theme, visibility, line-weight and color settings. Check
these in the **Export** tab.

Composite effects require PNG. Optimized PNG may change colors and gradients,
so use regular PNG to retain the original colors.

Preview zoom does not change export scale. If a print comes out at the wrong size,
check the architectural scale, PNG PPI and the print dialog's fit-to-page setting.
See [Exporting and printing](export.md).

## A large export or preview fails

Reduce the crop area or output resolution. Large images need more memory,
especially with compositing effects. Try regular PNG if Optimized PNG is
causing trouble.

## A project cannot be opened

Read the error or recovery message. Planner may offer a repair. If the file is
badly damaged, try a known saved copy.

Recovery messages list the original file's backup location. Keep that backup
until you are happy with the recovered plan.
See [Projects and recovery](projects.md).

[< Previous: Keyboard and mouse shortcuts](shortcuts.md)

[<< Back to Help](README.md)
