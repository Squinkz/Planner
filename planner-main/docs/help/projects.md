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
file. The recovery message gives its path and a summary of changes. A recovered
project opens unsaved: use **Save As** to keep the recovered copy. Missing artwork
may appear as a marked placeholder until its definition is available.

[> Next: Exporting and printing](export.md)

[< Previous: Appearance and color controls](appearance.md)

[Back to Help](README.md)
