# Export interaction performance audit — 2026-10-29

The largest repeated cost was regenerating the complete SVG scene when only the
crop or border changed. Print mode also regenerated every selected page at each
border/title-block edit. These are now separated from interactive drawing.

## Measurement

The diagnostic uses `demos/scissor_med.plan` in an isolated offscreen window,
with a 1000 × 800 viewport. It measures Digital, Architectural and Print modes
in PNG and SVG, at 300 PPI for physical exports. Print selects two full pages.
Each interaction has five samples; the table shows median milliseconds for an
edit plus its preview paint. Cold and settled paints are measured separately.
Python profiling is enabled in both runs, so these numbers include its overhead;
they are local comparative measurements, not universal frame-rate guarantees.

Reproduce with:

```powershell
python diagnostics/audit_export_interactions.py after
```

Raw results and per-action cumulative profiles are in
`diagnostics/export-performance/before.json`, `after.json`, and adjacent text files.
The diagnostic does not modify the demo or the user's project/session/preferences.

## Results

| Interaction | Before (ms) | After (ms) |
| --- | ---: | ---: |
| Digital PNG crop drag | 57 | 31 |
| Architectural PNG crop drag | 58 | 28 |
| Digital/Architectural PNG border drag | 55–58 | 40–41 |
| Digital/Architectural SVG crop drag | 1,639–1,837 | 29–32 |
| Digital/Architectural SVG border drag | 1,653–1,829 | 32–34 |
| Print PNG border editing | 344 | 41 |
| Print SVG border editing | 2,334 | 45 |
| Print PNG title-block toggling | 332 | 12 |
| Print SVG title-block toggling | 2,262 | 11 |
| Print PNG/SVG page-offset dragging | 31–32 | 28–29 |
| Cached panning across modes | 4–13 | 4–9 |

Panning and moving a crop within cached coverage do not rebuild the plan.
Print crop updates retain page artwork and generally take 8 ms; a first SVG
view-cache refresh can still take about 39 ms. The first SVG pan creates its
navigation bitmap and can take about 56 ms, followed by cached paints near 5 ms.

## Changes

- Cache a padded SVG scene independently of the crop and border. Crop updates
  change the visible clip; expanding beyond captured coverage rebuilds the scene
  once. Palette recoloring and the alternate solid-fill cache remain supported.
- Record ruler commands once per frame geometry. PNG retains native-density
  raster strips during both crop/slider drags and rest, for all border styles.
  Cache refusal or oversized strips use small visible raster tiles rather than
  direct vector replay. SVG borders continue to use vector commands.
- Reuse a right-hand title-block bitmap when only the crop width changes, and
  avoid recording an unused vector title block for raster previews.
- Reuse the Planner logo renderer and the most recent custom-logo decode.
  Updating the Planner SVG on disk invalidates its cached renderer.
- While Print border/title-block settings change, reuse the existing drawing
  context and render only decorations. Refresh full-quality pages after 180 ms
  without another edit. Page-offset dragging retains its existing fast path.

## Remaining costs

The first audit left full-quality Print SVG regeneration at 1,983–2,016 ms for
two pages after editing settled. The subsequent shared-vector change removes
that repeated construction/parsing cost:

| Full-quality Print SVG refresh | First audit (ms) | Shared vectors (ms) |
| --- | ---: | ---: |
| Border changes | 2,016 | 87 |
| Title-block changes | 1,983 | 84 |
| Page-offset changes | 2,015 | 87 |

Print now retains one transparent model SVG shared across pages. Each page
records its grid/room background, border and title block as native vector
commands. Page cuts retain independent clipping and drawing origins; font paths,
material patterns and furnishing strokes remain vector artwork. No SVG generation
or parsing is required for a settled frame-only change. Exported files continue
through the original complete-page renderer.

Raw follow-up timings are in `diagnostics/export-performance/shared-vectors-final.json`.
The first Print SVG preview still prepares the drawing once and takes about
1.76 seconds in this fixture. Actual model/annotation/style changes invalidate
that model cache. Tight vector budgets fall back to individually clipped SVG
pages instead of requiring the complete model to fit in memory. PNG full-quality
page refreshes remain about 300 ms for two pages.

The prepared PNG scene follow-up below removes most of that repeated setup cost.

Raster border edits still spend time laying out and painting ruler text and the
title block. At 40 ms per step they are improved, but do not consistently meet a
16 ms frame budget on this workload.

Retained raster memory remained within the configured budget at every measured
step. Print retained about 41–106 MiB depending on format and interaction; other
modes retained about 18–44 MiB. These counters exclude Qt/XML vector allocations.

## Verification

Focused checks cover scene and title-block cache reuse, SVG coverage expansion,
decoration-only updates followed by full page refresh, native SVG borders,
preview/export border and recoloring parity, compositing, outlined SVG text,
memory-budget fallbacks, export undo/redo, centred scaling, and physical PPI
scaling. Their scene-cache assertions check rebuild counts rather than timing
thresholds, so routine timing variation does not invalidate them.

## Appearance follow-up (29 October)

Extended the same isolated scissor-demo audit to line colors, canvas colors and
whole themes. Print SVG was still regenerating the complete model for each RGB
edit, despite the semantic recoloring support already used in other SVG modes.

| Print SVG interaction | Before (ms) | After (ms) |
| --- | ---: | ---: |
| Line color | 1,901 | 472 |
| Canvas color | 1,887 | 483 |
| Whole theme | 1,997 | 1,729 |
| Cold preview | 1,944 | 1,754 |

Color and theme figures are medians of three updates under cProfile. Cold setup
is one sample per run, so its smaller improvement should be treated as indicative.
Raw profiles/results are `followup-before` and `palette-final` in
`diagnostics/export-performance/`.

Print now recolors its retained model and reloads only affected SVG layers.
RGB edits do not regenerate SVG geometry, decode the project, or parse clipping
paths. Opacity, actual model/style changes and other geometry-affecting changes
still invalidate the model. Grid and page decorations refresh independently.

SVG layer serialization now builds Unicode XML in memory and encodes it once,
avoiding repeated encoding of thousands of small fragments. Physical SVG output
sets its dimensions during material processing, eliminating a second complete
XML parse/serialization pass. This also benefits Architectural exports and files.

Focused checks compare the recolored model with a fresh render, verify clip reuse
and opacity invalidation, and cover SVG layer/material parity, physical sizes,
page preview/export parity, title blocks and compositing. Raster retention remains
within budget (41 MiB at rest in this Print SVG fixture).

The remaining color-edit cost is mostly layer XML serialization/reloading and
rebuilding the raster context outside selected pages. Whole-theme changes still
rebuild the model, and cold SVG setup remains substantial. Full-quality Print PNG
refreshes remain another target: they repeatedly prepare an offscreen scene for
each page. Those costs are not resolved by this follow-up.

## Prepared PNG scenes (29 October)

Print PNG pages now share an independent prepared render viewport through
`ExportSceneCache`. Project decoding, export-only object filtering, room detection,
wall geometry and furnishing SVG renderers survive page cuts and frame edits.
The same cache is used by the PNG batch export worker, including optimized PNG.
Rendering and file output continue through `RenderPlan`.

| Two-page Print PNG interaction | Before (ms) | After (ms) |
| --- | ---: | ---: |
| Cold preview | 513 | 431 |
| Full-quality refresh after border edit | 340 | 108 |
| Full-quality refresh after title-block edit | 321 | 97 |
| Full-quality refresh after page-offset drag | 335 | 98 |

These are the same isolated scissor-demo cProfile probes as earlier, recorded in
`diagnostics/export-performance/png-scene-before.json` and `png-scene-after.json`.
Cold and settled refreshes are individual samples; the repeatable regression
checks assert preparation counts and exact pixels rather than elapsed time.

The cache compares scene/settings/catalog values with an independent snapshot,
so replacing a project snapshot or mutating one in place cannot accidentally
reuse stale geometry. Colors, fonts, visibility, measurements
and scene changes invalidate preparation. Explicit wall/room paint styles now
refresh the retained viewport without decoding/preparing its geometry again.
Crop, page origin/overlap coverage,
paper dimensions, title blocks, borders, PPI, sampling, grid origin and effects
are resolved for each page. Sampling or PPI changes rebuild the furnishing map
when its compensated stroke width changes, while retaining scene preparation.

Only one prepared scene and one furnishing map are retained. The preview releases
them when leaving Print/Export, changing project, or switching to SVG. The worker
releases its scene on completion or failure. Drawing errors discard the cache.
The editor's live objects are never borrowed or modified. Retained raster memory
is unchanged at 104.6 MiB at rest in this fixture; the extra model/vector data is
not included in that raster counter.

`check_export_scene_cache.py` verifies single preparation across different cuts,
densities, sampling levels, border sizes, title-block positions, architectural
scales, grid origins and effects. Each page is compared exactly with a fresh
render, including PPI metadata. It also covers invalidation, failure recovery and
preview cleanup. Existing checks cover multi-page worker PNG/SVG output, optimized
PNG, print overlap, physical density, vector sharing and compositing.

Remaining settled PNG work is now primarily painting the page/grid/rulers/title
block, rather than repeatedly decoding and preparing the scene. The cold preview
still prepares both the surrounding context and the independent export scene.

## SVG zoom follow-up (29 October)

The small demo did not reproduce the reported stall: navigation was already
4–10 ms there. An isolated copy of the saved recovery scene did reproduce it at
a 2000 × 1200 viewport. Its shared drawing had 11,149 SVG layers replayed for each
of four pages, including thousands of masks and paths outside each page's clip.

| Recovery-scene zoom interaction | Before (ms) | After (ms) |
| --- | ---: | ---: |
| First overview zoom frame | 794 | 19 |
| Repeated overview zoom frame, median | 17 | 11 |
| Sharp refresh at overview | 1,283 | 288 |
| Sharp refresh at 4× zoom | 918 | 190 |
| Sharp refresh at 16× zoom | 642 | 66 |
| Sharp refresh at 64× zoom | 379 | 35 |

SVG preview layers now have a spatial index of their rendered geometry intersected
with their clip bounds. Queries account for the painter's transforms, physical
device size, clipping and cosmetic-stroke fringes. Off-screen layers never submit
their clip paths or SVG renderer commands. RGB recoloring retains the index.

Print navigation also seeds a page bitmap from the previous sharp viewport image
when that entire page was visible and the cache budget permits it. This removes
the expensive first replay just to construct navigation bitmaps. Partial-page and
constrained-budget cases retain the vector rendering fallback. Sharp rendering
still resumes after the navigation timer expires.

The diagnostic `diagnostics/audit_svg_zoom.py` records timings and profiles under
`svg-zoom-session-before` and `svg-zoom-session-final` in
`diagnostics/export-performance/`. Its final run also compared all four optimized
views pixel-for-pixel with replaying every layer in the same recovery scene.
The source recovery file and project were read only.

Focused checks cover visibility pruning against the original renderer, negative
viewBox origins, clipping, rotation, nonuniform scaling, cosmetic strokes and
1.5× display scaling; the first-navigation-frame reuse check verifies zero page
vector replays followed by a sharp vector refresh. Existing SVG layer, material,
mask, recoloring and preview/export checks pass.

## Render-setting stalls and native crash follow-up (29 October)

The 404-object recovery scene reproduced multi-second Print refreshes with the
scale bar disabled. `diagnostics/audit_export_render_changes.py` reads the
recovery data into an isolated window and records profiles for scale, Solid
Objects, Solid Rooms, wall style and room style. Its Windows job limits this
diagnostic process to 900 MiB so stress cases cannot exhaust system memory.
It never writes the source project, preferences or recovery file.

Under that limit, the original nested SVG clipping sequence reproduced a native
access violation in `QPainter.setClipPath`. SVG replay now explicitly combines
the captured, occlusion and destination clips and submits one replacement mask.
It avoids the SVG engine's accumulation of complex native clip intersections.
The same capped scene, including a change from 1:50 to 1:1 and subsequent paint
changes, completes after this change. This reproduces and fixes a native crash
path; it is not proof that every possible native crash has the same cause.

Additional changes:

- Transparent-object capture reads the effective clip only after clip-state
  changes, skips background booleans when a conservative bound is entirely
  inside the clip, and omits redundant per-stroke masks. Necessary overlaps and
  passage masks remain intact.
- Furnishing-map copies retain their source for lazy solid variants instead of
  reparsing artwork in temporary capture maps.
- Prepared PNG export geometry survives explicit wall/room paint changes.
  Snapshot viewports also retain their filtered scene until model inputs change.
- Solid Rooms changes only the locally drawn Print background, preserving shared
  SVG model geometry. Room style still invalidates model vectors because it
  changes passage edges.
- Print vectors cover selected drawing regions with one page of overscan;
  context bitmaps cover visible source regions with similar overscan. Coverage
  is checked before reuse, and expands when needed. A distant off-sheet object
  no longer forces an entire-project render at extreme magnification.
- Print context rasters are capped at four million pixels within the existing
  aggregate budget. Selected pages retain their normal full-quality path.
- Obsolete shared SVG renderers are freed before replacement construction,
  avoiding simultaneous ownership of both native scenes. Parsed SVG clip paths
  use an LRU bounded by 256 entries, 262,144 elements and 4 MiB of source text.

Profiled recovery-scene SVG entry fell from about 13.2 seconds to 5.8 seconds.
The 1:1 scale stress sequence completes with about 270 MiB retained private
memory after appearance changes. Full SVG model rebuilds still require substantial
work; this pass does not make every rendering change instantaneous. Profiles
include Python profiling overhead and are intended as comparative measurements.

Checks cover native clip submission, independent frozen PNG/SVG pixel parity,
cache invalidation and bounds, source-map reuse, geometry reuse across paint
styles, coverage bounded despite distant objects, preview/export consistency,
compositing, raster budgets and renderer lifetime during replacement.

## Responsive raster and SVG rebuilds (30 October)

The remaining raster delay was confirmed without the profiler: the 404-object
recovery scene blocked for about 1.13 seconds on a scale edit and 0.50–0.85
seconds on appearance changes. The earlier 5.8-second SVG measurement included
Python profiling overhead; it was not an interaction-response target.

Preview scene painting now runs in one persistent, separate Qt process for PNG
and SVG, in Digital, Architectural and Print modes. The process retains prepared
PNG/SVG viewports, uses the editor's platform/font/style/theme, and coalesces each
preview slot to the most recent request. Appearance generations discard obsolete
queued work/results. Completed buffers enter the existing raster/vector caches;
file export continues through its existing independent renderer.

Selected sheets are queued before surrounding context where the native PNG
allocation fits the budget. The old context image remains visible while its
replacement is pending. SVG model generation runs separately; native layer
adoption and viewport painting remain in the editor.

Unprofiled measurements on the same recovery scene:

| Edit | PNG input response | PNG selected sheet ready | SVG input response | SVG selected sheet ready |
| --- | ---: | ---: | ---: | ---: |
| Scale | 56 ms | 606 ms | 133 ms | 1,494 ms |
| Solid Objects | 95 ms | 451 ms | 174 ms | 1,464 ms |
| Solid Rooms | 58 ms | 483 ms | 213 ms | 327 ms |
| Wall style | 57 ms | 499 ms | 135 ms | 1,000 ms |
| Room style | 45 ms | 436 ms | 118 ms | 986 ms |

Cold entry, including worker startup, showed its selected sheet after about 1.25
seconds for PNG and 2.20 seconds for SVG. Surrounding context can finish later.
This removes the synchronous full-scene stalls; it does not make every complete
vector rebuild take less than a second. The comparison explicitly separates
input response, selected-sheet readiness and completion of background context.
Raw timing runs use `verified-raster-responsive` / `verified-svg-responsive` with
`diagnostics/audit_export_render_changes.py ... async timing [svg]`.

Other hot-path changes:

- Transparent furnishing capture realizes the solid variant directly, avoiding
  construction of unused transparent and background-mask renderers. Realized
  snapshot maps survive subsequent captures.
- Ordered occluder queries use a spatial index instead of checking every later
  mask for every stroke. Frozen raster/vector comparisons retain exact pixels.
- Compatible SVG layers share one native SVG document and are rendered by ID.
  Invisible bounds anchors preserve cosmetic strokes; separate ink bounds keep
  visibility culling effective. Duplicate IDs, root opacity and global CSS use
  the existing independent-document fallback. Recoloring reloads the shared
  document once while retaining clips/indexing.
- Internal SVG preparation passes an owned ElementTree through material/color
  processing rather than repeatedly parsing and serializing it. The private
  worker transport preserves that tree. PNG transport copies lossless raw image
  data directly into its admitted QImage without PNG compression.
- Native rendering failure or a 30-second timeout ends the child process rather
  than the editor. Windows workers have a 768 MiB process-memory limit. Cached
  transfer files are bounded by 32 entries and twice the viewport raster budget.
  Leaving Export, switching projects and accepting window close stop the worker
  and clear its temporary files; failed/cancelled close keeps the editor active.
  Worker memory is separate from the editor's aggregate raster budget; per-process
  memory figures in the diagnostic are not aggregate RAM measurements.

Transient bitmap allocation failures now discard the worker's prepared scenes,
normal-map/lighting caches and Qt pixmap cache, process deferred scene deletion,
and retry the same job once. The failed render unwinds before caches are freed.
This prevents a single failed title-block allocation during texture adjustments
from becoming a sticky error result until the user toggles an export option.
The worker's memory limit, output resolution and ordinary warm-cache path are
unchanged. Persistent allocation failures and unrelated validation errors still
propagate normally.

`check_preview_allocation_recovery.py` injects title-block and MemoryError
failures into the real worker during texture-angle changes. It verifies exactly
one retry, fresh preparation with texture caches released, the same worker PID,
exact final export pixels, the viewport budget, and bounded persistent-failure
handling followed by recovery on a subsequent valid request.

`check_export_preview_process.py` drives the real worker/event loop. It compares
PNG pages exactly with direct exports, including title block, scale bar and
compositing, tests rapid edits/stale results, keeps UI timers running during
rendering, exercises all three scale modes and both formats, propagates a worker
validation error and a terminated/restarted worker, and checks project/window cleanup. Core renderer checks use an
explicit synchronous test setting to inspect preparation, clipping and cache
invalidation independently of process scheduling.

## Repeated bounds calculation during navigation (30 October)

The next profile found that every Print repaint traversed all visible objects
to calculate automatic bounds. SVG preparation could repeat the same traversal
again within that frame. This includes capturing opening symbols and realizing
furnishing renderers, even when only the camera or crop changed.

The export overlay now retains one bounds tuple keyed by the full scene render
key, scene revision, viewport font, units and furnishing-map identity. All
preview coverage paths share it. Geometry, visibility, definitions and font
changes invalidate it; unsuccessful empty-scene calculations are never cached.
The standalone bounds function and file export remain unchanged.

On the current 404-object recovery snapshot (Print 1:20, portrait), 20 warm pan
frames measured without profiling gave:

| Format | Uncached median / maximum | Cached median / maximum |
| --- | ---: | ---: |
| PNG | 23.93 / 29.68 ms | 7.06 / 8.54 ms |
| SVG | 54.71 / 67.01 ms | 5.20 / 10.51 ms |

Reproduce using `diagnostics/audit_export_render_changes.py <label> async timing
one navigation [svg]`, adding `uncachedBounds` for the original calculation.
These figures measure warm panning, not cold rendering. Cold SVG preparation
still took about five seconds on this snapshot at its current scale; caching
bounds does not remove that remaining work.

`check_export_model_bounds_cache.py` compares cached and uncached preview pixels
in all three scale modes and both formats, checks that navigation/frame changes
avoid traversal, and compares against freshly calculated bounds after mutable
geometry, visibility, furnishing, font, project replacement and empty-scene edits.

## Unused lumber clip during full rendering (30 October)

Call-site timing isolated another large cost: `DrawScene` installed the compound
building clip for lumber cross-lines before checking whether any visible lumber
wall needed them. On the 404-object snapshot, this unused operation consumed
about 3.28 seconds across SVG model/context preparation. The same clipping logic
was already deferred until needed during panning.

All rendering now defers this clip until the first visible four-sided lumber
wall. The existing compound clip, per-owner clip and opening cuts are retained
when cross-lines are drawn. PNG and SVG exports share the change; rendering
quality and the worker scheduling policy are unchanged.

Unprofiled Print SVG selected-sheet readiness on the same recovery snapshot
fell from about 5.2 seconds to 1.6 seconds on cold entry. A scale edit completed
its selected sheet in about 0.86 seconds after the change. PNG cold readiness
was about 1.03 seconds, with appearance replacements around 0.66–0.71 seconds.
The gain depends on the scene: visible lumber walls still require their clip.
Run `diagnostics/audit_export_render_changes.py <label> async timing [svg]`.

An isolated before/after comparison used the original eager-clip method and
the updated method against the same scene data, fonts and palette. All 16
cases had exactly equal PNG or rasterized SVG pixels, covering Brick/Lumber,
angled walls, doorway cuts, furnishing occlusion, solid/transparent objects and
full/partial crops. Existing checks also cover native SVG masks, hatch sampling,
Print caches/gestures and Build scene/pan caches.

## Furnishing preparation across preview densities (30 October)

Native PNG pages, sampled context previews and SVG models often request
different furnishing stroke widths. The neutral preparation cache previously
included that width for every asset, repeating SVG validation, font measurement,
authored bounds and fixed-detail setup even when width could not affect them.

Artwork without any dash declarations now shares neutral preparation across
widths. Dashed artwork retains the original width-specific cache, including
inherited, inline and stylesheet declarations. Final recoloring, stroke width,
selection/error policy and native renderers remain independent per request.
The existing 128-entry / 8 MiB source bound remains in place, with content,
canvas font and nominal dimensions still part of the cache key.

On the recovery scene, profiled `FurnishingRenderer` time fell from roughly
0.48–0.54 seconds to 0.26 seconds. Unprofiled PNG appearance replacements were
about 0.61–0.66 seconds versus 0.66–0.72 seconds before; overall SVG refresh time
changed little. This is a smaller gain than removing the unused lumber clip.
Finished native-renderer sharing was also evaluated but removed because it
showed no reliable end-to-end benefit on this scene.

`check_furnishing_preparation_reuse.py` verifies one compatible preparation
across three widths, separate preparation for dashed widths, and exact PNG and
rasterized SVG pixels against fresh preparation. Cases include real washer
lettering, authored bounds, fixed-size details, rotation, nonuniform scaling and
solid/transparent backgrounds. Existing font, dash and export-process checks
cover invalidation and integration.

## Cold SVG clip decoding (30 October)

The remaining cold wall builds were traced by viewport and caller; most belonged
to separate render contexts rather than repeated geometry within one context.
Another bounded improvement targets SVG clip decoding during preview adoption.
The parser now decodes command case/argument count only when a command changes,
and queries Qt's current path position only for relative or horizontal/vertical
segments. Absolute move/line/curve segments avoid those native calls. Path
coordinates, fill rules, command support and the bounded clip LRU are unchanged.

On the recovery scene's 59 unique clip paths, eight cold-cache runs gave median
decoding times of 40.49 ms for the frozen parser and 26.54 ms for the updated
parser. Every resulting QPainterPath matched exactly. This saves roughly 14 ms
during cold SVG clip adoption; it is not a claim of a comparable percentage
reduction in full preview refresh time. PNG rendering is unaffected.

`check_svg_clip_parser.py` adds 39 exact frozen-reference cases covering relative
and absolute commands, implicit repetitions, mixed commands, curve control
points, subpath closure, signed/exponential values, fill rules and independent
cached values. Existing SVG pixel/culling and real preview-worker checks verify
the displayed result and integration.

## Raster page/context cache interference (30 October)

Profiling inside the actual worker exposed a larger raster issue than clip
decoding: native PNG pages and sampled surrounding context alternated through
one ExportSceneCache. Different sampling widths repeatedly replaced furnishing
maps; differing context inputs could also evict preparation. The worker now
retains independent caches by format and page/context role. Overview and zoom
detail share their context role. There are at most four role/format entries,
created lazily, within the existing 768 MiB worker-process limit.

Bitmap adoption no longer prepares another local export scene in the editor.
SVG page backgrounds/decorations explicitly prepare their required local source;
raster rulers still configure their presentation metadata independently.

Another blocking cost came from realizing every furnishing renderer merely to
calculate culling bounds. Prepared ordinary artwork has an exact, paint-independent
viewBox. Its cached viewBox is now available without constructing a native
renderer, letting off-page artwork stay unrealized. Custom authored bounds can
include protruding ink and always keep the existing native-renderer calculation.
Cache lookup still validates source contents, canvas font, nominal dimensions
and width/dash compatibility; geometry is copied out of the bounded cache.

Unprofiled repeat runs on the 404-object Print recovery scene:

| Raster operation | Before | After |
| --- | ---: | ---: |
| Scale edit: selected pages ready | 402–431 ms | 285–313 ms |
| Scale edit: complete context refresh | 672–720 ms | 549–617 ms |
| Solid Objects: immediate input response | 247–262 ms | 78–84 ms |
| Solid Rooms: complete context refresh | 1,349–1,434 ms | 982–1,064 ms |

Other appearance timings were mixed; selected-sheet replacement is not universally
faster. Cold PNG startup increased modestly in some runs because the separate
context must prepare once. The main benefit is warm edits and reduced editor
blocking. Main-process retained private memory was about 195–196 MiB after the
changes; that excludes worker memory and is not an aggregate RAM claim.

`check_export_preview_cache_roles.py` drives the production worker through a
recording shim, verifies distinct page/context viewport ownership, retention
across alternation, exact pixels for six images and cleanup. The real asynchronous
preview check rejects any duplicate local scene preparation during PNG adoption.
`check_export_furnishing_culling.py` compares solid/transparent PNG and rasterized
SVG pixels against the original eager-renderer path, verifies off-page native
construction is skipped, and retains authored/flipped/protruding bounds.

## Retaining exact raster capture commands (30 October)

The next worker profile showed repeated transparent-object capture and
measurement preparation after background-only edits. Temporary solid-renderer
swaps inside transparent drawing were also going through the viewport's scene
edit observer. Restoring a borrowed renderer map consequently changed the
appearance revision and discarded prepared measurements, despite no scene edit.
Those internal swaps now restore the exact original map objects without reporting
an edit. Actual UI replacements retain the existing observed assignment path.

PNG previews with a retained ExportSceneCache can reuse the existing
ObjectPaintDevice command sequence and scene state. Room grid suppression,
title text and compositing changes can replay the same exact Qt paths, pens,
brushes, masks and transforms while drawing their changed backgrounds/frames
normally. Wall/room style, scene edits, crops, scale, sampling clearance, fonts,
paints and render hints remain part of invalidation. Labels and annotations
continue through the normal rendering path, with measurements no longer falsely
invalidated by the temporary map swaps.

Each viewport retains at most four captures, 8,192 commands, 262,144 path
elements and 16 MiB of embedded images. Oversized captures still render but are
not retained. This operates within the existing worker process-memory limit;
file exports and SVG models do not enable this cache. A QPicture prototype was
discarded after exact comparisons detected one-channel rounding differences.
The retained production path uses the original capture objects and has exact
pixel parity with direct rendering.

Unprofiled repeat runs on the same 404-object recovery scene:

| Raster operation | Before this pass | After |
| --- | ---: | ---: |
| Solid Rooms: selected pages ready | 597–681 ms | 352–355 ms |
| Solid Rooms: complete context refresh | 982–1,064 ms | 503–522 ms |
| Wall style: complete context refresh | 1,025–1,038 ms | 731–774 ms |
| Room style: complete context refresh | 1,191–1,228 ms | 953–971 ms |

Scale changes still require new model capture; their timings were broadly
unchanged. Solid Objects still requires capture when switching to transparency.
These figures are operation-specific, not a claim of a universal refresh gain.

`check_raster_capture_reuse.py` verifies capture hits without rebuilding a paint
device, exact backgrounds/title/compositing pixels, preserved renderer identities
and scene revisions, measurement reuse, changed-style/crop/density invalidation,
bounded retention and project edits. Real-worker, frozen native PNG/SVG, clip,
hatch, page gesture and editor-cache checks cover integration. Editor tests also
run with render-revision verification enabled.

## Live composite slider previews — 30 October 2026

Print-mode composite sliders previously requested complete worker-rendered pages
for every value. A newer value made the previous result stale before it could be
displayed, so continuous dragging could appear frozen until release.

Vignette and texture sliders now use the existing interactive page preview while
held. The shared plan context is reused, and decoration cache keys exclude
composite values. Decoration bitmaps contain no baked effects; the current
texture and vignette are painted once across each complete page, including its
border and title block, using that page's output pixel dimensions. Other slider
types retain their existing handling. The gesture still creates one undo entry.

Full-page worker prefetching is suppressed during composite drags. Releasing the
slider restores the ordinary complete-page preview, whose key still includes all
effect settings and whose pixels match file export exactly. Export rendering is
unchanged; Digital and Architectural previews retain their existing live effects.

`check_composite_live_preview.py` reproduces a held-slider drag with the real
worker, checks changing viewport images before release, verifies reuse of the
plan context and decorations, and rejects full-page render requests during that
drag. It also covers every texture slider across scale modes, title-block effect
coverage, undo/redo, final export parity and the raster budget.

The application mouse filter starts a gesture before the slider's pressed signal.
It now passes the actual watched control, and the slider signal also passes its
source explicitly. A later slider notification can classify an already-started
gesture without creating another undo entry. The regression uses mouse press,
held-button moves and release, and requires automatic viewport paints before any
forced image capture; programmatic slider-state changes alone missed this path.

## Exact native texture-lighting expansion — 30 October 2026

Angle, highlights, midtones and shadows invalidated the lighting tile. The
previous implementation walked every normal-map pixel in Python, even though
only its red and green bytes affect lighting and there are at most 65,536 pairs.
The selected wrinkled-paper map has 1,048,576 pixels but only 9,120 such pairs.

A one-entry preparation cache now retains the exact pair lookup for the current
file and modification stamp. Lighting arithmetic and Python rounding remain
unchanged for each distinct pair. The standard library's native charmap encoder
expands the resulting four-byte colors across the image, replacing the repeated
Python pixel loop. No GPU path, extra dependency, color quantization, reduced
texture resolution or changed shader arithmetic is introduced. UTF-32 with
surrogate-pass preserves all 65,536 keys as individual pixels, including adjacent
surrogate-valued pairs. Both preparation and final lighting caches hold one map.

An isolated copy of the current recovery scene (161 objects), with four selected
A4 landscape pages at 300 PPI and a 1000 × 800 viewport, gave these warm medians:

| Adjustment | Previous full preview refresh | Current |
| --- | ---: | ---: |
| Angle | 231.82 ms | 48.30 ms |
| Highlights | 232.29 ms | 49.41 ms |
| Midtones | 232.75 ms | 47.96 ms |
| Shadows | 230.17 ms | 49.02 ms |

The tile calculation alone fell from 216.30 ms to 35.26 ms. Complete viewport
images matched exactly in all four comparisons, with no page-decoration renders
during the measured adjustments. These timings include setting changes and
synchronous viewport grabs; they are not measured input-to-display latency.
Reproduce with `python tools/composite_lighting_probe.py`. The tool does not
write the recovery project and saves results in `diagnostics/`.

`check_normal_lighting_cache.py` compares every red/green pair against the frozen
previous pixel loop across eight angle/lighting combinations. It also verifies
lookup reuse without rereading the map, surrogate handling, file replacement,
changed dimensions and bounded cache entries. Existing texture, AO, mapping,
vignette, actual mouse-drag, title-block and asynchronous export checks cover
the rest of the rendering pipeline.

## NumPy CPU texture lighting — 30 October 2026

The remaining per-color Python loop and charmap expansion are now replaced with
NumPy CPU arrays. A one-entry preparation cache owns a two-byte index per texel,
the exact unique red/green keys, and double-precision normal coordinates.
Lighting retains the previous arithmetic order, scalar trigonometry and
ties-to-even rounding; a temporary RGBA palette expands with native array
indexing. The resulting QImage owns a copy of its bytes, independent of cache
eviction and temporary arrays. No texture resolution, filtering, page rendering
or composite interaction behavior changes.

NumPy is a runtime dependency, pinned to 2.4.6 for development/builds. Its import
is deferred until a normal texture needs rendering. The existing one-map cache
bounds remain; indexes use 2 MiB for the 1024 × 1024 example. The build collects
NumPy and its distribution metadata, including all accompanying licenses.

On the same isolated 161-object scene, four A4 landscape sheets at 300 PPI and
a 1000 × 800 viewport, warm synchronous refresh medians were:

| Adjustment | Standard-library palette | NumPy |
| --- | ---: | ---: |
| Angle | 47.51 ms | 16.94 ms |
| Highlights | 47.18 ms | 15.89 ms |
| Midtones | 47.60 ms | 16.12 ms |
| Shadows | 47.84 ms | 17.33 ms |

Lighting alone fell from 33.92 ms to 3.94 ms. Complete viewport images matched
exactly for every adjustment. These are setting-update plus synchronous-grab
timings, not input-to-display latency. The benchmark now defaults to comparing
against the immediately preceding palette implementation; `--baseline original`
retains comparison with the original per-pixel renderer.

The exhaustive lighting check now covers all 65,536 input pairs at 32 settings,
including deterministic random values, zero strengths and cardinal angles. It
checks exact pixels, lazy importing, reuse without rereading the map, file and
dimension changes, buffer ownership after eviction, and bounded caches. Existing
texture, AO, mapping, vignette, live mouse-drag, title-block, asynchronous worker
and print-preview checks cover integration.

Validation passed the ten focused rendering checks, the About/licenses check,
and the real held-mouse four-page probe. An isolated Windows bundle built with
the pinned build environment also passed its packaged smoke test, including
textured PNG, SVG, optimized PNG and NumPy's accompanying notices; the regular
`dist/Planner` distribution was not replaced.

## Bound the unused BLAS runtime — 30 October 2026

The NumPy wheel's OpenBLAS backend initialized a large unused thread pool on
this Windows machine. In a fresh Python process, default NumPy import raised
private committed memory from 8.3 MiB to 629.1 MiB. Configuring
`OPENBLAS_NUM_THREADS=1` before import instead raised it from 8.0 to 18.5 MiB.
Texture lighting uses elementwise operations rather than BLAS, so that pool
provided no rendering benefit. Its overhead left the preview worker close to
the existing 768 MiB cap, where Qt bitmap allocations and native rendering
could fail. Retrying an allocation could not remove the initialized pool.

Both the editor and worker now load NumPy through one cached initializer that
sets this backend's thread count before import, overriding a high inherited
setting. The initializer remains lazy, preserves CPU array arithmetic and
does not change Qt's own rendering threads or the worker's memory limit.

On the read-only recovery scene, with its saved Print settings and a 2068 × 843
viewport, 120 successive completed angle edits held worker private memory at
about 99.5 MiB, with a 146.6 MiB peak. The preceding default-pool run held about
710.5 MiB and peaked at 757.6 MiB. This is private committed memory, not download
size, working-set RAM or a claim of a leak. The isolated probe uses its own
window/session/preferences and captures native worker stderr.

The four-A4/300-PPI benchmark still gives 16–18 ms complete warm previews versus
49–51 ms with the standard-library palette, with exact image parity. Eleven
focused checks passed. `check_numpy_runtime_budget.py` starts from an unloaded
NumPy, injects a high inherited thread setting, checks initialization/reuse and
rejects the former import-time memory increase on Windows. The packaged smoke
test also requires the configured thread limit after a textured PNG render.
