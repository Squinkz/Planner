# Checks

Run from the repository root after installing `requirements-dev.txt`:

```powershell
python checks/run_checks.py
python checks/run_checks.py check_export_plan.py check_portable_parity.py
```

The runner executes each check in a separate process with temporary application
preferences, session and startup paths. It records failures from assertions and
unhandled Qt callbacks or threads. Python assertions must remain enabled.

Resolve temporary fixture roots with `Path(directory).resolve()` before comparing
them with paths returned by the app. Hosted Windows runners can expose TEMP
through an 8.3 alias such as `RUNNER~1`, while file dialogs and the app return
the canonical path.

Checks normally have a 30-second timeout. Repeated render integration checks
have 60 seconds, and the full external-theme matrix has 120 seconds to allow
for slower hosted Windows workers. These are hang limits, not performance targets.

`fixtures/` contains frozen reference implementations and render baselines.
[Synthetic plans](fixtures/plans/README.md) replace dependencies on personal
workspace drawings. They are test inputs, not application startup files or demos.

The runner creates ignored `diagnostics/`, `screenshots/` and `tmp/` output
directories as needed. Do not add generated captures as reference baselines
without reviewing their purpose and expected appearance.
