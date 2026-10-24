# Checks

Run from the repository root after installing `requirements-dev.txt`:

```powershell
python checks/run_checks.py
python checks/run_checks.py check_export_plan.py check_portable_parity.py
```

The runner executes each check in a separate process with temporary application
preferences, session and startup paths. It records failures from assertions and
unhandled Qt callbacks or threads. Python assertions must remain enabled.

`fixtures/` contains frozen reference implementations and render baselines.
[Synthetic plans](fixtures/plans/README.md) replace dependencies on personal
workspace drawings. They are test inputs, not application startup files or demos.

The runner creates ignored `diagnostics/`, `screenshots/` and `tmp/` output
directories as needed. Do not add generated captures as reference baselines
without reviewing their purpose and expected appearance.
