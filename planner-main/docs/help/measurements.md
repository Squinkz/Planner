# Units, measurements and visibility

## Units and precision

You can set the units used by Planner in the **Settings** menu. Planner uses
metric in millimeters by default, but this can be changed to imperial units if you
prefer working with inches or feet.

Metric options are millimeters, centimeters, meters and Adaptive Metric. Adaptive Metric
follows the grid's major interval at the current zoom or export scale.

Imperial units are either inches only, or feet and inches. Measurements displayed on the
canvas use fractions; other UI controls use decimal inches.

Changing units does not resize your drawing.

The **Precision** option in the **Settings** menu affects displayed canvas measurements, not the underlying dimensions or the precision of property controls:

- **High:** nearest 1 mm, or nearest 1/16 inch.
- **Medium:** nearest 5 mm, or nearest 1/4 inch.
- **Low:** nearest 20 mm, or nearest inch.

Medium is the default.

## Shown measurements

Use the **View** menu to control the display of measurements. `Ctrl + M`
toggles the display of all measurements on the canvas. Walls, stairs, counters, railings and elevators have independent
visibility controls.

Doors, windows, stairs and counters can optionally split wall measurements when they touch or intersect. These options can be configured in the **Settings** menu.

The measurement display options are overrides for entire classes of objects. If you need to
disable the display of measurements for a single object or group of objects only, use the
`Right-click` context menu and choose **Hide measurement**. You can enable it again later by
choosing **Show measurement**.

## Object visibility

| | |
|---|---|
![**World tab**](images/icons/world.png) | World tab |

The **World** tab toggles visibility for entire object categories. Objects can also be hidden on a per object basis,
and then unhidden at a later point.

| | | | |
|:---:|:---|:---|:---|
| ![Hide Selected](images/icons/hide_sel.png) | **Hide Selected** | `H` |  Temporarily hide selected objects. |
| ![Hide Unselected](images/icons/hide_unsel.png) | **Hide Unselected** | `Ctrl + H` |  Temporarily hide unselected objects. |
| ![Unhide All](images/icons/unhide.png) | **Unhide All** | `Alt + H` |  Restore all temporarily hidden objects. |

Hiding a wall hides its attached objects as well. If an object does not return with
Unhide, ensure that its category and the master visibility control are enabled.

Export has its own visibility and measurement overrides. See
[Exporting and printing](export.md).

[> Next: Appearance and color controls](appearance.md)

[< Previous: Toolbar Buttons](toolbar.md)

[Back to Help](README.md)
