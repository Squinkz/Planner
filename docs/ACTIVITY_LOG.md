# Activity Log

View > Activity Log opens a non-modal window for the current project. Its table
lists entries in chronological order, with local time, type, description and
restoration status. Search filters the table without changing the log. Selection
shows plain-text details. The window starts with the search box and table, with
no redundant entry-count/tip row. The window remains open while editing or changing
projects and refreshes to show the incoming project's log.

The log records scene edits, reference-image edits, Export settings, undo/redo,
project settings, canvas notifications, application errors, project/session
recovery and findings from Check for Problems. Continuous scene gestures follow
the existing undo boundaries. Coalesced keyboard edits update a single entry.
Export slider gestures likewise produce one entry at the end of the gesture.
Project settings are grouped after a short idle interval. Settings entries are
descriptive because those settings do not have a scene undo transaction.

Identical canvas/application notifications are suppressed for five seconds.
Problem findings are recorded when first detected, not on every recheck. Their
subsequent resolution, deletion or ignore action is recorded separately.
Auto-repair entries link to their corresponding retained scene edit. Actual
problems, including coincident objects, are checked after committed edits and
project loads without opening the Problems window. Checks are debounced and
deferred during canvas drags, rather than run on every frame. Potential-issue
checks start in the Problems tool; previously detected potential issues continue
to be rechecked after edits. The log uses the same problem-finding routines as
the tool and avoids a second scheduled check while that window is open.

## Restoration

Restore to Here means the state immediately after an edit. Undo/redo entries
identify the before/after side reached by that operation. The action is disabled
for the current state, notifications, settings without undo, expired history and
discarded branches.

Scene restoration uses the existing undo/redo journal, including reference-image
edits, after validating the complete route. Export restoration uses its separate
journal and affects only Export. The UI identifies the scope explicitly.
Restoration does not rewind the log. It appends a restoration entry, and normal
redo remains available. A new edit after restoration discards the old redo branch
as usual, but the abandoned branch's activity descriptions remain readable.

Normal undo retention remains 200 edits and 16 MiB of retained scene payload.
Export history retains its existing independent 100-entry limit. Log entries do
not retain model objects, image data or scene snapshots and do not extend those
limits. Expired descriptions remain in the log.

## Persistence and validation

Projects and session checkpoints store an optional top-level `activityLog`:

```json
{"version":1,"encoding":"zlib-base64","data":"..."}
```

The compressed JSON contains entries, currently retained scene undo/redo links,
and known issue metadata. Each entry has a sequence ID, UTC timestamp (or null),
type, summary, details, affected object IDs and an optional history anchor.
The UI converts UTC timestamps to local time. Existing projects can import their
retained undo records as Earlier edit entries with no invented timestamps.

Saved scene links match both stack position and a SHA-256 fingerprint of the
edit, with equivalent integer/float values normalized. Unmatched or discarded
journals cannot expose restoration. Export history remains session-local as
before, so saved Export descriptions become read-only after reopening a project.

The decoder validates structure and types, limits decompressed log data to
64 MiB and rejects trailing or incomplete compressed payloads. The normal 64 MiB
project-file limit also applies. Recovery can discard damaged activity metadata
without modifying scene geometry and records that action in the incoming log.
Log content is displayed as plain text and is never executed or parsed as HTML.

Clear Log asks for confirmation, clears descriptions and issue tracking, and
leaves undo/redo intact. An explicitly empty log remains empty on reopening
instead of importing old journal entries again. Future actions start a new log.
Startup templates exclude activity, so new projects start without their author's
log. Log-only events do not change the normal scene/settings dirty comparison;
they persist on project save and through session checkpoints. Export rendering
snapshots exclude the log.

## Implementation and checks

- `planner_app/activity_log.py`: compact descriptions, notifications, issue
  transitions, persistence, retained-journal links and restoration.
- `planner_app/ui/activity_log.py`: virtualized table model, search, details and
  restore/clear controls, using the existing application theme.
- `check_activity_log.py`: scene/reference/Export restoration, reload links,
  branch invalidation, undo expiry, coalescence, Clear Log and older projects.
- `check_activity_events.py`: settings, issue detection/resolution/ignore/repair,
  recovery events, session checkpoints, safe decoding and plain-text display.
