# Synthetic plan fixtures

These plans are generated test data, not user projects or demos.

- `rectangular_rooms.plan`: shared rectangular room boundaries and openings.
- `angled_rooms.plan`: oblique walls, varied widths and wall attachments.
- `dense_furnishings.plan`: multiple furnished rooms, curved artwork, counters,
  stairs and columns for geometry and export comparisons.

The fixtures contain no personal floor plans, reference images or saved history.
The current bundled furnishing definitions remain authoritative.

`../editor_interactions.py` loads `dense_furnishings.plan` for frozen/current
dragging, snapping and rendering comparisons. It adds an independently authored
isolated oblique wall and centers the selected endpoint before each gesture.
The shared matrices cover collision switches and modifier combinations without
using personal project data or local diagnostic outputs.
