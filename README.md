# Planner

Draw floor plans, arrange furnishings, and export drawings for sharing or printing.
Save editable projects as `.plan` files.

## Run from source

From the repository root on Windows:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe planner-main/main.py
```

For runtime dependencies only, install `planner-main/requirements.txt` instead.

## Repository layout

- `planner-main/`: the self-contained application and runtime resources.
- [checks/](checks/README.md): regression tests and synthetic fixtures.
- [tools/](tools/README.md): reusable developer utilities.
- [docs/](docs/README.md): development and implementation documentation.
- `demos/`: reserved for future demonstrations; none are bundled yet.

Run checks with `python checks/run_checks.py`. Test output goes to ignored
workspace directories, outside the application. See [Contributing](CONTRIBUTING.md).

## Licensing

Copyright (c) 2026 Dieter Stassen. A license for the original project code has
not yet been selected. Bundled third-party notices remain in
[LICENSES.txt](planner-main/LICENSES.txt) and beside their respective resources.

## User guide

Start with [Welcome to Planner and quickstart](planner-main/docs/help/README.md), followed by
its linked table of contents. The same guide is available inside Planner from
**Help > Help**, or **F1**.

## Technical documentation

Start at the [documentation index](docs/README.md) for development, resource
authoring and future-port references.

- [Development setup and command-line tools](docs/DEVELOPMENT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Porting and UI parity specification](docs/parity/README.md)
- [Help authoring and viewer behavior](docs/HELP_AUTHORING.md)
- [Furnishing definitions](docs/resources/FURNISHINGS.md)
- [Themes](docs/resources/THEMES.md)
- [Textures](docs/resources/TEXTURES.md)
- [Assets](docs/resources/ASSETS.md) and [fonts](docs/resources/FONTS.md)
