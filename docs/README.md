# Planner documentation

## User help

[Welcome to Planner](../planner-main/docs/help/README.md) contains the quickstart and linked user guide.
Everyday drawing, editing, search, appearance, project and export instructions
belong there. These pages also appear in the application's Help window.

## Development and implementation

- [Development setup, command-line export and checks](DEVELOPMENT.md)
- [Windows executable build](WINDOWS_BUILD.md)
- [Licensing and redistribution](LICENSING.md)
- [Releases and version numbers](RELEASING.md)
- [Architecture and source layout](ARCHITECTURE.md)
- [Portable numeric geometry contracts](GEOMETRY.md)
- [Editing transactions and desktop adapter boundaries](EDITING_PORTS.md)
- [Help authoring and viewer contract](HELP_AUTHORING.md)
- [Rendering diagnostics and performance probes](RENDER_DIAGNOSTICS.md)

## Resource authoring

These describe resource files and rendering contracts, rather than operating
the application. Paths in them identify resources under `planner-main/`.

- [Furnishing definitions, compounds and SVG artwork](resources/FURNISHINGS.md)
- [UI and canvas theme schemas](resources/THEMES.md)
- [Normal maps, AO companions and filename defaults](resources/TEXTURES.md)
- [UI icons, cursor assets and temporary About logo](resources/ASSETS.md)
- [Font resources and rendering](resources/FONTS.md)

## Future ports and parity

[The parity specification](parity/README.md) indexes behavior contracts, project
interchange, framework differences, executable workflows and reference renders.
It records implementation and acceptance requirements; it is not a second
user manual.

## Documentation maintenance

Keep technical documentation in this folder. The repository-root README
is the entry point; bundled third-party package notes and license notices stay
with their resources. Move user workflows into Help and link to them from
technical references instead of maintaining duplicate tutorials.
Changes to `planner-main/docs/help/` require an explicit user request. Routine implementation
changes may update technical contracts without changing the help pages.

From the workspace root, validate local links, organization and help with:

```text
python checks/run_checks.py check_documentation_links.py check_help_docs.py check_help_viewer.py
```
