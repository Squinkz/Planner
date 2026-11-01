# Development

These instructions are for contributors running Planner from source.

Planner uses Python, PySide6 and NumPy. The pinned development environment uses
Python 3.14, PySide6 6.11.2 and NumPy 2.4.6 on Windows.

Open PowerShell in the repository root and run:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe planner-main/main.py
```

For compatible runtime dependencies, use `planner-main/requirements.txt` in place of `requirements-dev.txt`.
NumPy loads lazily for CPU texture lighting and containment filtering in scenes
with at least 64 eligible walls. Both use `planner_app.numpy_runtime.LoadNumPy`.
Its unused OpenBLAS pool is limited to one thread before import in the editor and
preview worker; preserve this initialization order when adding array operations.

## Command-line export

Run from the application directory (`planner-main`):

```powershell
python -m planner_app.export_plan drawing.plan 200 -png
python -m planner_app.export_plan drawing.plan 200 -svg
python -m planner_app.export_plan drawing.plan 200 -5000 -5000 20000 15000 -png
```

The argument forms are `PLAN SCALE` and `PLAN SCALE X Y WIDTH LENGTH`. PNG is the default format; `-png` and `-svg` select the format. The former `-auto` and `-ruler` options are removed.

- Scale is pixels per meter, or nominal SVG units per meter. The required argument overrides saved density, scale units and architectural print mode.
- Bounds use millimeters. X and Y specify the lower-left corner; width extends right and length extends up.
- Crop width is `ceil(WIDTH × SCALE / 1000)`; height uses LENGTH. The selected border adds its width on both sides; an enabled title block adds its own extent.
- Explicit bounds override the saved export crop. Without either, automatic bounds enclose export-visible footprints and add 1000 mm on each side.
- Border style and size come from saved export settings, including legacy `ruler` settings. Without an override, the default is Ruler + Reference Zones, as in the Export tab.
- Files are written to `renders/` beside the input project as `<plan>_<scale>p.png` or `.svg`. Repeating an export to the same path replaces that file.
- The CLI applies saved export theme/color, wall style, solid-object/room, grid/origin, units, linework, dimension visibility, wall dimension mode/reference, visibility, title-block, scale-bar and compositing overrides. Partial option groups inherit from editing settings, as in the Export tab. Dimension precision and split settings use resolved export overrides. Texture/vignette affect PNG only. Export display units inherit project units until explicitly overridden. UI themes still come from application preferences.
- Export dimensions are limited to 32,767 units per side. PNG also has a 100-million-pixel allocation limit; SVG has no raster-area limit.
- Preview sampling is independent of export resolution. Oversized PNG previews retain a bounded overview and capture visible detail after navigation stops. SVG previews retain bounded navigation and viewport rasters. These caches share the viewport raster memory budget; previewing a larger image does not bypass file export limits.
- Opaque PNG output uses RGB; transparent backgrounds retain RGBA. Qt's working RGB32 image still occupies four bytes per pixel.

The CLI uses PySide6 and an offscreen Qt application. Drawing text uses the selected
canvas font. Title-block headings use Noto Sans and fields use D-DIN Condensed.
All SVG text, including rulers, scale bars and title blocks, is outlined.

## Local application state

On Windows, the normal Qt GenericDataLocation resolves Planner's app data under
`%LOCALAPPDATA%\Planner`. It holds `preferences.json`, `session.json`, recovery
backups and crash logs. Preferences include the theme pair and catalog view/sort
choices; the session includes the current project and window/panel state.
`PLANNER_PREFERENCES_PATH` and `PLANNER_SESSION_PATH` redirect these files for
isolated tests. `PLANNER_STARTUP_PATH` separately overrides the startup template.

For a first-time profile, close Planner before moving its local app-data folder
to a backup. Open background writers can recreate the session on shutdown.
This does not remove saved plans, `planner-main/startup.plan`, furnishings, fonts,
themes, textures or Help resources. New Project loads the startup template;
Close Project clears the canvas without loading it.
Startup, recovery and project actions activate Build; saved Export settings do
not reactivate the Export tab or start its preview worker during a load.

## Technical references

- [Architecture and checks](ARCHITECTURE.md)
- [Porting and UI parity](parity/README.md)
- [Help authoring and viewer contract](HELP_AUTHORING.md)
- [Furnishing definitions](resources/FURNISHINGS.md)
- [Themes](resources/THEMES.md)
- [Textures](resources/TEXTURES.md)
- [Assets](resources/ASSETS.md) and [fonts](resources/FONTS.md)
