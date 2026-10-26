# Projects and recovery

## Project handling

Use the **File** menu to open or save a project, or the shortcuts:

| | |
|---:|---|
| `Ctrl + N` | New project from the startup template. |
| `Ctrl + O` | Open a project. |
| `Ctrl + S` | Save project. |
| `Ctrl + Shift + S` | Save Project as. |
| `Ctrl + W` | Close project. |

Custom furnishing arrangements used on the canvas are embedded within a saved project.

## Startup file

Planner uses a startup file to set the defaults for new projects. You can set Planner up
the way you prefer, including adding objects to the canvas, and choose **File > Save startup file**.

This makes the current setup the starting template for new
projects. It is separate from saving a named project, and can include objects
as well as settings.

## Check for problems

**Edit** > **Check for problems**, or `Alt + P`, checks your map for missing graphics, missing definitions, invalid geometry
and other objects in impossible states. Select an entry to locate the affected objects. You can then
delete them or choose **Auto-Repair** if a repair is available.

The **Potential issues** tab lists geometry that may or may not be intentional, such as wall joins that
are nearly 90 degrees or walls that are almost parallel to the x or y axis. You can ignore an intentional
issue or choose **Auto-Repair** to correct it.

## Activity log

The **Activity Log**, available in the **View** menu, records your actions, application messages and detected
problems or potential issues.

Select an entry with an available restore state and choose **Restore to Here** to return to that point.
Planner retains a limited number of undo states, so older entries eventually become unavailable for restoration.
Their descriptions remain in the log.

## Recovery

Planner keeps recovery checkpoints and restores the session when available. Only one Planner process
can own a recovery session at a time; close the existing instance before launching another.

When opening a damaged or incomplete project, Planner attempts to recover settings and
resources where possible.

When a plan has issues, Planner may ask the user to either:

| | |
|---|---|
| **Remove:** | Delete the problem object and any dependent attachments. |
| **Highlight:** | Highlight broken objects for manual cleanup. |
| **Repair:** | Apply the correction proposed in the dialog. |

Unavailable choices are disabled. Closing a geometry dialog cancels loading.

Before applying recovery changes, Planner makes an exact backup of the original
file. The recovery message gives its path and a summary of changes. Missing artwork
may appear as a marked placeholder until its definition is available.

[> Next: Exporting and printing](export.md)

[< Previous: Appearance and color controls](appearance.md)

[Back to Help](README.md)
