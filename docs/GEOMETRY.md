# Numeric geometry

Source module paths below are relative to `planner_app/`.

This package contains geometry that can run without Qt, an application window,
scene models, fonts or a renderer. Its imports must remain standard-library-only
or refer to other modules within this package. `check_geometry_core.py` enforces
this boundary in a separate Python process with site packages disabled.

## Data contracts

- Points are numeric `(x, y)` pairs. Spatial bounds are `(left, top, right,
  bottom)`. `RectangleFootprint` and `FireplaceFootprint` explicitly return a
  rectangle specification `(x, y, width, height)` instead: retaining the extent
  avoids changing floating-point results when adapting back to desktop bounds.
- Calculations preserve the caller's units and axis direction. Conversion
  between millimeters and screen pixels stays outside this package.
- Inputs are finite coordinate sequences. These routines do not round values,
  change winding, reorder fragments or perform project validation.
- Polygon splitting and convex subtraction do not mutate their inputs. A
  subtraction that leaves the subject untouched returns that input by reference.
- The cutter for subtraction must be convex. Existing signed twice-area
  thresholds remain `1e-9` for degenerate cutters and `1e-7` for discarded
  fragments. Threshold units follow the caller's coordinate system.
- Spatial queries preserve insertion order. Touching edges and zero-area bounds
  do not intersect. Callers should use normalized bounds; legacy cell allocation
  and intersection behavior for reversed bounds are preserved for the adapter.
- The index snapshots numeric bounds. Treat inserted geometry as immutable;
  rebuild the index when its bounds change. Values are opaque payloads, never
  inspected by the geometry engine.

## Desktop adapters

`viewport/polygon_clipping.py` converts Qt points at the boundary and delegates
all clipping to `geometry/polygons.py`. `viewport/spatial_index.py` converts Qt
rectangle edges and delegates to `geometry/spatial_index.py`. Existing callers
keep their current interfaces, geometry caches and invalidation rules.

`geometry/junctions.py` builds junction polygons, material ownership patches and
sector cuts from numeric positions, normalized rays and opaque owner keys. The
viewport adapter maps owner keys back to scene objects and constructs Qt polygons.
Its result has five entries: junction polygons, owner patches, local transitions,
owner sector cuts, and per-owner footprint planes `(point, outwardUnitNormal)`.
Keep `dot(position - point, normal) <= 0`. Historical `jointMiters` arguments now
mean chamfer amounts (0 uncut, 1 full); the UI does not invert them. Numeric
half-plane clipping lives in `geometry/polygons.py`. The adapter trims body and
owner sources before both tracing and coverage completion, retaining the common
zero-chamfer/equal-width cache path. Unequal two-ray joins also trim body caps
against the owner seam, at every chamfer amount: the original rectangle cap must
not protrude beyond the intersecting wall edges. See [corner chamfers](parity/CHAMFERS.md)
for the portable contract.

`geometry/boundaries.py` groups contour bounds, classifies exterior edge fragments
and assembles ordered contours. Inputs are prepared `(left, top, right, bottom,
edgeTuples)` records; edges are `(x1, y1, x2, y2)`. `extent` supplies the source
path's width/height using the existing bounding arithmetic. With `joinContours`
disabled, results are independent directed segments; otherwise they are ordered
rings, closed by the rendering adapter. The numeric fill-rule tag distinguishes
retained histories; legacy signed-winding membership remains unchanged.

Trace state and edge caches are explicit inputs/outputs. The desktop still owns
the eight-history/32,768-point budget and the existing edge-cache limit. Cache
state contains numeric coordinates, never Qt points or paths. Treat cached
results as immutable. Qt contour canonicalization, prepared-contour retention
and final painter-path construction remain in the viewport adapter to preserve
their current closure/degenerate-point behavior.

Avoid creating a second clipping implementation in an adapter. New numerical
rules belong in the core and should have headless tests. Desktop integration
checks still verify collision behavior, measurement ownership, rendering, export
and cache reuse against the existing implementation.

`geometry/footprints.py` constructs scaled wall rectangles, world-space object
footprints and axes, column handles and tolerance-based ellipse polygons, and
fireplace bodies/footprints. Wall bodies deliberately scale before normalizing;
world-space footprints normalize before applying their width. These operations
have different rounding behavior and must not be merged. Column polygon output
is relative to its center so the desktop can reuse the existing translated-shape
cache. Native ellipse curves remain in `graphics/column.py`.

`geometry/measurements.py` merges boundary segments, determines ordered owners,
prepares convex projection slabs, clips measurement spans, projects openings and
assembles gap/opening dimensions. Fireplace spans move to their front/rear body
faces. Owner keys are opaque values, resolved to scene objects by the adapter.
The module never inspects models or accesses viewport state.

The desktop resolves which opening classes use a pocket half-span and which
visibility/side policies apply. Selection bypasses still happen before span
construction and blocker clipping. Qt contour flattening, coordinate transforms,
text formatting, fonts and display precision remain desktop responsibilities.
Prepared projection slabs are temporary per geometry change; existing global,
span and owner caches and their budgets remain owned by the viewport. Warm
queries return the same retained Qt footprint/dimension objects.

`check_footprint_measurement_core.py` runs these kernels with site packages
disabled and compares raw coordinates, bounds, native path elements, owner
identity and warm-cache reuse against the frozen Qt implementation. Its saved
scenes and rotated/large-offset fixtures complement the existing measurement,
collision, rendering, export and interaction checks.

`geometry/collisions.py` contains collision-category policy, separating-axis
overlap/containment, intersection-area significance, conservative junction reach
and rigid-translation recognition. The desktop classifies model types into
numeric flags in a bounded type cache. Structural exact-type rules, annotation
exclusions, opening precedence and railing/elevator exceptions remain distinct.
Qt rectangle intersection/union and exact native-path intersection remain backend
operations. Numeric area/perimeter tests consume the resulting polygons lazily.

The desktop retains one lazy numeric footprint mirror per queried object, tagged
by the retained corner/axis tuples. Rebuilding an object footprint clears the old
mirror. This bounded per-object storage avoids converting unchanged Qt vertices
for every separating-axis query; it adds no pair cache and is never serialized.
Existing collision epochs, pair-key validation, temporary-object references,
rigid-translation reuse and the 16,384-result cleanup threshold remain unchanged.

`geometry/attachments.py` selects attached control points, traverses connected objects
and fits ordered openings after wall edits. Seed/candidate records contain opaque
keys and numeric endpoints. Recursive traversal takes an optional lazy contact
callback, preserving breadth-first discovery and pair-query order. The desktop
provides its existing stroked-path intersection backend for wall/furnishing
contacts; endpoint-only connection modes run entirely in the numeric core.
Neither callback nor model objects are retained by the engine.

Opening fitting receives the old/new wall geometry, original-order total length,
ordered opening lengths/centers and a fixed-end policy resolved by the desktop.
Keeping Qt endpoint equality outside the core preserves its existing tolerance.
Insufficient-length failures, non-stretch positioning and mutation order across
walls remain desktop behavior. Opening interval/bounds predicates are numeric.
`check_collision_attachment_core.py` compares the frozen desktop implementation,
including native backend results, cache refreshes and attachment order, and runs
the kernels without site packages.

`geometry/opening_placement.py` projects the cursor onto a parent segment,
finds free opening intervals, clips blocker polygons and sizes the placement
span. Model opening-handle and fireplace-center edits also use its numeric
projection rules. The desktop retains preferred-wall/reverse scene ordering,
visibility, pixel reach, snap priorities, guide state and collision validation.
Prepared polygon coordinates/bounds are retained only for the existing opening
footprint generation; direct wall edits rebuild them with the original key.

`geometry/editing.py` contains point/opening rotations, transformed-opening
attachment validation, merged-wall opening rebasing, handle sizing and centers,
group member transforms, span fitting and subdivision-fraction selection. Qt
native length values are explicit inputs where required to preserve arithmetic.
Group transforms retain the original two-stage endpoint construction followed
by the model angle setter; combining those operations changes rounding.

The group span search retains its original thresholds and 40 bisection steps.
Original member snapshots are immutable within a gesture. The desktop prepares
their numeric axes/offsets once, refreshing when duplication replaces the member
list or its center/count changes. One record is retained per active gesture and
released with that gesture, avoiding repeated Qt conversions inside the search.
Snapping and anchored-bound corrections still occur at their original points.
Model mutations, flags, selection/pivot lifetime, validation/rollback and history
remain desktop responsibilities. `check_opening_transform_core.py` compares raw
model coordinates and placement/guide results against frozen Qt code, alongside
headless transform, clipping and subdivision checks.

`geometry/snapping.py` owns metric/imperial grid intervals, ordered target
indices, direct/alignment/grid priority and constrained-ray snapping. Inputs are
numeric positions, `(x, y, directSnap)` target records, view scale, enabled
policies and an optional ray. Results contain a point, applied flag, priority
and ordered guides. Strict distance comparisons, source-order ties, positive
ray restrictions and the original rounding/arithmetic order are retained.
The desktop resolves visibility, moving-object exclusions, Alt state, target
collection and movement axes; it also retains the public prepared Qt-target
layout for callers. Internal multi-anchor queries share a numeric snapshot.

Opening placement collects snap targets once per query, after finding an
eligible parent/gap. Nothing is retained between queries, so direct edits,
hidden objects, modifier changes and moving-object exclusions remain live.
`OpeningFits` batches only its read-only collision validation; the batch never
spans snapping or model edits. This avoids stale footprints during temporary
control-point assignments elsewhere in the interaction code.

Junction bounds use an ordered endpoint index within a collision pass, grouped
by exact object category and excluded-wall set. The intersection of X/Y strips is a conservative
broad phase; native Qt endpoint distance, ray construction, miter reach and
rectangle union still determine the result. Original scene/endpoint order is
preserved. Unbatched queries retain a direct scan. The index and bounds are
released with the pass, with no new persistent scene cache or project data.
`check_opening_snapping_core.py` compares a frozen pre-pass implementation,
including native junction bounds, raw snapping/guides and placement results;
it also imports/runs the numeric core without Qt or site packages.

`geometry/group_movement.py` contains fixed-parent group axis projection,
opening travel-interval intersection, bounded common displacement, opening
fraction translation and attachment-point reconstruction. Inputs are numeric
vectors, original opening fractions/lengths, selected endpoint policies and
ordered neighbour intervals keyed by opaque parent IDs. Parallel and opposing
parents share travel; nonparallel parents block it at the original tolerance.
Projection remains sequential and retains the last axis, avoiding roundoff
changes from collapsing repeated projections. Selected endpoints participate in
axis constraints but do not gain whole-opening bounds. Duplicate placement
ignores neighbour/source intervals and still uses final collision validation.

The desktop prepares parent geometry and stationary intervals once per update,
retaining source order. Attachment propagation preserves its original mutation
order and iteration count, with numeric point calculations only. Parent geometry
is read again after propagation when translating opening fractions. Model
setters, snap/guide state, Ctrl handling, selection, copies, release validation,
rollback and undo/redo remain in the desktop layer.

`GroupOpeningsFit` shares collision preparation only across the read-only final
validation of fixed-parent openings. Its batch ends before `FitWallOpenings`
mutates any model; no batch spans restoration, movement or `SetOpeningVertex`.
No new persistent scene/gesture caches are introduced. The group regression
compares exact raw geometry and guides against frozen pre-extraction drag code,
including repeated updates and changing modifiers/connected settings.

`geometry/opening_collisions.py` provides an ordered numeric broad phase for
bulk opening validation. It indexes conservative edge bounds and returns source
positions, preserving duplicates/order. Same-parent openings are always included
because their native collision predicate uses wall intervals, even when either
footprint has zero area. Nonfinite records/queries fall back to the original full
narrow phase; reversed bounds are normalized before indexing. The existing
256-cell-per-entry/query fallback bounds grid allocation for oversized geometry.

The desktop supplies native `JoinedObjectBounds`, retaining miter extensions and
ellipse/fireplace footprints. Native `ObjectsOverlap`/joined path intersections,
interval predicates, policies, exclusions and tolerances still decide collisions.
Junction endpoint lookup uses the intersection of X/Y strips, followed by the
same native distance test in source order; alignment snapping still uses its
existing union-of-strips query.

Bulk group and full-scene validation request an index only for at least four
queried openings and 32 scene wall/opening records. If the scene has only
sibling openings and their own structural parent, it keeps direct interval scans
because a spatial index cannot prune candidates. The first opening retains a
normal validation scan for quick failure. A subsequent valid-sized opening builds
the index once. Small validations and standalone fitting keep the direct scan.
The candidate record is scoped to read-only validation with `try/finally` cleanup
and nested-state restoration, ending before fitting or endpoint mutations.
No new persistent scene cache, history data or format field is introduced.
`check_collision_validation_core.py` compares frozen native validation, ordered
numeric candidates, early failures, direct edits and scope cleanup; it imports
and runs the index and square endpoint query without Qt/site packages.

Large constrained movements also prepare one ray-target snapshot in
`geometry/snapping.py`. Direct targets get a two-axis proximity index; alignment
coordinates retain the first source index for each unique X/Y value. Per-anchor
queries use conservative coordinate strips and then the unchanged ray/distance
math. ULP padding widens those strips at large coordinates. Final target/axis
order preserves strict-distance ties and the original alignment dictionary's
insertion order, including later improvements that end in a tie.

Sparse queries sort only their eligible unique coordinates. Dense mostly unique
queries stream the original target/axis order instead of sorting a nearly full
list repeatedly. A direct control-point winner returns before unnecessary alignment
work. Nonfinite target snapshots or non-normalized/nonfinite constraint inputs
retain the original full sweep. Constraint vectors are never silently normalized.

The desktop builds this snapshot only for at least three constrained anchors and
more than 32 targets, once per `SnapObjectMovement` call. Small/single-anchor and
unconstrained queries retain their prior paths. The numeric record remains local
to that movement update, so changed geometry, options, exclusions and modifiers
cannot reuse stale data. No scene/history cache or serialized setting is added.
`check_group_snapping_core.py` compares exact points, flags, priorities and guides
against frozen pre-optimization code, plus full group frames and headless imports.

## Scene restoration and fitting preparation

The desktop adapter groups openings by parent identity once per fitting/validation
operation when multiple walls need validation (single-wall validation retains its
direct scan). Preserve scene order for summing lengths (including duplicates), stable
center order for fitting, and wall order for applying results and early failure.
`FitOpeningCenters` remains the arithmetic boundary; model mutations stay outside.
No grouping is retained across calls or edits.

Snapshot restoration retains full coverage and avoids redundant unchanged-record
assignments. Point comparisons must be exact, including signed zero, rather than Qt's fuzzy equality.
Fireplace depth/offset setters still run because visible values can hide stored
values requiring normalization. Lists still rebuild in snapshot order when asked.
Do not replace this with a selection-only restore: attachments, copies and a
previous frame's moved objects may extend beyond the current selection.
`check_restoration_fitting.py` compares these adapters against frozen methods.

## Measurement orchestration

`PlanMeasurementComponents` prepares ordered opening indices and selected-owner
keys for disconnected components from explicit numeric/opaque keys. Group once by
parent; keep source ordering and duplicate opening entries while deduplicating
component members. The adapter resolves indices back to desktop objects and keeps
the existing component-cache keys, selection behavior and LRU limits.

`MeasurementOpening` snapshots numeric opening geometry plus explicit mode/side,
pocket-hinge and fireplace policy. Desktop classification resolves model types;
the core never imports models. `BuildOpeningDimensions` coordinates cutter spans,
opening interruptions, one-sided measurements, hidden-opening modes and fireplace
face offsets before assembling dimensions with the existing numeric span kernel.
The native length/midpoint are explicit inputs to preserve backend rounding.

Records are prepared lazily per opening on a span cache miss, shared only within
that build. Component plans are local to one call. No new retained scene cache,
revision dependency or project field is introduced. Native path conversion,
point construction and retained graphics caches stay in the desktop adapter.
`check_measurement_orchestration.py` compares frozen desktop orchestration and
exact ordered owner identities, exercises warm/changed caches and runs component
planning/span coordination without Qt or site packages.

## Native path backend

`geometry/path_operations.py` defines an explicit backend contract for opaque path
handles and ordered local coverage clipping. `graphics/path_operations.py` owns
Qt boolean operations, containment/intersection queries, contour conversion and
stroke preparation. Geometry code imports no concrete graphics backend.

Desktop adapters bind the Qt implementation. Its boolean/query methods are direct
native descriptors, with no conversions or retained cache. Stroke preparation
returns a bound native callable whose owner remains alive for its caller. Width,
cap/join, miter, dash and curve options are explicit; omitted options retain native
defaults. Pen-based stroke construction is a separate Qt-only adapter retaining
cosmetic and dash behavior. No runtime backend switching setting is provided.

Path handles, contour order, fill rules, curves and coordinate systems belong to
the backend. Keep broad-phase checks, transformations, normalized local origins,
cache keys and boolean order at their existing owner. In particular, do not flatten
curves, batch/reorder unions or move furniture clipping to full-scene coordinates.
`ClipPathCoverage` accepts an explicit backend and already-normalized/cullable
mask stream. It preserves each sequential union, subtraction and optional clip.

A future port implements the same operations and supplies its own path/pen/building
adapters. This step retains Qt's numerical implementation; it does not supply a
JavaScript boolean engine or remove Qt from painting and path construction.
`check_native_paths.py` checks native elements/strokes and the headless contract;
`check_native_path_composite.py` checks frozen hit/collision behavior and exact
PNG/SVG composite pixels.

## Continuing the separation

Other parts of `viewport/geometry.py` still depend on Qt and shared viewport state.
Extract cohesive calculations incrementally, taking explicit numeric inputs and
returning numeric results. Retain performance caches at an appropriate owner,
with explicit inputs/revisions. Do not move widget references, painter paths,
palette globals or implicit access to viewport attributes into this package.

Remaining candidates include scene target collection/placement transactions,
group selection/attachment orchestration, Qt contour flattening, remaining native
measurement path/cache adapters and model-edit transactions/state formats. Qt path
construction, drawing, text measurement and input events remain in the desktop
layer until their own boundaries are separated. Each extraction needs behavioral
comparisons and complete-scene performance measurements; a small standalone
speedup does not establish an interactive improvement.
