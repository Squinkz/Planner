# Specialized UI layouts

These composition rules supplement [CONTROLS.md](CONTROLS.md). A shared slider,
field or heading does not imply a generic form layout. Preserve the compositions
below alongside the widget's input, theme, focus and disabled-state rules.
Dimensions are logical pixels. Native style-derived slider handle centers are
used where specified instead of equally spacing arbitrary HTML elements.

## SETTINGS-01: measurement split controls

Settings > Dimensions uses two equally stretched columns separated by 48 px.
The page has margins left/top/right/bottom 16/20/16/16. Units and Canvas precision
occupy equal top-row columns, Units left and Canvas precision right, without a heading.
Each uses Appearance-style composition: a 120 px right-aligned caption, 8 px
gap and dropdown. A 12 px gap precedes the two-column body. The right column
contains Walls, Mode, then Doors, Windows, Stairs and Counters vertically, with
24 px between row layouts.
Each row is a horizontal composition with 16 px gaps:

`70 px bold object heading | vertical selector | expanding labels | reset`

Doors/Windows have three positions from top to bottom:

1. Split all wall measurements (wire value 0).
2. Split on facing side only (wire value 1, factory default).
3. Do not split wall measurements (wire value 2).

Stairs/Counters have only two positions:

1. Split wall measurements (slider index 0, wire value 0).
2. Do not split wall measurements (slider index 1, wire value 2, factory default).

There is no facing-side choice for stairs/counters. Never equate a two-position
selector's index 1 with wire mode 1. These are selectors, not amounts or progress
indicators. The vertical controls invert both appearance and controls so smaller
indices are at the top. Single/page steps are one index. Doors/Windows tracks
are 112 px high; Stairs/Counters are 49 px. The groove is 6 px wide with radius 3;
the 16 px high rounded thumb overhangs 5 px horizontally. Ordinary semantic
slider colors and disabled colors apply. Each selector is 20 px wide, keeping
the complete 16 px thumb inside its widget at every position.

Labels occupy a zero-margin, zero-spacing vertical area. First/last labels anchor
to top/bottom, and the middle label is centered. The category heading and reset
button remain vertically centered beside the complete selector, not beside one
individual label. Reset uses refresh artwork, 24 px icon, width 34, maximum height
32, and is enabled only when that category differs from its factory mode.

The labels and their surrounding area participate in selection. Press there to
focus the slider and immediately choose the corresponding height; drag across
labels to keep updating it, release to end the gesture. Track/handle interaction
uses the shared slider. Wheel input over the slider or label area changes modes,
not the dialog's scroll position. Positive wheel movement moves upward through
the choices; partial angle deltas accumulate to 120 units, while pixel scrolling
moves one position per nonzero event. Clamp at the ends. A label is not a
read-only caption or an independent radio button.

The left column has a bold centered Measure heading, then a checkbox tree styled
like the World visibility tree, without selected-row highlighting. Draw dimensions
is its initially expanded root, with Walls, Stairs, Counters
and Railings as children. Rows are 32 px high with 24 px indentation.
Expanding or collapsing the root fits the tree to 160 or 32 px respectively.
A bold centered Grid heading follows, with Draw Grid beneath it as a
label-left, checkbox-right form row, then an Appearance button that switches to
the Appearance tab. When the editor grid is off, Appearance's Grid heading,
captions, intensity sliders, number fields and reset buttons are disabled.
Their values are retained, and line-weight controls remain independent.
Master and category values
remain separate. Turning off the master retains nonempty category choices.
With no categories enabled, the Options master is unchecked and read-only, painted
disabled without disabling its branch or children. Checking a category restores it.
View > Toggle dimensions and M remain available
and enable walls if activated with no remembered categories. Units, precision
and Draw Grid remain available independently. Export overrides must not replace
the project settings edited by these controls.

The right column has a bold, centered Walls heading, then a Mode dropdown above
the split selectors. Exterior stacked is the factory default. All retains every
wall measurement; Exterior retains only outer boundary dimensions. Exterior stacked uses
up to three rows: openings nearest the wall, room divisions next, and overall
length outermost. Redundant rows are omitted and remaining rows close up. All split
selectors, their labels and reset buttons are hidden and disabled in stacked mode,
replaced by one Wall reference dropdown: Centerline or Wall faces (default).
Its field aligns with Mode. Other modes restore the saved split controls.
Turning
off wall dimensions or the editor dimension master additionally disables Mode
and its label, plus Wall reference. These controls re-enable from their saved values when wall
dimensions return; changing their enabled state does not alter their values. This is separate from the
wall visibility checkbox and the opening/counter/stair split selectors.

Build options use the same label-left, checkbox-right convention for collision
settings. The icon/text captions remain clickable, and all three checkbox fields
share a column and 32 px row height. Standalone checkboxes in Export use form
rows too; the Dimensions and Visibility trees retain their hierarchy and styling.
Coverage: `check_checkbox_layouts.py`.

## BUILD-01: Wall Tool composition

Build content has 14 px margins and a shared Wall Tool heading, then 8 px space.
Below is a horizontal composition with 14 px gaps:

`shape column | 1 px vertical divider | expanding preset/material column`

Shape choices Line, Square and Circle are mutually exclusive 24 × 28 buttons,
with 24 × 24 artwork. Circle uses octagon artwork. Flexible vertical spaces
separate the three choices. Line starts checked. The divider uses the semantic
border color. Do not turn this column into a horizontal row or merge it with the
thickness presets: shape and thickness are independent choices.

The right column contains a horizontal four-position width selector, then 8 px
space and the Material form. The selector has minimum width 164, an inset slider
layout of 12/52/12/0, and a horizontal-resize cursor. Four 24 × 28 preset tiles
sit at y=0, with radius 4 and normal/active semantic backgrounds. Their dimension
captions use 8 pt text in centered 44 × 18 boxes beginning at y=30. Each tile and
caption is centered over that preset's actual slider-handle center, including
the widget inset. Compute these centers from the slider's usable travel and
thumb geometry, not the full selector width divided into four equal cells.

The slider range is 0–3, with one-position steps. Defaults are 100/150/200/300 mm
and index 2 is selected. The caption follows project units and effective nominal
imperial defaults. The whole icon/caption area and slider select the nearest
preset on press/drag. Wheel input on either area adjusts the same slider. Q/W
step down/up; Escape during the selector's mouse gesture restores its starting
index. This is a discrete choice, without accumulated amount fill.

The Material form has no margins, a 16 px label/field gap and long-row wrapping.
The dropdown uses 32 × 24 swatches and shares material choices with object
properties. Shape, width and material configure newly drawn walls. Changing
these defaults does not edit selected existing walls. Their object-properties
controls remain independent.

Objects follows after 16 px with its shared heading and 8 px space. Doors,
Windows, Miscellaneous and Annotations are separate wrapping icon palettes using
the same flow layout as Furnish. Captions anchor below each icon; categories do
not become one fixed grid. The last category includes Label, Arrow, Measure,
Angle and North. Wrapping and horizontal overflow retain readable widget minima.

## EXPORT-UI-01: Export panel composition

The Export tab is divided into three independently sized regions. Heading,
path/browse, Type, separator and Digital/Architectural tabs stay above the scroll
area. Canvas, Border, Grid, Line Weight, Dimensions, Composite and Visibility
scroll together in that order. The 48 px Export action stays below the sidebar
splitter, outside this scroll area, with margins 14/8/14/14 and 28 px artwork.
Object Properties is hidden while Export is active. Returning to another tab
restores the previous properties split, rather than allocating a new default.

The panel's outer layout has zero margins and spacing. Heading margins are
14/14/14/0, path-row margins 14/14/14/6, and Type/mode margins 14/8/14/6.
Path takes available width beside a fixed 44 × 32 folder button with 26 px
artwork and a 6 px gap. Type has an 8 px label/field gap. The separator has
14/4/14/4 margins. Do not put the header or action inside the sections scroller.
The section page has 14 px margins, 20 px between sections, and 12 px between
a 40 px collapsible heading and its content. Section contents use 12 px spacing.
Sections initially collapse unless restored. Ordinary controls are 32 px high,
while the small captions above composite amount rows retain text height.
Hidden horizontal scrollbars do not authorize compressing readable controls
below their minima or discarding their horizontal scroll range.

Digital Scale is a label, 120 px settings number box and expanding unit selector
with 8 px gaps. PNG density is px/m or px/cm. The next row is Resolution with
equally stretched width and height fields separated by ×. Editing either field
updates the other and density, including border extent. Architectural Scale
uses an editable ratio dropdown, with PPI and an editable PPI dropdown alongside
it for PNG, then a resolution readout on the next row. SVG uses units/m in
Digital, omits both resolution rows and PPI, and removes the entire Composite
section. Optimized PNG uses the PNG layout. See EXPORT-01/03 for conversion,
defaults, encoding and bounded-preview rules.

Numeric widths below are the requested widths. The shared theme's readable
minimum takes precedence when larger: under the current theme, the nominal
72/80 px settings boxes occupy 88 px. Preserve the resolved minimum rather than
forcing an input below the shared widget contract.

| Section | Internal composition and dependent states |
| --- | --- |
| Canvas | Content-sized right-aligned labels, 8 px horizontal and 12 px vertical gaps. Theme, Background, Walls, Lines, then a Solid Objects caption with its checkbox in the right-hand field column. Color rows contain an expanding swatch button, 8 px gap and 32 px reset. Theme inheritance and explicit color overrides are distinct states. |
| Border | Full-width style dropdown without a redundant label, then Color and Border Size. Size caption sits above slider plus 72 px number field. Range 1–128, initial 28, expressed in output pixels/SVG units. None disables color/size dependents. |
| Grid | Show Grid caption with a right-hand checkbox, Color row, then caption-above-control amount rows. Each row is expanding slider, 80 px number, 34 px reset with 8 px gaps. Overall intensity is 0–2, others 0–1, three decimals. An extra 8 px separates Overall from Major/Minor/Origin. Show Grid off disables dependent groups. |
| Line Weight | Caption-above-control rows for Base width, Walls, Architectural objects, Furnishings and Dimensions. Slider, number, reset with 8 px gaps. Base width is 1–4 px with 104 px field; other fields are 0–2 multipliers with 88 px fields. Resets are 34 px. |
| Dimensions | Units label and expanding 32 px dropdown separated by 16 px, then a centered Measure heading and checkbox tree. Draw dimensions is the collapsible, initially expanded root with Walls/Stairs/Counters/Railings children. Rows are 32 px with 24 px indentation and no selection highlight; height fits 160 px expanded or 32 px collapsed. A centered Walls heading follows, then Mode and the conditionally visible Wall reference dropdown in one aligned form. Wall reference appears only for Exterior stacked. Wall controls and heading disable when export wall dimensions are off. No precision or split selectors are provided here. |
| Composite | Shared centered Vignette and Texture subheadings. Enable Vignette caption with a right-hand checkbox, then Strength caption and slider/80 px field/32 px reset. Texture dropdown follows its heading, then Scale, Angle, Strength, Highlights, Midtones, Shadows. Captions sit 4 px above rows, row gaps are 8 px. Texture None disables all amount groups, stretch textures also disable Scale. Vignette off disables Strength. |
| Visibility | Expanded scene checkbox hierarchy cloned from World, without reference-image controls. No selection highlight, 24 px indentation, height fitted to all rows. Preserve tree scroll position when rebuilding. |

Slider and number fields stay synchronized. Resets use the relevant factory or
texture-derived default, not a universal zero. Texture selection exposes its
filename in the tooltip. Export number fields use settings-style arrow buttons,
not the arrowless property scrub appearance. Color pickers preview changes,
preserve explicit versus inherited colors and support cancellation. Export has
its own undo/redo and camera/crop state. Presentation overrides must not leak
into the editing view. Native file pickers remain native (DIALOG-01).

## PROPERTIES-01: Object Properties composition

Object Properties is outside the tab pages, below an 8 px vertical splitter.
The initial upper/lower split is 2:1. Double-clicking the divider restores that
split, including when the properties panel is collapsed. The centered collapsible
icon/text heading stays above a separate frameless scroller. Its container has
1/12/1/0 margins, heading side insets 13, and scrolling content margins
13/8/14/14. Collapsing retains the heading and previous expanded height.
Horizontal overflow keeps readable field minima and a scroll range, even though
the horizontal scrollbar is hidden. Do not replace these controls with tiny
fields when the user narrows the sidebar.

The object identity heading inside the scroller is separate from the outer
Object Properties heading. Preserve the selected object's name and ID, selection
count or Multiple types message. Missing furnishings show the original missing
asset name. No selection shows No selection. Reference mode replaces the outer
heading and content temporarily, without deleting the normal identity widget.

The ordinary form has 16 px top inset, 16 px label/field gap and long-row
wrapping. Its visible rows share a polished height of at least 32 px. Position
is one labeled row containing equally stretched X/Y fields with 6 px gap. Size
is one labeled row containing Width, link button, Length with 6 px gaps and
equally stretched numeric fields. Both dimensions remain local/oriented sizes
regardless of Global/Local Transforms. Link state constrains numeric edits only,
never canvas handles. On deselection it returns to its type's default: on for
furnishings, pillars and fireplaces, off for control-point geometry. See SIZE-01.

| Selection | Distinct form composition |
| --- | --- |
| Furnishing / north arrow / pillar / column | Position precedes Size, then Angle and applicable flip/material controls. Position reports center in resize mode and the active rotation pivot in rotation mode. Editing it translates the geometry and pivot together. |
| North arrow opacity | After the main form, a full-width row uses the same 24 px opacity.svg icon, expanding 0–100 slider and 0.00–1.00 readout as labels. It defaults to fully opaque, supports mixed selections of north arrows, and applies to the entire symbol on canvas and in PNG/SVG exports. Slider drags form one undo step. Opacity survives project/history persistence, cloning and copy/paste. |
| Wall / counter / stair / railing / elevator | Size remains paired. No independent whole-object Position row. Selected control points expose their own coordinates below the main form. Material and automatic-sizing rows appear only for supported types. |
| Door / window attachment | Single Length row instead of paired Size, except fireplace. Sliding/pocket variants add Door size, pocket doors omit the ordinary Length row. Silled windows add Sill depth. Wall-inherited width is not an independent editable size. |
| Fireplace | Paired Size with its usual depth/span convention, Material and supported facing action. No independent whole-object Position or rotation mode. |
| Selected control point | A Point group follows after 12 px space. Group margins 10/18/10/10. One Position label precedes paired X/Y, with 6 px gap. Chamfer appears only for eligible two-ray wall/counter/stair junctions with an actual moving cut. |
| Stair / railing sizing | Autosize checkbox, then Step count/Tread depth for stairs or Post Count/Segment Width for railings. Each row stacks a selectable calculated readout and its manual editor. Manual editors appear only when all selected objects have Autosize off; mixed modes use readouts and a partial checkbox. Stair Direction is a square icon button whose redo/undo artwork follows direction state. |
| Label | Text, Position, Size, Point size, then a full-width opacity row. Text editor is 80–110 px high and Tab advances focus. Size has two equally stretched fields and no link button: either dimension always resizes proportionally. Opacity uses the 24 px opacity.svg icon instead of an Intensity caption, an expanding 0–100 slider and a 0.00–1.00 readout, with 10 px gaps. The row is at least the normal property-row height. Form row spacing is 8 px. |
| Arrow | Length, Direction icon button, Solid tip checkbox, Tip size, Tail thickness, then the same full-width opacity icon/slider/readout row as labels and reference image settings. Direction alternates Redo/Undo artwork with its persisted flip state, including undo/redo. Retain the arrow's 0.00–1.00 readout. The row is at least the normal property-row height, and form rows have explicit 8 px spacing. Endpoint coordinates use the shared Point group. |
| Measurement guide | Only Length from the arrow form, plus the applicable Point group. Arrow appearance rows do not remain visible as disabled controls. |
| Angle guide | Position for the middle anchor, then Angle. Angle is 0–180°; undefined angles disable the field and show Undefined, differing values show (different). Endpoint coordinates use the shared Point group. See GUIDE-01. |

Door/window action rows have an 8 px top inset and 16 px label/field gap. Their
buttons are square at the property row height with 24 px artwork. Mirror along
the wall uses flip_h, across the wall uses flip_v, measurement side uses the
measurement icon. Labels and availability vary with hinge, slide, pocket and
facing support. Measurement-side controls also depend on measurement visibility
and facing-side split mode. Do not show every action for every opening.

Room Label reuses the Label form and its existing dimensions, spacing, numeric
controls, position/pivot behavior and opacity row. Its text editor row is labelled
Name and uses a single-line QLineEdit in a standard-height row. Ordinary labels
retain their multiline text editor. A selectable, read-only Area value
and Units dropdown follow it before Position and Size. Units defaults to Project.
Both rows are hidden for ordinary labels, whose multiline editor remains labelled Text.
All property rows use the same polished control height and 8 px vertical gaps.
Opening facing/measurement controls continue directly after the window-well rows.
Mixed room-label selections display (different) when their calculated areas differ.

Property fields use the arrowless draggable numeric control (NUM-01), current
project units, suffixes and deferred typed commits. Scrubbing groups a gesture
into one edit, and cancellation restores it. Mixed selections retain blank
(different) fields and apply supported edits per object, including individual
aspect ratios. Unsupported mixed types show identity/count without a misleading
editable common form. The exact property inventory is in the object matrix.

## REFERENCE-01: Reference Image settings composition

Entering reference editing changes the outer heading to Reference Image with
image.svg artwork. There is no duplicate reference title inside the scroller.
The panel uses a zero-margin vertical layout with 8 px spacing, in this order:

1. Expanding path field and fixed 44 × 32 folder button, 26 px artwork, 6 px gap.
2. Opacity icon (24 px), expanding amount slider and percentage readout. There
   is no separate Opacity text label. Range 0–100%, initial 50%.
3. Zero-margin form with 16 px label/field gap and long-row wrapping: Position
   X/Y, Size Width/link/Length, Angle. Paired fields use equal stretch and 6 px
   gaps. Numeric fields are the shared arrowless property scrub controls.
4. Full-width Calibrate Scale text button.

Width/Length are the image's oriented dimensions, initially linked. Coordinate
and angle values use current units/degrees. X/Y follows the image center except
while rotation mode is active, when it follows the pivot. A property drag can
be cancelled atomically, including its pivot. Link choice resets when reference
editing closes. There is no Locked checkbox or separate position-image command.

The separate Reference Image tree branch starts off. First enable opens a native
image picker; cancel or failed load keeps the previous state. Enabling or clicking
the visible entry opens this panel and expands Properties. B toggles visibility;
enabling also opens World and the panel. Alt+B reopens settings only while the
image is visible. Merely returning to World does not reopen editing. Closing via
void click, Escape outside a gesture, tab change or disable restores the previous
selection, properties split/collapse and scroll state. Scene selection remains
blocked while reference editing is active.

While open the image is selected with the same resize/rotation/pivot handles as
furnishings. Scene objects cannot be picked and appear dimmed, while the image
and handles retain their contrast. Idle hints are hidden, active transform hints
remain. Image replacement retains center, angle and width and adapts height to
the new aspect ratio. Reference data is embedded project state, separate from
scene undo, collision, grouping and export visibility. LAYOUT-01 and HOVER-01
define the full transform and restoration rules.

## CALIBRATE-01: calibration interaction and distance prompt

Calibrate Scale requires an active visible reference image. It cancels pending
image gestures and disables its settings panel while leaving camera pan/zoom
available. The image cannot transform during point placement. Two separate
clicks place endpoints. After the first click, a line previews the second point.
Alternatively, press and drag past the platform drag threshold to place the
second point on release. A short press/release retains the two-click workflow.
The temporary line, measurement and normal point circles remain visible even
when scene measurements are off. Placed points can be dragged and show the usual
hover color and move cursor. Ctrl uses the annotation 15° snap path with visible
angle guides, active local/global origin, enabled snap target types and Alt
inversion. These points do not become scene objects.

Hints use the existing two-column key/action layout, never one prose line:

| State | Key/action rows |
| --- | --- |
| Placing | Left Mouse / Place point; Escape / Cancel |
| Two points placed | Enter / Confirm; Escape / Cancel |
| Dragging point | Ctrl / Snap to 15° increments; Right mouse / Cancel |

Right-click/Escape during a point drag restores that drag's starting points and
retains calibration. Outside a point drag it cancels the tool. Enter requires two
distinct points. It opens a window-modal Calibrate Reference Image dialog with
measurement icon, wrapped explanation, Distance row, inline error area and
standard OK/Cancel buttons. Minimum width is 440 px capped by available screen
width. The Distance row is an expanding ordinary settings UnitSpinBox with
arrow buttons, followed by a smaller fixed-size unit dropdown anchored right,
with 6 px gap. Do not substitute an arrowless scrub field or add a Units label.
No suffix duplicates the adjacent unit selector. Distance starts focused and
selected, uses six decimals, and defers typed commits.

Units are m, cm, mm, ft / in and in, with full-name tooltips. Initialize from
project units, mapping Adaptive Metric to Meters; Adaptive Metric is not an
option in this prompt. Changing units commits pending text and converts the
physical value instead of reinterpreting the same number. Feet/inches parsing
remains available. This choice does not change project units or persist.

OK commits the distance and rejects zero, nonfinite values or image dimensions
outside valid bounds with a themed inline error, keeping the prompt open and
image unchanged. Valid confirmation uniformly scales image width, height,
center and custom pivot about the first point. Preserve angle, aspect ratio and
opacity. The corresponding image feature under the first point stays fixed.
Cancel returns to the two picked points. Success exits calibration and re-enables
settings. Leaving reference mode, image replacement or project load cancels all
temporary points/dialog state. Only the resulting reference transform is saved.

## Composition map and precedence

- Paired Position/Size properties, centered link button, per-type link defaults,
  and reference-panel restoration: SIZE-01 and LAYOUT-01. Paired fields are not
  separate full-width form rows. Labels have no unlink option.
- Reference Image replaces the properties heading with image artwork and its own
  controls while preserving the previous properties state. Opacity uses its icon
  at the slider's left, not a separate Opacity text row.
- Build settings use General/Walls/Doors/Windows/Misc sub-tabs. Auto Tread Depth
  and Auto Railing Sizing are separate groups. Collision checks occupy one aligned
  column left of the midpoint, with icon/labels aligned to its right (BTN-01).
- Export has its pinned action and independently collapsible sections, and its
  Digital/Architectural controls vary by format (EXPORT-01). Vignette/Texture use
  shared centered subheadings. Amount controls pair slider, number field and reset.
- Furnish search includes its search artwork inside the field, followed by Sort
  then grid/list. That row stays pinned above scrolling results (LAYOUT-01).
- The centered icon/text group and line gaps of headings, sidebar tab metrics,
  settings number boxes versus arrowless scrub fields, themed prompts and native
  file pickers remain defined in TAB-01, NUM-01 and DIALOG-01.

Evidence: `check_measurement_settings.py`, `check_structural_measurements.py`,
`check_new_wall_settings.py`, `check_build_wrapping.py`, and the geometric
composition checks in `check_parity_layouts.py` and `check_parity_panel_layouts.py`.
Export behavior is covered by `check_export_settings.py`, `check_export_scale_modes.py`,
`check_export_dropdowns.py`, `check_export_button.py`, `check_export_history.py`
and `check_export_measurement_transitions.py`. Property/reference behavior is
covered by `check_properties_panel.py`, `check_linked_size.py`,
`check_reference_image.py`, `check_reference_calibration.py`,
`check_angle_point_properties.py` and `check_fireplace_dimension_conventions.py`.
Dated screenshots in the original
UI gallery are supporting evidence, not a substitute for these current rules.
