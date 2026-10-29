# Planner parity specification

This is the framework-independent reference for reproducing Planner's desktop
behavior, appearance and project interchange. Original capture baseline: 17 October 2026. Current contracts reviewed 26 October 2026 for Alpha 0.1.1.
It describes the implemented product, rather than a proposed redesign.

Start here:

1. [Controls and visual rules](CONTROLS.md): state colors, dropdowns, menus,
   numeric entry, selector versus amount sliders, color pickers, tabs, headings and dialogs.
2. [Layout and viewport interactions](INTERACTIONS.md): panel arrangement,
   selection, hover, cursors, gestures, export transitions and history.
3. [Project interchange](PROJECT_FORMAT.md): coordinates, records, references,
   embedded resources, history and recovery.
4. [Verification](VERIFICATION.md): executable scenario index, portable numeric
   examples, captured screens, measurements and known coverage limits.
5. [Reference gallery](reference/GALLERY.md): actual desktop renders, with
   machine-readable widget geometry and semantic palette values alongside them.
6. [Qt-to-browser migration](WEB_MIGRATION.md): inherited widget defaults, React/
   DOM event differences, focus, CSS sizing and browser acceptance requirements.
7. [First-port review](FIRST_PORT_REVIEW.md): pinned-source findings from the
   October 9 React port, separating verified differences from runtime risks.
8. [Object behavior](OBJECTS.md): all 31 current types, creation defaults, properties,
   handles, attachment, visibility, measurements, collision and drawing rules.
9. [Workflow and rendering examples](EXAMPLES.md): replayable editing checkpoints,
   saved projects and frozen PNG/SVG object renders with explicit scale/crop data.
10. [Corner chamfers](CHAMFERS.md): cutting-plane geometry, angle/thickness examples,
    zero-to-one convention and the 18 October plan migration.
11. [Help viewer contract](../HELP_AUTHORING.md): portable guide content, navigation,
    focus, theme styling and bundled-resource requirements for desktop and web.

For a new web implementation, read the migration contract before choosing or
building shared controls. It explains which apparent Qt defaults are requirements
that a native HTML input, select, range or generic dialog will not reproduce alone.

[Annotation behavior](ANNOTATIONS.md) covers free angles and movable guide labels.
It extends the current object matrix and render corpus without replacing the
historical UI gallery.

[Specialized UI layouts](LAYOUTS.md) specifies measurement split selectors, the
Wall Tool, Export, Object Properties, Reference Image settings and the calibration
workflow/prompt, including their unique rows and dependent widget states.

Current dimension contracts include Options and Export trees, independent master
toggle semantics, exterior/stacked tiers, wall reference and project/export
override ownership. Room tint/labels, window wells and additional opening types,
weighted lines, shared subdivision and resolved hover/click priority are covered
by the current prose and the 90-scenario index. Dated captures are retained as
historical evidence rather than silently regenerated for these changes.

## How to use this specification

Each rule has a stable identifier. `cases.json` connects identifiers to observable
Given/When/Then examples and existing executable checks. A new framework can use
the same scenarios without importing Python or Qt. Screens establish visual
targets; interaction scenarios establish state transitions. Both matter.

Use the bundled fonts, icons and source graphics. Preserve semantic theme roles
instead of copying one theme's hex colors into components. Distances in these
documents are logical pixels unless explicitly stated otherwise. Record device
scale, font, viewport size and theme when comparing renders.

Where prose cannot enumerate a large data table, the generated reference includes
the exact table: dropdown items/data/tooltips, numeric ranges/steps, widget bounds,
visibility, enabled state, layout margins/spacing and the resolved stylesheet.
These files are evidence from the baseline, not a second implementation.
Current prose contracts and executable checks take precedence over dated capture
metadata for bindings, defaults and controls that change between captures.

## Changes and responsibility

An intentional product change updates its rule, scenarios and affected examples
in the same change. Never regenerate reference images merely to make a failing
comparison pass. Review the difference first. A behavior discovered only in Qt
should be classified as intentional, a platform detail or a defect before a port
copies it. A bug is not automatically a new requirement.

Everyday instructions live in the [user guide](../../planner-main/help/README.md), including
[editing](../../planner-main/help/editing.md), [shortcuts](../../planner-main/help/shortcuts.md),
[export](../../planner-main/help/export.md), [appearance](../../planner-main/help/appearance.md) and
[furnishings](../../planner-main/help/furnishings.md). Resource schemas and implementation notes
are indexed in [technical documentation](../README.md). The
[editing boundary notes](../EDITING_PORTS.md) and [geometry contracts](../GEOMETRY.md)
explain implementation boundaries; this specification explains what a port
must reproduce.

## Scope and limits

The reference suite is a substantial starting baseline, not proof that every
possible app state has been captured. The verification document explicitly
separates automated checks, visual references and manual platform checks.
Native OS window decorations, file pickers, GPU presentation latency and every
combination of themes, objects and modifiers are not certified by offscreen
screenshots. A port needs a reviewed parity run before claiming a 1:1 clone.
