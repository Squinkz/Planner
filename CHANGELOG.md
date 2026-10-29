# Changelog

## Added features

- **Room detection and shading:** enclosed rooms receive theme-based tinting.
- **Room labels:** room names with automatically calculated areas and individual unit overrides.
- **Room Style:** choose between Canvas and Tinted interiors.
- **Solid Rooms:** optionally hide the grid inside rooms.
- **Exterior stacked dimensions:** dimension chains for openings, room divisions and overall lengths, with wall-face or centerline references.
- **Dimension controls:** dedicated wall-dimension options, category visibility, splitting settings and per-object hide/show and flip actions. Manual dimension guides support signed depth extensions with snapping at their endpoints.
- **New opening types:** swinging doors, double doors, awning windows and double-casement windows.
- **Window wells:** configurable depth and optional dashed outlines.
- **Line tools:** solid and dashed lines with selectable line-weight categories.
- **Selection mirroring:** flip objects horizontally or vertically using a shared selection origin or individual local origins.
- **Expanded subdivision and dissolution:** split and join counters, stairs, railings, arrows and line annotations.
- **Drag-and-drop wall tools:** place line, square and polygonal wall arrangements from the Build tab, with scrolling to adjust polygon segment counts during placement.
- **Connected stair annotations:** landing-aware inset lines and directional arrows across connected flights.
- **Grouped visibility controls:** organize object visibility by category.
- **Activity Log:** searchable, persistent records of edits, settings, exports and problems, with restoration to available undo states.
- **Cancellable exports:** progress reporting with rendering and encoding handled in a separate process.
- **Expanded furnishing catalog:** barbecue variants, overhead and corner cabinets, area/round/runner rugs in multiple sizes, a wardrobe rail, walking-person symbol and patio table.
- **User furnishing overrides:** separate user definition and image folders can override bundled furnishings without modifying the defaults.

## Bug fixes

- **Responsiveness:** improved theme switching, furnishing catalog updates and canvas panning, including fractional-pixel movement.
- **Rendering and exports:** corrected wall and opening outlines, small-scale artifacts and SVG masking inconsistencies.
- **Wall and room geometry:** improved precision handling and wall joins, reduced insignificant geometry warnings.
- **Pocket and barn doors:** reserved space can cross collinear control points and T-junctions without relaxing actual doorway collisions. Wall editing preserves door position and size, retaining the last valid drag position when support would be lost.
- **Furnishing duplication:** Shift-duplicating multiple furnishings preserves their stacking order and draw-behind settings.
- **Room label units:** areas default to square metres in metric modes and square feet in imperial modes, while retaining individual overrides.
- **Wall tool input:** corrected inactive modifier hints and unreliable scrolling during polygon palette drags.
