# Checks

Run from the repository root after installing `requirements-dev.txt`:

```powershell
python checks/run_checks.py
python checks/run_checks.py check_export_plan.py check_portable_parity.py
python checks/run_checks.py --report diagnostics/check-results.json
python checks/run_checks.py --jobs 1
```

The runner runs up to four checks concurrently by default, bounded by CPU count
and available memory on Windows. Use `--jobs N` to choose a worker count, or
`--jobs 1` for serial debugging. A single named check runs without copying the
checkout. Nested runner calls default to one worker to avoid multiplying pools.
Probes outside the repository, or inside the `diagnostics/` and `screenshots/`
output directories, run serially with their original sibling paths. This also
prevents artifact collection from moving a later diagnostic input away.

Every check still executes in a separate process with temporary application
preferences, session, startup and system-temp paths. Parallel workers receive
independent disposable copies of the public source/fixtures, so source-relative
captures and temporary fixture edits cannot collide or modify the checkout.
Private workspace drawings and generated/build directories are excluded.
The two native-platform font checks run exclusively after the parallel batch.
The runner records failures from assertions and
unhandled Qt callbacks or threads. Python assertions must remain enabled.
The optional JSON report records every check's status, duration, timeout,
return code and output in discovery/input order, plus the worker count and any
capture directory; failures still produce a nonzero process exit code.
Native faults are captured with Python's fault handler, and unused BLAS threads
are capped in child checks, matching the app's texture runtime configuration.
Console/child output uses UTF-8, including redirected Windows logs. Failure
details are saved immediately, even if the remaining run is later interrupted.
GitHub's Windows workflow installs only `requirements-dev.txt` and uploads
the text log, JSON report and captures. `check_check_runner.py` covers real
concurrent execution, worker limits, source/output isolation, native-check
serialization, failures, Unicode output and timeout reporting.

GitHub runs every discovered `check_*.py` at 100% scaling, plus nine paint,
dragging and snapping checks at 125% and 200% in separate Windows jobs. The
pan-DPI check also exercises 100%, 125%, 150%, 175% and 200% internally.
Each job retains logs, JSON results and failure captures, including on failure.

Resolve temporary fixture roots with `Path(directory).resolve()` before comparing
them with paths returned by the app. Hosted Windows runners can expose TEMP
through an 8.3 alias such as `RUNNER~1`, while file dialogs and the app return
the canonical path.

Checks normally have a 30-second timeout. The dorm-opening-mask and Print-paper
matrices, repeated render and guide-selection session integration checks
have 60 seconds, and the full external-theme, CLI export, sparse-history and selection-overlay matrices have 120 seconds to allow
for slower hosted Windows workers. Concurrent runs multiply these limits by
`ceil(jobs / 2)` to allow CPU contention. These are hang limits, not performance targets.

`fixtures/` contains frozen reference implementations and render baselines.
[Synthetic plans](fixtures/plans/README.md) replace dependencies on personal
workspace drawings. They are test inputs, not application startup files or demos.

The runner creates ignored `diagnostics/`, `screenshots/` and `tmp/` output
directories as needed. Do not add generated captures as reference baselines
without reviewing their purpose and expected appearance.
Parallel captures are retained separately for each check under
`diagnostics/check-runs/<run-id>/`; disposable source copies are removed when
the run finishes. Serial runs retain the original output locations.

The current UI and file contracts are indexed in
[parity verification](../docs/parity/VERIFICATION.md). In particular,
`check_export_dimension_settings.py` covers sparse export overrides versus
Options' project settings. `check_export_dimension_overrides.py` covers precision
and split overrides, shared controls and leaving Export when Options opens, while `check_hover_click_targets.py` and
`check_line_vertex_priority.py` check active hover against actual click targets.
Historical screenshots are not substitutes for those current interaction checks.

Activity Log coverage: `check_activity_log.py` checks journal restoration,
persistence, branches and expiry. `check_activity_events.py` checks issue and
recovery events, settings, checkpoint storage and safe decoding. See
[Activity Log](../docs/ACTIVITY_LOG.md).

`check_activity_storage.py` covers bounded decoded log rows, complete archived
history, streaming encoding and archive cleanup. `check_resource_lifetimes.py`
covers furnishing dialog/model destruction, repeated document replacement,
native renderer eviction, export undo bytes, synchronous SVG batch cleanup and
single-snapshot GUI export preparation.

Dimension visibility: `check_exterior_hidden_dimensions.py` covers hidden
openings/walls in every wall mode. `check_selection_dimension_overlay.py` checks
that selection, control points and group bounds do not modify ambient chains or
stack tiers. Both include rotated geometry and PNG/SVG output.
`check_dimension_action_policy.py` covers action eligibility across opening
types, wall modes, split settings, facing and hidden state, including inward
Exterior's orientation-independent splits and stacked mode's effective split-all behavior.

Architecture regressions: `check_architecture_boundaries.py` covers independent
snapshot/history imports, named replay, project/export view ownership, rendering
value keys and indexed problem validation. `check_architecture_edit_reliability.py`
and `check_activity_incremental_encoding.py` cover archive failure isolation and
bounded checkpoint preparation, including encoding on the recovery worker.
`check_architecture_worker_startup.py` covers missing theme resources, atomic
reloads and retained worker diagnostics. `check_render_capture_ownership.py`
checks transparent rendering resource ownership on success and failure.
`check_exterior_binary_splits.py` checks Exterior's two-position selectors,
reset, stored All-mode preferences, facing/flip independence and PNG/SVG output.
`check_stacked_dimension_rounding.py` checks that displayed spans balance to the
independently measured overall in every unit/precision, without altering geometry.
It includes opposite-side totals, reversed/rotated chains, both wall references
and PNG/SVG rendering. `check_dimension_chains_core.py` covers numeric rounding,
symmetry, nominal opening widths and incomplete-chain fallback without Qt.

Export/Print coverage includes physical PPI and centered scale changes, complete
page selection, crop/page gestures, fixed-spacing overlap, paper categories,
title-block layout/typography/logo modes, scale bars and wheel-input forwarding.
The `check_print_*.py`, `check_architectural_*.py`, `check_export_title_block.py`,
`check_export_scale_bar.py` and `check_export_wheel_scrolling.py` checks use
synthetic project inputs and repository resources.

`check_export_preview_process.py` exercises the real asynchronous worker and
stale-result rejection. `check_composite_live_preview.py` uses held mouse drags,
not only slider signals. `check_preview_allocation_recovery.py` checks bounded
failure recovery, while `check_numpy_runtime_budget.py` and
`check_normal_lighting_cache.py` cover import memory and exhaustive lighting
parity. `check_retained_dimensions.py` preserves editor painter pixels and
fallback behavior. `check_project_build_tab.py` verifies project transitions
and session recovery never activate Export.

`image_comparison.py` provides stored-channel NumPy comparisons for the pan/edit
raster, annotation, chamfer and mask checks. Their original error thresholds and
pixel/channel counting rules remain. `check_image_comparison.py` verifies an
independent byte-loop oracle, alpha, signed differences, odd sizes, padded rows
and source immutability. `check_numpy_containment.py` checks ordered results
against frozen geometry, including block boundaries, rotated/duplicate/degenerate
objects, large coordinates, tolerance boundaries, scalar fallback and cache
invalidation. Small scenes and cache hits do not initialize NumPy.

Developer probes may read an explicitly supplied project or a read-only recovery
copy. The automatically discovered `check_*.py` suite must use temporary state
and repository fixtures, so it can run on a fresh GitHub checkout. Do not turn
machine-specific wall-clock timings into correctness gates; use cache/preparation
counts and image/geometry comparisons for behavior.

The recent drag/zoom regression matrices use `fixtures/editor_interactions.py`
and the existing synthetic dense-room plan, with an additional isolated oblique
wall. No private project is copied or required. Dragged endpoints are centered
on screen, and the shared validation matrix requires each wall fixture to move.
The historical `check_flat_interactions.py` and `check_flat_next.py` filenames
remain stable, but their input is now wholly synthetic. Standalone local
performance benchmarks are separate from the automatically discovered suite.
