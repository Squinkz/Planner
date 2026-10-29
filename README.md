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
To build a Windows executable with editable external resources, see
[Windows executable build](docs/WINDOWS_BUILD.md).

## Repository layout

- `planner-main/`: the self-contained application and runtime resources.
- [checks/](checks/README.md): regression tests and synthetic fixtures.
- [tools/](tools/README.md): reusable developer utilities.
- [docs/](docs/README.md): development and implementation documentation.
- `demos/`: editable demonstration plans, currently a prewar rowhouse and a
  three-bedroom apartment.

Run checks with `python checks/run_checks.py`. Test output goes to ignored
workspace directories, outside the application. See [Contributing](CONTRIBUTING.md).

## Licensing

Copyright (c) 2026 Dieter Stassen. Original Planner code, tests and build tools
are licensed under [GPL-3.0-only](LICENSE).

The code license does not cover the separately copyrighted graphics and branding:

- [Original graphics terms](planner-main/ASSET_LICENSE.txt) permit inclusion in
  shared editable plans, exports and printed work, including commercial work,
  but not standalone asset redistribution.
- [Branding terms](planner-main/BRANDING_LICENSE.txt) permit the logo and app
  icon within unmodified official Planner packages, not separate redistribution
  or use on modified distributions.
- Third-party components retain their own licenses. See
  [LICENSES.txt](planner-main/LICENSES.txt) and notices beside those resources.

See [licensing scope and redistribution](docs/LICENSING.md) and
[release/version guidance](docs/RELEASING.md).

## User guide

Start with [Welcome to Planner and quickstart](planner-main/help/README.md), followed by
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
