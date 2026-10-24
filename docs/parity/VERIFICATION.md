# Verifying a port

[CHAMFER-01](CHAMFERS.md), added 18 October, specifies the translating corner cut
and inverted zero-to-one convention. Six independent JSON examples, 84 analytic
combinations, 144 desktop combinations (each in four object/endpoint orders),
and 18 frozen material renders cover it. Existing sharp-join parity compares new
zero with old one. Updated object/workflow/render records use the new default;
the original 17 October control-gallery images retain their historical capture.

[WALL-JOIN-01](CHAMFERS.md#wall-join-01-automatic-unequal-width-cap-clipping)
adds 432 independent comparisons for unequal two-wall outlines and material
containment, including the reported acute/obtuse vertical-wall arrangements.
Automatic body-cap clipping is required at zero as well as with manual chamfer.

## Object and workflow coverage

[OBJECTS.md](OBJECTS.md) and [EXAMPLES.md](EXAMPLES.md) add a per-type observed
matrix, two workflows with 20 frozen state checkpoints, portable `.plan` examples
and 33 object rendering cases. The matrix covers all 24 current types, whole/control point
properties, actual context actions and eight collision profiles. Workflow replay
uses desktop input/command adapters and independent assertions. Image replay
compares decoded pixels; SVG cases also check vector structure. See EXAMPLES for
commands, capture assumptions and explicit coverage limits. These references do
not certify a browser implementation or every possible multi-object interaction.

The current matrix includes paired object Position fields, Size linking, both
endpoints, and angle-guide middle/label states. Its model inventory is checked
against the scene classes so a new class cannot silently miss the matrix.
The original UI gallery remains a dated capture, not a current UI inventory.

## Three complementary references

1. **Behavior:** [cases.json](cases.json) gives stable IDs, rule IDs, starting
   conditions, actions and observable results. Its `checks` entries point to
   existing desktop regression tests, relative to the workspace (one directory
   above the application). Those tests are executable examples; they are not
   framework-independent test drivers. Reimplement their input events and
   assertions in the target framework.
2. **Visual:** [reference/GALLERY.md](reference/GALLERY.md) contains 32 actual
   desktop captures: main tabs, all four export modes, full enabled/disabled
   Composite sections, every full export section, complete Build palette, picker,
   dropdown, menu, three Settings pages and all Build settings subpages, shared
   idle/hover/pressed/disabled controls and a light-theme example. Beside each
   PNG is JSON with logical dimensions, fonts, control geometry, cursor names,
   numeric settings, dropdown contents and layout spacing. Palette JSON and
   resolved dark/light stylesheets retain the exact theme roles and selectors.
   Their generated arrow/indicator SVGs are archived under `style-assets/` with
   relative URLs, so the references do not depend on expired temporary files.
3. **Portable calculations:** [numeric-examples.json](numeric-examples.json)
   has 15 independently stated expected outputs for wall bodies, rectangular
   footprints, elliptical containment and metric/imperial grid intervals.
   Arrays represent points, sequences or function results, as specified by
   `operation`; `arguments` is a positional argument list. Boolean results must
   match exactly. Ordered sequences must retain order and length. Compare
   numeric leaves with the file's absolute/relative tolerances. Inputs must not
   be mutated. `RectangleFootprint` returns XYWH, corners, then axes.

The first fixture set is intentionally small and readable. Existing geometry
regressions cover many more cases, including ties, large coordinates, curves,
restoration and attachments. Port those cases incrementally; the 15 JSON examples
alone do not certify the complete geometry engine.

[color-popup-traces.json](color-popup-traces.json) adds five portable UI traces
with 15 individual transitions. Start a visible, unarmed popup for each trace.
`inside`/`outside` are points inside/outside its rectangle; `heldButtons` describes
buttons held **after** the event. `press`/`release` use left button, `right-press`
uses right, and `escape` is Escape key-down. After every step, assert `armed` and
`outcome` (`open`, `accepted`, `cancelled`). An adapter for a different framework
only needs to translate these events and expose these observable states. The
desktop adapter is `checks/check_parity_ui_traces.py`; it actually executes these
JSON traces. Existing color-picker tests additionally check value rollback,
field scrubbing and popup anchoring.

## Inherited Qt behavior and browser-specific acceptance

[WEB_MIGRATION.md](WEB_MIGRATION.md) covers the additional control/event/style
boundary identified in the [first-port review](FIRST_PORT_REVIEW.md).
[reference/qt-widget-defaults.json](reference/qt-widget-defaults.json) records 21
observations recorded with Qt 6.11.1/Fusion controls: deferred drafts, correction,
stepping, unfocused wheel, local text undo, contextual Escape, combo highlight/
acceptance, tab/slider keys, tree hit areas and modeless Settings Enter.
`checks/check_qt_implicit_ui.py` reproduces these observations and compares the
results without rewriting the reference by default.

[browser-cases.json](browser-cases.json) adds browser acceptance scenarios.
They are marked `requires-browser-run`; no browser execution is claimed. Named
Qt observations and desktop checks are partial evidence, not a browser pass.
Recreate the input sequences in the chosen browser automation framework, retain
the expected outcomes, and record actual engine/device/DPR results. See WEB-01
for the required control inventory and explicit adaptation register.

The gallery generator explicitly selects Fusion, matching the real app's entry
point. Its initial version omitted that selection; the reference was refreshed
during the first-port review. Metadata now names the base style explicitly rather
than relying on an unnamed QSS proxy. Production styling was not changed.

## Commands

Run from the workspace containing `checks/` and `planner-main/`:

```powershell
# Pure stdlib: no Qt or third-party imports, also suitable for CI without Qt.
python -S checks/check_portable_parity.py --numeric-only

# Examples, scenario index integrity and real project decode/encode.
python checks/run_checks.py check_portable_parity.py check_parity_ui_traces.py

# Native defaults missing from an ordinary React/HTML component mapping.
python checks/run_checks.py check_qt_implicit_ui.py

# Key UI rules, using the established isolated Qt runner.
python checks/run_checks.py check_color_picker.py check_drag_spinboxes.py check_slider_dragging.py check_canvas_cursors.py check_stacker_submenu.py check_export_dropdowns.py check_popup_dialogs.py check_export_scale_modes.py check_export_history.py check_measurement_menu_eligibility.py check_properties_collapse.py

# Explicitly regenerate baseline evidence after reviewing an intentional change.
python checks/capture_parity_reference.py

# Explicit regeneration of the separately reviewed inherited-behavior fixture.
python checks/check_qt_implicit_ui.py --record
```

The capture tool isolates session/startup paths in a temporary workspace folder,
constructs a small synthetic scene, validates its serialized round-trip, and
captures offscreen. It does not open or replace a user's saved project. It writes
only the reference directory and its temporary session directory. It is not run
automatically by checks, so a regression cannot silently rewrite its own baseline.

`reference/manifest.json` records source hashes, Qt/Python versions, platform,
screen size/DPI, style and capture names. Hash differences mean the baseline may
need review, not that an app change is necessarily wrong. Generate the normal
baseline at device scale 1. For 125% and 150%, use separate output directories
or copy the reviewed scale-1 baseline first; the current capture command replaces
its reference files. Do not compare physical pixel sizes across different DPRs
as though they were logical dimensions.

## Port acceptance gates

| Area | Required review |
| --- | --- |
| Numeric core | Portable vectors, plus translated geometry/snapping/collision regressions |
| Project interchange | Valid scene round-trips, used embeds, missing definitions, history incompatibility, staged recovery/cancel |
| Controls | Dropdown edge placement/scrolling; typed edit caret stability; slider/scrub cancellation; color popup rearming |
| Viewport | Hit/handle priority; rotated cursors; Shift before press; modifier changes mid-drag; cancel restores attachments/copies/pivots |
| Export | All format/mode combinations, dependency disabling, independent camera, crop/origin snapping and isolated undo |
| Layout | Narrow/wide sidebar, short/tall window, long names and paths, expanded sections, pinned action, properties collapse |
| Visual states | Idle, hovered, pressed, focused, checked, checked-hovered, disabled, mixed and error states |
| Slider semantics | Selectors/position controls have no amount fill; amount controls show magnitude using their actual min/max; enabled and disabled fill remain distinguishable |
| Scaling | 100/125/150% display scale, several world zooms, matching bundled fonts, both UI/canvas theme families |
| Native input | Real pointer capture outside windows, lost focus, right-click cancellation, popup edge crossing, keyboard focus/shortcuts |

Functional outcomes should match exactly. Geometry numeric tolerances must be
stated, not chosen after seeing failures. For visual diffs, first match logical
sizes, margins, font metrics and semantic colors; then inspect pixel overlays.
Different text rasterizers can change edge antialiasing without changing layout.
Any accepted tolerance needs a reviewed reason. Large font shifts, clipped text,
missing borders or different state colors are not antialiasing tolerances.

Offscreen captures cannot measure GPU/input latency, show the OS cursor or prove
native file-dialog behavior. Several older raster tests sample logical positions
as device pixels and are not reliable at fractional DPR without adaptation;
see the native-path extraction report. A passing default-scale test run does not
certify fractional-scale visual parity.

## Known gaps and observed discrepancies

- The scenario index maps to tests covering **parts** of each scenario. It does
  not claim that every prose sentence is already asserted. Dropdown screen-edge
  positioning, for example, needs explicit target-framework interaction tests;
  the existing all-dropdown check principally verifies sizing and text clearance.
- Captures are selected examples, not every object, focus state or dialog.
  Native window frames are excluded. Picker screenshot shows content; its real
  left anchoring and dismissal sequence are covered by interaction checks.
- SLIDE-02 distinguishes selector/position tracks from amount fill. Current shared
  horizontal Qt styling paints groove/sub-page identically; the gallery therefore
  does not yet establish an amount-fill color reference. This semantic requirement
  needs visual review rather than an automatic copy of either framework's default.
- During reference generation, switching themes while a retained QMessageBox
  exists exposed an `AppearanceMixin.SetThemes` assumption that every `icon()`
  method returns QIcon; QMessageBox returns an enum. The generator destroys its
  temporary message before switching. This is an observed desktop defect to
  resolve separately, not behavior a new framework should reproduce.
- Undo scene replay intentionally keeps Qt point equality behavior in desktop
  adapters. A port must decide equivalent numeric comparisons explicitly; see
  [editing boundaries](../EDITING_PORTS.md). Do not assume exact JSON-array equality replicates fuzzy
  QPointF comparisons at large coordinates.

### Guide session-selection recovery

Session UI recovery preserves whole-object and endpoint selections, AngleGuide
middle index 2, and linear/angular label index 3. Validation checks the selected
index against decoded objects before applying the scene. Only AngleGuide has a
middle point; MeasurementGuide/BoundaryLine/AngleGuide have label selection. Invalid
indices, including booleans, are rejected. Missing object IDs retain the existing
skip behavior. `check_session_guide_selection.py` exercises actual close/reopen
cycles, mixed selections, usable restored handles, exact scene preservation and
atomic rejection of an invalid object/index pair. This supersedes the earlier
audit's session-selection defect.

## Maintaining evidence

Add a scenario when fixing a user-visible regression. For complex popups or
gestures, record the sequence including button state, modifiers, focus and
pointer position before/after each event. Capture a representative visual state
when appearance matters. Keep expected results reviewed and independent of the
new implementation. Link changes from these rules back to their tests and
examples so the specification remains useful after the first port.


## HELP-01: current help-viewer parity

The viewer contract is maintained in [HELP_AUTHORING.md](../HELP_AUTHORING.md).
It includes modeless navigation, icon and device Back/Forward, wheel ownership in
blank margins, centered reading background versus outer margins, inline-code
weight/size, animated media and middle-click autoscroll. Backslash-newline hard
breaks stay within the same paragraph, without paragraph spacing. Preserve
escaped backslashes and literal code, inline formatting, lists, relative resources
and navigation history without rewriting source files. See `check_help_line_breaks.py`.
Those are application
UI requirements; this audit does not edit or certify the user-help prose.

## Current scenario inventory

The scenario index now includes free angles and movable labels, bounded numeric
expressions, linked Size/pivot Position, fixed SVG/compound details, optimized
PNG and bounded previews, role-aware SVG recoloring/occlusion, reference image
editing/calibration, imperial defaults, catalog ranking/sorting/layout, missing
asset location and transport restrictions, app-owned window state, Close versus
New, native browsing and help input. Each entry links executable desktop checks.
Browser entries remain acceptance definitions requiring a browser run.

Specialized layouts are specified in [LAYOUTS.md](LAYOUTS.md). Geometry checks
cover the measurement selectors, Wall Tool, pinned Export regions, format/scale
dependent rows, paired object/control-point properties, Reference Image controls
and the calibration prompt. Existing gesture checks cover the associated edits,
restoration, one-use units, snapping, cancellation and anchored calibration.
These checks supplement the dated gallery rather than claiming fresh screenshots
or browser verification for every conditional combination.

The object matrix tests its class inventory against scene models. The portable
index check requires these current rule families and validates desktop/browser
check paths. Matrix data are observations, not independent proof that observed
behavior is intentional; dedicated geometry and gesture assertions remain needed.
