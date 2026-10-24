# Contributing

Use Python 3.14 and install the pinned dependencies from the repository root:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe planner-main/main.py
.\.venv\Scripts\python.exe checks/run_checks.py
```

See [development](docs/DEVELOPMENT.md), [architecture](docs/ARCHITECTURE.md),
[resource authoring](docs/README.md) and the [parity specification](docs/parity/README.md).

Keep runtime code and bundled resources in `planner-main/`. Tests and fixtures
belong in `checks/`, reusable developer utilities in `tools/`, and developer
documentation in `docs/`. `demos/` is reserved for future demonstration material.
Diagnostics, temporary files and generated screenshots are local output.

Use PascalCase function names, camelCase variables and spaces around operators
and keyword arguments. Prefer readable code over small one-use wrappers.

Preserve appearance and editing behavior when changing rendering or geometry.
Run the checks appropriate to the change. Furnishing definition files are the
source of truth for catalog dimensions and composition.

The in-app guide under `planner-main/docs/help/` is maintained separately.
Do not edit those files without an explicit request from the project owner.

Before publishing a new asset, record its source and retain applicable notices.
The project has not yet selected a license for its original code. Bundled
third-party notices are in [LICENSES.txt](planner-main/LICENSES.txt).
