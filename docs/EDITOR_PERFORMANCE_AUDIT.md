# Editor performance audit

## NumPy containment filtering — 30 October 2026

Containment cache misses now batch bounding-box comparisons for scenes with at
least 64 eligible wall objects. The filter retains input order, the existing Qt
bounds test and the exact polygon containment predicate, including the 0.01 mm
tolerance and duplicate-owner choice. Small scenes use the scalar path. Cache
hits return before array setup. The temporary candidate matrix has at most 64
rows; no N-by-N matrix or new persistent geometry cache is retained. Nonfinite
rectangles fall back to the original scalar path.

`tools/numpy_geometry_probe.py` alternates the frozen and current methods with
identical synthetic walls, pillars, columns, counters and elevators. Repeated
recomputations include footprint/cache-key work and array construction. On
Windows/Python 3.14.3, Qt 6.11.2 and NumPy 2.4.6:

| Eligible objects | Frozen scalar | Batched filter |
| --- | ---: | ---: |
| 64 | 5.06 ms | 3.97 ms |
| 128 | 7.98 ms | 6.30 ms |
| 404 | 38.04 ms | 16.07 ms |
| 1,024 | 194.48 ms | 50.22 ms |
| 4,096 | 2,641.30 ms | 245.46 ms |

These measure containment recomputation, not whole editor frames. Existing cache
hits remain unchanged; 16/32-object cases keep the scalar path. The lazy shared
NumPy initializer cost 86.6 ms once in this process, and remains capped to one
unused BLAS thread. Tracked peak allocation for a 4,096-object recomputation was
about 1.69 MiB, including Python allocations and temporary arrays; this excludes
the already imported runtime and retained model/footprint data.

`check_numpy_containment.py` compares 101 matrices with the frozen pre-change
method, covering sizes around array/block boundaries, rotation, duplicate order,
empty footprints, excluded types, membership/geometry edits, large coordinates,
tolerance edges and unusual rectangles. Existing interaction, warning, collision
and render checks retain independent behavior and pixel assertions. The same
runtime initializer is shared with texture lighting; rendering itself is unchanged.

## Zooming the recovery scene — 30 October 2026

An isolated copy of the current recovery project contains 404 objects. The
diagnostic reads that snapshot without changing the real project or session.
At a 1600 × 1000 viewport, 16 anchored zoom steps (eight in, eight out) initially
took a median 100.74 ms/frame, with a maximum of 123.71 ms. Measurements consumed
most of the profiled time, particularly stacked exterior dimensions.

Two changes preserve the existing sharp rendering and wheel behavior:

- Dimension spans, owners and stacked tiers stay in project coordinates. Their
  preparation key no longer includes zoom. The annotation picture key still
  includes zoom, so current screen-space offsets, glyph sizes, minimum-span
  thresholds and adaptive units are redrawn at each zoom.
- When zoom changes, annotation recordings skip spans outside the visible area,
  using the existing conservative bounds test. These incomplete recordings
  never enter the reusable pan-picture cache. Complete recordings remain
  available for panning; no scaled bitmap or delayed quality pass is introduced.

Repeat unprofiled runs measured about 39–42 ms/frame, with maxima around
55–61 ms. One run after exact-pixel verification reported a median 38.92 ms and
maximum 55.49 ms. The drawing still has a visible-rendering cost; this is not a
claim that every editor interaction runs at 60 frames per second.

Reproduce with `python diagnostics/audit_editor_zoom.py <label> [parity]`. The
optional parity pass compares six recovery-scene zoom frames exactly with full
current-camera dimension replanning and complete annotation recordings.

`check_editor_zoom_measurements.py` covers all/exterior/stacked modes, wall-face
and centerline references, cursor anchoring, exact full-redraw pixels, world
geometry reuse, pan handoff and invalidation for geometry, hidden dimensions,
selection, split settings and visibility. It also passes at 150% display scaling
with render-revision verification enabled. Existing measurement, editor-cache,
pan and export checks cover integration.

## CPU preparation and submission — 30 October 2026

The GPU work remained an isolated offscreen benchmark. No editor backend change
was made. Further CPU experiments with generic camera caches, nested text
pictures and spatial annotation indexing did not give reliable benefits on the
current scene and were removed.

This pass keeps three narrower improvements:

- Dimension extension/tick coordinates use scalar arithmetic rather than
  repeatedly constructing temporary QPointF values. Each dimension's recorded
  line segments are submitted together, preserving their order before its label.
  Direct painting and SVG still use the original individual-line path.
- A single world-span preparation retains stacked lengths and lazily formatted
  labels. Label widths are reused by font/device style and adaptive unit band.
  Only visible labels are formatted, the dictionary is limited to 4,096 entries,
  and model/selection/unit/precision changes replace the preparation.
- Ordinary editor paints use the existing conservative opening-symbol bounds
  rejection, which previously ran only for panning or dirty-region painting.
  The bounds include swing length, sill depth, window wells and additional
  fixed-pixel arrow/antialias clearance. Export keeps its existing submission
  policy. Opening symbol calls in the 16-frame profile fell from 1,216 to 410.

Alternating before/after runs in the same process compared frozen original
methods with the updated methods, using identical camera sequences. Warm
cycle medians were approximately 44–46 ms before and 41–43 ms after. One full
64-frame aggregate (including slower initial samples) was 48.07 versus 41.53 ms.
The warm improvement is modest; the scene has not reached 60 FPS. These numbers
use the newer saved camera and should not be compared directly with the earlier
camera's 39–42 ms result.

Six recovery-scene camera positions matched the frozen original methods exactly.
`check_editor_cpu_submission.py` checks skipped symbol calls against an
all-symbol render, line batching, stacked-length reuse, cached-width font
invalidation, imperial formatting and precision. The broader checks include
150% display scaling with render-revision verification enabled. The precision
formatting check now centers a wall face at extreme zoom so its label remains
visible under the existing annotation culling policy.

## Isolated retained CPU prototype — 30 October 2026

The initial experiment in this section was **not enabled in the application**.
The later dimensions-only integration is documented in the next section. The
original prototype adds only development tools, with no production imports,
renderer switch, GPU backend or export changes.
Its scene is frozen for camera-only benchmarks; editing, selection transitions,
theme changes and manual/angle guide rendering are not implemented. Unsupported
annotation scenes fail explicitly rather than silently dropping their content.

`tools/retained_editor_probe.py` reads an isolated copy of the recovery project
or an explicitly supplied JSON project. It creates a hidden offscreen window
through the existing fixture, which redirects preferences and session writes to
a temporary folder. Original drawing methods are substituted only inside scoped
patches in this process. Image comparisons also verify that restoring those
methods reproduces the exact original frame after the prototype has rendered.

Two approaches were measured:

- Retained annotations: 340 dimension groups become native QGraphicsScene items.
  Their anchors stay in project coordinates, while labels, ticks and offsets keep
  their screen sizes. Zoom updates each visible dimension's span and endpoint
  positions; Qt paints the retained items without rebuilding an annotation
  QPicture or resubmitting every glyph and stroke from Python. Adaptive units
  still change with zoom. Whole-scene traversal avoids QGraphicsScene.render's
  source-query rejection of screen-sized children anchored outside the source
  rectangle; conservative explicit visibility tests bound actual painting.
- Retained model plus annotations: model commands and ordinary labels are
  recorded once as a native QPicture, with screen-space pens made cosmetic.
  Camera changes replay that picture with a new transform. On this scene the
  picture is about 1.36 MB and its initial construction takes about 50–60 ms.
  This is a feasibility measurement, not an appearance-equivalent replacement.

At 1600 × 1000 and 100% display scaling, alternating full viewport-grab tests
discard the first warm cycle and measure four subsequent 16-frame cycles
(eight anchored zoom steps in, eight out) for each variant. The same camera
sequence is used for the original and prototype in each process.

| Camera / variant | Current median | Prototype median | Reduction |
| --- | ---: | ---: | ---: |
| Saved, annotations only | 51.42 ms | 39.50 ms | 23% |
| Saved, model plus annotations | 50.40 ms | 30.79 ms | 39% |
| Room, model plus annotations | 26.02 ms | 22.03 ms | 15% |
| Detail, model plus annotations | 19.49 ms | 19.29 ms | 1% |

The saved camera in this recovery snapshot is zoom 0.14132865798613703. Earlier
audit numbers used different saved cameras and are not directly comparable.
Room and detail cases center on project position (6000, 8000), starting at zoom
0.6 and 1.5 respectively. These are synchronous render/grab times, not measured
interactive input-to-display latency. No claim of a general 60 FPS renderer is
supported by these results.

Seven image comparisons per variant expose the remaining visual differences:

- At 100% display scaling, annotations-only differs in 1,218–1,643 pixels out
  of 1.6 million, with a maximum channel difference of 7/255. No pixel exceeds
  an 8/255 channel difference. Native item transforms and primitive replay do
  not exactly reproduce the current annotation QPicture rasterization.
- At 150% scaling, device scaling must also be applied to cosmetic stroke
  widths. Even after that correction, 21–34 pixels per comparison exceed an
  8/255 channel difference, with maximum differences up to 139/255. This still
  needs work before integration. Median times were 72.08 versus 58.47 ms.
- The retained model differs more substantially after zoom changes. In the room
  case, about 12,000–20,500 pixels exceed 8/255 after scaling the recording.
  A single transformed picture cannot generally preserve pixel-based material
  patterns, passage clearances and SVG elements that cap their screen size.
  These need separate treatment instead of accepting the scaled output.

The original renderer is restored and its reference frame remains pixel-exact
after each experimental comparison. The experiment's own output is **not**
pixel-exact and is not accepted as a replacement. Its frozen model also lacks
spatial command culling, which helps explain why it provides virtually no
improvement in the detail case. A command-to-path flattening variant was slower
and had larger image differences; it was discarded.

The useful next architectural step is a retained annotation layer with complete
invalidation and device-scale parity. The entire-model picture should not be
integrated as-is. Retaining model artwork would additionally need spatially
bounded batches and separate handling of pixel-dependent drawing. These results
show further CPU gains are possible, but do not establish a drop-in solution
that preserves all appearance and behavior.

Reproduce sequentially, without competing tests or benchmarks:

```powershell
python tools/retained_editor_probe.py --parity
python tools/retained_editor_probe.py --model --parity
python tools/retained_editor_probe.py --model --parity --camera room
python tools/retained_editor_probe.py --model --parity --camera detail
$env:QT_SCALE_FACTOR = '1.5'
python tools/retained_editor_probe.py --parity
```

Results and comparison images go into the ignored `diagnostics/` directory,
with distinct names for camera, variant and display scale. `--project` accepts
a project JSON instead of the recovery snapshot. The probe requires visible
dimensions and an unselected scene without manual or angle guides.

## Integrated retained dimensions — 30 October 2026

The editor now retains ordinary dimension labels and backgrounds as native Qt
graphics items. It updates their absolute screen geometry for each camera frame
and paints onto the existing CPU QPixmap. The model renderer and export renderer
are unchanged. This is not a GPU renderer or an entire-scene recording.

The initial prototype's image differences came from primitive and transform
choices, not an unavoidable reduction in rendering quality:

- QPicture replays dimension line segments as separate two-point polylines.
  Using direct lines produces different antialiasing at fractional display
  scaling. The retained stroke item paints those same polylines with ordinary
  logical pen widths, so device scaling follows the original painter.
- QPicture replays label background fills as filled paths. A native rectangle
  item uses another raster operation and leaves slightly different edge pixels.
  The integrated backgrounds use those exact rectangle paths.
- Geometry is computed from the original projected endpoints, with the same
  arithmetic order and absolute coordinates. Glyph paths retain their separate
  translations. The scene mapping is the identity, avoiding additional camera
  transform rounding. No intermediate annotation recording pass is needed.

The layer reuses the existing world-span/stack planning and bounded label-value
cache. Selection overlays use the original ownership, invalidity, colors and
short-span policy. Adaptive unit changes rebuild the appropriate label paths.
Changes to geometry, selection, unit mode, precision, line widths, font, theme,
DPI or display scaling replace the affected preparation. Cold complete paints
and culled zoom paints preserve the original visibility policies separately.

Only one native layer is retained, with a maximum of 2,048 dimension records.
Manual/angle guides, live edits, panning, unsupported paint devices/DPI and larger
layers use the original annotation painter. PNG/SVG export always uses that
original path. No annotations are dropped when the optimization is ineligible.

The same saved 404-object camera and 16-step alternating benchmark measured
52.30 ms/frame with the previous dimension painter and 40.86 ms/frame with the
integrated layer: about 22% less total frame time. At 150% display scaling a
separate run measured 69.77 versus 60.71 ms. These remain synchronous viewport
render/grab measurements, not measured input latency or a general 60 FPS claim.

All seven recovery-scene image comparisons matched exactly at 100% and 150%
display scaling. `check_retained_dimensions.py` compares complete editor pixels
against the previous painter across all/exterior/stacked dimensions, both wall
references, fractional camera positions, adaptive thresholds, every unit mode,
precision, selections, line widths, theme/alpha/font changes and in-place edits.
It also checks pan/edit/guide/export handoffs and cache ownership reuse. Focused
checks run at 125%, 150% and 200% scaling with render-revision verification.
Undo/redo, project replacement and clearing the scene are compared against the
previous painter too. Empty scenes and inactive annotations release the native
layer rather than keeping the old project's graphics items alive.

Existing formatting checks now observe retained glyph preparation as well as
immediate text painting. The previous batch-recording check still exercises the
legacy painter used by export and fallback; its assertions were not relaxed.

Reproduce the integrated comparison using the same benchmark harness:

```powershell
python tools/retained_editor_probe.py --integrated --parity
$env:QT_SCALE_FACTOR = '1.5'
python tools/retained_editor_probe.py --integrated --parity
```

The `--integrated` option compares the actual application implementation against
its previous painter in scoped substitutions. Historical prototype options still
use that previous painter as their baseline. Results use the `integrated` suffix
in `diagnostics/`; the seven comparisons assert that temporary substitutions
restore the application's renderer and reproduce the reference frame exactly.

## Drag validation and railing geometry — 30 October 2026

Paint-time architectural validation now prepares blocker categories once and
uses conservative joined bounds to select local collision candidates. The
existing exact predicates, source ordering, hidden-object blocking and collision
settings remain authoritative. An unchanged paint snapshot reuses its validity
results during gestures too. After a geometry change, clear stationary objects
retain their results; objects with possible colliders invalidate conservatively
against the global geometry revision. Openings retain global invalidation for
host fitting, sibling intervals and distant reserved-door support. Candidate
indices exist only within a read-only validation scope and are released even
when validation raises an exception.

Railing posts now use spatial buckets for first-match deduplication, preserving
the native 0.01 mm contact test and the widest-post ownership rule. Cardinal
railing collections combine their post fills in one native boolean operation.
Oblique collections retain the original boolean-operation sequence: batching
those operations produced different antialiased edge pixels during evaluation.
Their post lookup improves, but large oblique symbol rebuilds remain expensive.

`tools/benchmark_drag_validation_railings.py` alternates frozen pre-change and
current methods in the same process. It discards one warmup and reports medians
of five samples. The final run used Windows 10, Python 3.14.3 and Qt 6.11.2:

| Synthetic workload | Before | After |
| --- | ---: | ---: |
| Architectural validation, 128 walls | 1.91 ms | 0.28 ms |
| Architectural validation, 512 walls | 24.08 ms | 1.14 ms |
| Architectural validation, 1,024 walls | 86.58 ms | 2.20 ms |
| Drag paint, 1,024 walls | 144.75 ms | 62.40 ms |
| Drag paint, 512 walls and 32 counters | 216.79 ms | 45.00 ms |
| Cardinal railing rebuild, 256 posts | 179.77 ms | 5.07 ms |
| Cardinal railing rebuild, 512 posts | 902.67 ms | 10.29 ms |
| Oblique railing rebuild, 512 posts at 37 degrees | 1,971.86 ms | 1,870.33 ms |

Drag paints change one wall endpoint each frame in an offscreen 1200 by 800
viewport, with measurements and tips disabled and most geometry outside the
viewport. Railing probes change the run length while retaining the post count.
These measurements are isolated workload costs, not end-to-end pointer latency,
general frame-rate promises or additive savings. Raw samples and environment
details are in `diagnostics/performance-hotspots-20261030/benchmark-final.json`.

`check_drag_validation_railings.py` compares validity with the frozen original
methods through local edits, blocker/visibility/settings changes, host changes,
reserved doors and randomized mixed scenes. It asserts one revalidation for a
clear local wall edit and none for unchanged snapshots, including a mixed scene
with distant blockers. Exact editor frame comparisons and 100 railing pixel
matrices cover cardinal/oblique runs, overlaps, shared posts, tolerance edges,
fractional zoom/DPR and SVG replay. Existing collision, movement, rotation,
recovery, pan, architectural rendering and export checks remain unchanged.

## Containment and picking follow-up — 30 October 2026

This pass uses the preceding drag-validation/railing implementation as its
baseline. It removes repeated work from three paths:

- Complete-scene containment queries can return from a revision key before
  walking footprints. Explicit subsets retain value-based validation. Large
  sparse scenes (at least 2,048 eligible objects) use ordered spatial candidates
  around each footprint's center before the unchanged Qt bounds and polygon
  containment predicates. Smaller/dense scenes retain the existing scalar or
  blockwise NumPy filters; their recomputation is not claimed to improve.
- Picking retains one scene snapshot containing source order, vertex indices
  and conservative body bounds. World-space data survives camera navigation;
  camera-dependent joined paths and guide-label bounds refresh independently.
  Endpoint hits return before constructing the body index. Exact native hit
  predicates and priority rules remain in place, including selected objects,
  contained objects, annotations, columns, window wells and joined corners.
- Architectural advisories and furnishing occlusion share one coincident-object
  grouping per scene preparation, avoiding a second complete encoding pass.

Point assignments now compare exact coordinates when notifying scene revisions.
Qt's fuzzy QPointF equality can otherwise hide a representable edit at large
world coordinates and leave revision-keyed rendering or picking stale. The
regression includes an assignment of approximately 0.02 mm at a 1e11 mm origin.
Picking snapshots are discarded on scene replacement; no historical sequence
of picking indices or paths is retained.

`tools/benchmark_containment_hover.py` alternates the frozen and current methods
in the same process. It discards one warmup and reports medians of five samples.
The final Windows/Python 3.14.3/Qt 6.11.2 run measured:

| Synthetic workload | Before | After |
| --- | ---: | ---: |
| Warm complete-scene containment, 1,024 walls | 4.810 ms | 0.003 ms |
| Sparse containment recomputation, 2,048 walls | 26.71 ms | 18.11 ms |
| Sparse containment recomputation, 4,096 walls | 62.93 ms | 42.01 ms |
| Warm picking in empty space inside a 1,024-wall plan | 12.649 ms | 0.037 ms |
| Cold endpoint picking, 1,024 walls | 5.35 ms | 3.56 ms |
| Hover paint, 1,024 walls | 16.05 ms | 7.51 ms |
| Zoom paint, 1,024 walls | 17.79 ms | 16.54 ms |
| Drag paint, 1,024 walls | 60.60 ms | 57.15 ms |

Paints use an offscreen 1200 by 800 viewport with measurements/tips disabled and
most objects offscreen. Warm picking samples average ten distinct queries;
warm containment samples average 100 calls. Cold queries invalidate the picking
snapshot. Drag samples change one wall endpoint; zoom samples change the camera.
These are isolated workload measurements, not end-to-end input latency or a
general frame-rate guarantee. Full raw samples, including smaller, dense and
coincident cases, are in
`diagnostics/performance-next-20261030/benchmark-final.json`. Drag paint gains
are modest and varied between runs; this pass's main gains are picking, hover
painting and large sparse containment. Room-boundary preparation remains a
significant drag cost.

`check_containment_hover_preparation.py` compares 6,832 picking queries against
the frozen pre-pass implementation, exercises every object type, and compares
exact editor frames. It covers zero-width objects, tolerance edges, precision
and line-width changes, hidden objects, collapsed openings, camera reuse,
large-coordinate assignment, and snapshot release. Sparse/dense containment
also matches the frozen NumPy method, while `check_numpy_containment.py` retains
its independent frozen scalar comparisons. Picking and pixel checks pass at
125% and 200% display scaling, alongside the existing interaction, rendering,
duplicate-repair, history/revision and export checks.

### Connected discovery and opening jambs follow-up (2026-10-30)

This pass addresses findings 5 and 7 using the implementation after the
containment/hover pass as its baseline. It preserves ordered discovery and the
existing exact contact and jamb-protection predicates.

- Connected discovery uses conservative stroked-path bounds to query nearby
  candidates in source order before native path intersection. Endpoint-only
  objects use endpoint buckets and no longer construct unused shape paths.
  Small candidate sets keep the original sweep. Nonfinite geometry falls back
  to the sweep. A 512-wall straight chain performs 511 exact path contact tests
  instead of 130,816. Shape paths are still prepared eagerly; dense or unusually
  large overlapping bounds can still produce quadratic candidate work.
- Opening jamb protection queries an ordered spatial index of expanded wall
  footprints, retaining the original bounds, polygon, tolerance and offset
  tests. Index setup occurs only for at least 32 walls and four openings after
  linear probes have already inspected at least one wall-list's worth of
  candidates. This avoids setup for single openings and cheap early matches.
  The index belongs to the existing prepared-scene lifetime. Sparse queries
  replace the openings-times-walls scan with one wall-index build and local
  candidates; densely occupied buckets can still approach the original cost.

`tools/benchmark_connections_openings.py` alternates frozen/current views,
discards one warmup and reports medians of five samples. Windows/Python 3.14.3/
Qt 6.11.2 results:

| Synthetic workload | Before | After |
| --- | ---: | ---: |
| Connected discovery, 128-wall chain | 5.90 ms | 4.02 ms |
| Connected discovery, 512-wall chain | 65.34 ms | 16.06 ms |
| Connected discovery, 1,024-wall chain | 248.06 ms | 35.04 ms |
| Connected discovery, 1,024 measurement guides | 498.62 ms | 8.32 ms |
| Drag paint, 128 walls / 16 openings | 25.03 ms | 14.41 ms |
| Drag paint, 512 walls / 1 opening | 46.87 ms | 48.61 ms |
| Drag paint, 512 walls / 4 openings | 65.55 ms | 58.41 ms |
| Drag paint, 512 walls / 32 openings | 158.01 ms | 59.88 ms |
| Drag paint, 512 walls / 64 openings | 264.64 ms | 51.65 ms |
| Drag paint, 1,024 walls / 64 openings | 582.19 ms | 115.63 ms |

Discovery includes path preparation, index construction and traversal. Paints
use a 1200 by 800 offscreen viewport, measurements/tips disabled, most objects
offscreen and one changed wall endpoint per sample. These synthetic timings
are not end-to-end pointer latency or a frame-rate guarantee. No improvement
is demonstrated for the single-opening case; smaller differences are noisy.
Raw samples and exact contact counts are in
`diagnostics/performance-connections-openings-20261030/benchmark-final.json`.
Room-boundary preparation remains unchanged and can still dominate other scenes.

All 36 focused checks passed. The new frozen-reference regression also passed
after its final expansion and at 125% and 200% display scaling. It compares
ordered attachment results across structural objects, furnishings, compound
gaps and annotations; endpoint tolerance boundaries, far-origin coordinates,
nonfinite fallback and dense endpoints; and exact raster/SVG jamb output across
24 scenes with varied opening types, hidden walls, zoom, line widths, opacity
and device ratios. Existing movement, rotation, grouping, clipping, cache and
export checks also passed. All 72 help files match their pre-pass SHA-256 hashes.

### Room-boundary preparation follow-up (2026-10-30)

Profiling after the connected-discovery/jamb pass identified component-bound
merging in `GeometryMixin.ConnectedWallPath` as a major room-scene edit cost.
The previous horizontal sweep processed every owned body/junction rectangle.
Rectangles from distant rows stayed active together, and several pieces of
the same component repeatedly participated in the sweep. Existing stationary
component paths were reused, but this complete bounds pass still ran after
every wall geometry edit.

The new broad phase indexes one envelope per endpoint-connected component.
Only components with overlapping envelopes proceed to the original exact
QRectF intersection tests on their owned pieces. An envelope alone never
establishes a connection: gaps and nested envelopes keep the previous result.
Components and member walls retain their original source order, so contour,
ownership and material assembly consume the same ordered inputs. A single
component bypasses merging entirely. Indexing is restricted to at least 32
components with more than two owned pieces per component on average; simple
isolated walls, smaller sets and nonfinite bounds keep the original sweep.

For 128 disjoint rectangular rooms (512 walls), one changed endpoint previously
caused 106,316 QRectF intersection calls during room preparation. The new pass
made zero: the spatial index rejected the disjoint component envelopes.
This count includes wall preparation and room classification and is recorded
separately from unprofiled timing measurements in
`diagnostics/performance-room-edits-20261030/comparison-counts.json`.

For sparse component neighborhoods, the new pass builds envelopes in O(P),
selects a cell size in O(C log C), then indexes and queries C components rather
than sweeping P owned pieces against one another. Here P is the number of
pieces and C the number of components. Index bucket expansion is capped by the
existing large-entry fallback. Dense or very large overlapping envelopes can
still require quadratic candidate work and expensive exact piece comparisons.
The index and envelope lists are temporary; no additional geometry history is
retained. Existing caches still retain unchanged native component paths; the
regression verifies that editing one of 128 disconnected rooms rebuilds only
that component.

`tools/benchmark_room_edits.py` alternates frozen/current implementations in
one process, discards one warmup and takes medians of five samples. The final
Windows/Python 3.14.3/Qt 6.11.2 run measured:

| Synthetic workload | Before | After |
| --- | ---: | ---: |
| Room preparation, 512 walls / 128 rectangular rooms | 50.54 ms | 21.47 ms |
| Room preparation, 1,024 walls / 256 rectangular rooms | 177.64 ms | 35.25 ms |
| Endpoint drag paint, 256 walls / 64 rooms | 38.44 ms | 28.97 ms |
| Endpoint drag paint, 512 walls / 128 rooms | 86.26 ms | 58.85 ms |
| Endpoint drag paint, 1,024 walls / 256 rooms | 301.88 ms | 167.75 ms |
| Whole-wall drag paint, 512 walls / 128 rooms | 67.06 ms | 36.05 ms |
| Whole-wall drag paint, 1,024 walls / 256 rooms | 217.56 ms | 68.19 ms |

Preparation includes wall geometry and room classification. Paints use a
1200 by 800 offscreen viewport, measurements/tips disabled and most geometry
offscreen. Each sample changes actual wall geometry. Endpoint paints use the
existing endpoint edit cache; whole-wall paints retain direct rendering. These
are isolated synchronous redraw times, excluding input handling and snapping.
They do not establish end-to-end latency or a general frame-rate guarantee.
Smaller/simple-wall scenes, connected chains and the crossed-wall grid showed
no consistent improvement; raw samples include slower medians as well as faster
ones. Full samples are in
`diagnostics/performance-room-edits-20261030/benchmark-final.json`.

A trial enabling the edit raster cache for whole-wall drags slowed some smaller
scenes and was removed. The edit-cache source remains byte-identical to its
pre-pass snapshot. This pass optimizes geometry preparation for transformations;
it does not expand raster eligibility or incrementally classify room topology.

All 36 distinct focused/integration checks passed, with the expanded regression
also passing at 100%, 125% and 200% display scaling. Frozen-reference comparisons
cover exact wall paths and owned polygons, component order, room paths/areas,
editor pixels and raster/SVG output; live endpoint edits, whole-wall moves,
rotation, hidden objects, previews through existing checks, tolerance boundaries,
far-origin geometry, nested and overlapping component envelopes, empty scenes,
and stationary component reuse. Movement, measurements, clipping, materials,
render caches and export integration checks passed. All 72 help files retain
their pre-pass SHA-256 hashes.

### Synchronous properties refresh follow-up (2026-10-30)

Profiling confirmed that a normal `RefreshProperties` called `EnsureObjectIds`
twice. Each call scanned every scene collection and rebuilt/reassigned stair
links and sizing metadata, even when only a selected object's position or size
had changed. Point selections additionally constructed a QLineF for every
same-type endpoint while checking chamfer eligibility. In the 1,024-wall probe,
30 refreshes performed 60 complete metadata passes.

The panel now requests reusable metadata once. Its key contains scene
membership, a dedicated metadata revision, and the effective stair/railing
sizing limits. ID assignments/resets, sizing-bound assignments and stair-link
replacement advance that revision; topology and unit/settings changes are also
covered. Geometry-only edits reuse the completed metadata preparation without
walking the scene or allocating another stair list. Explicit `EnsureObjectIds`
calls still perform a full repair by default, and captured/deleted states always
bypass reuse. This preserves insertion/history ID reservation and provides the
existing repair path for untracked in-place mutations of internal derived lists.

Chamfer eligibility rejects distant endpoint coordinates before constructing
QLineF objects, retaining the original native distance predicate for nearby
endpoints and the original ray/junction rules. A warm 1,024-wall vertex refresh
made 2 native QLineF length calls instead of 2,049, recorded separately in
`diagnostics/performance-properties-20261030/operation-counts.json`.
The scan itself remains O(W) per distinct selected joint; it has not become an
indexed or incremental neighborhood query.

No signal connections, timers, refresh frequency or render paths changed.
Selection/property updates remain synchronous. The metadata cache hit costs
O(1) in scene size; metadata rebuilds retain the original O(N) scene work plus
history-ID checks when IDs need assignment. Control setup, unit conversion,
mixed-value calculation and layout updates still run on each refresh. The new
retained state is a numeric policy/revision key; it retains no historical scene
objects or widget snapshots.

`tools/benchmark_property_refresh.py` uses one isolated main window and
alternates frozen/current handlers on the actual `selectionChanged` signal.
The frozen baseline includes the previous property/metadata methods and model
assignment notifications. Every update changes selected geometry. It discards
one warmup batch and reports medians of seven batches, each averaging 20
updates. Windows/Python 3.14.3/Qt 6.11.2 results:

| Synthetic workload | Before | After |
| --- | ---: | ---: |
| Wall properties, 1,024 walls | 1.229 ms | 0.957 ms |
| Vertex properties, 1,024 walls | 2.655 ms | 1.821 ms |
| Furnishing properties, 1,024 background walls | 1.436 ms | 1.095 ms |
| Vertex refresh plus properties-panel paint, 1,024 walls | 3.463 ms | 2.137 ms |
| Wall properties, 4,096 walls | 2.085 ms | 1.018 ms |
| Vertex properties, 4,096 walls | 7.773 ms | 2.752 ms |
| Furnishing properties, 4,096 background walls | 2.228 ms | 1.039 ms |
| Railing refresh plus properties-panel paint, 1,024 walls | 2.376 ms | 2.478 ms |

These isolate synchronous refresh work, with panel rendering measured separately.
They exclude viewport painting, pointer-event processing and snapping, and are
not end-to-end dragging latency. Smaller scenes showed modest/mixed changes;
the 128-wall furnishing case was 1.250 versus 1.360 ms. Panel painting remains
variable, and the railing panel case above demonstrates no improvement. Raw
samples for every scene/type combination are in
`diagnostics/performance-properties-20261030/benchmark-final.json`.

All 32 distinct focused/integration checks passed. The new frozen-reference
regression covers every object type, single/mixed selections, metric/imperial
units, visible control values/ranges/flags and exact panel/editor pixels. It
verifies immediate live values without event-loop delay; membership, ID,
sizing-policy and derived-link invalidation; captured/deleted object IDs;
bulk/reference-image early returns; and chamfer tolerance boundaries at large
coordinates. Exact comparisons also pass at 125% and 200% display scaling.
Existing property editing, expressions, resizing/rotation, stair sizing,
history/clipboard/recovery, scene caches and export checks passed. All 72 help
files retain their pre-pass SHA-256 hashes.

### Snapping preparation follow-up (2026-10-30)

The next profile confirmed repeated preparation during every movement update:
control/footprint/midpoint collectors each filtered scene visibility, numeric
targets were rebuilt, and movement snapping sorted new point/ray indices. Edge
resize snapping additionally ran three complete constrained target sweeps before
the arbitrary edge-contact pass. This pass keeps the same target order, exact
snap predicates, priorities, native movement distance metric and guide ties.

- The three collectors share one ordered visible-object tuple, keyed by scene
  membership, hidden-object revision and class visibility settings. Geometry
  changes do not invalidate visibility. Moving-object, moving-vertex, opening-
  parent, group and handle exclusions are still evaluated by each collector.
- One numeric snapshot retains the complete ordered `(x, y, direct)` values.
  Every query still collects and compares actual values, so caller-owned target
  mutations and stationary-object edits cannot leave stale lookup data. Point
  and ray indices are built lazily for more than 32 targets and reused when
  those values match. Query-specific scale, grid, range, anchor and direction
  remain current; switching Ctrl or snapping policies keeps the existing rules.
- Resize point probes use the existing prepared ray-query implementation,
  preserving its source-order and alignment-axis tie handling. Small target
  sets and nonfinite/unsupported ray inputs keep the full-sweep fallback. The
  arbitrary edge-contact pass remains unchanged.
- Replacing scene collections clears both new snapshots. There is one visible
  object tuple and one numeric target snapshot per viewport, with at most one
  point index and one ray preparation for that snapshot. Additional retained
  storage is O(N + T), with no history of gesture/target variants.

In a separate profiled count of ten warm movement queries with 1,024 stationary
walls, point-index preparation fell from ten calls to zero and visibility
checks from 30,750 to zero. Ten constrained queries likewise avoided all ten
ray-index rebuilds and their internal point-index preparation. The moving
furnishing's geometry changed each query. Counts are recorded independently of
timings in `diagnostics/performance-snapping-20261030/operation-counts.json`.

The warm path still performs O(N + T) collection/value checking. It avoids
repeated O(T log T) index construction, then uses the existing spatial queries.
Query work depends on candidate density and source-order sorting; dense aligned
targets can still approach full-sweep costs. Resize edge contacts still scan T
targets. The world footprint value key is still constructed, and edits to
stationary target geometry can still require expensive footprint rebuilding.
This is not constant-time snapping or a complete incremental target model.

`tools/benchmark_snapping_preparation.py` alternates frozen/current viewports,
discards one warmup and reports medians of five samples, each averaging five
queries. It includes footprint/control/midpoint collection, numeric conversion,
lookup construction and snap queries. Windows/Python 3.14.3/Qt 6.11.2 results:

| Synthetic workload | Before | After |
| --- | ---: | ---: |
| Movement, 16 stationary walls | 0.163 ms | 0.097 ms |
| Movement, 128 stationary walls | 1.329 ms | 0.787 ms |
| Movement, 512 stationary walls | 4.472 ms | 2.199 ms |
| Movement, 1,024 stationary walls | 10.083 ms | 4.353 ms |
| Constrained movement, 1,024 stationary walls | 11.674 ms | 5.297 ms |
| Edge resize, 1,024 stationary walls | 15.862 ms | 3.777 ms |
| Proportional corner resize, 1,024 stationary walls | 9.819 ms | 3.005 ms |
| Movement with 64 anchors, 1,024 stationary walls | 9.263 ms | 4.938 ms |
| Dense alignment targets, 1,024 stationary walls | 18.183 ms | 13.147 ms |
| Movement with a changed stationary wall each query | 62.671 ms | 58.881 ms |

The moving furnishing changes geometry each query; target geometry stays fixed
except in the final row, which also has 1,024 walls. These isolate snapping and
exclude pointer-event processing, properties refresh, collision validation and
viewport painting. They do not measure complete dragging latency or establish
a frame-rate guarantee. The stationary-edit case shows only a modest gain;
geometry rebuilding dominates it. Full samples are in
`diagnostics/performance-snapping-20261030/benchmark-final.json`.

All 38 distinct focused/integration checks passed. The new frozen-reference
regression compares 2,400 resize matrices, 400 movement matrices and 120 desktop
cases, including source order/duplicates, large coordinates, strict thresholds,
nonfinite fallback, mixed object types, units, modifiers, policy changes and
moving-object exclusions. It verifies mutable caller-target invalidation, lazy
index reuse, visibility/membership changes, disabled paths and scene replacement.
Exact editor frames also match at 125% and 200% display scaling. Existing real
drag/resize/group gestures, constraints, snapping options, rendering, properties,
room/cache and export checks passed. All 72 help files retain their pre-pass
SHA-256 hashes.

### Drag rollback and opening fitting follow-up (2026-10-30)

Profiling after the snapping pass confirmed that ordinary wall previews captured
the entire scene on every update, including furnishing/label QPointF copies and
wall metadata that their rollback never read. Group setup similarly captured a
complete scene just to obtain opening states. Opening fitting rebuilt baseline
maps and parent grouping, then processed every wall, including empty siblings.

This pass keeps the same fitting/validation and restoration policy:

- Wall-preview rollback captures wall coordinates and the complete opening
  state only. It still restores every wall coordinate and opening state on the
  same failure path. Public/history `CaptureState` remains unchanged.
- Group setup captures opening states directly. Group updates prepare fixed-
  opening maps only when fixed openings exist and reuse the original opening
  baseline tuple when no fixed-opening override is needed. The full group
  restoration pass remains in place, including connection/modifier changes.
- Immutable captured wall/opening tuples reuse their identity-based lookup maps.
  Mutable sequences/rows rebuild those maps. Parent grouping retains scene
  order and duplicate entries, with a key covering tracked membership and the
  current ordered parent identities. Reparenting invalidates grouping even
  without a topology change. Geometry adapters without tracked collections
  rebuild it conservatively. Only walls hosting openings enter the fitting loop.
- Empty opening lists bypass fitting preparation, while the existing scene
  validation still runs whenever requested. Pocket-door support, sibling sorting,
  floating-point summation order, center fitting and validation are unchanged.
  Fitting results themselves are not memoized or skipped for unchanged hosts.

The rollback capture is O(W + O), removing its previous dependency on furnishing
and label count. It still snapshots all wall coordinates, and group restoration
still visits the captured scene. Cold baseline/group preparation costs O(W + O);
warm grouping checks O parent identities and visits H host entries rather than W
walls. Sibling sorting/fitting and reserved-door collision costs remain. Here W
is walls, O openings and H wall entries with openings. One wall baseline map,
one opening baseline map and one current parent grouping are retained, totaling
O(W + O) storage. Scene collection replacement and empty-opening fits clear them;
no history of gesture variants is accumulated.

A separate count of ten warm wall updates with 1,024 walls, 1,024 furnishings,
1,024 labels and 64 doors recorded ten full-scene captures before and zero after.
Sort calls fell from 10,240 to 640 by excluding walls without openings. Counts
are in `diagnostics/performance-drag-fitting-20261030/operation-counts.json`.

`tools/benchmark_drag_fitting.py` alternates frozen/current viewports, discards
one warmup and reports medians of five samples, each averaging five updates.
The final Windows/Python 3.14.3/Qt 6.11.2 run measured the following. Every row
below uses 1,024 walls, 1,024 furnishings, 1,024 labels and 64 doors:

| Synthetic workload | Before | After |
| --- | ---: | ---: |
| Wall drag update, snapping disabled | 4.236 ms | 0.864 ms |
| Wall drag update, snapping enabled | 36.263 ms | 32.609 ms |
| Two-object group update, snapping disabled | 3.824 ms | 3.058 ms |
| Opening fitting only, one changed wall endpoint | 1.011 ms | 0.357 ms |
| Two-object group setup | 4.312 ms | 0.040 ms |

Connections are disabled in these benchmarks. Wall/group update probes execute
the real `UpdateInteraction`; separate fit probes change one wall endpoint and
retain an immutable baseline. Painting, properties refresh and release/commit
validation are excluded, so these are not complete dragging/display latency.
The snapping-enabled case shows a much smaller total gain because target work
dominates. Dense-opening fits and small-group updates also improve more modestly;
with 512 doors, fitting alone was 3.145 versus 2.638 ms. Large group restoration
and affected-object-only rollback remain follow-up opportunities. Full samples,
including smaller scenes and no-opening cases, are in
`diagnostics/performance-drag-fitting-20261030/benchmark-final.json`.

All 37 distinct focused/integration checks passed. The new frozen-reference
regression compares 320 complete drag frames and exact editor pixels, covering
rollback, connection and snapping changes, ordinary/reserved openings, parent
reassignment, membership/order changes, duplicate entries, mutable baselines,
untracked geometry adapters and requested validation with no openings. It also
asserts that wall previews and group setup no longer capture unrelated full-scene
state. Exact comparisons pass at 125% and 200% display scaling. Existing reserved
door, group/copy/transfer, collapsed-wall, fitting, history, snapping, properties,
render/cache and export checks passed. All 72 help files retain their pre-pass
SHA-256 hashes.

## Column occlusion preparation (2026-10-30)

Column assembly rebuilt every mapped curve and collision polygon whenever any
wall changed. Its per-column occluder scan recomputed both path bounds for every
pair, even for disjoint columns. A second, independent cost was the sequential
Qt exterior union: a growing combined bounding rectangle can intersect a column
that does not touch any earlier column, triggering expensive native booleans.

This pass preserves the original assembly and rendering rules:

- Cache mapped native column curves, polygons, bounds and the ordered winding
  fill separately from regular-wall geometry. Only changed column records rebuild
  their curve/polygon. Geometry keys still cover scale, ordered identities,
  endpoints, widths and miter settings; camera motion retains the existing final
  transform. Duplicate entries and material ownership retain source order.
- For at least 32 columns with finite bounds, use the existing ordered spatial
  index to find occluder candidates, then apply the original rectangle predicate.
  Smaller/nonfinite inputs retain the ordered scan. Native curves, intersection
  semantics, winding and per-column occluder order are unchanged.
- Retain one adaptive exterior checkpoint immediately before the first changed
  column. Reuse it only when the complete regular-wall key, scale and ordered
  prefix match. Continue the original sequence of bounding tests and native
  unions from that point. The checkpoint holds at most 32,768 path elements;
  larger paths fall back to a complete rebuild. No unions are regrouped, and no
  bounding-rectangle false positives are skipped: either can change native curve
  flattening and measurement geometry. This helps later columns most; changing
  regular walls or the first column still requires the original union sequence.
- Give public drawing results independent Qt wrappers while retaining the prior
  material/outline aliasing. Mutating a public path or polygon cannot corrupt
  retained preparation. Regular-only picking/collision scratch queries retain
  valid private preparation; topology/column-preview context changes invalidate
  it on such queries. Wall-list replacement releases both caches immediately.

The geometry-key scan remains O(W + C). Cold or changed-column preparation builds
an O(C log C) median sort and the spatial index; unchanged columns reuse that
preparation. Ordered queries sort their candidate sets, so their cost depends on
bucket occupancy and geometric density. Dense/large bounds can still require
quadratic pair work, and overlapping scenes retain quadratic occluder output.
The exterior union and growing-path bounds have their original native costs
except where the prefix can be reused. Retained storage is O(C + P), where P is
the cached polygon/curve data, plus the bounded checkpoint. There is no retained
pair matrix, neighborhood-path cache or history of gesture variants.

A separate profile of five warm rebuilds with 512 disjoint columns recorded:

| Python-visible work across five updates | Before | After wall edits | After final-column edits |
| --- | ---: | ---: | ---: |
| Column curve factories | 2,560 | 0 | 5 |
| Column polygon factories | 2,560 | 0 | 5 |
| QPainterPath boundingRect calls | 2,621,440 | 2,560 | 10 |
| QRectF intersects calls | 1,310,720 | 2,560 | 5 |

These are call counts, excluding operations internal to native Qt methods.
`diagnostics/performance-column-occlusion-20261030/operation-counts.json` retains
the complete counts. Timing below comes from a separate unprofiled run of
`tools/benchmark_column_occlusion.py`, using Windows/Python 3.14.3/Qt 6.11.2:

| Synthetic workload | Before | After |
| --- | ---: | ---: |
| 512-column sparse row, regular-wall edit preparation | 316.909 ms | 14.971 ms |
| 512-column sparse row, final-column edit preparation | 303.943 ms | 5.181 ms |
| 512-column sparse row, middle-column edit preparation | 281.895 ms | 14.217 ms |
| 512-column sparse row, regular-wall edit redraw | 357.421 ms | 84.485 ms |
| 512-column sparse row, final-column edit redraw | 355.167 ms | 79.245 ms |
| 64-column grid, regular-wall edit preparation, repeat run | 222.827 ms | 218.726 ms |
| 64-column grid, final-column edit preparation, repeat run | 209.266 ms | 8.887 ms |
| 64-column grid, first-column edit preparation, repeat run | 216.000 ms | 204.539 ms |
| 64-column grid, middle-column edit preparation, repeat run | 207.887 ms | 164.250 ms |

Each sample edits one real endpoint. Frozen/current variants alternate, discard
one warmup and report the median of five samples. Grid rows use a separate
15-sample repeat because the initial first-column result was slower (205.851
versus 240.814 ms); the repeat measured 216.000 versus 204.539 ms. That case and
grid regular-wall edits remain dominated by sequential native unions, with no
reliable large improvement demonstrated. The checkpoint first adapts on a changed
column; reported warm medians do not represent cold-build latency. Full samples,
including smaller scenes and dense overlaps, are in
`diagnostics/performance-column-occlusion-20261030/benchmark-final.json` and
`benchmark-grid-repeat.json` in the same directory.

Preparation includes regular walls, column shapes, occluders and exterior unions.
Redraws use 1200 x 800 offscreen QWidget.render calls in active drag state, with
measurements/tips disabled and most columns offscreen. The frozen method also
applies to geometry workspaces. Pointer handling, properties and display latency
are excluded; these are synthetic workload results, not complete frame timings
for every column layout.

All 36 distinct focused/integration checks passed. Final cache-context changes
also passed six relevant integration checks and the native regression at 125%
and 200% scaling. The new frozen-reference regression compares 70 native-path
matrices plus order/scale changes, adaptive middle-column edits and scratch
queries. It checks exact element types and floating-point coordinates, owned
polygons, material paths and occluder order; exact raster/SVG/editor images;
selective reuse, mutable-result isolation, cleanup and checkpoint-budget fallback.
Fixtures include threshold boundaries, sparse/dense/touching geometry, rotated
columns, zero widths, duplicate owners, mixed pillars/openings and large origins.
All 72 help files retain their pre-pass SHA-256 hashes. Check reports and the
hash verification are retained in the same diagnostics directory.

## Furnishing SVG variants (2026-10-30)

The furnishing renderer uses compensated variants to keep lettering horizontal
and preserve marked details' physical sizes. Every new size/camera key formerly
copied the whole SVG tree, traversed its IDs, serialized all artwork, and parsed
a new native QSvgRenderer. An initial 60-update profile attributed about 202 ms
of a 455 ms rotation-profile total to ElementTree serialization for a 12-lettered-
component compound. Those profiled times include instrumentation overhead and
are not the unprofiled benchmark results below.

This pass retains the existing SVG compensation calculations and native painter:

- A renderer lazily compiles one serialized template with slots for complete
  transform attributes. New variants calculate the original correction matrices
  and join the unchanged bytes with just those attributes. Original attribute
  order/escaping and absent attributes on skipped corrections are retained.
  Markers are checked against source values/text so authored content cannot be
  mistaken for a slot; duplicate IDs retain the original last-ID lookup policy.
- Fixed-detail-only compensation depends on physical dimensions, not camera
  orientation or destination bounds. Those variants now use physical dimensions
  as their key. The native renderer still receives current bounds and painter
  transforms. Lettered/mixed artwork keeps its original complete input key.
- Geometry arithmetic, text anchoring, shrink thresholds, drawing order, clips,
  gradients, opacity, theme/selection mapping and SVG export replay are unchanged.
  In particular, text is not extracted into a later overlay, which could expose
  lettering that was covered by a later SVG element.

For a warmed batch of 48 coffee-table rotations, full tree copies, full XML
serializations and native renderer constructions each fell from 48 to zero.
Physical resizing still constructs 48 native variants, but needs no full tree
copy/serialization. A 48-component mixed compound also retains its 48 native
parses for new lettering transforms while removing the 48 copies/serializations.
The renderer's existing 16-entry LRU limit remains; one template is retained per
renderer, with O(S + D) additional storage for S static SVG bytes and D dynamic
attributes. There is no history of XML trees or additional global variant cache.

For fixed-detail camera changes, variant preparation is a constant-size cache
lookup; native artwork painting still scales with SVG complexity. A new lettered
or resized variant still joins O(S + D) bytes and invokes Qt's native parser.
The optimization removes repeated Python XML traversal and escaping, not the
entire parsing/rasterization cost. Unchanged lettered renders use the same warm
cache path as before, with no reliable performance improvement expected.

`tools/benchmark_furnishing_variants.py` alternates the frozen/current methods
and reports medians of 11 samples, each averaging 48 renders after a discarded
warmup batch. It uses real washer/coffee-table artwork and synthetic compounds
made from those assets. Continuous transforms produce new values throughout
each sequence. The 800 x 600 offscreen QImage timings include compensation,
variant construction and antialiased native drawing, but exclude renderer
initialization, scene traversal, pointer handling, properties and display latency.
These are per-furnishing costs, not full editor frame timings. Separate cold
samples measure the first variant after renderer initialization; separate
profiles count calls outside the timed samples. Full samples and environment
details are in
`diagnostics/performance-furnishing-svg-20261031/benchmark-final.json`.

The final Windows/Python 3.14.3/Qt 6.11.2 run measured:

| Synthetic workload, per furnishing render | Before | After |
| --- | ---: | ---: |
| Washer rotation | 0.788 ms | 0.578 ms |
| Coffee-table rotation, fixed details only | 0.989 ms | 0.545 ms |
| Coffee-table zoom, fixed details only | 0.999 ms | 0.597 ms |
| Mixed 12-component compound rotation | 4.378 ms | 2.860 ms |
| Mixed 48-component compound zoom | 17.556 ms | 10.508 ms |
| Mixed 48-component compound resize | 17.756 ms | 10.423 ms |
| Unchanged 48-component compound | 2.584 ms | 2.589 ms |
| First variant, 48-component compound | 14.583 ms | 16.463 ms |

The cold-template cost is a tradeoff: the first compound variant is about 1.88 ms
slower in this run; subsequent transform updates avoid that setup. Smaller cold
cases were 0.742 versus 0.734 ms for the washer and 0.938 versus 0.995 ms for the
coffee table. The 12-component cold case was 4.439 versus 5.754 ms. Stationary
renders show no consistent improvement. No end-to-end editor gain is inferred
by multiplying these isolated timings by scene object count.

All 30 distinct focused checks passed, including furnishing rendering, font/theme
changes, compound/fixed-size geometry, flipping, clipping, backgrounds, selection,
hit testing, resize/rotation handles and PNG/SVG exports. The new frozen-reference
regression passes 270 exact raster/SVG comparisons, and checks newly generated
variant bytes against the original serialization. It covers continuous transforms,
LRU eviction/revisits, nested/rotated compounds, shear/reflection, duplicate IDs,
marker collisions, text occlusion, degenerate sizes and physical-size changes.
It also asserts no warm tree serialization and one native variant for 25
fixed-detail camera frames. The regression passes at 125% and 200% scaling too.
Final template-marker changes were rechecked with preparation/font integration.
This pass made no help-file edits. The final hash check detected changes to
`help/export.md` and `help/projects.md` during the run; those changes were left
intact. Check reports and the observed hash differences are in the same diagnostics
directory.

## Catalog search and thumbnail loading (2026-10-31)

The built-in catalog has 249 definitions including the hidden null entry. Quick
search created 248 result rows and requested every thumbnail before its first
paint. List mode requested each thumbnail twice: once while building rows and
again in RefreshIcons. Cache hits still intentionally read file contents to catch
external artwork edits with unchanged file sizes/timestamps. Search also rebuilt
normalized field phrases, word/alias sets and per-query phrases on every call.

This pass keeps the original matching, ranking and painting rules:

- A 4,096-entry LRU retains immutable search-field values keyed by the current
  name, keyword tuple and category tuple. No catalog dictionaries or mutable
  keyword/category lists are retained. In-place edits immediately use new keys;
  width/length matching and sorting still read current definitions. Query token
  normalization, phrases and name-synonym phrases are prepared once per query.
- Popup/list rows request their thumbnail through the decoration data role, on
  painting or explicit icon access. Hidden rows no longer render/read icons
  eagerly. A realized row retains its QIcon until the existing refresh/rebuild
  paths invalidate it. Theme refresh clears row thumbnails without realizing
  offscreen entries. Shared rendering, category headings, dimensions, tooltips,
  selection/hover painting, list ordering and placement behavior are unchanged.
- FurnishingThumbnailCache itself is unchanged. Content checking still catches
  same-size file edits with restored modification timestamps; paint/font/size
  dependencies, icon budgets and content sharing retain their existing policy.
  Grid views retain their existing lazy delegate path and content checks.

Search still scans the catalog and sorts matching results; fuzzy fallback still
constructs/checks its vocabulary. This is not an inverted index or a change to
the matching algorithm. It removes repeated field preparation and per-candidate
query-string allocation. Warm field preparation is O(N) value/key checks; actual
matching depends on query length, words and dimension alternatives. The field
cache is bounded by entry count, with storage proportional to retained text/set
data. It contains no historical model references. Larger working sets can evict
fields and lose reuse; the existing 4,096-entry SearchWords limit can also thrash.

Popup and list row construction, dimension formatting/measurement and row refresh
remain O(R). Thumbnail work is deferred to requested rows rather than R matches.
Scrolling to previously unseen entries still incurs their thumbnail loading
cost; this work has not disappeared. Each row holds its definition, shared cache
and an optional icon, without a reference back to the main window. Clearing rows
releases that preparation. Existing global icon/source budgets are unchanged.

In separate untimed first-paint probes of the complete built-in catalog:

| Work across result preparation and first paint | Before | After |
| --- | ---: | ---: |
| Popup thumbnail requests | 248 | 9 |
| Popup source-file reads | 220 | 8 |
| List thumbnail requests | 496 | 9 |
| List source-file reads | 440 | 9 |

The ninth row is partially visible. A second paint made zero additional thumbnail
requests/file reads in either implementation. These counts include inline/compound
artwork, which does not always need a source-file read. Explicitly requesting an
offscreen row's icon still produces the same usable icon immediately.

`tools/benchmark_catalog.py` alternates frozen/current implementations, discards
one warmup and reports medians of nine samples. Search samples average a batch of
queries in each named group. Larger catalogs replicate real definitions with
distinct names/keys. UI samples include row preparation/layout, thumbnails and a
synchronous first QWidget paint. Cold means a fresh thumbnail cache; normal
shared SVG/font caches and their existing limits remain in effect. The complete
catalog exceeds the 128-entry SVG preparation cache, so eager full-catalog passes
can repeatedly evict preparation. Warm UI samples retain thumbnail caches while
rebuilding rows. List probes explicitly rebuild the result list, representing a
changed result/unit layout rather than the early return for an identical key.

The final Windows/Python 3.14.3/Qt 6.11.2 run measured:

| Workload | Before | After |
| --- | ---: | ---: |
| 249 definitions, warm text search, per query | 1.535 ms | 0.631 ms |
| 249 definitions, fuzzy/no-match search, per query | 2.587 ms | 1.597 ms |
| 249 definitions, dimension search, per query | 1.813 ms | 0.995 ms |
| 4,096 synthetic definitions, warm text search, per query | 60.260 ms | 12.354 ms |
| Complete popup, cold thumbnail cache, first paint | 734.676 ms | 30.302 ms |
| Complete popup, warm thumbnail cache, rebuild and paint | 21.722 ms | 6.855 ms |
| Complete list, cold thumbnail cache, first paint | 795.923 ms | 34.112 ms |
| Complete list, warm thumbnail cache, rebuild and paint | 37.006 ms | 9.355 ms |

The popup shows eight full rows; the list is 420 x 380. Application startup,
window positioning, input dispatch and display latency are excluded. The numbers
are component/workload measurements, not complete interaction latency. Source
loading for future scroll positions is deferred. Full samples, counts and cache
accounting are in `diagnostics/performance-catalog-20261030/benchmark-final.json`.

All 18 distinct focused/integration checks passed. The new frozen regression
compares 456 search matrices, including ordered object identity, aliases, fuzzy
fallback, dimensions, punctuation, duplicate entries and mutable metadata. It
also compares 48 exact popup/list images across themes, units and scroll positions,
asserts bounded caching without retaining definitions, and verifies hidden-row
deferral, icon access, repaint reuse and lazy theme refresh. It passes at 125%
and 200% scaling. Existing search, quick placement/keyboard navigation, list/grid
dragging, categories, sorting, dimensions, user/embedded definitions, thumbnail
invalidation, theme and rendering checks passed. A pre-existing quick-search
test sampled logical widget coordinates as physical image pixels at 125%; the
frozen original failed the same assertion. That assertion now scales its sample
coordinates correctly, and the complete quick-search check passes at 125%.
All 72 help files retain their pre-pass hashes, including the user's prior edits.
Reports and hash verification are in the same diagnostics directory.

## Export-preview submission (2026-10-31)

Preview rendering already runs in a persistent process, but the GUI thread still
builds project snapshots and serializes jobs. The parent encoded the full catalog
and scene as JSON for each dispatched job, converting paths to tagged objects and
binary artwork to base64. A 128-wall probe sent about 1.31 MB before rendering.
Queued raster requests also evaluated their render factories immediately, even
when a later request replaced the same queue slot before dispatch.

This pass preserves the renderer and existing preview-result transport:

- Private preview job files use binary pickle transport, preserving native paths
  and bytes without base64/text conversion. Parent and persistent worker change
  together. Only the owning parent writes these temporary jobs; project files and
  final-export jobs keep their existing JSON formats. The small process command
  and response messages remain JSON. Job files are streamed directly to disk.
- Raster overview/detail callers provide a source-state guard using the same
  complete key they already use for cache invalidation. Their render factory is
  evaluated only when the request reaches dispatch. Replaced/generation-cleared
  requests therefore never encode the scene. If the source key changed before a
  new paint, dispatch drops the obsolete callback and schedules a fresh paint.
- Callers without a guard retain their existing eager snapshot timing, including
  vector/page requests whose arguments are already prepared. FIFO slot order,
  latest-key acceptance and generation cancellation retain their existing rules.
  Deferred-factory failures enter the normal error-result path, and dispatch
  checks ownership after callbacks so cancellation/closing cannot resume an old
  job. Failure chains are handled iteratively rather than recursively starting
  more queued jobs from an error callback.

The valid dispatched snapshot still costs O(N) project encoding. Serialization
still visits the job's scene/catalog graph and writes its bytes, with a lower
constant cost and smaller payload. For M replaced updates to one pending raster
slot, scene encoding falls from M snapshots to one, plus the existing per-update
key/queue work and one dispatch guard. No cross-frame project snapshot cache or
new rendering cache is introduced. One callback/key per queued slot replaces
the full pending snapshot on this path; generation changes and Close release
the closures. Worker scene/result budgets and the single overwritten job file
retain their existing lifetime policy.

`tools/benchmark_preview_submission.py` alternates the frozen/current parent
implementations, discards one warmup and reports medians of nine samples. It uses
real RenderArguments, source keys, the complete 249-entry catalog, and actual
temporary-file writes. QProcess state/stdin writes are stubbed so measurements
exclude worker startup, rendering and result adoption. Prepared-job dispatch
excludes project encoding; a single snapshot includes it. A burst replaces one
pending slot 16 times behind a deliberately busy worker, then dispatches once.
That is a coalescing workload, not a prediction that every 16 input events are
discarded in normal use.

The Windows/Python 3.14.3/Qt 6.11.2 run measured:

| GUI-thread submission workload | Before | After |
| --- | ---: | ---: |
| 128 walls + 32 furnishings, prepared job dispatch | 9.494 ms | 2.083 ms |
| 128 walls + 32 furnishings, snapshot plus dispatch | 10.622 ms | 3.099 ms |
| 1,024 walls + 256 furnishings, snapshot plus dispatch | 11.553 ms | 4.144 ms |
| 4,096 walls + 256 furnishings, prepared job dispatch | 13.632 ms | 3.334 ms |
| 4,096 walls + 256 furnishings, snapshot plus dispatch | 20.635 ms | 10.276 ms |
| 4,096 walls + 256 furnishings, complete 16-request burst | 127.800 ms | 11.141 ms |

The burst invoked its factory 16 times before and once after in every sample.
For the 4,096-wall single snapshot, the job file fell from 2,121,262 bytes to
1,193,230 bytes. Full samples, factory counts and file sizes are in
`diagnostics/performance-preview-20261031/benchmark-final.json`. The initial
profile and smaller workloads are retained there too. These measurements do not
establish complete preview/display latency. The remaining scene snapshot still
runs on the GUI thread; loading completed image/vector results also remains on
that thread and was not optimized or included in these submission timings.

All 26 distinct focused checks passed. The new regression verifies 16-to-1
factory coalescing, the eager API contract for unguarded calls, stale source-key
rejection without an intervening paint, generation cancellation, closure release,
factory failures and callback-triggered closing. Six real-worker PNG/SVG cases
match the legacy JSON-round-tripped arguments exactly, including transparency,
outline styling, sampling and Unicode labels. Existing real-worker tests cover
multiple pages, native/context cache ownership, stale settings, process failure
and restart, transient allocation recovery, live effects and shutdown. Export,
print/cache, appearance and rendering checks passed. Additional real-worker
checks and the new regression pass at 125% and 200% scaling. All 72 help files
retain their pre-pass hashes. Reports and hash verification are in the same
diagnostics directory.

## Native geometry history and optimized PNG lifetime (2026-10-31)

Historical component paths, ownership fragments, boundary paths and component
dimensions now share an LRU budget across a viewport, its child viewports and
geometry workspaces, including opening-placement and collision workspaces.
The existing entry-count limits remain, with additional aggregate limits of
16 MiB estimated storage and 262,144 native points/path elements. A single result
larger than either limit bypasses historical caching; the caller still receives
the complete calculated result. This changes retention and possible rebuild
frequency, not geometry algorithms, object order or drawing commands.

`viewport/geometry_cache.py` estimates Python container/key storage and native
path/polygon storage when inserting immutable results. Hits update LRU order
without rescanning geometry. Large compound keys reuse their calculated hash;
small keys retain ordinary tuple hashing. Dimension entries charge their shared
blocker/cutter tuples once while any entry references them. Weak cache ownership
removes accounting and retained keys when a workspace dies. Project replacement
clears the shared history, root geometry results, prepared member lists and owned
workspaces, and discards the export-overlay snapshot viewport. Opening-placement
polygons and their owner references are cleared too.

The byte estimate is deliberately approximate. Qt implicit sharing can cause
overcounting, and arbitrary model attribute graphs are not traversed. The budget
does not cap process memory: active scene results, raster surfaces and the other
existing numeric/preparation caches have separate lifetimes. Evicting historical
results can make returning to an earlier geometry state more expensive. Work to
weigh a new entry scales with its key/result size; a hit avoids that scan. Shared
dimension inputs avoid repeating the same large accounting traversal per
component. Normal eviction is amortized over insertions; project clearing visits
the retained entries.

`tools/benchmark_geometry_memory.py` runs each memory variant in a fresh process.
Its synthetic fixture retains up to 128 distinct complex histories, each with a
16,385-element native path, 64 owned polygons and model keys. This deliberately
isolates historical retention; it is not a typical drawing or a full-scene memory
benchmark. Windows process counters are recorded alongside tracemalloc because
Python allocation tracking alone misses most native path storage.

| Complex-history fixture | Before | After |
| --- | ---: | ---: |
| Retained history entries | 128 | 15 |
| Native elements/points charged | 2,138,240 | 250,575 |
| Working-set growth | 54.6 MiB | 6.0 MiB |
| Private-byte growth | 70.4 MiB | 7.2 MiB |
| Python bytes retained (tracemalloc) | 2.35 MiB | 0.30 MiB |

The point limit binds first in this fixture. After clearing, both variants return
near their process-memory baseline. A separate real 1,024-isolated-wall endpoint
edit probe alternates frozen/current geometry implementations, discards five
warmup batches and reports medians of 15 samples, each averaging eight edits.
Automatic Python GC is disabled as in the editor. The median changes from
10.836 ms to 10.952 ms per update; this is a memory-retention change with some
bookkeeping cost, not a demonstrated CPU speedup. Samples vary substantially.
Full measurements are in
`diagnostics/performance-memory-gc-20261031/geometry-memory-final.json`.

The collection finding was measured before choosing a policy change. Seven full
GUI-thread idle collections with 69,413 tracked Python objects took 8.29–9.36 ms
and each reported zero reclaimed objects. That idle fixture does not establish
the cost after a large allocation-heavy gesture. The existing gesture deferral,
30-second policy and GUI-thread destruction remain unchanged: the evidence does
not justify changing them. In the original PNG encoder, 512-, 1,024- and
1,536-square image probes spent only 0.52, 1.34 and 2.51 ms respectively across
6, 22 and 48 explicit chunk collections, against total encoding times of 2.85,
3.28 and 7.65 seconds. The existing per-192-KiB chunk collection remains too.
These initial probes are in `profile-gc-before.json` in the same diagnostics
directory; no collection-speed improvement is claimed.

Multipage optimized PNG exports now create one JavaScript engine per export job.
Each page still uses the same UPNG quantization, filtering, native zlib bridge,
pixel transfer chunks and PNG metadata. The encoder drops the page pixel global
and collects JavaScript garbage after success or failure, then closes the engine
in the worker's final cleanup. Encoding and explicit cleanup enforce engine
thread ownership. Single-page exports retain a fresh engine. There is no global
engine pool, cross-job engine retention or vendor-JavaScript change.

`tools/benchmark_png_reuse.py --samples 15` alternates original/current jobs,
discards one warmup job per variant and reports medians. Three distinct 256-square
opaque RGBA flat-color images use the production Math.random quantizer. Timings
include engine initialization, encoding, cleanup and per-page memory sampling;
they exclude scene rendering, image creation and file output. Windows/Python
3.14.3/Qt 6.11.2 results are:

| Optimized PNG workload | Before | After |
| --- | ---: | ---: |
| Single page, fresh engine | 730.519 ms | 735.161 ms |
| Three pages, complete encoding job | 2,143.891 ms | 1,895.635 ms |

The three-page job is about 12% faster in this fixture. Single-page samples
overlap and demonstrate no improvement. Quantization is stochastic, so samples
do not execute identical palette work. Reuse saves script initialization and
retains JavaScript execution state; these timings do not isolate JIT effects or
predict gains for large images dominated by quantization. Initial profiling
measured about 21–22 ms of vendor-script evaluation per new engine.

Engine reuse also has a memory tradeoff. During the three-page probe, sampled
private bytes ranged from 28.3–32.3 MiB before and 36.6–39.4 MiB after; sampled
working set ranged from 47.1–50.7 MiB and 49.1–51.4 MiB respectively. These are
interleaved measurements in one process and include allocator high-water effects;
they do not identify live retained allocation sizes or establish a leak. The
engine is deliberately retained through the job, then released. No PNG memory
reduction is claimed. Full timings, individual page times and process counters
are in `diagnostics/performance-memory-gc-20261031/png-benchmark-final.json`.

The new geometry regression compares 34 native geometry matrices and exact
raster/SVG output against frozen original methods under aggressive eviction,
including rebuilding and returning to evicted states. It verifies aggregate
limits, cross-cache LRU, oversized bypass, shared-input accounting, weak lifetime
cleanup, workspace sharing and project replacement. PNG regressions use equal
random starting states to compare exact encoded bytes, palettes, transparency,
pixels and DPI against the original implementation. They also cover repeated
pages, buffer reset, transfer failure/recovery, thread ownership, explicit engine
release, one engine for a three-page worker job and worker failure cleanup. Fixed
seeds are for parity checks; the final timing benchmark uses the production RNG.

All 27 distinct focused geometry, measurement, column, stair/railing, dragging,
scene/pan, project, export and print checks pass. Two large geometry checks initially
reached the concurrent runner's 30-second limit; serial reruns passed in 17.8 and
20.1 seconds. Those checks now allow 60 seconds on busy machines. Targeted new
regressions also pass at 125% and 200% scaling. The check reports, resolved timeout
history and final hash verification are retained in the same diagnostics
directory. All 72 help files retain their pre-pass hashes, including the user's
prior edits. The GUI collector and PNG vendor bridge remain byte-identical.

## Group restoration and preview GUI follow-ups (2026-10-31)

This pass addresses the two follow-ups identified after the original prioritized
audit: per-movement group rollback and GUI-thread preview preparation/adoption.
It also records fresh complete-window interaction profiles. Existing user edits,
including the help folder, are preserved.

### Group-drag restoration

`SceneChanges` can now collect changed model IDs during a group gesture. Group
preview restoration indexes the captured baseline once and restores affected wall,
furnishing and label rows in their original order. Changes to unselected models
are observed too. Opening restoration keeps its complete original sequence,
including fireplace normalization and parent-derived values. Connection/copy
changes rebuild the preparation; cancellation and release drop the index and stop
tracking. Mutable rows, unfamiliar adapters and large moving selections retain
the original linear restoration path. Copy removal during Shift transitions and
cancellation uses identity sets, reducing O(N*C) membership checks to O(N+C), where
C is the number of copies. This complexity reduction is not a separate measured
copy-cancellation speedup claim.

Captured furnishing/label QPointFs remain mutable. A compact native QDataStream
coordinate signature detects exact baseline changes, including signed zero;
changes trigger a complete restoration. This avoids thousands of Python/native
coordinate calls and float objects on each warm frame. It introduces transient
native polygon/byte buffers proportional to the baseline point count. The index,
point references and one signature live only for the gesture. Point replacement
notifications now observe signed-zero changes as well.

Index construction is O(N). Warm restoration performs an O(F+L) native baseline
coordinate check plus affected-row ordering/restoration, O(D log D), and the
existing complete opening work. Large selections use linear restoration to avoid
sorting most of the scene. Snapping, constraints, fitting, validation and painting
retain their own costs; complete dragging is not O(D).

`tools/benchmark_interaction_followups.py` alternates frozen/current viewports,
discards two warmups and reports medians of nine samples averaging five updates.
Each group scene contains N walls, N furnishings and N labels. Connections and
snapping are disabled for the timing table. Painting/properties are excluded from
the movement-only rows. Automatic Python GC is disabled as in the editor.

| Warm movement workload | Before | After |
| --- | ---: | ---: |
| N=128, two selected objects | 0.406 ms | 0.120 ms |
| N=1,024, two selected objects | 2.910 ms | 0.392 ms |
| N=1,024, 128 selected objects | 4.655 ms | 2.190 ms |
| N=4,096, two selected objects | 11.362 ms | 1.275 ms |
| N=1,024, 1,024 selected objects | 17.003 ms | 17.837 ms |

The last row demonstrates no gain when most moved rows require restoration.
A supplementary first-update probe creates a fresh drag baseline/index for each
sample, excludes capture/setup/painting, discards two warmups and takes nine
samples per variant. Before samples precede after samples in that probe. For
N=1,024/two selected, first movement changes from 3.008 to 5.802 ms; for N=4,096,
12.036 to 23.014 ms. The new preparation has an initial cost that is amortized
over subsequent movements. Raw results and its script are
`diagnostics/performance-followups-20261031/group-first-update.json` and
`probe_first_group.py`.

Synchronous update-plus-widget-render timings remain dominated by painting and
vary materially between runs. The final two-object/N=1,024 sample measured
130.457 to 105.953 ms, while the 128-object selection measured 121.341 to
139.257 ms; those latter sample ranges overlap. Earlier rendered runs varied in
both directions. No general rendering speedup, frame-rate target or measured
input-to-display improvement is claimed from the movement-component gain.

### Preview scene snapshots

Preview RenderArguments can reuse the encoded scene while its observed source
state is unchanged. One cached scene payload plus complete used-definition
signatures is limited to 8 MiB of serialized data. Cached data are bytes and
primitive metadata, with no live scene-model ownership. Every call receives
fresh scene containers; caller changes cannot poison the cache. Final export/save
paths retain fresh encoding. Embedded artwork validation, project settings, view
and UI data still run normally.

Invalidation includes geometry, appearance, topology, visibility and metadata
revisions, hidden membership, extra object metadata and complete nested values of
the definitions actually used by scene furnishings. This covers definitions held
outside the catalog dictionary too. Untracked model/list adapters bypass reuse.
Oversized payloads bypass retention, and project replacement clears it. Checking
metadata/definitions and reconstructing detached containers still costs O(N);
this lowers repeated preparation costs rather than eliminating scene traversal.

The same benchmark measures complete RenderArguments with the full catalog and
fresh current settings, excluding worker rendering/transport/result adoption:

| Preview snapshot workload | Before | After |
| --- | ---: | ---: |
| 128 walls + 32 furnishings, warm | 0.255 ms | 0.133 ms |
| 1,024 walls + 256 furnishings, warm | 1.837 ms | 0.771 ms |
| 4,096 walls + 256 furnishings, warm | 6.517 ms | 2.654 ms |
| 1,024 walls + 256 furnishings, cold | 1.853 ms | 2.427 ms |
| 4,096 walls + 256 furnishings, cold | 6.252 ms | 8.058 ms |

Creating the reusable payload adds work to a cold request. Repeated unchanged
overview/detail/crop requests recover that cost; continuously changing geometry
does not get the warm-hit benefit. The measured change is not a complete preview
latency improvement.

### Completed preview adoption

Completed private image/vector transports now load on a background QThread.
Images retain their exact pixels, format and DPI. SVG preparation constructs
independent native renderers off the GUI thread, then transfers their QObject
tree to the GUI thread before parenting, painting or normal destruction. Native
SVG loads use direct native-slot dispatch on their owning thread. Clip-path cache
lookup/insertion/accounting use short locks, with parsing outside the lock, so
background and GUI construction share the existing bounded cache safely.
Qt documents QImage and Qt SVG reentrancy and the QObject ownership-transfer
rules in its [thread support](https://doc.qt.io/qt-6/threads-modules.html) and
[QObject threading](https://doc.qt.io/qt-6/threads-qobject.html) documentation.

One prepared result can await consumption; additional completed results retain
the existing bounded disk cache. Revisiting a disk-only result also loads
asynchronously. Slot keys and generations still govern acceptance. Errors use
the existing preview-error path. Stale/cancelled results are discarded, and close
requests interruption and joins the task before deleting private files/thread
objects. Native SVG parsing itself cannot be interrupted mid-call, so closing
may wait for that operation. Recursive SVG visitor closures are explicitly
broken on success/failure so temporary XML and cancellation callbacks do not
wait for cyclic collection.

Native SVG preconstruction is skipped above the vector byte allowance. The
parsed document follows the existing caller-specific budget checks/page fallback
or construction path. In particular, Print can reject an oversized shared model
before native compilation. Very large non-Print documents can retain their
original GUI-side construction cost.

The adoption-only benchmark uses a 2,560-by-1,440 raw bitmap and an SVG generated
from 128 walls plus 128 actual washer furnishings. Both variants read the same
completed transport files. Before includes synchronous loading and SVG renderer
construction; after includes background loading/preparation and GUI handoff.
The test uses a native Qt event loop with a 1-ms heartbeat, two warmups and nine
alternating samples. Worker rendering/file production are excluded. The initial
qWait polling probe starved the background Python thread and is retained only
as a superseded diagnostic; final adoption results use the native event loop.

| Adoption metric, median across samples | Before | After |
| --- | ---: | ---: |
| Bitmap: initiating GUI callback | 5.550 ms | 0.106 ms |
| Bitmap: total readiness | 5.551 ms | 7.661 ms |
| Bitmap: largest GUI heartbeat gap | 5.585 ms | 1.511 ms |
| SVG: initiating GUI callback | 648.600 ms | 0.161 ms |
| SVG: total readiness | 648.601 ms | 667.549 ms |
| SVG: largest GUI heartbeat gap | 658.159 ms | 68.481 ms |

This is a responsiveness improvement with scheduling overhead, not a demonstrated
encoding/rendering throughput gain. Python work and some native operations still
delay GUI callbacks; the background thread does not eliminate the GIL or every
pause. Heartbeat gaps include scheduling and the existing GUI collector, and
are not input-to-display measurements. No constant frame-rate claim is made.

All timing samples are in `diagnostics/performance-followups-20261031/benchmark-final.json`;
the final adoption rerun is also in `adoption-final.json`. Tests compare 256 new
frozen group frames, mutable/external edits, Shift and connection changes,
cancelled state and exact pixels. They verify warm affected-row counts, scene
snapshot equality/invalidation/detachment/byte bypass, concurrent clip-cache
accounting, off-GUI loading, native child ownership, disk revisits, stale results,
malformed files, in-flight closing and oversized SVG budget behavior. The 30
distinct focused checks pass, with targeted regressions and real-worker checks
also passing at 125% and 200% scaling. All 72 help files retain their pre-pass
hashes. Verification and check reports are in the same diagnostics directory.

### Handoff for the next review

No user decision was required to complete these two follow-ups. The additional
complete-window profiles include UpdateInteraction, connected property refresh
signals, event processing and a synchronous viewport grab on a real MainWindow.
They explicitly process events and grab, which can paint twice; their cProfile
times include instrumentation overhead and must not be treated as display
latency. Baseline/current traces and scripts are in
`diagnostics/performance-followups-20261031/complete-interaction-profiles-reference-*.json`
and the accompanying `.pstats` files.

Those profiles identified these follow-up priorities:

- Paint-time architectural validation and coincident-record preparation revisited
  substantial scene data when moving furnishings/labels invalidated the scene
  key. The next section records the implemented local invalidation and record
  reuse, including conservative fallbacks and measured tradeoffs.
- Painting still traverses furnishings/labels and checks visibility/artwork
  bounds. The movement-only gain does not remove these whole-scene costs.
- With snapping enabled, group target/anchor preparation and queries remain
  significant. Fresh complete-window profiles include this case separately.
- Large SVG adoption still spends CPU on layer/XML preparation, serialization
  and native loading. Its worst GUI pauses are reduced but remain measurable.
  Moving more preparation into the existing render process would be a further
  architectural step; this pass retains exact native SVG output and ownership.

These are documented residual costs and follow-up opportunities. They are not
claimed solved by the two implemented changes, and no additional approval or
input request is pending.

### Paint preparation follow-up — 2026-10-31

Moving a furnishing or label previously invalidated architectural paint
validation across the scene. Even when individual collision predicates could
reuse their results, preparation still traversed the scene and rebuilt its
broad phase. Coincident-object preparation also reconstructed and JSON-encoded
unchanged architectural/annotation records on every geometry change.

`viewport/placement.py` now retains the current validation broad phase and uses
observed model geometry notifications to identify local edits. A furnishing edit
queries its old and new bounds, then runs the original exact predicates for
affected architecture in source order. Annotations do not affect architectural
collision validity. A bounded overlay replaces moved furnishings in spatial
queries, preserving blocker order and the original predicates. Full preparation
reuses furnishing bounds already computed during spatial-index construction.

Structural/attachment edits, unknown revision changes, policy/visibility/topology
changes, nonfinite edited bounds, and more than 256 distinct moved furnishings
take the original conservative full-validation path. Validation failures retain
the previous bounds and pending notifications, so retrying still checks both
old and new neighbors. Project cache clearing releases the retained index and
its object references. The full-validation path remains scene-wide.

`viewport/geometry.py` now reuses the exact canonical coincident-record string
for unchanged tracked built-in models. The existing furnishing tuple path,
ordering, visibility rules and ignored fields are unchanged. Model assignments
and coordinate edits discard cached strings, including equal assignments such
as integer/float substitutions that produce different JSON. Opening parent
indices, original-material values and derived fireplace depth/offset are checked
explicitly. Unknown/custom models and mutable original-material values keep
fresh encoding. Keys over 4,096 characters bypass retention, and clones/history
state exclude the cache.

Warm validation for a few distant furnishing/annotation edits avoids the
scene-wide scan. Dense collision neighborhoods, large spatial queries and exact
collision setup can still cost O(N). Coincident grouping remains O(N), including
ordering and visibility checks; it skips unchanged record allocation/encoding.
Reuse retains O(N) current-scene index/record data rather than historical
versions. This pass does not claim a process-memory reduction or constant-time
complete dragging.

The frozen reference methods are copied from the production sources saved
immediately before this pass. Their ASTs are verified against those snapshots.
Reference and current viewports share the current model notification code and
renderer; the comparison isolates preparation methods, rather than reverting
the entire project. Each independent fixture has N walls, N furnishings and N
labels. Measurements disable snapping, connections, measurements and tips, use
offscreen 1,200-by-800 viewports, and disable cyclic GC equally. Each row reports
the median of nine alternating before/after rounds after two warmup rounds.
Samples use three explicit model updates, except one for rendered frames,
preparation misses and the N=4,096 fixture. Cases run sequentially.

| Workload, N per category | Before | After |
| --- | ---: | ---: |
| Distant furnishing validation, 128 | 3.437 ms | 0.044 ms |
| Distant furnishing validation, 1,024 | 42.889 ms | 0.053 ms |
| Distant furnishing validation, 4,096 | 409.106 ms | 0.111 ms |
| Label validation, 1,024 | 43.016 ms | 0.027 ms |
| Furnishing validation near a wall collision, 1,024 | 48.104 ms | 3.245 ms |
| Coincident preparation, 1,024 | 12.548 ms | 4.223 ms |
| Coincident preparation, 4,096 | 50.787 ms | 18.617 ms |
| Combined preparation, distant furnishing, 128 | 4.983 ms | 0.609 ms |
| Combined preparation, distant furnishing, 1,024 | 55.775 ms | 4.477 ms |
| Combined preparation, distant furnishing, 4,096 | 432.235 ms | 18.189 ms |
| Combined preparation near a wall collision, 1,024 | 59.703 ms | 7.913 ms |
| Movement plus synchronous paint, distant furnishing, 128 | 10.860 ms | 6.775 ms |
| Movement plus synchronous paint, distant furnishing, 1,024 | 94.350 ms | 44.767 ms |
| Movement plus synchronous paint near a wall collision, 1,024 | 99.828 ms | 50.763 ms |
| Full preparation miss, distant furnishing, 128 | 5.296 ms | 5.512 ms |
| Full preparation miss, distant furnishing, 1,024 | 63.009 ms | 60.115 ms |
| Full preparation miss, distant furnishing, 4,096 | 531.615 ms | 452.440 ms |
| Full preparation miss near a wall collision, 1,024 | 62.082 ms | 64.262 ms |
| Wall movement with full validation, 1,024 | 46.379 ms | 49.101 ms |

The rendered-frame rows time explicit movement plus synchronous QWidget.render;
they exclude input dispatch, sidebar signals and display latency. N=4,096
rendering is omitted to bound benchmark runtime. Preparation misses clear the
validation and coincident keys outside the timer while retaining ordinary
geometry caches; these are not project-loading measurements. Full misses vary
by scene size, and structural wall validation regressed about 6% in this fixture
because maintaining reusable state adds bookkeeping. These results demonstrate
the intended repeated-edit improvement, not a universal gain on every path.

`tools/benchmark_paint_preparation.py` reproduces the workloads. Set
PLANNER_PAINT_BENCH_CASE to 128-distant, 1024-distant, 4096-distant or 1024-near
to run bounded cases separately. The check runner's default 30-second guard
applies per invocation, so run one fixture at a time. Raw samples, environment
versions and methodology are in
`diagnostics/performance-paint-preparation-20261031/benchmark-final.json`.

The new `check_paint_preparation.py` compares the frozen and optimized paths for
old/new collision neighborhoods, label edits, compound furnishings, 100 seeded
translation/resize/rotation updates, mixed architectural types and attached
openings, policy/visibility changes, manual invalidation, failure recovery,
overlay overflow and project-cache release. It compares exact painted images
during mixed-scene updates and checks all supported model types plus 159 record
field mutations, parent reordering, numeric spelling and mutable metadata.
Call-count assertions verify that a distant furnishing update computes only
its own bounds and that unchanged records are not serialized again.

All 12 focused checks pass, including group restoration, scene snapshots,
problem inspection, lazy validation, openings, columns, stairs, handles and
grouping. Targeted preparation/render-cache checks also pass at 125% and 200%
scaling, with pan DPI coverage at 125%. Reports and source verification are in
the same diagnostics directory. All 72 help-file hashes are unchanged. No Git
commands were run.

The remaining handoff was furnishing/label paint traversal, group snapping
preparation/queries, large SVG worker preparation, and the measured structural
validation regression. The following section closes that implementation list
and records its gains and tradeoffs. Scene-wide exact-collider keys and full
structural preparation remain complexity limits, not claims of constant-time
complete interaction.

### Final audit follow-ups — 2026-10-31

This pass completes the four remaining handoff items together. It preserves
rendering and gesture behavior in the frozen comparisons below. No further
implementation task or user decision is being proposed as part of this audit.
The measurements describe specific workloads; they do not claim that every
scene, cache miss or future performance opportunity has disappeared.

#### Furnishing and label paint traversal

`viewport/paint_candidates.py` maintains one current-scene spatial index of
world-space physical/artwork/text ink bounds. Editing a few objects updates a
bounded overlay; painting queries the viewport/dirty regions and restores source
order and duplicate-reference multiplicity before drawing. Both furnishing
layers and labels use those candidates. One recent query can be shared by the
scene/text/outline passes. Dense queries retain the original full-list path.
The overlay rebuilds after 256 distinct edited objects, so it does not accumulate
historical scene variants.

Geometry/appearance notification journals detect edits independently of the
architectural validation and snapping consumers. Missing/manual notifications,
topology/visibility changes, definition key/nominal-size changes, renderer
replacement and DPI/font policy changes rebuild preparation. Hidden objects do
not force artwork/layout loads. Derived room labels, north arrows and custom
models retain conservative fallback behavior. Exports retain their original
full-scene path and layer reuse. Project cache clearing releases the new index
and journals.

This removes repeated offscreen bounds/layout work, rather than making complete
painting independent of scene size. Advisory grouping, wall preparation and
visible artwork still have their existing costs. The index retains O(N) current
scene data. Warm sparse queries usually process the edited objects plus nearby
candidates; a large or dense query can still approach O(N). No process-memory
reduction is claimed.

#### Group snapping preparation and queries

`viewport/scene.py` reuses stationary target/anchor pools and their numeric
coordinates while only group movers change. Reuse observes topology, visibility,
snap options, transforms, connection changes, selected entries, definitions and
the existing mutable-baseline fingerprint. External stationary edits and unknown
revision changes rebuild the pools. Mutable/custom restoration adapters keep
fresh preparation. Start, copy/connection transitions, release, cancellation and
project replacement discard obsolete gesture state.

The large-group benchmark also demonstrated a query bottleneck after preparation
reuse: the previous x/y strip union revisited many aligned targets for every
anchor. `geometry/snapping.py` now separates direct two-dimensional point queries
from nearest one-dimensional coordinate alignment. Duplicate coordinates retain
their first source index; equal rounded-distance plateaus are walked to preserve
the original winning target. Exact thresholds, source/anchor tie order, native
movement-distance calculations and constrained-ray behavior remain unchanged.
The same point/coordinate preparation can serve unconstrained and constrained
movement. The existing preparation-count check now expects that cross-mode reuse.

Typical repeated group snapping avoids both the stationary scene scan and the
anchor-by-target alignment sweep. Direct dense neighborhoods and unusually large
rounded-distance tie plateaus can still require scanning many candidates. No
constant-time worst-case claim is made.

#### Structural validation regression

`viewport/placement.py` now creates local-validation membership/order maps only
when a furnishing/annotation edit needs them. A full structural validation also
skips the extra rectangle construction and overlay generator when the moved
furnishing overlay is empty. The conservative structural validation algorithm
and its exact collision predicates are unchanged.

The three-way 1,024-per-category benchmark measures the original pre-paint-
preparation baseline at 48.293 ms, the previous pass at 50.844 ms, and this pass
at 48.485 ms. The final difference from the original baseline is 0.193 ms, with
overlapping samples. This addresses the additional full-validation work without
claiming statistically proven zero overhead or a faster structural algorithm.

#### Large SVG worker preparation

`graphics/svg_preview.py` replaces repeated descendant clip scans with one
bottom-up pass. The existing render process now also prepares XML layers, exact
serialized clip paths, layer names, native SVG source bytes and recoloring
bindings. The adoption thread reads that private preparation, loads independent
native renderers, builds native bounds/index data and transfers QObject ownership
to the GUI thread as before. No native QObject is sent between processes.

`export_preview_worker.py` writes the original root first and optional preparation
second with one Pickler; the corresponding Unpickler preserves shared XML node
identities needed for recoloring. Caller vector budgets retain the exact original
root transport size. Oversized results discard transport-only preparation and
keep the original caller fallback. MemoryError during preparation or its second
transport record keeps/truncates back to the valid original root, preserving the
legacy loading path. Cancellation, stale-result rejection and close/join behavior
retain their existing ownership rules.

Moving this work into the existing process reduces GUI scheduling gaps, but the
larger prepared transport adds serialization/readiness cost. In the final real-
process fixture, SVG transport grows from 3,080,235 to 8,640,878 bytes. Total
readiness regresses while GUI heartbeat gaps improve. These are explicit
responsiveness/throughput tradeoffs, not an overall SVG speedup or a memory-saving
claim. Preparation-only XML/source bytes are released after adoption.

#### Benchmarks and verification

`tools/benchmark_final_performance_followups.py --case paint|snap|wall|svg` runs
bounded cases separately. Editor fixtures use N walls, N furnishings and N
labels; the dense fixture has 128 furnishings/labels and no walls. Painting
includes explicit model movement and synchronous QWidget.render into an
offscreen 1,200-by-800 image. Snapping includes group update/fitting and excludes
painting. These are not whole-window input-to-display measurements.

Each editor row is the median of nine alternating frozen/current samples after
two warmups. Warm paint and wall samples average three updates; other editor
samples use one. Miss cases clear their named preparation outside the timer and
retain ordinary geometry caches; they are not project-loading measurements.
The frozen methods share current model notifications/renderer infrastructure.
Their observer journal initializer is adapted to the new internal layout, with
the previous full-validation work retained. Wall measurements also include the
older pre-paint-preparation baseline separately.

| Workload | Before | After |
| --- | ---: | ---: |
| Sparse movement + paint, N=128 | 6.592 ms | 3.167 ms |
| Sparse movement + paint, N=1,024 | 46.998 ms | 17.188 ms |
| Sparse paint preparation miss, N=128 | 6.707 ms | 6.904 ms |
| Sparse paint preparation miss, N=1,024 | 43.450 ms | 44.773 ms |
| Dense movement + paint, 128 furnishings/labels | 10.311 ms | 10.691 ms |
| Dense paint preparation miss, 128 furnishings/labels | 10.512 ms | 13.591 ms |
| Snapped group, N=128, 2 selected, warm | 4.740 ms | 0.228 ms |
| Snapped group, N=1,024, 2 selected, warm | 40.288 ms | 0.687 ms |
| Snapped group, N=1,024, 128 selected, warm | 494.576 ms | 8.021 ms |
| Snap target preparation miss, N=128, 2 selected | 13.084 ms | 11.983 ms |
| Snap target preparation miss, N=1,024, 2 selected | 113.284 ms | 101.288 ms |
| Snap target preparation miss, N=1,024, 128 selected | 577.629 ms | 111.329 ms |
| Structural wall validation, N=1,024, previous/current | 50.844 ms | 48.485 ms |

The SVG fixture uses 64 walls and 64 actual washer furnishings, separate real
persistent reference/current render processes, two warmups and seven alternating
samples. The reference process renders with shared current infrastructure and
returns its original root; parent adoption uses the frozen pre-pass SVG renderer.
Current requests include process-side preparation and native result adoption.
Both variants use the same render arguments and run sequentially. Cyclic GC is
disabled equally in the benchmark parent. Phase boundaries are GUI-observed
process output readiness and completed adoption; they include scheduling and
transport effects, and are not isolated CPU measurements.

| SVG metric, median across samples | Before | After |
| --- | ---: | ---: |
| Request to native preview readiness | 492.572 ms | 576.475 ms |
| Request to observed producer output | 189.584 ms | 439.207 ms |
| Observed output to completed adoption | 308.238 ms | 134.426 ms |
| Largest 1-ms GUI heartbeat gap | 37.200 ms | 16.182 ms |

Raw samples, Python/Qt/platform details and methodology are in
`diagnostics/performance-final-followups-20261031/benchmark-final.json`.
Samples overlap and timing varies between runs; no confidence interval or
display-latency guarantee is claimed. The paint benchmark also compares exact
final pixels for each fixture. Dense/cold cases and SVG total readiness are
included to expose regressions rather than report only favorable rows.

All 35 focused checks pass, with final targeted checks covering subsequent
transport/validation adjustments. Preparation, rendering and real preview
process checks also pass at 125% and 200% scaling. New coverage includes 48 exact
rotated/sparse/dirty paint comparisons, complete viewport comparisons, 256 frozen
group frames plus warm reuse/mutable-baseline checks, 2,400 additional point-query
matrices, hidden artwork bypass, bounded overlays and project release. Prepared
SVG tests compare exact pixels/recolored XML for clipped/gradient/CSS/transparent
inputs, preserve logical budgets and inject preparation/partial-transport memory
failures to verify the legacy fallback. Existing checks cover preview ownership,
stale results, closing, allocation recovery and print output.

All 72 help-file hashes remain unchanged. No Git commands were run. Source
snapshots, check reports and final verification are retained in the diagnostics
directory. The four-item handoff is complete; the complexity limits and measured
tradeoffs above remain part of the result. That checklist did not establish
acceptable performance for every real saved project. The following user-reported
case exposed a workload missing from those fixtures.

### Real-project wall control-point dragging and zoom — flat.plan, 2026-10-31

The saved `plans/flat.plan` has 49 walls, 3 pillars, 9 counters, 2 railings,
38 openings, 95 furnishings, a north arrow and 8 labels. Its many distinct
furnishing definitions exercise the native cache differently from earlier
large fixtures made mostly of one repeated furnishing. Saved snapping options
are enabled, measurements are hidden and collision settings are false.
Openings still participate in collisions under the existing policy.

Three demonstrated inefficiencies were fixed:

- `SceneRenderValueKey` loaded normal and selected native renderers for every
  furnishing to inspect their identities. `EditSceneSnapshot` also loaded SVGs
  for bounds. These bookkeeping operations caused bounded-cache churn, including
  397 renderer constructions across two paints in the initial profiled step.
  Validity keys now use nonrealizing semantic tokens, and snapshots use existing
  metadata-only artwork geometry where available. Lazy population/eviction keeps
  tokens stable; map/render replacements, style edits, definition source/nominal
  size changes and direct dictionary replacements remain observable. Plain
  renderer dictionaries retain the original identity-based behavior.
- The native cache reserved all 16 possible scale variants before allocation.
  Broad zoom views therefore evicted active base artwork. Accounting now uses
  allocated variants, render-ready XML estimates, embedded images and borrowed
  solid renderers. Weak ownership notifications update costs as variants grow;
  old variants are retired before reusable base artwork. The per-map 16 MiB
  estimated budget, 128-entry limit and 16-variant maximum are unchanged. These
  are retention estimates, not measured RSS or peak-allocation bounds; a local
  drawing reference can transiently keep an evicted variant alive.
- Near-parallel junctions produced overly broad conservative radius bounds,
  returning blocker pools of 144 objects for individual walls. Exceptionally
  inflated bounds now consult the exact category owner/body footprints already
  used by collision predicates, retaining the raw body and a floating-point
  safety margin. No actual miter is capped and no collision tolerance is relaxed.
  The shared footprint builder keeps the original membership/exclusion keys.
  This can build geometry earlier in a pass in exchange for fewer candidates.
  Separate drag profiles show overlap calls falling from 2,599 to 557.

Production changes are in `graphics/furnishings.py`, `viewport/rendering.py`,
`viewport/edit_cache.py` and `viewport/geometry.py`. Project settings, snapping
rules, zoom factors/limits, cursor anchoring and full-quality rendering are
preserved in the comparisons below.

`tools/profile_flat_interactions.py` loads the project into a real MainWindow
with connected properties-panel signals. Its shown-window processEvents and grab
can paint twice; the initial roughly 311-ms drag result must not be compared
directly with the controlled single-paint benchmark below. Separate `.pstats`
files and stage measurements are retained in the diagnostics directory.

`tools/benchmark_flat_interactions.py --case drag|zoom-in|zoom-out|zoom-deep`
uses independent real MainWindows, saved settings and a 1,500-by-900 viewport.
Windows are hidden to prevent incidental duplicate paints. Each step includes
endpoint UpdateInteraction or wheelEvent, connected UI work, processEvents and
one forced viewport grab. The drag case selects wall ID 256, vertex 1. Each row
is the median of nine alternating unprofiled samples after two warmups, with
cyclic GC disabled equally. Zoom ticks continue in one direction; deep zoom
starts after eight outward ticks. These are controlled input-plus-render
workloads, not input-to-display latency measurements.

The reference freezes the original validity/snapshot methods, overlap/bounds
methods and native cache/factory implementation. Other application infrastructure
is shared. Frozen method ASTs match the source snapshots. Every benchmark checks
final model/gesture state, zoom/pan and exact pixels before an additional untimed
renderer-count probe; reported final zoom includes that extra probe tick.

| Saved flat.plan workload, median | Before | After |
| --- | ---: | ---: |
| Wall control-point update plus viewport render | 176.773 ms | 40.453 ms |
| Zoom outward from saved view | 32.409 ms | 29.781 ms |
| Continued outward zoom with the whole scene visible | 80.411 ms | 22.164 ms |
| Zoom inward from saved view | 12.742 ms | 13.240 ms |

The untimed drag probe constructs 198 base renderers before and zero after. The
deep-zoom probe constructs 66 before and zero after; the optimized map retains
67 entries within its unchanged estimated budget. The lower estimated counter
is not a measured RAM saving because its accounting policy changed. Zoom-in
shows no demonstrated gain. Dragging still spends roughly 14 ms in its update
and 26 ms in rendering here; snapping, validation and painting retain measurable
costs. No universal smoothness/frame-rate or all-project completion claim is made.

Raw samples and methodology are in
`diagnostics/performance-flat-20261031/benchmark-final.json`. Phase medians need
not sum to the median total because they can come from different samples.

All 24 focused checks pass, with final regressions also passing at 125% and 200%
scaling. The new check compares 31 exact saved-project drag/zoom frames across
three wall control points, model state, cursor anchoring and all eight collision
policies. It verifies nonrealizing keys, unchanged LRU order during inspection,
explicit/direct renderer replacement, style edits, eviction-stable tokens,
allocated-variant budgets, borrowed-solid accounting and weak cache ownership.
Existing checks cover native lifetimes, lettering/fixed variants, transparency,
exports, edit/pan caches, fractional/DPI rendering, junction ownership, compound
collisions and cold geometry parity.

The original flat.plan hash and all 72 help-file hashes are unchanged. No Git
commands were run. Source snapshots, production diff, raw timings, check reports
and verification hashes are in the diagnostics directory. This follow-up fixes
demonstrated real-project bottlenecks; representative saved-project profiling
remains necessary when a user reports another slow interaction.

### Further flat.plan endpoint optimization — 2026-10-31

This pass compares against the optimized version immediately above, retaining
its renderer, geometry-bound and collision fixes in both variants. It does not
reuse the original 176-ms reference as evidence for additional gains.

Three sources of repeated work were removed:

- `viewport/geometry.py`, `ConnectedWallPath`: snapping, room detection and paint
  alternate between complete and partial wall sets. The component cache alone
  still reassembled unchanged sets. A four-entry cache now restores the exact
  base-coordinate path, owner polygons, footprint cuts and component metadata.
  Its complete key preserves ordered membership, coordinates, widths, miters,
  scale and tracing mode; camera transforms are applied on every return. It is
  enabled for sets of at least 16 objects. Only repeated inputs are admitted;
  a bounded 16-hash admission history avoids retaining/accounting every unique
  cursor position. Hashes affect admission only, never result identity.
  All native results share the existing 16-MiB/262,144-point geometry budget,
  and project cache clearing releases the history. Columns retain their native
  adapter, whose ordinary-wall workspace can use the same cache.
- `viewport/snapping.py`, `SnapStairVertex`: the cap/alignment queries share one
  ordered midpoint-coordinate list and reuse numeric corner targets within a
  single read-only snap operation. No cross-frame target invalidation is needed.
  Direct/corner policies, duplicates, source order, alignment guides and grid
  fallback remain unchanged. A separate saved-project probe collects midpoints
  once instead of three times.
- `viewport/placement.py`, `PlacementBlockers`: collision pairs rejected by the
  existing settings/type policy are filtered before broad-phase queries and
  paint-validity signatures. Disabled collisions no longer make otherwise
  unchanged objects look dirty. The filter is shared by type/category within
  the immutable validation scope, preserving candidate order and the furnishing
  overlay. Exact predicates still handle every possible collision. Openings
  remain enabled under the original policy. The separate drag probe performs
  61 architectural placement validations instead of 93; validation is not
  deferred until mouse release.

`tools/benchmark_flat_next.py` freezes the start-of-pass `ConnectedWallPath`,
`SnapStairVertex` and `PlacementBlockers` methods in
`checks/fixtures/flat_next_reference_20261031.py`. Their ASTs are checked against
the source snapshots. Both variants use independent real MainWindows with
connected properties-panel signals, original saved settings, a 1,500-by-900
viewport and Qt offscreen rendering at 100% scale. Each sample measures input,
processEvents and one synchronous grab. Two warmups precede 15 alternating,
unprofiled samples; cyclic GC is disabled equally. Three independent drag runs
provide 45 samples per variant. Model/gesture state and zoom/pan are compared
at every step, with exact final pixels. Counters run outside the timed samples.
These measurements concern synchronous work, not input-to-display latency.

| Incremental saved-project workload, median | Start of this pass | After |
| --- | ---: | ---: |
| Wall endpoint update plus viewport render, 45 samples | 39.421 ms | 36.106 ms |
| Input-update portion of that workload | 14.045 ms | 10.583 ms |
| Viewport grab portion of that workload | 25.157 ms | 25.051 ms |
| Zoom inward, 15 samples | 11.147 ms | 11.019 ms |
| Zoom outward, 15 samples | 27.863 ms | 27.711 ms |
| Continued outward zoom, 15 samples | 22.268 ms | 22.341 ms |

The aggregate steady drag workload falls by 8.4%; its input portion falls by
24.6%. Per-run total medians are 39.567/36.106, 39.108/35.681 and 40.888/36.923
ms. Painting remains approximately 25 ms. The zoom differences do not establish
a meaningful improvement; no zoom factor, anchor, quality or debounce changed.
Phase medians need not sum to the median total.

The drag probe's shared geometry estimate rises from 3,259,688 to approximately
3,630,100 bytes, about 0.35 MiB extra, with four retained assemblies. Its point
counter rises from 7,159 to 12,291, within the unchanged budget. These are
conservative retention estimates, not measured process-memory differences or
peak-allocation bounds. Unique drag inputs bypass assembly storage; eviction
always falls back to exact reconstruction.

First-step warmup timings are retained in the raw files under `cold`, including
slower after-change samples. They are not isolated startup measurements: both
windows share Qt's event loop and deferred work can run during the other
variant's processEvents. This pass demonstrates steady-drag gains, not improved
cold/startup responsiveness. No cold improvement is claimed.

`check_flat_next.py` compares 96 exact native assembly states with camera,
tracing, miter, pillar, column and eviction variations; tests bounded admission,
cache hits, budget clearing and weak lifetimes; and compares 72 exact saved-plan
drag frames, model states and invalid-object sets across three control points,
Ctrl/Alt modifiers and all eight collision settings. The focused suite also
covers prior real-project zoom parity, snapping, furnishing variants, pan/edit
caches, geometry budgets, exports, junction ownership, railings and openings.
Final saved-project/native comparisons also pass at 125% and 200% scaling.

Reproduction: `python tools/benchmark_flat_next.py --case drag` (or `zoom-in`,
`zoom-out`, `zoom-deep`). Raw samples, three drag runs, merged results, source
snapshots, production diff, check reports and verification hashes are under
`diagnostics/performance-flat-next-20261031`. All 72 help files and the original
flat.plan remain unchanged. No Git commands were run.

### Local architectural validation during wall redraws — 2026-11-01

The single-wall comparison and a redraw trace confirmed that the existing edit
cache already repaints small old/new rectangles in the representative flat.plan
drag. Its preparation still performed scene-wide architectural checks. A
separate profiler sample attributed 19.446 ms of cumulative profiled work to
`InvalidArchitecturalObjects`, including 61 fitting calls. This is profiler
evidence identifying work, not an unprofiled frame-latency measurement.

`viewport/placement.py` now retains the original broad-phase index across local
plain-wall edits. It compares exact native collision-path element values and
clipped SAT bodies to detect changed junction owners, including stationary
neighbors whose joined footprints change. Objects near both the old and new
bounds are revalidated with the existing fitting predicates, in scene order.
Openings on edited parents are included even when the child itself emitted no
geometry notification. A bounded bounds overlay covers moved objects while the
original index remains unchanged. Later furnishing edits query this structural
overlay too, so they can find a wall far from its original index position.

The method retains live validation during gestures; no fitting predicate,
collision tolerance, drawing command, quality setting, snapping rule or release
behavior changed. A failed predicate does not publish new bounds or consume the
edit journal. Unknown/nonfinite edits, missing preparation, pocket-door scenes,
other structural edit classes and broad changes use the original full path.
More than 32 changed dependency objects, an affected set of at least 75% of the
validated architecture, or more than 256 distinct overlay entries also rebuild
normally. Global pocket-door support therefore remains conservative.

Additional wall-edit data is prepared for wall-edit activity, rather than
initial static/zoom-only scenes. One current scalar footprint snapshot is
limited to 4,096 owners and 32,768 native path elements; oversized snapshots
bypass the optimization. These limits bound the new fingerprint storage, not
total project memory. The original index/bounds and one current fingerprint
snapshot are retained, rather than a history of cursor positions. Existing
project cache clearing releases validation state. No measured process-memory
or peak-allocation improvement is claimed.

`tools/benchmark_local_paint.py` compares frozen start-of-pass
`InvalidArchitecturalObjects`, `RefreshArchitecturalValidation` and
`PlacementBlockers` methods against current code. Frozen ASTs match the source
snapshots; remaining application code is shared. Each case runs in four fresh
processes, with two real hidden MainWindows per process. Creation/preparation
order reverses on alternate trials and input order alternates per step. Each
trial discards two warmups and records 15 unprofiled samples per variant:
60 samples per variant, at 1,500 by 900 and 100% scale. Cyclic GC is disabled
equally inside a trial. Samples include input, connected UI work, processEvents
and one synchronous grab; the existing render-sample recorder separately times
paintEvent. Exactly one paint is asserted per step. Model/gesture state and
zoom/pan are compared every step, and exact final pixels every trial. Extra
placement-call counters run outside timings. Warmups are not isolated cold-start
measurements. Results concern synchronous work, not display latency.

| Workload, median | Start of this pass | After |
| --- | ---: | ---: |
| Wall 256, vertex 1: paintEvent | 23.705 ms | 18.732 ms |
| Same drag: input plus events plus grab | 36.062 ms | 31.209 ms |
| Same drag: input-update portion | 10.485 ms | 10.516 ms |
| Wall 1, vertex 0: paintEvent | 43.206 ms | 38.889 ms |
| Same second drag: input plus events plus grab | 67.222 ms | 64.706 ms |
| Isolated single wall: paintEvent | 2.941 ms | 2.948 ms |
| Same isolated drag: input plus events plus grab | 5.967 ms | 5.992 ms |
| Outward zoom: input plus events plus grab | 25.109 ms | 25.111 ms |

The representative drag reduces painting by 21.0% and total work by 13.5%.
Its untimed probe falls from 61 placement checks to 3. The second wall's probe
falls from 60 to 12, but its total reduction is only 3.7%; benefits depend on
the wall and its dependencies. Single-wall and zoom workloads show no meaningful
gain. Phase medians need not sum to the median total. Room-boundary preparation,
scene snapshots and other drawing work remain; painting is still substantially
more expensive than in the single-wall scene. This pass does not make all scene
preparation proportional only to changed objects.

Early fixed-construction-order zoom trials had mixed/slower results. Final
measurements balance setup order and isolate processes. An extended in-process
benchmark also failed while constructing its third pair of windows: Qt returned
a QStandardItem where the combo-box model was expected. That failure preceded
the trial's measurements. The final process-isolated trials completed without
changing application widget code. The earlier harness and zoom diagnostics are
retained for review; only the final independent-process results appear above.

`check_local_paint.py` compares 280 dependency updates against frozen validation,
including tiny junction-tolerance changes at large coordinates, zero-length
walls, pillars, columns, pocket-door fallback, parent/child openings, furnishing
edits after a wall moves far from the original index and exception retry. It
also checks that static scenes do not create wall-edit snapshots, that structural
commits actually reuse the index, and that oversized native fingerprints are
not copied. The saved-project matrix compares exact invalid-object sets, full
model/gesture state and pixels across three wall endpoints, all eight collision
policies and Ctrl/Alt combinations. Additional focused checks cover compound
collisions, railings, geometry budgets, resource lifetimes, scene/edit caches,
exports, prior drag fitting and pan/DPI behavior.

The existing resource-lifetime check initially failed on both frozen and current
validation: export successfully produced `single-snapshot_001.png`, while the
test expected `single-snapshot.png`. The check now verifies exactly one valid
matching PNG, preserving its one-prepared-scene assertion. Exporter behavior was
not changed.

Reproduction: `python tools/benchmark_local_paint.py --case drag`, optionally
`--wall-id 1 --vertex 0`, `--single-wall`, or `--case zoom-out`.
Raw per-trial samples, profiles, source snapshots, production diff, check reports
and verification hashes are in `diagnostics/performance-local-paint-20261101`.

The latest results for all 21 focused checks pass. The final 280-dependency and
90-frame saved-project matrix also passes at 125% and 200% scaling. All 72 help
files and the original flat.plan hash are unchanged. No Git commands were run.

### Retained paint membership and warnings — 2026-11-01

This pass starts after local architectural validation above. It retains unchanged
paint preparation; it does not defer validation, room detection or drawing until
release, and does not change any fitting or containment predicate.

`VisibleSceneObjects` retains ordered visible scene lists under topology,
visibility, visibility-setting values and hidden identities. Ordinary geometry
movement leaves those lists valid. Opaque drawing, edit snapshots and duplicate
grouping share them. Preview objects continue to be checked separately.

Furnishing duplicate groups and front-copy warnings now share one exact scalar
snapshot, including ordered identities, coordinates, dimensions, flips and the
definition key. Unchanged furnishings reuse their results while a wall moves.
Scene-order grouping, rear/front paint layers, repeated references, hidden
objects and persistence-derived non-furnishing records retain their original
semantics. One read-only collision pass shares the result between consumers.
Cross-pass retention is limited to 4,096 furnishing entries; no native artwork
is retained by this preparation.

Containment retains at most two current snapshots, for the architectural set
and the plain-wall subset used by edit painting. A changed subject is rechecked;
an unchanged subject is rechecked whenever a changed container's old or new
expanded bounds could contain it. The original oriented-footprint predicate,
0.01 tolerance and duplicate-order rule still decide the result. Occurrence
indices preserve repeated references. Snapshots are published only after all
predicates finish, so an exception leaves the prior dependency state available
for retry. Eligibility is limited to 16–4,096 finite ordinary walls, pillars,
columns, counters and elevators; unsupported shapes, more than 32 changed
entries, broad changes/affected sets and membership changes use full calculation.
Project cache clearing releases all three new preparations. These are bounded
entry counts, not measured process-memory or peak-allocation improvements.

`tools/benchmark_retained_paint.py` substitutes frozen start-of-pass
`DrawOpaqueScene`, `EditSceneSnapshot`, `ContainedWalls`, `DuplicateFurnishings`
and `CoincidentObjectGroups`; remaining code is shared. Frozen ASTs match the
saved source. Each workload uses four fresh processes with two independent
hidden MainWindows, alternating construction and input order, two discarded
warmups and 15 unprofiled samples per variant per trial. There are 60 samples
per variant at 1,500 by 900 and 100% scaling, with cyclic GC disabled equally.
Samples include input, connected UI work, processEvents and one synchronous
grab, with exactly one paint asserted. Model/gesture state is compared every
step and final pixels every trial. This measures synchronous work, not display
latency or isolated cold-start responsiveness.

| Workload, median | Start of this pass | After |
| --- | ---: | ---: |
| Wall 256, vertex 1: paintEvent | 18.312 ms | 16.960 ms |
| Same drag: input plus events plus grab | 30.442 ms | 29.298 ms |
| Wall 1, vertex 0: paintEvent | 41.241 ms | 39.787 ms |
| Same second drag: input plus events plus grab | 64.475 ms | 63.582 ms |
| Isolated wall: paintEvent | 2.741 ms | 2.833 ms |
| Same isolated drag: input plus events plus grab | 5.701 ms | 5.762 ms |
| Outward zoom: input plus events plus grab | 26.208 ms | 25.403 ms |

The representative drag improves painting by 7.4% and total work by 3.8%, with
lower paint medians in all four trials. The second wall has mixed per-trial
results despite the lower pooled medians; no uniform wall-1 gain is claimed.
The isolated-wall control initially showed a small slowdown and was repeated;
the table includes all eight trials, 120 samples per variant, without discarding
the initial trials. Its pooled total is 0.061 ms slower and paint is 0.092 ms
slower. Outward zoom improves by about 0.8 ms. Input processing, room-boundary
preparation, global scene-value snapshots and architectural footprint signatures
remain; this does not eliminate the busy-scene/single-wall gap. Phase medians
need not sum to the median total.

All 21 focused checks pass, including existing containment/NumPy paths,
duplicates and repair, export, visibility, scene revisions, resource lifetimes,
pan/DPI and edit caches. The new check covers 51 ordered membership/duplicate
comparisons, 418 frozen containment comparisons, actual omission of unaffected
exact predicates, broad/nonfinite fallback, exception retry and cache cleanup.
It also compares 90 exact saved-project model/validation/pixel frames across
three endpoints, all collision settings and modifier combinations. This matrix
passes at 100%, 125% and 200% scaling.

Reproduction: `python tools/benchmark_retained_paint.py`, optionally
`--wall-id 1 --vertex 0`, `--single-wall` or `--case zoom-out`;
`python checks/run_checks.py check_retained_paint.py` for the new regression.
Raw samples, source snapshots, production diff, checks and verification hashes
are in `diagnostics/performance-retained-paint-20261101`. All 72 help files and
the original flat.plan remain unchanged. No Git commands were run.

### Avoid redundant wall-boundary overlap probes — 2026-11-01

Wall-boundary assembly groups endpoint-connected components whose owned polygon
bounds overlap. Several polygons can prove the same connection repeatedly. Once
two components are already in one connected overlap group, another intersection
between their pieces cannot change the resulting partition.

`ConnectedWallPath` now rejects these already-connected pairs before native
rectangle tests. Direct group labels make that rejection constant-time. On each
union, only the smaller group's members are relabeled, so each member moves at
most logarithmically many times. Temporary membership lists use linear space
within the call; no new retained cache or dependency journal is introduced.
The existing rectangle sweep/spatial-index selection, native QRectF predicates,
pillar weld tolerances, ordered final groups, contour tracing, ownership and
room updates remain unchanged. The room-detection source is unchanged.

An untimed profile of the representative input-plus-paint step records 3,884
native rectangle-intersection calls before and 1,805 after. These counts identify
eliminated work; profiler elapsed times are not used as frame-latency evidence.
Completed-outline caching, a retained overlap graph and a lower spatial-index
threshold were also measured. They showed no useful net gain and were removed
from production. Their diagnostic snapshots/results remain labeled as prototypes.

`tools/benchmark_wall_boundary.py` compares frozen start-of-pass
`ConnectedWallPath` against the current implementation, with the retained paint
optimization above present in both variants. The frozen AST matches the saved
source. It uses the existing hidden-MainWindow harness at 1,500 by 900 and 100%
scale: four fresh processes, alternating creation and input order, two warmups
and 15 unprofiled samples per variant per process, cyclic GC disabled equally.
Input, connected UI work, processEvents and one synchronous grab are included;
exactly one paint is asserted. Model/gesture state is compared every step and
final pixels every trial. This is synchronous work, not display latency or an
isolated cold-start measurement.

| Workload, median | Start of this pass | After |
| --- | ---: | ---: |
| Wall 256, vertex 1: paintEvent | 17.206 ms | 16.795 ms |
| Same drag: input plus events plus grab | 29.341 ms | 28.693 ms |
| Wall 1, vertex 0: paintEvent | 41.007 ms | 41.200 ms |
| Same second drag: input plus events plus grab | 64.924 ms | 65.370 ms |
| Isolated wall: paintEvent | 2.915 ms | 2.903 ms |
| Same isolated drag: input plus events plus grab | 6.078 ms | 6.105 ms |
| Outward zoom: input plus events plus grab | 25.489 ms | 26.446 ms |

The representative drag improves painting by 2.4% and total work by 2.2%, with
lower paint and total medians in all four trials. Other workloads do not establish
a consistent improvement. Wall 1 and zoom were repeated because their controls
were variable; the table pools all eight trials for each, 120 samples per variant,
retaining the initial trials. Representative and isolated-wall cases have 60
samples per variant. Pooled median differences and paired-frame differences do
not agree for the controls: median current-minus-baseline total differences for
matched frames are -0.437 ms (wall 256), -0.136 ms (wall 1), -0.038 ms (isolated)
and +0.062 ms (zoom). Raw pooled medians above are retained, including slower
control results. An additional untimed zoom probe finds zero `MergeBounds` calls
in all 15 measured frames in both variants; it runs only during initial warmup.
No zoom improvement is claimed. Phase medians need not sum to the median total.

All 23 focused checks pass. The new regression compares 320 exact native overlap
snapshots and 96 exact assembly snapshots, covering joins/splits, reordered and
partial membership, both tracing modes, both broad phases, large coordinates,
miters, pillars, columns and budget eviction/lifetime. An operation-count assertion
confirms redundant rectangle probes are actually omitted. The 90-frame saved-plan
model/validation/pixel matrix passes at 100%, 125% and 200% scaling. Existing
checks cover live room tint, labels, stairs, passages, welding, near-straight
boundaries, materials, SVG/export, prior optimizations and pan/DPI behavior.

Reproduction: `python tools/benchmark_wall_boundary.py`, optionally
`--wall-id 1 --vertex 0`, `--single-wall` or `--case zoom-out`;
`python checks/run_checks.py check_wall_boundary.py` for the new regression.
Raw samples, profiles, source snapshots, production diff, checks and verification
are in `diagnostics/performance-wall-boundary-20261101`. All 72 help files and
the original flat.plan remain unchanged. No Git commands were run.

## Drag, zoom and pan cost isolation — 2026-11-01

This is a diagnostic pass, not another production optimization. The preceding
small improvements do not explain away the remaining busy-scene penalty.
Production source, all 72 help files, and flat.plan are unchanged in this pass.
No Git commands were run. Temporary bypasses exist only inside the diagnostic
process and are restored by context managers, including on exceptions.

The main matrix uses the original saved project/settings, a hidden real
MainWindow, a 1500x900 logical viewport and DPR 1. Each of 33 case/bypass pairs
runs in three independent processes with two independent windows. Creation
order reverses on alternate runs; frame order alternates. Two warmups precede
15 measured input/processEvents/grab steps: 45 matched pairs per bypass and
90 normal samples per control workload. Exactly one paint is asserted per step.
These are synchronous work times, not display latency or delivered frame rates.
Automatic cyclic GC is disabled equally; application timers and explicit
collections remain active. Normal controls compare model/camera state every
frame and exact final pixels, including pan release. Normal-versus-normal
matched median differences range from -0.19 to +0.51 ms across the ten cases.

| Normal workload | Input median ms | Paint median ms | Total median ms |
| --- | ---: | ---: | ---: |
| Wall 256, vertex 1 | 10.66 | 17.50 | 30.41 |
| Wall 1, vertex 0 | 25.11 | 41.24 | 66.44 |
| Isolated wall 256 | 1.25 | 2.79 | 6.08 |
| Zoom near saved camera, alternating ticks | 0.05 | 12.36 | 14.18 |
| Consecutive zoom inward | 0.05 | 9.94 | 11.58 |
| Consecutive zoom outward | 0.05 | 25.24 | 26.94 |
| Zoom farther out after eight outward ticks | 0.05 | 21.67 | 23.56 |
| Pan by (8, 5) device pixels | 0.06 | 6.93 | 8.72 |
| Pan by (8.25, 5.25) device pixels | 0.06 | 10.33 | 12.13 |
| Pixel-aligned pan after eight outward ticks | 0.06 | 10.78 | 12.57 |

Totals include event processing and grab overhead. Medians of separate phases
need not sum to the median total. Consecutive zoom traces change visible object
counts; the alternating trace stays near the original camera.

Separate phase wrappers include collision workspaces, not just the main
viewport. Inclusive timings nest and must not be added. The current phase
reports are `*-phases-2.json`; earlier exploratory instrumentation is retained.
cProfile runs separately on frame 17; its instrumented timings are not claimed
as achievable savings.

The highest priority is snap-preview collision preparation. `SnapStairVertex`
takes about 9.0 ms for wall 256 and 24.6 ms for wall 1; `WallFits` accounts for
5.5 and 20.9 ms inside those intervals. Temporary candidates enter
`CollisionCategoryGeometry`, which can prepare connected wall geometry in a
separate workspace. Ordinary paint preparation does not eliminate that work.
Skipping snapping entirely reduces input to roughly 1.5 ms. Matched median
total reductions are 9.20 and 14.44 ms, but matched mean reductions are 8.19 and
7.88 ms: the altered geometry sometimes makes later painting more expensive.
These bypasses change behavior and are evidence of cost, not proposed fixes.
The isolated-wall bypass slightly worsens total time despite reducing input.

Within geometry preparation, `GeometryCacheCost` repeatedly walks nested keys
and values to estimate retained bytes and native points. The median of its
combined per-frame input/paint time is 5.01 ms for wall 1, versus 0.70 ms for
wall 256 and zero in the timed navigation frames. This is a concrete secondary
target within the drag work: retain reliable cost metadata where possible,
while preserving shared-object accounting, bounded memory, eviction and object
lifetime. Eliminating all accounting is neither proposed nor measured as a
safe implementation. Cache accounting overlaps the geometry/snap timings above.

Room classification itself is small: `Room.UpdateBoundary` is about 0.34–0.36
ms. The much larger inclusive room check includes shared wall assembly and
tracing. Freezing `RoomDetection.Check` moves geometry work into other callers
and suppresses room/background revisions. Its matched median total change is
approximately zero for both walls; the slower wall's mean improves 3.97 ms,
with strongly mixed individual frames. Do not treat the inclusive room-check
time as independently removable work or defer visible room updates on this evidence.

Snapshot preparation is also a smaller target: wall 256's `EditSceneSnapshot`
is about 0.70 ms inclusive, plus 0.54 ms for the scene value key. Wall 1 usually
does not take the incremental snapshot path in timed frames. Disabling the edit
cache makes wall 256 slower by a matched median 2.10 ms. Wall 1 is mixed:
median -2.52 ms but mean +3.14 ms. Removing bookkeeping also removes retained
pixels, so this is not a pure snapshot-cost measurement.

Zooming needs separate work. Outward/deep traces render all 95 furnishings in
the profiled frame. `FurnishingSvgRenderer.render` takes about 5–6 ms, including
Python preparation and native SVG painting. Omitting that method reduces total
time by matched medians 5.36/5.98 ms, versus 1.10 ms near the saved camera.
Python-dispatched painter draw/fill/stroke suppression reduces outward/deep
totals by 7.97/6.93 ms. That bypass keeps text preparation and native SVG drawing;
it is not a measurement of all rasterization. The two bypass effects overlap
and cannot be summed into a promised optimization. Investigate retaining exact
furnishing drawing preparation/commands without scaling cached pixels, changing
cosmetic strokes, text sizing, clipping or draw order.

Panning already benefits from raster scrolling and exposed-strip redraws.
Fractional device-pixel movement intentionally takes the full repaint fallback
to preserve antialiasing; rounding the camera would change behavior. At 125%
scaling, two independent paired control runs give 9.97 ms for pixel-aligned
pan, 16.92 ms for fractional pan, and 19.77 ms for near-camera zoom. Their model,
camera and final pixels agree between normal windows. These are spot checks,
not a complete display-scaling matrix. Pan artwork bypass savings are small
(0.76 ms at the saved view, 0.05 ms at the wide view); remaining drawing and
exposed-strip preparation are more relevant than room/snapshot work.

The first matrix warmup follows project load without an idle pre-render, so its
large cold cost must not be called normal pan-start latency. Separate probes
render the idle scene twice before pressing the middle button. Three trials
give warm start/release medians of 12.11/13.68 ms at the saved view and
24.67/16.11 ms at the wide view; fractional-pan start/release is 12.74/13.85 ms.
These transition probes have phase wrappers enabled. Release also performs
cursor hit testing; its timing is not exclusively paint.

Recommended order: investigate exact snap-preview collision geometry and its
cache accounting first; address furnishing rendering for zoom separately;
then consider exposed-strip preparation and warm pan-start costs. Further
sub-millisecond snapshot work is not the leading opportunity. No specific
behavior-preserving speedup is established by these deliberately incomplete bypasses.

Artifacts: `diagnostics/performance-interaction-costs-20261101/summary.json`
contains aggregate metrics and methodology; per-case files contain raw samples,
phase timings and profiles. `verification.json` records unchanged hashes for
264 production/protected files and hashes of the diagnostic tools. The initial
hash manifest is `source-before.json`.

Reproduce individual trials with
`python tools/diagnose_interaction_costs.py --case drag --mode no-snap --run 0`.
Use run indices 0, 1 and 2 for the main matrix. Cases include `drag-wall1`,
`drag-single`, `zoom-in`, `zoom-out`, `zoom-deep`, `zoom-near`, `pan`,
`pan-fractional`, and `pan-wide`. Other measured modes are `normal`,
`frozen-rooms`, `no-qt-draw`, `no-artwork`, `no-edit-cache`, `phases` (run 2),
and `transitions` (pan cases). For 125% controls set `QT_SCALE_FACTOR=1.25` and
use `normal` with indices 125/126 for `pan`, `pan-fractional`, and `zoom-near`.
`python tools/summarize_interaction_costs.py` rebuilds the summary and verifies
the initial production/protected hashes after the full recorded matrix exists.

### Faster accounting and shared wall preparation — 2026-11-01

Implemented the first two scoped follow-ups from the cost investigation.
Production changes are limited to `viewport/geometry_cache.py` and
`viewport/geometry.py`. Snapping candidate generation, priority, acceptance,
collision predicates, room updates and drawing algorithms are unchanged.

`GeometryCacheCost` now handles exact built-in scalars and containers before
probing Qt types. Exact floats use the interpreter's fixed float object size;
integers and other scalars still use their actual dynamic size. Subclasses,
custom `__sizeof__`, Qt objects and uncommon containers retain the original
fallback. Identity deduplication, cycles, shared-ID exclusions, native point
counts and key-wrapper overhead remain identical. This deliberately does not
memoize aggregate sizes across mutable/aliased graphs. Budget limits, insertion
acceptance, accounting and LRU behavior are unchanged for the same inputs.

Wall collision workspaces can now reuse the viewport's body, junction, sector
and ownership-fragment caches when both use the same geometry budget. The keys
already describe the exact local calculation:

- Body: scale, object type, endpoints and width.
- Junction: scale, joint coordinates, ordered directions/widths/owner IDs and miters.
- Sector: polygon coordinates and exact clipping planes/cuts.
- Ownership: source coordinates and ordered cutter coordinates, with distinct pillar keys.

Complete paths, owner maps, membership keys, contour tracing and per-workspace
polygon metadata remain separate. Sharing polygon metadata would also require
sharing its point-count bookkeeping, so it is not done. Missing caches or a
different budget retain private preparation. Counter, stair and railing
workspaces stay private: their different populations and size caps must not
trim a large wall scene's caches. Existing limits and project cleanup apply to
the shared caches; no new unbounded history or object-ID-only cache was added.

The initial prototype shared these fragments across all structural categories.
It was restricted to the wall category before final verification. Initial
results/source are retained under `prototype-all-categories`; the table below
uses the final guarded source. Scalar dispatch and sharing were also measured
independently, with the other change held constant.

| Workload, both changes | Frozen total median ms | Current total median ms | Matched-frame median delta ms |
| --- | ---: | ---: | ---: |
| Wall 256, vertex 1 | 30.014 | 29.600 | +0.255 |
| Wall 1, vertex 0 | 63.462 | 59.977 | -3.091 |
| Isolated wall 256 | 5.552 | 5.706 | +0.027 |
| Zoom outward | 26.540 | 25.325 | -0.843 |
| Zoom near saved camera | 13.714 | 13.789 | +0.026 |
| Pixel-aligned pan | 8.247 | 8.509 | +0.149 |
| Fractional-pixel pan | 11.912 | 11.896 | -0.074 |

Negative matched deltas mean current is faster. The slower wall improves in all
four trials, with per-run matched median total deltas -1.19, -5.15, -1.84 and
-5.06 ms; pooled matched mean is -2.939 ms. The ordinary wall's pooled medians
look slightly faster while its matched median/mean are +0.255/+0.313 ms. It has
no consistent improvement. The isolated wall and navigation are controls; no
uniform navigation gain is claimed. This remains a modest full-frame saving,
not a solution to the entire busy-scene penalty.

On wall 1, accounting alone improves matched total median by 2.076 ms and
sharing alone by 1.054 ms (separate trials, not guaranteed additive). A separate
same-object replay of 63 real accounting requests from frame 17 takes
6.543 ms frozen versus 2.761 ms current. All byte/point results match exactly.
That is a microbenchmark, not the per-frame saving. Four warmups precede 40
alternating replays, with identical arguments and cyclic GC disabled equally.

An untimed operation probe on the slow wall records 2,199 versus 2,142 convex
subtractions and 69 versus 63 accounting insertions at frame 17. Estimated
retained geometry drops from 11,349,608 to 10,234,032 bytes and from 1,196 to
962 cache entries. This is budget accounting, not process RSS. The synthetic
unchanged-component regression drops repeated clipping operations from 71 to
zero while preserving exact native results. Expensive changed-component
construction still occurs and remains a later optimization target.

Each final workload uses four fresh processes with independent hidden real
MainWindows, alternating creation and frame order, two warmups and 15 timed
steps per variant: 60 samples each. Viewport is 1500x900 at DPR 1 with original
flat.plan settings. Exactly one paint per step, complete model/gesture/camera
comparisons every step, and exact final pixels are asserted. Timings cover
input, events and synchronous grab, not display latency. Separate cProfile
probes are used for operation counts; their timings are not performance claims.

All 19 focused checks pass on the final source. The new regression includes
600 exact accounting comparisons (aliasing, cycles, shared exclusions, large
integers, subclasses, custom sizes, mutable native paths/polygons), equal
budget/eviction sequences, 700 exact shared/private collision snapshots,
bounded/disabled budgets, workspace cleanup, and 90 exact saved-plan
model/validation/pixel frames including snap priorities/guides and modifiers.
The new matrix and `check_pan_dpi.py` also pass at 125% and 200% scaling.

One existing check has a scale assumption: `check_pan_dirty_regions.py` passes
at DPR 1 but fails at 125% with both frozen and current code. Its fixed (3,1)
logical-pixel moves become fractional device-pixel moves, so the test's strip
reuse/validation-retention assertion is not applicable there. The unchanged
test and both failure reports are retained; scaled verification uses the
DPI-aware check and the exact new parity matrix. This is not reported as a new
rendering regression or silently counted as a passing scaled strip test.

Artifacts are in `diagnostics/performance-snap-preparation-20261101`:
`benchmark-final.json`, `accounting-replay.json`, `profile-comparison.json`,
`checks-latest.json`, `production-changes.patch` and `verification.json`.
Frozen functions are AST-verified against source saved before this pass.
All 72 help files and flat.plan remain unchanged. No Git commands were run.

Reproduce with `python tools/benchmark_snap_preparation.py`, adding
`--wall-id 1 --vertex 0`, `--single-wall`, or
`--case zoom-out|zoom-near|pan|pan-fractional` as appropriate. Independent
comparisons use `--mode accounting` or `--mode preparation` on wall 1.
Run `python checks/run_checks.py --jobs 1 check_snap_preparation.py check_native_geometry_budget.py`
for the new/reference regressions. Set `QT_SCALE_FACTOR` to `1.25` or `2` for
the new parity matrix and `check_pan_dpi.py`. `finalize.py` in the artifact
directory verifies protected/source hashes, frozen function ASTs and final
check reports before collecting the recorded benchmark matrix.

### Fragment-local snapping preparation prototype — 2026-11-01

The measured follow-up narrows work inside changed-component ownership
construction. It does not add another component cache or attempt to infer a
wall dependency graph. Existing exact body/junction/sector/ownership keys and
their invalidation, budgets and cleanup remain in use.

An ownership probe on the slower wall showed why an unchanged-prefix cache
would have limited value: the expensive source/cutter sequences generally
changed at their first cutter. However, most subsequent fragment subtractions
returned the input unchanged. At frame 17, the two largest individual source
calculations performed 519 and 467 subtractions, of which 489 and 430 were
unchanged. Earlier cuts had already separated most fragments from later
cutters, but every attempt still converted Qt points and recomputed bounds.

`SubtractConvexPolygons` now retains numeric coordinates and bounds throughout
one ordered subtraction sequence. Unchanged fragments reuse their bounds;
new fragments receive fresh bounds. Only possibly overlapping fragments reach
the existing single-cutter calculation. Qt polygons are constructed once for
the final fragments. `PolygonBounds` is shared with single subtraction so the
rejection retains the exact original origin/extent rounding, empty/degenerate
handling and strict touching-edge comparisons. It introduces no tolerances or
approximate geometry. Uncertain comparisons retain the existing calculation.
Cutter order, fragment order, winding, area thresholds and cache keys stay
unchanged. Metadata lives only for that calculation; there is no retained
history requiring dependency tracking or eviction.

The production integration is the ownership-completion loop in
`viewport/geometry.py`; the numeric implementation is in `geometry/polygons.py`.
Both traced painting components and collision components use the same exact
ownership calculation. Snapping candidates, priorities, collision acceptance,
room classification, camera movement and drawing code are unchanged.

Final-source timings, four separate processes per workload:

| Workload | Frozen total median ms | Current total median ms | Matched-frame median delta ms | Matched mean delta ms |
| --- | ---: | ---: | ---: | ---: |
| Wall 1, vertex 0 | 61.097 | 55.536 | -5.584 | -5.557 |
| Wall 256, vertex 1 | 30.043 | 29.510 | -0.353 | -0.179 |
| Isolated wall 256 | 6.243 | 6.191 | -0.042 | +0.127 |
| Zoom outward | 26.963 | 26.519 | -0.262 | -0.016 |
| Zoom near saved camera | 14.353 | 14.256 | -0.125 | -0.160 |
| Pixel-aligned pan | 8.492 | 8.388 | +0.018 | -0.058 |
| Fractional-pixel pan | 12.546 | 12.299 | +0.075 | -0.186 |

Negative deltas mean current is faster. The slow wall improves in all four
runs, with matched median deltas -4.262, -5.623, -5.053 and -6.246 ms. This is
about 9% overall; input handling medians are 23.459 versus 17.754 ms, with a
matched median input saving of 5.071 ms. Matched paint savings are only 0.209 ms.
The ordinary wall improves slightly in each run (0.094–0.451 ms matched total),
but the effect is small. Isolated dragging and navigation remain controls;
their small mixed differences do not support a general navigation speedup.
This does not eliminate the busy-scene penalty or most remaining paint work.

Each run uses two independent hidden real MainWindows at 1500x900 and DPR 1,
original flat.plan settings, alternating creation and frame order, two warmups
and 15 unprofiled samples per variant. The seven workloads ran sequentially
without concurrent test/profile workloads. Exactly one paint is required per
sample; complete model/gesture/camera state is compared every frame and final
pixels every trial. Times include input, event processing and synchronous grab,
not display latency. cProfile is a separate operation-count probe. Exploratory
`benchmark-both-*` artifacts precede the final source and are excluded from
`benchmark-final.json`; some exploratory trials overlapped and are not evidence
for the final timing claim.

Reproduce with `python tools/benchmark_snap_local.py --wall-id 1 --vertex 0`,
the default wall arguments, `--single-wall`, or
`--case zoom-out|zoom-near|pan|pan-fractional`. Frozen start-of-pass construction
and subtraction functions are in `checks/fixtures/snap_local_reference_20261101.py`
and `snap_subtraction_reference_20261101.py`. The new parity check is
`python checks/run_checks.py --jobs 1 check_snap_local.py`. Evidence and the
source/protected-file manifest are in `diagnostics/performance-snap-local-20261101`.

All 27 focused checks pass, covering the new exact sequence comparison,
previous shared preparation, numeric primitives, geometry rebuilds, native
budgets, footprint measurements, wall caches, junction ownership/materials,
nearly straight walls, columns, snapping, collision policy, retained/local
paint, wall boundaries and pan/raster behavior. `check_snap_local.py` compares
22,121 ordered clipping cases (including empty/degenerate shapes, reversed
orders/windings, strict touching edges and adjacent floats, distant origins,
NaN/infinity outcomes), 700 collision snapshots with bounded/disabled budgets
and cleanup, and 90 exact saved-project model/snap/validation/pixel frames.
It and `check_pan_dpi.py` also pass at 125% and 200% scaling: 31 check executions
in the final reports. The earlier shared-preparation regression now counts
the new batch clipping entry point, retaining its positive reuse assertion
(36 batches versus zero), rather than counting the bypassed Qt adapter.

The separate frame-17 operation probe reduces numeric single-cutter calls
from 2,142 to 645 while preserving all 1,937 edge splits. Both variants retain
10,234,032 accounted geometry bytes, 39,008 native points and 962 entries at
that frame. These are budget estimates, not process RSS. Profile timings are
not used for the speed claim. Frozen function ASTs match the before snapshots;
only the two named production files changed. All 72 help files, their file
inventory and flat.plan remain unchanged. No Git commands were run.

### SVG furnishing zoom investigation — 2026-11-01

No production change was retained from this investigation. The snapshots and
verification manifest show all 264 tracked production/protected inputs
unchanged, including all 72 help files and flat.plan. Work is limited to
diagnostic prototypes, a reproducible benchmark driver and this audit.

A separate per-renderer probe on outward zoom found 95 furnishing draws at
frame 17, with 5.670 ms inside `FurnishingSvgRenderer.render`. Eleven draws
with lettering accounted for 3.610 ms; the remaining 84 accounted for 2.060 ms.
These are instrumented diagnostic observations, not unprofiled speedup claims.
The lettering renderer calculates exact screen-orientation/size corrections
and constructs a native SVG variant when the bounds/transform key changes.
Fixed-detail-only variants already use physical dimensions as their key and
can survive camera changes. Normal artwork and renderer/template preparation
are already retained independently of the camera.

Three approaches were evaluated:

- **Normalized vector-command replay:** record plain native artwork into a
  QPicture and replay it under the new bounds transform. Text, fixed details,
  animation and non-raster destinations fall back to existing rendering. All
  18 saved-plan zoom frames differed in pixels, despite equal model/gesture
  state. This prototype is rejected; its exploratory timings are not a gain.
- **Exact generated-source reuse:** observe source bytes passed to native
  variant constructors, independently for each renderer. Across 28 outward
  steps, all 263 constructed variant sources were distinct for their renderer.
  Existing input-key hits already avoid construction at repeated views. A
  second exact-source cache would not recover the observed misses. No transform
  rounding or approximate keys were introduced.
- **Compact lettering-template copies:** remove foreign editor-only XML from
  the copy used to construct lettering variants, preserving the original
  artwork/root and falling back when stylesheets are present. Saved-plan pixels
  matched in all 18 exploratory frames and all 12 final benchmark trials.
  However, the small timing differences were inconsistent and this was not
  promoted or claimed safe for all imported SVGs. A production version would
  require narrower removal rules and checks for foreign namespace content and
  references; the measured result did not justify that additional behavior risk.

Unprofiled current-versus-compact-prototype results:

| Workload | Current total median ms | Prototype total median ms | Matched-frame median delta ms | Matched mean delta ms |
| --- | ---: | ---: | ---: | ---: |
| Zoom outward | 28.252 | 27.503 | -0.613 | -1.008 |
| Zoom from an already wide view | 24.296 | 23.730 | -0.200 | +0.433 |
| Zoom near saved camera | 14.235 | 13.845 | +0.034 | -0.344 |

Negative deltas favor the prototype. Outward/deep runs each had one slower
run; near-camera runs had three slower matched medians. Pooled medians alone
therefore overstate the consistency. Each workload has four fresh processes,
two independent hidden real MainWindows at 1500x900/DPR 1, alternating window
creation and frame order, two warmups and 15 timed samples per variant per run
(60 samples each). Cyclic GC is disabled equally. Exactly one paint is asserted
per sample, model/gesture/camera state is compared every frame and final pixels
every trial. Workloads and separate probes ran sequentially. Times include
input, event processing and synchronous grab, not display latency.

A separate native-constructor probe at frame 17 observed 11 constructions:
44,501 source bytes and 1.648 ms current versus 35,575 bytes and 1.681 ms compact.
At frame 5, six constructions took 0.851 versus 0.722 ms. These single-step
instrumented measurements show that reduced source size does not establish a
consistent parser saving. The 3.610-ms lettering cost includes calculations,
parsing, cache maintenance and native drawing; it is not all removable work.

A larger possible follow-up would retain parsed static artwork and update
lettering separately **in original SVG paint order**, with conservative
fallbacks for clipping, opacity, styles and references. Drawing labels as a
final overlay would be incorrect: the existing lettering regression explicitly
covers a later SVG shape obscuring earlier text. No such rewrite is included
here, and its attainable gain has not been measured.

Artifacts are in `diagnostics/performance-svg-zoom-20261101`: `probe.json`,
`prototype-picture.json`, `source-probe.json`, `prototype-compact.json`,
`construction-probe.json`, `benchmark-final.json` and `verification.json`.
`python tools/benchmark_svg_zoom.py --case zoom-out|zoom-deep|zoom-near`
reproduces the compact-template comparison without editing production source.
The diagnostic folder retains the experiment code and original furnishing
implementation. No help files or artwork assets were edited; no Git commands
were run. With no production patch retained, the unchanged application's full
regression suite was not rerun for these rejected experiments.

### Wall-drag preparation and repaint locality investigation — 2026-11-01

This is an investigation with an isolated, measured prototype; no production
patch is retained. It qualifies the earlier suggestion that avoiding whole-scene
repainting would itself remove most of the busy-scene penalty. The ordinary
wall already uses local painting, and the geometry tracer already reuses most
unchanged edge classifications. Important preparation still occurs even when
only a small fraction of the canvas needs new pixels.

`locality-probe.json` records two distinct reasons for losing edit-raster reuse:

- `backgroundKey[14]` contains the room/label revisions. A change makes
  `DrawEditScene` repaint the complete foreground, even when the regenerated
  background has exactly the same pixels. In the saved-camera trajectories,
  both walls' background-pixel differences were zero throughout the probe.
- `CanCacheEditScene` excludes alignment guides. Their appearance clears the
  retained edit raster and uses direct scene painting. Simply removing the
  exclusion would be wrong: guides are drawn behind the scene, and an opaque
  retained image would cover them.

The ordinary wall 256 already had approximately 1.2–1.9% dirty coverage on
representative moving frames; it was not repainting the entire scene. The slow
wall 1 benchmark used in preceding passes has its edited endpoint **offscreen
at the saved camera**. This remains a valid stress trajectory but must not be
represented as ordinary on-screen wall dragging. This investigation therefore
adds a camera centered on wall 1's edited endpoint, restarting the same gesture
there before comparisons. Camera movement is setup, outside timing.

The diagnostic prototype does two things together:

1. When only the room/label background revision changes, compare the previous
   and new background images exactly. Identical pixels preserve the foreground
   raster. Otherwise compute conservative 32-device-pixel tiles containing
   actual background differences and include them in the existing dirty region.
   All other background-key changes retain full invalidation. The background
   itself is still generated normally, so this does not freeze room state or
   assume that opening/closing a room has only a local effect.
2. Retain alignment guides inside the edit raster in their original order:
   after the background and before scene objects, with the same aliased line
   treatment. Add old/new guide strips to the dirty region and guide values to
   the frame key. Existing axis-constraint and other eligibility exclusions,
   the broad-area fallback and full-quality drawing remain in place.

The visible-wall prototype's median dirty coverage is 13.54%, including zero
pixel-work frames; moving frames are generally 13–15%. Small coverage does not
make its draw preparation proportionally cheaper.

| Workload / prototype | Baseline total median ms | Prototype total median ms | Matched-frame median delta ms | Matched mean delta ms |
| --- | ---: | ---: | ---: | ---: |
| Wall 1, visible endpoint, both changes | 63.676 | 59.923 | -2.538 | -4.768 |
| Wall 1, saved/offscreen endpoint, both | 55.879 | 43.117 | -6.374 | -8.623 |
| Wall 256, saved visible endpoint, both | 30.534 | 30.070 | -0.319 | -0.940 |
| Wall 1, visible, background only | 64.232 | 61.924 | -0.265 | -1.393 |
| Wall 1, visible, guides only | 68.283 | 71.165 | +0.026 | -0.308 |

Negative matched deltas favor the prototype. Both changes together improve
all four runs for each main workload. For the visible slow wall, per-run
matched total medians are -2.864, -6.395, -3.703 and -1.606 ms. Pooled before/
after medians make the offscreen benefit look larger than the matched 6.374 ms;
both statistics are retained. Isolated changes are mixed and not additive:
retaining guides while the background still forces full redraws is insufficient.

Each workload uses four fresh processes, two independent hidden real MainWindows
at 1500x900/DPR 1, original flat.plan settings, alternating creation and frame
order, two warmups and 15 unprofiled samples per variant (60 samples each).
Exactly one paint is asserted per sample; complete model/gesture/camera state
is compared every frame and final pixels each trial. Cyclic GC is disabled
equally. The five workloads ran sequentially, separately from instrumentation
and parity runs. Times include input, events and synchronous grab, not display
latency. Prototype patch installation/compilation is outside the timed step.

Separate phase instrumentation of the visible-wall prototype shows roughly
16.1 ms in input snapping, 13.4 ms in `Room.Check` and 18.2 ms in `DrawScene`.
These are diagnostic medians, not additive promised savings. `Room.Check`
includes shared wall construction/contour assembly; freezing room detection
would neither preserve behavior nor necessarily remove that shared work.
`DrawScene` still includes approximately 5.7 ms of incremental architectural
validation, and around 6.5 ms in instrumented Qt drawing calls. The preceding
13.4-ms room stage and much of scene preparation survive the smaller dirty clip.
The final cProfile probes keep both windows in their active gesture until both
profiles finish, avoiding unrelated idle-window issue checking after cancellation.

Component and tracer probes further constrain the proposed next step:

- At frame 17, the painted component has 20 walls, 19 with unchanged raw
  geometry. Seventeen owners' final polygon lists are unchanged, as are 65 of
  76 exterior segments. The candidate collision component has those 20 walls
  plus a temporary candidate; it also retains 17 unchanged owner outputs.
- The existing numeric tracer already reuses 252 of 294 source edges in one
  call and 128 of 155 in another, retracing only 42 and 27 respectively. It
  already has changed-contour bounds, retained edge results and local spatial
  indexing. Reimplementing it under an "incremental" label would not imply a
  new saving. Unchanged final geometry is not proof that all work producing it
  can be omitted without dependency checks.

A larger architectural experiment would need to retain coherent component
preparation across candidate validation, committed geometry and room/paint
consumers, update only changed owner/junction records, and avoid repeatedly
assembling unchanged inputs. It must preserve the intentional difference
between temporary-candidate and live-scene membership. Room topology changes,
old/new intersections, miter ownership, openings and validation feedback need
explicit dependency propagation and conservative full fallbacks. The remaining
attainable saving has **not** been demonstrated by this paint-locality prototype;
the data does not support promising a dramatic speedup from dirty-region
painting alone.

Verification covers 144 exact intermediate model/pixel frames and eight exact
cancel comparisons: centered wall 1 with saved settings, floors off, solid-room
grid clipping, measurements on and transparent objects at DPR 1; default and
solid rooms at DPR 1.25; default at DPR 2. All passed. The 20 benchmark trials
also assert exact final pixels. This is not production-ready cache validation:
the prototype retains a prior background image and allocates NumPy difference
scratch space outside the production raster budget. Integration would need
budget/lifecycle handling, format/unavailable-NumPy fallbacks and broader
mutation/invalidity/room-topology checks. No production change was retained.

Evidence is under `diagnostics/performance-wall-locality-20261101`, including
`benchmark-final.json`, `locality-probe.json`, `locality-summary.json`,
`phase-probe.json`, `component-probe.json`, `trace-probe.json`,
`parity-results.json` and `verification.json`. Reproduce the primary comparison
with `python tools/benchmark_wall_locality.py --wall-id 1 --vertex 0 --center`;
omit `--center` for the older offscreen trajectory, use defaults for wall 256,
or add `--mode background|guides` for isolated prototypes. The `try_prototype.py`
script in the artifact directory compares every frame and cancellation, with
`--center` and `--scene-mode default|floors-off|solid-rooms|measurements|transparent`.
Set `QT_SCALE_FACTOR` to `1.25` or `2` for scaled runs. All 264 tracked production/
protected inputs, the 72-file help inventory and flat.plan remain unchanged.
No Git commands were run.
