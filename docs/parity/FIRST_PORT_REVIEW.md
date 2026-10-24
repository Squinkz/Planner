# First web port: UI parity review

Reviewed 17 October 2026. Reference repository:
[T-R3x3r/simplehouseplanner](https://github.com/T-R3x3r/simplehouseplanner).
Pinned source: [`b9b9c928d9678d03e4d8ef91f36a66268e0c7a10`](https://github.com/T-R3x3r/simplehouseplanner/tree/b9b9c928d9678d03e4d8ef91f36a66268e0c7a10),
commit dated 9 October 2026. A read-only checkout was inspected locally; this
review did not install its dependencies, run its app or change its source.
The [source manifest](reference/first-port-source.json) records reviewed file hashes.

## Frameworks actually used

[package.json](https://github.com/T-R3x3r/simplehouseplanner/blob/b9b9c928d9678d03e4d8ef91f36a66268e0c7a10/package.json)
declares React/React DOM ^19.2.0, TypeScript ~5.9.3 and Vite ^7.1.7. There is no
Qt-equivalent component library in its dependencies. UI is custom React + CSS,
native HTML form controls and bespoke popovers; drawing uses Canvas 2D and SVG.
Other declared dependencies include opentype.js, polygon-clipping and idb-keyval.
These are declared constraints, not a claim about installed dependency versions.

Desktop is PySide6/Qt 6.11.1 in the recorded environment, Qt Widgets with **Fusion**
base style and QSS, native Qt editing/layout/focus behavior, and painter/SVG
rendering. The important difference is the UI/control substrate, not TypeScript
versus Python. React can reproduce the behavior, but does not supply it for free.

## Evidence and time boundary

**S** below means directly visible in the pinned source. **Q** means tested in
the current desktop. **R** means a browser runtime consequence still needing a
browser test. Do not turn R into a claim of a reproduced browser bug.

The current desktop includes changes after the first port. This review identifies
risks/differences for the **next** port; it cannot establish which features were
missing or invented against an unrecorded October 9 desktop baseline. The user's
report of poor UX is context, not permission to invent a retrospective bug list.

## Concrete control differences and risks

| Finding | Evidence | Consequence / next-port rule |
| --- | --- | --- |
| Generic `Select` renders native HTML select, while material uses a separate custom popup | S: `src/ui/controls.tsx` Select; `MaterialSelect.tsx` | Native styling/placement is not DROP-01. Share an adapter and test all variants; browser-specific outcome R. WEB-04 |
| Material popup is fixed 210 px / max 330 px, right-aligned to trigger; Qt ordinary popup uses field left edge and content sizing | S: MaterialSelect positioning and CSS; Qt widgets.py | Anchoring and long-text sizing differ explicitly. WEB-04/11 |
| Material keyboard arrows call `onChange` on the current value directly | S: MaterialSelect root key handler; Q: popup navigation only highlights until acceptance | Opening navigation and committed selection must be separate states. WEB-04 |
| NumberField blocks scrub initiation when input is already focused and uses a 4 px threshold | S: controls.tsx pointer handlers; Qt DragSpinBox; Q: desktop drag threshold 10 in this environment | Repeated edits can require a different interaction; use the configured desktop threshold and focused-field scrubbing. WEB-03 |
| Scrub uses total displacement multiplied by the current Alt rate | S: NumberField `g.value + dx * step * ...`; Qt uses event-to-event deltas | Toggling Alt after movement can reinterpret prior travel. Browser jump R; algorithm difference S. WEB-03 |
| NumberField formats all values through three decimals and a value-dependent effect, has no numeric wheel handler, and explicitly resets draft on Escape | S: controls.tsx; Q: per-field metadata, unfocused wheel step and non-drag Escape probe | Preserve each control's precision, draft/caret, wheel and contextual cancellation; do not generalize the reusable component policy. WEB-02/03 |
| SettingNumber uses native range/accent-color and hardcodes .001 slider step | S: SettingNumber.tsx and CSS | Native thumb/track/keyboard details and selector-versus-amount fill need explicit adaptation. WEB-05 |
| Visibility wraps each caption/checkbox in one label | S: Visibility.tsx; Q: caption click does not toggle Qt checkbox | Hit area, hover cursor and toggling behavior differ. WEB-10 |
| Tab colors map selected to hoverBackground, inactive Export to activeBackground, selected Export to activeHoverBackground | S: style.css tab rules; Qt theme.py current selected states | Those are separate semantic states in the current baseline; exact palette mapping matters across themes. WEB-11 |
| Picker arms on any bubbled move and checks `:active` on leave, without the explicit outside-release/disarm state | S: ColorPicker.tsx; Q: picker trace fixture | Capture can deliver outside moves to a child; root events alone cannot establish real reentry. Missing state path S, exact visible result R. WEB-06 |
| Picker outside handler is a document bubble listener and does not consume the outside event | S: ColorPicker.tsx; Qt filter accepts/consumes dismissal | Underlying target may already have handled the press. Click-through is an R to test, not a reproduced claim. WEB-07 |
| Submenu uses enter/leave timers and click toggles | S: MaterialMenu.tsx; Qt ContextSubmenuController | Similar timer numbers do not prove identical pointer travel, parent press or forced-idle behavior. WEB-07 and MENU-01 |
| App global shortcuts return for input/select targets, except Ctrl+S | S: App.tsx key handler | This differs from the current export-specific pending-field undo routing. Keyboard ownership needs contextual rules, not a global editor exception. WEB-08 |
| Modal defaults include a backdrop, 520 px width, close button; modeless Settings exists separately | S: Modal component and CSS | Preserve each dialog's actual modality/default-button/Enter/escape behavior and measured size. Do not make every dialog a generic modal. WEB-09 |
| Canvas wheel zoom uses raw deltaY exponential without deltaMode normalization | S: Interaction.wheel; Qt has angle/pixel and discrete accumulators | Pixel/line/page devices need normalization; inconsistent devices are R. WEB-13 |

Relevant pinned sources:
[controls](https://github.com/T-R3x3r/simplehouseplanner/blob/b9b9c928d9678d03e4d8ef91f36a66268e0c7a10/src/ui/controls.tsx),
[material dropdown](https://github.com/T-R3x3r/simplehouseplanner/blob/b9b9c928d9678d03e4d8ef91f36a66268e0c7a10/src/ui/MaterialSelect.tsx),
[material submenu](https://github.com/T-R3x3r/simplehouseplanner/blob/b9b9c928d9678d03e4d8ef91f36a66268e0c7a10/src/ui/MaterialMenu.tsx),
[picker](https://github.com/T-R3x3r/simplehouseplanner/blob/b9b9c928d9678d03e4d8ef91f36a66268e0c7a10/src/ui/ColorPicker.tsx),
[visibility](https://github.com/T-R3x3r/simplehouseplanner/blob/b9b9c928d9678d03e4d8ef91f36a66268e0c7a10/src/ui/Visibility.tsx),
[slider wrapper](https://github.com/T-R3x3r/simplehouseplanner/blob/b9b9c928d9678d03e4d8ef91f36a66268e0c7a10/src/ui/SettingNumber.tsx),
[CSS](https://github.com/T-R3x3r/simplehouseplanner/blob/b9b9c928d9678d03e4d8ef91f36a66268e0c7a10/src/style.css),
[App](https://github.com/T-R3x3r/simplehouseplanner/blob/b9b9c928d9678d03e4d8ef91f36a66268e0c7a10/src/App.tsx),
[interaction](https://github.com/T-R3x3r/simplehouseplanner/blob/b9b9c928d9678d03e4d8ef91f36a66268e0c7a10/src/editor/interaction.ts).

## Protections the first port already includes

Preserve these rather than dismissing the whole earlier implementation:

- Canvas has pointer capture, pointercancel/window-blur paths and a second-button
  cancellation branch in pointermove, not only pointerdown.
- `Viewport` installs a nonpassive wheel listener, cleans listeners on teardown,
  scales its backing canvas by DPR and guards obsolete async export images.
- App passes a stable memoized context callback into the viewport effect.
- Assets convert `#AARRGGBB` to CSS `#RRGGBBAA`, and load bundled fonts before boot.
- Material dropdown uses a portal and resize/scroll repositioning, and handles
  mixed checkbox presentation through DOM indeterminate state.
- Settings explicitly uses a modeless dialog variant; not every window was
  incorrectly modal.

Sources: App, interaction, [Viewport](https://github.com/T-R3x3r/simplehouseplanner/blob/b9b9c928d9678d03e4d8ef91f36a66268e0c7a10/src/editor/Viewport.tsx),
[assets](https://github.com/T-R3x3r/simplehouseplanner/blob/b9b9c928d9678d03e4d8ef91f36a66268e0c7a10/src/render/assets.ts),
[boot](https://github.com/T-R3x3r/simplehouseplanner/blob/b9b9c928d9678d03e4d8ef91f36a66268e0c7a10/src/main.tsx).
Existence of a protection is source evidence, not proof of complete runtime parity.

## Documentation/testing implications

The new [migration contract](WEB_MIGRATION.md) makes these implicit defaults
explicit. `reference/qt-widget-defaults.json` records native behavior, and
`checks/check_qt_implicit_ui.py` replays it under the actual Fusion base style.
`browser-cases.json` gives browser acceptance cases for the control/event/CSS
boundary. The original picker traces remain portable input sequences.

The first port has no test script in package.json; its PARITY.md describes manual
validation and explicitly does not claim execution of all desktop checks. That
is not an automated parity gate. A production build proves compilation, not
that blur, popup dismissal, keyboard ownership or dragging match the desktop.
No browser runtime results are claimed by this review.

A source-to-control inventory should also flag unmatched controls and features.
For example, the pinned export panel exposes a `Reset automatic crop` button,
where the current desktop contract describes per-edge double-click reset. This
needs explicit provenance/approval before copying it into the next port; it is
not proof that such a button never existed in an older desktop build. Missing
newer object types/export features likewise belong in a baseline-version matrix,
not a fabricated historical UX diagnosis.
