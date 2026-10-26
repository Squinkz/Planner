# Editing boundaries for future ports

Source module paths below are relative to `planner_app/`.

The reusable sparse record engine lives in `edit_transactions.py`. The desktop
adapter remains `history_edits.SceneEdit`; its public name and project-history
encoding are unchanged. This split deliberately leaves Qt-specific coordination
in the desktop rather than imposing a generic transaction manager.

## Reuse: sparse record algorithms

`SparseSceneEdit.Between` creates reversible changes from two temporary snapshots.
`Apply` creates a transient result without mutating scene models. The current
snapshot contract has categories 0 (walls), 3 (openings), 5 (furnishings), 8 (labels),
selection slots 1/2/4, groups 6 and hidden objects 7. Records start with a live
object reference; remaining fields are opaque values supplied by an adapter.

Preserve these rules in a port:

- Object identity is distinct from value equality and serialized project IDs.
  Opening parent changes must be detected even for equal-valued wall objects.
- Values use the adapter's equality semantics. Desktop records still contain
  QPointF, including Qt's fuzzy point equality. Converting all points to plain
  tuples here would change what counts as an edit; that conversion is not made.
- Insertions/deletions retain unaffected relative order. Store full category
  order vectors only when surviving objects are actually reordered.
- Group membership uses unordered member identity; hidden membership uses object
  identity. Replay still preserves the stored list/position semantics.
- A selection-only change creates no edit. An edit that changes scene records
  stores both selections so undo/redo restores the relevant context.
- Validation rejects mismatched source records, invalid ordering and invalid
  membership at the same replay stages. Model-specific final validation is an
  explicit required adapter method; do not silently skip it when validation is
  requested.

The base class has no GUI or model imports and runs without third-party packages.
A new port supplies record capture, equivalent value/identity comparisons and
model validation rather than importing Qt or relying on Python object IDs on disk.

## Keep: desktop model adapter

`history_edits.py` owns edit tokens and retained-payload estimation. Python object
sizes, shared asset references and QPointF storage are desktop details. A future
runtime needs its own conservative estimate, not a translation of sys.getsizeof.
The existing count/byte caps and serialized history schema are unchanged.

Final validation of parent walls, groups and hidden objects stays in this adapter:
it depends on which live model classes are valid parents and members. The sparse
engine calls the adapter after generic replay checks; the adapter is read-only.

## Keep: transaction and UI coordinator

`viewport/scene.py` remains responsible for:

- `CaptureState` / `RestoreState`: Qt point snapshots, model setter order,
  attachment restoration, stair layout links, visibility and selection.
- `RecordEdit`: object IDs, pruning groups/hidden entries, stair bookkeeping,
  monotonic coalescing/revision guards, memory limits, redo invalidation and
  scene-change notification. A coalesced no-op still follows the existing
  revision/notification policy; no notification order was changed.
- `Undo` / `Redo`: cancel an active gesture before scene replay; dispatch to the
  separate export-options history when the export tab is active.

`viewport/interaction.py` owns gesture begin/release/cancel and preview cleanup.
Qt event ordering, mouse state, modifier keys, pending copies/pivots, widget focus,
cursor updates and repaint requests belong there. A future UI should implement
its own event adapter and logical gesture lifecycle; it need not copy every Qt
view field or inherit a new event framework.

Export undo (`ui/export_history.py`) uses a different state/preview lifecycle and
remains separate. Forcing it into scene-record history would add coupling rather
than remove it. Activity Log links to both journals while keeping their scopes
separate. Its persistent descriptions do not extend undo retention or retain
scene snapshots. See [Activity Log](ACTIVITY_LOG.md). Likewise, signal delivery,
dialogs, timers and widget wiring stay
in Qt. The code is left where it belongs; these notes describe the intentional
boundaries.

## Pointer target coordination

Pointer target resolution is also a desktop adapter responsibility.
`interaction.SelectionTarget` combines the scene hit with furnishing handles and
multi-selection semantics, and is shared by hover, cursors, presses, double-clicks
and context menus. A port needs the same priority outcome, not independent
hover and click hit tests that can disagree. Reference-image editing and
calibration intercept events in their exclusive modes before scene interaction.
See HOVER-01 and `check_hover_click_targets.py`.

## Verification

`check_edit_transactions.py` exercises the sparse engine without Qt and compares
Qt-valued records, replay/validation errors, memory estimates and instance sizes
against a frozen pre-split implementation. Existing checks cover coalescing,
branches, saved history, invalid history recovery, selection, cancellation,
group/copy/transform operations and export-tab undo routing. Paired diagnostics
also compare complete desktop commit/undo/redo work and scene-change signals.
