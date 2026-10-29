# Windows executable build

Build on Windows with Python 3.14. From the repository root:

```powershell
py -3.14 -m venv build/windows-venv
.\build\windows-venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build\windows-venv\Scripts\python.exe tools/build_windows.py
```

The build uses pinned PyInstaller/PySide6 versions. It creates the executable,
copies external resources, runs an isolated packaged smoke test, then writes
`dist/Planner-0.1.1-alpha-Windows.zip` for the current version. The filename uses the shared version in
`planner-main/planner_app/version.py`, which also supplies the About dialog.
The extracted directory is:

```text
Planner/
  Planner.exe
  furnishings/
  themes/
  textures/
  assets/fonts/
  help/
  _internal/
```

Ship the entire folder or ZIP. Furnishing definitions and artwork, fonts and
their notices, themes, textures, help pages and images are ordinary external files beside
the executable. Edits and additions use these folders and require restarting
Planner, rather than rebuilding the executable. Source runs continue using
`planner-main/` for all resources. All paths are independent of the working
directory used to launch the app.

`_internal/` holds Python, Qt and its plugins, compiled application modules,
icons, cursors, startup defaults, vendor JavaScript and license notices.
The notices include the complete GPLv3 text (COPYING), original graphics and
branding terms, and third-party notices. They are available in the Licenses
window. A binary release must also provide its matching corresponding source;
see [release guidance](RELEASING.md).
Developer docs, tests, build scripts and private workspace data are excluded.
Application preferences and recovery files still use the normal user-data paths.
The QtQml hook includes QJSEngine and its library dependencies for optimized PNG,
without collecting unused QML UI plugins. Dependency discovery uses a restricted
PATH so DLLs from unrelated installed tools do not enter the bundle.

The build replaces generated `dist/Planner/`. Maintain resources in the source
directories under `planner-main/`; edits to a previous build are not build inputs.

The executable icon is generated from the existing `assets/planner.svg` into
`build/windows/Planner.ico`. No source artwork is rewritten.

## Verification

The build launches `Planner.exe --smoke-test REPORT` with the offscreen platform,
a different working directory and temporary startup/session/preferences paths.
It checks resource locations, catalog and themes, font loading, project encoding,
help and GIF support, PNG/SVG rendering and optimized PNG's JavaScript runtime.
No normal app window opens and existing user state is not read or modified.

`build/windows/smoke-report.json` contains the result. The adjacent
`external-resources.json` records hashes of external distribution files. Source
help files are copied unchanged.

For a release, also try the extracted ZIP on a Windows machine without Python,
check native file dialogs and normal canvas interactions, and verify the app's
license notices. A build on the developer machine is not that independent test.

The manual **Build Windows** GitHub Actions workflow builds and smoke-tests the
same ZIP, then retains it as an artifact. It does not create or publish a release.
