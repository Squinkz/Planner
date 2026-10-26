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

Checks normally have a 30-second timeout. Repeated render and guide-selection session integration checks
have 60 seconds, and the full external-theme, CLI export and selection-overlay matrices have 120 seconds to allow
for slower hosted Windows workers. These are hang limits, not performance targets.

`fixtures/` contains frozen reference implementations and render baselines.
[Synthetic plans](fixtures/plans/README.md) replace dependencies on personal
workspace drawings. They are test inputs, not application startup files or demos.

The runner creates ignored `diagnostics/`, `screenshots/` and `tmp/` output
directories as needed. Do not add generated captures as reference baselines
without reviewing their purpose and expected appearance.

The current UI and file contracts are indexed in
[parity verification](../docs/parity/VERIFICATION.md). In particular,
`check_export_dimension_settings.py` covers sparse export overrides versus
Options' project settings. `check_export_dimension_overrides.py` covers precision
and split overrides, shared controls and leaving Export when Options opens, while `check_hover_click_targets.py` and
`check_line_vertex_priority.py` check active hover against actual click targets.
Historical screenshots are not substitutes for those current interaction checks.

Activity Log coverage: `check_activity_log.py` checks journal restoration,
persistence, branches and expiry. `check_activity_events.py` checks issue and
recovery events, settings, checkpoint storage and safe decoding. See
[Activity Log](../docs/ACTIVITY_LOG.md).

Dimension visibility: `check_exterior_hidden_dimensions.py` covers hidden
openings/walls in every wall mode. `check_selection_dimension_overlay.py` checks
that selection, control points and group bounds do not modify ambient chains or
stack tiers. Both include rotated geometry and PNG/SVG output.
`check_dimension_action_policy.py` covers action eligibility across opening
types, wall modes, split settings, facing and hidden state, including inward
Exterior's orientation-independent splits and stacked mode's effective split-all behavior.
`check_exterior_binary_splits.py` checks Exterior's two-position selectors,
reset, stored All-mode preferences, facing/flip independence and PNG/SVG output.
`check_stacked_dimension_rounding.py` checks that upper labels sum their displayed
inner spans in every unit/precision, without altering geometry, including both
wall references and PNG/SVG rendering.
