# Export shortcut audit

Audited 28 October 2026. Export is a preview/settings workspace: editing the scene
requires leaving Export. Grid and dimension visibility must be changed through
the Export controls.

| Command | Behaviour in Export |
|---|---|
| G / M | Disabled; View menu entries disabled; use Export controls. |
| B / Alt+B | Disabled; both reference-image View menu entries disabled. Reference controller also rejects browse/load/show/toggle requests. |
| Q / W | Wall-width shortcuts disabled. |
| D / S | Opening-placement hold keys blocked. |
| T / Space | Move Special and furnishing search blocked. |
| Delete / arrow keys | Cannot delete or nudge scene objects. Focused controls retain normal key handling. |
| H / Ctrl+H / Alt+H | Cannot change scene visibility. |
| Ctrl+G / Alt+G | Cannot group or ungroup objects. |
| Ctrl+Tab | Group-mode shortcut disabled; native tab navigation may still operate. |
| Ctrl+A / Ctrl+Shift+A | Cannot select/deselect scene objects. Text selection remains available in fields. |
| Ctrl+C / Ctrl+X / Ctrl+V / Ctrl+Shift+V | Scene clipboard commands blocked; Edit menu cut/copy/paste disabled. Text-field clipboard editing remains native. |
| Tab / Shift+Tab | Normal control navigation; cannot toggle transform orientation. |
| Ctrl+Z / Ctrl+Shift+Z | Export settings undo/redo, with pending field text committed first. |
| F / Escape | Maximize and restore the viewport. |
| 1 / 2 / 3 / 4 | Navigate workspace tabs. |
| Wheel / middle drag / crop handles / ruler drag | Export preview navigation and crop/origin controls. |
| Alt during crop or ruler drag | Temporary snapping inversion retained. |
| Project shortcuts | Remain available; project actions return to Build. |
| F1 / Alt+P | Help and problem inspection remain available. |

The audit covered registered QShortcuts in header/sidebar construction, application
key-event filtering, viewport key handlers, export overlay handling, reference-image
controller entry points, and View/Edit menu dispatch. Editor-only QShortcuts are
disabled on entry and restored on exit. View commands also guard their dispatch,
so disabled menus are not the only protection. Input-field guards preserve typing
and standard editing commands.

Regression coverage: `checks/check_export_shortcuts.py`, export settings/history
checks, reference-image checks, text-shortcut checks, opening-shortcut checks, and
project action/navigation checks. The previous test asserting that G/M modify
export overrides was replaced because that behaviour is no longer intended.
