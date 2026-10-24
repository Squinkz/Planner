# Controls and visual rules

Baseline sources: `planner_app/ui/widgets.py`, `color_picker.py`,
`context_submenu.py`, `menus.py`, `dialogs.py`, `export_panel.py`, and
`planner_app/graphics/theme.py`. Paths are relative to the application root.

## VIS-01: colors, typography and assets

UI and canvas themes are independent. UI artwork uses UI roles; scene artwork
uses canvas roles. Theme changes refresh existing icons, swatches, text and
cached scene artwork, without requiring the user to recreate controls.
Fresh profiles default to Heather UI and Magnetite Canvas. New projects enable
wall measurements and disable stair, counter, railing and elevator measurements;
saved choices override these defaults.

| State | Generic button background/border | Text |
| --- | --- | --- |
| Idle | `controlBackground` | `text` |
| Hover | `hoverBackground` | `text` |
| Pressed | `pressedBackground` | `text` |
| Checked | `activeBackground` | `activeText` |
| Checked and hovered | `activeHoverBackground` | `activeText` |
| Disabled | `disabledBackground` | `disabled` |

Other controls use their documented overrides. Disabled labels use `disabled`;
disabling only a slider thumb while leaving its label bright is insufficient.
Fields use `fieldBackground`; field selection uses `activeBackground`.
Menus use `controlBackground` and `menuBorder`. Error/highlight rendering uses
semantic error/warning roles, never the selection blue as a substitute.

Default UI: Noto Sans 10 pt, bundled regular/semibold/bold files, with unhinted
glyph proportions. Section text is 11 pt/700; tabs and export section buttons
are 14 logical px/600. Menu shortcuts are 8 pt, palette dimensions 7 pt/400,
palette captions 8 pt. Load actual fonts before measuring layout. Canvas labels
use the canvas theme's label font; measurements/rulers use Noto Sans. Imperial
fractions are enlarged without independently making them bold.

The reference palette exports Qt's eight-digit `#AARRGGBB` convention. Convert it
explicitly when a framework expects `#RRGGBBAA`; do not reinterpret the bytes.
Use the resolved stylesheet for exact selector-specific metrics and precedence.

## BTN-01: buttons and focus

Generic buttons have 1 px borders, radius 5, padding 4 vertical/12 horizontal,
minimum content height 22. Header buttons are transparent at rest with radius 4.
Opening/furnishing palette buttons have a 48 x 48 outer widget, a 40 x 40 icon
and stylesheet content constraints of 46 x 46; fullscreen is 30 x 30. Enabled clickable
buttons have a pointing-hand cursor; disabled controls revert to an arrow.
Palette drag sources instead show an open hand.

The vertical viewport toolbar uses 32 x 32 icons in 40 x 40 buttons. Furnishing
sort/view controls use 26 x 26 icons in 32 x 32 buttons beside the search field.
Header buttons use 28 x 28 icons. Properties icon-only
actions use 24 x 24 icons, zero padding and a 30 px minimum content height;
they stay square at the shared property row height. Export/reference browse
buttons use 26 x 26 icons in 44 x 32 buttons. Export's text button uses a 28 px icon.
Settings reset buttons use 24 x 24 icons with zero padding in 34 x 32 controls.
Settings object labels use 28 px artwork and collision labels use 24 px icons.
Collision checkboxes share a right-aligned column immediately left of the
section midpoint. Their icon/text labels share a left-aligned column on the
right. Clicking the icon or text toggles the same checkbox.
Settings tab icons use 24 x 24 icons alongside their labels.

Keep checked, pressed, hover, focus and disabled as distinct states. Retain
tooltips, accessible names, field labels and keyboard operation. Do not let
child labels intercept the enclosing menu/button's pointer events.

## SIZE-01: linked dimensions

Paired Width/Length fields have a centered 32 px link toggle using `link.svg`.
It starts unchecked for control-point objects (walls, counters, stairs and
railings), and checked for furnishings, pillars/columns, elevators, fireplaces
and reference images. Labels have no link toggle and always preserve proportions
when either Size field is edited. Link choices last only for the current selection;
deselecting or changing the selected objects resets the default. Reference-image
editing resets its link when it closes. Property refreshes keep the current choice. Linked
numeric edits and scrubs preserve each object's current aspect ratio; unlinked
edits change only the chosen dimension. Multi-selection preserves each object's
individual ratio, and both dimensions form one undo/cancel operation. Reject an
edit when size limits prevent preserving the ratio. The toggle is panel state,
not saved geometry, and does not change canvas handle behavior.

## DROP-01: ordinary dropdowns

Dropdowns use an explicitly styled list, not the native OS menu appearance.
The popup starts immediately below the field, independent of the selected row.
It initially scrolls to the top, rather than aligning the selected row with the
field. If there is insufficient room below and more room above, place it above.
Constrain its height to the available space and clamp horizontal position to the
screen. Preserve item order and editable/noneditable status.

Size the closed field for the longest item and optional icon, not just the
currently selected text. Icon allowance is icon width + 4; leave another 4 px
of text clearance after accounting for the actual arrow/padding geometry.
Update minimum size when items, fonts or styling change. A dropdown must fit
within its panel and must not clip text beneath the arrow.

Field: radius 5, padding top/bottom 4, left 10, right 6. Arrow area: 20 wide,
separate `controlBackground`, 1 px left divider, 16 x 16 down-arrow asset.
Hover highlights the arrow area and field border. Popup: 4 px outer padding;
rows have minimum content height 24, padding 5 vertical/14 horizontal, radius 4.
Selected rows use `activeBackground`/`activeText`. Disabled fields and arrow
areas use disabled colors. Editable fields retain ordinary text editing.

## MENU-01: menus and submenus

Menu rows align an 18 x 18 icon, action text and right-aligned shortcut. Header
rows have minimum width 300 (grow for content), margins 12 left/14 right and
14 between elements. Text reserves at least 126; nonempty shortcuts reserve 96.
Submenu rows reserve at least 250 and show a right-side arrow. Separators are
1 high, with 4 vertical/6 horizontal margin. Row hover and checked states use
active colors; inactive shortcuts use `mutedText`. Clicking an action closes
its menu. Disabled actions retain their position.

Hovering a submenu parent opens the child immediately; pressing it also opens
the child and consumes the press/release rather than triggering an ordinary
action. Child starts at the parent's right edge/top. Flip left if necessary;
clamp vertically to screen. Parent remains checked while its child is open.
Moving from parent into child keeps it open. Leaving both closes the child;
moving elsewhere in the root keeps the root open. Clicking outside closes the
menu chain. Closing root always clears child and forced-hover state.

Current controller has a 25 ms pointer watcher, 500 ms child-leave timer and
80 ms parent timer. These are not a blanket 500 ms hover delay: application
mouse moves outside parent/child can close the child immediately. Match the
observed transition cases in `check_stacker_submenu.py` before tuning timers.
After dismissal, a forced idle state prevents a stale highlighted parent until
it is entered again.

Toolbar split/menu buttons open their menu on right-click or left-click of the
arrow region. Their normal popup is right-aligned below the button; buttons
marked `menuToRight` open 6 px to its right.

## NUM-01: numeric fields

Numeric fields accept arithmetic with `+`, `-`, `*`, `/`, parentheses and normal
operator precedence. A leading `+`, `*` or `/` operates on the current value.
A leading minus remains an absolute negative value so coordinate entry is
unambiguous. Bare operands use the field's displayed units. Feet-and-inches
editors also accept their existing marked dimensions inside expressions.
Arithmetic commits on Enter or focus loss, including in fields where ordinary
numeric input previews live. Integer fields round results to the nearest integer,
with half values rounded away from zero. Invalid expressions, division by zero,
non-finite results and results outside the field limits retain the current value.
Relative shorthand is unavailable for blank mixed-value fields. Property edits
retain existing linked-size, validation and undo behavior.
The parser accepts only numeric literals and the four operators, with limits of
256 input characters, 128 tokens and 16 recursive levels. Names, calls, attributes,
collections, exponentiation and other code syntax are rejected. It never executes
source code. The shared implementation is `planner_app/number_expressions.py`,
with decimal/unit and integer adapters in `planner_app/ui/widgets.py`.

There are two deliberate control families. Property/color scrubbing fields have
no arrow buttons. Settings/export steppers use custom 16 x 16 arrow assets in a
20 px wide area; do not restore native arrows or put arrows on scrub fields.
Reference JSON records each field's family, range, step, decimals, suffix and
keyboard-tracking policy.

Scrubbing: a click types normally. Horizontal travel must reach the platform's
drag threshold before scrubbing begins. Once active, each horizontal pixel
changes the value by `singleStep / 10`; Alt divides that rate by another 10.
Clamp to range, update live, and show horizontal-resize cursor during the drag.
Release commits; Escape asks the owner to cancel/restore the pre-drag value.
Treat one drag as one undo operation. Mixed unedited properties display blank;
do not silently replace them with zero.

Most property/export option editors defer typed commits until Enter or focus
loss (`keyboardTracking = false`). Typing `1` must not immediately reformat the
field to `1.00` and disturb the caret. Color RGB/HSV fields deliberately track
valid input live so their preview stays synchronized. Preserve that distinction.

Decimal imperial UI readouts show up to the implemented three decimal places;
canvas dimensions use fractional formatting. Committing an unchanged rounded
imperial readout preserves its more precise stored value. Formatting is never
permission to round model coordinates.

[Specialized layouts](LAYOUTS.md) defines measurement split selectors, the
Wall Tool, Export, Object Properties, Reference Image settings and calibration.
Their composition, hit areas, labels and dependent states supplement these
shared widget rules.

## SLIDE-01: sliders and reset

Clicking the track immediately jumps the handle to the pointer and begins a
drag; there is no page-step repeat timer. Pressing the handle preserves the
grab offset. Dragging can reverse direction freely. Release commits; Escape
restores the drag-start value. Hiding/disabling or losing the mouse grab clears
drag state. Horizontal/vertical sliders use corresponding resize cursors.

Horizontal groove: 6 high, radius 3, `hoverBackground`; thumb: 16 wide,
5 px vertical overhang, radius 8, `sliderHandle`. Disabled groove uses
`disabledBackground`, disabled thumb uses `disabled`.

Composite/grid/line controls pair sliders with numeric entry and reset buttons.
The field and slider represent one value; resetting removes the override and
restores the inherited/default value. Group continuous changes into one undo
step. Disabled dependencies disable the label, slider, field and reset group.

### SLIDE-02: selector, position and amount semantics

Do not give every slider the same filled-track treatment. The meaning of the
control determines whether the track before the handle represents anything:

| Kind | Meaning | Track treatment | Examples |
| --- | --- | --- | --- |
| Selector | One choice from discrete alternatives, like a row of radio buttons | No accumulated fill; highlight the chosen position | Wall thickness preset selector; measurement display-mode selectors |
| Amount | How much of a quantity/effect is applied | Distinguishable filled portion from minimum to handle | Grid intensity, line weight, border size, vignette/texture strength, highlights/midtones/shadows, texture scale |
| Position/direction | A position or direction rather than an accumulated quantity | No amount fill, even when continuously adjustable | Texture rotation Angle |

A numeric value alone does not make a slider an amount control: preset indices
are numbers too. Conversely, discrete stepping does not make a quantity a
selector. Classify by what the user is changing, independently of orientation,
range and the widget class used to implement it.

For an amount, fill fraction is `(value - minimum) / (maximum - minimum)`, clamped
to 0..1; handle a zero-length range without division. Fill follows the control's
minimum end, including inverted orientation. A 0..2 slider at 1 is half filled.
Keep unfilled and filled portions distinguishable in enabled and disabled
appearances. A selector must not acquire a progress-bar appearance simply
because a new framework's default slider paints a filled segment.

**Baseline limitation:** the current shared horizontal Qt stylesheet sets groove
and sub-page to the same `hoverBackground` color. It does not consistently encode
the semantic distinction above. The existing gallery captures that appearance;
they must not be interpreted as a requirement that amount sliders have no fill.
This section records the intended distinction explicitly. An amount-fill visual
reference/color needs review when that styling is implemented; this documentation
change does not restyle the app or claim that an existing screenshot tests it.

## COLOR-01: picker contents and state machine

The picker has a two-dimensional saturation/value plane and a one-dimensional
vertical hue strip, using HSV consistently. Saturation increases left to right;
value increases bottom to top. Hue increases downward. SV minimum is 250 x 220,
hue strip is 32 wide. Both show crosshair cursors and outlined position markers.

Numeric layout is two vertical triplets: Red/Hue, Green/Sat, Blue/Value.
RGB: 0..255 integers; Hue: 0..360 degrees; Sat/Value: 0..100%, one decimal.
Hex accepts 3 or 6 hex digits, with or without `#`, case-insensitively. Keep
partially typed hex text intact; it does not change the last valid color.
Normalize to `#rrggbb` on acceptance. Retain the chosen hue through black/gray
states. Arrow keys change hue by 1 degree or SV by 1 percentage point.

The popup has no OK/Cancel buttons. It opens to the **left** of its color button
with a 4 px gap, aligned at its top, clamped to the screen. Changes preview live.

| State/event | Result |
| --- | --- |
| Just opened | Visible, unarmed; traveling from button does not close it |
| Pointer moves inside | Arm dismissal |
| Armed, pointer leaves with no buttons down | Accept and close |
| Pointer leaves while dragging | Keep open and continue the control's drag |
| Last button released outside | Keep open, disarm; allow release to reach control |
| Disarmed pointer stays outside | Keep open |
| Pointer moves inside again | Rearm; next unengaged leave accepts |
| Click outside, even before first entry | Accept and close; consume the dismissal click |
| Right-click inside or Escape | Cancel, close and restore pre-picker appearance |

An accepted color equal to the inherited theme color removes/avoids the override.
Lines overrides both `objectOutline` and `wallOutline`; to become inherited again,
the chosen color must match both. Background also affects physical-object
backgrounds. Border overrides `rulerBackground`, grid overrides `grid`. The
button displays a 16 x 16 swatch, a space, then `Theme` or the explicit color.
Reset is enabled only when an override exists.

## TAB-01: tabs and section headings

Sidebar tabs paint centered icons, retaining accessible names/tooltips. Export
is compact/square; the other three divide remaining width equally. No sidebar
tab scroll buttons. Normal inactive tabs use `controlBackground`/`mutedText`;
selected tabs use active colors; selected hover uses `activeHoverBackground`.
Inactive Export is emphasized with `hoverBackground`/`text`, but still has its
own selected state. Generic tab padding: 10 vertical/14 horizontal, 2 px right
gap, radius 5 on top corners, minimum content height 24.
Sidebar tabs use 32 x 32 icons, 6 px vertical padding and a 32 px minimum
content height so the larger icons fit without increasing the tab strip height.

Export sections look like tab headings, but collapse their own content rather
than switching pages. They are 40 high, checked when expanded. Current chevron
is down when expanded, up when collapsed. The whole heading is clickable.
Their hover/pressed/focus rules are in the resolved stylesheet. Section choices
survive save/restore. Digital/Architectural are actual mutually exclusive tabs,
with no redundant Mode label.

Shared noncollapsible headings put a centered icon/text group between flexible
horizontal lines. Optional icons are 18 px, icon-to-text spacing is 6 px, and
both line-to-group gaps are 10 px. Text padding is 4 px top/bottom and zero
left/right. Composite's Vignette/Texture use this same component.
Object Properties and Reference Image use it with an
interactive collapse arrow; click or Space/Enter toggles it.

## DIALOG-01: prompts

Application messages are themed, non-native, plain-text dialogs with 48 x 48
status icons and semantic warning/error/info colors. Minimum size is 440 x 180,
capped to screen size. A short message must not collapse to a tiny popup.
Allow longer content to grow. Export replacement paths stay on one line where
screen space allows, wrapping only when necessary; do not split at the drive
letter. Unsaved-project default is Save; replacement-export default is No.
Retain labels, order and escape behavior for each dialog; use reference captures
and `check_popup_dialogs.py`, not the new framework's arbitrary default ordering.

Geometry issues present Remove/Highlight/Repair individually. Unsupported
actions stay visible but disabled. Escape/window close cancels the entire staged
load. Repair descriptions and backup/recovery details must remain readable.

Project Open/Save, export and reference-image browsing use native file dialogs.
The themed message/dialog rules above do not authorize replacing the native file
explorer with a custom widget. Missing UI icons warn once and use transparent
fallback artwork rather than preventing startup. Disabled Paste retains its icon.

## Inherited widget behavior when porting

The [Qt-to-browser contract](WEB_MIGRATION.md) adds behavior not fully visible
in static captures: native text undo/correction, popup highlight versus commit,
focus/Enter/Tab routing, wheel stepping, pointer capture and CSS box sizing.
Use its recorded Qt observations and browser acceptance cases when selecting
a replacement widget library; matching colors and labels alone is insufficient.
