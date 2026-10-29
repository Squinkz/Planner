# Rendering diagnostics

## Capture a session

From the repository root:

```powershell
python tools/capture_rendering.py
```

Reproduce the interaction and close Planner. The launcher writes `diagnostics/render-diagnostics.json`. Use `--output <path>` to select a file in an existing directory.

Collection is opt-in. Developers can enable it with `PLANNER_RENDER_DIAGNOSTICS=1` and save a report through `viewport.renderDiagnostics.Write(path)`.

Reports record Python, Qt and platform details, plus:

- Paint callback CPU time and intervals between paints.
- Input age at paint entry and event-loop delays sampled by a 20 ms timer.
- Input timestamps, delivery sequences, oldest/latest input age and the number
  of delivered inputs combined into each paint. Mouse samples include local
  pointer positions; paint samples include camera offsets and pan state.
- Scene and collider preparation timings.
- Scene and pan cache hits and miss reasons.
- Recovery submissions, preparation, writer timing and save outcomes.
- Garbage-collection generation, duration and object counts.
- Retained raster bytes, peak admitted bytes and allocation or eviction events.

Sample buffers retain 2,048 entries; cache counters cover the session. Summaries include p50, p95, p99, maximums and counts above 16.7, 33 and 50 ms.

## Interpret a report

Paint intervals include idle time. Input age measures the time from Qt delivering the latest viewport input to paint callback entry. Paint duration and the event-loop timer measure CPU and GUI scheduling. Native presentation traces or external measurements provide display presentation and input-to-photon timing.

`relativeInputQueueLagMs` compares input-event timestamps with delivery time,
using the minimum observed clock offset as a baseline. It exposes additional
queueing relative to the least-delayed observed input, not absolute OS input
latency. Zero/absent timestamps are excluded, and timestamp regressions reset
that baseline. Input samples distinguish spontaneous/native and synthetic events.
Oldest input age helps identify a burst that the latest-input metric alone
would hide. Frame-pacing metadata includes the screen's reported refresh rate.

`pan_pacing_20261022.py` posts a controlled 250 Hz input stream while the normal
Qt event loop paints. It records final-position accuracy and repaint cadence,
unlike the synchronous repaint-cost probe. It defaults to offscreen and makes
no claims about monitor presentation. `capture_rendering.py` above captures the
same enhanced telemetry during an ordinary interactive app session.

Timeline events share a `perf_counter` clock and identify their thread. Recovery preparation covers GUI work and synchronous waiting; writer duration covers serialization and file I/O. Overlapping timestamps help identify operations to investigate. Controlled comparisons establish their effect on a hitch.

Reports contain timings, runtime metadata, viewport-local input positions and camera offsets. Project contents and recovery paths stay in their own storage.

## Raster and artwork budgets

Each viewport shares a 128 MiB budget across retained backgrounds, scene/pan buffers, PNG snapshots, SVG navigation/view images and ruler strips.

Oversized editing views use direct drawing. Oversized PNG previews keep a bounded overview and capture visible detail after navigation stops; file export limits remain independent. SVG navigation uses up to a quarter of the budget and four million pixels; stationary previews adapt sampling to available memory. Ruler strips can draw directly.

Raster counters describe application-owned retained surfaces. Process memory measurements additionally capture Qt backing stores, assets, vector data and export allocations.

Artwork caches retain 512 recent icon engines, 2,048 recent sources per registry, 1,024 recent tint paths and resources referenced by live widgets. Handle renderers retain 64 recent variants. Retirement is batched; monotonic filenames preserve live stylesheet references.

## Probes and validation

```powershell
python checks/run_checks.py ../tools/diagnostic_overhead_probe.py
python checks/run_checks.py ../tools/icon_cache_probe.py
```

The overhead probe measures dispatch costs of disabled diagnostic wrappers. The icon probe repeats artwork across themes and records registry counts. Their generated JSON files contain workload-specific measurements.

Set `PLANNER_VERIFY_RENDER_REVISIONS=1` to compare revision-keyed cache reuse with value-based validation. A mismatch raises an assertion. Scene models and tracked collections report geometry, appearance and topology mutations; edit stored coordinates to notify their owning objects.

## Native Windows soak

```powershell
python tools/native_render_soak.py --seconds 1200
python tools/native_render_soak.py --seconds 60 --switch-projects --output diagnostics/native-project-switch.json
```

The probes open isolated test windows and exercise editing, panning, zooming, resizing, theme changes and export previews. Temporary project and recovery fixtures are cleaned up on exit. Project-switch mode reloads a saved fixture.

Reports include CPU/event-loop diagnostics, Windows working-set and private-byte samples, and raster/artwork counts. The workload uses 200 walls and 20 doors; compare results under consistent workload and environment settings.

Dated audit reports, benchmark outputs and repair records under `diagnostics/`
preserve the conditions and observations of their individual runs. This guide
describes the current diagnostic workflow.

## Angled-room opening clips

Stair wall occlusion includes wall fills and strokes, with door and fireplace
openings removed. Exactly tangent opening cuts can cause Qt path subtraction
to fill an enclosed room at particular zoom levels. Build the cached opening
cuts relative to the world origin and give through-wall cuts clearance beyond
the outer stroke. Keep their jamb endpoints fixed. The visible wall cut still
uses its original half-stroke allowance, so adjoining walls do not gain notches.
Pocket recesses retain their narrower cut.

`check_angled_room_occlusion.py` exercises the original failure on a synthetic
angled enclosure, all opening variants, zoom/pan changes, floor shading, other
object layers and PNG/SVG rendering. `check_stair_occlusion_cache.py` retains
exact mask checks and verifies that camera translation does not rebuild the mask.

`check_angled_mask_clipping.py` compares interior object ink against an isolated
reference for stairs, counters, railings and furnishings. It includes door,
window, fireplace and overlapping-column masks, fractional camera positions,
floor shading, opaque/transparent PNG and painted SVG output, and cropped
exports. Solid-room grid clipping is checked separately for suppressed interior
lines and unchanged exterior lines. This complements the topology checks with
pixel assertions, rather than accepting any nonempty rendered object.
