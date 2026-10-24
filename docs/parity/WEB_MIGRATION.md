# Qt to browser UI migration contract

This supplements the control/interaction specification with behavior previously
supplied by Qt, its Fusion style and its event system. It applies to React or
another browser framework. React is a component/state framework, not a replacement
for Qt Widgets' complete control behavior. A matching-looking DOM element is not
automatically a matching interaction.

Evidence: [review of the first port](FIRST_PORT_REVIEW.md), the live Qt source,
[inherited widget observations](reference/qt-widget-defaults.json), existing tests
and the browser acceptance scenarios in [browser-cases.json](browser-cases.json).
The new browser scenarios are specifications awaiting a browser implementation,
not claims that the old port has passed browser tests.

## WEB-01: choose a baseline and prohibit invented behavior

Freeze the desktop version and these documents before porting. Treat the initial
web attempt as comparative evidence, not a second authority. Its October 9 source
predates the October 17 desktop reference; missing newer features do not prove
that the older port hallucinated or regressed them.

Every new framework control must identify its desktop counterpart, rule ID,
label/default/range, enabled/visible predicate, commit/cancel policy and evidence
capture or test. No invented options, renamed meanings, replacement tools,
reordered panels or generic component defaults silently substituted for these.
If no counterpart is found, record a question or an explicit platform adaptation.
Do not fill an undocumented gap by assuming what a floor-plan app usually does.
Keep a register of approved adaptations and unverified differences. An unverified
behavior is not a passed parity item.

Use the actual captured dropdown data, numeric metadata, source assets and
current project settings. Do not recreate a subset from screenshots alone.

Distinguish unavoidable host differences as well: a browser download filename is
not a desktop save path or a guarantee that the same disk file was overwritten.
File selection, clipboard access, native prompts and embedded-host shortcuts may
need explicit platform adapters. Keep cancel/failure/dirty/recovery outcomes
defined; never make the UI claim a desktop operation happened merely because a
similarly named browser button was clicked. Native OS file dialogs are outside
the themed app-message contract.

## WEB-02: numeric text is draft state, not model state

Keep separately: precise committed value, current draft string, editing/caret/
selection state, validation state and gesture-start value. React's controlled
`onChange` runs on text input; it is not Qt's deferred value commit. Its
[input documentation](https://react.dev/reference/react-dom/components/input)
also describes caret problems when controlled updates replace typed text.

Preserve intermediate strings such as `-`, `12.` or an unfinished imperial value.
Do not run a formatted model value through a render effect after every keystroke.
Do not change the input's component key when its numeric value changes: remounting
loses focus, selection, native text undo and pointer capture. Programmatic refresh
must distinguish an unchanged self-notification from a real external change.

Apply each field's range, decimals, single step, suffix, read-only/mixed state and
keyboard-tracking policy. `Number(text)` is not an imperial/unit parser; binary
floating-point model data must not be replaced by a rounded display string.
Mixed property fields are visually blank, not a newly invented `Mixed` value or
an implicit zero. Picker RGB/HSV use intentionally live valid-value previews;
deferred property fields wait for Enter or focus loss.

The Qt probe demonstrates a deferred field at 10.25 retaining that committed value
while its text is `12.`; Enter commits 12 and formats `12.00`. Committing an
incomplete `-` restores the prior valid value. Match this correction outcome,
not a browser form-validation bubble. Preserve native text selection and local
Ctrl+Z within a focused editor, distinct from scene/export history.

**Escape is contextual:** it cancels an active scrub/gesture. It is not a blanket
instruction to undo every typed edit. The non-dialog Qt field probe leaves a
`14.75` draft after Escape and commits it on subsequent focus loss. A dialog can
handle Escape differently. An improvement to typed-cancel policy requires an
explicit product decision, rather than inheriting one from a reusable web input.

Arithmetic entry must follow NUM-01, including relative shorthand, mixed-value
restrictions, bounds, deferred commits and rejected code syntax. JavaScript
`eval` and `Function` are not substitutes for the bounded parser.

## WEB-03: scrub, stepping and wheel ownership

Preserve click-to-edit and scrub-from-an-already-focused-field. Qt scrubbing does
not require blur before the next drag. Threshold is the desktop drag distance
(10 logical px in the recorded environment), based on horizontal displacement for
numeric scrubs. Palette drags/box gestures can use a different distance metric.
Do not replace all thresholds with a convenient hardcoded 4 px.

Scrub increment is based on movement since the previous event. Alt changes the
rate of subsequent movement; it must not rescale all displacement since press
and cause a value jump when Alt changes. Preserve continuous reversal, clamping,
fine rate, live preview and one final history operation. Keep the drag's starting
precise value until commit/cancel, even when React re-renders the control.

Up/Down step numeric values; suffixes remain visible/parsable. Wheel over a Qt
numeric field can step it even without focus: the recorded .5-step field changes
12.5 to 13 on one +120 wheel event with `focus: false`. Do not globally disable
wheel adjustment merely because it differs from a preferred browser pattern.
Route the wheel to the hovered control or its scroll container according to the
reference, and test boundaries/disabled cases explicitly. Do not zoom the canvas
as a second consequence of a field or popup handling the same wheel input.

## WEB-04: dropdowns need a complete interaction adapter

The generic HTML select and a bespoke material menu are not interchangeable
implementations of the same Qt dropdown. Native select popup layout, available
styling and input behavior are browser/platform controlled. Use a shared control
adapter where native behavior cannot meet DROP-01, preserving keyboard support
and accessible combobox/listbox semantics when replacing native controls.

Separate the committed selected value from the highlighted popup row. Recorded
Qt closed Down changes Beta to Gamma immediately. With the popup open, Up
highlights Beta while the value remains Gamma; Escape closes without committing
that highlight. Enter selects the highlighted row. Record popup reopen/highlight
behavior from the probe rather than assuming close always resets every row state.
`currentIndexChanged`/highlight/activation are different Qt concepts; do not map
every arrow press to a project edit. See [Qt's combo reference](https://doc.qt.io/qt-6/qcombobox.html).

Cover type-ahead search, Home/End, Up/Down, Enter/Escape, Tab/focus return, disabled
items, editable values such as print density, wheel and long scrolling lists.
Not every variant has all behaviors; use its actual configuration. Item icons
and per-item tooltips are part of the reference. Measure the longest text, icon
and arrow allocation. The ordinary Qt popup is left-aligned below its field,
scrolls to top, flips/clamps at edges, and is not a fixed-width right-aligned menu.

## WEB-05: slider semantics are independent of native range defaults

Follow SLIDE-01/02. A quantity uses an amount fill; a discrete choice or directional
position does not. Browser `accent-color` alone does not specify geometry or
guarantee those track semantics. Define track/thumb/filled-part/disabled styles
for each supported engine, or use a custom slider with equivalent keyboard and
accessibility behavior. Do not manufacture a progress fill for preset indices.

Keep track-click jump, grab offset, reversing, Escape restore and grouped history.
Observe singleStep/pageStep independently: a sample 0..100 range at 50 becomes
51 with Right, 61 with PageUp, then 0/100 with Home/End. Real controls can have
other ranges/steps. A normalized 0..1 effect is not necessarily restricted to
step .001 everywhere simply because another component uses that setting.

Measurement mode is a **vertical selector**, with inverted appearance/controls,
single/page step 1 and labels alongside its positions. It is not an ordinary
horizontal percentage slider. Its label area participates in dragging and wheel
selection; a label click must not become a canvas command.

## WEB-06: pointer capture changes event targeting, not pointer location

Qt widgets normally keep receiving events through a mouse grab during a drag.
Browser controls need equivalent pointer capture and cleanup. Captured events
can target a child even while coordinates are outside that child's rectangle.
Compute popup containment from client coordinates and actual bounds, not only
`event.target`, `contains()` or CSS `:active`. React portals also bubble through
the React tree; DOM ancestry alone is not an event-routing contract.
[Pointer Events](https://www.w3.org/TR/pointerevents4/) defines capture and chorded
buttons; [React portal docs](https://react.dev/reference/react-dom/createPortal)
explain the separate event ancestry.

Implement one gesture lifecycle: begin, update, commit or cancel, cleanup. Handle
pointerup outside, pointercancel, unexpected lost capture, window blur and DOM
unmount. After ordinary release, lostpointercapture must not cancel a transaction
that already committed. Capture a specific pointer ID and ignore unrelated input.
Mouse buttons are a bitmask: left=1, right=2, middle=4. A second button can arrive
as pointermove rather than a new pointerdown. Right-press during left-drag must
still cancel. The earlier port already handled that chord in its move handler;
do not remove this behavior while simplifying the next implementation.

Run the existing picker traces with real geometry checks. Release outside disarms
the picker until actual reentry, even with capture. A captured move bubbling
through the popup is not reentry. Keep cancellation/restoration separate from
acceptance. Test release from a scrub field, not just synthetic moves on the root.

## WEB-07: overlays, click-through and portal styling

Popover position uses the visible editor viewport, not arbitrary document offsets.
Reposition on resize, scroll, font/layout changes and browser zoom. Escape clipping
from scroll containers using a suitable overlay root, but preserve the editor's
theme variables, font and accessible ownership. A portal to `document.body` can
lose variables defined only on `.planner`; a portal inside `.planner` can still
be affected by its transforms/stacking contexts. Choose and test deliberately.

CSS z-index alone does not override a native modal dialog's top layer. A picker
opened from a dialog must appear above and remain interactive within that dialog's
modal context. Test that hierarchy instead of raising arbitrary z-index numbers.

Picker outside dismissal consumes its click in Qt. A document bubble listener
that closes after the clicked target already began a canvas drag is too late.
Use explicit input ownership/dismissal handling so that gesture does not start
underneath, including any subsequent click generated by the same press/release.
Other menus follow their own dismissal policy; do not apply picker consumption
to every popup without checking it.

## WEB-08: keyboard focus, shortcuts and default actions

Order ownership: active modal/popup or gesture; focused text/numeric editor;
focused control; canvas commands when applicable; supported application shortcuts.
Use the actual rule for each key, not one catch-all document listener.
Text Ctrl+A/C/X/V/Z belongs to text editing; supported Save/Save As still work.
Export undo deliberately commits pending export text and routes to export history;
it is an exception to blanket text-editor shortcut suppression.

Canvas Tab switches transform orientation; outside canvas, Tab must navigate
controls. Arrow keys on a focused slider/combo/tab bar must not nudge objects.
The Qt tab bar immediately activates the next tab on Right and stops at the last
tab in the probe; plain web buttons do not provide that behavior automatically.
Do not add a second activation on keyup or on the synthetic button click.
Preserve Escape priority and focus return after menus/dialogs.

Honor IME composition rather than treating Enter while composing as a command.
Do not let Delete or held placement keys escape from text editing. Mark commands
that may repeat versus one-shot toggles. Browser-reserved shortcuts and embedded
host shortcuts may not be interceptable; retain menu/button equivalents and log
any unavoidable adaptation instead of claiming a JavaScript handler guarantees it.

## WEB-09: dialogs are not all modal forms

Settings and Transform are modeless desktop windows. Blocking the editor behind
a generic web modal changes their behavior. Geometry/unsaved/replacement prompts
have different modal/default/escape rules. Retain those differences explicitly.

Enter in a Settings numeric/text field commits and moves focus without activating
the dialog's OK button; the probe keeps Settings visible after committing .37.
Unspecified web button types inside a form can submit it unexpectedly. Declare
button roles/types, route Enter deliberately and match the actual default button
for prompts. Do not make Escape, backdrop click and window close synonymous
for every dialog. Geometry-close cancels the whole staged load.

Modeless windows need deliberate layering, focus and keyboard handling. Modal
windows need focus containment and restoration. Use native dialog semantics or
equivalent behavior correctly; [the HTML dialog standard](https://html.spec.whatwg.org/multipage/interactive-elements.html#the-dialog-element)
distinguishes modal and modeless operation. Preserve app messages' minimum size,
plain text, status assets, button order and path wrapping; arbitrary generic
520 px modals are not the measured Qt dialog specification.

## WEB-10: checkbox/tree hit areas and disabled state

Qt's visibility tree has separate checkbox and caption areas. The probe leaves a
partially checked row unchanged on caption click, then unchecks it on checkbox
click. Wrapping an entire row in an HTML label makes its caption toggle too and
changes both hit area and cursor. Preserve the measured target boundaries;
indeterminate is a third presentation state, not a third arbitrary model value.
Retain keyboard toggling, hierarchy, counts and disabled/empty text roles.

`opacity: .5`, `aria-disabled` and a disabled-looking CSS class are not substitutes
for stopping activation. Disable children and clear drag state consistently;
allow tooltips according to the reference. An enabled clickable header can still
contain a disabled dependency group. Keep button focus/hover/checked state and
cursor distinct; a disabled reset button must not act or show an enabled hand.

## WEB-11: QSS metrics are not CSS declarations to copy literally

The Qt app explicitly selects **Fusion** before applying its stylesheet. The
reference generator now does the same. A QSS proxy style can have an empty name;
record the chosen base style and Qt version, not just `style().objectName()`.

Use measured **outer** widget bounds as targets. Qt's style content size, border,
padding, minimum size hints and layout negotiation differ from a web page with
global `box-sizing: border-box`. Example: palette widgets are 48 outer, although
their stylesheet content constraints say 46; copying 46 into border-box CSS
shrinks the control. Similarly a 22 px content minimum plus padding/border does
not mean an outer height of 22. Native form controls need explicit resets and
arrow/thumb/check assets to avoid browser-specific decorations.
[Qt box model](https://doc.qt.io/qt-6/stylesheet-customizing.html#the-box-model),
[CSS box sizing](https://www.w3.org/TR/css-ui-4/#box-sizing).

Map semantic states individually, including checked+hover, disabled, focus,
pressed, selected tab and collapsed/expanded section. Do not alias selected tab
to ordinary hover merely because colors look close in one theme. Export's inactive
emphasis and its active state are separately specified. Preserve border widths,
radius, control spacing and custom arrow area rather than sprinkling new CSS
over a native control whose intrinsic arrow still occupies space.

Qt's UI font is 10 **points**, not 10 px or an approximate 13 px. CSS length units
give 10 pt = 13 1/3 CSS px, before rasterization; actual font metrics and line height
still need measurement. Use bundled weights, no synthetic bold, and wait for
fonts before text measurement. See [CSS absolute units](https://www.w3.org/TR/css-values-4/#absolute-lengths).
Do not force the browser's `line-height: normal` to match Qt by assumption.

## WEB-12: scrolling and responsive layout are part of parity

Qt size policies, minimum-size hints and layouts negotiate space. Flex/grid often
need `min-width: 0`, `min-height: 0`, explicit scroll ownership and shrink rules.
Without them a child can push a pinned action below the screen or collapse labels
unlike Qt. Use available browser/container size, not 1440 x 900 as a minimum.
If hosted in an iframe, use the actual host viewport/overlay root rather than
top-level monitor dimensions. Avoid an accidental whole-page scrollbar plus an
independent sidebar scrollbar consuming the same wheel.

Test nested sidebar scroll, properties collapse/restore, splitter clamping,
long lists/paths, text wrapping and palette row anchoring at narrow widths and
short heights. At 1280 x 720 physical resolution browser chrome reduces the
usable area; 125/150% scaling reduces logical space further. Container-responsive
reflow may be appropriate, but changed label/control order must be an approved
adaptation. Keep the Export action reachable and leave model geometry unchanged.

Preserve the desktop's readable widget minimums. Narrow sidebar content may
overflow horizontally and remain reachable through horizontal scrolling; it need
not compress every field to the viewport width. Divider reset restores the
default width. Test both extremes of the horizontal scroll range.

## WEB-13: wheel, CSS coordinates and device pixels

DOM wheel deltas can be pixels, lines or pages. Normalize direction/units before
matching Qt's angle/pixel delta behavior. Discrete selector changes accumulate
notches instead of advancing a choice on every tiny trackpad event. Pan/zoom and
gesture-specific wheel actions are different from widget stepping. Install a
nonpassive listener only where preventing browser scroll is necessary.
[UI Events wheel definition](https://www.w3.org/TR/uievents/#interface-wheelevent).

Pointer positions/overlay bounds are CSS pixels. Canvas backing dimensions are
device pixels, scaled once by devicePixelRatio. World dimensions are millimeters.
Do not multiply hit radii or cursor hotspots by DPR twice. Respond when browser
zoom, display scale or monitor changes alter DPR, even if the app does not remount.
Export 1:1 means one output pixel/SVG unit per physical display pixel. Verify
pointer-anchored zoom and ruler/crop alignment, not just a sharp screenshot.

## WEB-14: rendering and asynchronous lifetime

Qt painter paths/fonts and Canvas/SVG are separate engines. Preserve fill rule,
clip order, cap/join/miter settings, transforms, local boolean-operation origins,
text anchor/baseline and non-scaling-stroke rules from the native-path contracts.
Do not rely on Canvas's default fill rule or a handwritten SVG subset to preserve
rounded corners, transformed rectangles, nested text or compound artwork.
Match normal, selected, transparent-object, PNG and SVG states independently.

Qt repaints/signals have stable object lifetimes; React render/effect updates and
asynchronous fonts/image decodes need equivalent ownership. Keep an active gesture
and its pivot/capture/starting state stable across renders. Clear listeners/timers
on teardown without adding duplicate handlers. Ignore obsolete async preview
results; stale format/scale images must not replace the current preview. A React
render is not a model transaction or permission to append a history record.

The first port already used a stable context callback, preview result keys,
cleanup functions, initial font loading and DPR-scaled backing canvases. Keep
those protections and test them. Static inspection alone does not certify that
every resource or gesture cleanup path is correct.

## WEB-15: tooltips and hover information

Preserve exact tooltip text and its owning hit area. Qt uses themed QToolTip
styling; an HTML `title` is native browser UI and cannot guarantee those colors,
padding, font or placement. Use an equivalent tooltip adapter where appearance
is part of parity. Keep the accessible name separate from transient hover text.
Do not convert a Qt tooltip into an always-visible explanatory paragraph, rename
a short label or add instructions as permanent UI merely because the browser
component makes that easy. Canvas contextual information remains separate from
ordinary control tooltips.

Tooltip delay/edge behavior should be measured in the target desktop environment
before choosing hardcoded web timing; the current fixtures record text, not full
tooltip timing. Test disappearing on leave, clipping near screen edges, disabled
controls and stale hover state after popup close. Preserve the submenu's existing
forced-idle handling so a dismissed parent does not stay highlighted.

## Acceptance gates

Run the inherited Qt probe, picker traces and existing regressions first. Then
execute [browser-cases.json](browser-cases.json) against the target framework with
real browser input, including Chromium and Firefox and other explicitly supported
engines. Use live screenshots and event/state assertions; DOM snapshots alone do
not verify pointer capture, native selects or focus behavior. Record any excluded
platform/feature, and distinguish passing, failing and not-yet-tested cases.
