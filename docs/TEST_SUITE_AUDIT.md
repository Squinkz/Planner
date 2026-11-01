# Test suite audits

## 2 November 2026

The initial complete run passed **535/557 checks**, with 22 failures. The
corrected suite passed **557/557** in a checkout containing only 1,883 Git-selected
public files, including uncommitted new source and fixtures. Private workspace
plans and diagnostic inputs were absent. The environment contains only the pinned
development dependencies on Windows/Python 3.14.3: PySide6 6.11.2 and NumPy 2.4.6.

| Verification | Result | Workers | Time |
| --- | --- | --- | --- |
| Complete clean-checkout suite, DPR 1 | 557/557 | 3 | 575.1 s |
| Focused editor suite, DPR 1.25 | 9/9 | 2 | 86.7 s |
| Focused editor suite, DPR 2 | 9/9 | 2 | 93.9 s |
| Final dense-pan and five-scale fresh-render follow-up | 2/2 | 2 | 13.8 s |

The dense-pan check was strengthened after the complete run when the additional
scaling jobs exposed its inappropriate high-DPI oracle. That one check was then
rerun at DPR 1, 1.25 and 2; the separate pan-DPI matrix was rerun unchanged. No
other Python source changed after the clean full-suite snapshot. These are
correctness runs; differing worker counts and workloads are not speed comparisons.

### Portability and missing coverage

Seven recent regression checks indirectly loaded a private local project through
benchmark helpers. They now use `checks/fixtures/editor_interactions.py`, the
existing synthetic dense-room fixture and an independently authored isolated
oblique wall. No personal project data were copied, derived into a public fixture,
or added to Git. The private plan remains ignored and untracked.

The shared matrices retain frozen/current comparisons of model state, snapping,
validation and exact rendered pixels. Endpoints are centered on screen, and the
validation matrix asserts that each tested wall actually moves. This prevents
offscreen or motionless gestures from supplying misleading rendering coverage.

The dense-pan check now compares **32 culled/unculled frames exactly**, including
edge re-entry, and retains draw-call reductions and validation-cache assertions.
Its steps are integral physical pixels at every display scale. Its original
fresh-render comparisons remain at DPR 1. At higher DPI, both cached paths share
small Qt clip-rounding differences from fresh painting (up to 4/255 in the initial
dense fixtures); the exact culling comparison isolates the optimization from
those shared differences. The independent `check_pan_dpi.py` still uses its
original fresh-render tolerances at 100%, 125%, 150%, 175% and 200%.

A runner regression exposed explicit scripts under `diagnostics/` being moved
away when a preceding parallel check's artifacts were collected. Such diagnostic
inputs now run serially, like external probes. A real two-probe regression checks
successful execution and preservation of both source files.

### Stale expectations corrected

- Acute-junction broad-phase bounds are intentionally tighter than the old frozen
  radius. Tests now require containment of the exact owner/body geometry inside
  the old conservative envelope. Frozen overlap, placement and snapping checks
  remain in place.
- Export rulers size their bands for physical text. Tests retain crop placement,
  separator, color, PNG/SVG, preview and output assertions using the current band
  dimensions. Print previews use physical border width instead of a stale digital
  border-size assumption. Free-crop/fireplace gesture fixtures select Digital
  explicitly, while workflow checkpoints retain the current Print default.
- Export snapshots now cover `borderTextSize` and `drawOpeningOutlines`, including
  nondefault values through freezing, undo/redo and save/reopen.
- Opening-symbol culling compares the scene interior, excluding the intentionally
  different editor/export ruler typography.
- All 25 changed object-render references were reviewed side by side for the
  existing physical measurement-text sizing. The other 17 images, all original
  synthetic plan inputs, crops and fonts remain unchanged. One SVG and its
  manifest entry were updated too. Workflow changes are limited to export state
  and camera; scene/selection/history/dirty-state expectations remain intact.
- Printer-Friendly Canvas now has an authored `#f3f3f3` room fill. Theme inheritance,
  contrast and live cache invalidation are still checked. The source-color audit
  permits only the exact transparent PDF compatibility-stroke operations, with
  negative tests that still reject opaque ink and unrelated functions.
- The combined ruler/zone SVG comparison permits at most 256 changed pixels,
  at most 4/255 per channel, and only beside existing ink edges. The measured
  difference was 142 pixels; flat interiors stay exact. Other border/format
  comparisons retain their original limit. The direct no-fill painter contract
  and asynchronous PNG comparisons remain unchanged.

### GitHub and scope

The Checks workflow discovers the entire `check_*.py` inventory at DPR 1 on every
push/PR, with additional independent Windows jobs for nine editor checks at 125%
and 200%. Logs, JSON reports and captures upload even on failure. The longer
frozen/current gesture matrices have 120-second base hang limits for hosted
workers; no wall-clock speed assertions were added. Other top-level Python files
in `checks/` are benchmarks, profilers, reference recorders or shared helpers.

This was a local GitHub-style validation, not a hosted Actions execution. The
uncommitted public files must be included in the eventual commit/push. No files
were staged, committed or pushed during this audit. A line/branch coverage
percentage is not claimed. Native file-dialog behavior, presentation latency and
every possible theme/object/modifier combination still require appropriate
manual or targeted testing. Diagnostic-only performance prototypes remain outside
the production regression suite.

All **920 production files**, including the **72 help files**, retain their
pre-audit hashes and inventory. Application behavior/rendering code was not edited.
Local evidence is recorded in `diagnostics/suite-audit-20261102-clean-full.json`,
`suite-audit-20261102-clean-scale1.25.json`, `suite-audit-20261102-clean-scale2.json`,
`suite-audit-20261102-pan-followup.json` and `suite-audit-20261102-verification.json`.
The checkout manifest and reviewed image differences are retained alongside them.

## 30 October 2026

The initial run found 470 passing checks and 31 failures among 501 checks.
The updated suite passed **502/502 checks** in a repository-only, clean-environment
run taking about 20 minutes. Results are recorded in
`diagnostics/full-suite-20261030-clean.json` and its text log.
Those generated files are local output, not committed test inputs.
After the final theme guard and hosted-runner timeout changes, the refreshed
checkout passed a further **14/14 focused checks**, including theme/dialog/icon
lifecycle, both heavy matrices, runner behavior, licenses and documentation.
That follow-up is recorded in `diagnostics/ci-final-followup-20261030.json`.

## Faster repeat audits

The runner now executes up to four checks concurrently, reducing the default
worker count for limited CPUs or available Windows memory. Each worker has a
disposable source copy, each check has private temporary/application state, and
generated captures are retained separately by check. Every check still launches
a fresh Python process with all existing assertions. The native font checks run
exclusively after the parallel batch. `--jobs 1` retains serial debugging.

A fixed sample of 16 checks, including editor rendering, Print, title blocks,
asynchronous preview, composite sliders, sessions and native text, passed at
every worker count in the clean Windows environment:

| Workers | Wall time |
| --- | ---: |
| 1 | 86.7 seconds |
| 2 | 50.0 seconds |
| 4 | 34.3 seconds |

The final default run passed **502/502 checks in 328.5 seconds (5 minutes
28 seconds)** with four workers, including the fixture corrections below.
The earlier serial run took 1211.3 seconds (20 minutes 11 seconds): a **3.69×
speedup**, or about 73% less waiting. The clean development virtual environment
and complete check inventory were retained. The report is
`diagnostics/full-suite-20261030-parallel-verified.json`, with its matching text
log. Disposable source workspaces were removed, and all 72 Help files still
matched the original hash manifest.

These runs were sequential, so the measurements do not compete with each other.
Reports are `diagnostics/runner-benchmark-{1,2,4}.json`. Timings are observations
on this workstation, not portable correctness gates. The runner regression also
proves concurrency using a rendezvous and verifies bounded execution, independent
source/captures, retained failure captures, ordered reports and native-check
serialization without a speed assertion.

The parallel audit also exposed a timing-dependent fixture: the furnishing-search
check inserted a synthetic wall without a committed object ID, so the activity
observer could raise when its timer ran. The fixture now obtains IDs through the
normal scene method and explicitly exercises that observer. Windows redirected
logs are forced to UTF-8, with Unicode failure coverage and immediate per-failure
records so a diagnostic cannot interrupt result collection.
The workflow check now retains one QApplication across both example windows;
recreating the application between windows could leave stale Qt model/binding
state. Four simultaneous workflow repetitions plus rendering and runner checks
passed after this fixture correction (`diagnostics/runner-workflow-lifetime.json`).

## NumPy comparison and containment follow-up

The pan-DPI, pan-wall-patch, live-edit raster, annotation, chamfer, angled-mask and
dense-occlusion checks now replace full-image Python scans with NumPy operations.
Stored bytes, changed-pixel versus changed-channel counting, signed errors,
QColor unpremultiplication where previously used, and all tolerances are retained.
Comparisons view the existing QImage storage, respect row padding, and gather
only changed pixels for detailed errors. They do not build full-image signed
copies for sparse pan/edit differences.

A byte-loop oracle verifies image formats, alpha, unsigned-subtraction hazards,
padding, physical pixel coordinates and source immutability. The separate
containment matrix checks the array filter against frozen geometry; see the
[editor audit](EDITOR_PERFORMANCE_AUDIT.md#numpy-containment-filtering--30-october-2026)
for timings and scope. Geometry and texture processing share the same lazy,
single-thread-budgeted NumPy initializer.

Sequential before/after runs of the same ten checks, using a preserved source
snapshot for the baseline and the clean development environment, both passed:

| Check group | Before | After |
| --- | ---: | ---: |
| Ten representative checks | 61.90 s | 44.14 s |
| DPI/panning check within that group | 21.27 s | 10.41 s |

Reports are `diagnostics/numpy-before-checks.json` and `numpy-after-checks.json`.
The standalone synthetic probe measured a 1,600 × 1,000 sparse comparison at
98.42 ms versus 1.43 ms, and a 400 × 300 all-changed comparison at 63.06 ms versus
6.51 ms. These are comparison operations, not complete test or renderer timings.
Two new independent regression checks bring the inventory to 504 checks.
The final clean-environment default run passed **504/504 in 342.8 seconds
(5 minutes 43 seconds)** with four workers. Its report is
`diagnostics/full-suite-20261030-numpy.json`. Whole-suite timings also include
the new regression checks and ordinary machine variation; the controlled
ten-check comparison above measures the affected group directly. All 72 Help
files still matched the pre-audit hash manifest, and worker copies were removed.

## Corrections and coverage

- Updated renamed controls, section order, project/recovery Build-tab policy,
  reference-editing state after Save, and explicit Export dimension controls.
  Grid/reference shortcuts remain blocked on Export.
- Updated painter observers for retained dimensions and outlined text. The painter
  lifetime check now exercises both QPicture fallback and retained-layer failure.
- Scoped the pre-reserved-door frozen movement/fitting matrices to ordinary
  openings. Current Pocket/Barn support, group last-valid behavior and rotations
  retain independent assertions in the reserved-door core/junction/wall-edit checks.
  Placement roundoff gets a 1e-12 fraction / 1e-8 mm allowance; identity and flags
  remain exact.
- Preserved compound collision checks using the shipped chair positions, adding
  an explicit open gap. Door tests now verify swing strokes precede the jambs.
- Kept dense curved-clip differences within tight aggregate bounds and required
  every changed pixel to stay next to frozen-reference ink edges. Independent
  native path and occlusion checks still verify geometry and filled regions.
- Reviewed 28 of 42 render images for outlined glyphs, jamb draw order and physical
  SVG sizing. Original project inputs and unchanged images remain. Added the
  existing guide Depth property to the object matrix; workflow reference changes
  are limited to Export camera offsets.
- Covered D-DIN Condensed Bold with its existing complete OFL notice and provenance.
  Printer-Friendly Canvas intentionally keeps its room fill white.
- Added runner regression checks for isolated state, assertion/Qt callback/thread
  failures, Unicode logs, nonzero exit codes and timeout reporting. GitHub uploads
  both human-readable output and per-check JSON diagnostics.
- Gave the dorm-opening-mask and Print-paper matrices 60-second hang limits:
  they took 15.4 and 12.2 seconds locally and need headroom on hosted Windows.
  Their rendering/geometry assertions remain enabled.
- Added a standard-message-box theme regression and fixed its enum-valued `icon()`
  handling. Theme refresh continues to refresh registered QIcons and preserves
  Qt's standard warning icon.

## CI verification

The checkout-style run copies only files selected by Git, including new source
and checks, into an isolated directory. It uses a fresh virtual environment with
only the pinned development dependencies: PySide6 6.11.2, its matching Qt bindings,
and NumPy 2.4.6, on Windows/Python 3.14.3. It enables the same offscreen/UTF-8
settings as the GitHub Windows job. The workflow itself remains the remote gate;
this local run does not claim that uncommitted changes have run on GitHub.

An additional Windows 8.3 temporary-path run passed all eight checks for runner
isolation, preferences, project/session recovery, reference images, export
destinations, project transitions and resource paths. The temporary root included
`RUNNER~1` aliases, exercising the canonical-path comparisons used on hosted runners.

The user-maintained `planner-main/help/` folder is excluded from editing. Its
72 files are checked against hashes captured before the audit. Historical gallery
captures and their original environment descriptions retain their provenance;
current technical contracts and the scenario index describe the newer features.

## Repeat

```powershell
python -m pip install -r requirements-dev.txt
python checks/run_checks.py --report diagnostics/check-results.json
```

Use `checks/README.md` for focused checks and the runtime/renderer audits for
workload-specific performance measurements. Correctness checks primarily assert
geometry, pixels, cache/preparation counts and lifecycle behavior; timeout limits
are hang protection, rather than portable performance targets.
