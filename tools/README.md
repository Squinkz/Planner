# Developer tools

Run these from the repository root with the development environment active.

- `capture_rendering.py`: launch an interactive instrumented Planner session.
- `native_render_soak.py`: Windows memory and event-loop soak test.
- `diagnostic_overhead_probe.py`: measure diagnostic-wrapper overhead.
- `icon_cache_probe.py`: exercise artwork-cache retention across themes.
- `pan_pacing_20261022.py`: controlled input-stream and repaint-pacing probe.
- `verify_repository.py`: review Git's selected file roots, caches and large files.
- `build_windows.py`: build and verify the Windows executable and ZIP. See
  [Windows build](../docs/WINDOWS_BUILD.md). `Planner.spec`, `windows_entry.py`
  and `frozen_smoke.py` support this build.

Usage, report fields and interpretation are in
[Rendering diagnostics](../docs/RENDER_DIAGNOSTICS.md).
Outputs go to the ignored `diagnostics/` directory. Historical one-off scripts
and downloaded tools in the original workspace are not repository dependencies.
